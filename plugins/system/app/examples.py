"""示例功能: 媒体发送、ark卡片、markdown、撤回、主动消息等 (仅主人可用)"""

import os
import asyncio
from core.plugin.decorators import handler


# ==================== 媒体发送示例 ====================

@handler(r'^图片$', name='图片', desc='发送网络图片示例', owner_only=True)
async def send_image(event, match):
    await event.reply_image(
        "https://i0.hdslb.com/bfs/openplatform/559162218f455ea859c783dceeda65cb1c724f4c.png",
        "reply_image 方法发送")


@handler(r'^本地图片$', name='本地图片', desc='发送本地图片示例', owner_only=True)
async def send_local_image(event, match):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "1.png")
    if not os.path.exists(path):
        return await event.reply(f"❌ 图片不存在: {path}")
    try:
        with open(path, 'rb') as f:
            data = f.read()
        await event.reply_image(data, f"📸 本地图片 ({len(data)/1024/1024:.2f}MB)")
    except Exception as ex:
        await event.reply(f"❌ 读取失败: {ex}")


@handler(r'^语音$', name='语音', desc='发送语音示例', owner_only=True)
async def send_voice(event, match):
    await event.reply_voice(
        "https://act-upload.mihoyo.com/sr-wiki/2025/06/03/160045374/420e9ac5c0c9d2b2c44b91f453b65061_2267222992827173477.wav")


@handler(r'^视频$', name='视频', desc='发送视频示例', owner_only=True)
async def send_video(event, match):
    await event.reply_video("https://i.elaina.vin/1.mp4")


@handler(r'^文件$', name='文件', desc='发送文件示例', owner_only=True)
async def send_file(event, match):
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("ElainaBot测试文件\n这是一个自动生成的文本文件示例")
        temp_path = f.name
    try:
        await event.reply_file(temp_path, "📄 自动生成的测试文件", file_name="elainabot_test.txt")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ==================== 撤回示例 ====================

@handler(r'^撤回测试$', name='撤回测试', desc='发送后3秒撤回', owner_only=True)
async def test_recall(event, match):
    data = await event.reply("⏰ 3秒后撤回...")
    if data:
        await asyncio.sleep(3)
        await event.recall()


@handler(r'^自动撤回$', name='自动撤回', desc='使用 auto_delete_time 自动撤回', owner_only=True)
async def test_auto_recall(event, match):
    await event.reply("⏰ 5秒后自动撤回", auto_delete_time=5)
    await event.reply_image(
        "https://i0.hdslb.com/bfs/openplatform/559162218f455ea859c783dceeda65cb1c724f4c.png",
        "🖼️ 10秒后撤回", auto_delete_time=10)


# ==================== Ark 卡片示例 ====================

@handler(r'^ark23$', name='ark23', desc='ark23列表卡片示例', owner_only=True)
async def send_ark23(event, match):
    await event.reply_ark(23, (
        "列表卡片示例", "ElainaBot",
        [['功能1: 图片'], ['功能2: 语音'], ['功能3: 视频', 'https://i.elaina.vin/api/']]))


@handler(r'^ark24$', name='ark24', desc='ark24文本+图片卡片示例', owner_only=True)
async def send_ark24(event, match):
    await event.reply_ark(24, (
        "功能强大的QQ机器人", "机器人信息", "ElainaBot", "支持插件化开发",
        "https://gchat.qpic.cn/qmeetpic/0/0-0-52C851D5FB926BC645528EB4AB462B3D/0",
        "https://i.elaina.vin/api/", "QQ Bot"))


@handler(r'^ark37$', name='ark37', desc='ark37图文卡片示例', owner_only=True)
async def send_ark37(event, match):
    await event.reply_ark(37, (
        "系统通知", "状态更新", "新功能上线",
        "https://gchat.qpic.cn/qmeetpic/0/0-0-52C851D5FB926BC645528EB4AB462B3D/0",
        "https://i.elaina.vin/api/"))


# ==================== 召回功能 ====================

@handler(r'^指定召回\s+(\S+)$', name='指定召回', desc='向指定用户发送召回消息', owner_only=True)
async def wakeup_user(event, match):
    uid = match.group(1)
    ok, r = await event.send_wakeup(uid, "📢 召回消息测试")
    if ok:
        await event.reply(f"✅ 召回成功 {uid[:8]}**** ID:{r}")
    else:
        await event.reply(f"❌ {r}")


@handler(r'^强制召回\s+(\S+)$', name='强制召回', desc='强制向指定用户发送召回消息', owner_only=True)
async def force_wakeup_user(event, match):
    uid = match.group(1)
    ok, r = await event.sender.force_wakeup(uid, "📢 强制召回测试")
    if ok:
        await event.reply(f"✅ 强制召回成功 {uid[:8]}**** ID:{r}")
    else:
        await event.reply(f"❌ {r}")


# ==================== 主动消息示例 ====================

@handler(r'^主动测试$', name='主动测试', desc='3秒后发送主动消息', owner_only=True)
async def test_active_message(event, match):
    target_id = event.group_id if event.is_group else event.user_id
    target_type = "群" if event.is_group else "用户"
    await event.reply(f"✅ 检测到{target_type}消息\nID: {target_id}\n\n⏰ 3秒后将发送主动消息...")

    await asyncio.sleep(3)
    if event.is_group:
        await event.send_to_group(event.group_id, "🎉 主动群消息（通过event发送）")
    else:
        await event.send_to_user(event.user_id, "🎉 主动私聊消息（通过event发送）")


@handler(r'^主动私聊\s+(\S+)\s+(.+)$', name='主动私聊', desc='向指定用户发送主动消息', owner_only=True)
async def test_send_to_user(event, match):
    uid, content = match.group(1), match.group(2)
    ok, data, _ = await event.send_to_user(uid, content)
    if ok:
        await event.reply(f"✅ 已发送主动私聊消息\n目标: {uid[:8]}****")
    else:
        await event.reply(f"❌ 发送失败: {data.get('message', '未知错误')}")


@handler(r'^主动群发\s+(\S+)\s+(.+)$', name='主动群发', desc='向指定群发送主动消息', owner_only=True)
async def test_send_to_group(event, match):
    gid, content = match.group(1), match.group(2)
    ok, data, _ = await event.send_to_group(gid, content)
    if ok:
        await event.reply(f"✅ 已发送主动群消息\n目标群: {gid[:8]}****")
    else:
        await event.reply(f"❌ 发送失败: {data.get('message', '未知错误')}")


@handler(r'^主动图片$', name='主动图片', desc='向当前会话主动发送图片', owner_only=True)
async def test_send_image_proactive(event, match):
    target_id = event.group_id if event.is_group else event.user_id
    if event.is_group:
        await event.reply_image(
            "https://i0.hdslb.com/bfs/openplatform/559162218f455ea859c783dceeda65cb1c724f4c.png",
            "📸 主动图片", target_group_id=target_id)
    else:
        await event.reply_image(
            "https://i0.hdslb.com/bfs/openplatform/559162218f455ea859c783dceeda65cb1c724f4c.png",
            "📸 主动图片", target_user_id=target_id)


# ==================== Web 面板示例 ====================
# Web 面板挂载在 HTTP 服务器上, 访问地址: http://<host>:<port>/web/
# 默认端口在 settings.yaml → server.port (默认 5001)
# 面板提供: 仪表盘、消息记录、插件管理、日志查看、统计、数据库、框架更新等功能
#
# 以下示例展示如何在插件中与 Web 面板交互:
#   1. 通过 WebSocket 推送实时消息到面板
#   2. 注册自定义 API 路由
#   3. 读取面板配置

@handler(r'^面板推送$', name='面板推送', desc='向 Web 面板推送一条自定义日志', owner_only=True)
async def push_to_panel(event, match):
    try:
        import web.ws as ws
        from datetime import datetime
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'content': f'来自插件的推送测试 (用户: {event.user_id})',
            'source': 'plugin.system.examples',
            'level': 'INFO',
        }
        ws.push_log('framework', entry)
        await event.reply("✅ 已推送日志到 Web 面板\n请在面板「日志」页查看")
    except Exception as e:
        await event.reply(f"❌ 推送失败: {e}")


@handler(r'^面板状态$', name='面板状态', desc='查看 Web 面板运行状态', owner_only=True)
async def panel_status(event, match):
    try:
        import web.ws as ws
        from core.base.config import cfg
        port = cfg.get('settings', 'server.port', 5001)
        client_count = len(ws._clients) if hasattr(ws, '_clients') else '未知'
        await event.reply(
            f"📊 Web 面板状态\n"
            f"端口: {port}\n"
            f"WebSocket 连接数: {client_count}\n"
            f"面板路径: /web/")
    except Exception as e:
        await event.reply(f"❌ 获取状态失败: {e}")


@handler(r'^面板广播\s+(.+)$', name='面板广播', desc='向所有面板客户端广播消息', owner_only=True)
async def panel_broadcast(event, match):
    content = match.group(1)
    try:
        import web.ws as ws
        ws.broadcast({'type': 'notification', 'message': content})
        await event.reply(f"✅ 已广播到所有面板客户端: {content}")
    except Exception as e:
        await event.reply(f"❌ 广播失败: {e}")
