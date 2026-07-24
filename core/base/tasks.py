"""后台任务管理 — 持有 fire-and-forget 任务的强引用, 防止被 GC 提前回收"""

import asyncio
from collections.abc import Coroutine
from typing import Any

_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """创建后台任务并持有强引用, 完成后自动释放。

    事件循环仅持有任务的弱引用, 裸 create_task 的返回值若不保存,
    任务可能在执行中途被垃圾回收 (CPython 官方文档明确警告)。
    """
    task = asyncio.get_running_loop().create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
