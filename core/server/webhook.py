"""Webhook 请求处理 — 验证 / 转发 / 交互响应"""

import json
import logging

from aiohttp import web

from core.base.sign import verify_and_respond
from core.message.event import Event

log = logging.getLogger("ElainaBot.webhook")


class WebhookHandler:
    """处理 QQ Bot webhook 回调: 签名验证 → 事件构造 → 分发"""

    def __init__(self, bot_registry, on_event, on_error=None):
        self._bot_registry = bot_registry
        self._on_event = on_event
        self._on_error = on_error or (lambda ctx: log.error(f"Webhook error: {ctx}"))

    async def handle(self, request: web.Request) -> web.Response:
        raw_body = await request.read()
        headers = dict(request.headers)

        appid = headers.get(
            "X-Bot-Appid", headers.get("x-bot-appid", "")
        ) or request.query.get("appid", "")
        if not appid:
            return web.json_response({"error": "missing appid"}, status=400)

        bot = self._bot_registry.get(appid)
        if not bot:
            return web.json_response({"error": f"unknown bot: {appid}"}, status=404)

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)

        # 签名验证 (op=13)
        if body.get("op") == 13:
            sig_resp = verify_and_respond(body, bot.secret)
            success = bool(sig_resp)
            log.info(f"[Webhook] 签名校验{'成功' if success else '失败'} appid={appid}")
            return (
                web.Response(text=sig_resp, content_type="application/json")
                if success
                else web.json_response({"error": "invalid validation"}, status=400)
            )

        # 事件构造与分发
        try:
            event = Event.from_webhook(headers, body)
            import asyncio

            asyncio.create_task(self._on_event(event))
        except Exception as e:
            self._on_error({"appid": appid, "source": "Webhook", "error": e})

        # 交互事件返回 ACK
        if body.get("t") == "INTERACTION_CREATE":
            return web.json_response({"op": 12, "code": 0})
        return web.json_response({})
