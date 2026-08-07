"""
L5 案例向量存储
将历史交易案例（场景+决策+结果）编码为向量存入 ChromaDB，支持相似场景检索。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CaseRecord:
    """交易案例"""
    case_id: str
    scene_summary: str             # 场景文本（用于向量嵌入）
    action: str
    confidence: float
    pnl_pct: float
    regime: str
    timestamp: datetime
    metadata: dict                 # 额外结构化字段


class CaseVectorStore:
    """
    基于 ChromaDB 的交易案例向量记忆。

    - 写入：每笔交易完成后存入
    - 读取：根据当前场景向量检索最相似历史案例
    """

    COLLECTION_NAME = "case_memory"

    def __init__(self, persist_path: str = "./data/chromadb"):
        import chromadb
        self.client = chromadb.PersistentClient(path=persist_path)
        self._col = None

    @property
    def collection(self):
        if self._col is None:
            self._col = self.client.get_or_create_collection(self.COLLECTION_NAME)
        return self._col

    def store(self, case: CaseRecord) -> str:
        """存储一个交易案例"""
        metadata = case.metadata or {}
        metadata.update({
            "action": case.action,
            "confidence": case.confidence,
            "pnl_pct": case.pnl_pct,
            "regime": case.regime,
            "timestamp": case.timestamp.isoformat(),
        })
        self.collection.add(
            documents=[case.scene_summary],
            metadatas=[metadata],
            ids=[case.case_id],
        )
        return case.case_id

    def query(
        self, scene_text: str, n_results: int = 5, regime_filter: Optional[str] = None
    ) -> list[dict]:
        """
        根据当前场景检索最相似的历史案例。

        Args:
            scene_text: 当前场景描述文本
            n_results: 返回条数
            regime_filter: 可选 Regime 过滤

        Returns:
            [{id, distance, metadata, document}, ...]
        """
        where = None
        if regime_filter:
            where = {"regime": regime_filter}

        try:
            results = self.collection.query(
                query_texts=[scene_text],
                n_results=n_results,
                where=where,
            )
        except Exception as e:
            logger.warning(f"ChromaDB query failed: {e}")
            return []

        if not results["ids"] or not results["ids"][0]:
            return []

        merged = []
        for i in range(len(results["ids"][0])):
            merged.append({
                "id": results["ids"][0][i],
                "distance": results["distances"][0][i] if results["distances"] else 0,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "document": results["documents"][0][i] if results["documents"] else "",
            })
        return merged

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def build_scene_text(
        self, regime: str, trend: str, vol_ratio: float, pct_change: float
    ) -> str:
        """将当前感知数据构建为场景文本，用于向量检索"""
        return (
            f"Regime: {regime}. "
            f"Trend: {trend}. "
            f"Volume ratio: {vol_ratio:.2f}. "
            f"Price change: {pct_change:.1f}%."
        )
