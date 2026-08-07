"""P1-09 消融实验框架

配置化开关各创新模块，一键对比实验结果。
每个开关都作用于真实运行链路（非模拟）：
  - memory_fusion: 关 → 空记忆（不召回）
  - causal_graph:  关 → 不写 Neo4j 因果图谱
  - dynamic_position: 关 → 仓位固定 20%（不随置信度调整）
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 全部创新模块开关（P1-09 要求 10 个创新点可独立开关；当前实现的真实可开关维度）
INNOVATION_SWITCHES = [
    "memory_fusion",      # 多路记忆召回
    "causal_graph",       # 因果图谱（抽取+写 Neo4j）
    "dynamic_position",   # 置信度动态仓位
    "debate",             # 多空辩论
    "falsification",      # 证伪校验
    "counterfactual",     # 反事实推演
    "regime_adapt",       # Regime 自适应
]


@dataclass
class AblationConfig:
    """消融配置：默认全开，可关任意开关"""
    switches: dict = field(default_factory=lambda: {s: True for s in INNOVATION_SWITCHES})

    @classmethod
    def baseline(cls) -> "AblationConfig":
        return cls()

    @classmethod
    def ablate(cls, switch: str) -> "AblationConfig":
        cfg = cls()
        if switch not in cfg.switches:
            raise ValueError(f"未知开关: {switch}（可选 {INNOVATION_SWITCHES}）")
        cfg.switches[switch] = False
        return cfg

    def to_dict(self) -> dict:
        return dict(self.switches)


def run_cycle_with_config(cfg: AblationConfig, symbol: str = "BTCUSDT",
                          cycle_id: Optional[int] = None) -> dict:
    """按配置运行一次真实决策周期（与工作台同链路）"""
    from l6_agent.graph_builder import DecisionPipeline

    sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
    import server  # noqa: F401  (复用 workbench 的 build_real_perception/memory)

    if cycle_id is None:
        cycle_id = int(__import__("time").time() * 1000) % 100000

    # 感知（含异常检测，独立于开关）
    perception = server.build_real_perception(symbol)

    # 记忆（memory_fusion 开关）
    memory = server.build_real_memory(symbol) if cfg.switches["memory_fusion"] else {
        "vector": [], "graph": [], "structured": [], "merged": []}

    # 因果图谱（causal_graph 开关）
    causal_triplets = []
    if cfg.switches["causal_graph"]:
        try:
            from l3_perception.causal_extractor import HybridCausalExtractor
            from l5_memory.causal_graph_query import CausalGraphQuery
            extractor = HybridCausalExtractor()
            df_5m = server.load_klines(symbol, "5m", 1500)
            triplets = extractor.extract_all(perception, kline_df=df_5m if not df_5m.empty else None)
            cg = CausalGraphQuery()
            cg.ensure_schema()
            for t in triplets:
                try:
                    cg.write_causal_triplet(t.cause_entity, "Factor", t.effect_entity,
                                            "Event", t.relation, t.confidence,
                                            evidence=f"{t.source}:{t.evidence}"[:400])
                except Exception:
                    pass
            causal_triplets = [t.cause_entity for t in triplets]
        except Exception as e:
            logger.warning(f"causal extraction skipped: {e}")

    # 动态仓位开关：覆盖决策的仓位约束（用真实账户初始值，非假账户）
    from l1_env_base.account import Account as _SimAccount
    _acct = _SimAccount()
    account = {"balance": _acct.initial_balance, "drawdown_pct": 0.0,
               "daily_trade_count": _acct.daily_trade_count}
    # P1-09：4 个 LLM 节点开关真实生效（跳过节点 → 真实决策差异）
    skip = set()
    if not cfg.switches["debate"]:
        skip.add("parallel_debate")
    if not cfg.switches["falsification"]:
        skip.add("falsify")
    if not cfg.switches["counterfactual"]:
        skip.add("counterfactual_analysis")
    # regime_adapt 关闭：regime 从感知中抹去（LLM 看不到市场状态）
    if not cfg.switches["regime_adapt"]:
        perception = dict(perception)
        perception["regime"] = "unknown"

    pipeline = DecisionPipeline(skip_nodes=skip) if skip else DecisionPipeline()
    result = pipeline.run(perception, memory, account, cycle_id=cycle_id)
    dec = result.get("decision")
    dec_dict = dec.model_dump() if hasattr(dec, "model_dump") else dict(dec or {})
    if not cfg.switches["dynamic_position"]:
        dec_dict["position_size_pct"] = 0.2  # 固定 20%
        dec_dict["leverage"] = 2.0

    return {
        "cycle_id": cycle_id,
        "action": dec_dict.get("action"),
        "confidence": float(dec_dict.get("confidence", 0) or 0),
        "position_size_pct": float(dec_dict.get("position_size_pct", 0) or 0),
        "leverage": float(dec_dict.get("leverage", 1) or 1),
        "causal_triplets": len(causal_triplets),
        "memory_recalled": len(memory.get("merged", [])),
    }


def run_ablation(symbol: str = "BTCUSDT", switches: Optional[list[str]] = None,
                 trials: int = 1, out_csv: str = "") -> pd.DataFrame:
    """跑 baseline + 各开关消融对比，返回结果表（CSV 可导出）"""
    switches = switches or INNOVATION_SWITCHES
    rows = []
    base = run_cycle_with_config(AblationConfig.baseline(), symbol=symbol)
    for _ in range(trials - 1):
        b = run_cycle_with_config(AblationConfig.baseline(), symbol=symbol)
        for k in base:
            if isinstance(base[k], (int, float)):
                base[k] = (base[k] + b[k]) / 2
    rows.append({"ablation": "baseline", **base})

    for sw in switches:
        cfg = AblationConfig.ablate(sw)
        r = run_cycle_with_config(cfg, symbol=symbol)
        rows.append({"ablation": f"-{sw}", **r})

    df = pd.DataFrame(rows)
    if out_csv:
        Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
        logger.info(f"[ablation] 结果已导出 → {out_csv}")
    return df
