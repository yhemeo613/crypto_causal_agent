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


def build_decision_graph() -> StateGraph:
    """
    构建 LangGraph 决策流程。

    节点流转：
    bull_debate → bear_debate → falsify → counterfactual → decide → END
    """

    prompts = PromptManager()
    bull = BullDebaterAgent(prompts)
    bear = BearDebaterAgent(prompts)
    falsifier = FalsifierAgent(prompts)
    counterfactual = CounterfactualAgent(prompts)
    sizer = ConfidenceSizerAgent(prompts)

    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("bull_debate", bull)
    graph.add_node("bear_debate", bear)
    graph.add_node("falsify", falsifier)
    graph.add_node("counterfactual", counterfactual)
    graph.add_node("decide", sizer)

    # 设置入口
    graph.set_entry_point("bull_debate")

    # 线性流转
    graph.add_edge("bull_debate", "bear_debate")
    graph.add_edge("bear_debate", "falsify")
    graph.add_edge("falsify", "counterfactual")
    graph.add_edge("counterfactual", "decide")
    graph.add_edge("decide", END)

    return graph


class DecisionPipeline:
    """
    一键式决策管道：感知 → 记忆 → 辩论 → 证伪 → 反事实 → 决策
    """

    def __init__(self):
        self.graph = build_decision_graph()
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
