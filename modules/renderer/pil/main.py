#!/usr/bin/env python
"""PIL 子进程渲染池子引擎

CPU 密集的 PIL 渲染放到独立子进程执行 (独立 GIL, 不卡主进程事件循环),
全局单例供所有插件共享。按需 fork 创建, 空闲自动回收, 崩溃自动重建。

插件中获取:
    pil = bot.module_manager.get("renderer").pil
    img_data, w, h = await pil.render(_render_sync, arg1, arg2)  # 函数与参数须可 pickle

配置: renderer 模块 data/pil.yaml
"""

import asyncio
import contextlib
import multiprocessing
import pickle
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from core.base.logger import EXTENSION, get_logger
from modules.renderer.base import IdleEngine

log = get_logger(EXTENSION, 'PIL渲染池')

_DEFAULTS = {
    'workers': 2,
    'max_concurrent': 4,
    'idle_timeout': 300,
    'task_timeout': 60,
}

_COMMENTS = {
    'workers': '渲染子进程数',
    'max_concurrent': '最大并发渲染任务数 (超出排队)',
    'idle_timeout': '进程池空闲回收 (秒), 回收后下次使用时重建',
    'task_timeout': '单次渲染超时 (秒)',
}


def _invoke(fn, args, kwargs):
    """子进程侧执行入口"""
    return fn(*args, **kwargs)


class PILRenderPool(IdleEngine):
    """PIL 子进程渲染池 (按需创建, 空闲回收, 崩溃重建)"""

    __slots__ = ('_pool',)

    def __init__(self, cfg):
        super().__init__(cfg, cfg.get('max_concurrent', 4))
        self._pool = None

    async def render(self, fn, *args, **kwargs):
        """在子进程池执行同步渲染函数并返回结果"""
        if self._closed:
            raise RuntimeError('PIL 渲染池已关闭')
        try:
            pickle.dumps((fn, args, kwargs))
        except Exception as e:
            raise ValueError(f'{getattr(fn, "__name__", fn)} 参数不可 pickle, 无法提交到子进程渲染: {e}') from e

        async with self._semaphore:
            self._active += 1
            try:
                return await self._run_in_pool(fn, args, kwargs, retried=False)
            finally:
                self._active -= 1
                self._mark_released()

    async def _run_in_pool(self, fn, args, kwargs, retried):
        pool = await self._ensure_pool()
        loop = asyncio.get_running_loop()
        try:
            fut = loop.run_in_executor(pool, _invoke, fn, args, kwargs)
            return await asyncio.wait_for(fut, timeout=self._cfg.get('task_timeout', 60))
        except BrokenProcessPool as e:
            await self._discard_pool()
            if retried:
                raise RuntimeError('PIL 渲染进程池连续崩溃') from e
            log.warning('渲染进程池崩溃, 重建后重试')
            return await self._run_in_pool(fn, args, kwargs, retried=True)

    async def _ensure_pool(self):
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            try:
                mp_ctx = multiprocessing.get_context('fork')
            except ValueError as e:
                raise RuntimeError('当前平台不支持 fork, PIL 子进程渲染池不可用') from e
            workers = self._cfg.get('workers', 2)
            # fork 继承已加载的插件模块, 子进程可直接执行插件的渲染函数
            self._pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp_ctx)
            log.info(f'PIL 渲染进程池已创建 ({workers} worker)')
            self._start_idle_cleanup(60)
            return self._pool

    async def _discard_pool(self):
        async with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            with contextlib.suppress(Exception):
                pool.shutdown(wait=False, cancel_futures=True)

    async def _release_idle(self):
        if self._pool is not None:
            await self._discard_pool()
            log.info('PIL 渲染进程池空闲回收')

    async def close(self):
        self._closed = True
        self._stop_idle_cleanup()
        await self._discard_pool()
