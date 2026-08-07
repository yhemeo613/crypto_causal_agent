"""账户系统 + 硬风控 单元测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l1_env_base.account import Account
from l1_env_base.risk_control import RiskController
from l1_env_base.matching_engine import OrderSide


def test_open_close():
    """正常开平仓"""
    acc = Account(initial_balance=100_000, max_leverage=5)
    pos = acc.open_position("BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=5, fee=3.6)
    assert pos.size == 0.1
    assert acc.balance == 100_000 - pos.margin - 3.6
    assert acc.used_margin > 0

    # 价格上涨
    trade = acc.close_position("BTCUSDT", exit_price=95000, fee=3.8, reason="manual")
    assert trade.pnl > 0, f"盈利应为正, 实际 {trade.pnl}"
    assert acc.positions == {}
    print(f"  [OK] 开仓→盈利平仓: PNL={trade.pnl:.2f}")


def test_stop_loss():
    """止损平仓"""
    acc = Account(initial_balance=100_000)
    pos = acc.open_position("BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=5, fee=3.6)
    trade = acc.close_position("BTCUSDT", exit_price=85000, fee=3.4, reason="stop_loss")
    assert trade.pnl < 0, f"亏损应为负, 实际 {trade.pnl}"
    print(f"  [OK] 止损平仓: PNL={trade.pnl:.2f}")


def test_risk_leverage_reject():
    """杠杆超限被拒绝"""
    rc = RiskController(max_leverage=5)
    acc = Account(initial_balance=100_000)
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=10, confidence=0.8)
    assert not result.allowed
    assert "杠杆" in result.reject_reason
    assert rc.total_rejects == 1
    print(f"  [OK] 杠杆10x拒绝: {result.reject_reason}")


def test_risk_confidence_reject():
    """置信度过低被拒绝"""
    rc = RiskController(min_confidence=0.4)
    acc = Account(initial_balance=100_000)
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=3, confidence=0.2)
    assert not result.allowed
    assert "置信度" in result.reject_reason
    print(f"  [OK] 置信度0.2拒绝: {result.reject_reason}")


def test_risk_confidence_pass():
    """置信度达标通过"""
    rc = RiskController(min_confidence=0.4)
    acc = Account(initial_balance=100_000)
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=3, confidence=0.7)
    assert result.allowed
    print(f"  [OK] 置信度0.7通过, 全部检查: {[c['rule'] for c in result.checks]}")


def test_risk_daily_trades():
    """日交易次数超限"""
    rc = RiskController(max_daily_trades=20)
    acc = Account(initial_balance=100_000)
    acc.daily_trade_count = 20  # 模拟已满
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=3, confidence=0.8)
    assert not result.allowed
    assert "日交易" in result.reject_reason
    print(f"  [OK] 日交易20次拒绝: {result.reject_reason}")


def test_risk_max_position():
    """最大持仓占比超限"""
    rc = RiskController(max_position_pct=0.5)
    acc = Account(initial_balance=10_000)
    acc.open_position("ETHUSDT", OrderSide.LONG, size=1, entry_price=3000, leverage=2, fee=1.2)
    # 已用保证金 = 1*3000/2 = 1500, 余额约 8499, 占比约 17.6%
    # 再开 BTC 大仓位
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.5, entry_price=90000, leverage=2, confidence=0.8)
    # 新保证金 = 0.5*90000/2 = 22500, 总额 = 24000, 余额约8499, 占比 = 282%
    assert not result.allowed
    assert "持仓占比" in result.reject_reason
    print(f"  [OK] 持仓占比超限拒绝: {result.reject_reason}")


def test_risk_all_checks_pass():
    """所有风控通过"""
    rc = RiskController()
    acc = Account(initial_balance=100_000)
    result = rc.check(acc, "BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=3, confidence=0.6, stop_loss=89100)
    assert result.allowed
    assert len(result.checks) == 6
    all_passed = all(c["passed"] for c in result.checks)
    assert all_passed
    print(f"  [OK] 6项检查全部通过: {[c['rule'] for c in result.checks]}")


def test_liquidation_triggered():
    """爆仓价计算 + 检测正确"""
    from l1_env_base.matching_engine import LiquidationEngine

    liq_engine = LiquidationEngine()
    acc = Account(initial_balance=100_000)
    pos = acc.open_position("BTCUSDT", OrderSide.LONG, size=0.1, entry_price=90000, leverage=5, fee=3.6)

    # 验证爆仓价在入场价之下（多头）
    assert pos.liquidation_price < 90000
    liq_pct = (90000 - pos.liquidation_price) / 90000 * 100
    print(f"  [OK] 多头爆仓价: {pos.liquidation_price:.0f} (入场90000, 距入场{liq_pct:.1f}%)")

    # LiquidationEngine 检测：价格跌到爆仓价以下应触发
    # balance 传保证金（逐仓模式），不是整个账户余额
    margin = pos.margin
    is_liq, _ = liq_engine.check(
        margin, pos.size, pos.entry_price, pos.leverage,
        pos.liquidation_price - 100, OrderSide.LONG,
    )
    assert is_liq, f"价格 {pos.liquidation_price - 100:.0f} 应触发爆仓"

    # 价格高于爆仓价不触发
    is_liq2, _ = liq_engine.check(
        margin, pos.size, pos.entry_price, pos.leverage,
        pos.liquidation_price + 100, OrderSide.LONG,
    )
    assert not is_liq2
    print(f"  [OK] 爆仓检测正确: 低于爆仓价触发, 高于不触发")

    # close_only 检查：极低余额只能平仓
    acc2 = Account(initial_balance=100_000)
    acc2.balance = 500
    rc = RiskController(max_drawdown_pct=0.3)
    cr = rc.check_close_only(acc2)
    assert not cr.allowed, "极端亏损应触发只平仓"
    print(f"  [OK] 极端亏损触发只平仓: {cr.reject_reason}")


if __name__ == "__main__":
    print("=" * 60)
    print("  账户系统 + 硬风控 测试")
    print("=" * 60)
    test_open_close()
    test_stop_loss()
    test_risk_leverage_reject()
    test_risk_confidence_reject()
    test_risk_confidence_pass()
    test_risk_daily_trades()
    test_risk_max_position()
    test_risk_all_checks_pass()
    test_liquidation_triggered()
    print("\n" + "=" * 60)
    print("  [OK] 全部测试通过 — 风控 100% 生效")
    print("=" * 60)
