"""DAU 统计图片渲染 — QQ 开放平台风格 (PIL)"""

import os
from io import BytesIO

# TDesign / QQ 开放平台配色
_BG = '#F3F5F8'
_CARD = '#FFFFFF'
_BORDER = '#E7EBF0'
_PRIMARY = '#0052D9'
_PRIMARY_LIGHT = '#366EF4'
_TEXT = '#1F2329'
_TEXT_SECONDARY = '#828A99'
_TEXT_TERTIARY = '#A6ADB8'
_UP = '#E34D59'
_DOWN = '#00A870'
_UP_BG = '#FDECEE'
_DOWN_BG = '#E3F9F0'
_FLAT = '#828A99'
_FLAT_BG = '#F0F1F5'
_BAR_BG = '#EDF1F7'

_FONT_PATHS = [
    # Windows
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyh.ttf',
    # Linux
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    # macOS
    '/System/Library/Fonts/PingFang.ttc',
]
_FONT_BOLD_PATHS = [
    'C:/Windows/Fonts/msyhbd.ttc',
    'C:/Windows/Fonts/msyhbd.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
]

_font_file = None
_font_bold_file = None


def _find_font():
    global _font_file, _font_bold_file
    if _font_file is not None:
        return _font_file
    for p in _FONT_PATHS:
        if os.path.isfile(p):
            _font_file = p
            break
    else:
        _font_file = ''
    for p in _FONT_BOLD_PATHS:
        if os.path.isfile(p):
            _font_bold_file = p
            break
    else:
        _font_bold_file = _font_file
    return _font_file


def _font(size, bold=False):
    from PIL import ImageFont

    path = _font_bold_file if bold else _font_file
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fmt_num(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    return f'{n:,}'


def _mask_id(s, n=3):
    s = str(s)
    return s if len(s) <= n * 2 else f'{s[:n]}****{s[-n:]}'


def _text_w(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _draw_delta(draw, x, y, diff):
    """绘制涨跌胶囊, 返回占用宽度"""
    if diff is None:
        return 0
    if diff > 0:
        txt, fg, bg = f'▲ {_fmt_num(diff)}', _UP, _UP_BG
    elif diff < 0:
        txt, fg, bg = f'▼ {_fmt_num(abs(diff))}', _DOWN, _DOWN_BG
    else:
        txt, fg, bg = '— 0', _FLAT, _FLAT_BG
    f = _font(22)
    w = _text_w(draw, txt, f) + 24
    h = 36
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=bg)
    draw.text((x + 12, y + (h - 22) // 2 - 3), txt, font=f, fill=fg)
    return w


def render_dau_image(stats, title, sub_title='', y_stats=None):
    """渲染 DAU 统计卡片, 返回 PNG bytes; PIL 不可用时返回 None

    stats: 含 users/groups_/received/sent/private/peak_hour/peak_hour_count/
           top_groups/top_users 的 dict
    y_stats: 昨日同时段对比 dict (可选)
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    _find_font()

    width = 860
    pad = 36
    top_groups = (stats.get('top_groups') or [])[:3]
    top_users = (stats.get('top_users') or [])[:3]

    list_rows = max(len(top_groups), len(top_users), 1)
    height = 500 + 120 + (86 + list_rows * 62) + 90

    img = Image.new('RGB', (width, height), _BG)
    d = ImageDraw.Draw(img)

    # ===== 顶部标题区 =====
    d.rounded_rectangle((pad, pad, pad + 8, pad + 44), radius=4, fill=_PRIMARY)
    d.text((pad + 26, pad - 2), title, font=_font(38, bold=True), fill=_TEXT)
    if sub_title:
        d.text((pad + 26, pad + 52), sub_title, font=_font(24), fill=_TEXT_SECONDARY)

    y = pad + 100

    # ===== 指标卡 2x2 =====
    def _y(key):
        return y_stats.get(key) if y_stats else None

    metrics = [
        ('活跃用户数', stats.get('users', 0), _y('users')),
        ('活跃群聊数', stats.get('groups_', 0), _y('groups_')),
        ('上行消息数', stats.get('received', 0), _y('received')),
        ('下行消息数', stats.get('sent', 0), _y('sent')),
    ]
    card_w = (width - pad * 2 - 24) // 2
    card_h = 150
    for i, (label, val, y_val) in enumerate(metrics):
        cx = pad + (i % 2) * (card_w + 24)
        cy = y + (i // 2) * (card_h + 24)
        d.rounded_rectangle(
            (cx, cy, cx + card_w, cy + card_h), radius=16,
            fill=_CARD, outline=_BORDER, width=2,
        )
        d.text((cx + 28, cy + 22), label, font=_font(24), fill=_TEXT_SECONDARY)
        num_font = _font(48, bold=True)
        d.text((cx + 28, cy + 62), _fmt_num(val), font=num_font, fill=_TEXT)
        if y_val is not None:
            nw = _text_w(d, _fmt_num(val), num_font)
            _draw_delta(d, cx + 28 + nw + 18, cy + 78, int(val) - int(y_val))

    y += card_h * 2 + 24 + 32

    # ===== 私聊消息 / 最活跃时段 =====
    row = [
        ('私聊消息', _fmt_num(stats.get('private', 0)), _y('private'), stats.get('private', 0)),
        ('最活跃时段', f"{stats.get('peak_hour', 0)}点", None, None),
    ]
    small_h = 110
    for i, (label, val, y_val, raw) in enumerate(row):
        cx = pad + i * (card_w + 24)
        d.rounded_rectangle(
            (cx, y, cx + card_w, y + small_h), radius=16,
            fill=_CARD, outline=_BORDER, width=2,
        )
        d.text((cx + 28, y + 18), label, font=_font(22), fill=_TEXT_SECONDARY)
        vf = _font(36, bold=True)
        d.text((cx + 28, y + 52), val, font=vf, fill=_TEXT)
        vw = _text_w(d, val, vf)
        if y_val is not None and raw is not None:
            _draw_delta(d, cx + 28 + vw + 16, y + 58, int(raw) - int(y_val))
        elif label == '最活跃时段' and stats.get('peak_hour_count'):
            d.text(
                (cx + 28 + vw + 16, y + 64),
                f"{_fmt_num(stats.get('peak_hour_count', 0))}条",
                font=_font(22), fill=_TEXT_TERTIARY,
            )

    y += small_h + 32

    # ===== 排行榜 =====
    rank_h = 86 + list_rows * 62
    half_w = card_w
    for i, (label, items, key) in enumerate(
        (('最活跃群组', top_groups, 'group_id'), ('最活跃用户', top_users, 'user_id'))
    ):
        cx = pad + i * (half_w + 24)
        d.rounded_rectangle(
            (cx, y, cx + half_w, y + rank_h), radius=16,
            fill=_CARD, outline=_BORDER, width=2,
        )
        d.text((cx + 28, y + 22), label, font=_font(24, bold=True), fill=_TEXT)
        if not items:
            d.text((cx + 28, y + 72), '暂无数据', font=_font(22), fill=_TEXT_TERTIARY)
            continue
        max_c = max(it.get('c', it.get('message_count', 0)) or 1 for it in items)
        for j, it in enumerate(items):
            ry = y + 72 + j * 62
            cnt = it.get('c', it.get('message_count', 0))
            rank_colors = (_PRIMARY, _PRIMARY_LIGHT, '#699EF5')
            d.rounded_rectangle(
                (cx + 28, ry, cx + 60, ry + 32), radius=8, fill=rank_colors[min(j, 2)])
            rf = _font(22, bold=True)
            d.text((cx + 28 + (32 - _text_w(d, str(j + 1), rf)) // 2, ry + 1),
                   str(j + 1), font=rf, fill='#FFFFFF')
            d.text((cx + 74, ry + 2), _mask_id(it.get(key, '')), font=_font(22), fill=_TEXT)
            cf = _font(22)
            cw = _text_w(d, f'{_fmt_num(cnt)}条', cf)
            d.text((cx + half_w - 28 - cw, ry + 2), f'{_fmt_num(cnt)}条',
                   font=cf, fill=_TEXT_SECONDARY)
            # 比例条
            bar_x, bar_y = cx + 74, ry + 40
            bar_w = half_w - 74 - 28
            d.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + 8), radius=4, fill=_BAR_BG)
            fill_w = max(8, int(bar_w * (cnt / max_c)))
            d.rounded_rectangle(
                (bar_x, bar_y, bar_x + fill_w, bar_y + 8), radius=4,
                fill=rank_colors[min(j, 2)])

    y += rank_h + 28

    # ===== 底部 =====
    d.text((pad, y), 'ElainaBot · 数据统计', font=_font(20), fill=_TEXT_TERTIARY)

    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
