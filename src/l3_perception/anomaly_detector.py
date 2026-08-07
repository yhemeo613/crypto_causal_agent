"""
P1-13 异常事件检测

检测市场异常事件（闪崩 / 异常波动 / 资金费率异常），
检测结果注入感知上下文，供 Agent 决策调整使用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AnomalyEvent:
    """异常事件"""
    type: str            # flash_crash | vol_spike | funding_extreme
    severity: str        # low | medium | high
    detail: str
    ts: Optional[datetime] = None


class AnomalyDetector:
    """市场异常事件检测器"""

    def __init__(
        self,
        flash_crash_pct: float = 0.05,        # 单根 K 线跌幅阈值 5%
        flash_crash_window_pct: float = 0.10, # 5 根累计跌幅阈值 10%
        vol_spike_mult: float = 3.0,          # ATR 相对 100 根均值倍数
        funding_extreme: float = 0.001,       # 资金费率绝对值 0.1%
    ):
        self.flash_crash_pct = flash_crash_pct
        self.flash_crash_window_pct = flash_crash_window_pct
        self.vol_spike_mult = vol_spike_mult
        self.funding_extreme = funding_extreme

    # ─── 闪崩检测（K 线） ────────────────────────────────

    def detect_flash_crash(self, df: pd.DataFrame) -> list[AnomalyEvent]:
        """单根跌幅超阈值 / 短窗口累计跌幅超阈值"""
        events = []
        if df is None or len(df) < 2:
            return events
        d = df.sort_values("ts").reset_index(drop=True)
        close = d["close"]
        # 单根跌幅
        ret = close.pct_change()
        last_ret = float(ret.iloc[-1]) if not ret.empty else 0.0
        if last_ret <= -self.flash_crash_pct:
            events.append(AnomalyEvent(
                type="flash_crash", severity="high",
                detail=f"单根K线跌幅 {last_ret*100:.2f}% (阈值 {self.flash_crash_pct*100:.0f}%)",
                ts=d["ts"].iloc[-1]))
        # 5 根累计跌幅
        if len(d) >= 5:
            win_ret = close.iloc[-5:].iloc[0] / close.iloc[-1] - 1
            if win_ret >= self.flash_crash_window_pct:
                events.append(AnomalyEvent(
                    type="flash_crash", severity="medium",
                    detail=f"5根K线累计跌幅 {win_ret*100:.2f}% (阈值 {self.flash_crash_window_pct*100:.0f}%)",
                    ts=d["ts"].iloc[-1]))
        return events

    # ─── 异常波动检测（ATR 倍数） ─────────────────────────

    def detect_vol_spike(self, df: pd.DataFrame) -> list[AnomalyEvent]:
        """当前 ATR 超过 100 根均值 3 倍"""
        events = []
        if df is None or len(df) < 100:
            return events
        d = df.sort_values("ts").reset_index(drop=True)
        high, low, close = d["high"], d["low"], d["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_base = tr.rolling(100).mean()
        if len(atr) < 2 or atr_base.iloc[-2] <= 0:
            return events
        ratio = atr.iloc[-1] / atr_base.iloc[-2]
        if ratio >= self.vol_spike_mult:
            events.append(AnomalyEvent(
                type="vol_spike", severity="medium",
                detail=f"ATR 达 100根均值 {ratio:.1f}x (阈值 {self.vol_spike_mult}x)",
                ts=d["ts"].iloc[-1]))
        return events

    # ─── 资金费率异常 ────────────────────────────────────

    def detect_funding_extreme(self, rates: list[dict]) -> list[AnomalyEvent]:
        """资金费率绝对值超阈值"""
        events = []
        if not rates:
            return events
        latest = rates[0]  # 已按 ts DESC
        rate = float(latest.get("rate", 0) or 0)
        if abs(rate) >= self.funding_extreme:
            events.append(AnomalyEvent(
                type="funding_extreme", severity="low" if abs(rate) < self.funding_extreme * 3 else "high",
                detail=f"资金费率 {rate*100:.4f}% (阈值 ±{self.funding_extreme*100:.2f}%)",
                ts=latest.get("ts")))
        return events

    # ─── 综合检测 ────────────────────────────────────────

    def detect_all(
        self,
        kline_df: pd.DataFrame = None,
        funding_rates: list[dict] = None,
    ) -> list[dict]:
        """全部检测，返回 dict 列表（供感知上下文注入）"""
        events: list[AnomalyEvent] = []
        if kline_df is not None and not kline_df.empty:
            events += self.detect_flash_crash(kline_df)
            events += self.detect_vol_spike(kline_df)
        if funding_rates:
            events += self.detect_funding_extreme(funding_rates)
        for e in events:
            logger.info(f"[anomaly] {e.type} ({e.severity}): {e.detail}")
        return [{"type": e.type, "severity": e.severity, "detail": e.detail,
                 "ts": e.ts if isinstance(e.ts, str) else (e.ts.isoformat() if e.ts else None)}
                for e in events]
