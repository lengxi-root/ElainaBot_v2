"""机器人/系统路由: /api/bot*, /api/robot/*, /api/system/*, /api/logs/*"""

from aiohttp import web

import web.auth as auth
import web.tools._bot.info as robot_info
import web.tools._bot.restart as bot_restart
import web.tools._stats.log as log_query
import web.tools._stats.system as system_info
from web.api.shared import get_bot_manager, handle_recent_logs


async def handle_get_bots(request: web.Request):
    mgr = get_bot_manager()
    bots = []
    if mgr:
        for appid, inst in mgr._bots.items():
            ws_connected = False
            if inst.ws_client:
                ws_connected = bool(getattr(inst.ws_client, '_session_id', None))
            avatar = getattr(inst, 'avatar_url', '') or ''
            robot_qq = getattr(inst, 'robot_qq', '') or ''
            if not avatar and robot_qq:
                avatar = f'http://q1.qlogo.cn/g?b=qq&nk={robot_qq}&s=100'
            bots.append(
                {
                    'appid': appid,
                    'name': getattr(inst, 'name', '') or appid,
                    'robot_qq': robot_qq,
                    'bot_id': getattr(inst, 'bot_id', ''),
                    'avatar': avatar,
                    'connected': ws_connected,
                    'connection_type': 'WebSocket' if inst.ws_client else 'Webhook',
                }
            )
    return web.json_response({'success': True, 'bots': bots})


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/bots', _(handle_get_bots)),
        web.get('/api/robot/info', _(robot_info.handle_get_robot_info)),
        web.get('/api/robot/qrcode', robot_info.handle_get_robot_qrcode),
        web.get('/api/system/info', _(system_info.handle_system_info)),
        web.get('/api/logs/recent', _(handle_recent_logs)),
        web.get('/api/logs/login', _(log_query.handle_get_login_logs)),
        web.post('/api/logs/unban', _(log_query.handle_unban_ip)),
        web.post('/api/logs/delete-ip', _(log_query.handle_delete_ip)),
        web.get('/api/logs/{log_type}', _(log_query.handle_get_logs)),
        web.post('/api/bot/restart', _(bot_restart.handle_restart)),
    ]
