"""
P1-01 对抗竞技场

多个策略基因在相同环境中对抗竞争，胜者基因进入下一代。
排名基于多环境加权适应度；支持多轮对抗（轮间精英保留 + 交叉/变异补充）。

竞技场积分规则：
  - 每基因在全部环境真实回测（backtest_gene）
  - 单环境排名得分（rank-based：第一名 n 分，递减）
  - 总分 = Σ 环境排名得分 × 环境权重（默认等权）
"""

from __future__ import annotations

import copy
import logging
import random
import sys
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_ENVS = ("bull", "bear", "range", "extreme")


class Arena:
    """多基因同环境对抗竞技场"""

    def __init__(
        self,
        envs: tuple[str, ...] = DEFAULT_ENVS,
        rounds: int = 3,
        env_weights: Optional[dict[str, float]] = None,
        keep_top: int = 2,          # 每轮精英保留数
        interval: str = "1h",
        seed: int = 42,
    ):
        self.envs = envs
        self.rounds = rounds
        self.env_weights = env_weights or {e: 1.0 for e in envs}
        self.keep_top = keep_top
        self.interval = interval
        self.random = random.Random(seed)
        self.round_history: list[dict] = []

    # ─── 评估：多环境回测 → 排名得分 ────────────────────

    def _evaluate(self, genes: list) -> dict[str, float]:
        """返回 {gene.id: 总分}（rank-based 加权）"""
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "dashboard"))
        import server  # noqa: F401

        scores = {g.id: 0.0 for g in genes}
        for env in self.envs:
            perfs = {}
            for g in genes:
                try:
                    perfs[g.id] = server.backtest_gene(g, envs=(env,), interval=self.interval)[env]
                except Exception as e:
                    logger.warning(f"[arena] {g.id} @ {env} 评估失败: {e}")
                    perfs[g.id] = -1.0
            # rank-based：绩效高者得高分（n, n-1, ...）
            ranked = sorted(perfs.items(), key=lambda kv: kv[1], reverse=True)
            n = len(ranked)
            for rank, (gid, _) in enumerate(ranked):
                scores[gid] += (n - rank) * self.env_weights.get(env, 1.0)
        return scores

    # ─── 新一代（精英保留 + 交叉/变异） ──────────────────

    def _next_generation(self, genes: list, ranked_ids: list[str], size: int) -> list:
        from l7_evolution.gene_encoder import GeneCrossover, GeneMutator

        by_id = {g.id: g for g in genes}
        elites = [copy.deepcopy(by_id[i]) for i in ranked_ids[: self.keep_top]]
        cross = GeneCrossover()
        mut = GeneMutator()
        new_pop = list(elites)
        pool = list(genes)
        while len(new_pop) < size:
            a, b = self.random.sample(pool, 2)
            if self.random.random() < 0.7:
                ca, cb = cross.crossover(a, b)
                child = ca if self.random.random() < 0.5 else cb
            else:
                child = mut.mutate(a, 0.2)
            child.id = f"arena_{len(new_pop)}_{self.random.randint(1000, 9999)}"
            new_pop.append(child)
        return new_pop[:size]

    # ─── 运行对抗 ────────────────────────────────────────

    def run(
        self,
        genes: list,
        progress_cb: Optional[Callable[[int, int, dict], None]] = None,
        cancel_event=None,
    ) -> dict:
        """运行多轮对抗，返回排名与每轮历史"""
        current = list(genes)
        final_ranking = []
        for r in range(self.rounds):
            if cancel_event is not None and (cancel_event() if callable(cancel_event) else cancel_event.is_set()):
                logger.info("[arena] 任务已取消")
                break
            scores = self._evaluate(current)
            ranked_ids = [gid for gid, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]
            ranked = [(gid, scores[gid]) for gid in ranked_ids]
            self.round_history.append({"round": r + 1, "ranking": ranked})
            final_ranking = ranked
            logger.info(f"[arena] 第 {r + 1} 轮: 冠军 {ranked_ids[0]} (总分 {scores[ranked_ids[0]]:.0f})")
            if r < self.rounds - 1 and len(current) > self.keep_top:
                current = self._next_generation(current, ranked_ids, len(current))
            if progress_cb:
                progress_cb(r + 1, self.rounds, {"champion": ranked_ids[0], "scores": scores})

        return {
            "rounds": len(self.round_history),
            "ranking": [{"gene_id": gid, "score": sc} for gid, sc in final_ranking],
            "history": self.round_history,
        }
