"""
L1 硬风控系统
所有风控规则在交易执行前强制检查，触发时拒绝订单 + 记录日志
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .account import Account
from .matching_engine import OrderSide

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    """风控检查结果"""
    allowed: bool = True
    reject_reason: str = ""
    checks: list[dict] = field(default_factory=list)   # 每项检查详情


class RiskController:
    """
    硬风控 —— 在所有交易决策执行前进行强制检查。

    规则（不可被 Agent 决策绕过）：
    1. 最大回撤限制
    2. 单笔最大亏损限制
    3. 杠杆上限
    4. 最大持仓比例
    5. 日交易次数上限
    6. 最低置信度阈值
    """

    def __init__(
        self,
        max_drawdown_pct: Optional[float] = None,
        max_loss_per_trade_pct: Optional[float] = None,
        max_leverage: Optional[float] = None,
        max_position_pct: Optional[float] = None,
        max_daily_trades: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ):
        # 未显式传参时从 config 读取（消除双份维护）
        from config_utils import get_section
        rc = get_section("risk_control")
        self.max_drawdown_pct = max_drawdown_pct if max_drawdown_pct is not None else float(rc.get("max_drawdown_pct", 0.30))
        self.max_loss_per_trade_pct = max_loss_per_trade_pct if max_loss_per_trade_pct is not None else float(rc.get("max_loss_per_trade_pct", 0.05))
        self.max_leverage = max_leverage if max_leverage is not None else float(rc.get("max_leverage", 5.0))
        self.max_position_pct = max_position_pct if max_position_pct is not None else float(rc.get("max_position_pct", 0.95))
        self.max_daily_trades = max_daily_trades if max_daily_trades is not None else int(rc.get("max_daily_trades", 20))
        self.min_confidence = min_confidence if min_confidence is not None else float(rc.get("min_confidence_threshold", 0.4))

        self.total_rejects: int = 0
        self.reject_log: list[dict] = []

    # ─── 综合检查 ──────────────────────────────────────────

    def check(
        self,
        account: Account,
        symbol: str,
        side: OrderSide,
        size: float,
        entry_price: float,
        leverage: float,
        confidence: float,
        stop_loss: float = 0.0,
    ) -> RiskCheckResult:
        """
        执行全部风控检查。

        Returns:
            RiskCheckResult: allowed=True 可以通过，否则携带拒绝原因
        """
        result = RiskCheckResult()

        # 1. 最大回撤
        self._check_drawdown(account, result)

        # 2. 单笔最大亏损
        if stop_loss > 0:
            self._check_loss_per_trade(account, side, size, entry_price, stop_loss, leverage, result)

        # 3. 杠杆上限
        self._check_leverage(leverage, result)

        # 4. 最大持仓比例
        self._check_position_pct(account, size, entry_price, leverage, result)

        # 5. 日交易次数
        self._check_daily_trades(account, result)

        # 6. 最低置信度
        self._check_confidence(confidence, result)

        if not result.allowed:
            self.total_rejects += 1
            self.reject_log.append({
                "reason": result.reject_reason,
                "checks": result.checks,
                "timestamp": datetime.now().isoformat(),
            })
            logger.warning(f"风控拒绝: {result.reject_reason}")

        return result

    def check_close_only(self, account: Account) -> RiskCheckResult:
        """
        极端行情下只允许平仓。
        当回撤超过阈值时触发。
        """
        result = RiskCheckResult()
        current_dd = account.drawdown_pct
        if current_dd >= self.max_drawdown_pct:
            result.allowed = False
            result.reject_reason = f"回撤 {current_dd*100:.1f}% 超过最大回撤 {self.max_drawdown_pct*100:.0f}%，强制只平仓"
            return result

        # 爆仓检查
        for pos in account.positions.values():
            if account.balance <= 0:
                result.allowed = False
                result.reject_reason = "余额为零或负数，强制平仓"
                return result

        return result

    # ─── 各项检查 ──────────────────────────────────────────

    def _check_drawdown(self, account: Account, result: RiskCheckResult):
        dd = account.drawdown_pct
        entry = {
            "rule": "max_drawdown",
            "limit": self.max_drawdown_pct,
            "current": round(dd, 4),
            "passed": dd < self.max_drawdown_pct,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"回撤 {dd*100:.1f}% >= {self.max_drawdown_pct*100:.0f}%"

    def _check_loss_per_trade(
        self, account: Account, side: OrderSide,
        size: float, entry: float, stop_loss: float,
        leverage: float, result: RiskCheckResult,
    ):
        margin = size * entry / leverage
        if side == OrderSide.LONG:
            loss = size * (entry - stop_loss)
        else:
            loss = size * (stop_loss - entry)
        loss_pct = abs(loss / margin) if margin > 0 else 0

        entry = {
            "rule": "max_loss_per_trade",
            "limit": self.max_loss_per_trade_pct,
            "current": round(loss_pct, 4),
            "passed": loss_pct <= self.max_loss_per_trade_pct,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"单笔亏损 {loss_pct*100:.1f}% > {self.max_loss_per_trade_pct*100:.0f}%"

    def _check_leverage(self, leverage: float, result: RiskCheckResult):
        entry = {
            "rule": "max_leverage",
            "limit": self.max_leverage,
            "current": leverage,
            "passed": leverage <= self.max_leverage,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"杠杆 {leverage}x > {self.max_leverage}x"

    def _check_position_pct(
        self, account: Account, size: float,
        entry_price: float, leverage: float,
        result: RiskCheckResult,
    ):
        new_margin = size * entry_price / leverage
        total_margin = account.used_margin + new_margin
        position_pct = total_margin / account.balance if account.balance > 0 else 999

        entry = {
            "rule": "max_position_pct",
            "limit": self.max_position_pct,
            "current": round(position_pct, 4),
            "passed": position_pct <= self.max_position_pct,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"持仓占比 {position_pct*100:.1f}% > {self.max_position_pct*100:.0f}%"

    def _check_daily_trades(self, account: Account, result: RiskCheckResult):
        entry = {
            "rule": "max_daily_trades",
            "limit": self.max_daily_trades,
            "current": account.daily_trade_count,
            "passed": account.daily_trade_count < self.max_daily_trades,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"日交易 {account.daily_trade_count} 次 >= {self.max_daily_trades}"

    def _check_confidence(self, confidence: float, result: RiskCheckResult):
        entry = {
            "rule": "min_confidence",
            "limit": self.min_confidence,
            "current": round(confidence, 4),
            "passed": confidence >= self.min_confidence,
        }
        result.checks.append(entry)
        if not entry["passed"]:
            result.allowed = False
            result.reject_reason = f"置信度 {confidence:.2f} < {self.min_confidence}"
