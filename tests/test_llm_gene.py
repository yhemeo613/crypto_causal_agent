"""P1-02 LLM 创新基因生成测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l7_evolution.llm_gene_generator import LLMGeneGenerator

SAMPLE_CODE = '''
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price < ma_long * 0.95 and volatility > 2.5:
        return 'long', 0.8
    elif price > ma_long * 1.15 and volume_ratio < 0.5:
        return 'short', 0.75
    else:
        return 'hold', 0.4
'''


def test_validate_code_ok():
    ok, msg = LLMGeneGenerator.validate_code(SAMPLE_CODE)
    assert ok and msg == "ok"


def test_validate_code_bad_syntax():
    ok, _ = LLMGeneGenerator.validate_code("def strategy(:")
    assert not ok


def test_validate_missing_function():
    ok, msg = LLMGeneGenerator.validate_code("x = 1")
    assert not ok and "def strategy" in msg


def test_novelty_same_is_zero():
    assert LLMGeneGenerator.novelty_score(SAMPLE_CODE, [SAMPLE_CODE]) < 0.05


def test_novelty_different_is_high():
    other = '''
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price > ma_short and ma_short > ma_long:
        return 'long', 0.6
    else:
        return 'hold', 0.5
'''
    n = LLMGeneGenerator.novelty_score(other, [SAMPLE_CODE])
    assert 0.0 < n < 1.0


def test_extract_json_plain():
    raw = '{"code": "def strategy(x):\\n    return 1", "params": {"a": 1}}'
    d = LLMGeneGenerator._extract_json(raw)
    assert d["params"]["a"] == 1


def test_generate_with_mock_llm(monkeypatch):
    gen = LLMGeneGenerator(api_key="sk-test")
    import json
    payload = json.dumps({"code": SAMPLE_CODE,
                          "params": {"ma_short_window": 10, "ma_long_window": 60}})
    monkeypatch.setattr(gen, "_call_llm", lambda user: payload)
    # existing 用不同代码（novelty 高，通过 P1-02 创新性硬过滤）
    r = gen.generate(context={"gene_summary": ["old gene A"]},
                     existing_codes=["def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):\n    return 'hold', 0.1"])
    assert r["validated"] is True
    assert r["gene"] is not None
    assert r["gene"].params["ma_long_window"] == 60


def test_generate_rejects_similar(monkeypatch):
    """P1-02 创新性硬过滤：与现有基因过于相似 → 拒绝"""
    gen = LLMGeneGenerator(api_key="sk-test")
    import json
    payload = json.dumps({"code": SAMPLE_CODE, "params": {}})
    monkeypatch.setattr(gen, "_call_llm", lambda user: payload)
    r = gen.generate(context={}, existing_codes=[SAMPLE_CODE])  # 完全相同
    assert r["validated"] is False
    assert "创新性不足" in r["error"]
