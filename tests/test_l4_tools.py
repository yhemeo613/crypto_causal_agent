"""P0-11 三级权限工具调度层测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l4_tools.tool_registry import (
    ToolCallDenied, ToolPermission, ToolRegistry, registry,
)


@pytest.fixture
def reg():
    return ToolRegistry()


# ─── 注册与枚举 ─────────────────────────────────────────────

def test_builtin_tools_registered(reg):
    tools = {t["name"]: t for t in reg.list_tools()}
    assert set(tools) == {
        "query_klines", "query_funding", "query_macro", "query_causal_graph",
        "calc_indicators", "calc_volatility", "submit_order",
    }
    # 三级权限齐全
    perms = {t["permission"] for t in reg.list_tools()}
    assert perms == {"read", "calc", "act"}
    # ACT 工具必须带门禁
    assert tools["submit_order"]["requires_gate"] is True
    assert tools["query_klines"]["requires_gate"] is False


def test_duplicate_register_rejected(reg):
    with pytest.raises(ValueError):
        reg.register("query_klines", ToolPermission.READ, lambda: 1)


def test_unknown_tool_denied(reg):
    with pytest.raises(ToolCallDenied):
        reg.call("not_exist")


# ─── 权限门禁：ACT 必须经辩论决策通过 ─────────────────────────

def test_act_denied_without_gate(reg):
    with pytest.raises(ToolCallDenied) as ei:
        reg.call("submit_order", decision_passed=False, symbol="BTCUSDT")
    assert "辩论决策" in str(ei.value)


def test_act_allowed_with_gate(reg):
    # 门禁通过后调用（不校验撮合结果，只验证门禁放行）
    result = reg.call("submit_order", decision_passed=True,
                      symbol="BTCUSDT", side="long", size_units=0.0001, leverage=2)
    assert "ok" in result  # 已放行到真实撮合（可能因无行情返回 ok=False）


def test_read_calc_no_gate_needed(reg):
    klines = reg.call("query_klines", symbol="BTCUSDT", interval="1h", limit=10)
    assert isinstance(klines, list) and len(klines) <= 10
    vol = reg.call("calc_volatility", symbol="BTCUSDT", interval="1h")
    assert "volatility_annualized" in vol


# ─── 权限隔离：只读/计算不可触发交易 ─────────────────────────

def test_permission_levels_are_strict(reg):
    act_tools = [t for t in reg.list_tools() if t["permission"] == "act"]
    read_calc = [t for t in reg.list_tools() if t["permission"] in ("read", "calc")]
    # 只有 ACT 有门禁
    assert all(t["requires_gate"] for t in act_tools)
    assert all(not t["requires_gate"] for t in read_calc)


def test_call_log_records(reg):
    reg.call("query_klines", symbol="BTCUSDT", interval="1h", limit=5)
    log = reg.call_log_since()
    assert log and log[-1]["allowed"] is True
    assert log[-1]["permission"] == "read"
