"""P1-11 知识蒸馏测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l7_evolution.knowledge_distiller import KnowledgeDistiller, _fidelity
from l7_evolution.evolution_engine import StrategyGene

SAMPLE = '''
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price > ma_short and volume_ratio > 1.0:
        return 'long', 0.7
    else:
        return 'hold', 0.3
'''

SAMPLE_BACK = '''
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price > ma_short:
        return 'long', 0.7
    else:
        return 'hold', 0.3
'''


def test_fidelity_high_when_similar():
    f = _fidelity(SAMPLE, SAMPLE_BACK)
    assert f > 0.8


def test_fidelity_low_when_different():
    other = '''
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    return 'hold', 0.1
'''
    f = _fidelity(SAMPLE, other)
    assert f < 0.7


def test_extract_json():
    raw = '```json\n{"rules": [{"condition": "a", "action": "long"}], "backtranslated_code": "x"}\n```'
    d = KnowledgeDistiller._extract_json(raw)
    assert d["rules"][0]["action"] == "long"


def test_distill_with_mock_llm(monkeypatch):
    import json
    dist = KnowledgeDistiller(api_key="sk-test")
    payload = json.dumps({
        "rules": [{"condition": "价格上穿均线", "action": "long", "reason": "趋势"}],
        "backtranslated_code": SAMPLE_BACK,
    })
    monkeypatch.setattr(dist, "_call_llm", lambda user: payload)
    gene = StrategyGene(id="best_1", logic_code=SAMPLE,
                        params={"ma_short_window": 10}, generation=0)
    r = dist.distill(gene)
    assert r["rules"][0]["action"] == "long"
    assert r["fidelity"] > 0.8


def test_distill_retry_on_empty(monkeypatch):
    dist = KnowledgeDistiller(api_key="sk-test")
    monkeypatch.setattr(dist, "_call_llm", lambda user: "{}")
    gene = StrategyGene(id="g1", logic_code=SAMPLE, params={}, generation=0)
    r = dist.distill(gene)
    assert r["rules"] == [] and r["error"]
