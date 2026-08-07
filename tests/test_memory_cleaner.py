"""P1-06 记忆自清洗测试"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from l5_memory.memory_cleaner import MemoryCleaner


def _mk_case(case_id: str, ts: str, action: str = "long", pnl: float = 0.01):
    from l5_memory.case_vector_store import CaseRecord
    return CaseRecord(
        case_id=case_id,
        scene_summary=f"scene for {case_id}",
        action=action,
        confidence=0.6,
        pnl_pct=pnl,
        regime="bull",
        timestamp=datetime.fromisoformat(ts),
        metadata={},
    )


@pytest.fixture
def cleaner(tmp_path):
    return MemoryCleaner(store_path=str(tmp_path / "chroma"),
                         max_entries=50, max_age_days=30, protect_recent=10)


def test_clean_removes_expired(cleaner):
    now = datetime.now(timezone.utc)
    # 1 条过期（60 天前）、1 条新
    cleaner.store.store(_mk_case("old-1", (now - timedelta(days=60)).isoformat()))
    cleaner.store.store(_mk_case("new-1", now.isoformat()))
    r = cleaner.clean()
    assert r["removed_expired"] == 1
    assert r["kept"] == 1


def test_clean_keeps_recent_high_freq(cleaner):
    now = datetime.now(timezone.utc)
    # 50 条新记忆（保护线 10 条内），超上限 50 → 应保留最近 50 条不删（没有溢出）
    for i in range(40):
        cleaner.store.store(_mk_case(f"k-{i}", now.isoformat()))
    r = cleaner.clean()
    assert r["total"] == 40
    assert r["removed_overflow"] == 0


def test_clean_overflow_trims_oldest(cleaner):
    now = datetime.now(timezone.utc)
    # 60 条新记忆，max_entries=50 → 删 10 条最旧
    for i in range(60):
        cleaner.store.store(_mk_case(f"o-{i:03d}", (now - timedelta(minutes=60 - i)).isoformat()))
    r = cleaner.clean()
    assert r["removed_overflow"] == 10
    assert r["kept"] == 50


def test_clean_idempotent(cleaner):
    now = datetime.now(timezone.utc)
    cleaner.store.store(_mk_case("i-1", now.isoformat()))
    r1 = cleaner.clean()
    r2 = cleaner.clean()
    assert r2["removed_total"] == 0  # 二次清洗无删除
    assert r1["kept"] == 1
