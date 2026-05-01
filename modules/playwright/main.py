#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Playwright 异步渲染模块

保持浏览器常驻, 通过信号量控制并发页面数, 供所有插件共享。

插件中获取:
    pw = bot.module_manager.get("playwright")

    # 截图 URL → bytes
    img = await pw.screenshot_url("https://example.com", full_page=True)

    # 截图 HTML 字符串 → bytes
    img = await pw.screenshot_html("<h1>Hello</h1>", viewport=(800, 600))

    # 高级: 自行操作页面
    async with pw.new_page(viewport=(1200, 800)) as page:
        await page.goto("https://example.com")
        await page.click("#btn")
        img = await page.screenshot(full_page=True)

配置文件 (data/ 下自动生成):
    config.yaml → max_pages / headless / timeout 等
"""

import asyncio
import tempfile
import os
from contextlib import asynccontextmanager

from core.base.logger import get_logger, EXTENSION

log = get_logger(EXTENSION, "Playwright")

_instance = None

_DEFAULTS = {
    'headless': True,
    'max_pages': 5,
    'default_timeout': 30000,
    'default_viewport_width': 1280,
    'default_viewport_height': 720,
    'image_format': 'jpeg',
    'image_quality': 90,
    'browser_type': 'chromium',
    'launch_args': [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
    ],
}

_COMMENTS = {
    'headless': '是否无头模式 (无界面)',
    'max_pages': '最大并发页面数',
    'default_timeout': '默认页面超时 (毫秒)',
    'default_viewport_width': '默认视口宽度',
    'default_viewport_height': '默认视口高度',
    'image_format': '截图格式: jpeg / png',
    'image_quality': '截图质量 (仅 jpeg, 1-100)',
    'browser_type': '浏览器类型: chromium / firefox / webkit',
    'launch_args': '浏览器启动参数',
}


# ==================== 模块入口 ====================

async def setup(ctx):
    global _instance
    cfg = ctx.ensure_config(_DEFAULTS, comments=_COMMENTS)
    _instance = PlaywrightRenderer(cfg)
    await _instance.initialize()
    if _instance.is_available():
        log.info(f"✅ Playwright 就绪 [{cfg['browser_type']}] 最大并发: {cfg['max_pages']}")
    else:
        log.warning("❌ Playwright 初始化失败, 截图功能不可用")
    return _instance


async def teardown():
    global _instance
    if _instance:
        await _instance.close()
        _instance = None


# ==================== PlaywrightRenderer ====================

class PlaywrightRenderer:
    """异步 Playwright 浏览器渲染器"""

    __slots__ = (
        '_cfg', '_pw', '_browser', '_semaphore',
        '_available', '_lock',
    )

    def __init__(self, cfg):
        self._cfg = cfg
        self._pw = None
        self._browser = None
        self._semaphore = asyncio.Semaphore(cfg.get('max_pages', 5))
        self._available = False
        self._lock = asyncio.Lock()

    async def initialize(self):
        try:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            browser_type = self._cfg.get('browser_type', 'chromium')
            launcher = getattr(self._pw, browser_type, self._pw.chromium)
            self._browser = await launcher.launch(
                headless=self._cfg.get('headless', True),
                args=self._cfg.get('launch_args', []),
            )
            self._available = True
        except Exception as e:
            log.error(f"Playwright 初始化失败: {e}")
            self._available = False

    def is_available(self):
        return self._available and self._browser is not None

    async def close(self):
        self._available = False
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None

    async def _ensure_browser(self):
        """浏览器崩溃时自动重启"""
        if self._browser and self._browser.is_connected():
            return True
        async with self._lock:
            if self._browser and self._browser.is_connected():
                return True
            log.warning("浏览器已断开, 正在重启...")
            try:
                from playwright.async_api import async_playwright
                if not self._pw:
                    self._pw = await async_playwright().start()
                browser_type = self._cfg.get('browser_type', 'chromium')
                launcher = getattr(self._pw, browser_type, self._pw.chromium)
                self._browser = await launcher.launch(
                    headless=self._cfg.get('headless', True),
                    args=self._cfg.get('launch_args', []),
                )
                self._available = True
                log.info("✅ 浏览器已重启")
                return True
            except Exception as e:
                log.error(f"浏览器重启失败: {e}")
                self._available = False
                return False

    # ---------- 核心 API ----------

    @asynccontextmanager
    async def new_page(self, viewport=None):
        """获取一个新页面 (async context manager), 自动限制并发

        用法:
            async with pw.new_page(viewport=(1200, 800)) as page:
                await page.goto(url)
                data = await page.screenshot()
        """
        if not await self._ensure_browser():
            raise RuntimeError("Playwright 浏览器不可用")

        vw = (viewport[0] if viewport else self._cfg.get('default_viewport_width', 1280))
        vh = (viewport[1] if viewport else self._cfg.get('default_viewport_height', 720))

        async with self._semaphore:
            page = await self._browser.new_page(
                viewport={'width': vw, 'height': vh},
            )
            page.set_default_timeout(self._cfg.get('default_timeout', 30000))
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    async def screenshot_url(self, url, *,
                             viewport=None,
                             full_page=True,
                             image_format=None,
                             quality=None,
                             wait_until='networkidle',
                             wait_ms=0,
                             selector=None,
                             timeout=None):
        """截图指定 URL, 返回图片 bytes

        参数:
            url         — 目标 URL
            viewport    — (width, height) 元组, None 则用默认值
            full_page   — 是否全页截图
            image_format— 'jpeg' / 'png', None 则用配置默认值
            quality     — jpeg 质量 1-100, None 则用配置默认值
            wait_until  — 页面加载等待策略: 'load' / 'domcontentloaded' / 'networkidle' / 'commit'
            wait_ms     — 页面加载完成后额外等待毫秒
            selector    — CSS 选择器, 指定则只截取该元素
            timeout     — 页面 goto 超时 (毫秒), None 则用默认
        """
        fmt = image_format or self._cfg.get('image_format', 'jpeg')
        q = quality or self._cfg.get('image_quality', 90)
        to = timeout or self._cfg.get('default_timeout', 30000)

        async with self.new_page(viewport=viewport) as page:
            await page.goto(url, wait_until=wait_until, timeout=to)
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
            return await self._take_screenshot(page, full_page, fmt, q, selector)

    async def screenshot_html(self, html, *,
                              viewport=None,
                              full_page=True,
                              image_format=None,
                              quality=None,
                              wait_ms=0,
                              selector=None,
                              base_url=None):
        """截图 HTML 字符串, 返回图片 bytes

        参数:
            html        — HTML 内容字符串
            viewport    — (width, height) 元组
            full_page   — 是否全页截图
            image_format— 'jpeg' / 'png'
            quality     — jpeg 质量 1-100
            wait_ms     — set_content 后额外等待毫秒
            selector    — CSS 选择器, 指定则只截取该元素
            base_url    — HTML 中相对路径的基础 URL
        """
        fmt = image_format or self._cfg.get('image_format', 'jpeg')
        q = quality or self._cfg.get('image_quality', 90)

        async with self.new_page(viewport=viewport) as page:
            kw = {}
            if base_url:
                kw['base_url'] = base_url
            await page.set_content(html, wait_until='networkidle', **kw)
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
            return await self._take_screenshot(page, full_page, fmt, q, selector)

    async def screenshot_file(self, file_path, **kwargs):
        """截图本地 HTML 文件, 返回图片 bytes

        参数同 screenshot_url, file_path 为本地文件绝对路径
        """
        url = f"file:///{os.path.abspath(file_path).replace(os.sep, '/')}"
        return await self.screenshot_url(url, **kwargs)

    async def pdf_url(self, url, *,
                      viewport=None,
                      wait_until='networkidle',
                      wait_ms=0,
                      timeout=None,
                      **pdf_kwargs):
        """将 URL 渲染为 PDF, 返回 bytes (仅 Chromium)"""
        to = timeout or self._cfg.get('default_timeout', 30000)
        async with self.new_page(viewport=viewport) as page:
            await page.goto(url, wait_until=wait_until, timeout=to)
            if wait_ms > 0:
                await page.wait_for_timeout(wait_ms)
            return await page.pdf(**pdf_kwargs)

    # ---------- 内部方法 ----------

    @staticmethod
    async def _take_screenshot(page, full_page, fmt, quality, selector):
        """统一截图逻辑"""
        kwargs = {'type': fmt, 'full_page': full_page}
        if fmt == 'jpeg':
            kwargs['quality'] = quality
        if selector:
            element = await page.query_selector(selector)
            if element:
                return await element.screenshot(**{k: v for k, v in kwargs.items() if k != 'full_page'})
        return await page.screenshot(**kwargs)
