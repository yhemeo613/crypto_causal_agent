"""
crypto_causal_agent — Agent 工作台后端 API (FastAPI)
端口 8699。提供：真实状态 / 数据 / 感知因果 / 记忆 / 决策 / 回测 / 进化 / 账户 / 配置 / 任务 / WebSocket
长任务（采集/导入/进化）后台线程执行 + WebSocket 推送进度。
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from dataclasses import asdict
import sys
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 将 src 加入路径
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

# 禁用 chromadb 遥测（posthog 版本不兼容导致 ERRO 刷屏）
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from l1_env_base.data_loader import import_all as _import_parquet  # noqa: E402
from l1_env_base.data_collector import MultiExchangeCollector, FREDCollector, CoinGeckoMacroCollector  # noqa: E402
from l1_env_base.account import Account  # noqa: E402
from l1_env_base.matching_engine import (  # noqa: E402
    MatchingEngine, LiquidationEngine, OrderRequest, OrderSide, OrderType,
)
from l1_env_base.risk_control import RiskController  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("workbench")

# ── 日志环形缓冲（监控用） ────────────────────────────
LOG_BUFFER_MAX = 800
log_buffer: deque[dict] = deque(maxlen=LOG_BUFFER_MAX)

class BufferLogHandler(logging.Handler):
    """将日志写入内存环形缓冲 + 推送 WebSocket"""

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            entry = {
                "ts": datetime.now().strftime("%H:%M:%S"),
                "level": record.levelname,
                "source": record.name,
                "message": msg,
            }
            log_buffer.append(entry)
            hub.emit("log", entry)
        except Exception:
            pass

_buf_handler = BufferLogHandler()
_buf_handler.setFormatter(logging.Formatter("%(message)s"))
_buf_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_buf_handler)
for _ln in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_ln).addHandler(_buf_handler)

# 抑制 chromadb 遥测刷屏（posthog capture 签名 bug，错误无意义）
for _ln in ("chromadb.telemetry.product.posthog", "chromadb.telemetry", "chromadb"):
    logging.getLogger(_ln).setLevel(logging.CRITICAL)

# 抑制 Neo4j INFORMATION 级 schema 通知（约束已存在等冗余提示，非错误）
logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)

app = FastAPI(title="Crypto Causal Agent Workbench", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def _jsonable(obj):
    """递归将 numpy 标量转为 Python 原生类型（FastAPI 序列化兼容）"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (datetime, pd.Timestamp)):
        return str(obj)
    return obj

# ─────────────────────────── 数据库辅助 ───────────────────────────

def pg_query(sql, params=None):
    """查询（业务库 5432：决策/进化/复盘/规则/交易）"""
    from db_conn import pg_query as _q
    return _q(sql, params or ())

def pg_execute(sql, params=None):
    """执行写操作（业务库 5432）"""
    from db_conn import pg_execute as _e
    _e(sql, params or ())

def ts_query(sql, params=None):
    """查询（时序库 5433：klines/funding_rates/macro_data）"""
    from db_conn import ts_query as _q
    return _q(sql, params or ())

def ts_execute(sql, params=None):
    """执行写操作（时序库 5433）"""
    from db_conn import ts_execute as _e
    _e(sql, params or ())

def load_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 5000):
    rows = ts_query(
        "SELECT ts, open, high, low, close, volume FROM klines "
        "WHERE symbol=%s AND interval=%s ORDER BY ts DESC LIMIT %s",
        (symbol, interval, limit),
    )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("ts").reset_index(drop=True)
    return df

# ─────────────────────────── WebSocket 广播 ───────────────────────────

class WsHub:
    def __init__(self):
        self.conns: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def bind(self, loop):
        self.loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.conns.add(ws)

    def disconnect(self, ws: WebSocket):
        self.conns.discard(ws)

    def emit(self, event: str, data: dict):
        if not self.loop:
            return
        payload = json.dumps({"event": event, "data": data, "ts": datetime.now().isoformat()}, default=str)
        for ws in list(self.conns):
            try:
                self.loop.create_task(ws.send_text(payload))
            except Exception:
                self.conns.discard(ws)

hub = WsHub()

# ─────────────────────────── Agent 运行状态 ───────────────────────────

class AgentRuntime:
    """Agent 循环运行引擎：start 后后台线程持续执行完整决策周期"""

    def __init__(self):
        self.status = "idle"          # idle | running | paused
        self.cycle_id = 0
        self.last_decision = None
        self.started_at = None
        self.lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self.cycle_interval = 120     # 每周期间隔秒

    def start(self):
        with self.lock:
            if self.status == "running":
                return
            self.status = "running"
            self.started_at = datetime.now().isoformat()
            self._pause_event.clear()
            self._stop_event.clear()
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True, name="agent-loop")
                self._thread.start()
        logger.info("Agent 启动：决策循环已开始（每 %.0f 秒一周期）", self.cycle_interval)
        hub.emit("agent.status", self.snapshot())

    def pause(self):
        with self.lock:
            if self.status == "running":
                self.status = "paused"
                self._pause_event.set()
        logger.info("Agent 暂停：当前周期完成后挂起")
        hub.emit("agent.status", self.snapshot())

    def resume(self):
        with self.lock:
            if self.status == "paused":
                self.status = "running"
                self._pause_event.clear()
        logger.info("Agent 恢复运行")
        hub.emit("agent.status", self.snapshot())

    def record_decision(self, decision: dict, cycle_id: int):
        with self.lock:
            self.cycle_id = cycle_id
            self.last_decision = decision

    def stop(self):
        self._stop_event.set()
        self._pause_event.clear()

    def _loop(self):
        while not self._stop_event.is_set():
            # 暂停时阻塞等待
            if self._pause_event.is_set():
                self._pause_event.wait(timeout=1)
                continue
            cycle = self.cycle_id + 1
            try:
                logger.info("=" * 20 + f" Agent Cycle #{cycle} 开始 " + "=" * 20)
                result = run_decision_cycle("BTCUSDT", cycle_id=cycle)
                dec = result.get("decision", {})
                logger.info(
                    "=" * 20 + f" Cycle #{result.get('cycle_id', cycle)} 完成: "
                    f"{dec.get('action')} conf={dec.get('confidence', 0):.2f} "
                    f"size={dec.get('position_size_pct', 0):.2f} lev={dec.get('leverage', 1)} " + "=" * 20)
            except Exception as e:
                logger.error(f"Cycle #{cycle} 执行失败: {e}")
                hub.emit("alert", {"level": "error", "title": f"Agent 周期 #{cycle} 失败", "detail": str(e)})
            # 周期间隔（可被暂停/停止中断）
            for _ in range(int(self.cycle_interval)):
                if self._stop_event.is_set() or self._pause_event.is_set():
                    break
                time.sleep(1)

    def snapshot(self) -> dict:
        with self.lock:
            try:
                k = ts_query("SELECT count(*) c FROM klines") or [{"c": 0}]
                tr = pg_query("SELECT count(*) c FROM trades") or [{"c": 0}]
                dl = pg_query("SELECT count(*) c FROM decision_logs") or [{"c": 0}]
                ev = pg_query("SELECT count(*) c FROM evolution_logs") or [{"c": 0}]
            except Exception:
                k = tr = dl = ev = [{"c": 0}]
            uptime = ""
            if self.started_at:
                try:
                    secs = (datetime.now() - datetime.fromisoformat(self.started_at)).total_seconds()
                    uptime = f"{int(secs // 3600)}h{int(secs % 3600 // 60)}m"
                except Exception:
                    pass
            return {
                "status": self.status,
                "cycle_id": self.cycle_id,
                "uptime": uptime,
                "last_decision": self.last_decision,
                "stats": {
                    "klines": k[0]["c"] if k else 0,
                    "trades": tr[0]["c"] if tr else 0,
                    "decisions": dl[0]["c"] if dl else 0,
                    "evolutions": ev[0]["c"] if ev else 0,
                },
            }

runtime = AgentRuntime()

# ── 全闭环持久状态：仿真账户 + 撮合引擎 + 硬风控（P0-12）──
sim_account = Account(initial_balance=100_000, max_leverage=5.0)
matching = MatchingEngine()
liquidation = LiquidationEngine()
risk_ctrl = RiskController(min_confidence=0.4)

# 元学习器（P1-10 全局实例）
_meta_learner = None

# 瞬时记忆全局实例（P1-05：跨周期持久，决策结果回写供后续召回）
from l5_memory.instant_memory import InstantMemory  # noqa: E402
_instant_mem = InstantMemory(window_size=20)

# ─────────────────────────── 长任务管理 ───────────────────────────

class Task:
    def __init__(self, kind: str, name: str, fn, cancel_event: threading.Event = None):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.name = name
        self.fn = fn
        self.cancel_event = cancel_event or threading.Event()
        self.status = "queued"        # queued | running | done | failed | cancelled
        self.progress = 0.0           # 0-100
        self.message = "排队中"
        self.result = None
        self.error = None
        self.created_at = datetime.now().isoformat()
        self.finished_at = None

    def to_dict(self):
        return {
            "id": self.id, "kind": self.kind, "name": self.name,
            "status": self.status, "progress": round(self.progress, 1),
            "message": self.message, "error": self.error,
            "result": _jsonable(self.result) if self.result is not None else None,
            "created_at": self.created_at, "finished_at": self.finished_at,
        }

class TaskManager:
    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="wb-task")
        self.lock = threading.Lock()

    def submit(self, kind: str, name: str, fn, progress_cb=None) -> Task:
        task = Task(kind, name, fn)
        with self.lock:
            self.tasks[task.id] = task

        def _run():
            task.status = "running"
            task.message = "运行中"
            hub.emit("task.update", task.to_dict())
            try:
                task.result = fn(task)
                task.status = "done"
                task.message = "完成"
                task.progress = 100.0
            except Exception as e:
                logger.exception("task %s failed", task.id)
                task.status = "failed"
                task.error = str(e)
                task.message = "失败"
                hub.emit("alert", {"level": "error", "title": f"任务失败: {task.name}", "detail": str(e)})
            finally:
                task.finished_at = datetime.now().isoformat()
                hub.emit("task.update", task.to_dict())

        self.executor.submit(_run)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def list(self) -> list[dict]:
        with self.lock:
            return [t.to_dict() for t in sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)]

    def cancel(self, task_id: str) -> bool:
        t = self.tasks.get(task_id)
        if t and t.status in ("queued", "running"):
            t.cancel_event.set()
            t.status = "cancelled"
            t.message = "已取消"
            t.finished_at = datetime.now().isoformat()
            hub.emit("task.update", t.to_dict())
            return True
        return False

tasks_mgr = TaskManager()

# ─────────────────────────── 真实回测 / 进化辅助 ───────────────────────────

def _bars_cache():
    from l2_sandbox.environment import EnvironmentRegistry
    cache = {}

    def load(env_name: str, interval: str = "1h"):
        if env_name not in cache:
            reg = EnvironmentRegistry(config_path=str(ROOT / "config" / "config.yaml"),
                                      data_dir=str(ROOT / "data" / "raw"))
            env = reg.load(env_name, interval=interval)
            cache[env_name] = {
                "bars": list(reg.iter_bars(env)),
                "summary": reg.summary(env),
                "regime": env.regime,
            }
        return cache[env_name]

    return load

def _compile_strategy(logic_code: str):
    """
    编译基因逻辑层代码为可调用策略函数（P1-02/逻辑层进化激活）。
    安全校验：白名单 AST 节点 + 限定函数签名。
    失败返回 None（回测走 MA 兜底）。
    """
    if not logic_code or "def strategy" not in logic_code:
        return None
    # 默认代码与 MA 兜底等价 → 走向量化快速路径（避免逐 bar 损失）
    try:
        from l7_evolution.evolution_engine import DEFAULT_STRATEGY_CODE
        if logic_code.strip() == DEFAULT_STRATEGY_CODE.strip():
            return None
    except Exception:
        pass
    try:
        from l7_evolution.gene_encoder import GeneEncoder
        tree = GeneEncoder.encode(logic_code)
        if tree is None:
            return None
        ns: dict = {}
        exec(compile(tree, "<gene>", "exec"), ns)
        fn = ns.get("strategy")
        if fn is None or not callable(fn):
            return None
        # 探针调用：验证签名兼容（6 个位置参数）
        try:
            fn(1.0, 1.0, 1.0, 1.0, 1.0, "trend_up")
        except TypeError:
            return None
        return fn
    except Exception as e:
        logger.warning(f"strategy 编译失败，走 MA 兜底: {e}")
        return None


def _backtest_ma_vectorized(closes, vols, short, long, vol_th, commission):
    """MA 交叉策略向量化回测（P2-06：numpy 批量计算）"""
    import numpy as np
    closes = np.asarray(closes, dtype=float)
    vols = np.asarray(vols, dtype=float)
    n = len(closes)
    if n < long + 2:
        return -1.0
    s = pd.Series(closes)
    ma_s = s.rolling(short).mean().values
    ma_l = s.rolling(long).mean().values
    vol_std = s.rolling(short).std().values
    vol_ratio = vols / (vol_std + 1e-9)

    sig = np.where(ma_s > ma_l, 1.0, -1.0)
    valid = (vol_ratio > vol_th) & ~np.isnan(ma_s) & ~np.isnan(ma_l)
    cand = np.where(valid, sig, np.nan)
    pos = pd.Series(cand).ffill().fillna(0.0).values  # 条件不满足时保持前仓位

    idx = np.arange(long, n - 1)
    rets = pos[idx] * (closes[idx + 1] / closes[idx] - 1.0)
    rets = np.where(pos[idx] != 0, rets - commission, rets)
    if rets.size == 0:
        return 0.0
    return float(np.prod(1.0 + rets) - 1.0)


def backtest_gene(gene, envs=("bull", "bear", "range", "extreme"), interval="1h") -> dict[str, float]:
    """
    真实数据回测策略基因：
    - 逻辑层：执行 gene.logic_code 的 strategy()（若可编译）
    - 参数层：ma_short_window / ma_long_window / vol_threshold 等
    - 兜底：logic_code 无效时用 MA 交叉信号
    """
    from l1_env_base import matching_engine  # noqa: F401  确保撮合模块可导入
    from l7_evolution.evolution_engine import StrategyGene

    p = gene.params
    short, long = int(p.get("ma_short_window", 20)), int(p.get("ma_long_window", 60))
    vol_th = float(p.get("vol_threshold", 1.0))
    commission = float(_cfg_value("matching.commission", 0.0004))
    strat_fn = _compile_strategy(getattr(gene, "logic_code", ""))

    load = _bars_cache()
    perf = {}
    for env in envs:
        data = load(env, interval)
        bars = data["bars"]
        regime = data.get("regime", env)
        closes = [b["c"] for b in bars]
        if len(closes) < long + 2:
            perf[env] = -1.0
            continue
        # P2-06 向量化：无自定义策略函数时走 numpy 快速路径
        if strat_fn is None:
            vols = [float(b.get("v", 0) or 0) for b in bars]
            perf[env] = _backtest_ma_vectorized(closes, vols, short, long, vol_th, commission)
            continue
        s = pd.Series(closes)
        ma_s = s.rolling(short).mean()
        ma_l = s.rolling(long).mean()
        vol_series = s.pct_change().rolling(20).std() * (365 * 24) ** 0.5
        equity = 1.0
        pos = 0  # 1 long / -1 short / 0 flat
        for i in range(long, len(bars) - 1):
            if pd.isna(ma_s.iloc[i]) or pd.isna(ma_l.iloc[i]):
                continue
            price = closes[i]
            ma_short_v, ma_long_v = float(ma_s.iloc[i]), float(ma_l.iloc[i])
            vol = float(bars[i].get("v", 0) or 0)
            vol_ratio = vol / (float(s.rolling(short).std().iloc[i]) + 1e-9) if not pd.isna(s.rolling(short).std().iloc[i]) else 1.0
            volatility = float(vol_series.iloc[i]) if not pd.isna(vol_series.iloc[i]) else 0.0

            # 逻辑层执行（优先）→ 否则 MA 兜底
            if strat_fn is not None:
                try:
                    out = strat_fn(price, ma_short_v, ma_long_v, volatility, vol_ratio, regime)
                    action = out[0] if isinstance(out, (tuple, list)) else out
                    action = str(action).lower() if action else "hold"
                except Exception:
                    action = "hold"
                sig = 1 if action == "long" else (-1 if action == "short" else 0)
            else:
                sig = 1 if ma_short_v > ma_long_v else -1
            if vol_ratio > vol_th and sig != 0:
                pos = sig
            elif sig == 0:
                pos = 0
            ret = pos * (closes[i + 1] / closes[i] - 1)
            if pos != 0:
                ret -= commission
            equity *= (1 + ret)
        perf[env] = equity - 1.0
    return perf

def _cfg_value(path: str, default=None):
    """从 config.yaml 读取点分路径配置（兜底默认值）"""
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
        node = cfg
        for part in path.split("."):
            node = node[part]
        return node
    except Exception:
        return default

def make_env_perf_func(progress_cb=None, cancel_event=None, total=None):
    def env_perf_func(gene):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("cancelled")
        return backtest_gene(gene)
    return env_perf_func

# ─────────────────────────── 感知 / 决策真实调用 ───────────────────────────

def build_real_perception(symbol: str = "BTCUSDT") -> dict:
    """从数据库真实 K 线构建三层感知切片 + 宏观"""
    from l3_perception.time_slicer import TimeSlicer, PerceptionContextBuilder

    df_5m = load_klines(symbol, "5m", 5000)
    df_1h = load_klines(symbol, "1h", 5000)
    df_1d = load_klines(symbol, "1d", 2000)
    klines_map = {}
    if not df_5m.empty: klines_map["5m"] = df_5m
    if not df_1h.empty: klines_map["1h"] = df_1h
    if not df_1d.empty: klines_map["1d"] = df_1d

    macro = {}
    try:
        for r in ts_query("SELECT indicator, value, ts FROM macro_data WHERE source='FRED' ORDER BY ts DESC LIMIT 20"):
            macro[r["indicator"]] = r["value"]
    except Exception:
        pass

    slicer = TimeSlicer()
    builder = PerceptionContextBuilder()
    # 切片时间戳用数据库最新 K 线时间（数据为历史回放，不用系统 now）
    ts = datetime.now(timezone.utc)
    for df in klines_map.values():
        if not df.empty and df["ts"].max() < ts:
            ts = df["ts"].max()
    slices = slicer.slice(ts, klines_map, macro_data=macro or None)
    # Regime 四态判定（P1-04）：趋势方向 + 波动率
    regime = "unknown"
    l2 = slices.get("L2")
    if l2 is not None:
        d = getattr(l2, "trend_direction", "neutral")
        regime = "trend_up" if d == "up" else ("trend_down" if d == "down" else "range")
    l1 = slices.get("L1")
    if l1 is not None and float(getattr(l1, "volatility", 0) or 0) > 4.0:
        regime = "high_vol"
    ctx = builder.build(slices, regime=regime, symbol=symbol)

    # P1-13 异常事件检测：闪崩 / 异常波动 / 资金费率极端 → 注入感知上下文
    try:
        from l3_perception.anomaly_detector import AnomalyDetector
        det = AnomalyDetector()
        anomalies = det.detect_all(
            kline_df=df_5m if not df_5m.empty else None,
            funding_rates=ts_query(
                "SELECT rate, ts FROM funding_rates WHERE symbol=%s ORDER BY ts DESC LIMIT 1",
                (symbol,)) or [])
        if isinstance(ctx, dict):
            ctx["anomalies"] = anomalies
    except Exception as e:
        logger.warning("anomaly detection skipped: %s", e)
    return _jsonable(ctx)

def _build_case_scene(perception, result, dec_dict, current_price) -> str:
    """构建案例场景文本（供 ChromaDB 向量召回）"""
    try:
        p = perception or {}
        regime = p.get("regime", "unknown") if isinstance(p, dict) else "unknown"
        l1 = (p.get("l1_micro") or {}) if isinstance(p, dict) else {}
        l2 = (p.get("l2_meso") or {}) if isinstance(p, dict) else {}
        return (f"BTCUSDT regime={regime} price={current_price:.0f} "
                f"L1_trend={l1.get('trend', '?')} L1_pct={(l1.get('pct_change') or 0):.2%} "
                f"L2_trend={l2.get('trend', '?')} L2_pct={(l2.get('pct_change') or 0):.2%} "
                f"causal_triplets={len(result.get('causal_triplets') or [])} "
                f"bull={len((result.get('bull_debate') or {}).get('arguments') or [])} "
                f"bear={len((result.get('bear_debate') or {}).get('arguments') or [])}")
    except Exception:
        return f"BTCUSDT cycle decision action={dec_dict.get('action', 'hold')}"


def build_real_memory(symbol: str = "BTCUSDT") -> dict:
    """三层真实记忆召回（P0-10：FusionRecaller 三路融合 + 时间衰减 + 负样本加权）"""
    from l5_memory.instant_memory import InstantMemory
    from l5_memory.case_vector_store import CaseVectorStore
    from l5_memory.causal_graph_query import CausalGraphQuery
    from l5_memory.fusion_recaller import FusionRecaller

    mem = _instant_mem  # 全局瞬时记忆（跨周期持久，P1-05）
    store = CaseVectorStore(persist_path=str(ROOT / "data" / "chromadb"))
    g = CausalGraphQuery()
    g.ensure_schema()
    merged = []
    case_matches = []
    causal_paths = []
    try:
        fr = FusionRecaller(instant_memory=mem, case_store=store, causal_graph=g)
        items = fr.recall(symbol + " market regime")
        merged = [{
            "source": it.source, "content": it.content,
            "relevance": round(it.relevance, 4), "score": round(it.score, 4),
            "metadata": it.metadata,
        } for it in items]
        case_matches = [it for it in merged if it["source"] == "vector"]
        causal_paths = [it for it in merged if it["source"] == "causal_graph"]
        logger.info(f"融合召回: {len(merged)} 条 (vector={len(case_matches)} causal={len(causal_paths)} instant={len(merged)-len(case_matches)-len(causal_paths)})")
    except Exception as e:
        logger.warning(f"融合召回降级: {e}")
    memory = {
        "case_matches": case_matches,
        "causal_paths": causal_paths,
        "instant_context": [f"{e.action} pnl={e.pnl}" for e in mem.get_recent(5)],
        "merged": merged,
    }
    g.close()
    return memory

def run_decision_cycle(symbol: str = "BTCUSDT", cycle_id: Optional[int] = None) -> dict:
    """真实全闭环决策：感知 → 记忆 → LLM 辩论 → 决策，写入 decision_logs"""
    from l6_agent.graph_builder import DecisionPipeline
    from l5_memory.instant_memory import InstantMemoryEntry

    if cycle_id is None:
        cycle_id = runtime.cycle_id + 1
    perception = build_real_perception(symbol)
    memory = build_real_memory(symbol)

    # ── L4 工具调度层接线：Agent 感知通过工具注册表取数（P0-11，写调用日志）──
    try:
        from l4_tools.tool_registry import registry as _tr
        _tr.call("query_klines", symbol=symbol, interval="1h", limit=120)
        _tr.call("query_klines", symbol=symbol, interval="5m", limit=60)
        _tr.call("query_funding", symbol=symbol, limit=20)
        _tr.call("query_macro", limit=10)
        _tr.call("calc_indicators", symbol=symbol, interval="1h", limit=120)
        _tr.call("calc_volatility", symbol=symbol, interval="1h")
        _tr.call("query_causal_graph", symbol=symbol, depth=2)
    except Exception as e:
        logger.warning("l4 tool calls failed: %s", e)
    # 真实仿真账户快照（不再写死 98000 假账户）
    try:
        px = ts_query(
            "SELECT close FROM klines WHERE symbol=%s AND interval='5m' "
            "ORDER BY ts DESC LIMIT 1", (symbol,))
        cur_price = float(px[0]["close"]) if px else 0.0
        account = asdict(sim_account.snapshot(cur_price))
    except Exception:
        account = asdict(sim_account.snapshot(0.0))

    # ── 因果图谱激活：统计 + LLM 混合抽取，写入 Neo4j（P0-06）──
    causal_triplets = []
    try:
        from l3_perception.causal_extractor import HybridCausalExtractor
        from l5_memory.causal_graph_query import CausalGraphQuery

        extractor = HybridCausalExtractor()
        df_5m = load_klines(symbol, "5m", 1500)
        triplets = extractor.extract_all(
            perception, kline_df=df_5m if not df_5m.empty else None)
        cg = CausalGraphQuery()
        cg.ensure_schema()
        written = 0
        for t in triplets:
            try:
                cg.write_causal_triplet(
                    cause_name=t.cause_entity,
                    cause_type="Event" if any(k in t.cause_entity for k in
                                              ("price", "close", "open", "high", "low", "return", "pct")) else "Factor",
                    effect_name=t.effect_entity,
                    effect_type="Event" if any(k in t.effect_entity for k in
                                               ("price", "close", "open", "high", "low", "return", "pct")) else "Factor",
                    relation=t.relation,
                    confidence=t.confidence,
                    evidence=f"{t.source}:{t.evidence}"[:400],
                )
                written += 1
            except Exception as e:
                logger.warning("write causal triplet failed: %s", e)
        causal_triplets = [{
            "cause": t.cause_entity, "relation": t.relation, "effect": t.effect_entity,
            "confidence": t.confidence, "source": t.source, "evidence": t.evidence[:120],
        } for t in triplets]
        logger.info(f"因果图谱: 抽取 {len(triplets)} 条 / 写入 Neo4j {written} 条")
    except Exception as e:
        logger.warning("causal extraction skipped: %s", e)

    pipeline = DecisionPipeline()
    result = pipeline.run(perception, memory, account, cycle_id=cycle_id)

    dec = result.get("decision")
    dec_dict = dec.model_dump() if hasattr(dec, "model_dump") else dec

    # 写入决策日志
    try:
        pg_execute(
            "INSERT INTO decision_logs (cycle_id, symbol, action, confidence, position_size, "
            "debate_json, falsification_json, counterfactual_json, reasoning_chain, ts) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            (cycle_id, symbol, dec_dict.get("action", "hold"), dec_dict.get("confidence", 0),
             dec_dict.get("position_size_pct", 0),
             json.dumps(result.get("bull_debate", {}), default=str),
             json.dumps(result.get("falsification", {}), default=str),
             json.dumps(result.get("counterfactual", {}), default=str),
             dec_dict.get("reasoning", "")[:2000]),
        )
    except Exception as e:
        logger.warning("write decision_logs failed: %s", e)

    # ── 全闭环执行：硬风控 → 下单 → 撮合 → 持仓/平仓（P0-12）──
    exec_note = "hold 无操作"
    try:
        ts = datetime.now(timezone.utc)
        rows = ts_query(
            "SELECT ts, open, high, low, close, volume FROM klines "
            "WHERE symbol=%s AND interval='5m' ORDER BY ts DESC LIMIT 1", (symbol,))
        if rows:
            r = rows[0]
            current_price = float(r["close"])
            kline = {"o": float(r["open"]), "h": float(r["high"]),
                     "l": float(r["low"]), "c": float(r["close"]), "v": float(r["volume"])}
        else:
            current_price, kline = 0.0, {}

        action = dec_dict.get("action", "hold")
        confidence = float(dec_dict.get("confidence", 0) or 0)
        pos = sim_account.positions.get(symbol)

        # P1-04 Regime 自适应：按市场状态调整仓位/杠杆/门槛
        regime = perception.get("regime", "unknown") if isinstance(perception, dict) else "unknown"
        try:
            from l6_agent.regime_adapter import RegimeAdapter
            adj = RegimeAdapter().adjust(
                regime, float(dec_dict.get("position_size_pct", 0) or 0),
                float(dec_dict.get("leverage", 1) or 1), confidence)
            if adj["gated"] or adj["position_pct"] <= 0:
                action = "hold"  # 门槛降级
            dec_dict["position_size_pct"] = adj["position_pct"]
            dec_dict["leverage"] = adj["leverage"]
            dec_dict["regime_mode"] = adj["mode"]
        except Exception as e:
            logger.warning(f"regime adapt skipped: {e}")

        if kline and current_price > 0 and action in ("long", "short") and confidence >= risk_ctrl.min_confidence:
            side = OrderSide.LONG if action == "long" else OrderSide.SHORT
            size_usd = sim_account.balance * float(dec_dict.get("position_size_pct", 0.2) or 0)
            size_units = size_usd / current_price  # USDT → 合约张数（币本位）
            lev = min(float(dec_dict.get("leverage", 1) or 1), sim_account.max_leverage)
            risk = risk_ctrl.check(sim_account, symbol, side, size_units, current_price, lev, confidence)
            if risk.allowed and size_usd > 0:
                order = OrderRequest(symbol=symbol, side=side, order_type=OrderType.MARKET,
                                     size=size_units, leverage=lev, timestamp=ts)
                fill = matching.match_market(order, kline, current_price)
                if fill.filled:
                    sim_account.open_position(symbol, side, fill.fill_size, fill.fill_price,
                                              lev, fee=fill.fee, timestamp=ts)
                    pg_execute(
                        "INSERT INTO trades (cycle_id, symbol, side, entry_price, size, leverage, entry_ts) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (cycle_id, symbol, side.value, fill.fill_price, fill.fill_size, lev, ts))
                    exec_note = (f"开仓 {side.value} {fill.fill_size:.4f} @ {fill.fill_price:.1f} "
                                 f"(滑点 {fill.slippage_pct:.4f}, 手续费 {fill.fee:.2f})")
                    logger.info(f"撮合成交: {exec_note}")
            else:
                exec_note = f"风控拒绝: {risk.reject_reason}"

        elif kline and current_price > 0 and pos:
            # 已有持仓：先检查爆仓，再处理反向/平仓信号
            liq = liquidation.check(sim_account.balance, pos.size, pos.entry_price,
                                    pos.leverage, current_price, pos.side)
            if liq.get("liquidated"):
                trade = sim_account.close_position(symbol, liq["liquidation_price"], 0.0,
                                                   timestamp=ts, reason="liquidation")
                pg_execute(
                    "UPDATE trades SET exit_price=%s, exit_ts=%s, pnl=%s WHERE symbol=%s AND exit_ts IS NULL",
                    (trade.exit_price, ts, trade.pnl, symbol))
                exec_note = f"爆仓强平 @ {trade.exit_price:.1f} pnl={trade.pnl:.2f}"
                logger.warning(f"爆仓强平: {exec_note}")
            elif action == "close" or (action in ("long", "short") and action != pos.side.value):
                close_side = OrderSide.SHORT if pos.side == OrderSide.LONG else OrderSide.LONG
                fill = matching.match_market(
                    OrderRequest(symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                                 size=pos.size, timestamp=ts), kline, current_price)
                trade = sim_account.close_position(symbol, fill.fill_price, fill.fee,
                                                   timestamp=ts, reason="decision-close")
                pg_execute(
                    "UPDATE trades SET exit_price=%s, exit_ts=%s, pnl=%s WHERE symbol=%s AND exit_ts IS NULL",
                    (trade.exit_price, ts, trade.pnl, symbol))
                exec_note = (f"平仓 {trade.exit_price:.1f} pnl={trade.pnl:.2f} "
                             f"fees={trade.fee:.2f} reason={trade.exit_reason}")
                logger.info(f"撮合平仓: {exec_note}")

        # 持仓市值重估（含浮盈浮亏）
        pos = sim_account.positions.get(symbol)
        if pos and current_price > 0:
            equity = sim_account.equity(current_price)
            exec_note += f" | 持仓浮盈 {pos.unrealized_pnl(current_price):.2f} 账户权益 {equity:.0f}"
    except Exception as e:
        logger.warning("execution chain failed: %s", e)
        exec_note = f"执行链路异常: {e}"

    # 复盘记录（trade 级）：写入 replay_reports（P1-05）
    try:
        review = {
            "cycle_id": cycle_id, "action": dec_dict.get("action"),
            "confidence": float(dec_dict.get("confidence", 0) or 0),
            "execution": exec_note,
            "balance": round(sim_account.balance, 2),
            "total_realized_pnl": round(sim_account.total_realized_pnl, 2),
            "open_positions": {k: {"side": v.side.value, "size": v.size,
                                   "entry": v.entry_price, "lev": v.leverage}
                               for k, v in sim_account.positions.items()},
        }
        pg_execute(
            "INSERT INTO replay_reports (level, cycle_id, report_json) VALUES ('trade', %s, %s)",
            (cycle_id, json.dumps(review, default=str)))
        # P1-05 记忆回写：决策结果写入瞬时记忆（供后续周期召回）
        try:
            _instant_mem.push(InstantMemoryEntry(
                timestamp=ts, cycle_id=cycle_id, price=current_price if current_price > 0 else 0.0,
                action=str(dec_dict.get("action", "hold")),
                confidence=float(dec_dict.get("confidence", 0) or 0),
                pnl=sim_account.total_realized_pnl,
                regime=perception.get("regime", "unknown") if isinstance(perception, dict) else "unknown",
                summary=exec_note,
            ))
        except Exception as e:
            logger.warning(f"instant memory push failed: {e}")

        # 案例向量记忆（ChromaDB 增量学习）：每周期存入一个案例供相似场景召回
        try:
            from l5_memory.case_vector_store import CaseVectorStore, CaseRecord
            _case_store = CaseVectorStore(persist_path=str(ROOT / "data" / "chromadb"))
            scene = _build_case_scene(perception, result, dec_dict, current_price)
            _case_store.store(CaseRecord(
                case_id=f"cycle-{cycle_id}",
                scene_summary=scene,
                action=str(dec_dict.get("action", "hold")),
                confidence=float(dec_dict.get("confidence", 0) or 0),
                pnl_pct=sim_account.total_realized_pnl / sim_account.initial_balance,
                regime=perception.get("regime", "unknown") if isinstance(perception, dict) else "unknown",
                timestamp=ts,
                metadata={"cycle_id": cycle_id, "execution": exec_note[:200]},
            ))
        except Exception as e:
            logger.warning(f"case vector store failed: {e}")
    except Exception as e:
        logger.warning("write replay_reports failed: %s", e)

    runtime.record_decision(dec_dict, cycle_id)
    hub.emit("agent.decision", {"cycle_id": cycle_id, "action": dec_dict.get("action"),
                                "confidence": dec_dict.get("confidence", 0)})
    return {
        "cycle_id": cycle_id,
        "perception": perception,
        "causal_triplets": causal_triplets,
        "bull_debate": result.get("bull_debate"),
        "bear_debate": result.get("bear_debate"),
        "falsification": result.get("falsification"),
        "counterfactual": result.get("counterfactual"),
        "decision": dec_dict,
    }

# ─────────────────────────── 任务执行体（采集/导入/进化） ───────────────────────────

def task_collect(symbol: str, intervals: list[str], force: bool = False):
    def fn(task: Task):
        collector = MultiExchangeCollector(data_dir=str(ROOT / "data" / "raw"))
        total = 0
        n = len(intervals)
        for i, interval in enumerate(intervals):
            if task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            task.message = f"采集 {symbol} {interval}"
            task.progress = i / n * 80
            hub.emit("task.update", task.to_dict())
            try:
                df = collector.download_klines(symbol=symbol, interval=interval, force=force)
                if not df.empty:
                    total += len(df)
            except Exception as e:
                logger.warning("collect %s %s: %s", symbol, interval, e)
        # 资金费率
        try:
            task.message = f"采集 {symbol} 资金费率"
            task.progress = 85
            hub.emit("task.update", task.to_dict())
            df = collector.download_funding_rates(symbol=symbol, force=force)
            if not df.empty:
                total += len(df)
        except Exception as e:
            logger.warning("funding: %s", e)
        return {"total_rows": total, "symbol": symbol, "intervals": intervals}

    return tasks_mgr.submit("collect", f"采集 {symbol}", fn)


def task_collect_incremental(symbol: str = "BTCUSDT", intervals: list[str] | None = None):
    """实时增量采集：从数据库最新时间戳 → now，新数据直接写入 TimescaleDB"""
    if intervals is None:
        intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]

    def fn(task: Task):
        from l1_env_base.data_loader import import_klines_df

        collector = MultiExchangeCollector(data_dir=str(ROOT / "data" / "raw"))
        added = {}
        n = len(intervals)
        for i, interval in enumerate(intervals):
            if task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            task.message = f"增量采集 {symbol} {interval}"
            task.progress = i / n * 100
            hub.emit("task.update", task.to_dict())
            try:
                # 数据库该周期最新时间戳
                rows = ts_query(
                    "SELECT max(ts) m FROM klines WHERE symbol=%s AND interval=%s",
                    (symbol, interval))
                last_ts = rows[0]["m"] if rows and rows[0].get("m") else None
                since = None
                if last_ts is not None:
                    since = (last_ts - timedelta(days=1)).strftime("%Y-%m-%d")  # 重叠 1 天兜底
                df = collector.download_klines_incremental(
                    symbol=symbol, interval=interval, since=since)
                if df.empty:
                    added[interval] = 0
                    continue
                # 去重：过滤已存在时间戳（重叠兜底区间）
                if last_ts is not None:
                    df = df[df["ts"] > last_ts]
                n_added = import_klines_df(df, symbol=symbol, interval=interval)
                added[interval] = n_added
                if n_added:
                    logger.info("增量入库 %s %s: +%d 条", symbol, interval, n_added)
            except Exception as e:
                logger.warning("增量采集 %s %s 失败: %s", symbol, interval, e)
                added[interval] = -1
        hub.emit("db.updated", {"ts": datetime.now().isoformat(), "added": added})
        return {"added": added, "symbol": symbol}

    return tasks_mgr.submit("collect_incremental", f"增量采集 {symbol}", fn)

def task_import_parquet():
    def fn(task: Task):
        task.message = "导入 parquet → TimescaleDB"
        task.progress = 5
        hub.emit("task.update", task.to_dict())
        # 复用 data_loader 的核心函数（在子线程中运行）
        from l1_env_base import data_loader
        k = data_loader.import_klines()
        f = data_loader.import_funding()
        m = data_loader.import_macro()
        hub.emit("db.updated", {"ts": datetime.now().isoformat()})
        return {"klines": k, "funding": f, "macro": m}

    return tasks_mgr.submit("import", "导入数据", fn)

def task_evolution(generations: int, population_size: int, params: dict):
    cancel_event = threading.Event()
    experiment_id = uuid.uuid4().hex[:8]  # P2-07 实验版本号

    def fn(task: Task):
        from l7_evolution.evolution_engine import EvolutionEngine

        engine = EvolutionEngine(
            population_size=population_size,
            generations=generations,
            crossover_rate=float(params.get("crossover_rate", 0.7)),
            mutation_rate=float(params.get("mutation_rate", 0.2)),
            tournament_size=int(params.get("tournament_size", 3)),
            elitism_count=int(params.get("elitism_count", 2)),
            generalization_weight=float(params.get("generalization_weight", 0.3)),
        )
        engine.init_population()

        def env_perf_func(gene):
            if cancel_event.is_set() or task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            return backtest_gene(gene)

        history = []
        for gen in range(generations):
            if cancel_event.is_set() or task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            engine.evaluate_population(env_perf_func)
            best = engine.population[0]
            engine.history.append({
                "generation": gen,
                "best_fitness": best.fitness,
                "avg_fitness": float(pd.Series([g.fitness for g in engine.population]).mean()),
                "best_params": best.params,
                "env_performances": best.env_performances,
            })
            task.progress = (gen + 1) / generations * 100
            task.message = f"进化 第 {gen + 1}/{generations} 代 best={best.fitness:.4f}"
            hub.emit("task.update", task.to_dict())
            hub.emit("evolution.generation", {
                "generation": gen,
                "best_fitness": best.fitness,
                "avg_fitness": engine.history[-1]["avg_fitness"],
            })
            # P2-03 每代记录全种群（含父代关系，供进化树）
            try:
                for g in engine.population:
                    try:
                        parents = json.dumps(getattr(g, "parent_ids", []))
                    except Exception:
                        parents = None
                    pg_execute(
                        "INSERT INTO evolution_logs (generation, gene_id, gene_params, gene_code, fitness, experiment_id, parent_gene_ids) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (gen, g.id, json.dumps(g.params),
                         getattr(g, "logic_code", None) or "", float(g.fitness or 0),
                         experiment_id, parents))
            except Exception as e:
                logger.warning(f"population log: {e}")
            if gen < generations - 1:
                engine.evolve_generation()

        # 记录进化日志（best 摘要，P2-07 版本管理）
        try:
            for h in engine.history:
                pg_execute(
                    "INSERT INTO evolution_logs (generation, gene_id, gene_params, gene_code, fitness, experiment_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (h["generation"], "best", json.dumps(h["best_params"]),
                     engine.best_gene.logic_code if engine.best_gene else None,
                     h["best_fitness"], experiment_id),
                )
            # P1-05 世代级复盘：写入 replay_reports（level=generation）
            from l7_evolution.replay_engines import ReplayEngines
            rp = ReplayEngines()
            for h in engine.history:
                rep = rp.generation_replay(
                    h["generation"], h["best_fitness"], h["avg_fitness"], population_size)
                pg_execute(
                    "INSERT INTO replay_reports (level, generation, report_json) "
                    "VALUES ('generation', %s, %s)",
                    (h["generation"], json.dumps(rep.metrics, default=str)))
            # P1-05 策略级复盘：best 基因 + 最近交易
            try:
                trades_rows = pg_query(
                    "SELECT side, entry_price, exit_price, pnl FROM trades "
                    "WHERE exit_ts IS NOT NULL ORDER BY exit_ts DESC LIMIT 20")
                if trades_rows and engine.best_gene is not None:
                    rep_s = rp.strategy_replay(engine.best_gene, trades_rows)
                    pg_execute(
                        "INSERT INTO replay_reports (level, gene_id, report_json) "
                        "VALUES ('strategy', %s, %s)",
                        (engine.best_gene.id, json.dumps(rep_s.metrics, default=str)))
            except Exception as e:
                logger.warning(f"strategy replay: {e}")
        except Exception as e:
            logger.warning("evolution_logs: %s", e)

        return {
            "generations": generations,
            "history": engine.history,
            "best": {"fitness": engine.best_gene.fitness if engine.best_gene else None,
                     "params": engine.best_gene.params if engine.best_gene else None,
                     "env_performances": engine.best_gene.env_performances if engine.best_gene else None},
        }

    task = tasks_mgr.submit("evolution", f"进化 {generations} 代", fn)
    task.cancel_event = cancel_event
    return task


def task_hpo(n_trials: int, params: dict):
    """Auto-HPO 后台任务：Optuna 参数层贝叶斯搜索"""
    cancel_event = threading.Event()

    def fn(task: Task):
        from l7_evolution.auto_hpo import AutoHPO

        hpo = AutoHPO(
            n_trials=n_trials,
            envs=tuple(params.get("envs", ["bull", "bear", "range", "extreme"])),
            interval=params.get("interval", "1h"),
            timeout_seconds=int(params.get("timeout_seconds", 0)),
        )

        def progress_cb(done, total, best):
            task.progress = done / total * 100
            task.message = f"HPO 搜索 {done}/{total} trial best={best:.4f}"
            hub.emit("task.update", task.to_dict())
            if cancel_event.is_set() or task.cancel_event.is_set():
                raise InterruptedError("cancelled")

        result = hpo.run(progress_cb=progress_cb, cancel_event=lambda: (
            cancel_event.is_set() or task.cancel_event.is_set()) or None)
        # 记录 HPO 结果到进化日志（generation=-1 标记）
        try:
            pg_execute(
                "INSERT INTO evolution_logs (generation, gene_id, gene_params, fitness) "
                "VALUES (-1, 'hpo-best', %s, %s)",
                (json.dumps(result["best_params"]), result["best_score"]))
        except Exception as e:
            logger.warning("hpo log: %s", e)
        return result

    task = tasks_mgr.submit("hpo", f"Auto-HPO {n_trials} trials", fn)
    task.cancel_event = cancel_event
    return task

# ─────────────────────────── API 请求模型 ───────────────────────────

class DecisionRun(BaseModel):
    symbol: str = "BTCUSDT"

class BacktestRun(BaseModel):
    env: str = "bull"
    interval: str = "1h"
    gene_code: Optional[str] = None
    params: dict = {}

class EvolutionStart(BaseModel):
    generations: int = 5
    population_size: int = 8
    crossover_rate: float = 0.7
    mutation_rate: float = 0.2
    tournament_size: int = 3
    elitism_count: int = 2

class ConfigUpdate(BaseModel):
    data: dict = {}

class TaskCreate(BaseModel):
    kind: str = "collect"      # collect | import | decision | backtest | evolution
    name: str = ""
    interval_seconds: int = 0  # 0 = 一次性
    params: dict = {}

# ─────────────────────────── 路由 ───────────────────────────

@app.get("/api/logs")
def api_logs(limit: int = 200, level: str = "ALL"):
    """最近日志（环形缓冲）：?limit=200&level=ERROR"""
    items = list(log_buffer)
    if level != "ALL":
        items = [x for x in items if x["level"] == level]
    return {"logs": items[-limit:]}

@app.get("/api/health")
def api_health():
    """系统完整性体检：数据库 / 数据新鲜度 / 任务 / 各层模块"""
    from dashboard_stats import get_db_stats
    db = get_db_stats()

    # 数据新鲜度
    try:
        rows = ts_query(
            "SELECT interval, max(ts) m FROM klines WHERE symbol='BTCUSDT' GROUP BY interval")
        freshness = {}
        now = datetime.now(timezone.utc)
        for r in rows:
            lt = r.get("m")
            if lt is None:
                continue
            if isinstance(lt, str):
                lt = datetime.fromisoformat(lt.replace("Z", "+00:00"))
            freshness[r["interval"]] = round(max((now - lt).total_seconds() / 60, 0), 1)
    except Exception:
        freshness = {}

    # 各层模块完整性
    import importlib
    layers = {}
    for lid, mod in [("L1", "l1_env_base"), ("L2", "l2_sandbox"), ("L3", "l3_perception"),
                     ("L4", "l4_tools"), ("L5", "l5_memory"), ("L6", "l6_agent"), ("L7", "l7_evolution")]:
        try:
            importlib.import_module(mod)
            layers[lid] = "ok"
        except Exception as e:
            layers[lid] = f"fail: {e}"

    return {
        "status": "healthy",
        "ts": datetime.now().isoformat(),
        "components": {
            "databases": {
                "timescaledb": {"ok": db["timescale"]["hypertables"] > 0, "klines": db["timescale"]["klines"]},
                "neo4j": {"ok": db["neo4j"]["connected"], "nodes": db["neo4j"]["nodes"]},
                "redis": {"ok": db["redis"]["connected"]},
                "chromadb": {"ok": db["chromadb"]["connected"], "cases": db["chromadb"]["cases"]},
            },
            "layers": layers,
            "data_freshness_minutes": freshness,
            "agent": runtime.snapshot(),
            "tasks": {"background": len(tasks_mgr.tasks), "running": sum(1 for t in tasks_mgr.tasks.values() if t.status == "running"),
                      "scheduled": len(_scheduled)},
            "websocket_clients": len(hub.conns),
        },
        "log_count": len(log_buffer),
    }

@app.get("/api/agent/status")
def api_agent_status():
    snap = runtime.snapshot()
    try:
        rows = pg_query(
            "SELECT cycle_id, symbol, action, confidence, position_size, ts "
            "FROM decision_logs ORDER BY cycle_id DESC LIMIT 10")
        snap["recent_decisions"] = rows
    except Exception:
        snap["recent_decisions"] = []
    return {"state": snap, "ts": datetime.now().isoformat()}

@app.post("/api/agent/start")
def api_agent_start():
    runtime.start()
    hub.emit("agent.status", runtime.snapshot())
    return {"ok": True, "status": runtime.status}

@app.post("/api/agent/pause")
def api_agent_pause():
    runtime.pause()
    hub.emit("agent.status", runtime.snapshot())
    return {"ok": True, "status": runtime.status}

@app.post("/api/agent/resume")
def api_agent_resume():
    runtime.resume()
    hub.emit("agent.status", runtime.snapshot())
    return {"ok": True, "status": runtime.status}

@app.get("/api/db")
def api_db():
    from dashboard_stats import get_db_stats
    return {"db": get_db_stats(), "ts": datetime.now().isoformat()}

@app.post("/api/tools/plan")
def api_tools_plan(body: dict = None):
    """工具规划器（P1-07）：LLM 规划工具序列并执行"""
    from l4_tools.planner import ToolPlanner
    from l4_tools.tool_registry import registry as _tr

    body = body or {}
    task = body.get("task", "")
    if not task:
        return {"ok": False, "error": "缺少 task"}
    planner = ToolPlanner(_tr)
    try:
        r = planner.plan_and_execute(task, decision_passed=bool(body.get("decision_passed", False)))
        return {"ok": True, **r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/tools")
def api_tools_list():
    """工具注册表：三级权限列表 + 调用日志"""
    from l4_tools.tool_registry import registry as _tr
    return {"tools": _tr.list_tools(), "call_log": _tr.call_log_since(30)}


@app.post("/api/tools/call")
def api_tools_call(body: dict):
    """调度工具：ACT 需 decision_passed=True 门禁"""
    from l4_tools.tool_registry import ToolCallDenied, registry as _tr
    name = body.get("name", "")
    decision_passed = bool(body.get("decision_passed", False))
    kwargs = body.get("kwargs", {}) or {}
    try:
        result = _tr.call(name, decision_passed=decision_passed, **kwargs)
        return {"ok": True, "name": name, "result": result}
    except ToolCallDenied as e:
        return {"ok": False, "name": name, "denied": str(e)}
    except Exception as e:
        return {"ok": False, "name": name, "error": str(e)}


@app.get("/api/architecture")
def api_architecture():
    """七层架构 + 数据库：状态基于 /api/health 真实组件，不再写死"""
    from dashboard_stats import get_db_stats
    db = get_db_stats()
    pg_ok = db["timescale"]["hypertables"] > 0 or db["pg"]["tables"]
    n4 = db["neo4j"]["connected"]
    rd = db["redis"]["connected"]
    ch = db["chromadb"]["connected"]
    layer_status = {
        "L1": "online" if pg_ok else "offline",
        "L2": "online" if pg_ok else "offline",
        "L3": "online" if pg_ok else "offline",
        "L4": "online" if pg_ok else "offline",
        "L5": "online" if (n4 or ch) else "offline",
        "L6": "active" if runtime.status in ("running", "paused") else "idle",
        "L7": "online" if pg_ok else "offline",
    }
    return {
        "layers": [
            {"id": "L1", "cn": "环境底座层", "status": layer_status["L1"], "desc": "多交易所数据采集 · 本地撮合仿真 · 账户系统 · 硬风控"},
            {"id": "L2", "cn": "仿真沙箱层", "status": layer_status["L2"], "desc": "牛市 · 熊市 · 震荡 · 极端波动 四环境沙箱"},
            {"id": "L3", "cn": "因果感知层", "status": layer_status["L3"], "desc": "L1/L2/L3 三时序切片 · LLM因果抽取 · 统计因果发现"},
            {"id": "L4", "cn": "工具调度层", "status": layer_status["L4"], "desc": "只读 · 计算 · 动作 三级权限工具调度"},
            {"id": "L5", "cn": "三层复合记忆", "status": layer_status["L5"], "desc": "滑动窗口瞬时记忆 · ChromaDB向量记忆 · Neo4j因果图谱记忆"},
            {"id": "L6", "cn": "辩论多Agent决策", "status": layer_status["L6"], "desc": "多空辩论 → 证伪校验 → 反事实推演 → 置信度仓位决策"},
            {"id": "L7", "cn": "元进化控制层", "status": layer_status["L7"], "desc": "Python AST 双层基因 · DEAP 遗传进化 · 三级复盘"},
        ],
        "databases": [
            {"name": "TimescaleDB PG17", "icon": "TS", "port": "5433", "hypertables": db["timescale"]["hypertables"], "status": "connected" if pg_ok else "offline", "klines": db["timescale"]["klines"]},
            {"name": "Neo4j 5", "icon": "N4", "port": "7687", "status": "connected" if n4 else "offline", "nodes": db["neo4j"]["nodes"]},
            {"name": "Redis 7", "icon": "RD", "port": "6379", "status": "connected" if rd else "offline"},
            {"name": "ChromaDB", "icon": "CH", "type": "embedded", "status": "connected" if ch else "offline", "cases": db["chromadb"]["cases"]},
        ],
    }

@app.get("/api/klines")
def api_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 2000):
    df = load_klines(symbol, interval, limit)
    if df.empty:
        return {"symbol": symbol, "interval": interval, "rows": 0, "data": []}
    return {
        "symbol": symbol, "interval": interval, "rows": len(df),
        "data": df.to_dict(orient="records"),
    }

@app.get("/api/data/sources")
def api_data_sources():
    collector = MultiExchangeCollector(data_dir=str(ROOT / "data" / "raw"))
    files = sorted(p.name for p in (ROOT / "data" / "raw").glob("*.parquet"))
    return {"exchanges": collector.available_exchanges, "parquet_files": files}

@app.post("/api/data/collect")
def api_data_collect(body: dict):
    symbol = body.get("symbol", "BTCUSDT")
    intervals = body.get("intervals", ["1h", "4h", "1d"])
    force = body.get("force", False)
    incremental = body.get("incremental", False)
    if incremental:
        task = task_collect_incremental(symbol, intervals)
    else:
        task = task_collect(symbol, intervals, force)
    return {"task_id": task.id, "task": task.to_dict()}

@app.get("/api/data/latest")
def api_data_latest(symbol: str = "BTCUSDT"):
    """各周期数据新鲜度：最新时间戳 + 距现在分钟数"""
    rows = ts_query(
        "SELECT interval, max(ts) latest_ts, count(*) c FROM klines "
        "WHERE symbol=%s GROUP BY interval ORDER BY interval",
        (symbol,))
    now = datetime.now(timezone.utc)
    result = {}
    for r in rows:
        lt = r.get("latest_ts")
        if lt is None:
            continue
        if isinstance(lt, str):
            lt = datetime.fromisoformat(lt.replace("Z", "+00:00"))
        age_min = max((now - lt).total_seconds() / 60, 0)
        result[r["interval"]] = {
            "latest_ts": lt.isoformat(),
            "age_minutes": round(age_min, 1),
            "count": r["c"],
        }
    return {"symbol": symbol, "freshness": result, "server_now": now.isoformat()}

@app.post("/api/data/import")
def api_data_import():
    task = task_import_parquet()
    return {"task_id": task.id, "task": task.to_dict()}

@app.get("/api/perception/graph-evolution")
def api_perception_graph_evolution(buckets: int = 6):
    """因果图谱演化（P2-08）：按关系更新时间切片 → 演化序列"""
    try:
        from l5_memory.causal_graph_query import CausalGraphQuery
        cg = CausalGraphQuery()
        with cg.driver.session() as s:
            rows = s.run(
                "MATCH (c:Event)-[r:CAUSES]->(e:Event) "
                "RETURN c.id AS cause, e.id AS effect, r.relation AS rel, "
                "r.confidence AS conf, r.updated AS updated").data()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    dated = []
    for r in rows:
        upd = r.get("updated")
        ts = upd.isoformat() if upd is not None else ""
        dated.append({"cause": r["cause"], "effect": r["effect"],
                      "relation": r.get("rel", ""), "confidence": float(r.get("conf", 0) or 0),
                      "ts": ts})

    if not dated:
        return {"ok": True, "evolution": [], "total": 0}

    # 按时间排序后均分桶
    dated.sort(key=lambda d: d["ts"])
    n = max(1, buckets)
    size = max(1, -(-len(dated) // n))
    evolution = []
    for i in range(0, len(dated), size):
        chunk = dated[i:i + size]
        evolution.append({
            "ts": chunk[-1]["ts"] or f"step{i // size + 1}",
            "step": len(evolution) + 1,
            "triplets": chunk,
        })
    return {"ok": True, "evolution": evolution, "total": len(dated)}


@app.get("/api/regime/policy")
def api_regime_policy():
    """Regime 自适应策略表（P1-04）"""
    from l6_agent.regime_adapter import RegimeAdapter
    return {"ok": True, "policies": RegimeAdapter().describe(),
            "current_regime": "unknown"}


@app.get("/api/account/history")
def api_account_history(limit: int = 100):
    """账户权益历史（从 replay_reports trade 级提取，无需新表）"""
    rows = pg_query(
        "SELECT cycle_id, report_json, created_at FROM replay_reports "
        "WHERE level='trade' ORDER BY id DESC LIMIT %s", (limit,))
    history = []
    for r in reversed(rows):
        try:
            rep = json.loads(r["report_json"]) if isinstance(r["report_json"], str) else (r["report_json"] or {})
        except Exception:
            continue
        history.append({
            "cycle_id": r["cycle_id"],
            "ts": (r.get("created_at") or "").strftime("%m-%d %H:%M") if hasattr(r.get("created_at"), "strftime") else "",
            "balance": rep.get("balance", 0),
            "pnl": rep.get("total_realized_pnl", 0),
            "execution": (rep.get("execution") or "")[:40],
        })
    return {"ok": True, "history": history}


@app.get("/api/perception/slices")
def api_perception_slices(symbol: str = "BTCUSDT"):
    try:
        return {"perception": build_real_perception(symbol)}
    except Exception as e:
        logger.exception("perception failed")
        return {"error": str(e)}

@app.get("/api/perception/granger")
def api_perception_granger(symbol: str = "BTCUSDT"):
    from l3_perception.causal_extractor import StatisticalCausalDiscovery
    df_1d = load_klines(symbol, "1d", 400)
    if df_1d.empty or len(df_1d) < 30:
        return {"error": "数据不足", "rows": len(df_1d)}
    close = df_1d.set_index("ts")["close"]
    volume = df_1d.set_index("ts")["volume"]
    ret = close.pct_change()
    disc = StatisticalCausalDiscovery()
    triplets = disc.discover(target_series=ret.dropna(), candidate_factors={"volume": volume}, max_lag=5)
    return {"triplets": [t.model_dump() if hasattr(t, "model_dump") else t for t in triplets]}

@app.get("/api/causal/graph")
def api_causal_graph():
    from l5_memory.causal_graph_query import CausalGraphQuery
    g = CausalGraphQuery()
    g.ensure_schema()
    try:
        # 直接查询全部 CAUSES 边（事件节点名是指标名，不含 BTC，按名称过滤会漏）
        with g.driver.session() as s:
            rows = s.run(
                "MATCH (c:Event)-[r:CAUSES]->(e:Event) "
                "RETURN c.name AS cause, e.name AS effect, "
                "r.relation AS relation, r.confidence AS confidence "
                "ORDER BY r.confidence DESC").data()
        triples = [{
            "source": r["cause"], "target": r["effect"],
            "relation": r.get("relation", "causes"),
            "confidence": float(r.get("confidence") or 0.5),
        } for r in rows]
    except Exception as e:
        triples = []
    finally:
        g.close()
    nodes, links = {}, []
    for t in triples:
        src = t.get("source") or "?"
        dst = t.get("target") or "?"
        rel = t.get("relation") or "causes"
        conf = t.get("confidence", 0.5)
        nodes.setdefault(src, {"id": src, "conf": 0})
        nodes.setdefault(dst, {"id": dst, "conf": 0})
        nodes[src]["conf"] = max(nodes[src]["conf"], conf)
        nodes[dst]["conf"] = max(nodes[dst]["conf"], conf)
        links.append({"source": src, "target": dst, "relation": rel, "confidence": conf})
    return {"nodes": list(nodes.values()), "links": links}

@app.get("/api/memory/recall")
def api_memory_recall(query: str = "BTCUSDT market", top_k: int = 5):
    from l5_memory.case_vector_store import CaseVectorStore
    from l5_memory.instant_memory import InstantMemory
    from l5_memory.causal_graph_query import CausalGraphQuery

    store = CaseVectorStore(persist_path=str(ROOT / "data" / "chromadb"))
    try:
        vector = store.query(query, n_results=top_k)
    except Exception as e:
        vector = [{"error": str(e)}]
    mem = InstantMemory(window_size=10)
    g = CausalGraphQuery()
    g.ensure_schema()
    try:
        causal = g.query_causal_paths("BTC", max_depth=3)
    except Exception:
        causal = []
    g.close()
    return {
        "vector": vector,
        "instant": [{"action": e.action, "pnl": e.pnl, "confidence": e.confidence, "cycle_id": e.cycle_id}
                    for e in mem.get_recent(10)],
        "causal": causal,
    }

@app.post("/api/decision/run")
def api_decision_run(body: DecisionRun):
    try:
        return run_decision_cycle(body.symbol)
    except Exception as e:
        logger.exception("decision failed")
        return {"error": str(e)}

@app.get("/api/decision/{cycle_id}")
def api_decision_detail(cycle_id: int):
    rows = pg_query(
        "SELECT cycle_id, symbol, action, confidence, position_size, debate_json, "
        "falsification_json, counterfactual_json, reasoning_chain, ts "
        "FROM decision_logs WHERE cycle_id=%s ORDER BY id DESC LIMIT 1", (cycle_id,))
    if not rows:
        return {"error": "not found"}
    r = rows[0]
    for k in ("debate_json", "falsification_json", "counterfactual_json"):
        try:
            r[k] = json.loads(r[k]) if r[k] else None
        except Exception:
            pass
    return r

@app.post("/api/backtest/run")
def api_backtest_run(body: BacktestRun):
    from l2_sandbox.environment import EnvironmentRegistry
    try:
        reg = EnvironmentRegistry(config_path=str(ROOT / "config" / "config.yaml"),
                                  data_dir=str(ROOT / "data" / "raw"))
        env = reg.load(body.env, interval=body.interval)
        summary = reg.summary(env)
        result = {"env": body.env, "summary": summary}
        if body.gene_code or body.params:
            from l7_evolution.evolution_engine import StrategyGene
            gene = StrategyGene(id="manual", logic_code=body.gene_code or "", params=body.params, generation=0)
            result["performance"] = backtest_gene(gene, envs=(body.env,), interval=body.interval)
        return result
    except Exception as e:
        logger.exception("backtest failed")
        return {"error": str(e)}

@app.get("/api/backtest/result")
def api_backtest_result(env: str = "bull"):
    from l2_sandbox.environment import EnvironmentRegistry
    try:
        reg = EnvironmentRegistry(config_path=str(ROOT / "config" / "config.yaml"),
                                  data_dir=str(ROOT / "data" / "raw"))
        env_obj = reg.load(env, interval="1h")
        return {"env": env, "summary": reg.summary(env_obj)}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/export")
def api_export(body: dict = None):
    """导出实验数据（CSV/JSON/Pickle）到 data/experiments/<ts>"""
    from experiment_exporter import export_all
    body = body or {}
    out = str(ROOT / "data" / "experiments" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    r = export_all(out, formats=tuple(body.get("formats", ["csv", "json", "pickle"])))
    return r


@app.post("/api/memory/clean")
def api_memory_clean():
    """手动触发记忆自清洗（P1-06）"""
    from l5_memory.memory_cleaner import MemoryCleaner
    try:
        r = MemoryCleaner(store_path=str(ROOT / "data" / "chromadb")).clean()
        return {"ok": True, "result": r}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def task_arena(n_genes: int, rounds: int, params: dict):
    """对抗竞技场后台任务（P1-01）"""
    cancel_event = threading.Event()

    def fn(task: Task):
        from l7_evolution.arena import Arena
        from l7_evolution.evolution_engine import EvolutionEngine, StrategyGene

        # 生成初始种群（随机参数）
        engine = EvolutionEngine(population_size=n_genes, generations=1)
        engine.init_population()
        genes = engine.population

        arena = Arena(
            envs=tuple(params.get("envs", ["bull", "bear", "range", "extreme"])),
            rounds=rounds,
            keep_top=int(params.get("keep_top", 2)),
            interval=params.get("interval", "1h"),
        )

        def progress_cb(done, total, info):
            task.progress = done / total * 100
            task.message = f"竞技场 第 {done}/{total} 轮 冠军={info.get('champion', '?')}"
            hub.emit("task.update", task.to_dict())
            if cancel_event.is_set() or task.cancel_event.is_set():
                raise InterruptedError("cancelled")

        result = arena.run(genes, progress_cb=progress_cb,
                           cancel_event=lambda: cancel_event.is_set() or task.cancel_event.is_set())
        # 记录冠军到进化日志
        try:
            if result["ranking"]:
                champ_id = result["ranking"][0]["gene_id"]
                champ = next((g for g in genes if g.id == champ_id), None)
                if champ:
                    pg_execute(
                        "INSERT INTO evolution_logs (generation, gene_id, gene_params, fitness) "
                        "VALUES (-2, %s, %s, %s)",
                        (champ.id, json.dumps(champ.params), result["ranking"][0]["score"]))
        except Exception as e:
            logger.warning("arena log: %s", e)
        return result

    task = tasks_mgr.submit("arena", f"对抗竞技场 {n_genes} 基因 × {rounds} 轮", fn)
    task.cancel_event = cancel_event
    return task


@app.post("/api/meta/train")
def api_meta_train(body: dict = None):
    """元学习训练（P1-10）：从进化日志学习环境→参数先验"""
    from l7_evolution.meta_learner import MetaLearner

    body = body or {}
    samples = MetaLearner.load_training_samples(limit=int(body.get("limit", 50)))
    m = MetaLearner(epochs=int(body.get("epochs", 200)))
    r = m.train(samples)
    if not r["trained"]:
        return {"ok": False, "error": r.get("error", "训练失败")}
    global _meta_learner
    _meta_learner = m
    return {"ok": True, **r}


@app.post("/api/meta/compare")
def api_meta_compare(body: dict = None):
    """元初始化 vs 随机初始化 真实回测对比"""
    from l7_evolution.meta_learner import MetaLearner

    body = body or {}
    global _meta_learner
    m = _meta_learner
    if m is None:
        m = MetaLearner()
        samples = MetaLearner.load_training_samples()
        if not m.train(samples).get("trained"):
            return {"ok": False, "error": "训练样本不足，先运行进化产生 fitness 记录"}
        _meta_learner = m
    r = m.compare(symbol=body.get("symbol", "BTCUSDT"),
                  interval=body.get("interval", "1h"),
                  n_random=int(body.get("n_random", 3)))
    return {"ok": "error" not in r, **r}


@app.post("/api/distill")
def api_distill(body: dict = None):
    """知识蒸馏（P1-11）：将高表现基因蒸馏为可解释规则写入知识库"""
    from l7_evolution.knowledge_distiller import KnowledgeDistiller
    from l7_evolution.evolution_engine import StrategyGene

    body = body or {}
    gene_id = body.get("gene_id", "")
    gene = None
    try:
        if gene_id:
            rows = pg_query(
                "SELECT gene_id, gene_code, gene_params FROM evolution_logs "
                "WHERE gene_id=%s AND gene_code IS NOT NULL ORDER BY id DESC LIMIT 1",
                (gene_id,))
        else:
            # 默认：蒸馏 fitness 最高的基因（无 fitness 时取最新带代码的记录）
            rows = pg_query(
                "SELECT gene_id, gene_code, gene_params, fitness FROM evolution_logs "
                "WHERE gene_code IS NOT NULL ORDER BY fitness DESC NULLS LAST, id DESC LIMIT 1")
        if rows:
            r = rows[0]
            try:
                params = json.loads(r["gene_params"]) if isinstance(r["gene_params"], str) else (r["gene_params"] or {})
            except Exception:
                params = {}
            gene = StrategyGene(id=r["gene_id"], logic_code=r["gene_code"], params=params, generation=0)
    except Exception as e:
        logger.warning("distill load gene failed: %s", e)

    if gene is None:
        return {"ok": False, "error": "没有可蒸馏的基因（需要 gene_code + fitness 记录）"}

    r = KnowledgeDistiller().distill(gene)
    if r["error"]:
        return {"ok": False, "error": r["error"]}
    KnowledgeDistiller.save_rules(r["rules"], r["gene_id"], r["fidelity"])
    return {"ok": True, "gene_id": r["gene_id"], "fidelity": round(r["fidelity"], 3),
            "rules": r["rules"]}


@app.get("/api/knowledge/rules")
def api_knowledge_rules(limit: int = 50):
    """查询知识库蒸馏规则"""
    from l7_evolution.knowledge_distiller import KnowledgeDistiller
    rules = KnowledgeDistiller.load_rules(limit=limit)
    return {"ok": True, "rules": rules}


@app.post("/api/llm-gene/generate")
def api_llm_gene(body: dict = None):
    """LLM 创新基因生成（P1-02）：编译验证 + 创新性检查"""
    from l7_evolution.llm_gene_generator import LLMGeneGenerator

    body = body or {}
    existing = []
    try:
        rows = pg_query("SELECT gene_code FROM evolution_logs WHERE gene_code IS NOT NULL LIMIT 20")
        existing = [r["gene_code"] for r in rows if r.get("gene_code")]
    except Exception:
        pass
    gen = LLMGeneGenerator()
    r = gen.generate(context={"reviews": body.get("reviews") or [],
                              "gene_summary": body.get("gene_summary") or []},
                     existing_codes=existing)
    if not r["validated"]:
        return {"ok": False, "error": r["error"]}
    gene = r["gene"]
    # 记录到进化日志（generation=-3 标记 LLM 生成）
    try:
        pg_execute(
            "INSERT INTO evolution_logs (generation, gene_id, gene_params, fitness) "
            "VALUES (-3, %s, %s, NULL)",
            (gene.id, json.dumps(gene.params)))
    except Exception as e:
        logger.warning("llm-gene log: %s", e)
    return {"ok": True, "gene": {"id": gene.id, "params": gene.params,
                                 "code": gene.logic_code[:2000]},
            "novelty": round(r["novelty"], 3)}


@app.post("/api/hpo/start")
def api_hpo_start(body: dict = None):
    """启动 Auto-HPO 后台任务（P1-12）"""
    body = body or {}
    task = task_hpo(
        n_trials=int(body.get("n_trials", 20)),
        params={"envs": body.get("envs", ["bull", "bear", "range", "extreme"]),
                "interval": body.get("interval", "1h"),
                "timeout_seconds": int(body.get("timeout_seconds", 0))},
    )
    return {"ok": True, "task": task.to_dict()}


@app.post("/api/arena/start")
def api_arena_start(body: dict = None):
    """启动对抗竞技场后台任务（P1-01）"""
    body = body or {}
    task = task_arena(
        n_genes=int(body.get("n_genes", 8)),
        rounds=int(body.get("rounds", 3)),
        params={"envs": body.get("envs", ["bull", "bear", "range", "extreme"]),
                "interval": body.get("interval", "1h"),
                "keep_top": int(body.get("keep_top", 2))},
    )
    return {"ok": True, "task": task.to_dict()}


@app.get("/api/experiments")
def api_experiments():
    """实验版本列表（P2-07）"""
    rows = pg_query(
        "SELECT experiment_id, min(generation) AS start_gen, max(generation) AS end_gen, "
        "count(*) AS records, max(fitness) AS best_fitness "
        "FROM evolution_logs WHERE experiment_id IS NOT NULL "
        "GROUP BY experiment_id ORDER BY min(id) DESC LIMIT 50")
    return {"ok": True, "experiments": rows}


@app.get("/api/experiments/compare")
def api_experiments_compare(a: str = "", b: str = ""):
    """对比两次实验（P2-07）"""
    if not a or not b:
        return {"ok": False, "error": "需要 a 与 b 两个 experiment_id"}

    def _summary(eid):
        rows = pg_query(
            "SELECT generation, fitness FROM evolution_logs "
            "WHERE experiment_id=%s ORDER BY generation", (eid,))
        if not rows:
            return None
        fs = [float(r["fitness"] or 0) for r in rows]
        return {"experiment_id": eid, "generations": len(rows),
                "best_fitness": max(fs), "avg_fitness": sum(fs) / len(fs),
                "last_fitness": fs[-1]}

    sa, sb = _summary(a), _summary(b)
    if sa is None or sb is None:
        return {"ok": False, "error": "实验不存在"}
    diff = sa["best_fitness"] - sb["best_fitness"]
    return {"ok": True, "A": sa, "B": sb,
            "better": "A" if diff > 0 else ("B" if diff < 0 else "平局"),
            "best_diff": round(diff, 4)}


@app.get("/api/evolution/tree")
def api_evolution_tree(experiment_id: str = ""):
    """基因进化树数据（P2-03）：gene_id → 父代关系 → ECharts tree 结构"""
    if experiment_id:
        rows = pg_query(
            "SELECT generation, gene_id, parent_gene_ids, fitness FROM evolution_logs "
            "WHERE experiment_id=%s AND gene_id != 'best' ORDER BY generation, id",
            (experiment_id,))
    else:
        rows = pg_query(
            "SELECT generation, gene_id, parent_gene_ids, fitness FROM evolution_logs "
            "WHERE gene_id != 'best' ORDER BY generation, id LIMIT 500")

    nodes = {}
    for r in rows:
        try:
            parents = json.loads(r["parent_gene_ids"]) if r.get("parent_gene_ids") else []
        except Exception:
            parents = []
        nodes[r["gene_id"]] = {
            "generation": int(r["generation"]), "fitness": float(r["fitness"] or 0),
            "parents": parents,
        }

    # 构建树（父代 → 子代）
    children_map: dict[str, list[str]] = {}
    for gid, info in nodes.items():
        for p in info["parents"]:
            children_map.setdefault(p, []).append(gid)

    roots = [gid for gid in nodes if not nodes[gid]["parents"]]

    def build(gid):
        node = {"name": gid, "value": nodes[gid]["fitness"]}
        kids = [build(c) for c in children_map.get(gid, [])]
        if kids:
            node["children"] = kids
        return node

    tree = [build(r) for r in roots] or []
    return {"ok": True, "tree": tree, "node_count": len(nodes)}


@app.get("/api/evolution/convergence")
def api_evolution_convergence():
    """进化收敛性分析报告（P2-04）"""
    from l7_evolution.convergence_analysis import ConvergenceAnalyzer
    r = ConvergenceAnalyzer.analyze_from_db()
    return {"ok": "error" not in r, **r}


@app.post("/api/evolution/start")
def api_evolution_start(body: EvolutionStart):
    task = task_evolution(body.generations, body.population_size, body.model_dump())
    return {"task_id": task.id, "task": task.to_dict()}

@app.post("/api/evolution/{task_id}/pause")
def api_evolution_pause(task_id: str):
    t = tasks_mgr.get(task_id)
    if t:
        t.cancel_event.set()
        return {"ok": True}
    return {"ok": False, "error": "not found"}

@app.get("/api/evolution/curve")
def api_evolution_curve():
    rows = pg_query("SELECT generation, fitness FROM evolution_logs ORDER BY generation, id")
    return {"curve": rows}

@app.get("/api/evolution/population")
def api_evolution_population():
    """进化种群浏览器：读 evolution_logs 各代个体记录"""
    rows = pg_query(
        "SELECT generation, gene_id, gene_params, fitness, parent_gene_ids, env_performances "
        "FROM evolution_logs ORDER BY generation ASC, id ASC")
    for r in rows:
        for k in ("gene_params", "parent_gene_ids", "env_performances"):
            v = r.get(k)
            if isinstance(v, str):
                try:
                    r[k] = json.loads(v)
                except Exception:
                    r[k] = None
            # JSONB 列 psycopg2 已自动解析为 dict/list，直接保留
            else:
                r[k] = v
    return {"population": rows}

@app.get("/api/account")
def api_account():
    try:
        trades = pg_query("SELECT side, pnl, pnl_pct, entry_ts, exit_reason FROM trades ORDER BY id DESC LIMIT 100")
        total_pnl = (pg_query("SELECT COALESCE(SUM(pnl),0) s FROM trades") or [{"s": 0}])[0]["s"]
        decisions = pg_query("SELECT count(*) c FROM decision_logs") or [{"c": 0}]
    except Exception:
        trades, total_pnl, decisions = [], 0, [{"c": 0}]
    # 初始资金与权益：从全局仿真账户读真实值（不再写死 100000）
    initial = sim_account.initial_balance
    cur = 0.0
    try:
        px = ts_query("SELECT close FROM klines WHERE symbol='BTCUSDT' AND interval='5m' ORDER BY ts DESC LIMIT 1")
        cur = float(px[0]["close"]) if px else 0.0
    except Exception:
        pass
    equity = sim_account.equity(cur) if cur > 0 else sim_account.balance + float(total_pnl or 0)
    return {
        "initial_balance": initial,
        "equity": round(equity, 2),
        "drawdown_pct": round(sim_account.drawdown_pct, 4),
        "total_trades": len(sim_account.trade_history) or len(trades),
        "total_decisions": decisions[0]["c"],
        "trades": trades,
    }

def _resolve_env(cfg):
    """递归替换 ${VAR} 占位符为环境变量实际值（未配置 → 空字符串，前端据此判断配置状态）"""
    if isinstance(cfg, dict):
        return {k: _resolve_env(v) for k, v in cfg.items()}
    if isinstance(cfg, list):
        return [_resolve_env(v) for v in cfg]
    if isinstance(cfg, str):
        import re as _re
        def _sub(m):
            return os.environ.get(m.group(1), "")
        return _re.sub(r"\$\{([A-Z0-9_]+)\}", _sub, cfg)
    return cfg


@app.get("/api/config")
def api_config():
    import yaml
    with open(ROOT / "config" / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return _resolve_env(cfg)

@app.put("/api/config")
def api_config_put(body: ConfigUpdate):
    import yaml
    path = ROOT / "config" / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("data", {}).update(body.data)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return {"ok": True}

# ── 定时任务（简单 interval 调度） ──
_scheduled: dict[str, dict] = {}

@app.get("/api/tasks")
def api_tasks_list():
    return {"background": tasks_mgr.list(), "scheduled": list(_scheduled.values())}

@app.post("/api/tasks")
def api_tasks_create(body: TaskCreate):
    tid = uuid.uuid4().hex[:8]
    item = {
        "id": tid, "kind": body.kind, "name": body.name or body.kind,
        "interval_seconds": body.interval_seconds, "params": body.params,
        "status": "active", "last_run": None, "last_result": None,
    }
    _scheduled[tid] = item
    return {"id": tid, "task": item}

@app.delete("/api/tasks/{tid}")
def api_tasks_delete(tid: str):
    return {"ok": _scheduled.pop(tid, None) is not None}

def _scheduler_loop():
    while True:
        time.sleep(5)
        for tid, item in list(_scheduled.items()):
            if item.get("status") != "active":
                continue
            # 简单节流：至少间隔 interval_seconds
            last = item.get("last_run")
            now = time.time()
            if last and (now - last) < max(item.get("interval_seconds", 60), 30):
                continue
            item["last_run"] = now
            kind = item["kind"]
            try:
                if kind == "collect":
                    t = task_collect(item["params"].get("symbol", "BTCUSDT"),
                                     item["params"].get("intervals", ["1h"]))
                    item["last_result"] = f"task {t.id}"
                elif kind == "collect_incremental":
                    t = task_collect_incremental(
                        item["params"].get("symbol", "BTCUSDT"),
                        item["params"].get("intervals"))
                    item["last_result"] = f"task {t.id}"
                elif kind == "import":
                    t = task_import_parquet()
                    item["last_result"] = f"task {t.id}"
                elif kind == "decision":
                    threading.Thread(target=lambda: run_decision_cycle("BTCUSDT"), daemon=True).start()
                    item["last_result"] = "decision triggered"
                elif kind == "backtest":
                    item["last_result"] = "backtest scheduled"
                elif kind == "memory_clean":
                    from l5_memory.memory_cleaner import run_scheduled_clean
                    item["last_result"] = str(run_scheduled_clean(str(ROOT / "data" / "chromadb")))
            except Exception as e:
                item["last_result"] = f"error: {e}"

@app.on_event("startup")
async def startup():
    hub.bind(asyncio.get_event_loop())
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    # 自动注册实时增量采集（默认开启，无需手动配置）
    if "__auto_incr_fast" not in _scheduled:
        _scheduled["__auto_incr_fast"] = {
            "id": "__auto_incr_fast", "kind": "collect_incremental",
            "name": "实时增量 · 1m/5m", "interval_seconds": 300, "auto": True,
            "params": {"symbol": "BTCUSDT", "intervals": ["1m", "5m"]},
            "status": "active", "last_run": None, "last_result": None,
        }
        _scheduled["__auto_incr_mid"] = {
            "id": "__auto_incr_mid", "kind": "collect_incremental",
            "name": "实时增量 · 15m/1h", "interval_seconds": 1800, "auto": True,
            "params": {"symbol": "BTCUSDT", "intervals": ["15m", "1h"]},
            "status": "active", "last_run": None, "last_result": None,
        }
        _scheduled["__auto_incr_slow"] = {
            "id": "__auto_incr_slow", "kind": "collect_incremental",
            "name": "实时增量 · 4h/1d", "interval_seconds": 14400, "auto": True,
            "params": {"symbol": "BTCUSDT", "intervals": ["4h", "1d"]},
            "status": "active", "last_run": None, "last_result": None,
        }
        _scheduled["__memory_clean"] = {
            "id": "__memory_clean", "kind": "memory_clean",
            "name": "记忆自清洗 · 24h", "interval_seconds": 86400, "auto": True,
            "params": {}, "status": "active", "last_run": None, "last_result": None,
        }
    # Agent 循环自动恢复（AUTO_START_AGENT=1 时后端启动即运行）
    if os.environ.get("AUTO_START_AGENT", "") == "1" and runtime.status == "idle":
        runtime.start()
        logger.info("AUTO_START_AGENT=1: Agent 决策循环已自动启动")
    logger.info("workbench backend started (auto incremental tasks registered)")

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        await ws.send_text(json.dumps({"event": "hello", "data": {"msg": "connected"}}))
        while True:
            await ws.receive_text()   # 保持连接
    except WebSocketDisconnect:
        hub.disconnect(ws)

if __name__ == "__main__":
    print("=" * 60)
    print("  Agent 工作台后端 API: http://localhost:8699")
    print("  WebSocket: ws://localhost:8699/ws")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8699, log_level="warning")
