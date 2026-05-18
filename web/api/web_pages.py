"""自定义页面路由: /api/web-pages/*"""

from aiohttp import web

import web.auth as auth


async def handle_get_web_pages(request: web.Request):
    from core.plugin.web_pages import get_pages

    return web.json_response({'success': True, 'pages': get_pages()})


async def handle_get_web_page_html(request: web.Request):
    from core.plugin.web_pages import get_page_html

    key = request.match_info['key']
    html = get_page_html(key)
    if html is None:
        return web.json_response({'success': False, 'error': '页面不存在'}, status=404)
    return web.Response(text=html, content_type='text/html', charset='utf-8')


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/web-pages', _(handle_get_web_pages)),
        web.get('/api/web-pages/{key}', _(handle_get_web_page_html)),
    ]
