"""撮合引擎单元测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l1_env_base.matching_engine import (
    MatchingEngine, OrderRequest, OrderSide, OrderType,
    FillResult, SlippageModel, LiquidationEngine, FundingRateSettler,
)
import pandas as pd
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════
# 1. 市价单撮合
# ═══════════════════════════════════════════════════════════════

def test_market_buy():
    engine = MatchingEngine()
    order = OrderRequest("BTCUSDT", OrderSide.LONG, OrderType.MARKET, size=0.1, leverage=5)
    kline = {"o": 90000, "h": 90500, "l": 89500, "c": 90300, "v": 100}
    result = engine.match_market(order, kline, current_price=kline["c"])
    assert result.filled
    assert result.fill_price >= kline["h"]               # 买入价 ≥ 最高价（含滑点）
    assert result.fill_price < kline["h"] * 1.005        # 滑点不超过 0.5%
    assert result.fee > 0
    assert result.slippage_pct >= 0
    print(f"  [OK] 买入 {kline['h']} → {result.fill_price:.2f} (滑点 {result.slippage_pct*100:.4f}%, 费 {result.fee:.2f})")


def test_market_sell():
    engine = MatchingEngine()
    order = OrderRequest("BTCUSDT", OrderSide.SHORT, OrderType.MARKET, size=0.1, leverage=5)
    kline = {"o": 90000, "h": 90500, "l": 89500, "c": 89700, "v": 100}
    result = engine.match_market(order, kline, current_price=kline["c"])
    assert result.filled
    assert result.fill_price <= kline["l"]               # 卖出价 ≤ 最低价
    print(f"  [OK] 卖出 {kline['l']} → {result.fill_price:.2f} (滑点 {result.slippage_pct*100:.4f}%)")


# ═══════════════════════════════════════════════════════════════
# 2. 滑点与成交量正相关
# ═══════════════════════════════════════════════════════════════

def test_slippage_scales_with_size():
    slippage = SlippageModel("linear", base_slippage=0.0001, volume_factor=0.1)
    bar_vol = 1_000_000  # $1M volume

    slip_small = slippage.compute(1_000, bar_vol)
    slip_large = slippage.compute(100_000, bar_vol)
    assert slip_large > slip_small, f"slip_large={slip_large} <= slip_small={slip_small}"
    print(f"  [OK] 小额滑点 {slip_small*100:.4f}% < 大额滑点 {slip_large*100:.4f}%")


# ═══════════════════════════════════════════════════════════════
# 3. 爆仓计算
# ═══════════════════════════════════════════════════════════════

def test_liquidation():
    liq = LiquidationEngine(maintenance_margin_rate=0.005)

    # 账户 $10000, 0.1 BTC 多头 @90000, 5x 杠杆
    entry = 90000
    size = 0.1
    lev = 5
    balance = 10000
    margin = size * entry / lev                           # = 1800
    liq_price = liq.compute_liquidation_price(entry, lev, OrderSide.LONG, balance, size)
    print(f"  [OK] 多头爆仓价: ${liq_price:.2f} (入场 {entry})")
    assert liq_price < entry, "多头爆仓价应低于入场价"

    # 价格跌到爆仓价以下
    is_liq, _ = liq.check(balance, size, entry, lev, liq_price - 100, OrderSide.LONG)
    assert is_liq, f"价格 {liq_price - 100} 应触发爆仓"

    # 价格高于爆仓价不爆
    is_liq2, _ = liq.check(balance, size, entry, lev, entry, OrderSide.LONG)
    assert not is_liq2, "当前价格等于入场价不应爆仓"

    # 空头爆仓
    liq_short = liq.compute_liquidation_price(entry, lev, OrderSide.SHORT, balance, size)
    assert liq_short > entry, "空头爆仓价应高于入场价"
    print(f"  [OK] 空头爆仓价: ${liq_short:.2f} (入场 {entry})")


# ═══════════════════════════════════════════════════════════════
# 4. 限价单
# ═══════════════════════════════════════════════════════════════

def test_limit_order():
    engine = MatchingEngine()
    kline = {"o": 90000, "h": 92000, "l": 88000, "c": 91000, "v": 100}

    # 限价买入 @89000 — 最低价 88000 < 89000，应成交
    buy = OrderRequest("BTCUSDT", OrderSide.LONG, OrderType.LIMIT, size=0.1, limit_price=89000)
    r = engine.match_limit(buy, kline)
    assert r.filled
    assert r.fill_price == 89000
    assert r.slippage_pct == 0.0
    print(f"  [OK] 限价买入 @89000 成交")

    # 限价买入 @87000 — 最低价 88000 > 87000，不应成交
    buy2 = OrderRequest("BTCUSDT", OrderSide.LONG, OrderType.LIMIT, size=0.1, limit_price=87000)
    r2 = engine.match_limit(buy2, kline)
    assert not r2.filled
    print(f"  [OK] 限价买入 @87000 未触及")


# ═══════════════════════════════════════════════════════════════
# 5. 止损单
# ═══════════════════════════════════════════════════════════════

def test_stop_order():
    engine = MatchingEngine()
    kline = {"o": 90000, "h": 92000, "l": 85000, "c": 86000, "v": 100}

    # 卖出止损 @87000 — 最低价 85000 < 87000，应触发
    sell_stop = OrderRequest("BTCUSDT", OrderSide.SHORT, OrderType.STOP, size=0.1, stop_price=87000)
    r = engine.match_stop(sell_stop, kline, current_price=kline["c"])
    assert r.filled
    print(f"  [OK] 止损卖出触发 → {r.fill_price:.2f}")

    # 买入止损 @93000 — 最高价 92000 < 93000，不触发
    buy_stop = OrderRequest("BTCUSDT", OrderSide.LONG, OrderType.STOP, size=0.1, stop_price=93000)
    r2 = engine.match_stop(buy_stop, kline, current_price=kline["c"])
    assert not r2.filled
    print(f"  [OK] 止损买入 @93000 未触发")


# ═══════════════════════════════════════════════════════════════
# 6. 资金费率结算
# ═══════════════════════════════════════════════════════════════

def test_funding_rate():
    rates_df = pd.DataFrame([
        {"ts": pd.Timestamp("2026-01-01 00:00", tz="UTC"), "rate": 0.0001},  # 0.01%
        {"ts": pd.Timestamp("2026-01-01 08:00", tz="UTC"), "rate": -0.0005}, # -0.05%
    ])
    settler = FundingRateSettler(rates_df)

    ts = pd.Timestamp("2026-01-01 04:00", tz="UTC")  # 在第一条费率期间
    val = 100000  # $10万持仓

    payment_long = settler.settle(1, val, OrderSide.LONG, ts)
    assert payment_long < 0, f"正费率时多头应支付，实际 {payment_long}"
    print(f"  [OK] 多头支付: {payment_long:.2f} USDT (费率 0.01%)")

    ts2 = pd.Timestamp("2026-01-01 12:00", tz="UTC")  # 在第二条费率期间
    payment_short = settler.settle(1, val, OrderSide.SHORT, ts2)
    assert payment_short < 0, f"负费率时空头应支付，实际 {payment_short}"
    print(f"  [OK] 空头支付: {payment_short:.2f} USDT (费率 -0.05%)")


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  撮合引擎测试")
    print("=" * 60)
    test_market_buy()
    test_market_sell()
    test_slippage_scales_with_size()
    test_liquidation()
    test_limit_order()
    test_stop_order()
    test_funding_rate()
    print("\n" + "=" * 60)
    print("  [OK] 全部测试通过")
    print("=" * 60)
