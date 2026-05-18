"""更新路由: /api/update/*"""

from aiohttp import web

import web.auth as auth
import web.tools._updater.handlers as handler


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/update/changelog', _(handler.handle_get_changelog)),
        web.get('/api/update/version', _(handler.handle_get_current_version)),
        web.get('/api/update/check', _(handler.handle_check_update)),
        web.post('/api/update/start', _(handler.handle_start_update)),
        web.get('/api/update/progress', _(handler.handle_get_update_progress)),
        web.get('/api/update/mirrors', _(handler.handle_get_mirrors)),
        web.get('/api/update/test-mirrors', _(handler.handle_test_mirrors)),
        web.post('/api/update/mirror', _(handler.handle_set_custom_mirror)),
        web.post('/api/update/upload', _(handler.handle_upload_update)),
        web.get('/api/update/environment', _(handler.handle_detect_environment)),
    ]
