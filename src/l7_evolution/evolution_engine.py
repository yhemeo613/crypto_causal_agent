"""
L7 遗传进化引擎
DEAP 框架：锦标赛选择 + AST交叉 + 参数变异 + 适应度评估
"""

from __future__ import annotations

import logging
import random
import copy
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .gene_encoder import (
    StrategyGene, GeneCrossover, GeneMutator, GeneEncoder,
)

logger = logging.getLogger(__name__)

# 默认策略模板 — 量化趋势跟踪
DEFAULT_STRATEGY_CODE = """
def strategy(price, ma_short, ma_long, volatility, volume_ratio, regime):
    if price > ma_short and volume_ratio > 1.0 and regime == 'trend_up':
        return 'long', 0.7
    elif price < ma_short and volume_ratio < 0.9 and regime == 'trend_down':
        return 'short', 0.6
    else:
        return 'hold', 0.3
"""


class FitnessEvaluator:
    """四环境适应度评估器"""

    def __init__(self, generalization_weight: float = 0.3):
        self.w = generalization_weight

    def evaluate(self, gene: StrategyGene, env_performances: dict[str, float]) -> float:
        """
        综合适应度 = 平均夏普 × (1 − w × 泛化惩罚)
        泛化惩罚 = 四环境夏普的标准差 / 均值
        """
        values = list(env_performances.values())
        if not values:
            return 0.0

        mean_val = np.mean(values)
        std_val = np.std(values)
        penalty = std_val / (abs(mean_val) + 1e-9)
        fitness = mean_val * (1.0 - self.w * min(penalty, 1.0))
        # 保留原始值（负收益真实展示）；engine 排序自然把负值排后，选择安全
        return fitness


class EvolutionEngine:
    """
    遗传进化引擎。

    流程：
    1. 初始化种群（随机参数 + 默认策略模板）
    2. 评估适应度（四环境沙箱回测）
    3. 锦标赛选择
    4. 交叉 + 变异
    5. 精英保留
    6. 重复 N 代
    """

    def __init__(
        self,
        population_size: Optional[int] = None,
        generations: Optional[int] = None,
        crossover_rate: Optional[float] = None,
        mutation_rate: Optional[float] = None,
        tournament_size: Optional[int] = None,
        elitism_count: Optional[int] = None,
        generalization_weight: Optional[float] = None,
    ):
        # 未显式传参时读 config evolution 段（消除双份维护）
        from config_utils import get_section
        ev = get_section("evolution")
        self.pop_size = population_size if population_size is not None else int(ev.get("population_size", 12))
        self.generations = generations if generations is not None else int(ev.get("generations", 30))
        self.crossover_rate = crossover_rate if crossover_rate is not None else float(ev.get("crossover_rate", 0.7))
        self.mutation_rate = mutation_rate if mutation_rate is not None else float(ev.get("mutation_rate", 0.2))
        self.tournament_size = tournament_size if tournament_size is not None else int(ev.get("tournament_size", 3))
        self.elitism_count = elitism_count if elitism_count is not None else int(ev.get("elitism_count", 2))
        self.generalization_weight = generalization_weight if generalization_weight is not None else float(ev.get("generalization_penalty_weight", 0.3))

        self.crossover = GeneCrossover()
        self.mutator = GeneMutator()
        self.evaluator = FitnessEvaluator(self.generalization_weight)

        self.population: list[StrategyGene] = []
        self.best_gene: Optional[StrategyGene] = None
        self.history: list[dict] = []

    def init_population(self, logic_code: str = DEFAULT_STRATEGY_CODE) -> list[StrategyGene]:
        """生成初始种群，参数从 PARAM_SPACE 随机采样（单一来源）"""
        from l7_evolution.gene_encoder import random_params
        self.population = []
        for i in range(self.pop_size):
            params = random_params()
            self.population.append(StrategyGene(
                id=f"gen0_{i}", logic_code=logic_code,
                params=params, generation=0,
            ))
        return self.population

    def evaluate_population(
        self,
        env_perf_func,  # callable: (gene) -> dict[str, float]
    ):
        """评估种群所有个体"""
        for gene in self.population:
            perf = env_perf_func(gene)
            gene.env_performances = perf
            gene.fitness = self.evaluator.evaluate(gene, perf)

        self.population.sort(key=lambda g: g.fitness, reverse=True)
        best = self.population[0]
        if not self.best_gene or best.fitness > self.best_gene.fitness:
            self.best_gene = copy.deepcopy(best)

    def evolve_generation(self) -> list[StrategyGene]:
        """进化一代"""
        new_pop = []

        # 精英保留
        sorted_pop = sorted(self.population, key=lambda g: g.fitness, reverse=True)
        elites = [copy.deepcopy(g) for g in sorted_pop[:self.elitism_count]]
        new_pop.extend(elites)

        # 锦标赛选择 + 交叉 + 变异
        while len(new_pop) < self.pop_size:
            parent_a = self._tournament_select()
            parent_b = self._tournament_select()

            if random.random() < self.crossover_rate:
                child_a, child_b = self.crossover.crossover(parent_a, parent_b)
                new_pop.append(child_a)
                if len(new_pop) < self.pop_size:
                    new_pop.append(child_b)
            else:
                new_pop.append(self.mutator.mutate(parent_a, self.mutation_rate))

        # 变异
        for i in range(self.elitism_count, len(new_pop)):
            if random.random() < self.mutation_rate:
                new_pop[i] = self.mutator.mutate(new_pop[i], self.mutation_rate)

        self.population = new_pop[:self.pop_size]
        return self.population

    def run(
        self, env_perf_func, verbose: bool = True
    ) -> StrategyGene:
        """运行完整进化"""
        self.init_population()

        for gen in range(self.generations):
            self.evaluate_population(env_perf_func)
            best = self.population[0]

            self.history.append({
                "generation": gen,
                "best_fitness": best.fitness,
                "avg_fitness": np.mean([g.fitness for g in self.population]),
                "best_params": best.params,
                "env_performances": best.env_performances,
            })

            if verbose and gen % 5 == 0:
                logger.info(
                    f"Gen {gen:3d}: best_fit={best.fitness:.4f} "
                    f"avg_fit={np.mean([g.fitness for g in self.population]):.4f} "
                    f"params={best.params}"
                )

            if gen < self.generations - 1:
                self.evolve_generation()

        return self.best_gene or self.population[0]

    def _tournament_select(self) -> StrategyGene:
        candidates = random.sample(self.population, min(self.tournament_size, len(self.population)))
        return max(candidates, key=lambda g: g.fitness)
