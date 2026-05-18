#!/usr/bin/env python
"""ElainaBot 入口"""

import asyncio
import contextlib
import os
import ssl
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
sys.dont_write_bytecode = True

# 全局跳过 SSL 证书验证
_orig_ctx = ssl.create_default_context


def _no_verify(*a, **kw):
    c = _orig_ctx(*a, **kw)
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


ssl.create_default_context = _no_verify

# 加载 .env 文件 (必须在导入核心模块之前)
_env_path = os.path.join(_ROOT, '.env')
if os.path.isfile(_env_path):
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_path, override=False)
    except ImportError:
        pass  # python-dotenv 未安装时静默跳过


def main():
    import json
    import pathlib
    import shutil

    with contextlib.suppress(Exception):
        for r in json.loads(pathlib.Path(_ROOT, 'web', 'deprecated_files.json').read_text('utf-8')):
            t = pathlib.Path(_ROOT, r)
            t.unlink(missing_ok=True)
            c = t.parent / '__pycache__'
            if c.is_dir():
                shutil.rmtree(c, ignore_errors=True)

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from core.bot.manager import BotManager

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(BotManager().start())


if __name__ == '__main__':
    main()
