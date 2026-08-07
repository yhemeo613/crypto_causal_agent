"""
L7 双层基因编解码器
逻辑层：Python AST 策略函数   参数层：超参 dict
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyGene:
    """双层策略基因"""
    id: str
    logic_code: str               # Python 策略函数源码
    params: dict                   # {param_name: value}
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    fitness: float = 0.0
    env_performances: dict = field(default_factory=dict)


class GeneEncoder:
    """基因编解码器：策略源码 ↔ AST ↔ 可交叉变异"""

    @staticmethod
    def encode(code: str) -> ast.Module | None:
        """Python 源码 → AST"""
        try:
            tree = ast.parse(code)
            # 验证安全性：只允许白名单节点
            for node in ast.walk(tree):
                tp = type(node).__name__
                if tp in ("Import", "ImportFrom", "Exec", "Eval", "Global"):
                    if not any(kw in ast.dump(node) for kw in ("numpy", "pandas", "math", "statistics")):
                        raise ValueError(f"Forbidden node: {tp}")
            return tree
        except SyntaxError as e:
            return None

    @staticmethod
    def decode(tree: ast.Module) -> str:
        return ast.unparse(tree)

    @staticmethod
    def extract_function(code: str, func_name: str = "strategy") -> str | None:
        """从源码提取 strategy 函数"""
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return ast.unparse(node)
        return None


class GeneCrossover:
    """基因交叉：交换两个策略基因的 AST 子树 + 参数"""

    def crossover(self, gene_a: StrategyGene, gene_b: StrategyGene) -> tuple[StrategyGene, StrategyGene]:
        tree_a = GeneEncoder.encode(gene_a.logic_code)
        tree_b = GeneEncoder.encode(gene_b.logic_code)

        if tree_a and tree_b:
            # 找可交换的 AST 节点
            nodes_a = [n for n in ast.walk(tree_a) if isinstance(n, (ast.If, ast.BinOp, ast.Compare))]
            nodes_b = [n for n in ast.walk(tree_b) if isinstance(n, (ast.If, ast.BinOp, ast.Compare))]

            if nodes_a and nodes_b:
                import random
                swap_a = random.choice(nodes_a)
                swap_b = random.choice(nodes_b)
                # 交换
                if type(swap_a) == type(swap_b):
                    dummy_a = ast.Name(id="__swap__", ctx=ast.Load())
                    dummy_b = ast.Name(id="__swap__", ctx=ast.Load())
                    for node in ast.walk(tree_a):
                        if node is swap_a:
                            if hasattr(node, 'ops'): node.ops = swap_b.ops
                    for node in ast.walk(tree_b):
                        if node is swap_b:
                            if hasattr(node, 'ops'): node.ops = swap_a.ops

        # 参数交叉
        child_params_a = copy.deepcopy(gene_a.params)
        child_params_b = copy.deepcopy(gene_b.params)
        common_keys = set(child_params_a) & set(child_params_b)
        if len(common_keys) > 1:
            import random
            swap_key = random.choice(list(common_keys))
            child_params_a[swap_key], child_params_b[swap_key] = child_params_b[swap_key], child_params_a[swap_key]

        return (
            StrategyGene(
                id=f"{gene_a.id}x{gene_b.id}",
                logic_code=GeneEncoder.decode(tree_a) if tree_a else gene_a.logic_code,
                params=child_params_a,
                generation=max(gene_a.generation, gene_b.generation) + 1,
                parent_ids=[gene_a.id, gene_b.id],
            ),
            StrategyGene(
                id=f"{gene_b.id}x{gene_a.id}",
                logic_code=GeneEncoder.decode(tree_b) if tree_b else gene_b.logic_code,
                params=child_params_b,
                generation=max(gene_a.generation, gene_b.generation) + 1,
                parent_ids=[gene_a.id, gene_b.id],
            ),
        )


class GeneMutator:
    """基因变异：随机修改 AST 节点 + 参数扰动"""

    def mutate(self, gene: StrategyGene, mutation_rate: float = 0.2) -> StrategyGene:
        import random
        new_params = copy.deepcopy(gene.params)
        for k in new_params:
            if random.random() < mutation_rate:
                new_params[k] *= random.uniform(0.8, 1.2)

        tree = GeneEncoder.encode(gene.logic_code)
        if tree and random.random() < mutation_rate:
            comparators = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
            if comparators:
                target = random.choice(comparators)
                if target.ops:
                    old_op = target.ops[0]
                    op_map = {ast.Lt: ast.Gt, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.GtE: ast.LtE}
                    if type(old_op) in op_map:
                        target.ops = [op_map[type(old_op)]()]

        return StrategyGene(
            id=f"{gene.id}_m{generation}",
            logic_code=GeneEncoder.decode(tree) if tree else gene.logic_code,
            params=new_params,
            generation=gene.generation + 1,
            parent_ids=[gene.id],
        )

generation = 1  # for id generation
