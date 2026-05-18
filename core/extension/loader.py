"""统一扩展加载器 — Plugin/Module 共用的文件发现 + 动态导入 + 清单读取"""

import ast
import importlib.util
import os
import sys

# ==================== 文件发现 ====================


def find_entry(mod_dir: str, entry_name: str = 'main.py') -> str | None:
    """返回模块入口文件路径, 不存在则返回 None"""
    path = os.path.join(mod_dir, entry_name)
    return path if os.path.isfile(path) else None


def discover_extensions(base_dir: str, *, skip_underscore: bool = True):
    """扫描 base_dir 下所有有效扩展目录, 返回 [(name, dir_path), ...]"""
    if not os.path.isdir(base_dir):
        return []
    results = []
    for name in sorted(os.listdir(base_dir)):
        mod_dir = os.path.join(base_dir, name)
        if not os.path.isdir(mod_dir):
            continue
        if skip_underscore and name.startswith('_'):
            continue
        results.append((name, mod_dir))
    return results


# ==================== 动态导入 ====================


def import_module(name: str, mod_dir: str, *, namespace: str = 'modules'):
    """动态导入 Python 模块, 返回 module 对象"""
    entry = os.path.join(mod_dir, 'main.py')
    if not os.path.isfile(entry):
        raise FileNotFoundError(f'入口文件不存在: {entry}')

    mod_name = f'{namespace}.{name}'
    spec = importlib.util.spec_from_file_location(mod_name, entry, submodule_search_locations=[mod_dir])
    if spec is None or spec.loader is None:
        raise ImportError(f'无法加载模块: {mod_name}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def unload_module(name: str, *, namespace: str = 'modules'):
    """从 sys.modules 卸载模块"""
    sys.modules.pop(f'{namespace}.{name}', None)


# ==================== 清单读取 ====================

_MANIFEST_FIELDS = ('name', 'description', 'version', 'author', 'github', 'releases')

DEFAULT_MANIFEST = {
    'name': '',
    'description': '',
    'version': '1.0.0',
    'author': '',
    'github': '',
    'releases': '',
}


def read_manifest(mod_dir: str, *, var_name: str = '__module_meta__', entry_name: str = 'main.py') -> dict:
    """通过 AST 解析模块元数据 (__module_meta__ 变量), 不执行代码"""
    entry = os.path.join(mod_dir, entry_name)
    if not os.path.isfile(entry):
        return dict(DEFAULT_MANIFEST)

    try:
        with open(entry, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == var_name:
                return ast.literal_eval(node.value)  # type: ignore[no-any-return]
    except Exception:
        pass
    return dict(DEFAULT_MANIFEST)


def apply_manifest(info, meta: dict):
    """将清单字段应用到信息对象"""
    for key in _MANIFEST_FIELDS:
        val = meta.get(key)
        if val is not None:
            setattr(info, key, str(val) if not isinstance(val, str) else val)
