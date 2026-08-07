"""
统一配置读取（消除双份维护/硬编码）

所有组件从 config/config.yaml 读取参数，环境变量覆盖 ${VAR} 占位符。
组件构造函数保留显式传参优先（传了就用，没传读 config）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent

_cfg_cache: Optional[dict] = None


def load_config(force: bool = False) -> dict:
    """加载 config.yaml（带缓存）"""
    global _cfg_cache
    if _cfg_cache is None or force:
        import yaml
        path = _ROOT / "config" / "config.yaml"
        try:
            _cfg_cache = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            _cfg_cache = {}
    return _cfg_cache


def _resolve(value: Any, default: Any = None) -> Any:
    """解析 ${ENV_VAR} 占位符（env 不存在回退 default）"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], default)
    return value


def get_section(name: str) -> dict:
    """读取 config 顶层 section，解析 env 占位符"""
    cfg = load_config()
    section = cfg.get(name, {})
    if not isinstance(section, dict):
        return {}
    return {k: _resolve(v) for k, v in section.items()}


def get_value(path: str, default: Any = None) -> Any:
    """读取点分路径配置，如 'risk_control.max_leverage'"""
    node = load_config()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return _resolve(node, default)


def ensure_dotenv() -> None:
    """确保 .env 已加载（幂等）"""
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
