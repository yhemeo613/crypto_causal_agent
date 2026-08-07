"""
P2-04 进化收敛性分析

从进化历史计算收敛性指标，输出统计报告：
  - 收敛代数：best fitness 最后一次显著改善的代
  - 适应度方差：末 10% 代种群适应度方差（收敛 → 方差收窄）
  - 基因多样性：唯一基因参数比例
  - 收敛速度：前 25% 代 vs 后 25% 代的改善幅度比
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ConvergenceAnalyzer:
    """进化收敛性分析器"""

    @staticmethod
    def analyze(history: list[dict]) -> dict:
        """
        history: [{"generation": int, "best_fitness": float, "avg_fitness": float, ...}]
        """
        if not history or len(history) < 2:
            return {"error": "进化历史不足（需 ≥2 代）"}

        bests = np.array([float(h.get("best_fitness", 0) or 0) for h in history])
        avgs = np.array([float(h.get("avg_fitness", 0) or 0) for h in history])
        n = len(bests)

        # 收敛代数：best fitness 最后一次显著改善（>1e-6 提升）
        converged_at = 0
        for i in range(1, n):
            if bests[i] > bests[i - 1] + 1e-6:
                converged_at = i
        converged = converged_at >= n - 1  # 末代仍在改善 → 未收敛

        # 适应度方差（末 10% 代）
        tail = bests[int(n * 0.9):] if n >= 5 else bests
        fitness_variance = float(np.var(tail)) if len(tail) > 1 else 0.0

        # 基因多样性：唯一基因参数（JSON 键序归一化）
        param_keys = set()
        for h in history:
            p = h.get("params") or h.get("best_params")
            if p:
                param_keys.add(json.dumps(p, sort_keys=True))
        diversity = len(param_keys) / max(n, 1)

        # 收敛速度：前 25% vs 后 25% 平均改善
        q = max(int(n * 0.25), 1)
        early_improve = float(bests[q] - bests[0]) if n > q else 0.0
        late_improve = float(bests[-1] - bests[-1 - q]) if n > q + 1 else 0.0
        speed = early_improve / (abs(late_improve) + 1e-9) if abs(late_improve) > 1e-9 else (
            float("inf") if early_improve > 0 else 0.0)

        report = {
            "generations": n,
            "best_fitness": float(bests[-1]),
            "avg_fitness": float(avgs[-1]),
            "converged": bool(converged),
            "converged_at_generation": converged_at if converged_at > 0 else None,
            "fitness_variance_tail": round(fitness_variance, 6),
            "gene_diversity_ratio": round(diversity, 4),
            "convergence_speed_ratio": round(speed, 3) if speed != float("inf") else None,
            "early_improvement": round(early_improve, 4),
            "late_improvement": round(late_improve, 4),
        }
        logger.info(f"[convergence] 收敛={converged} 收敛代={converged_at} "
                    f"多样性={diversity:.2f} 方差={fitness_variance:.6f}")
        return report

    @staticmethod
    def analyze_from_db(limit: int = 200) -> dict:
        """从 evolution_logs 读取进化历史分析"""
        from db_conn import pg_query
        rows = pg_query(
            "SELECT generation, gene_id, gene_params, fitness FROM evolution_logs "
            "WHERE generation >= 0 AND fitness IS NOT NULL ORDER BY generation, id")
        history = []
        for r in rows:
            try:
                params = json.loads(r["gene_params"]) if isinstance(r["gene_params"], str) else (r["gene_params"] or {})
            except Exception:
                params = {}
            history.append({"generation": int(r["generation"]),
                            "best_fitness": float(r["fitness"] or 0),
                            "avg_fitness": float(r["fitness"] or 0),
                            "params": params})
        if not history:
            return {"error": "无进化记录（先运行进化实验）"}
        return ConvergenceAnalyzer.analyze(history)
