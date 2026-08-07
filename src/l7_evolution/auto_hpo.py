"""
P1-12 Auto-HPO 超参优化

使用 Optuna 贝叶斯优化对策略参数层基因做超参搜索。
评估目标：真实四环境回测平均绩效（复用 backtest_gene）。
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import optuna

logger = logging.getLogger(__name__)

# 静音 Optuna 信息日志
optuna.logging.set_verbosity(optuna.logging.WARNING)

# 参数空间来自 gene_encoder 单一来源（消除三份拷贝）
from l7_evolution.gene_encoder import PARAM_SPACE as SEARCH_SPACE  # noqa: E402


class AutoHPO:
    """Optuna 参数层基因贝叶斯搜索"""

    def __init__(
        self,
        n_trials: int = 30,
        envs: tuple[str, ...] = ("bull", "bear", "range", "extreme"),
        interval: str = "1h",
        timeout_seconds: int = 0,
    ):
        self.n_trials = n_trials
        self.envs = envs
        self.interval = interval
        self.timeout_seconds = timeout_seconds
        self.study: Optional[optuna.Study] = None
        self.history: list[dict] = []

    # ─── 参数采样 ────────────────────────────────────────

    def _sample_params(self, trial: optuna.Trial) -> dict:
        params = {}
        for name, spec in SEARCH_SPACE.items():
            if spec["kind"] == "int":
                params[name] = trial.suggest_int(name, spec["min"], spec["max"])
            else:
                params[name] = trial.suggest_float(name, spec["min"], spec["max"])
        return params

    # ─── 评估目标（真实回测） ────────────────────────────

    def _objective(self, trial: optuna.Trial) -> float:
        from l7_evolution.evolution_engine import StrategyGene

        params = self._sample_params(trial)
        gene = StrategyGene(id=f"hpo_{trial.number}", logic_code="",
                            params=params, generation=0)

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dashboard"))
        import server  # noqa: F401  (复用 backtest_gene)

        try:
            perf = server.backtest_gene(gene, envs=self.envs, interval=self.interval)
            score = float(sum(perf.values()) / max(len(perf), 1))
        except Exception as e:
            logger.warning(f"[hpo] trial {trial.number} 评估失败: {e}")
            score = -1.0

        self.history.append({
            "trial": trial.number, "params": params, "perf": perf, "score": score,
        })
        return score

    # ─── 运行搜索 ────────────────────────────────────────

    @staticmethod
    def _cancelled(cancel_event) -> bool:
        if cancel_event is None:
            return False
        return cancel_event() if callable(cancel_event) else cancel_event.is_set()

    def run(
        self,
        progress_cb: Optional[Callable[[int, int, float], None]] = None,
        cancel_event=None,
    ) -> dict:
        """运行贝叶斯搜索，返回 best_params / best_value / history"""
        self.study = optuna.create_study(direction="maximize",
                                         sampler=optuna.samplers.TPESampler(seed=42))
        start = time.time()
        for i in range(self.n_trials):
            if self._cancelled(cancel_event):
                logger.info(f"[hpo] 任务已取消（第 {i} trial）")
                break
            if self.timeout_seconds and (time.time() - start) > self.timeout_seconds:
                break
            self.study.optimize(self._objective, n_trials=1)
            if progress_cb:
                progress_cb(i + 1, self.n_trials,
                            self.study.best_value if self.study.best_trial else 0.0)

        best = self.study.best_trial
        logger.info(f"[hpo] 完成: best_score={best.value:.4f} params={best.params}")
        return {
            "best_params": best.params,
            "best_score": best.value,
            "best_perf": self.history[best.number]["perf"] if best.number < len(self.history) else {},
            "trials": len(self.history),
            "history": self.history[-200:],
        }
