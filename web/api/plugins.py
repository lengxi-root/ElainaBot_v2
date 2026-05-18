"""插件管理路由: /api/plugins/*"""

from aiohttp import web

import web.auth as auth
import web.tools._plugin_mgr.config as _config
import web.tools._plugin_mgr.files as _files
import web.tools._plugin_mgr.scan as _scan


def get_routes() -> list:
    _ = auth.require_auth
    return [
        web.get('/api/plugins/scan', _(_scan.handle_scan_plugins)),
        web.get('/api/plugins/scan-dirs', _(_scan.handle_scan_plugin_dirs)),
        web.post('/api/plugins/toggle', _(_files.handle_toggle_plugin)),
        web.post('/api/plugins/read', _(_files.handle_read_plugin)),
        web.post('/api/plugins/save', _(_files.handle_save_plugin)),
        web.post('/api/plugins/create', _(_files.handle_create_plugin)),
        web.post('/api/plugins/create-folder', _(_files.handle_create_folder)),
        web.get('/api/plugins/folders', _(_files.handle_get_folders)),
        web.post('/api/plugins/upload', _(_files.handle_upload_plugin)),
        web.post('/api/plugins/reload', _(_files.handle_reload_plugin)),
        web.post('/api/plugins/config-files', _(_config.handle_plugin_config_files)),
        web.get('/api/plugins/bots', _(_config.handle_get_plugin_bots)),
        web.post('/api/plugins/bots', _(_config.handle_set_plugin_bots)),
    ]
