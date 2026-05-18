"""模块管理路由: /api/modules/*"""

from aiohttp import web

import web.auth as auth
import web.tools._plugin_mgr.module as _module


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/modules/scan', _(_module.handle_scan_modules)),
        web.post('/api/modules/toggle', _(_module.handle_module_toggle)),
        web.post('/api/modules/upload', _(_module.handle_module_upload)),
    ]
