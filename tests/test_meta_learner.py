"""P1-10 元学习（MAML 先验版）测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l7_evolution.meta_learner import MetaLearner, PARAM_ORDER, _env_features


def test_param_normalization_roundtrip():
    params = {"ma_short_window": 20, "ma_long_window": 60, "vol_threshold": 1.0,
              "vol_boost": 2.0, "rsi_oversold": 30, "rsi_overbought": 70}
    vec = MetaLearner._normalize_params(params)
    assert len(vec) == 6 and all(0 <= v <= 1 for v in vec)
    back = MetaLearner._denormalize_params(vec)
    assert back["ma_short_window"] == 20
    assert abs(back["vol_threshold"] - 1.0) < 0.01


def test_train_needs_min_samples():
    m = MetaLearner()
    r = m.train([])
    assert r["trained"] is False


def test_train_and_predict():
    m = MetaLearner(epochs=100)
    # 两个不同环境的样本
    samples = [
        {"feat": {"trend_strength": 5.0, "volatility": 0.5, "avg_volume_ratio": 1.2, "max_drawdown": 0.1},
         "params": {"ma_short_window": 10, "ma_long_window": 30, "vol_threshold": 0.8,
                    "vol_boost": 1.5, "rsi_oversold": 25, "rsi_overbought": 75},
         "fitness": 0.5},
        {"feat": {"trend_strength": -3.0, "volatility": 0.9, "avg_volume_ratio": 0.8, "max_drawdown": 0.3},
         "params": {"ma_short_window": 30, "ma_long_window": 90, "vol_threshold": 1.2,
                    "vol_boost": 2.0, "rsi_oversold": 30, "rsi_overbought": 70},
         "fitness": 0.3},
    ]
    r = m.train(samples)
    assert r["trained"] is True
    feat = {"trend_strength": 4.0, "volatility": 0.6, "avg_volume_ratio": 1.1, "max_drawdown": 0.15}
    pred = m.predict_init(feat)
    assert len(pred) == len(PARAM_ORDER)
    assert 5 <= pred["ma_short_window"] <= 50
    assert 20 <= pred["ma_long_window"] <= 200


def test_env_features_from_db():
    f = _env_features("BTCUSDT", "1h")
    assert set(f) == {"trend_strength", "volatility", "avg_volume_ratio", "max_drawdown"}
    assert isinstance(f["volatility"], float)
