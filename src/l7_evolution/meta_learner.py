"""
P1-10 元学习加速（MAML 先验版）

从历史进化经验中学习"环境特征 → 高表现参数"的元知识，
新环境适应时用学到的先验初始化策略基因（而非随机初始化），
加速收敛。模型：torch MLP（环境特征 4 维 → 策略参数 6 维）。

环境特征（从真实数据计算）：
  trend_strength: 趋势强度（收盘价与均线偏离）
  volatility: 年化波动率
  avg_volume_ratio: 平均量比
  max_drawdown: 最大回撤

训练数据：evolution_logs 中真实基因参数 + fitness（按 fitness 加权）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# 项目根 + dashboard 路径（供真实回测复用）
_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "dashboard")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 参数顺序/范围来自 gene_encoder 单一来源（消除第三份拷贝）
from l7_evolution.gene_encoder import PARAM_ORDER, PARAM_SPACE  # noqa: E402


def _env_features(symbol: str = "BTCUSDT", interval: str = "1h") -> dict:
    """从真实 K 线计算环境特征（时序库 5433）"""
    from db_conn import ts_query
    rows = ts_query(
        "SELECT close, volume FROM klines WHERE symbol=%s AND interval=%s "
        "ORDER BY ts DESC LIMIT 200", (symbol, interval))

    closes = np.array([float(r["close"]) for r in rows][::-1])
    vols = np.array([float(r["volume"]) for r in rows][::-1])
    if len(closes) < 20:
        return {"trend_strength": 0.0, "volatility": 0.0,
                "avg_volume_ratio": 1.0, "max_drawdown": 0.0}
    rets = np.diff(closes) / closes[:-1]
    trend = float((closes[-1] / np.mean(closes[-20:]) - 1) * 100)
    vol = float(np.std(rets) * (365 * 24) ** 0.5)
    vol_ratio = float(np.mean(vols[-20:] / (np.mean(vols) + 1e-9)))
    peak = np.maximum.accumulate(closes)
    dd = float(np.max((peak - closes) / peak))
    return {"trend_strength": trend, "volatility": vol,
            "avg_volume_ratio": vol_ratio, "max_drawdown": dd}


@dataclass
class MetaLearner:
    """环境特征 → 策略参数 元学习先验（torch MLP）"""

    hidden: int = 32
    lr: float = 1e-3
    epochs: int = 200
    _model: Optional[object] = None

    # ─── 模型构建 ────────────────────────────────────────

    def _build_model(self):
        import torch
        import torch.nn as nn
        model = nn.Sequential(
            nn.Linear(4, self.hidden), nn.ReLU(),
            nn.Linear(self.hidden, self.hidden), nn.ReLU(),
            nn.Linear(self.hidden, len(PARAM_ORDER)),
        )
        return model

    # ─── 参数归一化（防止不同量纲参数失衡） ────────────────

    @staticmethod
    def _normalize_params(params: dict) -> np.ndarray:
        """按先验范围归一化到 [0,1]（范围来自 PARAM_SPACE 单一来源）"""
        out = []
        for k in PARAM_ORDER:
            spec = PARAM_SPACE[k]
            lo, hi = spec["min"], spec["max"]
            v = float(params.get(k, spec["default"]))
            out.append(max(0.0, min(1.0, (v - lo) / max(hi - lo, 1e-9))))
        return np.array(out, dtype=np.float32)

    @staticmethod
    def _denormalize_params(vec) -> dict:
        out = {}
        for i, k in enumerate(PARAM_ORDER):
            spec = PARAM_SPACE[k]
            lo, hi = spec["min"], spec["max"]
            v = float(np.clip(vec[i], 0, 1)) * (hi - lo) + lo
            out[k] = int(round(v)) if spec["kind"] == "int" else round(v, 3)
        return out

    # ─── 训练（真实 evolution_logs 样本） ─────────────────

    def train(self, samples: list[dict]) -> dict:
        """
        samples: [{"feat": {...}, "params": {...}, "fitness": float}, ...]
        用 fitness 加权回归训练。
        """
        import torch

        if len(samples) < 2:
            return {"trained": False, "error": f"训练样本不足 ({len(samples)} < 2)"}

        feats = np.array([[s["feat"]["trend_strength"], s["feat"]["volatility"],
                           s["feat"]["avg_volume_ratio"], s["feat"]["max_drawdown"]]
                          for s in samples], dtype=np.float32)
        targets = np.array([self._normalize_params(s["params"]) for s in samples], dtype=np.float32)
        weights = np.array([max(float(s.get("fitness", 0) or 0), 0) + 0.1 for s in samples],
                           dtype=np.float32)
        # 归一化权重
        weights = weights / weights.sum()

        feats_t = torch.from_numpy(feats)
        tgt_t = torch.from_numpy(targets)
        w_t = torch.from_numpy(weights).unsqueeze(1)

        self._model = self._build_model()
        opt = torch.optim.Adam(self._model.parameters(), lr=self.lr)
        loss_fn = torch.nn.MSELoss(reduction="none")

        for _ in range(self.epochs):
            opt.zero_grad()
            pred = self._model(feats_t)
            loss = (loss_fn(pred, tgt_t) * w_t).mean()
            loss.backward()
            opt.step()

        with torch.no_grad():
            train_loss = float(loss_fn(self._model(feats_t), tgt_t).mean())
        logger.info(f"[meta] 训练完成: samples={len(samples)} loss={train_loss:.4f}")
        return {"trained": True, "samples": len(samples), "train_loss": train_loss}

    # ─── 预测初始化 ──────────────────────────────────────

    def predict_init(self, feat: dict) -> dict:
        import torch
        if self._model is None:
            raise RuntimeError("模型未训练")
        vec = torch.from_numpy(np.array(
            [feat["trend_strength"], feat["volatility"],
             feat["avg_volume_ratio"], feat["max_drawdown"]], dtype=np.float32))
        with torch.no_grad():
            out = self._model(vec).numpy()
        return self._denormalize_params(out)

    # ─── 对比验证（元初始化 vs 随机初始化） ───────────────

    def compare(self, symbol: str = "BTCUSDT", interval: str = "1h",
                n_random: int = 3) -> dict:
        """新环境：预测初始化 vs 随机初始化 的真实回测绩效对比"""
        import server  # noqa: F401  (路径已由模块顶部注入)
        from l7_evolution.evolution_engine import StrategyGene

        if self._model is None:
            return {"error": "模型未训练"}

        feat = _env_features(symbol, interval)
        meta_params = self.predict_init(feat)
        gene = StrategyGene(id="meta_init", logic_code="", params=meta_params, generation=0)
        try:
            meta_score = float(sum(server.backtest_gene(gene, envs=("bull", "bear", "range", "extreme")).values()) / 4)
        except Exception:
            meta_score = -1.0

        # 随机初始化基准（平均）
        import random
        rng = random.Random(42)
        rand_scores = []
        for i in range(n_random):
            p = {"ma_short_window": rng.randint(5, 50), "ma_long_window": rng.randint(20, 200),
                 "vol_threshold": rng.uniform(0.3, 1.5), "vol_boost": rng.uniform(1.0, 3.0),
                 "rsi_oversold": rng.randint(20, 35), "rsi_overbought": rng.randint(65, 80)}
            g = StrategyGene(id=f"rand_{i}", logic_code="", params=p, generation=0)
            try:
                rand_scores.append(float(sum(server.backtest_gene(g, envs=("bull", "bear", "range", "extreme")).values()) / 4))
            except Exception:
                rand_scores.append(-1.0)
        rand_score = float(np.mean(rand_scores)) if rand_scores else -1.0

        improvement = (meta_score - rand_score) / (abs(rand_score) + 1e-9) * 100 if rand_score != 0 else 0.0
        return {"meta_init_params": meta_params, "meta_score": round(meta_score, 4),
                "random_score": round(rand_score, 4), "improvement_pct": round(improvement, 1)}

    # ─── 数据加载（真实 evolution_logs） ─────────────────

    @staticmethod
    def load_training_samples(limit: int = 50) -> list[dict]:
        """从 evolution_logs 加载 (feat, params, fitness) 训练样本（统一连接）"""
        from db_conn import pg_query
        rows = pg_query(
            "SELECT gene_params, fitness FROM evolution_logs "
            "WHERE gene_params IS NOT NULL AND fitness IS NOT NULL "
            "ORDER BY id DESC LIMIT %s", (limit,))

        samples = []
        feat = _env_features()
        for r in rows:
            try:
                params = json.loads(r["gene_params"]) if isinstance(r["gene_params"], str) else (r["gene_params"] or {})
            except Exception:
                continue
            if not params:
                continue
            samples.append({"feat": feat, "params": params,
                            "fitness": float(r["fitness"] or 0)})
        return samples
