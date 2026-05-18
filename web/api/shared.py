"""API 路由共享工具 (上下文引用 + 日志查询辅助)"""

import asyncio

from aiohttp import web

from core.application import get_app
from core.storage.log import SharedLogService

# 向后兼容: set_context 保留但实际从 Application 获取上下文
_bot_manager = None
_base_dir = ''


def set_context(bot_manager, base_dir: str):
    """注入全局上下文 (由 web/api/__init__.py 调用)"""
    global _bot_manager, _base_dir
    _bot_manager = bot_manager
    _base_dir = base_dir


def get_bot_manager():
    """获取 BotManager/Application (优先从 Application, 回退到兼容全局)"""
    app = get_app()
    if app:
        return app
    return _bot_manager


def get_base_dir():
    """获取项目根目录"""
    app = get_app()
    if app:
        return app._base_dir
    return _base_dir


def _resolve_bot_manager():
    """解析 BotManager/Application 引用"""
    return get_app() or _bot_manager


def _iter_bots(appid_filter=''):
    """按 appid 过滤机器人迭代器"""
    bm = _resolve_bot_manager()
    if not bm:
        return []
    if appid_filter and appid_filter in bm._bots:
        return [(appid_filter, bm._bots[appid_filter])]
    return list(bm._bots.items())


_LOG_SQL = 'SELECT * FROM log ORDER BY id DESC LIMIT 50'


def _query_bot_logs(log_type, appid_filter, post_fn=None):
    """从各机器人 SQLite 查询日志 (同步)"""
    results = []
    for appid, inst in _iter_bots(appid_filter):
        try:
            rows = inst.log_service.query(log_type, _LOG_SQL)
            for r in rows:
                r['appid'] = appid
                r['bot_name'] = getattr(inst, 'name', appid)
                if post_fn:
                    post_fn(r)
            results.extend(rows)
        except Exception:
            pass
    results.sort(key=lambda r: r.get('id', 0))
    return results[-50:]


def _tag_direction(r):
    if r.get('direction') == 'send':
        r['is_bot'] = True


def _tag_lifecycle_extra(r):
    if r.get('extra'):
        r['raw_message'] = r['extra']


def _gather_recent_logs_sync(appid_filter):
    """同步聚合所有日志查询 (在 executor 中执行)"""
    messages = _query_bot_logs('message', appid_filter, _tag_direction)
    lifecycle = _query_bot_logs('lifecycle', appid_filter, _tag_lifecycle_extra)
    shared = SharedLogService._instance
    if shared:
        framework = shared.query('framework', _LOG_SQL)
        framework.reverse()
        errors = shared.query('error', _LOG_SQL)
        errors.reverse()
    else:
        framework = []
        errors = []
    return {
        'message': messages,
        'framework': framework,
        'error': errors,
        'lifecycle': lifecycle,
    }


async def handle_recent_logs(request: web.Request):
    appid_filter = request.query.get('appid', '')
    loop = asyncio.get_running_loop()
    payload = await loop.run_in_executor(None, _gather_recent_logs_sync, appid_filter)
    return web.json_response(payload)
