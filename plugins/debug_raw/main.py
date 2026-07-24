"""调试插件: 输出消息原始 payload 与 event 字段 (仅机器人 102050728 响应)"""

import json

from core.plugin.decorators import handler

BOT_APPID = '102050728'

EVENT_FIELDS = (
    'event_type', 'appid', 'user_id', 'username', 'group_id', 'channel_id',
    'guild_id', 'content', 'raw_content', 'message_id', 'event_id',
    'timestamp', 'chat_id', 'chat_type', 'member_role', 'image_url',
)


@handler(r'^原始数据$', name='原始数据', desc='用代码框输出消息原始 payload')
async def show_raw(event, match):
    if event.appid != BOT_APPID:
        return
    raw = json.dumps(event.raw, ensure_ascii=False, indent=2)
    await event.reply(f"```json\n{raw}\n```", msg_type=2)


@handler(r'^取event$', name='取event', desc='输出 event 对象常用字段')
async def show_event(event, match):
    if event.appid != BOT_APPID:
        return
    data = {k: getattr(event, k, None) for k in EVENT_FIELDS}
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    await event.reply(f"```json\n{text}\n```", msg_type=2)
