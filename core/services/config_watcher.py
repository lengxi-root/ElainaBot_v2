"""配置热加载轮询服务"""

import asyncio
import contextlib

from core.base.config import cfg


class ConfigWatcherService:
    """定期检查配置文件变更并触发热加载"""

    def __init__(self, interval: float = 5.0):
        self._interval = interval
        self._task = None

    async def __call__(self):
        """可直接作为 asyncio.create_task() 的协程"""
        while True:
            await asyncio.sleep(self._interval)
            with contextlib.suppress(Exception):
                await cfg.reload_if_changed('bot', 'settings', 'templates')

    def start(self):
        self._task = asyncio.create_task(self())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
