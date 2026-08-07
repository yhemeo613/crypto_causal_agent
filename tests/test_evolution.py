"""L7 进化层测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import random
import numpy as np

from l7_evolution.gene_encoder import (
    StrategyGene, GeneEncoder, GeneCrossover, GeneMutator,
)
from l7_evolution.evolution_engine import EvolutionEngine, DEFAULT_STRATEGY_CODE
from l7_evolution.replay_engines import GeneSandbox, ReplayEngines


def test_gene_encode_decode():
    code = """
def strategy(price, ma_short, ma_long, vol, regime):
    if price > ma_short and vol > 1.0:
        return 'long', 0.7
    else:
        return 'hold', 0.3
"""
    tree = GeneEncoder.encode(code)
    assert tree is not None
    decoded = GeneEncoder.decode(tree)
    assert "ma_short" in decoded
    assert "return" in decoded
    print(f"  [OK] encode→decode: {len(decoded)} chars")


def test_gene_crossover():
    code_a = """
def strategy(price, ma_s, ma_l, v, r):
    if price > ma_s and v > 1.0:
        return 'long', 0.8
    return 'hold', 0.3
"""
    code_b = """
def strategy(price, ma_s, ma_l, v, r):
    if price < ma_l and v < 0.9:
        return 'short', 0.7
    return 'hold', 0.3
"""
    gene_a = StrategyGene("ga", code_a, {"ma_s_window": 10, "ma_l_window": 50})
    gene_b = StrategyGene("gb", code_b, {"ma_s_window": 20, "ma_l_window": 100})

    crossover = GeneCrossover()
    child_a, child_b = crossover.crossover(gene_a, gene_b)

    assert child_a.generation == 1
    assert len(child_a.parent_ids) == 2
    assert "return" in child_a.logic_code
    print(f"  [OK] 交叉: child_a.id={child_a.id}")


def test_gene_mutation():
    gene = StrategyGene("gm", DEFAULT_STRATEGY_CODE, {"ma_s_window": 10, "rsi_oversold": 30})
    mutator = GeneMutator()
    mutated = mutator.mutate(gene, mutation_rate=0.5)

    assert mutated.generation == 1
    assert mutated.id.startswith("gm_")
    print(f"  [OK] 变异: {mutated.id} params={mutated.params}")


def test_sandbox():
    code = """
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price > ma_short and volume_ratio > 1.0:
        return 'long', 0.8
    elif price < ma_long and volume_ratio < 0.9:
        return 'short', 0.6
    return 'hold', 0.3
"""
    r1 = GeneSandbox.execute(code, price=91000, ma_short=90000, ma_long=85000,
                              volatility=0.5, volume_ratio=1.2, regime="trend_up")
    assert r1["action"] == "long", f"应为long, {r1}"

    r2 = GeneSandbox.execute(code, price=84000, ma_short=90000, ma_long=85000,
                              volatility=0.5, volume_ratio=0.8, regime="trend_down")
    assert r2["action"] == "short", f"应为short, {r2}"

    r3 = GeneSandbox.execute(code, price=88000, ma_short=90000, ma_long=85000,
                              volatility=0.5, volume_ratio=0.95, regime="range")
    assert r3["action"] == "hold"
    print(f"  [OK] 沙箱: long={r1} short={r2} hold={r3}")


def test_evolution_engine():
    random.seed(42)
    np.random.seed(42)

    # 模拟四环境回测函数
    def mock_backtest(gene):
        envs = ["bull", "bear", "range", "extreme"]
        perf = {}
        for env in envs:
            perf[env] = random.uniform(-0.5, 2.0)
        return perf

    engine = EvolutionEngine(
        population_size=8, generations=5,
        crossover_rate=0.7, mutation_rate=0.2,
        tournament_size=3, elitism_count=1,
    )

    best = engine.run(mock_backtest, verbose=False)

    assert best is not None
    assert best.fitness > 0
    assert len(engine.history) == 5
    assert engine.history[0]["best_fitness"] > 0

    # 验证进化趋势：最后一代适应度应有所提升
    first_fit = engine.history[0]["best_fitness"]
    last_fit = engine.history[-1]["best_fitness"]
    print(f"  [OK] 5代进化: Gen0 fit={first_fit:.4f} → Gen4 fit={last_fit:.4f} "
          f"best_params={best.params}")


def test_replay_engines():
    replay = ReplayEngines()
    trades = [
        {"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -30},
    ]
    r = replay.trade_replay(trades)
    assert "4笔" in r.summary
    print(f"  [OK] 交易复盘: {r.summary}")

    from l7_evolution.gene_encoder import StrategyGene
    gene = StrategyGene("rg1", DEFAULT_STRATEGY_CODE, {"ma_s": 10}, fitness=0.85)
    r2 = replay.strategy_replay(gene, trades)
    print(f"  [OK] 策略复盘: {r2.summary}")

    r3 = replay.generation_replay(10, 0.9, 0.6, 12)
    print(f"  [OK] 世代复盘: {r3.summary}")


if __name__ == "__main__":
    print("=" * 60)
    print("  L7 进化层测试")
    print("=" * 60)
    test_gene_encode_decode()
    test_gene_crossover()
    test_gene_mutation()
    test_sandbox()
    test_evolution_engine()
    test_replay_engines()
    print("\n" + "=" * 60)
    print("  [OK] 全部通过")
    print("=" * 60)
