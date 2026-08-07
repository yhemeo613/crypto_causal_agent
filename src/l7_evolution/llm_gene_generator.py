"""
P1-02 LLM 创新基因生成

LLM 基于复盘报告 + 历史基因库生成全新的策略逻辑基因。
流程：
  1. DeepSeek 生成策略函数源码 + 参数默认值
  2. 编译验证（ast.parse + compile 必须通过）
  3. 创新性检查（AST 结构相似度 < 0.7 才接受）
  4. 封装为 StrategyGene（逻辑层=源码，参数层=dict）
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

GENERATE_SYSTEM = """你是量化交易策略架构师。请设计一个全新的加密货币永续合约交易策略。

要求：
1. 输出一个完整的 Python 策略函数，签名必须为：
   def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
2. 函数返回 (action, confidence)，action ∈ {"long", "short", "hold"}，confidence ∈ [0,1]。
3. 策略逻辑必须与已有基因库显著不同（不同的信号组合/不同的入场出场条件/不同的风控思路）。
4. 同时输出 DEFAULT_PARAMS 字典，包含策略使用的参数默认值：
   {"ma_short_window": int, "ma_long_window": int, "vol_threshold": float, ...}

输出格式（严格 JSON）：
{"code": "def strategy(...):\\n    ...", "params": {...}}
代码放在 JSON 字符串内，转义换行。"""


def _ast_signature(code: str) -> list[str]:
    """AST 节点类型序列（去掉字面量），用于结构相似度"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    seq: list[str] = []

    def walk(node):
        if isinstance(node, (ast.Constant, ast.Name)):
            seq.append(type(node).__name__)
            return
        seq.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return seq


class LLMGeneGenerator:
    """LLM 创新基因生成器"""

    def __init__(self, api_key: Optional[str] = None, model: str = ""):
        from openai import OpenAI
        from llm_config import get_llm_config
        cfg = get_llm_config()
        self.model = model or cfg["model"]
        self.api_key = api_key or cfg["api_key"]
        self.client = OpenAI(api_key=self.api_key, base_url=cfg["api_base"])

    # ─── LLM 调用 ────────────────────────────────────────

    def _call_llm(self, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置，无法生成基因")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": GENERATE_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0.7,
            max_tokens=1500,
        )
        return resp.choices[0].message.content or ""

    # ─── 解析与验证 ──────────────────────────────────────

    @staticmethod
    def _extract_json(raw: str) -> dict:
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 容错：直接提取 def strategy 函数
            m = re.search(r"def strategy\(.*?\n(?:[ \t].*\n)*", raw)
            return {"code": m.group(0) if m else "", "params": {}}

    @staticmethod
    def validate_code(code: str) -> tuple[bool, str]:
        """编译验证：ast.parse + compile"""
        if "def strategy" not in code:
            return False, "缺少 def strategy 函数"
        try:
            ast.parse(code)
            compile(code, "<gene>", "exec")
            return True, "ok"
        except SyntaxError as e:
            return False, f"语法错误: {e}"

    @staticmethod
    def novelty_score(new_code: str, existing_codes: list[str]) -> float:
        """创新性 = 1 - 最大结构相似度（< 0.7 视为足够创新）"""
        if not existing_codes:
            return 1.0
        sig_new = _ast_signature(new_code)
        if not sig_new:
            return 0.0
        best = 0.0
        for old in existing_codes:
            sig_old = _ast_signature(old)
            if sig_old:
                best = max(best, SequenceMatcher(None, sig_new, sig_old).ratio())
        return 1.0 - best

    # ─── 生成入口 ────────────────────────────────────────

    def generate(
        self,
        context: Optional[dict] = None,
        existing_codes: Optional[list[str]] = None,
        max_retries: int = 2,
    ) -> dict:
        """
        生成创新基因。

        Args:
            context: 复盘报告/基因库摘要（如 {"reviews": [...], "gene_summary": [...]}）
            existing_codes: 现有基因逻辑代码列表（用于创新性检查）

        Returns:
            {"gene": StrategyGene, "validated": bool, "novelty": float, "error": str}
        """
        from l7_evolution.evolution_engine import StrategyGene

        ctx = context or {}
        user = "现有基因库摘要：\n"
        for s in (ctx.get("gene_summary") or [])[-5:]:
            user += f"  - {s}\n"
        if ctx.get("reviews"):
            user += "复盘报告要点：\n" + "\n".join(f"  - {r}" for r in ctx["reviews"][-5:]) + "\n"
        user += "\n请生成一个与上述基因显著不同的新策略。"

        existing = existing_codes or []
        last_err = ""
        for _ in range(max_retries + 1):
            raw = self._call_llm(user)
            data = self._extract_json(raw)
            code = str(data.get("code", ""))
            params = data.get("params") or {}
            ok, msg = self.validate_code(code)
            if not ok:
                last_err = f"编译失败: {msg}"
                continue
            novelty = self.novelty_score(code, existing)
            if existing and novelty < 0.3:
                # 与现有基因结构相似度 > 0.7 → 创新性不足，重试生成（P1-02 硬过滤）
                last_err = f"创新性不足 (novelty={novelty:.2f} < 0.3)，重试"
                logger.info(f"[llm-gene] {last_err}")
                user += "\n（上次生成与现有基因过于相似，请改用完全不同的逻辑结构）"
                continue
            gene = StrategyGene(
                id=f"llm_{os.urandom(3).hex()}",
                logic_code=code,
                params=params if isinstance(params, dict) else {},
                generation=0,
            )
            logger.info(f"[llm-gene] 生成成功: novelty={novelty:.2f} params={list(gene.params.keys())}")
            return {"gene": gene, "validated": True, "novelty": novelty, "error": ""}

        return {"gene": None, "validated": False, "novelty": 0.0, "error": last_err or "解析失败"}
