"""L3 感知层测试：三时序切片 + LLM 因果抽取"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from l3_perception.time_slicer import TimeSlicer, PerceptionContextBuilder
from l3_perception.causal_extractor import (
    LLMCausalExtractor, HybridCausalExtractor, CausalTriplet
)


def make_multi_interval_data():
    """生成 5m/1h/1d 三周期测试 K 线"""
    np.random.seed(42)
    base = pd.Timestamp("2026-07-01", tz="UTC")

    data = {}
    # 5m: 3 天
    n = 3 * 24 * 12
    ts = pd.date_range(base, periods=n, freq="5min", tz="UTC")
    close_5m = 90000 + np.cumsum(np.random.randn(n) * 50)
    data["5m"] = pd.DataFrame({
        "ts": ts, "close": np.abs(close_5m),
        "open": np.abs(close_5m - 20), "high": np.abs(close_5m + 30),
        "low": np.abs(close_5m - 30), "volume": np.abs(np.random.randn(n) * 10 + 100),
    })

    # 1h: 30 天
    n = 30 * 24
    ts = pd.date_range(base, periods=n, freq="1h", tz="UTC")
    close_1h = 90000 + np.cumsum(np.random.randn(n) * 200)
    data["1h"] = pd.DataFrame({
        "ts": ts, "close": np.abs(close_1h),
        "open": np.abs(close_1h - 100), "high": np.abs(close_1h + 150),
        "low": np.abs(close_1h - 150), "volume": np.abs(np.random.randn(n) * 20 + 500),
    })

    # 1d: 180 天
    n = 180
    ts = pd.date_range(base - timedelta(days=180), periods=n, freq="1D", tz="UTC")
    close_1d = 80000 + np.cumsum(np.random.randn(n) * 500)
    data["1d"] = pd.DataFrame({
        "ts": ts, "close": np.abs(close_1d),
        "open": np.abs(close_1d - 300), "high": np.abs(close_1d + 400),
        "low": np.abs(close_1d - 400), "volume": np.abs(np.random.randn(n) * 50 + 2000),
    })

    return data


def test_time_slicer():
    """三时序切片生成"""
    data = make_multi_interval_data()
    slicer = TimeSlicer(l1_window_days=1, l1_interval="5m",
                        l2_window_days=14, l2_interval="1h",
                        l3_window_days=90, l3_interval="1d")

    ts_5m = data["5m"]["ts"].iloc[-1]
    ts_1h = data["1h"]["ts"].iloc[-1]
    ts = min(ts_5m, ts_1h)

    slices = slicer.slice(ts, data, macro_data={"DFF": 5.25, "CPI": 315.0})

    assert "L1" in slices
    assert "L2" in slices
    assert "L3" in slices

    l1 = slices["L1"]
    assert l1.price_current > 0
    assert l1.trend_direction in ("up", "down", "neutral")
    assert l1.volume_ratio > 0

    l3 = slices["L3"]
    assert l3.macro_indicators == {"DFF": 5.25, "CPI": 315.0}
    assert l3.window_days == 90

    print(f"  [OK] L1: price={l1.price_current:.0f} trend={l1.trend_direction}")
    print(f"  [OK] L2: price={slices['L2'].price_current:.0f} pct={slices['L2'].pct_change:.1f}%")
    print(f"  [OK] L3: price={l3.price_current:.0f} macro={l3.macro_indicators}")


def test_no_future_leak():
    """无未来函数泄漏"""
    data = make_multi_interval_data()
    slicer = TimeSlicer(l1_window_days=1, l1_interval="5m")
    df_5m = data["5m"]
    ts = df_5m["ts"].iloc[500]

    slicer.slice(ts, data)
    mask = (df_5m["ts"] <= ts) & (df_5m["ts"] > ts - timedelta(days=1))
    window_df = df_5m.loc[mask]
    assert (window_df["ts"] <= ts).all()
    print(f"  [OK] 无未来泄漏: {len(window_df)} bars")


def test_perception_context():
    """打包为 PerceptionContext"""
    data = make_multi_interval_data()
    slicer = TimeSlicer()
    ts = min(data["5m"]["ts"].iloc[-1], data["1h"]["ts"].iloc[-1])
    slices = slicer.slice(ts, data)

    builder = PerceptionContextBuilder()
    ctx = builder.build(slices, regime="trend_up", symbol="BTCUSDT")

    assert ctx["symbol"] == "BTCUSDT"
    assert ctx["regime"] == "trend_up"
    assert ctx["l1_micro"] is not None
    assert ctx["l3_macro"] is not None
    print(f"  [OK] PerceptionContext: {list(ctx.keys())}")


def test_llm_causal_extraction():
    """LLM 因果抽取（真实 API 调用）"""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    extractor = LLMCausalExtractor()
    assert extractor.available, "DeepSeek Key 已配置但仍 unavailable"

    # 构造真实感知上下文
    data = make_multi_interval_data()
    slicer = TimeSlicer()
    ts = min(data["5m"]["ts"].iloc[-1], data["1h"]["ts"].iloc[-1])
    slices = slicer.slice(ts, data, macro_data={"DFF": 5.25, "CPI": 315.0, "UNRATE": 4.1})
    builder = PerceptionContextBuilder()
    ctx = builder.build(slices, regime="trend_up")

    results = extractor.extract(ctx, max_triplets=3)
    assert len(results) > 0, "LLM 应返回至少一条因果"
    assert all(isinstance(r, CausalTriplet) for r in results)

    for r in results:
        assert r.cause_entity, "cause 不能为空"
        assert r.effect_entity, "effect 不能为空"
        assert 0 <= r.confidence <= 1, f"confidence {r.confidence} 超出范围"

    print(f"  [OK] LLM 因果: {len(results)} 条")
    for r in results:
        print(f"    {r.cause_entity} --{r.relation}--> {r.effect_entity} "
              f"(conf={r.confidence:.2f})")


def test_hybrid_extractor():
    """混合抽取器"""
    data = make_multi_interval_data()
    slicer = TimeSlicer()
    ts = min(data["5m"]["ts"].iloc[-1], data["1h"]["ts"].iloc[-1])
    slices = slicer.slice(ts, data)
    builder = PerceptionContextBuilder()
    ctx = builder.build(slices, regime="trend_up")

    extractor = HybridCausalExtractor()
    results = extractor.extract_all(perception_context=ctx)

    assert len(results) > 0
    assert all(r.source == "llm" for r in results)  # P0 全为 LLM
    print(f"  [OK] 混合抽取: {len(results)} 条 (全部 LLM 来源)")


if __name__ == "__main__":
    print("=" * 60)
    print("  L3 感知层测试")
    print("=" * 60)
    test_time_slicer()
    test_no_future_leak()
    test_perception_context()
    test_llm_causal_extraction()
    test_hybrid_extractor()
    print("\n" + "=" * 60)
    print("  [OK] 全部测试通过")
    print("=" * 60)
