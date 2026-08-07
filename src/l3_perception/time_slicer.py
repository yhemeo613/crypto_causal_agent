"""
L3 三时序切片感知
对每个时间点生成 L1(微观)/L2(中期)/L3(宏观) 三层感知切片
严格遵循时间对齐规则，零未来函数泄漏
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class TimeSlice:
    """单个时间切片"""
    level: str                         # L1 | L2 | L3
    timestamp: datetime
    window_days: int
    kline_interval: str

    # 价格统计
    price_current: float = 0.0
    price_mean: float = 0.0
    price_std: float = 0.0
    price_min: float = 0.0
    price_max: float = 0.0
    pct_change: float = 0.0            # 窗口内涨跌幅
    volatility: float = 0.0            # 年化波动率

    # 趋势指标
    trend_direction: str = "neutral"   # up | down | neutral
    trend_strength: float = 0.0        # 0~1
    ma_short: float = 0.0
    ma_long: float = 0.0

    # 成交量
    volume_current: float = 0.0
    volume_mean: float = 0.0
    volume_ratio: float = 0.0          # 当前/均值

    # 高/低点
    is_local_high: bool = False
    is_local_low: bool = False

    # 宏观（L3 专属）
    macro_indicators: dict = field(default_factory=dict)


class TimeSlicer:
    """
    三时序切片生成器。

    取当前时间点 t，向前看三段时间窗口，生成 L1/L2/L3 切片。
    严格使用 t 之前的数据，绝不泄漏未来信息。
    """

    def __init__(
        self,
        l1_window_days: int = 1,
        l1_interval: str = "5m",
        l2_window_days: int = 14,
        l2_interval: str = "1h",
        l3_window_days: int = 90,
        l3_interval: str = "1d",
    ):
        self.l1_window = timedelta(days=l1_window_days)
        self.l1_interval = l1_interval
        self.l2_window = timedelta(days=l2_window_days)
        self.l2_interval = l2_interval
        self.l3_window = timedelta(days=l3_window_days)
        self.l3_interval = l3_interval

    def slice(
        self,
        timestamp: datetime,
        klines: dict[str, pd.DataFrame],     # interval → DataFrame
        macro_data: Optional[dict] = None,    # 宏观指标 {name: value}
    ) -> dict[str, TimeSlice]:
        """
        生成当前时刻的三层感知切片。

        Args:
            timestamp: 当前时间点
            klines: {"5m": df, "1h": df, "1d": df} 多周期 K 线
            macro_data: 可选宏观数据

        Returns:
            {"L1": TimeSlice, "L2": TimeSlice, "L3": TimeSlice}
        """
        slices = {}

        # L1 微观
        df_1 = klines.get(self.l1_interval)
        if df_1 is not None:
            slices["L1"] = self._build_slice(
                "L1", timestamp, df_1, self.l1_window, self.l1_interval
            )

        # L2 中期
        df_2 = klines.get(self.l2_interval)
        if df_2 is not None:
            slices["L2"] = self._build_slice(
                "L2", timestamp, df_2, self.l2_window, self.l2_interval
            )

        # L3 宏观
        df_3 = klines.get(self.l3_interval)
        if df_3 is not None:
            s3 = self._build_slice(
                "L3", timestamp, df_3, self.l3_window, self.l3_interval
            )
            if macro_data:
                s3.macro_indicators = macro_data
            slices["L3"] = s3

        return slices

    # ─── 内部 ──────────────────────────────────────────────

    def _build_slice(
        self, level: str, ts: datetime,
        df: pd.DataFrame, window: timedelta, interval: str,
    ) -> TimeSlice:
        """构造单层切片，严格往前看"""
        # 只取 ts 之前的数据（不含 ts 后的未来数据）
        mask = (df["ts"] <= ts) & (df["ts"] > ts - window)
        window_df = df.loc[mask].copy()

        if window_df.empty:
            return TimeSlice(level=level, timestamp=ts, window_days=window.days, kline_interval=interval)

        close = window_df["close"]
        volume = window_df["volume"]
        current_price = float(close.iloc[-1])

        # 波动率（年化）
        returns = close.pct_change().dropna()
        periods_per_year = {"5m": 365*24*12, "1m": 365*24*60, "15m": 365*24*4,
                            "1h": 365*24, "4h": 365*6, "1d": 365}
        annual_factor = np.sqrt(periods_per_year.get(interval, 365*24))
        vol = float(returns.std() * annual_factor) if len(returns) > 1 else 0.0

        # 趋势判断
        ma_short = float(close.tail(min(len(close)//3, 20)).mean())
        ma_long = float(close.mean())
        trend_dir = "up" if current_price > ma_long * 1.02 else (
            "down" if current_price < ma_long * 0.98 else "neutral"
        )
        # 趋势强度：价格偏离均线的标准差倍数
        trend_strength = min(1.0, abs(current_price - ma_long) / (close.std() + 1e-9))

        # 局部极值（近 10 根 K 线）
        recent_n = min(10, len(close))
        recent_high = close.iloc[-recent_n:].max()
        recent_low = close.iloc[-recent_n:].min()

        return TimeSlice(
            level=level,
            timestamp=ts,
            window_days=window.days,
            kline_interval=interval,
            price_current=current_price,
            price_mean=float(close.mean()),
            price_std=float(close.std()),
            price_min=float(close.min()),
            price_max=float(close.max()),
            pct_change=float((close.iloc[-1] / close.iloc[0] - 1) * 100) if len(close) > 1 else 0.0,
            volatility=vol,
            trend_direction=trend_dir,
            trend_strength=trend_strength,
            ma_short=ma_short,
            ma_long=ma_long,
            volume_current=float(volume.iloc[-1]),
            volume_mean=float(volume.mean()),
            volume_ratio=float(volume.iloc[-1] / volume.mean()) if volume.mean() > 0 else 1.0,
            is_local_high=current_price >= recent_high * 0.99,
            is_local_low=current_price <= recent_low * 1.01,
        )


class PerceptionContextBuilder:
    """
    将三时序切片 + 市场 Regime 打包为 PerceptionContext。
    这是对接 L6 LangGraph State 的输入格式。
    """

    def build(
        self,
        slices: dict[str, TimeSlice],
        regime: str = "unknown",
        symbol: str = "BTCUSDT",
    ) -> dict:
        """生成 PerceptionContext dict，可直接用于 AgentState"""
        return {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "regime": regime,
            "l1_micro": self._slice_to_dict(slices.get("L1")),
            "l2_meso": self._slice_to_dict(slices.get("L2")),
            "l3_macro": self._slice_to_dict(slices.get("L3")),
        }

    @staticmethod
    def _slice_to_dict(s: Optional[TimeSlice]) -> Optional[dict]:
        if s is None:
            return None
        return {
            "level": s.level,
            "window_days": s.window_days,
            "price_current": s.price_current,
            "price_mean": s.price_mean,
            "pct_change": s.pct_change,
            "volatility": s.volatility,
            "trend_direction": s.trend_direction,
            "trend_strength": s.trend_strength,
            "volume_ratio": s.volume_ratio,
            "is_local_high": s.is_local_high,
            "is_local_low": s.is_local_low,
            "macro_indicators": s.macro_indicators if s.level == "L3" else {},
        }
