"""L5 记忆系统测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime, timedelta, timezone
from l5_memory.instant_memory import InstantMemory, InstantMemoryEntry
from l5_memory.case_vector_store import CaseVectorStore, CaseRecord
from l5_memory.causal_graph_query import CausalGraphQuery
from l5_memory.fusion_recaller import FusionRecaller


def test_instant_memory():
    mem = InstantMemory(window_size=5)
    now = datetime.now(timezone.utc)
    for i in range(8):
        mem.push(InstantMemoryEntry(
            timestamp=now + timedelta(hours=i),
            cycle_id=i, price=90000 + i * 100,
            action="long" if i % 2 == 0 else "short",
            confidence=0.5 + i * 0.05, pnl=100 if i % 2 == 0 else -50,
            regime="trend_up", summary=f"Trade {i}",
        ))

    assert len(mem) == 5, f"窗口应为5, 实际{len(mem)}"
    assert mem.last().cycle_id == 7
    assert mem.win_rate() == 2 / 5  # 偶数 long 盈利
    print(f"  [OK] 窗口={len(mem)}, 胜率={mem.win_rate():.0%}, 平均置信度={mem.avg_confidence():.2f}")


def test_case_vector_store():
    store = CaseVectorStore(persist_path="./data/chromadb")

    # 写入
    for i in range(3):
        store.store(CaseRecord(
            case_id=f"test_{i}",
            scene_summary=f"Regime: trend_up. Trend: up. Volume ratio: {1.0+i*0.5:.2f}. Price change: {10+i*5:.1f}%.",
            action="long" if i < 2 else "short",
            confidence=0.7 + i * 0.1,
            pnl_pct=5.0 if i == 0 else -3.0 if i == 1 else 2.0,
            regime="trend_up",
            timestamp=datetime.now(timezone.utc),
            metadata={},
        ))

    # 检索
    scene = "Regime: trend_up. Trend: up. Volume ratio: 1.10. Price change: 12.0%."
    results = store.query(scene, n_results=2)
    assert len(results) >= 1, f"应至少1条, 实际{len(results)}"

    # 清理
    store.collection.delete(ids=["test_0", "test_1", "test_2"])
    print(f"  [OK] 写入3条, 查询返回{len(results)}条, top dist={results[0]['distance']:.4f}")


def test_causal_graph():
    g = CausalGraphQuery()
    g.ensure_schema()

    # 写入因果链
    g.write_causal_triplet("利率上升", "macro", "BTC下跌", "price", "causes_decrease", 0.8, "FRED DFF up")
    g.write_causal_triplet("BTC下跌", "price", "市场恐慌", "sentiment", "triggers", 0.7, "High vol")
    g.write_causal_triplet("成交量萎缩", "volume", "BTC波动加剧", "price", "leads_to", 0.5, "")

    # 查询
    paths = g.query_causal_paths("BTC", max_depth=2)
    top = g.query_top_confidence_triplets(limit=5)

    assert len(top) > 0, f"应有因果三元组, 实际{len(top)}"
    print(f"  [OK] 因果路径={len(paths)}条, top置信度={top[0]['confidence']:.2f}")

    # 清理（仅删测试数据，不清空生产图谱）
    g.clear_test_data(["利率上升", "BTC下跌", "市场恐慌", "成交量萎缩", "BTC波动加剧"])
    g.close()


def test_fusion_recaller():
    # 瞬时记忆
    mem = InstantMemory(window_size=5)
    now = datetime.now(timezone.utc)
    for i in range(3):
        mem.push(InstantMemoryEntry(
            timestamp=now - timedelta(hours=3 - i), cycle_id=i,
            price=90000, action="long", confidence=0.7, pnl=-200 if i == 1 else 100,
            regime="trend_up", summary="",
        ))

    # 向量
    store = CaseVectorStore(persist_path="./data/chromadb")
    store.store(CaseRecord("t1", "trend_up up vol 1.0 pct 10%", "long", 0.8, -5.0, "trend_up", now, {}))
    store.store(CaseRecord("t2", "trend_down down vol 2.0 pct -8%", "short", 0.6, 8.0, "trend_down", now, {}))

    # 因果
    g = CausalGraphQuery()
    g.ensure_schema()
    g.write_causal_triplet("BTC价格", "price", "成交量变化", "volume", "causes", 0.6, "")

    # 融合
    fusion = FusionRecaller(mem, store, g, decay_factor=0.9, negative_sample_weight=2.0)
    results = fusion.recall("trend_up up vol 1.0 pct 10%")

    assert len(results) > 0, "应有融合结果"
    # 负样本应该排前面
    has_negative_boosted = any(
        r.metadata.get("pnl_pct", 0) < 0 and r.negative_boost > 1.0
        for r in results if r.source == "vector"
    )
    print(f"  [OK] 融合结果={len(results)}条, 负样本加权={'YES' if has_negative_boosted else 'NO'}")

    # 清理（仅删测试数据，不清空生产图谱）
    store.collection.delete(ids=["t1", "t2"])
    g.clear_test_data(["BTC价格", "成交量变化"])
    g.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  L5 记忆系统测试")
    print("=" * 60)
    test_instant_memory()
    test_case_vector_store()
    test_causal_graph()
    test_fusion_recaller()
    print("\n" + "=" * 60)
    print("  [OK] 全部通过")
    print("=" * 60)
