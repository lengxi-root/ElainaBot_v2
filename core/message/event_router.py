"""事件端点路由器 — 根据事件类型生成 reply/recall API 端点 URL"""

from core.message.event import (
    AT_MESSAGE_CREATE,
    C2C_MESSAGE_CREATE,
    DIRECT_MESSAGE_CREATE,
    GROUP_AT_MESSAGE_CREATE,
    GROUP_MESSAGE_CREATE,
    INTERACTION_CREATE,
    MESSAGE_CREATE,
)

# 回复端点模板: event_type → lambda event → endpoint_str
REPLY_ENDPOINTS = {
    GROUP_AT_MESSAGE_CREATE: lambda e: f"/v2/groups/{e.group_openid or e.group_id}/messages",
    GROUP_MESSAGE_CREATE: lambda e: f"/v2/groups/{e.group_openid or e.group_id}/messages",
    C2C_MESSAGE_CREATE: lambda e: f"/v2/users/{e.raw_user_id or e.user_id}/messages",
    AT_MESSAGE_CREATE: lambda e: f"/channels/{e.channel_id}/messages",
    DIRECT_MESSAGE_CREATE: lambda e: f"/dms/{e.guild_id}/messages",
    MESSAGE_CREATE: lambda e: f"/channels/{e.channel_id}/messages",
}

# 需 msg_id / event_id 回复的事件类型
MSG_ID_TYPES = frozenset(
    {
        GROUP_AT_MESSAGE_CREATE,
        GROUP_MESSAGE_CREATE,
        C2C_MESSAGE_CREATE,
        AT_MESSAGE_CREATE,
        DIRECT_MESSAGE_CREATE,
    }
)
EVENT_ID_TYPES = frozenset({INTERACTION_CREATE})


def get_reply_endpoint(event) -> str | None:
    """根据事件获取回复 API 端点路径"""
    fn = REPLY_ENDPOINTS.get(event.event_type)
    if fn:
        return fn(event)
    return None


def get_recall_endpoint(event) -> str | None:
    """根据事件获取撤回 API 端点路径"""
    et = event.event_type
    mid = event.message_id or ""

    if et in MSG_ID_TYPES:
        if et in (C2C_MESSAGE_CREATE,):
            return f"/v2/users/{event.raw_user_id or event.user_id}/messages/{mid}"
        if et in (GROUP_AT_MESSAGE_CREATE, GROUP_MESSAGE_CREATE):
            return f"/v2/groups/{event.group_openid or event.group_id}/messages/{mid}"
        if et in (AT_MESSAGE_CREATE,):
            return f"/channels/{event.channel_id}/messages/{mid}"
        if et in (DIRECT_MESSAGE_CREATE,):
            return f"/dms/{event.guild_id}/messages/{mid}"

    if et in EVENT_ID_TYPES:
        eid = event.event_id or ""
        if et == INTERACTION_CREATE:
            return f"/interactions/{eid}"

    return None
