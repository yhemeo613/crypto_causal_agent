"""
L7 三级复盘 + 基因沙箱
"""

from __future__ import annotations

import logging
import ast
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class GeneSandbox:
    """安全沙箱执行策略基因代码"""

    ALLOWED_BUILTINS = {
        "abs", "min", "max", "sum", "len", "range",
        "True", "False", "None", "float", "int", "bool", "str",
        "round", "isinstance",
    }

    @staticmethod
    def execute(code: str, func_name: str = "strategy", **inputs) -> dict:
        """
        安全执行策略函数。

        Args:
            code: Python 策略源码
            func_name: 函数名
            **inputs: 传入参数

        Returns:
            {"action": "long"|"short"|"hold", "confidence": 0.0~1.0}
        """
        tree = ast.parse(code)
        tree = GeneSandbox._clean(tree)

        compiled = compile(tree, "<gene>", "exec")
        namespace = {"__builtins__": {k: __builtins__[k] for k in GeneSandbox.ALLOWED_BUILTINS if k in __builtins__}}
        exec(compiled, namespace)

        func = namespace.get(func_name)
        if func is None:
            return {"action": "hold", "confidence": 0.0}

        try:
            result = func(**inputs)
            if isinstance(result, tuple) and len(result) >= 2:
                return {"action": str(result[0]), "confidence": float(result[1])}
            return {"action": "hold", "confidence": 0.0}
        except Exception as e:
            logger.warning(f"Gene execution error: {e}")
            return {"action": "hold", "confidence": 0.0}

    @staticmethod
    def _clean(tree: ast.Module) -> ast.Module:
        """移除危险节点"""
        for node in ast.walk(tree):
            for child in list(ast.iter_child_nodes(node)):
                tp = type(child).__name__
                if tp in ("Import", "ImportFrom"):
                    if not any(kw in ast.dump(child) for kw in ("numpy", "math", "statistics", "random")):
                        node.body.remove(child)
        return tree


@dataclass
class ReplayReport:
    level: str                   # trade | strategy | generation
    summary: str
    metrics: dict
    improvements: list[str] = None


class ReplayEngines:
    """三级复盘引擎"""

    def trade_replay(self, trades: list[dict]) -> ReplayReport:
        """L1 交易级复盘：单笔交易审视"""
        if not trades:
            return ReplayReport("trade", "无交易", {})
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        return ReplayReport(
            level="trade",
            summary=f"{len(trades)}笔, 胜率{wins/len(trades):.0%}, 总PNL={total_pnl:.1f}",
            metrics={"total_trades": len(trades), "win_rate": wins/max(len(trades),1), "total_pnl": total_pnl},
        )

    def strategy_replay(self, gene: "StrategyGene", trades: list[dict]) -> ReplayReport:
        """L2 策略级复盘：策略审视"""
        from .gene_encoder import StrategyGene
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        return ReplayReport(
            level="strategy",
            summary=f"Gene {gene.id} Gen{gene.generation}: fitness={gene.fitness:.3f}",
            metrics={
                "gene_id": gene.id, "generation": gene.generation,
                "fitness": gene.fitness, "win_rate": wins/max(len(trades), 1),
                "params": gene.params,
                "env_performances": gene.env_performances,
            },
        )

    def generation_replay(self, gen: int, best_fitness: float, avg_fitness: float,
                          pop_size: int) -> ReplayReport:
        """L3 世代级复盘：进化趋势审视"""
        return ReplayReport(
            level="generation",
            summary=f"Gen {gen}: best={best_fitness:.4f} avg={avg_fitness:.4f}",
            metrics={
                "generation": gen, "best_fitness": best_fitness,
                "avg_fitness": avg_fitness, "population_size": pop_size,
            },
        )
