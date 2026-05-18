"""OpenAPI 路由: /api/openapi/*"""

from aiohttp import web

import web.auth as auth
import web.tools._openapi.handler as handler


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.post('/api/openapi/start-login', _(handler.handle_start_login)),
        web.post('/api/openapi/check-login', _(handler.handle_check_login)),
        web.post('/api/openapi/login-status', _(handler.handle_get_login_status)),
        web.post('/api/openapi/verify-login', _(handler.handle_verify_saved_login)),
        web.post('/api/openapi/logout', _(handler.handle_logout)),
        web.post('/api/openapi/botlist', _(handler.handle_get_botlist)),
        web.post('/api/openapi/botdata', _(handler.handle_get_botdata)),
        web.post('/api/openapi/notifications', _(handler.handle_get_notifications)),
        web.post('/api/openapi/whitelist', _(handler.handle_get_whitelist)),
        web.post('/api/openapi/whitelist/update', _(handler.handle_update_whitelist)),
        web.post('/api/openapi/whitelist/delete-qr', _(handler.handle_get_delete_qr)),
        web.post(
            '/api/openapi/whitelist/check-delete-auth',
            _(handler.handle_check_delete_auth),
        ),
        web.post('/api/openapi/whitelist/execute-delete', _(handler.handle_execute_delete_ip)),
        web.post('/api/openapi/whitelist/batch-add', _(handler.handle_batch_add_whitelist)),
    ]
