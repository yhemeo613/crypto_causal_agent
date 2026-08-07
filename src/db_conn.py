"""
统一数据库连接（消除 7 处重复连接串）

- PostgreSQL: config database.postgresql（host/port/dbname/user/password，env 覆盖）
- Neo4j:      config database.neo4j（uri/user/password）
- ChromaDB:   本地持久化路径
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from config_utils import ensure_dotenv, get_value

ensure_dotenv()


def pg_conn_params() -> dict:
    """业务库连接参数（本地 PG 5432，config + env 覆盖）"""
    return {
        "host": get_value("database.postgresql.host", "localhost"),
        "port": int(get_value("database.postgresql.port", 5432)),
        "dbname": get_value("database.postgresql.dbname", "crypto_agent"),
        "user": get_value("database.postgresql.user", "postgres"),
        "password": get_value("database.postgresql.password",
                              os.environ.get("PG_PASSWORD", "admin")),
    }


def ts_conn_params() -> dict:
    """时序库连接参数（docker timescaledb 5433）"""
    return {
        "host": get_value("database.timescaledb.host", "localhost"),
        "port": int(get_value("database.timescaledb.port", 5433)),
        "dbname": get_value("database.timescaledb.dbname", "crypto_agent"),
        "user": get_value("database.timescaledb.user", "postgres"),
        "password": get_value("database.timescaledb.password",
                              os.environ.get("PG_PASSWORD", "admin")),
    }


def get_pg_conn():
    import psycopg2
    return psycopg2.connect(**pg_conn_params())


def get_ts_conn():
    import psycopg2
    return psycopg2.connect(**ts_conn_params())


def pg_query(sql: str, params: tuple = ()) -> list[dict]:
    """业务库查询（RealDictCursor）"""
    import psycopg2.extras
    conn = get_pg_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            try:
                return cur.fetchall()
            except Exception:
                return []
    finally:
        conn.close()


def pg_execute(sql: str, params: tuple = ()):
    """业务库写操作"""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()


def ts_query(sql: str, params: tuple = ()) -> list[dict]:
    """时序库查询（klines/funding_rates/macro_data，RealDictCursor）"""
    import psycopg2.extras
    conn = get_ts_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            try:
                return cur.fetchall()
            except Exception:
                return []
    finally:
        conn.close()


def ts_execute(sql: str, params: tuple = ()):
    """时序库写操作"""
    conn = get_ts_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()


def neo4j_params() -> dict:
    return {
        "uri": get_value("database.neo4j.uri", "bolt://localhost:7687"),
        "user": get_value("database.neo4j.user", "neo4j"),
        "password": get_value("database.neo4j.password",
                              os.environ.get("NEO4J_PASSWORD", "neo4j123")),
    }


def get_neo4j_driver():
    from neo4j import GraphDatabase
    p = neo4j_params()
    return GraphDatabase.driver(p["uri"], auth=(p["user"], p["password"]))


def get_chroma_client(path: Optional[str] = None):
    import chromadb
    store_path = path or get_value("database.chromadb.path", "./data/chromadb")
    return chromadb.PersistentClient(
        path=store_path,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
