"""
P1-04 Regime 自适应决策权重调节

不同市场状态（Regime）下调整 Agent 决策参数：
  - position_scale: 仓位缩放系数（趋势市满仓，震荡/高波动降仓）
  - max_leverage: 杠杆上限
  - min_confidence: 置信度门槛（高波动时要求更高置信度）
  - mode: 决策模式标签（供观测差异）

应用点：run_decision_cycle 决策后，对 position_size_pct / leverage 缩放，
并对置信度低于门槛的决策降级为 hold。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REGIME_POLICY: dict[str, dict] = {
    "trend_up":   {"position_scale": 1.0, "max_leverage": 3.0, "min_confidence": 0.40, "mode": "顺势满仓"},
    "trend_down": {"position_scale": 0.8, "max_leverage": 2.0, "min_confidence": 0.45, "mode": "谨慎防守"},
    "range":      {"position_scale": 0.6, "max_leverage": 1.0, "min_confidence": 0.50, "mode": "低仓位少动"},
    "high_vol":   {"position_scale": 0.5, "max_leverage": 1.0, "min_confidence": 0.55, "mode": "风控优先"},
    "unknown":    {"position_scale": 0.8, "max_leverage": 2.0, "min_confidence": 0.45, "mode": "默认"},
}


class RegimeAdapter:
    """按 Regime 调整决策参数（P1-04）"""

    def __init__(self, policies: dict | None = None):
        self.policies = policies or REGIME_POLICY

    def adjust(self, regime: str, position_pct: float, leverage: float,
               confidence: float) -> dict:
        """
        根据市场状态调整决策参数。

        Returns:
            {"position_pct": 调整后仓位, "leverage": 调整后杠杆,
             "confidence": 原置信度, "action": 调整后动作(hold 表示被降级),
             "mode": 策略模式, "gated": 是否被门槛降级}
        """
        policy = self.policies.get(regime or "unknown", self.policies["unknown"])
        new_pct = round(position_pct * policy["position_scale"], 4)
        new_lev = round(min(leverage, policy["max_leverage"]), 2)

        gated = False
        action = "hold" if new_pct <= 0 else None  # 由调用方决定动作
        if confidence < policy["min_confidence"]:
            gated = True
            new_pct = 0.0
            new_lev = 1.0

        return {
            "position_pct": new_pct,
            "leverage": new_lev,
            "confidence": round(confidence, 4),
            "mode": policy["mode"],
            "gated": gated,
            "regime": regime,
        }

    def describe(self) -> dict:
        """输出全部 Regime 策略（前端展示/观测差异）"""
        return {k: dict(v) for k, v in self.policies.items()}
