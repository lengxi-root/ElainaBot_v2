"""鉴权路由: /api/auth/*"""

from aiohttp import web

import web.auth as auth
from core.base.config import cfg

_WEAK_PASSWORDS = frozenset({'admin', '123456', 'password', 'admin123', '12345678'})


async def handle_login(request: web.Request):
    ip = auth.get_real_ip(request)
    auth.cleanup_expired_ip_bans()
    if auth.is_ip_banned(ip):
        return web.json_response({'success': False, 'error': 'IP 已被封禁'}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({'success': False, 'error': '请求格式错误'}, status=400)

    password = body.get('password', '')
    admin_pwd = cfg.get('settings', 'web.admin_password', '')
    if not admin_pwd:
        return web.json_response({'success': False, 'error': '未配置管理员密码'}, status=500)

    if password != admin_pwd:
        auth.record_ip_access(ip, 'fail')
        remaining = auth.get_remaining_attempts(ip)
        if remaining <= 0:
            return web.json_response({'success': False, 'error': 'IP 已被封禁，12小时后解除'}, status=403)
        return web.json_response(
            {
                'success': False,
                'error': f'密码错误，还剩 {remaining} 次机会',
                'remaining': remaining,
            },
            status=401,
        )

    auth.record_ip_access(ip, 'success')
    token = auth.create_session(request)
    return web.json_response({'success': True, 'token': token})


async def handle_auth_check(request: web.Request):
    return web.json_response({'success': True})


async def handle_password_status(request: web.Request):
    pwd = cfg.get('settings', 'web.admin_password', '')
    return web.json_response({'success': True, 'is_default': pwd in _WEAK_PASSWORDS or not pwd})


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.post('/api/auth/login', handle_login),
        web.get('/api/auth/check', _(handle_auth_check)),
        web.get('/api/auth/password-status', _(handle_password_status)),
    ]
