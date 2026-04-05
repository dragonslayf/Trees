"""
自定义 MMDetection 模块：从本仓库 `Models/` 加载真实的 TreeNet、TREEFPN（非占位实现）。

使用前请将仓库 `Trees` 目录加入 PYTHONPATH，或在 `Trees` 目录下运行脚本。

在 config 中可写（推荐）::
    custom_imports = dict(imports=['mmdet_custom_models'], allow_failed_imports=False)
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_MODELS_DIR = _ROOT / "Models"
if _MODELS_DIR.is_dir() and str(_MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(_MODELS_DIR))

# TreeNet.py / TreeFPN.py 在导入末尾会向 mmdet 注册
_tree_net_mod = importlib.import_module("TreeNet")
_tree_fpn_mod = importlib.import_module("TreeFPN")

TreeNet = _tree_net_mod.TreeNet
TREEFPN = _tree_fpn_mod.TREEFPN


def register_custom_modules() -> None:
    """显式再次注册（幂等，已注册则跳过）。"""
    _tree_net_mod._register_tree_net()
    _tree_fpn_mod._register_tree_fpn()


register_custom_modules()
