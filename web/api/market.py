"""插件市场路由: /api/market/*"""

from aiohttp import web

import web.auth as auth
import web.tools._market.install as _install
import web.tools._market.local as _local
import web.tools._market.market as _market


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/market/list', _(_market.handle_market_list)),
        web.get('/api/market/categories', _(_market.handle_market_categories)),
        web.post('/api/market/detail', _(_market.handle_market_detail)),
        web.post('/api/market/refresh', _(_market.handle_market_refresh)),
        web.post('/api/market/preview', _(_install.handle_market_preview)),
        web.post('/api/market/install', _(_install.handle_market_install)),
        web.post('/api/market/uninstall', _(_install.handle_market_uninstall)),
        web.get('/api/market/local', _(_local.handle_local_plugins)),
        web.post('/api/market/local/read', _(_local.handle_local_plugin_read)),
        web.post('/api/market/local/save', _(_local.handle_local_plugin_save)),
        web.get('/api/market/mirror', _(_market.handle_market_get_mirror)),
        web.post('/api/market/mirror', _(_market.handle_market_set_mirror)),
        web.post('/api/market/mirror/test', _(_market.handle_market_test_mirror)),
    ]
