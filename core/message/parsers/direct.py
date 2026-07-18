#!/usr/bin/env python
"""C2C 私聊消息解析器"""

from core.message.parsers.base import MessageParser, MessageUtils


class DirectMessageParser(MessageParser):
    """C2C 私聊消息解析器"""

    def parse(self, event, d):
        super().parse(event, d)
        event.is_group = False
        event.is_direct = True
        # C2C 无艾特语义, <@xxx> 属于普通文本, 保留在 content 中
        if '<@' in (event.raw_content or ''):
            content = MessageUtils.sanitize_content(event.raw_content, keep_at=True)
            if event.image_url:
                content = f'{content}<{event.image_url}>' if content else f'<{event.image_url}>'
            event.content = content
