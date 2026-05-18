"""配置路由: /api/config*, /api/config-file/*"""

from aiohttp import web

import web.auth as auth
import web.tools._config.handler as config_handler
import web.tools._plugin_mgr.config as _plugin_config


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/config', _(config_handler.handle_get_config)),
        web.post('/api/config/save', _(config_handler.handle_save_config)),
        web.post('/api/config-file/read', _(_plugin_config.handle_read_config)),
        web.post('/api/config-file/save', _(_plugin_config.handle_save_config)),
    ]
