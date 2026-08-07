"""
L6 LangGraph 全局 AgentState
所有 Agent 节点通过此 State 传递数据
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ─── 感知 ──────────────────────────────────────────────

class PerceptionContext(BaseModel):
    timestamp: str = ""
    symbol: str = "BTCUSDT"
    regime: str = "unknown"
    l1_micro: Optional[dict] = None
    l2_meso: Optional[dict] = None
    l3_macro: Optional[dict] = None


# ─── 记忆召回 ──────────────────────────────────────────

class MemoryRecall(BaseModel):
    case_matches: list = Field(default_factory=list)
    causal_paths: list = Field(default_factory=list)
    instant_context: list = Field(default_factory=list)
    merged: list = Field(default_factory=list)


# ─── 辩论 ──────────────────────────────────────────────

class DebateRecord(BaseModel):
    agent_role: str = ""             # bull | bear
    arguments: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    conclusion: str = ""


class FalsificationResult(BaseModel):
    is_falsified: bool = False
    evidence: list[str] = Field(default_factory=list)
    confidence_adjusted: float = 0.0
    reasoning: str = ""


class CounterfactualPath(BaseModel):
    scenario: str = ""
    probability: float = 0.0
    expected_return: float = 0.0
    expected_risk: float = 0.0


class CounterfactualResult(BaseModel):
    paths: list[CounterfactualPath] = Field(default_factory=list)
    weighted_confidence: float = 0.0


# ─── 决策 ──────────────────────────────────────────────

class DecisionResult(BaseModel):
    action: str = "hold"             # long | short | hold
    confidence: float = 0.0
    position_size_pct: float = 0.0
    leverage: float = 1.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reasoning: str = ""


class AccountSnapshot(BaseModel):
    balance: float = 0.0
    equity: float = 0.0
    used_margin: float = 0.0
    available_margin: float = 0.0
    drawdown_pct: float = 0.0
    daily_trade_count: int = 0


# ─── 全局 State ────────────────────────────────────────

class AgentState(BaseModel):
    """LangGraph 全局状态，在各 Agent 节点间流转"""
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # 感知
    perception: Optional[PerceptionContext] = None

    # 记忆
    memory: Optional[MemoryRecall] = None

    # 辩论
    bull_debate: Optional[DebateRecord] = None
    bear_debate: Optional[DebateRecord] = None

    # 证伪
    falsification: Optional[FalsificationResult] = None

    # 反事实
    counterfactual: Optional[CounterfactualResult] = None

    # 决策
    decision: Optional[DecisionResult] = None

    # 账户
    account: Optional[AccountSnapshot] = None

    # 流程控制
    cycle_id: int = 0
    next_step: str = "bull_debate"
    errors: list[str] = Field(default_factory=list)
