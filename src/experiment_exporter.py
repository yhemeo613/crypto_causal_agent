"""
实验数据记录与导出（P0-15）

将 DB 中的决策日志 / 进化日志 / 交易记录 / 复盘报告 / 基因库
导出为结构化文件：CSV / JSON / Pickle，可直接被 pandas 加载分析。
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _pg_query(sql: str, params: tuple = ()) -> list[dict]:
    from db_conn import pg_query as _q
    return _q(sql, params)


TABLES = {
    "decisions": ("decision_logs", "cycle_id"),
    "trades": ("trades", "id"),
    "evolution": ("evolution_logs", "id"),
    "replay_reports": ("replay_reports", "id"),
}


def export_all(out_dir: str | Path, formats: tuple[str, ...] = ("csv", "json", "pickle")) -> dict:
    """
    导出全部实验数据。

    Args:
        out_dir: 输出目录（默认 data/experiments/<timestamp>）
        formats: 可选 csv / json / pickle

    Returns:
        {"out_dir": str, "files": [相对路径...], "records": {表名: 行数}}
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files, records = [], {}

    for key, (table, order_col) in TABLES.items():
        rows = _pg_query(f"SELECT * FROM {table} ORDER BY {order_col}")
        records[key] = len(rows)
        df = pd.DataFrame(rows)
        if not df.empty:
            for f in df.select_dtypes(include=["datetime64[ns, UTC]", "datetime64[ns]"]).columns:
                df[f] = df[f].astype(str)

        base = out / key
        if "csv" in formats:
            p = base.with_suffix(".csv")
            (df if not df.empty else pd.DataFrame()).to_csv(p, index=False)
            files.append(p.name)
        if "json" in formats:
            p = base.with_suffix(".json")
            p.write_text(json.dumps(rows, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append(p.name)
        if "pickle" in formats:
            p = base.with_suffix(".pkl")
            df.to_pickle(p)
            files.append(p.name)

    # 基因库（Pickle：基因编码/解码对象）
    gene_files = _export_genes(out)
    files.extend(gene_files)

    # 元信息
    meta = {
        "exported_at": datetime.now().isoformat(),
        "records": records,
        "files": files,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    files.append("meta.json")

    logger.info(f"[export] 导出完成 → {out} ({len(files)} 文件, {records})")
    return {"out_dir": str(out), "files": files, "records": records}


def _export_genes(out: Path) -> list[str]:
    """导出基因库为 Pickle + CSV（进化日志中的基因代码/参数）"""
    files = []
    try:
        rows = _pg_query(
            "SELECT id, generation, gene_id, parent_gene_ids, gene_code, gene_params, "
            "fitness, env_performances FROM evolution_logs ORDER BY id")
        if rows:
            for r in rows:
                if isinstance(r.get("gene_params"), str):
                    try:
                        r["gene_params"] = json.loads(r["gene_params"])
                    except Exception:
                        pass
            p = out / "gene_library.pkl"
            p.write_bytes(pickle.dumps(rows))
            files.append(p.name)

            df = pd.DataFrame([{
                "gene_id": r.get("gene_id"), "generation": r.get("generation"),
                "fitness": r.get("fitness"), "gene_code": (r.get("gene_code") or "")[:200],
            } for r in rows])
            c = out / "gene_library.csv"
            df.to_csv(c, index=False)
            files.append(c.name)
    except Exception as e:
        logger.warning(f"[export] 基因库导出跳过: {e}")
    return files


def export_decision_csv(symbol: str = "BTCUSDT", out_dir: str | Path = "data/experiments") -> str:
    """便捷导出：单交易对决策序列（论文分析常用）"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = _pg_query(
        "SELECT cycle_id, symbol, action, confidence, position_size, ts "
        "FROM decision_logs WHERE symbol=%s ORDER BY cycle_id", (symbol,))
    df = pd.DataFrame(rows)
    p = out / f"decisions_{symbol}.csv"
    df.to_csv(p, index=False)
    return str(p)
