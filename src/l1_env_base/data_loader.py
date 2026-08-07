"""
L1 数据导入器：将 data/raw/*.parquet 导入 TimescaleDB
- klines:      BTCUSDT_{interval}_*.parquet → klines 表 (hypertable)
- funding:     BTCUSDT_funding_*.parquet   → funding_rates 表 (hypertable)
- macro:       fred_*.parquet / coingecko_*.parquet → macro_data 表 (hypertable)

幂等策略：临时表 COPY → INSERT ... ON CONFLICT DO NOTHING，不删除任何现有数据。
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2

# 将 src 加入路径（与 main.py 一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_DB = os.getenv("PG_DB", "crypto_agent")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "admin")


def get_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASSWORD, dbname=PG_DB,
    )


def _copy_insert(conn, table: str, columns: list[str], df: pd.DataFrame) -> int:
    """临时表 COPY 导入后 INSERT ... ON CONFLICT DO NOTHING，返回插入行数"""
    col_sql = ", ".join(columns)
    temp = f"{table}_import_tmp"
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=True, date_format="%Y-%m-%d %H:%M:%S+00")
    buf.seek(0)
    with conn.cursor() as cur:
        # 会话级临时表，连接关闭自动清理
        cur.execute(f"CREATE TEMP TABLE {temp} (LIKE {table}) ON COMMIT DROP")
        cur.execute(f"ALTER TABLE {temp} DROP CONSTRAINT IF EXISTS {temp}_pkey")
        cur.copy_expert(f"COPY {temp} ({col_sql}) FROM STDIN WITH (FORMAT CSV, HEADER true)", buf)
        cur.execute(
            f"INSERT INTO {table} ({col_sql}) "
            f"SELECT {col_sql} FROM {temp} ON CONFLICT DO NOTHING"
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted


def import_klines(symbol: str = "BTCUSDT") -> int:
    """导入全部周期 K 线"""
    total = 0
    conn = get_conn()
    try:
        for p in sorted(DATA_DIR.glob(f"{symbol}_*_2024-01-01_2026-06-30.parquet")):
            interval = p.name.split("_")[1]
            if interval == "funding":
                continue
            df = pd.read_parquet(p)
            df["symbol"] = symbol
            df["interval"] = interval
            cols = ["ts", "symbol", "interval", "open", "high", "low", "close", "volume"]
            n = _copy_insert(conn, "klines", cols, df[cols])
            total += n
            print(f"  [OK] {symbol} {interval}: 导入 {n:,} 行")
    finally:
        conn.close()
    return total


def import_funding(symbol: str = "BTCUSDT") -> int:
    p = DATA_DIR / f"{symbol}_funding_2024-01-01_2026-06-30.parquet"
    if not p.exists():
        print(f"  [WARN] {p.name} 不存在")
        return 0
    conn = get_conn()
    try:
        df = pd.read_parquet(p)
        df["symbol"] = symbol
        cols = ["ts", "symbol", "rate"]
        n = _copy_insert(conn, "funding_rates", cols, df[cols])
        print(f"  [OK] funding_rate: 导入 {n:,} 行")
        return n
    finally:
        conn.close()


def import_macro() -> int:
    """导入 FRED 宏观序列 + CoinGecko BTC 日线"""
    total = 0
    conn = get_conn()
    try:
        for p in sorted(DATA_DIR.glob("fred_*.parquet")):
            indicator = p.name.split("_")[1]
            df = pd.read_parquet(p)
            df["source"] = "FRED"
            df["indicator"] = indicator
            cols = ["ts", "source", "indicator", "value"]
            n = _copy_insert(conn, "macro_data", cols, df[cols])
            total += n
            print(f"  [OK] FRED {indicator}: 导入 {n:,} 行")

        p = DATA_DIR / "coingecko_btc_365d.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            rows = []
            for _, r in df.iterrows():
                rows.append({"ts": r["ts"], "source": "COINGECKO", "indicator": "BTC_PRICE", "value": r["price"]})
                rows.append({"ts": r["ts"], "source": "COINGECKO", "indicator": "BTC_MARKET_CAP", "value": r["market_cap"]})
                rows.append({"ts": r["ts"], "source": "COINGECKO", "indicator": "BTC_TOTAL_VOLUME", "value": r["total_volume"]})
            mdf = pd.DataFrame(rows)
            n = _copy_insert(conn, "macro_data", ["ts", "source", "indicator", "value"], mdf)
            total += n
            print(f"  [OK] CoinGecko: 导入 {n:,} 行")
    finally:
        conn.close()
    return total


def import_klines_df(df: pd.DataFrame, symbol: str = "BTCUSDT", interval: str = "1h") -> int:
    """增量写入单批 K 线 DataFrame → klines 表（ON CONFLICT DO NOTHING 幂等）"""
    if df is None or df.empty:
        return 0
    conn = get_conn()
    try:
        d = df.copy()
        d["symbol"] = symbol
        d["interval"] = interval
        cols = ["ts", "symbol", "interval", "open", "high", "low", "close", "volume"]
        n = _copy_insert(conn, "klines", cols, d[cols])
        return n
    finally:
        conn.close()


def import_all():
    print("=" * 60)
    print("  parquet → TimescaleDB 数据导入")
    print("=" * 60)
    print("\n[1/3] K 线...")
    k = import_klines()
    print("\n[2/3] 资金费率...")
    f = import_funding()
    print("\n[3/3] 宏观数据...")
    m = import_macro()
    print("\n" + "=" * 60)
    print(f"  导入完成: klines {k:,} + funding {f:,} + macro {m:,}")
    print("=" * 60)


if __name__ == "__main__":
    import_all()
