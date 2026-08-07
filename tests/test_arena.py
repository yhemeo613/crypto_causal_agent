"""P1-01 对抗竞技场测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l7_evolution.arena import Arena
from l7_evolution.evolution_engine import StrategyGene


def _mk_gene(gid: str, **params):
    base = {
        "ma_short_window": 10, "ma_long_window": 40, "vol_threshold": 1.0,
        "vol_boost": 1.5, "rsi_oversold": 30, "rsi_overbought": 70,
    }
    base.update(params)
    return StrategyGene(id=gid, logic_code="", params=base, generation=0)


@pytest.fixture
def arena():
    return Arena(envs=("bear",), rounds=2, keep_top=1, interval="1h")


def test_arena_returns_ranking(arena):
    genes = [_mk_gene(f"g{i}", ma_short_window=w) for i, w in enumerate([5, 15, 30, 50])]
    r = arena.run(genes)
    assert r["rounds"] == 2
    assert len(r["ranking"]) == 4
    # 排名有序（得分递减）
    scores = [x["score"] for x in r["ranking"]]
    assert scores == sorted(scores, reverse=True)
    assert r["history"][0]["round"] == 1


def test_arena_champion_consistent(arena):
    genes = [_mk_gene(f"g{i}", ma_short_window=w) for i, w in enumerate([5, 15, 30, 50])]
    r1 = arena.run(genes)
    r2 = Arena(envs=("bear",), rounds=2, keep_top=1, interval="1h", seed=7).run(
        [_mk_gene(f"g{i}", ma_short_window=w) for i, w in enumerate([5, 15, 30, 50])])
    # 固定种子 → 冠军一致（真实回测确定性）
    assert r1["ranking"][0]["gene_id"] == r2["ranking"][0]["gene_id"]


def test_arena_cancel():
    arena = Arena(envs=("bear",), rounds=5, interval="1h")
    genes = [_mk_gene(f"g{i}") for i in range(4)]
    r = arena.run(genes, cancel_event=lambda: True)
    assert r["rounds"] == 0  # 立即取消


def test_arena_rank_scores_positive():
    arena = Arena(envs=("bear",), rounds=1, interval="1h")
    genes = [_mk_gene(f"g{i}", ma_short_window=w) for i, w in enumerate([5, 15, 30, 50])]
    r = arena.run(genes)
    assert all(x["score"] >= 1 for x in r["ranking"])  # rank-based 至少 1 分
