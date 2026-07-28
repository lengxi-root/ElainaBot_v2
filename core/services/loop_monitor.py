"""事件循环卡顿监控服务"""

import asyncio
import time

from core.base.logger import SYSTEM, get_logger

log = get_logger(SYSTEM, '循环监控')


class LoopMonitorService:
    """定期心跳检测事件循环延迟, 超过阈值时告警

    事件循环被同步阻塞 (CPU 密集/同步 IO) 时, sleep 的实际唤醒时间会晚于预期,
    差值即为循环被卡住的时长。用于定位 Redis/MySQL/HTTP 集中超时的根因。
    """

    def __init__(self, interval: float = 1.0, threshold: float = 1.0):
        self._interval = interval
        self._threshold = threshold
        self._task = None

    async def __call__(self):
        while True:
            start = time.monotonic()
            await asyncio.sleep(self._interval)
            lag = time.monotonic() - start - self._interval
            if lag >= self._threshold:
                log.warning(
                    f'事件循环卡顿 {lag:.2f}s — 存在同步阻塞操作 '
                    f'(CPU 密集/同步 IO), 期间所有协程被拖慢, 可能引发 Redis/MySQL 集中超时'
                )

    def start(self):
        self._task = asyncio.create_task(self())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
