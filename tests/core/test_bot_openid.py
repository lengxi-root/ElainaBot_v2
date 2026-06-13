"""全量环境机器人虚拟 id 处理测试 (bot_openid + parse_group_message)"""

import pytest

from core.message import bot_openid
from core.message.event import GROUP_MESSAGE_CREATE, Event

# 用户给出的真实 payload 中的两个 id
REAL_ID = 'B142869621B362EE510D3AE031149696'  # mentions[].id (is_you)
VIRTUAL_ID = '2326853CB1D2BEEA340A3F94CB550222'  # content 里的虚拟 id
APPID = '102000001'


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """每个用例使用独立缓存与持久化文件, 避免污染真实 data 目录"""
    monkeypatch.setattr(bot_openid, '_FILE', str(tmp_path / 'bot_openids.json'))
    monkeypatch.setattr(bot_openid, '_data', {})
    yield


def _full_at_payload(content, mention_id=REAL_ID, extra_mentions=None):
    mentions = [{'id': mention_id, 'bot': True, 'is_you': True, 'scope': 'single'}]
    if extra_mentions:
        mentions.extend(extra_mentions)
    return {
        'id': 'evt',
        'op': 0,
        't': GROUP_MESSAGE_CREATE,
        'd': {
            'id': 'msg',
            'author': {'id': 'C82DDAE23FDFC2E54CE6B4F6B0106F8A'},
            'content': content,
            'timestamp': '2026-06-14T05:01:25+08:00',
            'group_openid': 'group_001',
            'mentions': mentions,
            'attachments': [],
        },
    }


def _ids(appid):
    return bot_openid._data[appid]['ids']


class TestVirtualIdStripping:
    def test_only_self_strips_virtual_id(self):
        """仅艾特机器人: 真实 id 与 content 虚拟 id 不一致, 虚拟艾特也被移除"""
        evt = Event.from_websocket(APPID, _full_at_payload(f'<@{VIRTUAL_ID}> /三角洲菜单 '))
        assert evt.is_at_self is True
        assert evt.content == '/三角洲菜单'
        assert _ids(APPID) == {REAL_ID, VIRTUAL_ID}
        assert bot_openid.is_done(APPID) is True

    def test_single_id_bot(self):
        """单 id 机器人: content 与 mentions 一致, 也标记完成"""
        evt = Event.from_websocket(APPID, _full_at_payload(f'<@{REAL_ID}> /菜单'))
        assert evt.content == '/菜单'
        assert _ids(APPID) == {REAL_ID}
        assert bot_openid.is_done(APPID) is True

    def test_done_skips_rejudge(self):
        """已完成的 appid: 后续出现新虚拟 id 不再登记, 直接按缓存移除"""
        Event.from_websocket(APPID, _full_at_payload(f'<@{VIRTUAL_ID}> /菜单'))
        assert bot_openid.is_done(APPID) is True
        evt = Event.from_websocket(APPID, _full_at_payload('<@NEWUNKNOWN> /签到'))
        assert 'NEWUNKNOWN' not in _ids(APPID)
        assert '<@NEWUNKNOWN>' in evt.content

    def test_not_only_self_does_not_learn(self):
        """同时艾特其他用户: 不登记虚拟 id, 仅移除已知真实 id 的艾特"""
        other = {'id': 'OTHERUSER', 'bot': False, 'is_you': False, 'scope': 'single'}
        evt = Event.from_websocket(
            APPID, _full_at_payload(f'<@{REAL_ID}> <@OTHERUSER> hi', extra_mentions=[other])
        )
        assert evt.is_at_other_user is True
        assert bot_openid.is_done(APPID) is False
        assert '<@OTHERUSER>' in evt.content
        assert _ids(APPID) == {REAL_ID}


class TestBotOpenidModule:
    def test_add(self):
        bot_openid.add(APPID, 'id_a')
        bot_openid.add(APPID, 'id_a')
        bot_openid.add(APPID, 'id_b')
        assert _ids(APPID) == {'id_a', 'id_b'}

    def test_learn_marks_done(self):
        bot_openid.learn(APPID, '<@x> <@y> hi')
        assert _ids(APPID) == {'x', 'y'}
        assert bot_openid.is_done(APPID) is True

    def test_strip_multiple_ids(self):
        bot_openid.add(APPID, 'id_a')
        bot_openid.add(APPID, 'id_b')
        assert bot_openid.strip_self_at(APPID, '<@id_a><@id_b> /cmd') == '/cmd'

    def test_strip_unknown_appid_noop(self):
        assert bot_openid.strip_self_at('unknown', '<@x> hi') == '<@x> hi'

    def test_persist_roundtrip(self):
        """落盘后重新加载: id 与 done 保留"""
        bot_openid.learn(APPID, f'<@{REAL_ID}> <@{VIRTUAL_ID}>')
        bot_openid._data.clear()
        bot_openid._load()
        assert _ids(APPID) == {REAL_ID, VIRTUAL_ID}
        assert bot_openid.is_done(APPID) is True

    def test_load_legacy_string_format(self):
        """兼容旧格式 {appid: "openid"}"""
        import json

        with open(bot_openid._FILE, 'w', encoding='utf-8') as f:
            json.dump({APPID: REAL_ID}, f)
        bot_openid._data.clear()
        bot_openid._load()
        assert _ids(APPID) == {REAL_ID}
        assert bot_openid.is_done(APPID) is False
