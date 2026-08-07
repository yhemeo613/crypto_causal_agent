"""
P1-06 记忆自清洗

定期清理低质量/过时记忆，保持记忆库有效性：
  - 过期清理：按 timestamp 删除超过 max_age_days 的记忆
  - 上限控制：超过 max_entries 时删除最旧条目（保留近期高频访问）
  - 高频保护：最近 protect_recent 条永不清理
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryCleaner:
    """ChromaDB 案例记忆清洗器"""

    def __init__(
        self,
        store_path: str = "./data/chromadb",
        max_entries: int = 2000,
        max_age_days: int = 90,
        protect_recent: int = 100,
    ):
        from l5_memory.case_vector_store import CaseVectorStore
        self.store = CaseVectorStore(persist_path=store_path)
        self.max_entries = max_entries
        self.max_age_days = max_age_days
        self.protect_recent = protect_recent

    def _all_entries(self) -> tuple[list[str], list[dict]]:
        """返回 (ids, metadatas)"""
        try:
            got = self.store.collection.get(include=["metadatas"])
        except Exception as e:
            logger.warning(f"记忆读取失败: {e}")
            return [], []
        ids = got.get("ids") or []
        metas = got.get("metadatas") or []
        return ids, metas

    def clean(self) -> dict:
        """执行一次清洗，返回统计"""
        ids, metas = self._all_entries()
        if not ids:
            return {"total": 0, "removed_expired": 0, "removed_overflow": 0, "kept": 0}

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self.max_age_days)

        to_delete: list[str] = []
        expired = 0
        for i, meta in enumerate(metas):
            ts = (meta or {}).get("timestamp") or ""
            try:
                t = datetime.fromisoformat(ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t < cutoff:
                    to_delete.append(ids[i])
                    expired += 1
            except Exception:
                # 无时间戳或解析失败：视为低质量，超过保护线才删
                if i >= self.protect_recent:
                    to_delete.append(ids[i])

        # 上限控制：保留最近 max_entries 条（含保护线内）
        kept_ids = [i for i in ids if i not in to_delete]
        overflow = len(kept_ids) - self.max_entries
        if overflow > 0:
            # 按存储顺序（近似时间序）删除最旧
            old_first = [i for i in kept_ids if i not in set(ids[: self.protect_recent])]
            for i in old_first[:overflow]:
                if i not in to_delete:
                    to_delete.append(i)

        if to_delete:
            try:
                self.store.collection.delete(ids=to_delete)
                logger.info(f"[memory-clean] 删除 {len(to_delete)} 条记忆 "
                            f"(过期 {expired}, 超上限 {max(0, overflow)})")
            except Exception as e:
                logger.warning(f"记忆删除失败: {e}")
                return {"total": len(ids), "error": str(e)}

        kept = len(ids) - len(to_delete)
        return {
            "total": len(ids),
            "removed_expired": expired,
            "removed_overflow": max(0, overflow),
            "removed_total": len(to_delete),
            "kept": kept,
        }


def run_scheduled_clean(store_path: str = "./data/chromadb", **kw) -> dict:
    """供定时任务调用的便捷入口"""
    try:
        return MemoryCleaner(store_path=store_path, **kw).clean()
    except Exception as e:
        logger.warning(f"定时记忆清洗失败: {e}")
        return {"error": str(e)}
