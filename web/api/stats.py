"""统计路由: /api/statistics/*"""

from aiohttp import web

import web.auth as auth
import web.tools._stats.statistics as handler


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/statistics', _(handler.handle_get_statistics)),
        web.get('/api/statistics/chart', _(handler.handle_get_chart_data)),
        web.get('/api/statistics/task/{task_id}', _(handler.handle_get_task_status)),
        web.get('/api/statistics/dates', _(handler.handle_get_available_dates)),
    ]
