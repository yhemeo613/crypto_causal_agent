"""
L5 多路融合召回器
融合向量检索（ChromaDB）+ 因果图谱（Neo4j）+ 瞬时记忆（滑动窗口）
时间衰减 + 负样本加权 + 去重排序
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RecallItem:
    """单条召回结果"""
    source: str                           # instant | vector | causal_graph
    content: str                          # 内容简述
    relevance: float = 1.0                # 原始相关性分数
    decay_weight: float = 1.0             # 时间衰减权重
    negative_boost: float = 1.0           # 负样本加权（>1 表示失败案例更重要）
    score: float = 0.0                    # 综合得分
    metadata: dict = field(default_factory=dict)


class FusionRecaller:
    """
    多路融合召回器。

    三路召回：
    1. 瞬时记忆 — 滑动窗口最近 N 步
    2. 向量记忆 — ChromaDB 相似历史案例
    3. 因果记忆 — Neo4j 因果路径查询

    融合策略：
    - 时间衰减：越久远的记忆权重越低
    - 负样本加权：亏损案例权重 > 盈利案例（失败比成功更有学习价值）
    - 去重按综合得分降序
    """

    def __init__(
        self,
        instant_memory,          # InstantMemory
        case_store,              # CaseVectorStore
        causal_graph,            # CausalGraphQuery
        decay_factor: float = 0.95,
        negative_sample_weight: float = 2.0,
    ):
        self.instant = instant_memory
        self.cases = case_store
        self.causal = causal_graph
        self.decay_factor = decay_factor
        self.negative_weight = negative_sample_weight

    def recall(self, scene_text: str, current_ts: Optional[datetime] = None) -> list[RecallItem]:
        """
        执行三路融合召回。

        Args:
            scene_text: 当前场景描述（用于向量检索）
            current_ts: 当前时间戳（用于时间衰减）

        Returns:
            综合排序后的召回结果
        """
        current_ts = current_ts or datetime.now(timezone.utc)
        items: list[RecallItem] = []

        # 路 1：瞬时记忆
        items.extend(self._recall_instant(current_ts))

        # 路 2：向量记忆
        items.extend(self._recall_vector(scene_text))

        # 路 3：因果记忆
        items.extend(self._recall_causal(scene_text))

        # 融合
        for item in items:
            item.decay_weight = self._compute_decay(item, current_ts)
            item.negative_boost = self._compute_negative_boost(item)
            item.score = item.relevance * item.decay_weight * item.negative_boost

        # 去重 + 排序
        seen = set()
        unique = []
        for item in sorted(items, key=lambda x: x.score, reverse=True):
            key = f"{item.source}|{(item.content or '')[:50]}"  # content 可能为 None，容错
            if key not in seen:
                seen.add(key)
                unique.append(item)

        logger.info(f"召回: 瞬时{sum(1 for i in items if i.source=='instant')} "
                    f"向量{sum(1 for i in items if i.source=='vector')} "
                    f"因果{sum(1 for i in items if i.source=='causal_graph')} "
                    f"→ 融合后{len(unique)}条")

        return unique

    # ─── 各路召回 ──────────────────────────────────────────

    def _recall_instant(self, current_ts: datetime) -> list[RecallItem]:
        items = []
        for entry in self.instant.get_recent(10):
            age_hours = (current_ts - entry.timestamp).total_seconds() / 3600
            items.append(RecallItem(
                source="instant",
                content=f"Cycle#{entry.cycle_id}: {entry.action} conf={entry.confidence:.2f} pnl={entry.pnl:.1f}",
                relevance=entry.confidence,
                metadata={"cycle_id": entry.cycle_id, "age_hours": age_hours,
                          "action": entry.action, "pnl": entry.pnl, "regime": entry.regime},
            ))
        return items

    def _recall_vector(self, scene_text: str) -> list[RecallItem]:
        results = self.cases.query(scene_text, n_results=5)
        items = []
        for r in results:
            meta = r.get("metadata") or {}  # chroma 偶发返回 None metadata，容错
            dist = r.get("distance", 1.0)
            relevance = max(0.0, 1.0 - dist)  # distance 越小越相似
            items.append(RecallItem(
                source="vector",
                content=r.get("document", ""),
                relevance=relevance,
                metadata=meta,
            ))
        return items

    def _recall_causal(self, scene_text: str) -> list[RecallItem]:
        keywords = _extract_keywords(scene_text)
        if not keywords:
            return []
        results = self.causal.query_related_events(keywords, limit=5)
        items = []
        for r in results:
            edges = r.get("edges", [])
            avg_conf = sum(e.get("conf", 0) for e in edges if e.get("conf")) / max(len(edges), 1)
            items.append(RecallItem(
                source="causal_graph",
                content=f"{r['name']} ({r['type']}): {len(edges)} causal links",
                relevance=avg_conf,
                metadata=r,
            ))
        return items

    # ─── 权重计算 ──────────────────────────────────────────

    def _compute_decay(self, item: RecallItem, current_ts: datetime) -> float:
        """时间衰减：越久远权重越低"""
        age_hours = item.metadata.get("age_hours")
        if age_hours is None:
            ts_str = item.metadata.get("timestamp")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    age_hours = (current_ts - ts).total_seconds() / 3600
                except Exception:
                    age_hours = 24.0
            else:
                return 1.0  # 概念性记忆不衰减

        return self.decay_factor ** (age_hours / 24)

    def _compute_negative_boost(self, item: RecallItem) -> float:
        """负样本加权：亏损案例 > 盈利案例"""
        pnl = item.metadata.get("pnl")
        if pnl is None:
            pnl_pct = item.metadata.get("pnl_pct")
            if pnl_pct is not None and pnl_pct < 0:
                return self.negative_weight
            return 1.0

        if pnl < 0:
            return self.negative_weight
        return 1.0


def _extract_keywords(text: str) -> list[str]:
    """简单关键词提取"""
    import re
    words = re.findall(r'[a-zA-Z_]+', text)
    stopwords = {"the", "a", "an", "is", "was", "to", "in", "of", "and", "or", "ratio", "trend", "regime", "price"}
    return [w for w in words if w.lower() not in stopwords and len(w) > 2]
