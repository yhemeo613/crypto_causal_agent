"""
L2 四环境仿真沙箱
构建牛/熊/震荡/极端四种市场环境，支持环境切换和数据迭代
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Iterator

import pandas as pd
import numpy as np
import yaml


# ═══════════════════════════════════════════════════════════════
# 环境定义
# ═══════════════════════════════════════════════════════════════

@dataclass
class Environment:
    """单个仿真环境"""
    name: str
    description: str
    date_start: str
    date_end: str
    regime: str = ""                # trend / range / extreme
    data: Optional[pd.DataFrame] = None

    @property
    def days(self) -> int:
        s = datetime.fromisoformat(self.date_start)
        e = datetime.fromisoformat(self.date_end)
        return (e - s).days


class EnvironmentRegistry:
    """
    四环境注册中心。

    从 config.yaml 读取环境定义，从 data/raw/ 加载 K 线数据。
    环境切换时自动清理旧数据，保证无状态泄漏。
    """

    def __init__(self, config_path: str = "config/config.yaml", data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.symbol = cfg["data"]["binance"]["symbols"][0]
        self.intervals = cfg["data"]["binance"]["kline_intervals"]
        self.env_configs = cfg["sandbox"]["environments"]
        self._current: Optional[Environment] = None
        self._data_cache: dict[str, pd.DataFrame] = {}

    # ─── 环境列表 ──────────────────────────────────────────

    def list_environments(self) -> list[Environment]:
        """列出所有可用环境（不加载数据）"""
        envs = []
        for name, ec in self.env_configs.items():
            envs.append(Environment(
                name=name,
                description=ec.get("description", ""),
                date_start=ec["date_range"][0],
                date_end=ec["date_range"][1],
                regime=self._infer_regime(name),
            ))
        return envs

    # ─── 环境切换 ──────────────────────────────────────────

    def load(self, env_name: str, interval: str = "1h") -> Environment:
        """
        加载指定环境的数据。

        Args:
            env_name: bull | bear | range | extreme
            interval: K线周期

        Returns:
            Environment with loaded data
        """
        if env_name not in self.env_configs:
            raise ValueError(f"未知环境: {env_name}, 可用: {list(self.env_configs.keys())}")

        # 清除旧环境状态（无泄漏）
        self._current = None

        ec = self.env_configs[env_name]
        df = self._load_kline_data(interval, ec["date_range"][0], ec["date_range"][1])

        # Regime：优先 config 显式标注，否则数据驱动分类（不再写死）
        regime = ec.get("regime") or self.classify_regime(df) or self._infer_regime(env_name)

        env = Environment(
            name=env_name,
            description=ec.get("description", ""),
            date_start=ec["date_range"][0],
            date_end=ec["date_range"][1],
            regime=regime,
            data=df,
        )
        self._current = env
        return env

    def get_current(self) -> Optional[Environment]:
        return self._current

    # ─── 数据迭代 ──────────────────────────────────────────

    def iter_bars(self, env: Optional[Environment] = None) -> Iterator[dict]:
        """
        按时间步遍历 K 线数据。

        Yields:
            dict with keys: ts, symbol, o, h, l, c, v, regime
        """
        env = env or self._current
        if env is None or env.data is None or env.data.empty:
            raise RuntimeError("未加载环境或无数据")

        for _, row in env.data.iterrows():
            yield {
                "ts": row["ts"],
                "symbol": self.symbol,
                "o": row["open"],
                "h": row["high"],
                "l": row["low"],
                "c": row["close"],
                "v": row["volume"],
                "regime": env.regime,
            }

    def get_bar_count(self, env: Optional[Environment] = None) -> int:
        env = env or self._current
        if env is None or env.data is None:
            return 0
        return len(env.data)

    # ─── Regime 分类器（数据驱动：趋势 R² + 年化波动率）────────

    def classify_regime(
        self, df: pd.DataFrame, window: Optional[int] = None
    ) -> str:
        """
        基于数据自动分类 Regime（不再写死）：
          - 强趋势（线性拟合 R²>0.5 且价格变化>15%）→ trend_up / trend_down
          - 高波动（年化波动率 > 4.0）→ high_vol
          - 其余 → range

        Returns:
            "trend_up" | "trend_down" | "range" | "high_vol" | "unknown"
        """
        if df is None or df.empty or len(df) < 30:
            return "unknown"

        close = df["close"].astype(float)
        n = len(close)
        pct_change = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]

        # 线性趋势拟合 R²（衡量价格是否呈单边趋势）
        x = np.arange(n)
        slope, intercept = np.polyfit(x, close, 1)
        yhat = slope * x + intercept
        ss_res = float(((close - yhat) ** 2).sum())
        ss_tot = float(((close - close.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / (ss_tot + 1e-9)

        # 年化波动率（小时 K 线）
        returns = close.pct_change().dropna()
        vol = float(returns.std() * np.sqrt(365 * 24)) if len(returns) > 2 else 0.0

        if r2 > 0.5 and abs(pct_change) > 0.15:
            return "trend_up" if pct_change > 0 else "trend_down"
        if vol > 4.0:
            return "high_vol"
        return "range"

    # ─── 内部 ──────────────────────────────────────────────

    def _load_kline_data(self, interval: str, start: str, end: str) -> pd.DataFrame:
        """从 Parquet 文件加载并切片 K 线数据"""
        # 匹配文件：BTCUSDT_1h_2024-01-01_2026-06-30.parquet
        pattern = f"{self.symbol}_{interval}_*.parquet"
        files = sorted(self.data_dir.glob(pattern))

        if not files:
            raise FileNotFoundError(
                f"未找到 {self.symbol} {interval} K线数据，请先运行 python main.py download"
            )

        df = pd.read_parquet(files[0])
        # 按日期范围切片
        mask = (df["ts"] >= start) & (df["ts"] <= f"{end}T23:59:59")
        sliced = df[mask].copy()
        sliced = sliced.sort_values("ts").reset_index(drop=True)

        if sliced.empty:
            raise ValueError(f"{self.symbol} {interval} 在 {start}~{end} 范围内无数据")

        return sliced

    @staticmethod
    def _infer_regime(name: str) -> str:
        mapping = {"bull": "trend_up", "bear": "trend_down", "range": "range", "extreme": "high_vol"}
        return mapping.get(name, "unknown")

    # ─── 环境摘要 ──────────────────────────────────────────

    def summary(self, env: Optional[Environment] = None) -> dict:
        """生成环境统计摘要"""
        env = env or self._current
        if env is None or env.data is None or env.data.empty:
            return {}

        df = env.data
        close = df["close"]
        returns = close.pct_change().dropna()

        return {
            "name": env.name,
            "description": env.description,
            "regime": env.regime,
            "bars": len(df),
            "date_start": str(df["ts"].min()),
            "date_end": str(df["ts"].max()),
            "price_start": round(float(close.iloc[0]), 2),
            "price_end": round(float(close.iloc[-1]), 2),
            "pct_change": round(float((close.iloc[-1] / close.iloc[0] - 1) * 100), 2),
            "max_price": round(float(close.max()), 2),
            "min_price": round(float(close.min()), 2),
            "volatility_annualized": round(float(returns.std() * np.sqrt(365 * 24) * 100), 2),
            "max_drawdown_pct": round(float(self._max_drawdown(close) * 100), 2),
        }

    @staticmethod
    def _max_drawdown(series: pd.Series) -> float:
        rolling_max = series.cummax()
        drawdown = (series - rolling_max) / rolling_max
        return float(drawdown.min())
