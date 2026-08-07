"""Regime 数据驱动分类器测试（不再写死）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import pandas as pd
import pytest

from l2_sandbox.environment import EnvironmentRegistry


def _mk_df(closes):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "ts": ts, "open": closes, "high": closes * 1.01, "low": closes * 0.99,
        "close": closes, "volume": np.full(n, 1000.0),
    })


def test_trend_up_detected():
    closes = np.linspace(30000, 70000, 200) + np.random.randn(200) * 300
    assert EnvironmentRegistry().classify_regime(_mk_df(closes)) == "trend_up"


def test_trend_down_detected():
    closes = np.linspace(70000, 35000, 200) + np.random.randn(200) * 300
    assert EnvironmentRegistry().classify_regime(_mk_df(closes)) == "trend_down"


def test_range_detected():
    closes = np.full(200, 40000.0) + np.random.randn(200) * 150
    assert EnvironmentRegistry().classify_regime(_mk_df(closes)) == "range"


def test_high_vol_detected():
    rng = np.random.default_rng(1)
    # 无趋势的高波动：随机游走 × 正弦调制（趋势抵消）
    walk = np.cumsum(rng.standard_normal(200) * 3000)
    closes = 40000 + walk * np.sin(np.arange(200) / 10)
    assert EnvironmentRegistry().classify_regime(_mk_df(closes)) == "high_vol"


def test_short_data_unknown():
    assert EnvironmentRegistry().classify_regime(_mk_df([100, 101])) == "unknown"
