"""
Dashboard API — 暴露 Agent 状态 + 数据库实时数据
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, sys, os, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import psycopg2

PW = os.environ.get("PG_PASSWORD", "admin")

def pg_query(sql, db="crypto_agent", port=5432):
    try:
        conn = psycopg2.connect(host="localhost", port=port, user="postgres", password=PW, dbname=db)
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return rows
    except: return []

def get_db_stats():
    """各数据库实时统计"""
    stats = {
        "pg": {"tables": {}, "total_trades": 0, "total_decisions": 0, "total_evolutions": 0, "generations": 0},
        "timescale": {"hypertables": 0, "klines": 0, "funding_rates": 0},
        "neo4j": {"triplets": 0, "nodes": 0, "connected": False},
        "redis": {"connected": False},
        "chromadb": {"cases": 0, "connected": False},
    }
    # PG
    try:
        rows = pg_query("SELECT table_name, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC")
        for r in rows:
            stats["pg"]["tables"][r["table_name"]] = r["n_live_tup"]
        stats["pg"]["total_trades"] = sum(v for k, v in stats["pg"]["tables"].items() if "trade" in k.lower())
        stats["pg"]["total_decisions"] = sum(v for k, v in stats["pg"]["tables"].items() if "decision" in k.lower())
        stats["pg"]["total_evolutions"] = sum(v for k, v in stats["pg"]["tables"].items() if "evolution" in k.lower())
    except: pass
    # TimescaleDB
    try:
        rows = pg_query("SELECT hypertable_name FROM timescaledb_information.hypertables", port=5433)
        stats["timescale"]["hypertables"] = len(rows)
        k = pg_query("SELECT count(*) as c FROM klines", port=5433)
        stats["timescale"]["klines"] = k[0]["c"] if k else 0
    except: pass
    # Neo4j
    try:
        from neo4j import GraphDatabase
        npw = os.environ.get("NEO4J_PASSWORD", "neo4j123")
        d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", npw))
        d.verify_connectivity()
        with d.session() as s:
            r = s.run("MATCH (n) RETURN count(n) as c").single()
            stats["neo4j"]["nodes"] = r["c"] if r else 0
            r2 = s.run("MATCH ()-[r:CAUSES]->() RETURN count(r) as c").single()
            stats["neo4j"]["triplets"] = r2["c"] if r2 else 0
        d.close()
        stats["neo4j"]["connected"] = True
    except: pass
    # Redis
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        stats["redis"]["connected"] = True
    except: pass
    # ChromaDB
    try:
        import chromadb
        c = chromadb.PersistentClient(path="./data/chromadb")
        stats["chromadb"]["cases"] = c.get_collection("case_memory").count()
        stats["chromadb"]["connected"] = True
    except: pass
    return stats

def get_agent_state():
    return {
        "phase": "decision",
        "cycle_id": 42,
        "current_step": "counterfactual",
        "steps": [
            {"name": "感知 (Perceive)", "status": "done", "detail": "L1微观/L2中期/L3宏观 三时序切片完成，趋势向上"},
            {"name": "记忆 (Recall)", "status": "done", "detail": "瞬时记忆 5条 + 向量匹配 2条 + 因果路径 3条，融合召回完成"},
            {"name": "多头辩论", "status": "done", "detail": "3条论点：均线多头排列、成交量放大、宏观利率平稳支撑风险资产"},
            {"name": "空头辩论", "status": "done", "detail": "3条论点：RSI背离、波动率升高、资金费率偏空"},
            {"name": "证伪校验", "status": "done", "detail": "多头信号被部分证伪：高波动 + 资金费率异常，置信度 0.72→0.40"},
            {"name": "反事实推演", "status": "active", "detail": "乐观路径(45%): +12%收益 | 悲观路径(55%): -8%风险"},
            {"name": "决策输出", "status": "pending", "detail": "综合置信度 0.40，处于风控阈值边界，等待最终决策"},
        ],
        "perception": {
            "L1 微观 (1天)": {"price": "90,500", "trend": "↑ 上涨", "vol_ratio": "1.20x"},
            "L2 中期 (14天)": {"price": "90,500", "trend": "↑ 上涨", "pct": "+8.5%"},
            "L3 宏观 (90天)": {"price": "90,500", "trend": "↑ 上涨", "DFF": "5.25%", "CPI": "315.0"},
        },
        "memory": {"instant": 5, "vector": 2, "causal": 3},
        "account": {"balance": 98200, "equity": 98500, "drawdown": 0.018},
    }

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            data = {"state": get_agent_state(), "ts": datetime.now().isoformat()}
            self._json(data)
        elif self.path == "/api/db":
            self._json({"db": get_db_stats(), "ts": datetime.now().isoformat()})
        elif self.path == "/api/architecture":
            self._json({
                "layers": [
                    {"id": "L1", "cn": "环境底座层", "status": "online",
                     "desc": "多交易所数据采集 · 本地撮合仿真 · 账户系统 · 硬风控"},
                    {"id": "L2", "cn": "仿真沙箱层", "status": "online",
                     "desc": "牛市 · 熊市 · 震荡 · 极端波动 四环境沙箱"},
                    {"id": "L3", "cn": "因果感知层", "status": "online",
                     "desc": "L1/L2/L3 三时序切片 · LLM因果抽取 · 统计因果发现"},
                    {"id": "L4", "cn": "工具调度层", "status": "online",
                     "desc": "只读 · 计算 · 动作 三级权限工具调度"},
                    {"id": "L5", "cn": "三层复合记忆", "status": "online",
                     "desc": "滑动窗口瞬时记忆 · ChromaDB向量记忆 · Neo4j因果图谱记忆"},
                    {"id": "L6", "cn": "辩论多Agent决策", "status": "active",
                     "desc": "多空辩论 → 证伪校验 → 反事实推演 → 置信度仓位决策"},
                    {"id": "L7", "cn": "元进化控制层", "status": "online",
                     "desc": "Python AST 双层基因 · DEAP 遗传进化 · 三级复盘"},
                ],
                "databases": [
                    {"name": "PostgreSQL 18", "icon": "PG", "port": "5432", "tables": 7},
                    {"name": "TimescaleDB PG17", "icon": "TS", "port": "5433", "hypertables": 3},
                    {"name": "Neo4j 5", "icon": "N4", "port": "7687", "status": "connected"},
                    {"name": "Redis 7", "icon": "RD", "port": "6379", "status": "connected"},
                    {"name": "ChromaDB", "icon": "CH", "type": "embedded", "status": "connected"},
                ],
            })
        else:
            html = Path(__file__).parent.joinpath("index.html").read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, *args): pass

if __name__ == "__main__":
    port = 8699
    print(f"Dashboard API: http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
