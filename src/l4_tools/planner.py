"""
P1-07 工具调用规划器

LLM 根据任务描述规划工具调用序列（只读/计算工具），
依次执行并汇总结果。带短期缓存（同任务 60s 内复用）。

流程：
  1. 任务描述 + 可用工具清单 → LLM 输出工具序列 JSON
  2. 校验工具名/权限（仅 READ/CALC，ACT 需决策门禁走 ToolRegistry 强制）
  3. 依次调用 ToolRegistry.call，汇总输出
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PLAN_SYSTEM = """你是工具调度规划器。给定一个分析任务和可用工具列表，规划最优调用序列。

规则：
1. 只使用提供的工具，输出 JSON 数组，每项 {"tool": "工具名", "kwargs": {...}}。
2. 按数据依赖排序（先查数据 → 再计算指标）。
3. 最多 5 个工具调用，不要重复调用同一工具。
4. 只输出 JSON，不要解释。"""


class ToolPlanner:
    """LLM 工具调用规划器"""

    def __init__(self, registry, api_key: Optional[str] = None):
        from openai import OpenAI
        from llm_config import get_llm_config
        cfg = get_llm_config()
        self.registry = registry
        self.api_key = api_key or cfg["api_key"]
        self.client = OpenAI(api_key=self.api_key, base_url=cfg["api_base"])
        self.model = cfg["model"]
        self._cache: dict[str, tuple[float, list[dict]]] = {}  # task -> (ts, plan)
        self._result_cache: dict[str, tuple[float, dict]] = {}

    # ─── 规划 ────────────────────────────────────────────

    def _call_llm(self, task: str) -> list[dict]:
        tools_desc = "\n".join(
            f"- {t['name']} ({t['permission']}): {t['description']}"
            for t in self.registry.list_tools() if t["permission"] in ("read", "calc"))
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": PLAN_SYSTEM},
                      {"role": "user",
                       "content": f"任务：{task}\n\n可用工具：\n{tools_desc}\n\n请输出工具调用序列 JSON。"}],
            temperature=0.1, max_tokens=800,
        )
        raw = resp.choices[0].message.content or ""
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        try:
            plan = json.loads(raw)
            if isinstance(plan, dict):
                plan = plan.get("plan") or plan.get("steps") or []
            return [p for p in plan if isinstance(p, dict) and p.get("tool")]
        except json.JSONDecodeError:
            return []

    # ─── 执行 ────────────────────────────────────────────

    def plan_and_execute(self, task: str, decision_passed: bool = False,
                         cache_seconds: int = 60) -> dict:
        """规划并执行，带结果缓存"""
        now = time.time()
        cached = self._result_cache.get(task)
        if cached and (now - cached[0]) < cache_seconds:
            logger.info(f"[planner] 命中缓存: {task[:30]}")
            return {"cached": True, **cached[1]}

        plan = self._cache.get(task, (0, []))[1]
        if not plan or (now - self._cache.get(task, (0, []))[0]) > 120:
            plan = self._call_llm(task)
            self._cache[task] = (now, plan)
        logger.info(f"[planner] 规划 {len(plan)} 步: {[p['tool'] for p in plan]}")

        results = []
        for step in plan:
            name = step["tool"]
            kwargs = step.get("kwargs") or {}
            try:
                r = self.registry.call(name, decision_passed=decision_passed, **kwargs)
                results.append({"tool": name, "ok": True, "result": r})
            except Exception as e:
                results.append({"tool": name, "ok": False, "error": str(e)})

        out = {"task": task, "steps": plan, "results": results,
               "success": sum(1 for r in results if r["ok"])}
        self._result_cache[task] = (now, out)
        return {"cached": False, **out}
