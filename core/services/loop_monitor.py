"""事件循环卡顿监控服务

主循环每 tick 更新心跳时间戳, 独立守护线程检测心跳停滞。
超过阈值时打印主线程当前调用栈, 定位阻塞事件循环的同步代码
(此类卡顿会连锁引发 Redis 读超时 / MySQL 连接池获取超时等误报)。

同时周期检查进程打开的文件描述符数量, 接近 ulimit 上限时告警并
统计 fd 类型分布 (socket / 普通文件 / pipe 等), 定位 fd 泄漏来源
(fd 耗尽会导致新建 MySQL/Redis 连接失败、SQLite 无法打开等连锁故障)。
"""

import asyncio
import os
import sys
import threading
import time
import traceback
from collections import Counter

try:
    import resource
except ImportError:  # Windows 无 resource 模块
    resource = None  # type: ignore[assignment]

from core.base.logger import SERVICE, get_logger

log = get_logger(SERVICE, '循环监控')


class LoopMonitorService:
    """检测 asyncio 事件循环长时间无法调度的卡顿并输出主线程堆栈"""

    def __init__(self, tick: float = 0.5, stall_threshold: float = 2.0, fd_check_interval: float = 60.0, fd_warn_ratio: float = 0.8):
        self._tick = tick
        self._threshold = stall_threshold
        self._fd_interval = fd_check_interval
        self._fd_ratio = fd_warn_ratio
        self._fd_warned = False
        self._task = None
        self._thread = None
        self._stop = threading.Event()
        self._last_beat = time.monotonic()
        self._main_thread_id = threading.main_thread().ident

    async def _heartbeat(self):
        while True:
            self._last_beat = time.monotonic()
            await asyncio.sleep(self._tick)

    def _dump_main_stack(self):
        frame = sys._current_frames().get(self._main_thread_id)
        if frame is None:
            return '<无法获取主线程堆栈>'
        return ''.join(traceback.format_stack(frame))

    @staticmethod
    def _fd_limit():
        if resource is None:
            return -1
        try:
            return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        except Exception:
            return -1

    def _check_fds(self):
        try:
            fds = os.listdir('/proc/self/fd')
        except OSError:
            return
        limit = self._fd_limit()
        if limit <= 0:
            return
        used = len(fds)
        if used < limit * self._fd_ratio:
            self._fd_warned = False
            return
        if self._fd_warned:
            return
        self._fd_warned = True
        kinds = Counter()
        for fd in fds:
            try:
                target = os.readlink(f'/proc/self/fd/{fd}')
            except OSError:
                continue
            if target.startswith(('socket:', 'pipe:', 'anon_inode:')):
                kinds[target.split(':')[0]] += 1
            else:
                kinds[os.path.dirname(target) or target] += 1
        top = ', '.join(f'{k}={v}' for k, v in kinds.most_common(8))
        log.error(f'文件描述符即将耗尽: {used}/{limit} — fd 分布: {top}')

    def _watch(self):
        stall_reported = False
        stall_start = 0.0
        next_fd_check = time.monotonic()
        while not self._stop.wait(self._tick):
            now = time.monotonic()
            if now >= next_fd_check:
                next_fd_check = now + self._fd_interval
                self._check_fds()
            lag = now - self._last_beat
            if lag >= self._threshold:
                if not stall_reported:
                    stall_reported = True
                    stall_start = self._last_beat
                    log.error(f'检测到事件循环卡顿 ≥{lag:.1f}s, 主线程当前堆栈:\n{self._dump_main_stack()}')
            elif stall_reported:
                stall_reported = False
                log.warning(f'事件循环恢复, 本次卡顿约 {time.monotonic() - stall_start - self._tick:.1f}s')

    def start(self):
        self._last_beat = time.monotonic()
        self._task = asyncio.create_task(self._heartbeat())
        self._thread = threading.Thread(target=self._watch, name='loop-monitor', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            self._task = None
