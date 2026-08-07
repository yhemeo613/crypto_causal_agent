"""P1-13 异常事件检测测试"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import pandas as pd
import pytest

from l3_perception.anomaly_detector import AnomalyDetector


def _kline_df(closes, base_price=100.0):
    """构造 K 线 df（open/high/low/close/volume/ts）"""
    rows = []
    prev = base_price
    for i, c in enumerate(closes):
        o = prev
        rows.append({
            "ts": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
            "open": float(o), "high": float(max(o, c) * 1.002), "low": float(min(o, c) * 0.998),
            "close": float(c), "volume": 100.0,
        })
        prev = c
    return pd.DataFrame(rows)


def test_flash_crash_single_bar():
    # 单根 -8% 跌幅
    df = _kline_df([100, 100, 100, 92])
    ev = AnomalyDetector(flash_crash_pct=0.05).detect_flash_crash(df)
    assert any(e.type == "flash_crash" and e.severity == "high" for e in ev)


def test_no_flash_crash_normal():
    df = _kline_df([100, 101, 102, 101.5])
    ev = AnomalyDetector().detect_flash_crash(df)
    assert ev == []


def test_vol_spike_detected():
    # 平稳 101 根后单根巨幅波动
    closes = [100 + np.sin(i / 10) for i in range(101)] + [130]
    df = _kline_df(closes)
    ev = AnomalyDetector(vol_spike_mult=2.0).detect_vol_spike(df)
    assert any(e.type == "vol_spike" for e in ev)


def test_funding_extreme():
    rates = [{"rate": 0.005, "ts": "2026-01-01T00:00:00"}]  # 0.5% 极端
    ev = AnomalyDetector().detect_funding_extreme(rates)
    assert len(ev) == 1 and ev[0].type == "funding_extreme"
    assert ev[0].severity == "high"  # > 3x 阈值


def test_detect_all_integration():
    df = _kline_df([100, 100, 100, 92])
    out = AnomalyDetector().detect_all(kline_df=df, funding_rates=[{"rate": 0.002, "ts": "x"}])
    types = {e["type"] for e in out}
    assert "flash_crash" in types
    assert "funding_extreme" in types
    for e in out:
        assert {"type", "severity", "detail"} <= set(e)
