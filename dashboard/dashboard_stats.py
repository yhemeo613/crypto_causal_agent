"""数据库健康统计（供工作台 /api/db 使用）"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def pg_query(sql, db="crypto_agent", port=5433):
    import psycopg2
    import psycopg2.extras
    try:
        conn = psycopg2.connect(
            host="localhost", port=port, user="postgres",
            password=os.getenv("PG_PASSWORD", "admin"), dbname=db,
        )
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            try:
                return cur.fetchall()
            except Exception:
                return []
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_db_stats():
    stats = {
        "pg": {"tables": {}, "total_trades": 0, "total_decisions": 0, "total_evolutions": 0, "generations": 0},
        "timescale": {"hypertables": 0, "klines": 0, "funding_rates": 0},
        "neo4j": {"triplets": 0, "nodes": 0, "connected": False},
        "redis": {"connected": False},
        "chromadb": {"cases": 0, "connected": False},
    }

    # 业务库（本地 PG 5432：决策/进化/复盘/规则/交易）
    try:
        from db_conn import pg_query as _pq
        rows = _pq("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        tables = {}
        for r in rows:
            t = r["tablename"]
            c = _pq(f"SELECT count(*) c FROM {t}")
            tables[t] = c[0]["c"] if c else 0
        stats["pg"]["tables"] = tables
        tr = _pq("SELECT count(*) c FROM trades")
        stats["pg"]["total_trades"] = tr[0]["c"] if tr else 0
        dl = _pq("SELECT count(*) c FROM decision_logs")
        stats["pg"]["total_decisions"] = dl[0]["c"] if dl else 0
        ev = _pq("SELECT count(*) c FROM evolution_logs")
        stats["pg"]["total_evolutions"] = ev[0]["c"] if ev else 0
        gen = _pq("SELECT COALESCE(MAX(generation),0) g FROM evolution_logs")
        stats["pg"]["generations"] = gen[0]["g"] if gen else 0
    except Exception:
        pass

    # 时序库（docker timescaledb 5433：klines/funding/macro）
    try:
        from db_conn import ts_query as _tq
        rows = _tq("SELECT hypertable_name FROM timescaledb_information.hypertables")
        stats["timescale"]["hypertables"] = len(rows)
        k = _tq("SELECT count(*) c FROM klines")
        stats["timescale"]["klines"] = k[0]["c"] if k else 0
        f = _tq("SELECT count(*) c FROM funding_rates")
        stats["timescale"]["funding_rates"] = f[0]["c"] if f else 0
    except Exception:
        pass

    # Neo4j
    try:
        from db_conn import get_neo4j_driver
        d = get_neo4j_driver()
        d.verify_connectivity()
        with d.session() as s:
            r = s.run("MATCH (n) RETURN count(n) AS c").single()
            stats["neo4j"]["nodes"] = r["c"] if r else 0
            r2 = s.run("MATCH ()-[r:CAUSES]->() RETURN count(r) AS c").single()
            stats["neo4j"]["triplets"] = r2["c"] if r2 else 0
        d.close()
        stats["neo4j"]["connected"] = True
    except Exception:
        pass

    # Redis
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        stats["redis"]["connected"] = True
    except Exception:
        pass

    # ChromaDB
    try:
        from db_conn import get_chroma_client
        c = get_chroma_client(str(ROOT / "data" / "chromadb"))
        stats["chromadb"]["cases"] = c.get_collection("case_memory").count()
        stats["chromadb"]["connected"] = True
    except Exception:
        pass

    return stats
