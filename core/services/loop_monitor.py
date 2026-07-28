"""事件循环卡顿监控服务

主循环每 tick 更新心跳时间戳, 独立守护线程检测心跳停滞。
超过阈值时打印主线程当前调用栈, 定位阻塞事件循环的同步代码
(此类卡顿会连锁引发 Redis 读超时 / MySQL 连接池获取超时等误报)。
"""

import asyncio
import sys
import threading
import time
import traceback

from core.base.logger import SERVICE, get_logger

log = get_logger(SERVICE, '循环监控')


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

    async def _heartbeat(self):
        while True:
            self._last_beat = time.monotonic()
            await asyncio.sleep(self._tick)

    def _dump_main_stack(self):
        frame = sys._current_frames().get(self._main_thread_id)
        if frame is None:
            return '<无法获取主线程堆栈>'
        return ''.join(traceback.format_stack(frame))

    def _watch(self):
        stall_reported = False
        stall_start = 0.0
        while not self._stop.wait(self._tick):
            lag = time.monotonic() - self._last_beat
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
