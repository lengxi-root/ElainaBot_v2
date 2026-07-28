"""事件循环卡顿监控服务

主循环每 tick 更新心跳时间戳, 独立守护线程检测心跳停滞。
超过阈值时打印主线程当前调用栈, 定位阻塞事件循环的同步代码
(此类卡顿会连锁引发 Redis 读超时 / MySQL 连接池获取超时等误报)。

卡顿归因: 堆栈采样落在 recv/select/getpeername 等微秒级系统调用上时,
说明并非该行代码慢, 而是整个进程被暂停 — 常见元凶是 gen2 GC 全量回收
(在任意内存分配点触发) 或内存换页 (swap)。因此额外挂 gc 回调统计每次
回收耗时, 并采样 /proc/self/stat 的 majflt (缺页中断) 区分两者。
"""

import asyncio
import gc
import os
import sys
import threading
import time
import traceback

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]

from core.base.logger import SERVICE, get_logger

log = get_logger(SERVICE, '循环监控')

_GC_SLOW_SECONDS = 0.3  # 单次 GC 超过该耗时直接告警


class LoopMonitorService:
    """检测 asyncio 事件循环长时间无法调度的卡顿并输出主线程堆栈"""

    def __init__(self, tick: float = 0.5, stall_threshold: float = 2.0):
        self._tick = tick
        self._threshold = stall_threshold
        self._task = None
        self._thread = None
        self._stop = threading.Event()
        self._last_beat = time.monotonic()
        self._main_thread_id = threading.main_thread().ident
        # GC 统计 (gc 回调在触发回收的线程执行, 主线程为主; 简单赋值线程安全)
        self._gc_start = 0.0
        self._gc_total_time = 0.0  # 累计 GC 耗时
        self._gc_last_slow = ''  # 最近一次慢 GC 描述

    # ===== GC 探针 =====

    def _gc_callback(self, phase, info):
        if phase == 'start':
            self._gc_start = time.monotonic()
            return
        elapsed = time.monotonic() - self._gc_start
        self._gc_total_time += elapsed
        if elapsed >= _GC_SLOW_SECONDS:
            desc = f'gen{info.get("generation")} 回收 {info.get("collected", 0)} 个对象, 耗时 {elapsed:.2f}s'
            self._gc_last_slow = desc
            log.warning(f'GC 暂停: {desc} (期间事件循环完全冻结)')

    # ===== 资源采样 (Linux) =====

    @staticmethod
    def _read_fd_count():
        """当前进程打开的 fd 数 (逼近 ulimit 时 socket/epoll 会大量报 Errno 24)"""
        try:
            return len(os.listdir('/proc/self/fd'))
        except OSError:
            return -1

    @staticmethod
    def _read_majflt():
        """读取进程累计 major page fault 次数 (换页/swap 会使其暴涨)"""
        try:
            with open('/proc/self/stat') as f:
                return int(f.read().split(')')[-1].split()[9])
        except (OSError, ValueError, IndexError):
            return -1

    def _dump_main_stack(self):
        frame = sys._current_frames().get(self._main_thread_id)
        if frame is None:
            return '<无法获取主线程堆栈>'
        return ''.join(traceback.format_stack(frame))

    def _watch(self):
        stall_reported = False
        stall_start = 0.0
        gc_time_at_stall = 0.0
        majflt_at_stall = -1
        while not self._stop.wait(self._tick):
            lag = time.monotonic() - self._last_beat
            if lag >= self._threshold:
                if not stall_reported:
                    stall_reported = True
                    stall_start = self._last_beat
                    gc_time_at_stall = self._gc_total_time
                    majflt_at_stall = self._read_majflt()
                    self._gc_last_slow = ''
                    log.error(f'检测到事件循环卡顿 ≥{lag:.1f}s, 主线程当前堆栈:\n{self._dump_main_stack()}')
            elif stall_reported:
                stall_reported = False
                total = time.monotonic() - stall_start - self._tick
                gc_time = self._gc_total_time - gc_time_at_stall
                majflt_now = self._read_majflt()
                majflt_delta = majflt_now - majflt_at_stall if majflt_now >= 0 and majflt_at_stall >= 0 else -1
                cause = []
                if gc_time >= total * 0.5:
                    cause.append(f'GC 占 {gc_time:.1f}s{f" ({self._gc_last_slow})" if self._gc_last_slow else ""}')
                elif gc_time > 0:
                    cause.append(f'GC 占 {gc_time:.1f}s')
                if majflt_delta > 100:
                    cause.append(f'major 缺页 +{majflt_delta} (内存换页/swap, 检查系统内存)')
                fd_count = self._read_fd_count()
                if fd_count > 0 and resource is not None:
                    soft_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                    if fd_count >= soft_limit * 0.8:
                        cause.append(f'fd 已用 {fd_count}/{soft_limit} (接近上限, 将触发 Errno 24)')
                log.warning(
                    f'事件循环恢复, 本次卡顿约 {total:.1f}s'
                    + (f' — 归因: {"; ".join(cause)}' if cause else ' — 期间无 GC/换页, 疑似宿主机 CPU 争抢或同步阻塞代码')
                )

    def start(self):
        self._last_beat = time.monotonic()
        self._task = asyncio.create_task(self._heartbeat())
        if self._gc_callback not in gc.callbacks:
            gc.callbacks.append(self._gc_callback)
        self._thread = threading.Thread(target=self._watch, name='loop-monitor', daemon=True)
        self._thread.start()

    async def _heartbeat(self):
        while True:
            self._last_beat = time.monotonic()
            await asyncio.sleep(self._tick)

    def stop(self):
        self._stop.set()
        if self._gc_callback in gc.callbacks:
            gc.callbacks.remove(self._gc_callback)
        if self._task:
            self._task.cancel()
            self._task = None
