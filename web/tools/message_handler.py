"""消息管理 — 聊天列表/历史/发送/昵称"""

import json
import time
import asyncio
import random
import base64
from datetime import datetime, timedelta, date as _date

from aiohttp import web
from core.base.logger import report_error, report_error_raw, FRAMEWORK

_nickname_cache = {}
_CACHE_TIMEOUT = 86400
_base_dir = ''
_bot_manager = None

# 聊天列表短期缓存 (避免多次刷新同一详情重复诡汇总查询)
_chat_list_cache = {}  # {(chat_type, appid_filter): (timestamp, chats)}
_CHAT_LIST_TTL = 30  # 秒
_chat_list_lock = None  # asyncio.Lock, 延迟初始化


def set_context(base_dir: str, bot_manager=None):
    global _base_dir, _bot_manager
    _base_dir = base_dir
    _bot_manager = bot_manager


def _get_nickname(user_id):
    if not user_id:
        return "未知用户"
    cached = _nickname_cache.get(user_id)
    if cached and time.time() - cached['ts'] < _CACHE_TIMEOUT:
        return cached['name']
    # 从 data.db 查 users.name
    if _bot_manager:
        for inst in _bot_manager._bots.values():
            try:
                r = inst.log_service.query_data(
                    "SELECT name FROM users WHERE user_id=?", (user_id,))
                if r and r[0].get('name'):
                    name = r[0]['name']
                    _nickname_cache[user_id] = {'name': name, 'ts': time.time()}
                    return name
            except Exception:
                pass
    return f"用户{user_id[-6:]}"


def _batch_get_nicknames(user_ids):
    """批量查询昵称 — 每个 bot 最多一次 SQL, 避免 N+1"""
    if not user_ids:
        return {}
    now = time.time()
    out = {}
    pending = []
    for uid in user_ids:
        if not uid:
            continue
        c = _nickname_cache.get(uid)
        if c and now - c['ts'] < _CACHE_TIMEOUT:
            out[uid] = c['name']
        else:
            pending.append(uid)
    if pending and _bot_manager:
        # SQLite 占位符限制, 分批 (1万/次 足够)
        for chunk_start in range(0, len(pending), 500):
            chunk = pending[chunk_start:chunk_start + 500]
            placeholders = ','.join('?' * len(chunk))
            sql = f"SELECT user_id, name FROM users WHERE user_id IN ({placeholders})"
            for inst in _bot_manager._bots.values():
                try:
                    rows = inst.log_service.query_data(sql, tuple(chunk))
                    for r in rows:
                        uid = r.get('user_id')
                        nm = r.get('name')
                        if uid and nm and uid not in out:
                            out[uid] = nm
                            _nickname_cache[uid] = {'name': nm, 'ts': now}
                except Exception:
                    pass
    # fallback for missing
    for uid in user_ids:
        if uid and uid not in out:
            out[uid] = f"用户{uid[-6:]}"
    return out


def _iter_bots(appid_filter=''):
    """按 appid 过滤机器人迭代器; 空字符串=全部"""
    if not _bot_manager:
        return []
    if appid_filter and appid_filter in _bot_manager._bots:
        return [(appid_filter, _bot_manager._bots[appid_filter])]
    return list(_bot_manager._bots.items())


def _get_bot(appid=''):
    """按 appid 获取单个 bot 实例, 找不到返回 None"""
    if not _bot_manager or not _bot_manager._bots:
        return None
    if appid and appid in _bot_manager._bots:
        return _bot_manager._bots[appid]
    return next(iter(_bot_manager._bots.values()))


def _recent_dates(days=1):
    """返回最近 N 天的日期字符串列表 (含今天)"""
    today = _date.today()
    return [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]


def _query_chat_messages_sync(chat_type, chat_id, appid_filter, days=3, limit=300):
    """查某个聊天会话的最近消息 — SQL WHERE 下推, 走索引, 避免全表扶描+Python过滤"""
    if not _bot_manager:
        return []
    dates = _recent_dates(days)
    results = []
    if chat_type == 'group':
        where = "group_id = ?"
        params = (chat_id,)
    else:
        # 私聊: user_id 匹配 且 group_id 为空或 'c2c'
        where = "user_id = ? AND (group_id = '' OR group_id = 'c2c')"
        params = (chat_id,)
    sql = f"SELECT * FROM log WHERE {where} ORDER BY id DESC LIMIT {limit}"
    for appid, inst in _iter_bots(appid_filter):
        bot_qq = getattr(inst, 'robot_qq', '') or ''
        bot_name = getattr(inst, 'name', appid)
        for d in dates:
            try:
                rows = inst.log_service.query('message', sql, params, date=d)
                for r in rows:
                    r['appid'] = appid
                    r['bot_name'] = bot_name
                    r['bot_qq'] = bot_qq
                    r['_date'] = d
                results.extend(rows)
            except Exception:
                pass
    results.sort(key=lambda r: (r.get('_date', ''), r.get('id', 0)))
    return results[-limit:]


def _query_older_messages_sync(chat_type, chat_id, appid_filter, before_date_str, limit=300, max_days=14):
    """从 before_date 前一天开始往前搜索, 找到第一个有消息的日期即返回"""
    if not _bot_manager:
        return [], '', False
    try:
        bd = datetime.strptime(before_date_str, '%Y-%m-%d').date()
    except ValueError:
        return [], '', False

    if chat_type == 'group':
        where = "group_id = ?"
        params = (chat_id,)
    else:
        where = "user_id = ? AND (group_id = '' OR group_id = 'c2c')"
        params = (chat_id,)
    sql = f"SELECT * FROM log WHERE {where} ORDER BY id DESC LIMIT {limit}"

    for offset in range(1, max_days + 1):
        d = (bd - timedelta(days=offset)).strftime('%Y-%m-%d')
        results = []
        for appid, inst in _iter_bots(appid_filter):
            bot_qq = getattr(inst, 'robot_qq', '') or ''
            bot_name = getattr(inst, 'name', appid)
            try:
                rows = inst.log_service.query('message', sql, params, date=d)
                for r in rows:
                    r['appid'] = appid
                    r['bot_name'] = bot_name
                    r['bot_qq'] = bot_qq
                    r['_date'] = d
                results.extend(rows)
            except Exception:
                pass
        if results:
            results.sort(key=lambda r: r.get('id', 0))
            return results[-limit:], d, True
    return [], '', False


def _aggregate_chats_sync(chat_type, appid_filter, days=3):
    """SQL 聚合聊天列表 — 避免下载几千条诡代反检柒"""
    if not _bot_manager:
        return []
    dates = _recent_dates(days)
    if chat_type == 'group':
        # 按 group_id 聚合 — 需要 idx_msg_group_id 索引加速
        agg_sql = (
            "SELECT group_id AS chat_id, MAX(id) AS last_id, MAX(timestamp) AS last_time, "
            "COUNT(*) AS msg_count FROM log WHERE group_id != '' AND group_id != 'c2c' "
            "GROUP BY group_id"
        )
    else:
        agg_sql = (
            "SELECT user_id AS chat_id, MAX(id) AS last_id, MAX(timestamp) AS last_time, "
            "COUNT(*) AS msg_count FROM log WHERE user_id != '' AND (group_id = '' OR group_id = 'c2c') "
            "GROUP BY user_id"
        )
    # 汇总: chat_key -> {appid, last_id, last_time, msg_count}
    merged = {}
    for appid, inst in _iter_bots(appid_filter):
        bot_name = getattr(inst, 'name', appid)
        for d in dates:
            try:
                rows = inst.log_service.query('message', agg_sql, date=d)
                for r in rows:
                    cid = r.get('chat_id', '')
                    if not cid:
                        continue
                    key = (appid, cid)
                    item = merged.get(key)
                    if not item:
                        item = {'chat_id': cid, 'appid': appid, 'bot_name': bot_name,
                                'last_id': 0, 'last_time': '', 'last_date': '',
                                'msg_count': 0}
                        merged[key] = item
                    item['msg_count'] += r.get('msg_count', 0) or 0
                    rid = r.get('last_id', 0) or 0
                    rts = r.get('last_time', '') or ''
                    # 在同 bot+chat 下, 选靠近的那一天作为预览来源
                    if rid and (rid > item['last_id'] or d > item['last_date']):
                        item['last_id'] = rid
                        item['last_time'] = rts
                        item['last_date'] = d
            except Exception:
                pass
    if not merged:
        return []
    # 拉取每个聊天的最后一条 content (仅 last_date 那天 + last_id)
    # 按 (appid, date) 分组 — 然后多个 id IN (...) 一次查
    by_path = {}  # (appid, date) -> [last_id]
    for (appid, _cid), item in merged.items():
        if item['last_id']:
            by_path.setdefault((appid, item['last_date']), []).append(item['last_id'])
    id_to_content = {}  # (appid, id) -> content
    for (appid, d), ids in by_path.items():
        inst = _bot_manager._bots.get(appid)
        if not inst or not ids:
            continue
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            placeholders = ','.join('?' * len(chunk))
            sql = f"SELECT id, content FROM log WHERE id IN ({placeholders})"
            try:
                rows = inst.log_service.query('message', sql, tuple(chunk), date=d)
                for r in rows:
                    id_to_content[(appid, r.get('id'))] = r.get('content', '')
            except Exception:
                pass
    chats = []
    for (appid, cid), item in merged.items():
        item['last_content'] = id_to_content.get((appid, item['last_id']), '')
        chats.append(item)
    chats.sort(key=lambda c: c.get('last_time', ''), reverse=True)
    return chats


async def handle_get_nickname(request: web.Request):
    body = await request.json()
    uid = body.get('user_id', '')
    if not uid:
        return web.json_response({'success': False, 'message': '缺少用户ID'}, status=400)
    return web.json_response({'success': True, 'data': {'user_id': uid, 'nickname': _get_nickname(uid)}})


async def handle_get_nicknames_batch(request: web.Request):
    body = await request.json()
    uids = body.get('user_ids', [])
    if not uids or not isinstance(uids, list):
        return web.json_response({'success': False, 'message': '缺少用户ID列表'}, status=400)
    result = {uid: _get_nickname(uid) for uid in uids}
    return web.json_response({'success': True, 'data': {'nicknames': result}})


async def handle_get_chats(request: web.Request):
    """获取聊天列表 — SQL GROUP BY 聚合 + 批量昵称 + 短期缓存"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    chat_type = body.get('type', 'group')
    search = body.get('search', '').lower()
    appid_filter = body.get('appid', '')
    page = max(int(body.get('page', 1)), 1)
    page_size = min(int(body.get('page_size', 50)), 100)

    global _chat_list_lock
    if _chat_list_lock is None:
        _chat_list_lock = asyncio.Lock()

    cache_key = (chat_type, appid_filter)
    now = time.time()
    cached = _chat_list_cache.get(cache_key)
    if cached and now - cached[0] < _CHAT_LIST_TTL:
        chats = cached[1]
    else:
        async with _chat_list_lock:
            # 二次检查: 等锁期间可能已被另一个请求刷新
            cached = _chat_list_cache.get(cache_key)
            if cached and time.time() - cached[0] < _CHAT_LIST_TTL:
                chats = cached[1]
            else:
                loop = asyncio.get_event_loop()
                chats = await loop.run_in_executor(None, _aggregate_chats_sync, chat_type, appid_filter, 1)
                if chat_type == 'user':
                    ids = [c['chat_id'] for c in chats]
                    nicks = await loop.run_in_executor(None, _batch_get_nicknames, ids)
                    for c in chats:
                        c['nickname'] = nicks.get(c['chat_id'], f"用户{c['chat_id'][-6:]}")
                        c['avatar'] = (c['nickname'] or '?')[0].upper()
                else:
                    for c in chats:
                        c['nickname'] = f"群{c['chat_id'][-6:]}"
                        c['avatar'] = c['chat_id'][0].upper() if c['chat_id'] else '?'
                _chat_list_cache[cache_key] = (time.time(), chats)

    if search:
        chats = [c for c in chats if search in c['chat_id'].lower() or search in c.get('nickname', '').lower()]

    total = len(chats)
    start = (page - 1) * page_size
    paged = chats[start:start + page_size]

    return web.json_response({'success': True, 'data': {
        'chats': paged, 'total': total, 'page': page, 'page_size': page_size,
    }})


async def handle_get_chat_history(request: web.Request):
    """获取聊天记录 — 支持按日期分页加载

    before_date: 可选, YYYY-MM-DD, 加载该日期之前的消息 (往前搜索到有数据为止)
    不传则加载今天的消息
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    chat_type = body.get('chat_type', 'group')
    chat_id = body.get('chat_id', '')
    appid_filter = body.get('appid', '')
    before_date = body.get('before_date', '')

    if not chat_id:
        return web.json_response({'success': True, 'data': {'messages': [], 'has_more': False}})

    loop = asyncio.get_event_loop()

    if before_date:
        rows, oldest_date, has_more = await loop.run_in_executor(
            None, _query_older_messages_sync, chat_type, chat_id, appid_filter, before_date, 300, 14)
    else:
        rows = await loop.run_in_executor(
            None, _query_chat_messages_sync, chat_type, chat_id, appid_filter, 1, 300)
        oldest_date = _date.today().strftime('%Y-%m-%d')
        has_more = True

    # 收集需要查询的 user_id (仅非bot消息), 批量取昵称
    uid_set = set()
    for r in rows:
        if r.get('direction') != 'send':
            uid = r.get('user_id', '')
            if uid:
                uid_set.add(uid)
    nicks = await loop.run_in_executor(None, _batch_get_nicknames, list(uid_set)) if uid_set else {}

    messages = []
    for r in rows:
        uid = r.get('user_id', '')
        content = r.get('content', '')
        msg_type = r.get('type', '')
        is_bot = r.get('direction') == 'send'

        if content.startswith('[Bot:'):
            idx = content.find('] ')
            if idx > 0:
                content = content[idx + 2:]

        plugin_name = r.get('plugin_name', '')
        source = 'web_panel' if plugin_name == 'WebPanel' else (
            'onebot' if msg_type in ('onebot_send', 'onebot_recv') else '')
        messages.append({
            'id': r.get('id', len(messages)),
            'message_id': r.get('message_id', ''),
            'user_id': uid,
            'appid': r.get('appid', ''),
            'bot_qq': r.get('bot_qq', '') if is_bot else '',
            'nickname': (r.get('bot_name', '') or 'Bot') if is_bot else nicks.get(uid, f"用户{uid[-6:]}" if uid else '未知用户'),
            'content': content,
            'timestamp': r.get('timestamp', ''),
            'is_self': is_bot,
            'source': source,
        })

    # 取最近一条非 bot 消息的 message_id 用于发送回复 (仅初始加载)
    last_msg_id = ''
    if not before_date:
        today_str = _date.today().strftime('%Y-%m-%d')
        for r in reversed(rows):
            if r.get('_date', '') != today_str:
                continue
            mid = r.get('message_id', '')
            if mid and r.get('type') != 'plugin' and r.get('direction') != 'send':
                last_msg_id = mid
                break

    return web.json_response({'success': True, 'data': {
        'messages': messages, 'last_msg_id': last_msg_id,
        'oldest_date': oldest_date, 'has_more': has_more,
    }})


async def handle_send_message(request: web.Request):
    """发送消息 (支持 multipart/form-data)

    参数:
        chat_type:       group | user
        chat_id:         群/用户 openid
        appid:           机器人 appid
        msg_type:        text | markdown | media | ark
        content:         文本内容 / 资源URL (media) / ARK kv JSON (ark)
        msg_id:          回复消息 ID (被动回复需要)
        image:           图片文件 (仅 text 模式, 与 content 一起发送)
        media_file_type: 富媒体文件类型 1=图片 2=视频 3=语音 4=文件 (仅 media)
        ark_template_id: ARK 模板 ID (仅 ark)
    """
    if not _bot_manager:
        return web.json_response({'success': False, 'message': '机器人管理器未初始化'}, status=500)

    try:
        # 支持 multipart/form-data 和 JSON
        if request.content_type and 'multipart' in request.content_type:
            reader = await request.multipart()
            fields = {}
            image_data = None
            while True:
                part = await reader.next()
                if part is None:
                    break
                name = part.name
                if name == 'image':
                    image_data = await part.read()
                else:
                    fields[name] = (await part.read()).decode('utf-8', errors='replace')
        else:
            fields = await request.json()
            image_data = None

        chat_type = fields.get('chat_type', '')
        chat_id = fields.get('chat_id', '')
        appid = fields.get('appid', '')
        msg_type = fields.get('msg_type', 'text')
        content = fields.get('content', '').strip()
        msg_id = fields.get('msg_id', '')
        media_file_type = int(fields.get('media_file_type', '1'))
        ark_template_id = int(fields.get('ark_template_id', '23'))

        if not chat_type or not chat_id:
            return web.json_response({'success': False, 'message': '缺少 chat_type/chat_id'}, status=400)
        if not content and not image_data and msg_type != 'ark':
            return web.json_response({'success': False, 'message': '消息内容为空'}, status=400)

        bot = _get_bot(appid)
        if not bot:
            return web.json_response({'success': False, 'message': '无可用机器人'}, status=400)

        sender = bot.sender
        bot_appid = getattr(bot, 'appid', '') or appid
        bot_name = getattr(bot, 'name', '') or bot_appid
        bot_qq = getattr(bot, 'robot_qq', '') or ''

        # 根据消息类型发送
        is_group = chat_type == 'group'
        gid = chat_id if is_group else None
        uid = chat_id if not is_group else None

        if msg_type == 'media' and content:
            ok, data = await _send_media_url(
                sender, content, file_type=media_file_type,
                group_id=gid, user_id=uid, msg_id=msg_id)

        elif msg_type == 'ark' and content:
            ok, data = await _send_ark(
                sender, ark_template_id, content,
                group_id=gid, user_id=uid, msg_id=msg_id)

        elif msg_type == 'text' and image_data:
            ok, data = await _send_text_with_image(
                sender, content, image_data,
                group_id=gid, user_id=uid, msg_id=msg_id)

        else:
            api_msg_type = 2 if msg_type == 'markdown' else 0
            if chat_type == 'group':
                ok, data, actual_payload = await sender.send_to_group(
                    chat_id, content, msg_id=msg_id, msg_type=api_msg_type)
            else:
                ok, data, actual_payload = await sender.send_to_user(
                    chat_id, content, msg_id=msg_id, msg_type=api_msg_type)

        # 保存图片到本地缓存 (data/media/)
        media_label = sender._save_media(image_data, 1) if image_data else ''

        # 构建显示内容
        display = _build_display(msg_type, content, image_data, media_file_type, ark_template_id, media_label)

        send_payload = locals().get('actual_payload') or {'msg_type': msg_type, 'content': content}
        if ok:
            _log_sent_message(bot, chat_type, chat_id, display, bot_appid, bot_name, bot_qq, send_payload)
            return web.json_response({'success': True, 'message': '发送成功'})
        err_msg = data.get('message', '发送失败') if isinstance(data, dict) else str(data)
        _log_send_error(bot, msg_type, chat_type, chat_id, send_payload, data, bot_appid, msg_id)
        return web.json_response({'success': False, 'message': err_msg})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({'success': False, 'message': str(e)}, status=500)


async def handle_recall_message(request: web.Request):
    """撤回消息 — 仅 2 分钟内由 web 面板发出 (is_self) 的消息可撤回

    参数: chat_type, chat_id, appid, message_id
    """
    if not _bot_manager:
        return web.json_response({'success': False, 'message': '机器人管理器未初始化'}, status=500)
    try:
        body = await request.json()
    except Exception:
        body = {}
    chat_type = body.get('chat_type', '')
    chat_id = body.get('chat_id', '')
    appid = body.get('appid', '')
    message_id = body.get('message_id', '')

    if not message_id or not chat_id or chat_type not in ('group', 'user'):
        return web.json_response({'success': False, 'message': '参数缺失'}, status=400)

    bot = _get_bot(appid)
    if not bot:
        return web.json_response({'success': False, 'message': '无可用机器人'}, status=400)

    endpoint = f"/v2/{'groups' if chat_type == 'group' else 'users'}/{chat_id}/messages/{message_id}"

    try:
        ok, data = await bot.sender.delete(endpoint)
    except Exception as e:
        return web.json_response({'success': False, 'message': str(e)}, status=500)

    if ok:
        return web.json_response({'success': True})
    err = data.get('message', '撤回失败') if isinstance(data, dict) else str(data)
    return web.json_response({'success': False, 'message': err})


# ==================== 日志记录 ====================

def _build_display(msg_type, content, image_data, media_file_type, ark_template_id, media_label=''):
    """构建日志显示内容"""
    if msg_type == 'media':
        type_names = {1: '图片', 2: '视频', 3: '语音', 4: '文件'}
        return f"[富媒体:{type_names.get(media_file_type, '?')}] {content[:200]}"
    if msg_type == 'ark':
        return f"[ARK:{ark_template_id}] {content[:200]}"
    if msg_type == 'markdown':
        return f"[Markdown] {content[:200]}"
    if image_data and media_label:
        return f"{content[:200]}\n{media_label}" if content else media_label
    return content[:200]


def _log_sent_message(bot, chat_type, chat_id, display, bot_appid, bot_name, bot_qq='', payload=None):
    """成功发送 → 写消息数据库 + 推送到面板"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    group_id = chat_id if chat_type == 'group' else ''
    user_id = chat_id if chat_type != 'group' else ''
    raw = json.dumps(payload, ensure_ascii=False, default=str) if payload else display

    # 写 message.db
    try:
        log_service = getattr(bot, 'log_service', None)
        if log_service:
            asyncio.ensure_future(log_service.add('message', {
                'type': 'plugin',
                'user_id': user_id,
                'group_id': group_id,
                'content': display,
                'plugin_name': 'WebPanel',
                'raw_message': raw, 'direction': 'send',
            }))
    except Exception:
        pass

    # 推送到面板实时日志
    try:
        import web.ws as _ws
        _ws.push_log('message', {
            'appid': bot_appid,
            'bot_name': bot_name,
            'bot_qq': bot_qq,
            'user_id': user_id,
            'group_id': group_id,
            'content': display,
            'is_bot': True,
            'direction': 'send',
            'source': 'web_panel',
            'plugin_name': 'WebPanel',
        })
    except Exception:
        pass


def _log_send_error(bot, msg_type, chat_type, chat_id, send_payload, api_resp, bot_appid, msg_id=''):
    """发送失败 → 写报错数据库
    content=接收原始消息(来源信息), traceback=API报错响应, context=发送载荷(完整)
    """
    report_error_raw(
        FRAMEWORK, 'Web消息发送',
        content=f"[WebPanel] chat_type={chat_type} chat_id={chat_id} msg_id={msg_id}",
        tb=json.dumps(api_resp, ensure_ascii=False, default=str)[:2000] if api_resp else '',
        context=json.dumps(send_payload, ensure_ascii=False, default=str)[:2000] if send_payload else '',
        appid=bot_appid,
    )


def _log_upload_error(sender, endpoint, resp_data, detail=''):
    """上传失败 → 写报错数据库"""
    err_msg = resp_data.get('message', '') if isinstance(resp_data, dict) else str(resp_data)
    err_code = resp_data.get('code', '') if isinstance(resp_data, dict) else ''
    report_error(FRAMEWORK, "Web媒体上传",
                 f"上传失败 {detail} → {err_code}: {err_msg}",
                 context={
                     'appid': getattr(sender, '_appid', ''),
                     'endpoint': endpoint,
                     'api_response': json.dumps(resp_data, ensure_ascii=False, default=str)[:1000]
                         if resp_data else '',
                 })


# ==================== 辅助: 富媒体 ====================

def _media_endpoints(group_id, user_id):
    """返回 (upload_ep, send_ep)"""
    if group_id:
        return f"/v2/groups/{group_id}/files", f"/v2/groups/{group_id}/messages"
    return f"/v2/users/{user_id}/files", f"/v2/users/{user_id}/messages"


async def _web_send_media(sender, *, file_info, content='', group_id=None, user_id=None, msg_id=''):
    """file_info 已就绪, 直接发送富媒体消息"""
    _, send_ep = _media_endpoints(group_id, user_id)
    payload = {'msg_type': 7, 'msg_seq': random.randint(10000, 999999),
               'content': content or '', 'media': {'file_info': file_info}}
    if msg_id:
        payload['msg_id'] = msg_id
    return await sender.post_json(send_ep, payload)


async def _send_media_url(sender, url, *, file_type=1, group_id=None, user_id=None, msg_id=''):
    """通过 URL 上传并发送富媒体"""
    upload_ep, _ = _media_endpoints(group_id, user_id)
    ok, resp = await sender.post_json(upload_ep,
                                       {'srv_send_msg': False, 'file_type': file_type, 'url': url})
    if not ok:
        _log_upload_error(sender, upload_ep, resp, f'URL上传 file_type={file_type}')
        return False, resp
    file_info = resp.get('file_info')
    if not file_info:
        _log_upload_error(sender, upload_ep, resp, 'URL上传返回无file_info')
        return False, {'message': '上传失败: 无 file_info'}
    return await _web_send_media(sender, file_info=file_info,
                                  group_id=group_id, user_id=user_id, msg_id=msg_id)


async def _send_text_with_image(sender, content, image_bytes, *, group_id=None, user_id=None, msg_id=''):
    """上传图片 bytes 并发送"""
    if not image_bytes:
        return False, {'message': '图片数据为空'}
    upload_ep, _ = _media_endpoints(group_id, user_id)
    ok, resp = await sender.post_json(upload_ep, {
        'srv_send_msg': False, 'file_type': 1,
        'file_data': base64.b64encode(image_bytes).decode(),
    })
    if not ok:
        return False, resp
    file_info = resp.get('file_info')
    if not file_info:
        return False, {'message': '上传失败: 无 file_info'}
    return await _web_send_media(sender, file_info=file_info, content=content,
                                  group_id=group_id, user_id=user_id, msg_id=msg_id)


# ==================== 辅助: ARK ====================

async def _send_ark(sender, template_id, kv_json_str, *, group_id=None, user_id=None, msg_id=''):
    """发送 ARK 消息

    template_id: ARK 模板 ID (23, 24, 37 等)
    kv_json_str: kv 数据的 JSON 字符串 (数组)
    """
    try:
        kv_data = json.loads(kv_json_str)
    except json.JSONDecodeError as e:
        return False, {'message': f'ARK kv JSON 解析失败: {e}'}

    if not isinstance(kv_data, list):
        return False, {'message': 'ARK kv 必须是 JSON 数组'}

    payload = {
        'msg_type': 3, 'msg_seq': random.randint(10000, 999999),
        'content': '',
        'ark': {'template_id': template_id, 'kv': kv_data},
    }
    if msg_id:
        payload['msg_id'] = msg_id

    _, send_ep = _media_endpoints(group_id, user_id)
    return await sender.post_json(send_ep, payload)
