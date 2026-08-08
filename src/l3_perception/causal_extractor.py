"""
L3 因果三元组抽取
P0: LLM 因果（DeepSeek）+ 统计因果（Granger + 相关性）
"""

from __future__ import annotations

import logging
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CausalTriplet:
    """因果三元组：原因 -> 关系 -> 结果"""
    cause_entity: str
    relation: str
    effect_entity: str
    confidence: float = 0.0
    lag_periods: int = 0
    source: str = "llm"
    evidence: str = ""
    timestamp: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════
# 统计因果发现（Granger 因果 + 相关性）
# ═══════════════════════════════════════════════════════════════

class StatisticalCausalDiscovery:
    """基于 Granger 因果检验 + Pearson 相关性的因果发现"""

    def __init__(self, significance_level: float = 0.05):
        self.alpha = significance_level

    def discover(
        self,
        target_series: pd.Series,
        candidate_factors: dict[str, pd.Series],
        max_lag: int = 5,
    ) -> list[CausalTriplet]:
        from statsmodels.tsa.stattools import grangercausalitytests

        results = []
        target_aligned = target_series.dropna()

        for factor_name, factor_series in candidate_factors.items():
            factor_aligned = factor_series.dropna()
            common_idx = target_aligned.index.intersection(factor_aligned.index)
            if len(common_idx) < max_lag + 10:
                continue

            y = target_aligned.loc[common_idx].values
            x = factor_aligned.loc[common_idx].values
            y_diff = np.diff(y)
            x_diff = np.diff(x)
            min_len = min(len(y_diff), len(x_diff))
            data = np.column_stack([y_diff[:min_len], x_diff[:min_len]])
            data = data[~np.isnan(data).any(axis=1)]

            if len(data) < max_lag + 10:
                continue

            try:
                gc_result = grangercausalitytests(
                    data, maxlag=min(max_lag, len(data) // 10)
                )
            except Exception as e:
                logger.debug(f"Granger test failed for {factor_name}: {e}")
                continue

            best_lag, best_pvalue = 0, 1.0
            for lag, lag_result in gc_result.items():
                pvalue = lag_result[0]["ssr_chi2test"][1]
                if pvalue < best_pvalue:
                    best_pvalue, best_lag = pvalue, lag

            confidence = 1.0 - best_pvalue
            corr = np.corrcoef(y_diff[:min_len], x_diff[:min_len])[0, 1]

            if confidence > 1.0 - self.alpha:
                direction = "increases" if corr > 0 else "decreases"
                results.append(CausalTriplet(
                    cause_entity=f"{factor_name}变化",
                    relation=f"causes_{direction}",
                    effect_entity="BTCUSDT价格",
                    confidence=min(confidence, 0.99),
                    lag_periods=best_lag,
                    source="statistical",
                    evidence=f"Granger p={best_pvalue:.4f}, Pearson r={corr:.3f}",
                ))

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def discover_from_df(
        self, df: pd.DataFrame, target_col: str = "close",
        factor_cols: list[str] = None, max_lag: int = 5,
    ) -> list[CausalTriplet]:
        if "ts" in df.columns:
            df = df.set_index("ts")
        target = df[target_col]
        if factor_cols is None:
            factor_cols = [c for c in df.columns if c != target_col]
        candidates = {col: df[col] for col in factor_cols if col in df.columns}
        return self.discover(target, candidates, max_lag=max_lag)


# ═══════════════════════════════════════════════════════════════
# LLM 因果抽取（DeepSeek）
# ═══════════════════════════════════════════════════════════════

class LLMCausalExtractor:
    """使用 DeepSeek LLM 从感知上下文中抽取因果三元组。"""

    SYSTEM_PROMPT = """你是一个金融市场因果推理专家。根据提供的市场数据，识别其中存在的因果关系。

输出格式（只输出 JSON 数组，不要其他内容）：
[
  {
    "cause": "原因实体",
    "relation": "causes_increase | causes_decrease | triggers | suppresses",
    "effect": "结果实体",
    "confidence": 0.0~1.0,
    "evidence": "数据证据简述"
  }
]

要求：
1. 只输出有明确数据支撑的因果关系
2. 优先输出对交易决策有指导意义的因果
3. 只输出 JSON 数组"""

    def __init__(self):
        from llm_config import get_llm_config
        self.llm_cfg = get_llm_config()
        self.api_key = self.llm_cfg["api_key"]
        self.available = bool(self.api_key and len(self.api_key) > 20)

    def extract(self, perception_context: dict, max_triplets: int = 5) -> list[CausalTriplet]:
        if not self.available:
            logger.warning("DeepSeek API Key 未配置")
            return []

        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.llm_cfg["api_base"])
        ctx_text = self._format_context(perception_context)

        try:
            response = client.chat.completions.create(
                model=self.llm_cfg["model"],
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",
                     "content": f"分析以下市场数据中的因果关系，输出最多 {max_triplets} 条：\n\n{ctx_text}"},
                ],
                temperature=self.llm_cfg["temperature"],
                max_tokens=self.llm_cfg["max_tokens"],
            )
            raw = response.choices[0].message.content.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            items = json.loads(raw)
            return [
                CausalTriplet(
                    cause_entity=item["cause"],
                    relation=item.get("relation", "relates_to"),
                    effect_entity=item["effect"],
                    confidence=item.get("confidence", 0.5),
                    source="llm",
                    evidence=item.get("evidence", ""),
                )
                for item in items
            ]
        except Exception as e:
            logger.error(f"LLM 因果抽取失败: {e}")
            return []

    @staticmethod
    def _format_context(ctx: dict) -> str:
        lines = []
        for level_key, label in [
            ("l1_micro", "L1 微观"), ("l2_meso", "L2 中期"), ("l3_macro", "L3 宏观")
        ]:
            data = ctx.get(level_key)
            if data:
                lines.append(f"\n[{label}]")
                for k, v in data.items():
                    if isinstance(v, float):
                        lines.append(f"  {k}: {v:.4f}")
                    elif v:
                        lines.append(f"  {k}: {v}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 混合因果抽取器
# ═══════════════════════════════════════════════════════════════

class HybridCausalExtractor:
    """统计因果 + LLM 因果 双路混合"""

    def __init__(self):
        self.statistical = StatisticalCausalDiscovery()
        self.llm = LLMCausalExtractor()

    def extract_all(
        self,
        perception_context: dict,
        kline_df: Optional[pd.DataFrame] = None,
    ) -> list[CausalTriplet]:
        all_triplets = []

        # 路 1：统计因果
        if kline_df is not None and not kline_df.empty:
            stat_results = self.statistical.discover_from_df(kline_df)
            all_triplets.extend(stat_results)
            logger.info(f"统计因果: {len(stat_results)} 条")

        # 路 2：LLM 因果
        if perception_context:
            llm_results = self.llm.extract(perception_context)
            all_triplets.extend(llm_results)
            logger.info(f"LLM 因果: {len(llm_results)} 条")

        # 去重
        seen = set()
        unique = []
        for t in all_triplets:
            key = f"{t.cause_entity}|{t.relation}|{t.effect_entity}"
            if key not in seen:
                seen.add(key)
                unique.append(t)
        return sorted(unique, key=lambda x: x.confidence, reverse=True)
