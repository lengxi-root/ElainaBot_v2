"""消息层公共导出 — 供插件导入消息类型常量"""

from core.message._http import (
    MSG_TYPE_ARK,
    MSG_TYPE_MARKDOWN,
    MSG_TYPE_MEDIA,
    MSG_TYPE_TEXT,
    MessageType,
)

__all__ = [
    'MSG_TYPE_ARK',
    'MSG_TYPE_MARKDOWN',
    'MSG_TYPE_MEDIA',
    'MSG_TYPE_TEXT',
    'MessageType',
]
