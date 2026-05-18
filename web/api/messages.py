"""消息路由: /api/message/*"""

from aiohttp import web

import web.auth as auth
import web.tools._message.handlers as handler


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.post('/api/message/chats', _(handler.handle_get_chats)),
        web.post('/api/message/history', _(handler.handle_get_chat_history)),
        web.post('/api/message/send', _(handler.handle_send_message)),
        web.post('/api/message/nickname', _(handler.handle_get_nickname)),
        web.post('/api/message/nicknames', _(handler.handle_get_nicknames_batch)),
        web.post('/api/message/recall', _(handler.handle_recall_message)),
    ]
