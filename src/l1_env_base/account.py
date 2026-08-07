"""
L1 仿真账户系统
管理余额、保证金、持仓、PNL、开平仓操作
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .matching_engine import OrderSide


@dataclass
class Position:
    """单笔持仓"""
    symbol: str
    side: OrderSide
    size: float                # 持仓数量（合约张数）
    entry_price: float         # 开仓均价
    leverage: float
    margin: float              # 已用保证金
    liquidation_price: float
    opened_at: datetime
    take_profit: float = 0.0
    stop_loss: float = 0.0

    def unrealized_pnl(self, current_price: float) -> float:
        """未实现盈亏"""
        if self.side == OrderSide.LONG:
            return self.size * (current_price - self.entry_price)
        else:
            return self.size * (self.entry_price - current_price)

    def pnl_pct(self, current_price: float) -> float:
        """未实现盈亏比例（相对于保证金）"""
        if self.margin == 0:
            return 0.0
        return self.unrealized_pnl(current_price) / self.margin


@dataclass
class TradeRecord:
    """已完成交易记录"""
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    size: float
    leverage: float
    pnl: float
    pnl_pct: float
    fee: float
    entry_ts: datetime
    exit_ts: datetime
    exit_reason: str = ""       # manual | stop_loss | take_profit | liquidation | risk_control


@dataclass
class AccountSnapshot:
    """账户快照（用于 LangGraph State 传递）"""
    balance: float
    equity: float
    available_margin: float
    used_margin: float
    positions: list[dict]
    daily_pnl: float
    total_pnl: float
    daily_trade_count: int
    peak_equity: float
    drawdown_pct: float
    timestamp: datetime


class Account:
    """
    仿真交易账户。

    管理余额、持仓、保证金，支持开仓/平仓/减仓操作。
    """

    def __init__(
        self,
        initial_balance: float = 100_000,
        max_leverage: float = 5.0,
        maintenance_margin_rate: float = 0.005,
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance        # 可用余额（USDT）
        self.max_leverage = max_leverage
        self.maintenance_margin_rate = maintenance_margin_rate

        self.positions: dict[str, Position] = {}   # symbol → Position
        self.trade_history: list[TradeRecord] = []
        self.total_fees: float = 0.0
        self.total_realized_pnl: float = 0.0
        self.daily_trade_count: int = 0
        self.last_trade_date: Optional[datetime] = None
        self.peak_equity: float = initial_balance

    # ─── 属性 ──────────────────────────────────────────────

    @property
    def used_margin(self) -> float:
        return sum(p.margin for p in self.positions.values())

    @property
    def available_margin(self) -> float:
        return self.balance - self.used_margin

    @property
    def equity(self, current_price: Optional[float] = None) -> float:
        """总权益 = 余额 + 所有未实现盈亏"""
        upnl = 0.0
        if current_price is not None:
            for p in self.positions.values():
                upnl += p.unrealized_pnl(current_price)
        return self.balance + upnl

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        current = self.balance + self.total_realized_pnl
        return max(0.0, 1.0 - current / self.peak_equity)

    # ─── 开仓 ──────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        entry_price: float,
        leverage: float,
        fee: float,
        timestamp: Optional[datetime] = None,
    ) -> Position:
        """开仓：扣除保证金和手续费，创建持仓"""
        if symbol in self.positions:
            raise ValueError(f"已有 {symbol} 持仓，请先平仓")

        if leverage > self.max_leverage:
            raise ValueError(f"杠杆 {leverage}x 超过上限 {self.max_leverage}x")

        position_value = size * entry_price
        margin = position_value / leverage
        total_cost = margin + fee

        if total_cost > self.balance:
            raise ValueError(f"余额不足: 需要 {total_cost:.2f}, 可用 {self.balance:.2f}")

        self.balance -= total_cost
        self.total_fees += fee

        # 计算爆仓价
        liq_price = self._calc_liq_price(entry_price, leverage, side, margin, size)

        pos = Position(
            symbol=symbol, side=side, size=size,
            entry_price=entry_price, leverage=leverage,
            margin=margin, liquidation_price=liq_price,
            opened_at=timestamp or datetime.now(timezone.utc),
        )
        self.positions[symbol] = pos
        self._bump_daily_count(timestamp)
        return pos

    # ─── 平仓 ──────────────────────────────────────────────

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        fee: float,
        timestamp: Optional[datetime] = None,
        reason: str = "manual",
    ) -> TradeRecord:
        """平仓：释放保证金，结算盈亏"""
        pos = self.positions.pop(symbol, None)
        if pos is None:
            raise ValueError(f"无 {symbol} 持仓")

        # 盈亏
        pnl = pos.unrealized_pnl(exit_price)
        # 净回收 = 保证金 + 盈亏 - 手续费
        net_return = pos.margin + pnl - fee

        self.balance += net_return
        self.total_fees += fee
        self.total_realized_pnl += pnl

        # 更新峰值权益
        current_equity = self.balance
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        ts = timestamp or datetime.now(timezone.utc)
        trade = TradeRecord(
            symbol=symbol, side=pos.side,
            entry_price=pos.entry_price, exit_price=exit_price,
            size=pos.size, leverage=pos.leverage,
            pnl=pnl, pnl_pct=pnl / pos.margin if pos.margin else 0,
            fee=fee, entry_ts=pos.opened_at, exit_ts=ts,
            exit_reason=reason,
        )
        self.trade_history.append(trade)
        return trade

    # ─── 减仓 ──────────────────────────────────────────────

    def reduce_position(
        self,
        symbol: str,
        reduce_size: float,
        exit_price: float,
        fee: float,
        timestamp: Optional[datetime] = None,
        reason: str = "manual",
    ) -> TradeRecord:
        """部分平仓"""
        pos = self.positions.get(symbol)
        if pos is None:
            raise ValueError(f"无 {symbol} 持仓")
        if reduce_size >= pos.size:
            return self.close_position(symbol, exit_price, fee, timestamp, reason)

        # 按比例计算盈亏
        ratio = reduce_size / pos.size
        pnl = pos.unrealized_pnl(exit_price) * ratio
        released_margin = pos.margin * ratio
        net_return = released_margin + pnl - fee

        self.balance += net_return
        self.total_fees += fee
        self.total_realized_pnl += pnl

        # 更新持仓
        pos.size -= reduce_size
        pos.margin -= released_margin

        ts = timestamp or datetime.now(timezone.utc)
        trade = TradeRecord(
            symbol=symbol, side=pos.side,
            entry_price=pos.entry_price, exit_price=exit_price,
            size=reduce_size, leverage=pos.leverage,
            pnl=pnl, pnl_pct=pnl / released_margin if released_margin else 0,
            fee=fee, entry_ts=pos.opened_at, exit_ts=ts,
            exit_reason=reason,
        )
        self.trade_history.append(trade)
        return trade

    # ─── 快照 ──────────────────────────────────────────────

    def snapshot(self, current_price: float = 0.0) -> AccountSnapshot:
        """生成账户快照，用于传递给 LangGraph State"""
        return AccountSnapshot(
            balance=self.balance,
            equity=self.equity(current_price) if current_price else self.balance,
            available_margin=self.available_margin,
            used_margin=self.used_margin,
            positions=[{
                "symbol": p.symbol, "side": p.side.value,
                "size": p.size, "entry_price": p.entry_price,
                "leverage": p.leverage, "margin": p.margin,
                "liquidation_price": p.liquidation_price,
                "unrealized_pnl": p.unrealized_pnl(current_price) if current_price else 0,
            } for p in self.positions.values()],
            daily_pnl=self.total_realized_pnl,
            total_pnl=self.total_realized_pnl + (
                sum(p.unrealized_pnl(current_price) for p in self.positions.values())
                if current_price else 0
            ),
            daily_trade_count=self.daily_trade_count,
            peak_equity=self.peak_equity,
            drawdown_pct=self.drawdown_pct,
            timestamp=datetime.now(timezone.utc),
        )

    # ─── 内部 ──────────────────────────────────────────────

    def _calc_liq_price(
        self, entry: float, lev: float, side: OrderSide,
        margin: float, size: float,
    ) -> float:
        mm = size * entry * self.maintenance_margin_rate
        if side == OrderSide.LONG:
            return entry - (margin - mm) / size
        else:
            return entry + (margin - mm) / size

    def _bump_daily_count(self, timestamp: Optional[datetime]):
        ts = timestamp or datetime.now(timezone.utc)
        today = ts.date()
        if self.last_trade_date != today:
            self.daily_trade_count = 1
            self.last_trade_date = today
        else:
            self.daily_trade_count += 1
