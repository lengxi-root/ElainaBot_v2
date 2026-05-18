"""Web 面板 API 路由聚合 — 按模块拆分路由注册"""

from aiohttp import web

import web.ws as panel_ws

# 导入所有路由模块
from web.api import (
    auth,
    bots,
    config,
    database,
    market,
    messages,
    modules,
    openapi,
    plugins,
    stats,
    update,
    web_pages,
)
from web.api import shared as _shared

_ROUTE_MODULES = [
    auth,
    bots,
    plugins,
    modules,
    config,
    messages,
    stats,
    update,
    openapi,
    database,
    web_pages,
    market,
]


def get_routes() -> list:
    """聚合所有模块路由 + WebSocket/SSE"""
    routes = []
    for mod in _ROUTE_MODULES:
        routes.extend(mod.get_routes())
    # WebSocket / SSE
    routes.extend(
        [
            web.get('/ws/panel', panel_ws.handle_ws),
            web.get('/api/sse/panel', panel_ws.handle_sse),
        ]
    )
    return routes


def set_context(bot_manager, base_dir: str):
    """注入运行时上下文到所有工具模块 (保持与旧 api.py 兼容)"""
    _shared.set_context(bot_manager, base_dir)

    import web.tools._bot.info as robot_info
    import web.tools._bot.restart as bot_restart
    import web.tools._config.handler as config_handler
    import web.tools._database.browser as database_browser
    import web.tools._market.shared as market_shared
    import web.tools._openapi.handler as openapi_handler
    import web.tools._plugin_mgr.shared as _plugin_shared
    import web.tools._stats.statistics as statistics_handler
    import web.tools._stats.system as system_info
    import web.tools._updater.handlers as update_handler

    robot_info.set_context(bot_manager)
    _plugin_shared.set_context(base_dir, bot_manager)
    config_handler.set_context(base_dir)
    from web.tools._message.shared import set_context as _msg_set_ctx

    _msg_set_ctx(base_dir, bot_manager)
    statistics_handler.set_context(bot_manager)
    update_handler.set_context(base_dir)
    bot_restart.set_context(base_dir)
    system_info.set_context(bot_manager)
    openapi_handler.set_context(base_dir)
    market_shared.set_context(base_dir)
    database_browser.set_context(bot_manager, base_dir)
