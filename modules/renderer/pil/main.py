#!/usr/bin/env python
"""PIL 子进程渲染池子引擎

CPU 密集的 PIL 渲染放到独立子进程执行, 子进程拥有独立 GIL, 渲染再重也不会
与主进程事件循环争抢 GIL (线程池渲染大图会饿死事件循环, 造成秒级卡顿)。
全局单例, 供所有插件共享, 不再每个插件各开一个渲染池。

插件中获取 (经渲染引擎模块):
    pil = bot.module_manager.get("renderer").pil

    # 渲染函数须为模块级函数, 参数与返回值可 pickle
    img_data, w, h = await pil.render(_render_sync, arg1, arg2)

按需 fork 创建 (继承已加载的插件模块), 空闲自动回收 (释放内存, 热重载后
新代码随重建生效), 崩溃自动重建; 不可用时回退线程池, 功能不受影响。

配置文件 (renderer 模块 data/ 下自动生成):
    pil.yaml → workers / idle_timeout / task_timeout 等
"""

import asyncio
import contextlib
import multiprocessing
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from core.base.logger import EXTENSION, get_logger

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


class PILRenderPool:
    """PIL 子进程渲染池 (按需创建, 空闲回收, 崩溃重建)"""

    __slots__ = (
        '_cfg',
        '_pool',
        '_lock',
        '_semaphore',
        '_active',
        '_last_release',
        '_cleanup_task',
        '_closed',
    )

    def __init__(self, cfg):
        self._cfg = cfg
        self._pool = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(cfg.get('max_concurrent', 4))
        self._active = 0
        self._last_release = 0.0
        self._cleanup_task = None
        self._closed = False

    def is_available(self):
        return not self._closed

    async def render(self, fn, *args, **kwargs):
        """在子进程池执行同步渲染函数并返回结果 (不可用时回退线程池)"""
        if self._closed:
            raise RuntimeError('PIL 渲染池已关闭')
        try:
            pickle.dumps((fn, args, kwargs))
        except Exception:
            log.warning(f'{getattr(fn, "__name__", fn)} 参数不可 pickle, 回退线程池执行')
            return await asyncio.to_thread(fn, *args, **kwargs)

        async with self._semaphore:
            self._active += 1
            try:
                return await self._run_in_pool(fn, args, kwargs, retried=False)
            finally:
                self._active -= 1
                self._last_release = time.monotonic()

    async def _run_in_pool(self, fn, args, kwargs, retried):
        pool = await self._ensure_pool()
        if pool is None:
            return await asyncio.to_thread(fn, *args, **kwargs)
        loop = asyncio.get_running_loop()
        try:
            fut = loop.run_in_executor(pool, _invoke, fn, args, kwargs)
            return await asyncio.wait_for(fut, timeout=self._cfg.get('task_timeout', 60))
        except BrokenProcessPool:
            await self._discard_pool()
            if retried:
                log.error('渲染进程池连续崩溃, 回退线程池执行')
                return await asyncio.to_thread(fn, *args, **kwargs)
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
            except ValueError:
                log.warning('当前平台不支持 fork, 渲染回退线程池')
                return None
            workers = self._cfg.get('workers', 2)
            # fork 继承主进程已加载的插件模块, 子进程可直接执行插件的渲染函数
            self._pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp_ctx)
            log.info(f'PIL 渲染进程池已创建 ({workers} worker)')
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._idle_cleanup())
            return self._pool

    async def _discard_pool(self):
        async with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            with contextlib.suppress(Exception):
                pool.shutdown(wait=False, cancel_futures=True)

    async def _idle_cleanup(self):
        """空闲超时后回收子进程 (释放内存, 也让插件热重载后的新代码生效)"""
        idle_timeout = self._cfg.get('idle_timeout', 300)
        while True:
            await asyncio.sleep(60)
            if (
                self._pool is not None
                and self._active == 0
                and self._last_release
                and time.monotonic() - self._last_release >= idle_timeout
            ):
                await self._discard_pool()
                log.info('PIL 渲染进程池空闲回收')

    async def close(self):
        """模块卸载时调用: 停止清理任务并关闭进程池"""
        self._closed = True
        task, self._cleanup_task = self._cleanup_task, None
        if task and not task.done():
            task.cancel()
        pool, self._pool = self._pool, None
        if pool is not None:
            with contextlib.suppress(Exception):
                pool.shutdown(wait=False, cancel_futures=True)
