"""L6 LangGraph 决策层测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from l6_agent.state import AgentState, DecisionResult
from l6_agent.graph_builder import DecisionPipeline
from l5_memory.instant_memory import InstantMemory, InstantMemoryEntry
from l5_memory.case_vector_store import CaseVectorStore, CaseRecord
from l5_memory.causal_graph_query import CausalGraphQuery
from l5_memory.fusion_recaller import FusionRecaller
from datetime import datetime, timezone


def build_test_context():
    """构建真实测试上下文"""
    now = datetime.now(timezone.utc)

    # 感知
    perception = {
        "timestamp": now.isoformat(),
        "symbol": "BTCUSDT",
        "regime": "trend_up",
        "l1_micro": {
            "level": "L1", "window_days": 1,
            "price_current": 90500.0, "pct_change": 2.3,
            "volatility": 0.45, "trend_direction": "up",
            "trend_strength": 0.6, "volume_ratio": 1.2,
        },
        "l2_meso": {
            "level": "L2", "window_days": 14,
            "price_current": 90500.0, "pct_change": 8.5,
            "volatility": 0.38, "trend_direction": "up",
            "trend_strength": 0.7, "volume_ratio": 1.1,
        },
        "l3_macro": {
            "level": "L3", "window_days": 90,
            "price_current": 90500.0, "pct_change": 25.0,
            "volatility": 0.52, "trend_direction": "up",
            "trend_strength": 0.8, "volume_ratio": 0.9,
            "macro_indicators": {"DFF": 5.25, "CPI": 315.0, "UNRATE": 4.1},
        },
    }

    # 瞬时记忆
    mem = InstantMemory(window_size=5)
    for i in range(3):
        mem.push(InstantMemoryEntry(
            timestamp=now, cycle_id=i, price=90000 + i * 500,
            action="long", confidence=0.7, pnl=200 if i < 2 else -100,
            regime="trend_up", summary=f"Trade {i}",
        ))

    # 向量记忆
    store = CaseVectorStore(persist_path="./data/chromadb")
    store.store(CaseRecord("p4_t1", "trend_up up vol 1.2 pct 10%", "long", 0.8, 8.0, "trend_up", now, {}))
    store.store(CaseRecord("p4_t2", "trend_up up vol 1.5 pct 15%", "long", 0.7, -4.0, "trend_up", now, {}))
    scene = "trend_up up vol 1.2 pct 2.3%"
    vector_results = store.query(scene, n_results=2)

    # 因果记忆
    g = CausalGraphQuery()
    g.ensure_schema()
    g.write_causal_triplet("利率平稳", "macro", "BTC上涨", "price", "causes_increase", 0.75, "DFF stable")
    g.write_causal_triplet("BTC上涨", "price", "做多情绪", "sentiment", "triggers", 0.65, "")
    causal_paths = g.query_causal_paths("BTC", max_depth=2)

    memory = {
        "case_matches": [{"content": r.get("document", ""), "metadata": r.get("metadata", {})} for r in vector_results],
        "causal_paths": causal_paths,
        "instant_context": [f"C{i}: {e.action} pnl={e.pnl}" for i, e in enumerate(mem.get_recent(5))],
        "merged": [],
    }

    account = {"balance": 98000, "drawdown_pct": 0.02, "daily_trade_count": 3}

    return perception, memory, account, store, g


def test_decision_pipeline():
    """全闭环决策流程"""
    perception, memory, account, store, g = build_test_context()

    pipeline = DecisionPipeline()
    result = pipeline.run(perception, memory, account, cycle_id=42)

    # 验证各阶段 — 转为 plain dict
    def to_dict(v):
        return v.model_dump() if hasattr(v, 'model_dump') else v

    bull = to_dict(result["bull_debate"])
    bear = to_dict(result["bear_debate"])
    fals = to_dict(result["falsification"])
    cf = to_dict(result["counterfactual"])
    dec = to_dict(result["decision"])

    print(f"  Bull: {len(bull['arguments'])} args, conclusion={bull['conclusion'][:50]}...")
    print(f"  Bear: {len(bear['arguments'])} args, conclusion={bear['conclusion'][:50]}...")
    print(f"  Falsify: is_falsified={fals['is_falsified']}, adj_conf={fals.get('confidence_adjusted',0):.2f}")
    print(f"  Counterfactual: {len(cf['paths'])} paths, w_conf={cf['weighted_confidence']:.2f}")
    print(f"  DECISION: action={dec['action']} conf={dec['confidence']:.2f} "
          f"size={dec['position_size_pct']:.2f} leverage={dec['leverage']}x")
    print(f"  Reasoning: {dec['reasoning'][:80]}...")

    assert dec["action"] in ("long", "short", "hold")
    assert 0 <= dec["confidence"] <= 1

    # 清理（仅删测试数据，不清空生产图谱）
    store.collection.delete(ids=["p4_t1", "p4_t2"])
    g.clear_test_data(["利率平稳", "BTC上涨", "做多情绪"])
    g.close()

    print(f"\n  [OK] 全闭环决策完成: {dec['action']}")


if __name__ == "__main__":
    print("=" * 60)
    print("  L6 LangGraph 决策层测试")
    print("=" * 60)
    test_decision_pipeline()
    print("\n" + "=" * 60)
    print("  [OK] 测试通过")
    print("=" * 60)
