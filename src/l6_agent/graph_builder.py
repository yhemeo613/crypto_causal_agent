"""
L6 LangGraph 流程编排
构建 bull_debate → bear_debate → falsify → counterfactual → decide 流程
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import StateGraph, END

from .state import AgentState
from .prompt_manager import PromptManager
from .agents.debate_agents import (
    BullDebaterAgent, BearDebaterAgent, FalsifierAgent,
    CounterfactualAgent, ConfidenceSizerAgent,
)

logger = logging.getLogger(__name__)


class ParallelDebateNode:
    """P2-02 并行辩论节点：bull + bear 两 Agent 同时执行，延迟减半"""

    def __init__(self, bull, bear):
        self.bull = bull
        self.bear = bear

    def __call__(self, state):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(self.bull.__call__, state)
            f2 = ex.submit(self.bear.__call__, state)
            rb, rb2 = f1.result(), f2.result()
        out = {}
        out.update(rb or {})
        out.update(rb2 or {})
        return out


def build_decision_graph(skip: set[str] | None = None) -> StateGraph:
    """
    构建 LangGraph 决策流程。

    节点流转：
    bull_debate → bear_debate → falsify → counterfactual → decide → END

    Args:
        skip: 要跳过的节点名集合（P1-09 消融：真实跳过该 LLM 节点）
    """
    skip = skip or set()
    prompts = PromptManager()
    bull = BullDebaterAgent(prompts)
    bear = BearDebaterAgent(prompts)
    falsifier = FalsifierAgent(prompts)
    counterfactual = CounterfactualAgent(prompts)
    sizer = ConfidenceSizerAgent(prompts)

    graph = StateGraph(AgentState)

    # 添加节点（节点名避免与状态键同名，langgraph ≥0.1.10 禁止同名）
    # P2-02：bull + bear 合并为并行节点（延迟减半）；skip="debate" 时跳过
    nodes = [
        ("parallel_debate", ParallelDebateNode(bull, bear)),
        ("falsify", falsifier),
        ("counterfactual_analysis", counterfactual),
        ("decide", sizer),
    ]
    for name, agent in nodes:
        if name not in skip:
            graph.add_node(name, agent)

    # 线性流转（跳过被消融的节点，前驱直连后继）
    chain = [name for name, _ in nodes if name not in skip]
    if not chain:
        chain = ["decide"]
    graph.set_entry_point(chain[0])
    for i in range(len(chain) - 1):
        graph.add_edge(chain[i], chain[i + 1])
    graph.add_edge(chain[-1], END)

    return graph


class DecisionPipeline:
    """
    一键式决策管道：感知 → 记忆 → 辩论 → 证伪 → 反事实 → 决策
    """

    def __init__(self, skip_nodes: set[str] | None = None):
        self.graph = build_decision_graph(skip=skip_nodes)
        self.app = self.graph.compile()

    def run(
        self,
        perception: dict,
        memory: dict,
        account: Optional[dict] = None,
        cycle_id: int = 0,
    ) -> dict:
        """
        运行一次完整决策流程。

        Args:
            perception: PerceptionContext dict
            memory: MemoryRecall dict
            account: AccountSnapshot dict (optional)
            cycle_id: 决策周期编号

        Returns:
            最终 AgentState dict
        """
        from .state import (
            PerceptionContext, MemoryRecall, AccountSnapshot,
            DecisionResult,
        )

        initial_state = AgentState(
            perception=PerceptionContext(**perception),
            memory=MemoryRecall(**memory),
            account=AccountSnapshot(**(account or {})),
            cycle_id=cycle_id,
            next_step="bull_debate",
        )

        result = self.app.invoke(initial_state.model_dump())

        # 提取决策
        decision = result.get("decision")
        if decision:
            dec = decision if isinstance(decision, dict) else decision.model_dump()
            logger.info(
                f"Pipeline Cycle#{cycle_id}: "
                f"{dec.get('action','hold')} "
                f"conf={dec.get('confidence',0):.2f}"
            )

        return result
