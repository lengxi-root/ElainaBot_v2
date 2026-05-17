"""HTTP 服务器管理 — aiohttp 启动/关闭/Web面板挂载"""

import logging

from aiohttp import web

from core.base.config import cfg

log = logging.getLogger("ElainaBot.http_server")


class HttpServer:
    """管理 aiohttp HTTP 服务器生命周期"""

    def __init__(self, bot_manager, base_dir: str):
        self._bot_manager = bot_manager
        self._base_dir = base_dir
        self._app = None
        self._runner = None

    @property
    def app(self) -> web.Application:
        return self._app

    def init_app(self) -> web.Application:
        """初始化 aiohttp Application"""
        self._app = web.Application(client_max_size=20 * 1024 * 1024)

        # 核心路由
        self._app.router.add_post("/", self._bot_manager._handle_webhook)
        self._app.router.add_get("/health", self._bot_manager._handle_health)

        return self._app

    async def start(self):
        """启动 HTTP 服务器"""
        if not self._app:
            self.init_app()

        # 挂载 Web 面板
        try:
            from web.setup import setup_web

            setup_web(self._app, self._bot_manager, self._base_dir)
        except Exception as e:
            log.warning(f"Web 面板加载失败: {e}")

        # 抑制 aiohttp BadStatusLine 日志噪音
        class _BadStatusLineFilter(logging.Filter):
            def filter(self, record):
                return "BadStatusLine" not in record.getMessage()

        logging.getLogger("aiohttp.server").addFilter(_BadStatusLineFilter())

        host = cfg.get("settings", "server.host", "0.0.0.0")
        port = cfg.get("settings", "server.port", 5200)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        await web.TCPSite(self._runner, host, port).start()
        log.info(f"HTTP 服务器已启动: {host}:{port}")

    async def shutdown(self, timeout: float = 5):
        """关闭 HTTP 服务器"""
        if self._runner:
            try:
                import asyncio

                await asyncio.wait_for(self._runner.cleanup(), timeout=timeout)
            except TimeoutError:
                pass
            except Exception:
                pass
            self._runner = None
