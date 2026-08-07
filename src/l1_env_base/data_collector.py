"""
L1 多源数据采集管道
支持多交易所（Binance / OKX / Bybit）+ FRED 宏观数据
输出：Parquet 文件 → ./data/raw/
"""

from __future__ import annotations

import time
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import yaml

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════

def _load_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_proxy() -> str:
    """从 config 或环境变量获取代理地址"""
    # 确保 .env 已加载
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    cfg = _load_config()
    proxy = cfg["data"].get("proxy", "")
    if proxy.startswith("${"):
        env_var = proxy.strip("${}")
        proxy = os.environ.get(env_var, "")
    return proxy


# ═══════════════════════════════════════════════════════════════
# 多交易所数据采集器
# ═══════════════════════════════════════════════════════════════

class MultiExchangeCollector:
    """
    多交易所数据采集器，支持 Binance / OKX / Bybit 的永续合约 K 线和资金费率。

    按优先级依次尝试，任一可用即可。
    """

    # 交易所注册表：名称 → (ccxt 类名, 永续合约后缀, 现货后缀)
    EXCHANGE_REGISTRY = {
        "binance": {
            "ccxt_id": "binance",
            "linear_suffix": "/USDT:USDT",     # BTC/USDT:USDT
            "spot_suffix": "/USDT",            # BTC/USDT
            "funding": True,                    # 支持资金费率查询
        },
        "okx": {
            "ccxt_id": "okx",
            "linear_suffix": "/USDT:USDT",
            "spot_suffix": "/USDT",
            "funding": True,
        },
        "bybit": {
            "ccxt_id": "bybit",
            "linear_suffix": "/USDT:USDT",
            "spot_suffix": "/USDT",
            "funding": True,
        },
    }

    def __init__(
        self,
        data_dir: str = "./data/raw",
        exchanges: Optional[list[str]] = None,
        proxy: str = "",
    ):
        """
        Args:
            data_dir: 数据存储目录
            exchanges: 交易所优先级列表，默认 ["binance", "okx", "bybit"]
            proxy: 代理地址
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if exchanges is None:
            cfg = _load_config()
            exchanges = cfg["data"]["binance"].get("exchanges", ["binance", "okx", "bybit"])

        self.exchanges = exchanges
        self.proxy = proxy or _get_proxy()

        import ccxt
        self._ccxt = ccxt
        self._connections: dict[str, object] = {}
        self._available: set[str] = set()
        self._unavailable: set[str] = set()

        self._probe_exchanges()

    def _probe_exchanges(self):
        """探测哪些交易所可用"""
        for name in self.exchanges:
            if name not in self.EXCHANGE_REGISTRY:
                logger.warning(f"未知交易所: {name}，跳过")
                self._unavailable.add(name)
                continue

            info = self.EXCHANGE_REGISTRY[name]
            try:
                exchange = self._create_exchange(name)
                exchange.fetch_time()
                self._connections[name] = exchange
                self._available.add(name)
                logger.debug(f"  [OK] {name} 可用")
            except Exception as e:
                self._unavailable.add(name)
                logger.warning(f"  [--] {name} 不可用: {e}")

        if not self._available:
            raise RuntimeError(
                f"所有交易所均不可用 ({self.exchanges})，请检查代理或网络"
            )
        logger.debug(f"可用交易所: {sorted(self._available)}")

    def _create_exchange(self, name: str):
        """创建 ccxt 交易所实例"""
        info = self.EXCHANGE_REGISTRY[name]
        params = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},  # 永续合约
        }
        if self.proxy:
            params["proxies"] = {"https": self.proxy, "http": self.proxy}

        klass = getattr(self._ccxt, info["ccxt_id"])
        return klass(params)

    def _get_exchange(self, name: Optional[str] = None):
        """获取一个可用的交易所实例"""
        if name and name in self._connections:
            return self._connections[name]
        # 返回第一个可用的
        for n in self.exchanges:
            if n in self._connections:
                return self._connections[n]
        raise RuntimeError("没有可用的交易所")

    def _to_ccxt_symbol(self, symbol: str, exchange_name: str) -> str:
        """BTCUSDT → BTC/USDT:USDT"""
        info = self.EXCHANGE_REGISTRY[exchange_name]
        if "/" in symbol:
            return symbol
        for quote in ["USDT", "USDC", "BUSD"]:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                return f"{base}{info['linear_suffix']}"
        raise ValueError(f"无法解析交易对: {symbol}")

    # ─── K 线下载 ──────────────────────────────────────────

    def download_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        start: str = "2024-01-01",
        end: Optional[str] = None,
        exchange: Optional[str] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        """下载永续合约 K 线，自动选择可用交易所"""
        end = end or datetime.now().strftime("%Y-%m-%d")
        output_path = self.data_dir / f"{symbol}_{interval}_{start}_{end}.parquet"

        if output_path.exists() and not force:
            logger.info(f"K线已存在: {output_path}")
            return pd.read_parquet(output_path)

        # 选择交易所
        if exchange and exchange in self._available:
            ex = self._get_exchange(exchange)
            ex_name = exchange
        else:
            ex_name = next(iter(self._available))
            ex = self._connections[ex_name]

        ccxt_symbol = self._to_ccxt_symbol(symbol, ex_name)
        logger.info(f"下载 K线 [{ex_name}]: {ccxt_symbol} {interval} {start} → {end}")

        since_ms = ex.parse8601(f"{start}T00:00:00Z")
        end_ms = ex.parse8601(f"{end}T23:59:59Z")

        all_candles = []
        current_since = since_ms
        batch_count = 0
        consecutive_errors = 0

        while current_since < end_ms:
            try:
                candles = ex.fetch_ohlcv(
                    ccxt_symbol, timeframe=interval,
                    since=current_since, limit=1000,
                )
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                if self._is_rate_limited(e):
                    wait = 60
                    logger.warning(f"限流，等待 {wait}s ({consecutive_errors}/5)")
                else:
                    wait = 5
                    logger.warning(f"下载失败: {e}")
                time.sleep(wait)

                if consecutive_errors >= 5:
                    logger.warning(f"连续失败，终止。已获取 {len(all_candles)} 条")
                    break
                continue

            if not candles:
                break

            all_candles.extend(candles)
            batch_count += 1
            current_since = candles[-1][0] + 1

            if batch_count % 10 == 0:
                logger.info(f"  进度: {len(all_candles)} 条 ...")
            time.sleep(0.05)

        if not all_candles:
            logger.warning("未下载到数据")
            return pd.DataFrame()

        df = pd.DataFrame(
            all_candles,
            columns=["ts", "open", "high", "low", "close", "volume"],
        )
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)

        df.to_parquet(output_path, index=False)
        logger.info(f"  [OK] {len(df):,} 条 → {output_path}")
        return df

    # ─── K 线增量下载（实时更新） ──────────────────────────

    def download_klines_incremental(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        since: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        增量下载 K 线：从 since（默认最近 7 天）拉取到当前时间。
        返回新 K 线 DataFrame（由调用方负责写入数据库/parquet）。
        """
        end = datetime.now().strftime("%Y-%m-%d")
        if since is None:
            since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        if exchange and exchange in self._available:
            ex = self._get_exchange(exchange)
            ex_name = exchange
        else:
            ex_name = next(iter(self._available))
            ex = self._connections[ex_name]

        ccxt_symbol = self._to_ccxt_symbol(symbol, ex_name)
        logger.info(f"增量下载 K线 [{ex_name}]: {ccxt_symbol} {interval} {since} → {end}")

        since_ms = ex.parse8601(f"{since}T00:00:00Z")
        end_ms = ex.parse8601(f"{end}T23:59:59Z")

        all_candles = []
        current_since = since_ms
        consecutive_errors = 0

        while current_since < end_ms:
            try:
                candles = ex.fetch_ohlcv(
                    ccxt_symbol, timeframe=interval,
                    since=current_since, limit=1000,
                )
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                if self._is_rate_limited(e):
                    logger.warning(f"限流，等待 30s ({consecutive_errors}/5)")
                    time.sleep(30)
                else:
                    logger.warning(f"增量下载失败: {e}")
                    time.sleep(5)
                if consecutive_errors >= 5:
                    logger.warning(f"连续失败，终止。已获取 {len(all_candles)} 条")
                    break
                continue

            if not candles:
                break
            all_candles.extend(candles)
            current_since = candles[-1][0] + 1
            time.sleep(0.03)

        if not all_candles:
            logger.info(f"  增量: 无新数据 ({symbol} {interval})")
            return pd.DataFrame()

        df = pd.DataFrame(
            all_candles,
            columns=["ts", "open", "high", "low", "close", "volume"],
        )
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        logger.info(f"  [OK] 增量 {len(df):,} 条 ({symbol} {interval})")
        return df

    # ─── 资金费率 ──────────────────────────────────────────

    def download_funding_rates(
        self,
        symbol: str = "BTCUSDT",
        start: str = "2024-01-01",
        end: Optional[str] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        """下载资金费率历史"""
        end = end or datetime.now().strftime("%Y-%m-%d")
        output_path = self.data_dir / f"{symbol}_funding_{start}_{end}.parquet"

        if output_path.exists() and not force:
            logger.info(f"资金费率已存在: {output_path}")
            return pd.read_parquet(output_path)

        # 找支持资金费率的交易所
        ex_name = None
        for n in self.exchanges:
            if n in self._available and self.EXCHANGE_REGISTRY[n]["funding"]:
                ex_name = n
                break
        if ex_name is None:
            logger.warning("没有可用的交易所支持资金费率查询")
            return pd.DataFrame()

        ex = self._connections[ex_name]
        ccxt_symbol = self._to_ccxt_symbol(symbol, ex_name)
        logger.info(f"下载资金费率 [{ex_name}]: {ccxt_symbol}")

        since_ms = ex.parse8601(f"{start}T00:00:00Z")
        end_ms = ex.parse8601(f"{end}T23:59:59Z")

        all_rates = []
        current_since = since_ms
        consecutive_errors = 0

        while current_since < end_ms:
            try:
                rates = ex.fetch_funding_rate_history(
                    ccxt_symbol, since=current_since, limit=1000,
                )
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                if self._is_rate_limited(e):
                    time.sleep(60)
                else:
                    logger.warning(f"资金费率失败: {e}")
                    time.sleep(5)
                if consecutive_errors >= 5:
                    break
                continue

            if not rates:
                break
            all_rates.extend(rates)
            current_since = rates[-1]["timestamp"] + 1
            time.sleep(0.05)

        if not all_rates:
            return pd.DataFrame()

        df = pd.DataFrame([
            {"ts": pd.to_datetime(r["timestamp"], unit="ms", utc=True), "rate": r["fundingRate"]}
            for r in all_rates
        ])
        df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        df.to_parquet(output_path, index=False)
        logger.info(f"  [OK] 资金费率: {len(df):,} 条")
        return df

    # ─── 批量下载 ──────────────────────────────────────────

    def download_all(self, cfg: Optional[dict] = None) -> dict[str, pd.DataFrame]:
        """根据 config.yaml 批量下载"""
        if cfg is None:
            cfg = _load_config()

        data_cfg = cfg["data"]["binance"]
        results = {}

        for symbol in data_cfg["symbols"]:
            for interval in data_cfg["kline_intervals"]:
                key = f"{symbol}_{interval}"
                results[key] = self.download_klines(
                    symbol=symbol, interval=interval,
                    start=data_cfg["start_date"], end=data_cfg["end_date"],
                )
            results[f"{symbol}_funding"] = self.download_funding_rates(
                symbol=symbol,
                start=data_cfg["start_date"], end=data_cfg["end_date"],
            )
        return results

    # ─── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def _is_rate_limited(e: Exception) -> bool:
        msg = str(e).lower()
        return any(kw in msg for kw in ["418", "429", "banned", "rate limit", "too many"])

    @property
    def available_exchanges(self) -> list[str]:
        return sorted(self._available)


# ═══════════════════════════════════════════════════════════════
# ─── FRED 传统宏观数据 ────────────────────────────────

class FREDCollector:
    """采集 FRED 宏观经济数据（利率、CPI、失业率），免费注册即可。"""

    def __init__(self, api_key: str = "", data_dir: str = "./data/raw"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 确保 .env 已加载
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass

        if not api_key:
            cfg = _load_config()
            api_key = cfg["data"]["fred"].get("api_key", "")
            if api_key.startswith("${"):
                env_var = api_key.strip("${}")
                api_key = os.environ.get(env_var, "")
        if not api_key:
            raise RuntimeError("FRED API Key 未配置，请设置 FRED_API_KEY 环境变量")

        self.api_key = api_key
        self._fred = None

    @property
    def fred(self):
        if self._fred is None:
            # 直接 HTTP 调用 FRED API，无需额外依赖
            self._fred = self.api_key
        return self._fred

    def _call_fred(self, series_id: str, start: str, end: str) -> pd.DataFrame:
        """直接 HTTP 调用 FRED API"""
        import requests
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={self.api_key}"
            f"&observation_start={start}&observation_end={end}"
            "&file_type=json"
        )
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        records = []
        for obs in data.get("observations", []):
            if obs["value"] != ".":
                records.append({"ts": obs["date"], "value": float(obs["value"])})
        return pd.DataFrame(records)

    def download_series(self, series_id: str, start: str = "2024-01-01",
                        end: Optional[str] = None, force: bool = False) -> pd.DataFrame:
        end = end or datetime.now().strftime("%Y-%m-%d")
        output_path = self.data_dir / f"fred_{series_id}_{start}_{end}.parquet"
        if output_path.exists() and not force:
            logger.info(f"FRED 已存在: {series_id}")
            return pd.read_parquet(output_path)
        logger.info(f"下载 FRED: {series_id}")
        try:
            df = self._call_fred(series_id, start, end or datetime.now().strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error(f"FRED {series_id} 失败: {e}")
            return pd.DataFrame()
        if df.empty:
            return df
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.dropna().drop_duplicates(subset="ts").sort_values("ts")
        df.to_parquet(output_path, index=False)
        logger.info(f"  [OK] FRED {series_id}: {len(df)} 条")
        return df

    def download_all(self, cfg: Optional[dict] = None) -> dict:
        if cfg is None:
            cfg = _load_config()
        fc = cfg["data"]["fred"]
        start = cfg["data"]["binance"]["start_date"]
        end = cfg["data"]["binance"]["end_date"]
        results = {}
        for sid in fc.get("series", []):
            results[sid] = self.download_series(sid, start=start, end=end)
        return results


# ─── CoinGecko 加密宏观数据（免费，无需 API Key）──────────

class CoinGeckoMacroCollector:
    """通过 CoinGecko 免费 API 获取加密市场宏观指标。"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, data_dir: str = "./data/raw"):
        self.data_dir = __import__("pathlib").Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download_global_market(self) -> dict:
        url = f"{self.BASE_URL}/global"
        import requests
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()["data"]
            return {
                "total_mcap": data["total_market_cap"]["usd"],
                "total_volume_24h": data["total_volume"]["usd"],
                "btc_dominance": data["market_cap_percentage"]["btc"],
                "eth_dominance": data["market_cap_percentage"]["eth"],
                "active_cryptos": data["active_cryptocurrencies"],
            }
        except Exception as e:
            logger.warning(f"CoinGecko global failed: {e}")
            return {}

    def download_btc_history(self, days: int = 365, force: bool = False):
        import logging, requests, pandas as pd
        from datetime import datetime, timezone
        logger = logging.getLogger(__name__)
        output_path = self.data_dir / f"coingecko_btc_{days}d.parquet"
        if output_path.exists() and not force:
            return pd.read_parquet(output_path)
        url = f"{self.BASE_URL}/coins/bitcoin/market_chart?vs_currency=usd&days={days}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            d = r.json()
            prices = pd.DataFrame(d["prices"], columns=["ts", "price"])
            prices["ts"] = pd.to_datetime(prices["ts"], unit="ms", utc=True)
            mcap = pd.DataFrame(d["market_caps"], columns=["ts", "market_cap"])
            mcap["ts"] = pd.to_datetime(mcap["ts"], unit="ms", utc=True)
            vol = pd.DataFrame(d["total_volumes"], columns=["ts", "total_volume"])
            vol["ts"] = pd.to_datetime(vol["ts"], unit="ms", utc=True)
            df = prices.merge(mcap, on="ts").merge(vol, on="ts")
            df.to_parquet(output_path, index=False)
            logger.info(f"  [OK] CoinGecko BTC history: {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"CoinGecko BTC history failed: {e}")
            return pd.DataFrame()

    def download_all(self, cfg=None):
        results = {}
        global_data = self.download_global_market()
        if global_data:
            results["global"] = global_data
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"  Global MCap: ${global_data['total_mcap']/1e12:.2f}T  "
                       f"BTC: {global_data['btc_dominance']:.1f}%")
        results["btc_history"] = self.download_btc_history(days=365)
        return results


class FearGreedCollector:
    """
    免费情绪指标采集器（P0-02 免费替代方案）：Alternative.me Crypto Fear & Greed Index。

    - 完全免费，无需 API Key
    - 恐慌贪婪指数（0-100）：市场情绪，替代 Glassnode 链上情绪维度
    - 附带 BTC 历史价格（用于后续 MVRV 等近似计算）
    """

    FNG_URL = "https://api.alternative.me/fng/"
    PRICE_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    NAME = "fear_greed"

    def __init__(self, data_dir: str = "./data/raw"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download_fng(self, limit: int = 730) -> pd.DataFrame:
        """恐惧贪婪指数（免费）"""
        import requests
        r = requests.get(self.FNG_URL, params={"limit": limit, "format": "json"},
                         timeout=20)
        r.raise_for_status()
        payload = r.json()
        rows = []
        for d in payload.get("data", []):
            try:
                rows.append({
                    "ts": pd.Timestamp(int(d["timestamp"]), unit="s", tz="UTC"),
                    "value": float(d["value"]),
                    "classification": d.get("value_classification", ""),
                })
            except Exception:
                continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        return df

    def download_all(self, start: str = "2024-01-01", end: str = "2026-06-30") -> dict:
        """下载 FNG 情绪指数 + BTC 价格，写 parquet"""
        out = {}
        # 1. 恐惧贪婪指数
        try:
            df = self.download_fng()
            if not df.empty:
                f = self.data_dir / f"fear_greed.parquet"
                df.to_parquet(f)
                logger.info(f"  [OK] Fear&Greed: {len(df)} 行 → {f.name}")
                out["fear_greed"] = df
        except Exception as e:
            logger.warning(f"Fear&Greed 采集失败: {e}")
        return out


class GlassnodeCollector:
    """
    采集 Glassnode 链上数据（P0-02，可选）。

    注意：Glassnode 高级指标为收费服务（studio.glassnode.com）。
    未配置 GLASSNODE_API_KEY 时不再阻断流程——项目默认使用免费替代：
    FearGreedCollector（Alternative.me 恐慌贪婪指数，无需 Key）。
    若配置了 Key，则继续采集链上指标。
    """

    BASE_URL = "https://api.glassnode.com/v1/metrics"

    # 指标路径：地址活跃度 / 转账量 / 矿工净头寸变化
    METRICS = {
        "active_addresses": "addresses/active_count",
        "transfer_volume": "transactions/transfers_volume_sum",
        "miner_netflow": "miners/flow_net",
    }

    def __init__(self, data_dir: str = "./data/raw"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass

        api_key = os.environ.get("GLASSNODE_API_KEY", "")
        if not api_key:
            cfg = _load_config()
            api_key = (cfg.get("data", {}).get("glassnode", {}).get("api_key", "") or "").strip()
            if api_key.startswith("${"):
                api_key = os.environ.get(api_key.strip("${}"), "")
        if not api_key:
            # 未配置：不再阻断——项目默认免费替代（FearGreedCollector）
            self.api_key = ""
            logger.warning(
                "GLASSNODE_API_KEY 未配置：Glassnode 为收费服务，跳过链上指标采集；"
                "免费替代已启用：Fear&Greed 恐慌贪婪指数（无需 Key）")
            return
        self.api_key = api_key

    def collect_metric(self, name: str, symbol: str = "BTC",
                       start: str = "2024-01-01", end: str = "2026-06-30",
                       interval: str = "1d") -> "pd.DataFrame":
        """采集单个链上指标"""
        import requests

        path = self.METRICS.get(name)
        if path is None:
            raise ValueError(f"未知指标: {name}, 可选 {list(self.METRICS)}")
        url = (f"{self.BASE_URL}/{path}?a={symbol}&i={interval}"
               f"&s={start}&u={end}&api_key={self.api_key}")
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            import pandas as pd
            df = pd.DataFrame(data)
            if df.empty:
                logger.warning(f"  [--] Glassnode {name}: 空数据")
                return df
            df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
            df = df.drop(columns=["t"]).rename(columns={"v": name})
            df = df[["ts", name]]
            out = self.data_dir / f"glassnode_{name}.parquet"
            df.to_parquet(out, index=False)
            logger.info(f"  [OK] Glassnode {name}: {len(df)} 行 → {out.name}")
            return df
        except Exception as e:
            logger.error(f"Glassnode {name} 采集失败: {e}")
            return pd.DataFrame()

    def download_all(self, start: str = "2024-01-01", end: str = "2026-06-30") -> dict:
        """采集全部链上指标"""
        results = {}
        for name in self.METRICS:
            results[name] = self.collect_metric(name, start=start, end=end)
        return results


# ═══════════════════════════════════════════════════════════════
# 数据完整性校验
# ═══════════════════════════════════════════════════════════════

def validate_kline_data(df: "pd.DataFrame", interval: str, start: str, end: str) -> dict:
    """校验 K 线数据完整性"""
    result = {
        "total_rows": len(df), "expected_rows": 0, "completeness_pct": 100.0,
        "gaps": 0, "null_pct": 0.0, "is_valid": True, "warnings": [],
    }
    if df.empty:
        result["is_valid"] = False
        result["warnings"].append("数据为空")
        return result

    null_ratio = df[["open", "high", "low", "close", "volume"]].isnull().mean().max()
    result["null_pct"] = round(null_ratio * 100, 2)
    if null_ratio > 0.01:
        result["warnings"].append(f"空值 {result['null_pct']}% > 1%")

    freq_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
    freq = freq_map.get(interval, "1h")
    expected_index = pd.date_range(start=start, end=end, freq=freq, tz="UTC")
    result["expected_rows"] = len(expected_index)
    if result["expected_rows"] > 0:
        result["completeness_pct"] = round(len(df) / result["expected_rows"] * 100, 2)

    time_diffs = df["ts"].diff().dropna()
    expected_diff = pd.Timedelta(freq)
    gaps = time_diffs[time_diffs > expected_diff * 1.5]
    result["gaps"] = len(gaps)
    if result["gaps"] > 0:
        result["warnings"].append(f"{len(gaps)} 个缺口，最大 {gaps.max()}")

    if result["completeness_pct"] < 95:
        result["is_valid"] = False
    if null_ratio > 0.05:
        result["is_valid"] = False

    return result


def validate_all(cfg: Optional[dict] = None) -> bool:
    """校验所有已下载数据"""
    if cfg is None:
        cfg = _load_config()
    data_dir = Path(cfg["data"]["binance"]["data_dir"])
    data_cfg = cfg["data"]["binance"]
    all_valid = True

    print("\n" + "=" * 60)
    print("  数据完整性校验")
    print("=" * 60)

    for symbol in data_cfg["symbols"]:
        for interval in data_cfg["kline_intervals"]:
            pattern = f"{symbol}_{interval}_*.parquet"
            files = list(data_dir.glob(pattern))
            if not files:
                print(f"\n  [WARN] {symbol} {interval}: 未找到数据")
                all_valid = False
                continue

            df = pd.read_parquet(files[0])
            result = validate_kline_data(df, interval, data_cfg["start_date"], data_cfg["end_date"])
            status = "[OK]" if result["is_valid"] else "[FAIL]"
            print(f"\n  {status} {symbol} {interval}: "
                  f"{result['total_rows']:,}/{result['expected_rows']:,} "
                  f"({result['completeness_pct']}%)")
            for w in result["warnings"]:
                print(f"      ! {w}")
            if not result["is_valid"]:
                all_valid = False

    print("\n" + "=" * 60)
    print(f"  结果: {'[OK] 全部通过' if all_valid else '[FAIL] 有问题'}")
    print("=" * 60)
    return all_valid