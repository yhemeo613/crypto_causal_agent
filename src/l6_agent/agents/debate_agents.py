"""
L6 四大辩论 Agent 节点
每个节点是一个独立的 LLM Agent，通过 DeepSeek API 调用
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from openai import OpenAI

from ..state import (
    AgentState, DebateRecord, FalsificationResult,
    CounterfactualResult, CounterfactualPath, DecisionResult,
)
from ..prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class BaseAgent:
    """Agent 基类：封装 DeepSeek LLM 调用"""

    def __init__(self, prompt_manager: PromptManager):
        self.prompts = prompt_manager
        from llm_config import get_llm_config, make_openai_client
        self.llm_cfg = get_llm_config()
        self.client = make_openai_client()

    def _call_llm(self, system: str, user: str, model: str = "") -> str:
        try:
            response = self.client.chat.completions.create(
                model=model or self.llm_cfg["model"],
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.llm_cfg["temperature"],
                max_tokens=self.llm_cfg["max_tokens"],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return "{}"

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}


class BullDebaterAgent(BaseAgent):
    """多头辩论：构建做多论证"""

    def __call__(self, state: AgentState) -> dict:
        if not state.perception or not state.memory:
            return {"errors": ["perception or memory missing"]}

        user_prompt = self.prompts.build_debate_prompt(
            state.perception.model_dump(), state.memory.model_dump()
        )
        raw = self._call_llm(self.prompts.BULL_SYSTEM, user_prompt)
        data = self._parse_json(raw)

        debate = DebateRecord(
            agent_role="bull",
            arguments=data.get("arguments", []),
            evidence=data.get("evidence", []),
            conclusion=data.get("conclusion", ""),
        )
        logger.info(f"Bull: conf={data.get('confidence', 0):.2f}, {len(debate.arguments)} args")
        return {
            "bull_debate": debate,
            "next_step": "bear_debate",
        }


class BearDebaterAgent(BaseAgent):
    """空头辩论：构建做空论证"""

    def __call__(self, state: AgentState) -> dict:
        if not state.perception or not state.memory:
            return {"errors": ["perception or memory missing"]}

        user_prompt = self.prompts.build_debate_prompt(
            state.perception.model_dump(), state.memory.model_dump()
        )
        raw = self._call_llm(self.prompts.BEAR_SYSTEM, user_prompt)
        data = self._parse_json(raw)

        debate = DebateRecord(
            agent_role="bear",
            arguments=data.get("arguments", []),
            evidence=data.get("evidence", []),
            conclusion=data.get("conclusion", ""),
        )
        logger.info(f"Bear: conf={data.get('confidence', 0):.2f}, {len(debate.arguments)} args")
        return {
            "bear_debate": debate,
            "next_step": "falsify",
        }


class FalsifierAgent(BaseAgent):
    """证伪校验：主动寻找推翻结论的证据"""

    def __call__(self, state: AgentState) -> dict:
        if not state.bull_debate or not state.bear_debate or not state.perception:
            return {"errors": ["debate or perception missing"]}

        user_prompt = self.prompts.build_falsifier_prompt(
            state.perception.model_dump(),
            state.bull_debate.conclusion,
            state.bear_debate.conclusion,
        )
        raw = self._call_llm(self.prompts.FALSIFIER_SYSTEM, user_prompt)
        data = self._parse_json(raw)

        result = FalsificationResult(
            is_falsified=data.get("is_falsified", False),
            evidence=data.get("evidence", []),
            confidence_adjusted=data.get("confidence_adjusted", 0.0),
            reasoning=data.get("reasoning", ""),
        )
        logger.info(f"Falsifier: is_falsified={result.is_falsified}, adj_conf={result.confidence_adjusted:.2f}")
        return {
            "falsification": result,
            "next_step": "counterfactual",
        }


class CounterfactualAgent(BaseAgent):
    """反事实推演：构建假设路径"""

    def __call__(self, state: AgentState) -> dict:
        if not state.perception:
            return {"errors": ["perception missing"]}

        # 辩论摘要
        debate_summary = ""
        if state.bull_debate:
            debate_summary += f"Bull: {state.bull_debate.conclusion}\n"
        if state.bear_debate:
            debate_summary += f"Bear: {state.bear_debate.conclusion}\n"

        falsification_str = ""
        if state.falsification:
            falsification_str = state.falsification.reasoning

        user_prompt = self.prompts.build_counterfactual_prompt(
            state.perception.model_dump(), debate_summary, falsification_str
        )
        raw = self._call_llm(self.prompts.COUNTERFACTUAL_SYSTEM, user_prompt)
        data = self._parse_json(raw)

        paths = []
        for p in data.get("paths", []):
            paths.append(CounterfactualPath(
                scenario=p.get("scenario", ""),
                probability=p.get("probability", 0.0),
                expected_return=p.get("expected_return", 0.0),
                expected_risk=p.get("expected_risk", 0.0),
            ))

        result = CounterfactualResult(
            paths=paths,
            weighted_confidence=data.get("weighted_confidence", 0.0),
        )
        logger.info(f"Counterfactual: {len(paths)} paths, w_conf={result.weighted_confidence:.2f}")
        return {
            "counterfactual": result,
            "next_step": "decide",
        }


class ConfidenceSizerAgent(BaseAgent):
    """置信度仓位：综合所有推理输出最终交易决策"""

    def __call__(self, state: AgentState) -> dict:
        if not state.perception:
            return {"errors": ["perception missing"]}

        debate_summary = ""
        if state.bull_debate:
            debate_summary += f"Bull({len(state.bull_debate.arguments)} args): {state.bull_debate.conclusion}\n"
        if state.bear_debate:
            debate_summary += f"Bear({len(state.bear_debate.arguments)} args): {state.bear_debate.conclusion}\n"

        falsification_str = ""
        if state.falsification:
            falsification_str = (
                f"is_falsified={state.falsification.is_falsified}, "
                f"adj_confidence={state.falsification.confidence_adjusted:.2f}"
            )

        counterfactual_str = ""
        if state.counterfactual:
            paths = state.counterfactual.paths
            counterfactual_str = f"{len(paths)} paths, w_conf={state.counterfactual.weighted_confidence:.2f}"
            for p in paths:
                counterfactual_str += f"\n  {p.scenario} (p={p.probability:.2f}, ret={p.expected_return:.1f}%)"

        account = state.account.model_dump() if state.account else {}

        user_prompt = self.prompts.build_decision_prompt(
            state.perception.model_dump(),
            debate_summary, falsification_str, counterfactual_str, account,
        )
        raw = self._call_llm(self.prompts.CONFIDENCE_SIZER_SYSTEM, user_prompt)
        data = self._parse_json(raw)

        decision = DecisionResult(
            action=data.get("action", "hold"),
            confidence=data.get("confidence", 0.0),
            position_size_pct=data.get("position_size_pct", 0.0),
            leverage=data.get("leverage", 1.0),
            stop_loss=data.get("stop_loss", 0.0),
            take_profit=data.get("take_profit", 0.0),
            reasoning=data.get("reasoning", ""),
        )
        logger.info(f"Decision: {decision.action} conf={decision.confidence:.2f} size={decision.position_size_pct:.2f}")
        return {
            "decision": decision,
            "next_step": "done",
        }
