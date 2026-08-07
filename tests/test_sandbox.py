"""四环境沙箱测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from l2_sandbox.environment import EnvironmentRegistry, Environment


def make_test_kline(symbol="BTCUSDT", interval="1h", days=400, seed=42):
    """生成测试用的模拟 K 线数据并保存"""
    np.random.seed(seed)
    n = days * 24
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")

    # 模拟牛→熊→震荡→极端 四阶段走势
    close = np.zeros(n)
    phase_len = n // 4
    # Phase 1: 牛市上涨（40000→70000）
    close[:phase_len] = np.linspace(40000, 70000, phase_len) + np.random.randn(phase_len) * 800
    # Phase 2: 熊市下跌（70000→30000）
    close[phase_len:2*phase_len] = np.linspace(70000, 30000, phase_len) + np.random.randn(phase_len) * 1000
    # Phase 3: 震荡（30000→35000 窄幅）
    close[2*phase_len:3*phase_len] = np.linspace(30000, 35000, phase_len) + np.random.randn(phase_len) * 300
    # Phase 4: 极端波动
    rng = np.random.default_rng(seed)
    close[3*phase_len:] = 35000 + rng.standard_normal(phase_len) * 3000

    close = np.abs(close)
    high = close + np.abs(np.random.randn(n) * 200)
    low = close - np.abs(np.random.randn(n) * 200)
    open_p = low + np.abs(np.random.randn(n) * (high - low))
    volume = np.abs(np.random.randn(n) * 100 + 500)

    df = pd.DataFrame({
        "ts": ts, "open": open_p, "high": high, "low": low,
        "close": close, "volume": volume,
    })

    data_dir = Path("data/raw")
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{symbol}_{interval}_2024-01-01_2026-06-30.parquet"
    df.to_parquet(path, index=False)
    return df


def test_list_environments():
    """列出所有环境"""
    registry = EnvironmentRegistry()
    envs = registry.list_environments()
    assert len(envs) == 4
    names = [e.name for e in envs]
    assert "bull" in names
    assert "bear" in names
    assert "range" in names
    assert "extreme" in names
    print(f"  [OK] 4个环境: {names}")


def test_load_and_switch():
    """加载环境 + 切换无泄漏"""
    make_test_kline()
    registry = EnvironmentRegistry()

    # 加载牛市槽位（regime 数据驱动，不再写死）
    bull = registry.load("bull", interval="1h")
    assert bull.name == "bull"
    assert not bull.data.empty
    assert bull.regime == registry.classify_regime(bull.data)
    bull_count = registry.get_bar_count()
    print(f"  [OK] 牛市槽位: {bull_count} bars, regime={bull.regime}（数据驱动）")

    # 切换到熊市（旧数据应清除）
    bear = registry.load("bear", interval="1h")
    assert bear.name == "bear"
    assert bear.regime == registry.classify_regime(bear.data)
    bear_count = registry.get_bar_count()
    assert bear_count != bull_count, "不同环境应有不同数据量"
    print(f"  [OK] 熊市: {bear_count} bars, regime={bear.regime}")

    # 验证旧环境已清除
    current = registry.get_current()
    assert current is not None
    assert current.name == "bear"
    print(f"  [OK] 环境切换: 当前=bear, 旧数据已清除")


def test_iter_bars():
    """遍历 K 线"""
    make_test_kline()
    registry = EnvironmentRegistry()
    env = registry.load("range", interval="1h")

    bars = list(registry.iter_bars(env))
    assert len(bars) > 0
    bar = bars[0]
    assert "ts" in bar
    assert "o" in bar
    assert "h" in bar
    assert "l" in bar
    assert "c" in bar
    assert "v" in bar
    assert bar["regime"] == registry.classify_regime(env.data)  # 数据驱动
    print(f"  [OK] 遍历 {len(bars)} bars, 首bar: o={bar['o']:.0f} c={bar['c']:.0f} regime={bar['regime']}")


def test_summary():
    """环境摘要"""
    make_test_kline()
    registry = EnvironmentRegistry()
    env = registry.load("bull", interval="1h")
    s = registry.summary(env)

    assert s["name"] == "bull"
    assert s["bars"] > 0
    assert s["pct_change"] != 0
    assert s["max_drawdown_pct"] < 0  # 牛市最大回撤应为负
    print(f"  [OK] 摘要: {s['bars']}bars, "
          f"价格{s['price_start']}→{s['price_end']} ({s['pct_change']}%), "
          f"最大回撤{s['max_drawdown_pct']}%, 年化波动{s['volatility_annualized']}%")


def test_regime_classifier():
    """Regime 自动分类"""
    registry = EnvironmentRegistry()
    make_test_kline()
    env = registry.load("bull", interval="1h")

    # 用数据的前 200 条（趋势上涨约 10%）测试分类器
    df_small = env.data.head(200)
    regime = registry.classify_regime(df_small, window=50)
    assert regime in ("trend_up", "trend_down", "range", "high_vol")
    print(f"  [OK] 自动分类: {regime}")

    # 极端行情测试：构造纯高波动无趋势
    np.random.seed(1)
    n = 100
    base = 1000
    noise = np.random.randn(n) * 200
    high_vol = pd.DataFrame({
        "close": base + noise - noise.mean(),  # 中心化，无趋势
    })
    r2 = registry.classify_regime(high_vol, window=30)
    assert r2 == "high_vol", f"高波动应被分类为 high_vol, 实际 {r2}"
    print(f"  [OK] 高波动检测: {r2}")


if __name__ == "__main__":
    print("=" * 60)
    print("  四环境沙箱测试")
    print("=" * 60)
    test_list_environments()
    test_load_and_switch()
    test_iter_bars()
    test_summary()
    test_regime_classifier()
    print("\n" + "=" * 60)
    print("  [OK] 全部测试通过")
    print("=" * 60)
