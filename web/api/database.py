"""数据库浏览路由: /api/database/*"""

from aiohttp import web

import web.auth as auth
import web.tools._database.browser as browser


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/database/list', _(browser.handle_list_databases)),
        web.post('/api/database/tables', _(browser.handle_list_tables)),
        web.post('/api/database/query', _(browser.handle_query_table)),
        web.post('/api/database/sql', _(browser.handle_execute_sql)),
        web.post('/api/database/delete', _(browser.handle_delete_rows)),
    ]
