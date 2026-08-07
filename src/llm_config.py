"""
LLM 配置统一读取（消除硬编码）

所有 LLM 调用方（辩论/因果抽取/基因生成/蒸馏）从 config.yaml 的 llm 段
读取 provider/model/api_key/api_base/temperature/max_tokens，
支持环境变量覆盖（${DEEPSEEK_API_KEY} 等）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent


def _load_yaml() -> dict:
    import yaml
    cfg_path = _ROOT / "config" / "config.yaml"
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _resolve(value, default=""):
    """解析 ${ENV_VAR} 占位符"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.environ.get(env_name, default)
    return value


def get_llm_config() -> dict:
    """返回合并 env 覆盖后的 LLM 配置"""
    cfg = _load_yaml().get("llm", {})
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
    return {
        "provider": _resolve(cfg.get("provider", "deepseek")),
        "model": _resolve(cfg.get("model", "deepseek-chat")),
        "api_key": _resolve(cfg.get("api_key", ""), os.environ.get("DEEPSEEK_API_KEY", "")),
        "api_base": _resolve(cfg.get("api_base", "https://api.deepseek.com")),
        "temperature": float(cfg.get("temperature", 0.0)),
        "max_tokens": int(cfg.get("max_tokens", 4096)),
        "timeout": int(cfg.get("timeout", 30)),
        "retry": int(cfg.get("retry", 3)),
    }


def make_openai_client():
    """统一构造 OpenAI 兼容客户端"""
    from openai import OpenAI
    cfg = get_llm_config()
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["api_base"])


def make_client(provider: Optional[str] = None):
    """
    P2-01 多 LLM 基座分派：
      - deepseek / openai / 任意 OpenAI 兼容 → OpenAI 客户端
      - claude → Anthropic 客户端
    未配置对应 key 时明确报错。
    """
    cfg = get_llm_config()
    provider = (provider or cfg["provider"] or "deepseek").lower()
    if provider in ("deepseek", "openai", "zhipu", "moonshot", "dashscope"):
        from openai import OpenAI
        return OpenAI(api_key=cfg["api_key"], base_url=cfg["api_base"])
    if provider == "claude":
        import anthropic
        if not cfg["api_key"]:
            raise RuntimeError("CLAUDE API Key 未配置（llm.api_key 或 ANTHROPIC_API_KEY）")
        return anthropic.Anthropic(api_key=cfg["api_key"])
    raise RuntimeError(f"未知 LLM provider: {provider}（支持 deepseek/openai/claude 等）")


def chat(provider: Optional[str], model: str, messages: list[dict],
         temperature: float, max_tokens: int) -> str:
    """统一聊天调用（provider 分派，P2-01）"""
    p = (provider or get_llm_config()["provider"] or "deepseek").lower()
    if p == "claude":
        client = make_client("claude")
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [{"role": "user", "content": m["content"]} for m in messages if m["role"] == "user"]
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            system=sys_msg or None, messages=user_msgs,
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    client = make_client(p)
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""
