# 技术设计文档（TDD）

## 自主因果推理型加密永续合约进化 Agent

> **文档版本**：v1.0  
> **创建日期**：2026-08-06  
> **参考 PRD**：PRD.md v1.0  
> **项目代号**：crypto_causal_agent

---

## 目录

- [1. 关键决策回顾](#1-关键决策回顾)
- [2. 工程目录结构](#2-工程目录结构)
- [3. LangGraph 全局 State Schema](#3-langgraph-全局-state-schema)
- [4. 层间接口契约](#4-层间接口契约)
- [5. 数据库表结构设计](#5-数据库表结构设计)
- [6. 配置文件设计](#6-配置文件设计)
- [7. 日志与实验数据记录方案](#7-日志与实验数据记录方案)
- [8. 开发环境与 Docker 编排](#8-开发环境与-docker-编排)

---

## 1. 关键决策回顾

> 以下决策为技术方案设计的约束条件，所有设计均基于此。

| 决策 | 结论 |
|------|------|
| LLM 基座 | **DeepSeek 主力**（L6/L7 所有 Prompt 默认基于 DeepSeek） |
| 因果三元组抽取 | **LLM + 统计因果混合**（P0 用 LLM 抽取，P1 加 PC/Granger 增强） |
| 策略基因编码 | **Python AST 操作**（LLM 生成代码片段，`ast` 模块做交叉/变异） |
| 部署环境 | **单机 CPU + 外部 LLM API**（无 GPU，PyTorch CPU-only） |

---

## 2. 工程目录结构

```
crypto_causal_agent/
│
├── config/
│   ├── config.yaml                  # 主配置文件
│   └── prompts/                     # Agent Prompt 模板
│       ├── bull_debater.yaml        # 多头辩论 Agent Prompt
│       ├── bear_debater.yaml        # 空头辩论 Agent Prompt
│       ├── falsifier.yaml           # 证伪校验 Agent Prompt
│       ├── counterfactual.yaml      # 反事实推演 Agent Prompt
│       └── confidence_sizer.yaml    # 置信度仓位 Agent Prompt
│
├── src/
│   ├── __init__.py
│   │
│   ├── l1_env_base/                 # L1 环境底座层
│   │   ├── __init__.py
│   │   ├── data_collector.py        # 多源数据采集管道（币安/Glassnode/FRED）
│   │   ├── matching_engine.py       # 本地撮合仿真引擎（订单簿重建）
│   │   ├── account.py               # 仿真账户系统（余额/保证金/持仓/PNL）
│   │   └── risk_control.py          # 硬风控（最大回撤/单笔亏损/杠杆上限）
│   │
│   ├── l2_sandbox/                  # L2 仿真沙箱层
│   │   ├── __init__.py
│   │   ├── environment.py           # 四环境数据集构建器
│   │   ├── regime_classifier.py     # 市场 Regime 分类器（P1）
│   │   └── backtest_runner.py       # 回测运行器（单策略/单环境）
│   │
│   ├── l3_perception/               # L3 因果感知层
│   │   ├── __init__.py
│   │   ├── time_slicer.py           # 三时序切片感知（L1/L2/L3）
│   │   ├── causal_extractor.py      # 因果三元组抽取（LLM + 统计因果）
│   │   ├── statistical_causal.py    # 统计因果发现（PC/Granger, P1）
│   │   └── neo4j_writer.py          # Neo4j 因果图谱写入
│   │
│   ├── l4_tools/                    # L4 工具调度层
│   │   ├── __init__.py
│   │   ├── readonly_tools.py        # 只读工具集（数据查询类）
│   │   ├── compute_tools.py         # 计算工具集（指标计算类）
│   │   ├── action_tools.py          # 动作工具集（下单/调仓类）
│   │   ├── tool_planner.py          # 工具调用规划器（LLM 自主规划）
│   │   └── call_cache.py            # 工具调用缓存
│   │
│   ├── l5_memory/                   # L5 三层复合记忆系统
│   │   ├── __init__.py
│   │   ├── instant_memory.py        # 瞬时记忆管理（滑动窗口）
│   │   ├── case_vector_store.py     # 案例向量存储（ChromaDB）
│   │   ├── causal_graph_query.py    # 因果图谱查询（Neo4j）
│   │   ├── fusion_recaller.py       # 多路融合召回器（向量+图谱+结构化）
│   │   └── memory_cleaner.py        # 记忆自清洗器（P1）
│   │
│   ├── l6_agent/                    # L6 辩论多 Agent 决策层
│   │   ├── __init__.py
│   │   ├── state.py                 # LangGraph 全局 State 定义（Pydantic）
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── bull_debater.py      # 多头辩论 Agent
│   │   │   ├── bear_debater.py      # 空头辩论 Agent
│   │   │   ├── falsifier.py         # 证伪校验 Agent
│   │   │   ├── counterfactual.py    # 反事实推演 Agent
│   │   │   └── confidence_sizer.py  # 置信度仓位 Agent
│   │   ├── graph_builder.py         # LangGraph 流程编排（节点+边）
│   │   └── prompt_manager.py        # 角色专属 Prompt 管理器
│   │
│   └── l7_evolution/                # L7 元进化控制层
│       ├── __init__.py
│       ├── gene_encoder.py          # 双层基因编解码器（Python AST）
│       ├── gene_sandbox.py          # 基因代码安全沙箱
│       ├── evolution_engine.py      # 遗传进化引擎（选择/交叉/变异）
│       ├── llm_innovator.py         # LLM 创新基因生成器（P1）
│       ├── arena.py                 # 对抗竞技场（P1）
│       ├── replay_engines.py        # 三级复盘引擎
│       ├── meta_learner.py          # MAML 元学习加速（P1）
│       ├── knowledge_distiller.py   # 知识蒸馏器（P1）
│       ├── hpo_optimizer.py         # Auto-HPO 超参优化（P1）
│       └── generalization_penalty.py # 泛化惩罚计算器
│
├── db/                              # 数据库相关
│   ├── migrations/                  # PostgreSQL 迁移脚本
│   │   └── 001_init.sql
│   └── neo4j_init.cypher            # Neo4j 初始化脚本
│
├── experiments/                     # 实验配置与输出
│   ├── configs/                     # 实验配置文件
│   │   └── default_experiment.yaml
│   └── outputs/                     # 实验产出（gitignore）
│       ├── evolution_logs/
│       ├── trade_logs/
│       └── reports/
│
├── scripts/                         # 实验脚本
│   ├── run_evolution.py             # 启动完整进化实验
│   ├── run_ablation.py              # 消融实验脚本
│   └── export_paper_data.py         # 论文数据导出
│
├── tests/                           # 测试
│   ├── test_matching_engine.py
│   ├── test_risk_control.py
│   ├── test_causal_extractor.py
│   ├── test_memory_fusion.py
│   ├── test_agent_debate.py
│   └── test_gene_evolution.py
│
├── main.py                          # 主入口
├── requirements.txt                 # Python 依赖
├── docker-compose.yml               # Docker 编排（PostgreSQL/TimescaleDB/Neo4j/Redis）
├── Makefile                         # 常用命令快捷方式
└── README.md                        # 项目说明
```

---

## 3. LangGraph 全局 State Schema

基于 PRD 7.6 节，State 需在所有 Agent 节点间传递。使用 Pydantic v2 强类型约束。

```python
# src/l6_agent/state.py

from __future__ import annotations
from datetime import datetime
from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


# ─── 感知相关 ───────────────────────────────────────

class TimeSlice(BaseModel):
    """三时序切片之一"""
    level: str = Field(..., description="L1 | L2 | L3")
    start_ts: datetime
    end_ts: datetime
    kline_summary: dict = Field(default_factory=dict, description="OHLCV 统计摘要")
    technical_indicators: dict = Field(default_factory=dict)
    causal_events: list[dict] = Field(default_factory=list, description="该时段因果事件列表")


class PerceptionContext(BaseModel):
    """感知上下文（三个时间切片汇总）"""
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str = "BTCUSDT"
    l1_micro: Optional[TimeSlice] = None    # 近期微观
    l2_meso: Optional[TimeSlice] = None     # 中期结构
    l3_macro: Optional[TimeSlice] = None    # 长期宏观
    regime: str = "unknown"                 # 市场 Regime（P1）


# ─── 记忆召回相关 ───────────────────────────────────

class MemoryRecallResult(BaseModel):
    """多路融合召回结果"""
    case_matches: list[dict] = Field(default_factory=list, description="ChromaDB 案例向量匹配")
    causal_paths: list[dict] = Field(default_factory=list, description="Neo4j 因果路径")
    structured_data: list[dict] = Field(default_factory=list, description="PostgreSQL 结构化查询")
    merged: list[dict] = Field(default_factory=list, description="去重融合后的结果")
    decay_weights: list[float] = Field(default_factory=list, description="时间衰减权重")


# ─── 辩论相关 ───────────────────────────────────────

class DebateRecord(BaseModel):
    """一轮辩论记录"""
    agent_role: str = Field(..., description="bull | bear")
    arguments: list[str] = Field(default_factory=list, description="论点列表")
    evidence: list[dict] = Field(default_factory=list, description="证据（数据引用）")
    conclusion: str = ""                       # 结论


class FalsificationResult(BaseModel):
    """证伪校验结果"""
    is_falsified: bool = False
    falsifying_evidence: list[dict] = Field(default_factory=list)
    confidence_after_falsification: float = 0.0
    reasoning: str = ""


class CounterfactualPath(BaseModel):
    """一条反事实路径"""
    scenario: str = Field(..., description="假设场景描述")
    probability: float = Field(..., ge=0.0, le=1.0)
    expected_return: float = 0.0
    expected_risk: float = 0.0


class CounterfactualResult(BaseModel):
    """反事实推演结果"""
    paths: list[CounterfactualPath] = Field(default_factory=list)
    weighted_confidence: float = 0.0
    recommended_action: str = ""              # long | short | hold


# ─── 决策与仓位 ─────────────────────────────────────

class DecisionResult(BaseModel):
    """最终决策"""
    action: str = Field(default="hold", description="long | short | hold")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    position_size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    leverage: float = Field(default=1.0, ge=1.0, le=5.0)
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning_chain: str = ""                 # 完整推理链摘要


class Position(BaseModel):
    """当前持仓"""
    symbol: str = "BTCUSDT"
    side: str = ""                            # long | short
    size: float = 0.0
    entry_price: float = 0.0
    leverage: float = 1.0
    unrealized_pnl: float = 0.0
    margin: float = 0.0
    liquidation_price: float = 0.0


class AccountSnapshot(BaseModel):
    """账户快照"""
    balance: float = 0.0
    equity: float = 0.0
    available_margin: float = 0.0
    used_margin: float = 0.0
    positions: list[Position] = Field(default_factory=list)
    daily_pnl: float = 0.0
    total_pnl: float = 0.0


# ─── 全局 State ─────────────────────────────────────

class AgentState(BaseModel):
    """LangGraph 全局状态"""
    # 消息（add_messages 累加模式）
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # 感知
    perception: Optional[PerceptionContext] = None

    # 记忆召回
    memory_recall: Optional[MemoryRecallResult] = None

    # 辩论
    bull_debate: Optional[DebateRecord] = None
    bear_debate: Optional[DebateRecord] = None

    # 证伪
    falsification: Optional[FalsificationResult] = None

    # 反事实
    counterfactual: Optional[CounterfactualResult] = None

    # 决策
    decision: Optional[DecisionResult] = None

    # 账户
    account: Optional[AccountSnapshot] = None

    # 元数据
    cycle_id: int = 0                         # 当前决策循环编号
    timestamp: datetime = Field(default_factory=datetime.now)

    # 流程控制
    next_step: str = "perceive"               # 状态机：perceive → recall → debate → falsify → counterfactual → decide → execute

    # 错误
    errors: list[str] = Field(default_factory=list)
```

### State 流转

```
perceive → recall → debate → falsify → counterfactual → decide → execute → perceive (循环)
```

每个节点读取/写入 State 的对应字段，`next_step` 控制流转方向。节点间通过 LangGraph 的 `add_messages` 累加 LLM 消息历史。

---

## 4. 层间接口契约

### 4.1 数据流总览

```
L1 环境底座 ──→ L2 沙箱 ──→ L3 感知 ──→ L5 记忆 ──→ L6 决策 ──→ L4 工具 ──→ L1 撮合
                                     │              │              │
                                     └── Neo4j ─────┘              │
                                                                   │
                              L7 进化 ←── 复盘数据 ←───────────────┘
```

### 4.2 接口定义

#### L1 → L2

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `get_market_data(symbol, start, end)` | L1→L2 | `pd.DataFrame` (OHLCV + depth) | 沙箱请求行情数据 |
| `execute_order(order)` | L2→L1 | `OrderRequest → OrderResult` | 沙箱向撮合引擎下单 |
| `get_account()` | L2→L1 | `AccountSnapshot` | 沙箱查询账户状态 |

#### L2 → L3

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `get_environment_context()` | L2→L3 | `dict` (regime + env_meta) | 感知层获取当前环境上下文 |
| `get_market_snapshot(ts)` | L2→L3 | `MarketSnapshot` (OHLCV slice) | 感知层获取某时刻市场数据 |

#### L3 → L5

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `write_causal_triplets(triplets)` | L3→L5 | `list[CausalTriplet]` | 因果三元组写入 Neo4j |
| `get_perception_context(ts)` | L3→L6 | `PerceptionContext` | 感知上下文传递给决策层 |

#### L5 ↔ L6

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `recall(context)` | L6→L5→L6 | `MemoryRecallResult` | 决策层请求记忆召回 |
| `store_case(case)` | L6→L5 | `CaseRecord` | 决策后写入案例记忆 |
| `store_instant(context)` | L6→L5 | `InstantMemoryChunk` | 写入瞬时记忆 |

#### L6 → L4

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `plan_tools(context)` | L6→L4 | `ToolPlan` | LLM 自主规划工具调用 |
| `execute_tool(plan)` | L6→L4 | `ToolResult` | 执行工具（三级权限检查） |

#### L6 → L1（通过 L2）

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `submit_decision(DecisionResult)` | L6→L2→L1 | `DecisionResult → OrderRequest` | 决策→下单→撮合 |

#### L7 复盘数据

| 接口 | 方向 | 数据格式 | 说明 |
|------|------|---------|------|
| `get_trade_logs(cycle)` | L1→L7 | `list[TradeRecord]` | 进化层获取交易记录 |
| `get_decision_logs(cycle)` | L6→L7 | `list[DecisionLog]` | 进化层获取决策日志 |
| `update_gene(gene, fitness)` | L7→L5 | `GeneRecord` | 进化后的基因写入基因库 |

---

## 5. 数据库表结构设计

### 5.1 PostgreSQL + TimescaleDB（结构化数据）

```sql
-- db/migrations/001_init.sql

-- ─── 行情数据（TimescaleDB hypertable）───────────
CREATE TABLE klines (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      VARCHAR(20) NOT NULL,
    interval    VARCHAR(5) NOT NULL,    -- 1m,5m,15m,1h,4h,1d
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    quote_volume DOUBLE PRECISION,
    trades      INTEGER,
    PRIMARY KEY (ts, symbol, interval)
);
SELECT create_hypertable('klines', 'ts');

-- ─── 资金费率 ───────────────────────────────────
CREATE TABLE funding_rates (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      VARCHAR(20) NOT NULL,
    rate        DOUBLE PRECISION,
    PRIMARY KEY (ts, symbol)
);
SELECT create_hypertable('funding_rates', 'ts');

-- ─── 宏观数据 ───────────────────────────────────
CREATE TABLE macro_data (
    ts          TIMESTAMPTZ NOT NULL,
    source      VARCHAR(50) NOT NULL,   -- FRED, Glassnode
    indicator   VARCHAR(100) NOT NULL,  -- CPI, FFR, SOPR, MVRV...
    value       DOUBLE PRECISION,
    PRIMARY KEY (ts, source, indicator)
);
SELECT create_hypertable('macro_data', 'ts');

-- ─── 交易记录 ───────────────────────────────────
CREATE TABLE trades (
    id              SERIAL PRIMARY KEY,
    cycle_id        INTEGER NOT NULL,           -- 决策循环编号
    gene_id         VARCHAR(64),                -- 策略基因 ID
    symbol          VARCHAR(20) NOT NULL,
    side            VARCHAR(10) NOT NULL,       -- long | short
    entry_price     DOUBLE PRECISION,
    exit_price      DOUBLE PRECISION,
    size            DOUBLE PRECISION,
    leverage        DOUBLE PRECISION,
    entry_ts        TIMESTAMPTZ NOT NULL,
    exit_ts         TIMESTAMPTZ,
    pnl             DOUBLE PRECISION,
    pnl_pct         DOUBLE PRECISION,
    exit_reason     VARCHAR(50),               -- tp | sl | manual | liquidation
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_trades_cycle ON trades(cycle_id);
CREATE INDEX idx_trades_gene ON trades(gene_id);

-- ─── 决策日志 ───────────────────────────────────
CREATE TABLE decision_logs (
    id              SERIAL PRIMARY KEY,
    cycle_id        INTEGER NOT NULL,
    gene_id         VARCHAR(64),
    symbol          VARCHAR(20) NOT NULL,
    action          VARCHAR(10) NOT NULL,       -- long | short | hold
    confidence      DOUBLE PRECISION,
    position_size   DOUBLE PRECISION,
    debate_json     JSONB,                     -- 辩论完整记录
    falsification_json JSONB,                  -- 证伪完整记录
    counterfactual_json JSONB,                 -- 反事实完整记录
    reasoning_chain TEXT,                      -- 完整推理链
    prompt_json     JSONB,                     -- LLM prompt + response
    ts              TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_decision_logs_cycle ON decision_logs(cycle_id);

-- ─── 进化记录 ───────────────────────────────────
CREATE TABLE evolution_logs (
    id              SERIAL PRIMARY KEY,
    generation      INTEGER NOT NULL,
    gene_id         VARCHAR(64) NOT NULL,
    parent_gene_ids JSONB,                     -- 父代基因 ID 列表
    gene_code       TEXT,                      -- 基因代码（Python 片段）
    gene_params     JSONB,                     -- 参数层基因
    fitness         DOUBLE PRECISION,          -- 综合适应度
    env_performances JSONB,                    -- 四环境分别表现
    generalization_penalty DOUBLE PRECISION,   -- 泛化惩罚
    innovation_score DOUBLE PRECISION,         -- 创新性评分
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_evolution_logs_gen ON evolution_logs(generation);

-- ─── 复盘报告 ───────────────────────────────────
CREATE TABLE replay_reports (
    id              SERIAL PRIMARY KEY,
    level           VARCHAR(20) NOT NULL,       -- trade | strategy | generation
    cycle_id        INTEGER,
    gene_id         VARCHAR(64),
    generation      INTEGER,
    report_json     JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── 实验元数据 ───────────────────────────────────
CREATE TABLE experiments (
    id              SERIAL PRIMARY KEY,
    experiment_name VARCHAR(200) NOT NULL,
    config_json     JSONB NOT NULL,
    status          VARCHAR(20) DEFAULT 'running',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    notes           TEXT
);
```

### 5.2 Neo4j（因果图谱）

```cypher
-- db/neo4j_init.cypher

-- 约束
CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (f:Factor) REQUIRE f.name IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:Regime) REQUIRE r.name IS UNIQUE;

-- 索引
CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.type);
CREATE INDEX IF NOT EXISTS FOR ()-[c:CAUSES]-() ON (c.confidence);

-- 因果三元组示例: (Factor)-[:CAUSES {confidence, lag, source}]->(Event)
-- Factor: 宏观指标、链上数据、技术形态
-- Event:  价格变动、波动率变化、趋势转变
```

### 5.3 ChromaDB（向量记忆）

```
集合名称: case_memory
嵌入模型: text-embedding-3-small (OpenAI) 或 DeepSeek 兼容嵌入
向量维度: 1536
元数据结构:
{
    "case_id": str,
    "scene_summary": str,        # 场景描述（用于生成向量）
    "action": str,
    "pnl_pct": float,
    "timestamp": str,
    "gene_id": str,
    "regime": str,
    "confidence": float
}
```

---

## 6. 配置文件设计

### config.yaml

```yaml
# config/config.yaml

# ─── 项目基本信息 ───────────────────────────
project:
  name: crypto_causal_agent
  version: 0.1.0
  log_level: INFO
  seed: 42                           # 全局随机种子（可复现性）

# ─── LLM 配置 ───────────────────────────────
llm:
  provider: deepseek                 # deepseek | claude | openai
  model: deepseek-chat               # deepseek-v3 对应模型
  api_key: ${DEEPSEEK_API_KEY}       # 环境变量注入
  api_base: https://api.deepseek.com
  temperature: 0.0                   # 实验模式固定 0
  max_tokens: 4096
  timeout: 30                        # 秒
  retry: 3                           # 失败重试次数

# ─── 数据库连接 ────────────────────────────
database:
  postgresql:
    host: localhost
    port: 5432
    dbname: crypto_agent
    user: agent
    password: ${PG_PASSWORD}
    pool_size: 10
  neo4j:
    uri: bolt://localhost:7687
    user: neo4j
    password: ${NEO4J_PASSWORD}
  chromadb:
    path: ./data/chromadb             # 本地持久化路径
    collection: case_memory
  redis:
    host: localhost
    port: 6379
    db: 0

# ─── 数据采集 ──────────────────────────────
data:
  binance:
    symbols: [BTCUSDT]                # 可扩展
    kline_intervals: [1m, 5m, 15m, 1h, 4h, 1d]
    start_date: "2024-01-01"
    end_date: "2026-06-30"
    data_dir: ./data/raw
  glassnode:
    api_key: ${GLASSNODE_API_KEY}     # P0 如果有 Key
    metrics: [sopr, mvrv, puell]
  fred:
    api_key: ${FRED_API_KEY}
    series: [DFF, CPIAUCSL, UNRATE]   # 联邦基金利率/CPI/失业率

# ─── 撮合仿真 ──────────────────────────────
matching:
  initial_balance: 100000             # 初始资金（USDT）
  commission: 0.0004                  # 手续费 0.04%
  slippage_model: linear              # linear | square_root | fixed
  slippage_base: 0.0001               # 基础滑点
  funding_rate_interval_hours: 8      # 资金费率结算周期

# ─── 硬风控 ────────────────────────────────
risk_control:
  max_drawdown_pct: 0.30              # 最大回撤 30%
  max_position_pct: 0.95              # 最大持仓比例
  max_leverage: 5                     # 最大杠杆
  max_loss_per_trade_pct: 0.05        # 单笔最大亏损 5%
  max_daily_trades: 20                # 每日最大交易次数
  min_confidence_threshold: 0.4       # 最低置信度阈值

# ─── 四环境沙箱 ────────────────────────────
sandbox:
  environments:
    bull:
      date_range: ["2024-01-01", "2024-03-31"]
      description: "牛市环境"
    bear:
      date_range: ["2024-04-01", "2024-09-30"]
      description: "熊市环境"
    range:
      date_range: ["2024-10-01", "2025-01-31"]
      description: "震荡环境"
    extreme:
      date_range: ["2024-08-01", "2024-08-31"]
      description: "极端波动环境（如 8·5 暴跌）"

# ─── 感知 ──────────────────────────────────
perception:
  time_slices:
    l1:
      window_days: 1                  # 近期微观：1天
      kline_interval: 5m
    l2:
      window_days: 14                 # 中期结构：14天
      kline_interval: 1h
    l3:
      window_days: 90                 # 长期宏观：90天
      kline_interval: 1d
  causal_extraction:
    llm_provider: deepseek
    statistical_methods: [granger]    # P1 阶段加入 PC
    min_confidence: 0.3               # 因果边最低置信度

# ─── 记忆 ──────────────────────────────────
memory:
  instant_window_size: 10             # 瞬时记忆最近 N 步
  vector_top_k: 5                     # 向量检索 Top-K
  causal_depth: 3                     # 因果图谱查询深度
  decay_factor: 0.95                  # 时间衰减因子（每步）
  negative_sample_weight: 2.0         # 负样本权重倍率
  auto_clean_interval_hours: 24       # 记忆自清洗间隔

# ─── 进化 ──────────────────────────────────
evolution:
  population_size: 12                 # 每代策略数量
  generations: 30                     # 进化代数
  mutation_rate: 0.2                  # 变异率
  crossover_rate: 0.7                 # 交叉率
  selection_method: tournament        # tournament | roulette
  tournament_size: 3
  generalization_penalty_weight: 0.3  # 泛化惩罚权重
  elitism_count: 2                    # 精英保留数

# ─── 实验 ──────────────────────────────────
experiment:
  output_dir: ./experiments/outputs
  save_trade_logs: true
  save_decision_logs: true
  save_llm_prompts: true
  export_format: [csv, json, pickle]
```

---

## 7. 日志与实验数据记录方案

### 7.1 日志分层

| 层级 | 内容 | 存储 | 格式 |
|------|------|------|------|
| **系统日志** | 模块运行状态、错误、警告 | `logs/system.log` | 结构化 JSON 行 |
| **决策日志** | 每笔交易的完整推理链 | PostgreSQL `decision_logs` | JSONB |
| **交易日志** | 撮合结果、账户变动 | PostgreSQL `trades` | 行 |
| **进化日志** | 基因演化、适应度变化 | PostgreSQL `evolution_logs` | 行 + JSONB |
| **LLM 日志** | 每次 LLM 调用的 prompt + response | `logs/llm/{date}/{cycle_id}.jsonl` | JSONL |

### 7.2 日志库配置

使用 Python `structlog` 做结构化日志：

```python
# 示例配置
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),          # 开发环境彩色输出
        # structlog.processors.JSONRenderer(),    # 生产环境 JSON
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```

### 7.3 实验数据导出

`scripts/export_paper_data.py` 导出内容：

1. **进化曲线 CSV**：`generation, fitness, sharpe, max_drawdown, ...`
2. **消融对比 CSV**：`module, enabled, sharpe_mean, sharpe_std, ...`
3. **决策日志 JSON**：完整推理链（可导入 Jupyter Notebook 分析）
4. **账户净值曲线 CSV**：`timestamp, equity, balance, pnl`
5. **统计检验结果 CSV**：`comparison, t_statistic, p_value, effect_size`

---

## 8. 开发环境与 Docker 编排

### docker-compose.yml

```yaml
version: "3.8"

services:
  postgres:
    image: timescale/timescaledb:2.16-pg16
    environment:
      POSTGRES_DB: crypto_agent
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${PG_PASSWORD:-agent123}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/migrations:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent -d crypto_agent"]
      interval: 5s
      retries: 5

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-neo4j123}
    ports:
      - "7474:7474"   # HTTP
      - "7687:7687"   # Bolt
    volumes:
      - neo4jdata:/data
      - ./db/neo4j_init.cypher:/docker-entrypoint-initdb.d/init.cypher
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD:-neo4j123}", "RETURN 1"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
  neo4jdata:
```

### requirements.txt

```
# 核心框架
langgraph==0.1.*
langchain==0.2.*
langchain-core==0.2.*
pydantic==2.*

# LLM
openai==1.*                       # DeepSeek 兼容 OpenAI SDK
langchain-openai==0.1.*

# 数据处理
pandas==2.*
numpy==1.*
TA-Lib==0.4.*

# 数据库
psycopg2-binary==2.9.*
chromadb==0.5.*
neo4j==5.*
redis==5.*

# 数据采集
python-binance==1.*
ccxt==4.*
fredapi==0.5.*

# 进化算法
deap==1.4.*
optuna==3.5.*

# 元学习
torch==2.*                        # CPU-only

# 统计与因果
statsmodels==0.14.*               # Granger 因果检验
networkx==3.*                     # 因果图辅助

# 实验与日志
structlog==24.*
pyyaml==6.*
joblib==1.*

# 测试
pytest==8.*
pytest-asyncio==0.*
```

---

> **文档结束**  
> 本 TDD 将在技术评审会议后更新。所有设计均基于 PRD v1.0 和已确认的四个关键决策。
