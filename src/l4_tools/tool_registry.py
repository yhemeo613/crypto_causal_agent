"""
L4 工具调度标准化层（P0-11）
三级权限工具调度：
  - READ  只读工具：数据查询（不产生任何状态变更）
  - CALC  计算工具：指标计算（纯函数，不触发交易）
  - ACT   动作工具：下单/调仓（必须经辩论决策通过门禁后方可调用）

门禁规则（不可绕过）：
  - ACT 工具调用时必须携带 decision_passed=True，否则拒绝
  - READ/CALC 工具永远不可能触发交易
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class ToolPermission(str, Enum):
    READ = "read"      # 只读：数据查询
    CALC = "calc"      # 计算：指标计算
    ACT = "act"        # 动作：下单/调仓（需门禁）


@dataclass
class ToolSpec:
    """工具规格"""
    name: str
    description: str
    permission: ToolPermission
    fn: Callable[..., Any]
    args_schema: dict = field(default_factory=dict)   # {"arg": "说明"}
    requires_gate: bool = False                        # ACT 工具必须 True


class ToolCallDenied(Exception):
    """工具调用被权限系统拒绝"""
    pass


# ═══════════════════════════════════════════════════════════════
# 内置工具实现（真实组件，非占位）
# ═══════════════════════════════════════════════════════════════

def _pg_query(sql: str, params: tuple = ()):
    """内部 PG 查询（统一连接：db_conn 从 config 读取）"""
    from db_conn import ts_query as _q
    return _q(sql, params)


def _read_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 300) -> list[dict]:
    """只读：查询历史 K 线"""
    rows = _pg_query(
        "SELECT ts, open, high, low, close, volume FROM klines "
        "WHERE symbol=%s AND interval=%s ORDER BY ts DESC LIMIT %s",
        (symbol, interval, limit))
    for r in rows:
        for k in ("open", "high", "low", "close", "volume"):
            r[k] = float(r[k])
    return rows


def _read_funding(symbol: str = "BTCUSDT", limit: int = 50) -> list[dict]:
    """只读：查询资金费率"""
    return _pg_query(
        "SELECT ts, rate FROM funding_rates WHERE symbol=%s ORDER BY ts DESC LIMIT %s",
        (symbol, limit))


def _read_macro(indicator: Optional[str] = None, limit: int = 30) -> list[dict]:
    """只读：查询宏观数据（FRED）"""
    if indicator:
        return _pg_query(
            "SELECT indicator, value, ts FROM macro_data WHERE indicator=%s ORDER BY ts DESC LIMIT %s",
            (indicator, limit))
    return _pg_query(
        "SELECT indicator, value, ts FROM macro_data ORDER BY ts DESC LIMIT %s", (limit,))


def _read_causal_graph(symbol: str = "BTCUSDT", depth: int = 2) -> dict:
    """只读：查询 Neo4j 因果图谱"""
    try:
        from l5_memory.causal_graph_query import CausalGraphQuery
        cg = CausalGraphQuery()
        paths = cg.query_causal_paths(symbol, max_depth=depth)
        return {"paths": paths}
    except Exception as e:
        return {"paths": [], "error": str(e)}


def _calc_indicators(symbol: str = "BTCUSDT", interval: str = "1h",
                     limit: int = 300) -> dict:
    """计算：MA20/MA60/RSI/ATR 技术指标（纯计算，无状态变更）"""
    rows = _read_klines(symbol, interval, limit)
    if not rows:
        return {"symbol": symbol, "interval": interval, "indicators": {}}
    df = pd.DataFrame(list(reversed(rows)))
    close = df["close"]
    high, low = df["high"], df["low"]
    out = {}
    for w in (20, 60):
        if len(close) >= w:
            out[f"ma{w}"] = float(close.rolling(w).mean().iloc[-1])
    # RSI(14)
    if len(close) > 14:
        delta = close.diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = (-delta.clip(upper=0)).rolling(14).mean()
        rs = up / down.replace(0, 1e-12)
        out["rsi14"] = float(100 - 100 / (1 + rs.iloc[-1]))
    # ATR(14)
    if len(close) > 14:
        tr = pd.concat([high - low, (high - close.shift()).abs(),
                        (low - close.shift()).abs()], axis=1).max(axis=1)
        out["atr14"] = float(tr.rolling(14).mean().iloc[-1])
    out["last_close"] = float(close.iloc[-1])
    return {"symbol": symbol, "interval": interval, "indicators": out}


def _calc_volatility(symbol: str = "BTCUSDT", interval: str = "1h",
                     window: int = 100) -> dict:
    """计算：收益率波动率（年化）"""
    rows = _read_klines(symbol, interval, window + 1)
    if len(rows) < 2:
        return {"volatility": 0.0}
    df = pd.DataFrame(list(reversed(rows)))
    ret = df["close"].pct_change().dropna()
    vol = float(ret.std() * (365 * 24) ** 0.5 if interval.endswith("h") else ret.std() * 16)
    return {"symbol": symbol, "interval": interval, "volatility_annualized": round(vol, 6),
            "samples": len(ret)}


# ACT 工具：下单（动作门禁在 ToolRegistry.call 强制）
def _act_submit_order(symbol: str = "BTCUSDT", side: str = "long",
                      size_units: float = 0.0, leverage: float = 2.0) -> dict:
    """动作：提交市价订单（需 decision_passed 门禁）"""
    from l1_env_base.matching_engine import (MatchingEngine, OrderRequest, OrderSide, OrderType)
    rows = _pg_query(
        "SELECT ts, open, high, low, close, volume FROM klines "
        "WHERE symbol=%s AND interval='5m' ORDER BY ts DESC LIMIT 1", (symbol,))
    if not rows:
        return {"ok": False, "reason": "无最新行情"}
    r = rows[0]
    price = float(r["close"])
    kline = {"o": float(r["open"]), "h": float(r["high"]), "l": float(r["low"]),
             "c": float(r["close"]), "v": float(r["volume"])}
    order = OrderRequest(symbol=symbol, side=OrderSide.LONG if side == "long" else OrderSide.SHORT,
                         order_type=OrderType.MARKET, size=size_units, leverage=leverage)
    fill = MatchingEngine().match_market(order, kline, price)
    return {"ok": fill.filled, "fill_price": round(fill.fill_price, 2),
            "fill_size": round(fill.fill_size, 6), "fee": round(fill.fee, 2),
            "slippage_pct": round(fill.slippage_pct, 5)}


# ═══════════════════════════════════════════════════════════════
# 工具注册表 + 三级权限调度
# ═══════════════════════════════════════════════════════════════

class ToolRegistry:
    """三级权限工具注册表与调度器"""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self.call_log: list[dict] = []
        self._register_builtin()

    def _register_builtin(self):
        self.register(
            "query_klines", ToolPermission.READ, _read_klines,
            "查询历史 K 线", {"symbol": "交易对", "interval": "周期", "limit": "条数"})
        self.register(
            "query_funding", ToolPermission.READ, _read_funding,
            "查询资金费率", {"symbol": "交易对", "limit": "条数"})
        self.register(
            "query_macro", ToolPermission.READ, _read_macro,
            "查询宏观数据(FRED)", {"indicator": "指标名(可选)", "limit": "条数"})
        self.register(
            "query_causal_graph", ToolPermission.READ, _read_causal_graph,
            "查询 Neo4j 因果图谱", {"symbol": "交易对", "depth": "路径深度"})
        self.register(
            "calc_indicators", ToolPermission.CALC, _calc_indicators,
            "计算 MA/RSI/ATR 指标", {"symbol": "交易对", "interval": "周期"})
        self.register(
            "calc_volatility", ToolPermission.CALC, _calc_volatility,
            "计算年化波动率", {"symbol": "交易对", "interval": "周期"})
        self.register(
            "submit_order", ToolPermission.ACT, _act_submit_order,
            "提交市价订单（需辩论决策门禁）", {"symbol": "交易对", "side": "long/short",
                                          "size_units": "张数", "leverage": "杠杆"})

    def register(self, name: str, permission: ToolPermission, fn: Callable,
                 description: str = "", args_schema: dict = None):
        if name in self._tools:
            raise ValueError(f"工具 {name} 已注册")
        spec = ToolSpec(name=name, description=description, permission=permission,
                        fn=fn, args_schema=args_schema or {},
                        requires_gate=(permission == ToolPermission.ACT))
        self._tools[name] = spec
        logger.info(f"[l4] 注册工具 {name} ({permission.value})")
        return spec

    # ─── 调度入口（唯一调用途径，权限强制） ───────────────

    def call(self, name: str, decision_passed: bool = False, **kwargs) -> dict:
        """
        调用工具（统一门禁）：
        - READ/CALC：任意调用
        - ACT：必须 decision_passed=True，否则拒绝（不可绕过）
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ToolCallDenied(f"未知工具: {name}")

        if spec.permission == ToolPermission.ACT and not decision_passed:
            self.call_log.append({"tool": name, "permission": "act", "allowed": False,
                                  "reason": "辩论决策未通过，动作工具禁止调用"})
            raise ToolCallDenied(
                f"动作工具 {name} 需要辩论决策通过 (decision_passed=True) 后方可调用")

        try:
            result = spec.fn(**kwargs)
        except Exception as e:
            self.call_log.append({"tool": name, "permission": spec.permission.value,
                                  "allowed": False, "reason": str(e)})
            return {"ok": False, "error": str(e)}

        self.call_log.append({"tool": name, "permission": spec.permission.value,
                              "allowed": True, "kwargs": {k: v for k, v in kwargs.items()}})
        return result

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description,
                 "permission": t.permission.value, "args_schema": t.args_schema,
                 "requires_gate": t.requires_gate}
                for t in self._tools.values()]

    def call_log_since(self, n: int = 50) -> list[dict]:
        return self.call_log[-n:]


# 全局单例
registry = ToolRegistry()
