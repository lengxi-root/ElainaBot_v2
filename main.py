#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ElainaBot 入口"""

import sys, os, ssl, asyncio

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
sys.dont_write_bytecode = True

# 全局跳过 SSL 证书验证
_orig_ctx = ssl.create_default_context
def _no_verify(*a, **kw):
    c = _orig_ctx(*a, **kw); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE; return c
ssl.create_default_context = _no_verify


def main():
    import json, shutil, pathlib
    try:
        for r in json.loads(pathlib.Path(_ROOT, 'web', 'deprecated_files.json').read_text('utf-8')):
            t = pathlib.Path(_ROOT, r); t.unlink(missing_ok=True)
            c = t.parent / '__pycache__'
            if c.is_dir(): shutil.rmtree(c, ignore_errors=True)
    except Exception:
        pass

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from core.bot.manager import BotManager
    try:
        asyncio.run(BotManager().start())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
