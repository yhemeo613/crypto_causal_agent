"""
crypto_causal_agent — 自主因果推理型加密永续合约进化 Agent
主入口：环境自检 / 数据下载 / 回测 / 进化实验
"""

from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# 将 src 加入路径
sys.path.insert(0, str(Path(__file__).parent / "src"))


def cmd_check(_args=None) -> int:
    """环境自检：验证所有依赖和模块可正常导入"""
    import importlib
    import yaml

    print("=" * 60)
    print("  crypto_causal_agent 环境自检")
    print("=" * 60)

    errors = []

    # ─── 1. 配置文件检查 ────────────────────
    print("\n[1/4] 配置文件...")
    config_path = Path(__file__).parent / "config" / "config.yaml"
    if not config_path.exists():
        errors.append("config/config.yaml 不存在")
        print("  [FAIL] config/config.yaml 不存在")
    else:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        print(f"  [OK] config.yaml 加载成功 (project: {cfg['project']['name']} v{cfg['project']['version']})")

    # ─── 2. Python 版本 ─────────────────────
    print("\n[2/4] Python 环境...")
    v = sys.version_info
    print(f"  Python {v.major}.{v.minor}.{v.micro}")
    if (v.major, v.minor) < (3, 11):
        errors.append(f"需要 Python ≥ 3.11，当前 {v.major}.{v.minor}")
        print("  [FAIL] 版本过低，需要 ≥ 3.11")
    else:
        print("  [OK] 版本满足要求")

    # ─── 3. 核心依赖导入 ────────────────────
    print("\n[3/4] 核心依赖...")
    deps = {
        # 框架
        "langgraph": "langgraph",
        "langchain": "langchain_core",
        "pydantic": "pydantic",
        # LLM
        "openai": "openai",
        # 数据处理
        "pandas": "pandas",
        "numpy": "numpy",
        # 数据库
        "psycopg2": "psycopg2",
        "chromadb": "chromadb",
        "neo4j": "neo4j",
        "redis": "redis",
        # 数据采集
        "ccxt": "ccxt",
        # 进化
        "deap": "deap",
        "optuna": "optuna",
        # 统计
        "statsmodels": "statsmodels",
        "networkx": "networkx",
        # 日志
        "structlog": "structlog",
        "yaml": "yaml",
    }

    for name, module in deps.items():
        try:
            importlib.import_module(module)
            print(f"  [OK] {name}")
        except ImportError as e:
            errors.append(f"缺少依赖 {name}: {e}")
            print(f"  [FAIL] {name} — {e}")

    # TA-Lib 特殊处理（C 库可能缺失）
    try:
        import talib
        print(f"  [OK] TA-Lib (talib)")
    except ImportError:
        print(f"  [WARN] TA-Lib 未安装（技术指标计算将降级为 pandas 实现）")

    # PyTorch（CPU-only 即可）
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  [OK] torch (device={device})")
    except ImportError:
        print(f"  [WARN] torch 未安装（MAML 元学习将不可用）")

    # ─── 4. 项目模块导入 ─────────────────────
    print("\n[4/4] 项目模块...")
    modules = [
        "l1_env_base",
        "l2_sandbox",
        "l3_perception",
        "l4_tools",
        "l5_memory",
        "l6_agent",
        "l6_agent.agents",
        "l7_evolution",
    ]
    for m in modules:
        try:
            importlib.import_module(m)
            print(f"  [OK] src.{m}")
        except ImportError as e:
            errors.append(f"模块 {m} 导入失败: {e}")
            print(f"  [FAIL] src.{m} — {e}")

    # ─── 结果 ───────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"  [FAIL] 自检未通过 — {len(errors)} 个问题:")
        for e in errors:
            print(f"    - {e}")
        print("  请先解决以上问题后重新运行。")
        return 1
    else:
        print("  [OK] 全部自检通过！可以开始开发。")
        print("=" * 60)
        return 0


def cmd_download(args) -> int:
    """下载历史数据"""
    import logging
    from l1_env_base.data_collector import (
        MultiExchangeCollector, FREDCollector, CoinGeckoMacroCollector,
        FearGreedCollector, validate_all
    )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("  多源数据采集")
    print("=" * 60)

    # ─── 币安 K 线 + 资金费率 ──────────────────
    print("\n[1/2] 币安数据...")
    collector = MultiExchangeCollector(data_dir="./data/raw")

    # 显示可用交易所
    print(f"  可用交易所: {collector.available_exchanges}")
    if not collector.available_exchanges:
        print("  [FAIL] 没有可用的交易所，请检查代理或网络")
        return 1

    success_count = 0
    fail_count = 0

    for interval in args.intervals:
        try:
            df = collector.download_klines(
                symbol=args.symbol,
                interval=interval,
                start=args.start,
                end=args.end,
                force=args.force,
            )
            if not df.empty:
                success_count += 1
                print(f"  [OK] {args.symbol} {interval}: {len(df):,} 条")
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            print(f"  [FAIL] {args.symbol} {interval}: {e}")

    # 资金费率
    try:
        df_fr = collector.download_funding_rates(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            force=args.force,
        )
        if not df_fr.empty:
            print(f"  [OK] {args.symbol} funding_rate: {len(df_fr):,} 条")
        else:
            print(f"  [WARN] {args.symbol} funding_rate: 未获取到数据")
    except Exception as e:
        print(f"  [FAIL] {args.symbol} funding_rate: {e}")

    # ─── 宏观数据（FRED + CoinGecko）──────────
    print("\n[2/2] 宏观数据...")

    # FRED 传统宏观
    try:
        fred = FREDCollector(data_dir="./data/raw")
        for sid, df in fred.download_all().items():
            if not df.empty:
                print(f"  [OK] FRED {sid}: {len(df):,} 条")
            else:
                print(f"  [WARN] FRED {sid}: 无数据")
    except Exception as e:
        print(f"  [WARN] FRED: {e}")

    # CoinGecko 加密宏观
    try:
        cg = CoinGeckoMacroCollector(data_dir="./data/raw")
        cg.download_all()
    except Exception as e:
        print(f"  [WARN] CoinGecko: {e}")

    # 免费情绪指标（Fear&Greed，替代收费的 Glassnode）
    print("\n[2.5] 免费情绪指标（Fear&Greed，无需 Key）...")
    try:
        fg = FearGreedCollector(data_dir="./data/raw")
        fg.download_all()
    except Exception as e:
        print(f"  [WARN] Fear&Greed: {e}")

    # ─── 校验 ──────────────────────────────────
    print()
    validate_all()

    print(f"\n下载完成: 成功 {success_count}, 失败 {fail_count}")
    return 0 if fail_count == 0 else 1


def cmd_backtest(args) -> int:
    """运行单策略回测"""
    from l2_sandbox.environment import EnvironmentRegistry

    print("=" * 60)
    print("  单策略回测")
    print("=" * 60)

    registry = EnvironmentRegistry()
    envs_to_run = ["bull", "bear", "range", "extreme"] if args.env == "all" else [args.env]

    for env_name in envs_to_run:
        print(f"\n--- {env_name} ---")
        try:
            env = registry.load(env_name, interval="1h")
            summary = registry.summary(env)
            print(f"  Bars: {summary['bars']}  "
                  f"价格: {summary['price_start']} → {summary['price_end']} "
                  f"({summary['pct_change']}%)")
            print(f"  最大回撤: {summary['max_drawdown_pct']}%  "
                  f"年化波动: {summary['volatility_annualized']}%")
            print(f"  Regime: {summary['regime']}")
        except Exception as e:
            print(f"  [FAIL] {e}")

    return 0


def cmd_evolve(args) -> int:
    """运行真实进化实验：四环境回测评估 + 遗传进化"""
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    sys.path.insert(0, str(Path(__file__).parent / "dashboard"))
    from l7_evolution.evolution_engine import EvolutionEngine
    import server as _srv  # 复用真实回测

    engine = EvolutionEngine(
        population_size=args.population,
        generations=args.generations,
        generalization_weight=0.3,
    )
    engine.init_population()

    def env_perf_func(gene):
        return _srv.backtest_gene(gene, envs=("bull", "bear", "range", "extreme"))

    best = engine.run(env_perf_func)
    print(f"[OK] 进化完成: {args.generations} 代 × {args.population} 个体")
    print(f"  best fitness: {best.fitness:.4f}")
    print(f"  best params: {best.params}")
    print(f"  各环境绩效: {best.env_performances}")
    return 0


def cmd_export(args) -> int:
    """导出实验数据（CSV/JSON/Pickle，pandas 可加载）"""
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from experiment_exporter import export_all
    from datetime import datetime as _dt
    out = args.out or str(Path(__file__).parent / "data" / "experiments" /
                          _dt.now().strftime("%Y%m%d_%H%M%S"))
    r = export_all(out, formats=tuple(args.format))
    print(f"[OK] 导出完成 → {r['out_dir']}")
    for f in r["files"]:
        print(f"  {f}")
    print(f"  记录数: {r['records']}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="crypto_causal_agent — 自主因果推理型加密永续合约进化 Agent"
    )
    sub = parser.add_subparsers(dest="command")

    # check
    p_check = sub.add_parser("check", help="环境自检")
    p_check.set_defaults(func=cmd_check)

    # download
    p_dl = sub.add_parser("download", help="下载历史数据")
    p_dl.add_argument("--symbol", default="BTCUSDT")
    p_dl.add_argument("--start", default="2024-01-01")
    p_dl.add_argument("--end", default="2026-06-30")
    p_dl.add_argument("--intervals", nargs="+",
                      default=["1m", "5m", "15m", "1h", "4h", "1d"])
    p_dl.add_argument("--force", action="store_true", help="强制重新下载")
    p_dl.set_defaults(func=cmd_download)

    # backtest
    p_bt = sub.add_parser("backtest", help="单策略回测")
    p_bt.add_argument("--config", default="config/config.yaml")
    p_bt.add_argument("--env", default="bull", choices=["bull", "bear", "range", "extreme", "all"])
    p_bt.set_defaults(func=cmd_backtest)

    # evolve
    p_ev = sub.add_parser("evolve", help="运行进化实验")
    p_ev.add_argument("--config", default="config/config.yaml")
    p_ev.add_argument("--generations", type=int, default=3)
    p_ev.add_argument("--population", type=int, default=4)
    p_ev.add_argument("--resume", type=int, default=0, help="从第 N 代断点恢复")
    p_ev.set_defaults(func=cmd_evolve)

    # export
    p_ex = sub.add_parser("export", help="导出实验数据 (CSV/JSON/Pickle)")
    p_ex.add_argument("--out", default="", help="输出目录")
    p_ex.add_argument("--format", nargs="+", default=["csv", "json", "pickle"])
    p_ex.set_defaults(func=cmd_export)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
