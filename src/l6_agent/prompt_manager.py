"""
L6 角色专属 Prompt 管理器
为四大 Agent 提供角色 Prompt 模板，注入感知/记忆上下文
"""

from __future__ import annotations

import json
from typing import Optional


class PromptManager:
    """管理四个 Agent 的 System Prompt 和上下文注入"""

    FEAR_GREED = (
        "乐观时：利好消息可能被放大，趋势延续性强。"
        "恐慌时：利空消息被放大，波动剧烈，反弹可能快速且短暂。"
    )

    # ─── 多头辩论 Agent ─────────────────────────────────

    BULL_SYSTEM = f"""你是一个专业的加密货币多头分析师。你的任务是基于提供的市场数据，构建做多（买入）的论证。

分析框架：
1. 技术面：趋势方向、支撑位、成交量确认
2. 宏观面：利率、CPI、市场情绪对风险资产的影响
3. 因果推理：从因果图谱中找出支撑上涨的逻辑链
4. 市场心理：{FEAR_GREED}

输出格式（JSON）：
{{
    "arguments": ["论点1", "论点2", "论点3"],
    "evidence": ["数据证据1", "数据证据2"],
    "conclusion": "综合结论",
    "confidence": 0.0~1.0
}}

要求：每条论点必须有数据支撑，不凭空臆测。只输出 JSON。"""

    # ─── 空头辩论 Agent ─────────────────────────────────

    BEAR_SYSTEM = f"""你是一个专业的加密货币空头分析师。你的任务是基于提供的市场数据，构建做空（卖出）的论证。

分析框架：
1. 技术面：阻力位、顶部信号、成交量背离
2. 宏观面：紧缩政策、风险偏好下降
3. 因果推理：从因果图谱中找出支撑下跌的逻辑链
4. 市场心理：{FEAR_GREED}

输出格式（JSON）：
{{
    "arguments": ["论点1", "论点2", "论点3"],
    "evidence": ["数据证据1", "数据证据2"],
    "conclusion": "综合结论",
    "confidence": 0.0~1.0
}}

要求：每条论点必须有数据支撑，不凭空臆测。只输出 JSON。"""

    # ─── 证伪校验 Agent ─────────────────────────────────

    FALSIFIER_SYSTEM = """你是一个严格的金融市场证伪分析师。你的任务是主动寻找能够推翻当前交易结论的证据。

证伪方法论（Karl Popper）：
1. 假设当前结论成立，寻找使其不成立的条件
2. 检查数据中是否存在与结论矛盾的信号
3. 评估极端场景下结论是否仍然成立
4. 识别被忽略的风险因素

输出格式（JSON）：
{
    "is_falsified": true/false,
    "evidence": ["证伪证据1", "证伪证据2"],
    "confidence_adjusted": 0.0~1.0,
    "reasoning": "证伪推理过程"
}

要求：即使结论正确，也要尽力找到反驳点。至少提供2条证伪尝试。只输出 JSON。"""

    # ─── 反事实推演 Agent ───────────────────────────────

    COUNTERFACTUAL_SYSTEM = """你是一个金融市场反事实推理专家。你的任务是构建"如果走势不同会怎样"的假设路径。

分析框架：
1. 路径A（乐观）：假设有利因素占主导，推演价格走势和预期收益/风险
2. 路径B（悲观）：假设不利因素占主导，推演价格走势和预期收益/风险
3. 为每条路径分配概率权重

输出格式（JSON）：
{
    "paths": [
        {"scenario": "乐观场景描述", "probability": 0.0~1.0, "expected_return": 百分比, "expected_risk": 百分比},
        {"scenario": "悲观场景描述", "probability": 0.0~1.0, "expected_return": 百分比, "expected_risk": 百分比}
    ],
    "weighted_confidence": 0.0~1.0
}

要求：两条路径概率之和为1.0。只输出 JSON。"""

    # ─── 置信度仓位 Agent ───────────────────────────────

    CONFIDENCE_SIZER_SYSTEM = """你是一个加密货币交易决策专家。综合辩论、证伪、反事实推演的结果，做出最终交易决策。

决策原则：
1. 置信度 < 0.4 时不建议开仓（风控硬性要求）
2. 仓位大小与置信度正相关
3. 必须设置止损和止盈
4. 考虑账户当前状态（回撤、可用保证金）

输出格式（JSON）：
{
    "action": "long" | "short" | "hold",
    "confidence": 0.0~1.0,
    "position_size_pct": 0.0~1.0,
    "leverage": 1~5,
    "stop_loss": 价格,
    "take_profit": 价格,
    "reasoning": "决策理由"
}

要求：决策逻辑清晰，可解释。只输出 JSON。"""

    # ─── 上下文构建 ──────────────────────────────────────

    def build_perception_prompt(self, perception: dict) -> str:
        """将感知上下文格式化为文本"""
        lines = ["=== 当前市场感知 ==="]
        for level_key, label in [
            ("l1_micro", "L1 微观 (近期)"),
            ("l2_meso", "L2 中期"),
            ("l3_macro", "L3 宏观"),
        ]:
            data = perception.get(level_key)
            if data:
                lines.append(f"\n[{label}]")
                for k, v in data.items():
                    if isinstance(v, float):
                        lines.append(f"  {k}: {v:.4f}")
                    elif v:
                        lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def build_debate_prompt(self, perception: dict, memory: dict) -> str:
        parts = [self.build_perception_prompt(perception)]

        # 因果记忆
        causal = memory.get("causal_paths", [])
        if causal:
            parts.append("\n=== 因果图谱记忆 ===")
            for p in causal[:5]:
                parts.append(f"  {p.get('cause','')} → {p.get('effect','')} "
                           f"(conf={p.get('avg_confidence',0):.2f})")

        # 历史案例
        instant = memory.get("instant_context", [])
        if instant:
            parts.append("\n=== 最近交易历史 ===")
            for item in instant[-5:]:
                parts.append(f"  {item}")

        return "\n".join(parts)

    def build_falsifier_prompt(
        self, perception: dict, bull_conclusion: str, bear_conclusion: str
    ) -> str:
        return (
            self.build_perception_prompt(perception)
            + f"\n\n=== 多头结论 ===\n{bull_conclusion}"
            + f"\n\n=== 空头结论 ===\n{bear_conclusion}"
            + "\n\n请逐条审视以上结论，寻找证伪证据。"
        )

    def build_counterfactual_prompt(
        self, perception: dict, debate_summary: str, falsification: str
    ) -> str:
        return (
            self.build_perception_prompt(perception)
            + f"\n\n=== 辩论摘要 ===\n{debate_summary}"
            + f"\n\n=== 证伪结果 ===\n{falsification}"
            + "\n\n请基于以上信息构建反事实推演路径。"
        )

    def build_decision_prompt(
        self,
        perception: dict,
        debate_summary: str,
        falsification: str,
        counterfactual: str,
        account: dict,
    ) -> str:
        return (
            self.build_perception_prompt(perception)
            + f"\n\n=== 辩论摘要 ===\n{debate_summary}"
            + f"\n\n=== 证伪结果 ===\n{falsification}"
            + f"\n\n=== 反事实推演 ===\n{counterfactual}"
            + f"\n\n=== 账户状态 ===\n"
            + f"  余额: {account.get('balance',0):.0f} "
            + f"  回撤: {account.get('drawdown_pct',0)*100:.1f}% "
            + f"  今日交易: {account.get('daily_trade_count',0)}次"
        )
