"""
P1-11 知识蒸馏

将高表现策略基因的核心逻辑蒸馏为可解释规则，写入知识库。

流程：
  1. 输入高表现基因（logic_code + params + fitness）
  2. LLM 将策略源码翻译为 N 条 if-then 可解释规则（JSON）
  3. 保真度验证：规则回译代码与原代码 AST 结构相似度（≥0.8 视为高保真）
  4. 规则持久化到 knowledge_rules 表 + 可导出 CSV
"""

from __future__ import annotations

import ast
import json
import logging
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DISTILL_SYSTEM = """你是量化策略解释器。请将给定的策略代码蒸馏为清晰、可解释的交易规则。

要求：
1. 输出 3-6 条 if-then 规则，每条包含：触发条件（自然语言）、动作（long/short/hold）、理由。
2. 规则必须忠实反映原代码逻辑（不添加原代码没有的条件）。
3. 同时输出"回译代码"：仅用规则表达的信号函数（def strategy(...)），用于保真度校验。

输出格式（严格 JSON）：
{"rules": [{"condition": "价格上穿均线且量比>1", "action": "long", "reason": "趋势确认"}, ...],
 "backtranslated_code": "def strategy(...):\\n    ..."}
"""


def _ast_signature(code: str) -> list[str]:
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


def _fidelity(original: str, backtranslated: str) -> float:
    """保真度：回译代码与原代码 AST 结构相似度"""
    s1, s2 = _ast_signature(original), _ast_signature(backtranslated)
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


class KnowledgeDistiller:
    """策略基因 → 可解释规则 蒸馏器"""

    def __init__(self, api_key: Optional[str] = None, model: str = ""):
        from openai import OpenAI
        from llm_config import get_llm_config
        cfg = get_llm_config()
        self.model = model or cfg["model"]
        self.api_key = api_key or cfg["api_key"]
        self.client = OpenAI(api_key=self.api_key, base_url=cfg["api_base"])

    def _call_llm(self, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": DISTILL_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0.2, max_tokens=1200,
        )
        return resp.choices[0].message.content or ""

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
            return {}

    def distill(self, gene, max_retries: int = 2) -> dict:
        """
        蒸馏一个基因为可解释规则。

        Returns:
            {"rules": [...], "fidelity": float, "gene_id": str, "error": str}
        """
        code = getattr(gene, "logic_code", "") or ""
        params = json.dumps(getattr(gene, "params", {}), ensure_ascii=False)
        user = f"策略代码：\n{code}\n\n参数：\n{params}\n\n请蒸馏为可解释规则。"
        last_err = ""
        for _ in range(max_retries + 1):
            raw = self._call_llm(user)
            data = self._extract_json(raw)
            rules = data.get("rules") or []
            back = data.get("backtranslated_code") or ""
            if not rules:
                last_err = "LLM 未返回规则"
                continue
            fid = _fidelity(code, back) if back else 0.0
            logger.info(f"[distill] {len(rules)} 条规则, 保真度 {fid:.2f}")
            return {"rules": rules, "fidelity": fid,
                    "gene_id": getattr(gene, "id", ""), "error": ""}
        return {"rules": [], "fidelity": 0.0, "gene_id": getattr(gene, "id", ""),
                "error": last_err or "解析失败"}

    @staticmethod
    def save_rules(rules: list[dict], gene_id: str, fidelity: float) -> None:
        """持久化到 knowledge_rules 表（统一连接）"""
        from db_conn import get_pg_conn
        conn = get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS knowledge_rules ("
                    "id SERIAL PRIMARY KEY, gene_id VARCHAR(64), rule_json JSONB, "
                    "fidelity DOUBLE PRECISION, created_at TIMESTAMPTZ DEFAULT NOW())")
                for r in rules:
                    cur.execute(
                        "INSERT INTO knowledge_rules (gene_id, rule_json, fidelity) VALUES (%s,%s,%s)",
                        (gene_id, json.dumps(r, ensure_ascii=False), fidelity))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def load_rules(limit: int = 50) -> list[dict]:
        from db_conn import get_pg_conn
        import psycopg2.extras
        conn = get_pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS knowledge_rules ("
                    "id SERIAL PRIMARY KEY, gene_id VARCHAR(64), rule_json JSONB, "
                    "fidelity DOUBLE PRECISION, created_at TIMESTAMPTZ DEFAULT NOW())")
                cur.execute("SELECT id, gene_id, rule_json, fidelity, created_at "
                            "FROM knowledge_rules ORDER BY id DESC LIMIT %s", (limit,))
                return list(cur.fetchall())
        finally:
            conn.close()
