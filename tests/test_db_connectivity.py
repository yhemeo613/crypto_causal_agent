"""综合数据库连通性测试"""
import sys, os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

results = []

# ─── 1. PostgreSQL ──────────────────────────────────────
try:
    import psycopg2
    pw = os.environ.get("PG_PASSWORD", "")
    conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password=pw, dbname="crypto_agent")
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    results.append(("[OK] PostgreSQL", f"{len(tables)} tables: {tables}"))
except Exception as e:
    results.append(("[FAIL] PostgreSQL", str(e)[:80]))

# ─── 2. Neo4j ───────────────────────────────────────────
try:
    from neo4j import GraphDatabase
    pw = os.environ.get("NEO4J_PASSWORD", "neo4j123")
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", pw))
    driver.verify_connectivity()
    with driver.session() as s:
        r = s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Test) REQUIRE n.id IS UNIQUE").consume()
        s.run("MERGE (n:Test {id: 1}) SET n.name = 'hello'").consume()
        result = s.run("MATCH (n:Test {id: 1}) RETURN n.name").single()
        s.run("MATCH (n:Test) DETACH DELETE n").consume()
    driver.close()
    results.append(("[OK] Neo4j", f"Cypher CRUD OK: {result['n.name']}"))
except Exception as e:
    results.append(("[FAIL] Neo4j", str(e)[:80]))

# ─── 3. Redis ───────────────────────────────────────────
try:
    import redis
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    r.ping()
    r.set("__test__", "ok", ex=5)
    val = r.get("__test__")
    results.append(("[OK] Redis", f"SET/GET: {val}"))
except Exception as e:
    results.append(("[FAIL] Redis", str(e)[:80]))

# ─── 4. ChromaDB ────────────────────────────────────────
try:
    import chromadb
    # settings 必须与 src/l5_memory/case_vector_store.py 一致，否则 SharedSystemClient 单例冲突
    client = chromadb.PersistentClient(
        path="./data/chromadb",
        settings=chromadb.Settings(anonymized_telemetry=False))
    col_name = "test_conn"
    try:
        col = client.get_collection(col_name)
    except:
        col = client.create_collection(col_name)
    col.add(documents=["hello world"], ids=["id1"])
    r = col.query(query_texts=["hello"], n_results=1)
    client.delete_collection(col_name)
    results.append(("[OK] ChromaDB", f"query OK: {len(r['ids'][0])} result"))
except Exception as e:
    results.append(("[FAIL] ChromaDB", str(e)[:80]))

# ─── 输出 ───────────────────────────────────────────────
print("=" * 60)
print("  数据库连通性测试")
print("=" * 60)
for status, detail in results:
    print(f"  {status}  {detail}")
print("=" * 60)
all_ok = all(s.startswith("[OK]") for s, _ in results)
print(f"  {'[OK] ALL PASSED' if all_ok else '[FAIL]'}")
print("=" * 60)
