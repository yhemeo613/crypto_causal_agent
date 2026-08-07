"""P1-04 Regime 自适应权重调节测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l6_agent.regime_adapter import RegimeAdapter


def test_trend_up_full_position():
    r = RegimeAdapter().adjust("trend_up", 0.2, 2.0, 0.6)
    assert r["position_pct"] == 0.2
    assert r["leverage"] == 2.0
    assert r["gated"] is False
    assert r["mode"] == "顺势满仓"


def test_high_vol_reduces_position_and_leverage():
    r = RegimeAdapter().adjust("high_vol", 0.2, 2.0, 0.6)
    assert r["position_pct"] == 0.1   # 0.2 * 0.5
    assert r["leverage"] == 1.0       # 上限 1x
    assert r["mode"] == "风控优先"


def test_low_confidence_gated():
    r = RegimeAdapter().adjust("high_vol", 0.2, 2.0, 0.5)  # conf 0.5 < 0.55 门槛
    assert r["gated"] is True
    assert r["position_pct"] == 0.0


def test_range_halves_position():
    r = RegimeAdapter().adjust("range", 0.2, 2.0, 0.6)
    assert r["position_pct"] == 0.12  # 0.2 * 0.6
    assert r["leverage"] == 1.0


def test_unknown_default():
    r = RegimeAdapter().adjust("weird", 0.2, 3.0, 0.6)
    assert r["mode"] == "默认"
    assert r["position_pct"] == 0.16  # 0.2 * 0.8


def test_describe_all_regimes():
    d = RegimeAdapter().describe()
    assert set(d) == {"trend_up", "trend_down", "range", "high_vol", "unknown"}
