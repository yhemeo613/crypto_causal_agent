"""
L1 本地撮合仿真引擎
基于历史 K 线模拟订单簿、滑点、手续费、资金费率、爆仓
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# 订单模型
# ═══════════════════════════════════════════════════════════════

class OrderSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass
class OrderRequest:
    """下单请求"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float              # 合约张数（币本位）或 USDT 数量
    leverage: float = 1.0
    limit_price: float = 0.0     # 限价单价格
    stop_price: float = 0.0      # 止损触发价
    reduce_only: bool = False
    timestamp: Optional[datetime] = None


@dataclass
class FillResult:
    """成交结果"""
    filled: bool = False
    fill_price: float = 0.0
    fill_size: float = 0.0
    fee: float = 0.0              # 手续费（USDT）
    slippage_pct: float = 0.0
    reject_reason: str = ""


# ═══════════════════════════════════════════════════════════════
# 滑点模型
# ═══════════════════════════════════════════════════════════════

class SlippageModel:
    """滑点计算：订单越大，滑点越大"""

    def __init__(
        self,
        model: Optional[str] = None,
        base_slippage: Optional[float] = None,   # 基础滑点
        volume_factor: Optional[float] = None,   # 成交量占比影响系数
    ):
        from config_utils import get_section
        mc = get_section("matching")
        self.model = model or mc.get("slippage_model", "linear")
        self.base_slippage = base_slippage if base_slippage is not None else float(mc.get("slippage_base", 0.0001))
        self.volume_factor = volume_factor if volume_factor is not None else 0.1

    def compute(self, order_size_usd: float, bar_volume_usd: float) -> float:
        """
        返回滑点比例（正数），如 0.001 = 0.1%
        """
        if bar_volume_usd <= 0:
            return self.base_slippage

        volume_ratio = order_size_usd / (bar_volume_usd * 0.1)  # 假设可用 10% 流动性

        if self.model == "linear":
            return self.base_slippage + self.volume_factor * volume_ratio
        elif self.model == "square_root":
            return self.base_slippage + self.volume_factor * np.sqrt(volume_ratio)
        else:  # fixed
            return self.base_slippage


# ═══════════════════════════════════════════════════════════════
# 撮合引擎
# ═══════════════════════════════════════════════════════════════

class MatchingEngine:
    """
    基于历史 K 线数据的本地撮合仿真引擎。

    撮合逻辑：
    - 市价买入：以 high 为参考价 + 滑点
    - 市价卖出：以 low 为参考价 - 滑点
    - 限价单：当 K 线范围穿过限价时成交
    - 止损单：当价格触发止损价时转为市价单
    """

    def __init__(
        self,
        commission: Optional[float] = None,   # 手续费（config matching.commission 优先）
        slippage_model: Optional[SlippageModel] = None,
    ):
        from config_utils import get_section
        mc = get_section("matching")
        self.commission = commission if commission is not None else float(mc.get("commission", 0.0004))
        self.slippage = slippage_model or SlippageModel()

    # ─── 市价单撮合 ──────────────────────────────────────

    def match_market(
        self,
        order: OrderRequest,
        kline: dict,       # 当前 K 线 {"o": float, "h": float, "l": float, "c": float, "v": float}
        current_price: float,
    ) -> FillResult:
        """
        市价单撮合。

        Args:
            order: 订单请求
            kline: 当前 K 线数据（O/H/L/C/V）
            current_price: 当前最新价（通常 C 或 close）
        """
        usd_value = order.size * current_price
        slip = self.slippage.compute(usd_value, kline["v"] * current_price)

        if order.side == OrderSide.LONG:
            ref_price = kline["h"]          # 买入以最高价为参考（悲观假设）
            fill_price = ref_price * (1 + slip)
        else:
            ref_price = kline["l"]          # 卖出以最低价为参考
            fill_price = ref_price * (1 - slip)

        fee = usd_value * self.commission

        return FillResult(
            filled=True,
            fill_price=fill_price,
            fill_size=order.size,
            fee=fee,
            slippage_pct=slip,
        )

    # ─── 限价单撮合 ──────────────────────────────────────

    def match_limit(
        self,
        order: OrderRequest,
        kline: dict,
    ) -> FillResult:
        """
        限价单撮合：K 线范围穿过限价时成交，以限价成交。
        买入限价 = 价格跌到 limit 以下成交
        卖出限价 = 价格涨到 limit 以上成交
        """
        if order.limit_price <= 0:
            return FillResult(reject_reason="无效限价")

        l, h = kline["l"], kline["h"]

        if order.side == OrderSide.LONG:
            if l <= order.limit_price:
                fill_price = order.limit_price
            else:
                return FillResult(reject_reason="未触及限价")
        else:
            if h >= order.limit_price:
                fill_price = order.limit_price
            else:
                return FillResult(reject_reason="未触及限价")

        usd_value = order.size * fill_price
        fee = usd_value * self.commission

        return FillResult(
            filled=True,
            fill_price=fill_price,
            fill_size=order.size,
            fee=fee,
            slippage_pct=0.0,     # 限价单无滑点
        )

    # ─── 止损单撮合 ──────────────────────────────────────

    def match_stop(
        self,
        order: OrderRequest,
        kline: dict,
        current_price: float,
    ) -> FillResult:
        """
        止损单撮合：触发后转为市价单。
        买入止损 = 价格涨到 stop 以上触发市价买入
        卖出止损 = 价格跌到 stop 以下触发市价卖出
        """
        if order.stop_price <= 0:
            return FillResult(reject_reason="无效止损价")

        l, h = kline["l"], kline["h"]
        triggered = False

        if order.side == OrderSide.LONG:
            if h >= order.stop_price:
                triggered = True
        else:
            if l <= order.stop_price:
                triggered = True

        if not triggered:
            return FillResult(reject_reason="未触发止损")

        # 触发后以市价成交
        return self.match_market(order, kline, current_price)

    # ─── 统一撮合入口 ────────────────────────────────────

    def match(
        self,
        order: OrderRequest,
        kline: dict,
        current_price: float,
    ) -> FillResult:
        """根据订单类型分发到对应撮合方法"""
        if order.order_type == OrderType.MARKET:
            return self.match_market(order, kline, current_price)
        elif order.order_type == OrderType.LIMIT:
            return self.match_limit(order, kline)
        elif order.order_type == OrderType.STOP:
            return self.match_stop(order, kline, current_price)
        else:
            return FillResult(reject_reason=f"未知订单类型: {order.order_type}")


# ═══════════════════════════════════════════════════════════════
# 资金费率结算
# ═══════════════════════════════════════════════════════════════

class FundingRateSettler:
    """永续合约资金费率结算器，每 8 小时结算一次"""

    SETTLE_INTERVAL = timedelta(hours=8)

    def __init__(self, funding_rates: Optional[pd.DataFrame] = None):
        """
        Args:
            funding_rates: DataFrame with columns [ts, rate]
        """
        self.rates = funding_rates

    def get_rate(self, timestamp: datetime) -> float:
        """获取指定时间戳对应的资金费率"""
        if self.rates is None or self.rates.empty:
            return 0.0
        # 找最近的前一个费率
        mask = self.rates["ts"] <= timestamp
        if not mask.any():
            return 0.0
        return float(self.rates.loc[mask, "rate"].iloc[-1])

    def settle(
        self,
        position_size: float,        # 持仓数量
        position_value: float,       # 持仓价值（USDT）
        position_side: OrderSide,
        timestamp: datetime,
    ) -> float:
        """
        计算应付/应收资金费。

        Returns:
            正数 = 收到资金费，负数 = 支付资金费
        """
        rate = self.get_rate(timestamp)
        if rate == 0.0:
            return 0.0

        payment = position_value * rate
        # 多头付空头（rate > 0 时多头付），空头收（rate < 0 时空头付）
        if position_side == OrderSide.LONG:
            return -payment
        else:
            return payment


# ═══════════════════════════════════════════════════════════════
# 爆仓模拟
# ═══════════════════════════════════════════════════════════════

class LiquidationEngine:
    """永续合约爆仓模拟"""

    def __init__(
        self,
        maintenance_margin_rate: float = 0.005,   # 维持保证金率 0.5%
    ):
        self.mmr = maintenance_margin_rate

    def check(
        self,
        balance: float,               # 账户余额（USDT）
        position_size: float,         # 持仓数量
        entry_price: float,           # 开仓均价
        leverage: float,              # 杠杆
        current_price: float,         # 当前价格
        side: OrderSide,
    ) -> tuple[bool, float]:
        """
        检查是否爆仓。

        Returns:
            (is_liquidated, liquidation_price)
        """
        if position_size == 0:
            return False, 0.0

        # 持仓保证金
        position_value = position_size * entry_price
        margin = position_value / leverage

        # 未实现盈亏
        if side == OrderSide.LONG:
            unrealized_pnl = position_size * (current_price - entry_price)
        else:
            unrealized_pnl = position_size * (entry_price - current_price)

        equity = balance + unrealized_pnl

        # 维持保证金
        maintenance_margin = position_value * self.mmr

        # 爆仓判定
        is_liquidated = equity < maintenance_margin

        # 爆仓价格（当 equity = maintenance_margin 时）
        if side == OrderSide.LONG:
            liq_price = entry_price - (balance - maintenance_margin) / position_size
        else:
            liq_price = entry_price + (balance - maintenance_margin) / position_size

        return is_liquidated, liq_price

    def compute_liquidation_price(
        self,
        entry_price: float,
        leverage: float,
        side: OrderSide,
        balance: float,
        position_size: float,
    ) -> float:
        """计算预估爆仓价格"""
        margin = position_size * entry_price / leverage
        maintenance = position_size * entry_price * self.mmr

        if side == OrderSide.LONG:
            return entry_price - (balance - maintenance) / position_size
        else:
            return entry_price + (balance - maintenance) / position_size
