"""Web 面板自定义侧边栏页面示例

本模块在 main.py 中通过 `from plugins.system.app import web_pages` 导入时自动执行注册。
插件卸载时通过 on_unload 自动注销。
"""

from core.plugin.decorators import on_unload
from core.plugin.web_pages import register_page, unregister_page

# ==================== 注册侧边栏页面 ====================
# 模块被 import 时立即注册 (与 @handler 装饰器同理)

register_page(
    key='system-example',
    label='系统示例',
    source='plugin',
    source_name='system',
    html='''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f23; color: #e0e0e0; padding: 32px; }
  .card { background: #1a1a2e; border: 1px solid #2a2a3e; border-radius: 12px;
          padding: 24px; max-width: 600px; margin: 0 auto; }
  h1 { font-size: 20px; margin-bottom: 8px; color: #7c8aff; }
  p { font-size: 14px; color: #aaa; line-height: 1.6; margin-bottom: 12px; }
  .info { background: #16213e; border-radius: 8px; padding: 16px; margin-top: 16px;
          font-size: 13px; line-height: 1.8; }
  .info code { background: #2a2a3e; padding: 2px 6px; border-radius: 4px; color: #7c8aff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
           background: rgba(124,138,255,.15); color: #7c8aff; margin-left: 6px; }
</style>
</head>
<body>
  <div class="card">
    <h1>自定义侧边栏页面 <span class="badge">示例</span></h1>
    <p>这是系统插件 <code>app/web_pages.py</code> 子模块自动注册的面板页面。</p>
    <p>模块 import 时注册, 插件卸载时自动注销。</p>
    <div class="info">
      <strong>使用方法:</strong><br>
      1. 导入: <code>from core.plugin.web_pages import register_page</code><br>
      2. 注册: <code>register_page(key, label, html=...)</code><br>
      3. 注销: <code>unregister_page(key)</code><br><br>
      <strong>参数:</strong><br>
      - <code>key</code> — 页面唯一标识 (URL 路径)<br>
      - <code>label</code> — 侧边栏显示名称<br>
      - <code>html</code> — HTML 内容字符串<br>
      - <code>html_file</code> — 或指定 HTML 文件路径<br>
      - <code>source</code> — 来源类型 (plugin / module)
    </div>
  </div>
</body>
</html>''',
)


@on_unload
def _unload_web_pages():
    unregister_page('system-example')
