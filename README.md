# Crypto Causal Agent — 自主因果推理型加密永续合约进化 Agent

> 一个**纯离线仿真**的学术研究型自主 Agent：用**因果推理**理解市场，用**多 Agent 辩论**做决策，用**遗传进化**自我改进——全程不碰真实资金，产出可复现、可解释、可导出的实验数据。

---

## 目录

- [1. 我们想干什么](#1-我们想干什么)
- [2. 核心架构：七层流水线](#2-核心架构七层流水线)
- [3. 十大创新点](#3-十大创新点)
- [4. 全闭环决策周期（Agent 每 2 分钟做什么）](#4-全闭环决策周期agent-每-2-分钟做什么)
- [5. 技术栈](#5-技术栈)
- [6. 目录结构](#6-目录结构)
- [7. 数据库设计（双库 + 图谱 + 向量）](#7-数据库设计双库--图谱--向量)
- [8. 快速开始](#8-快速开始)
- [9. 使用指南](#9-使用指南)
- [10. Dashboard Agent 工作台](#10-dashboard-agent-工作台)
- [11. API 参考](#11-api-参考)
- [12. 实验能力矩阵](#12-实验能力矩阵)
- [13. 配置说明](#13-配置说明)
- [14. 测试](#14-测试)
- [15. 常见问题](#15-常见问题)
- [16. 路线图](#16-路线图)

---

## 1. 我们想干什么

**一句话**：打造一个能"看懂因果、自主辩论、自我进化"的加密永续合约交易 Agent，并让它的一切行为可被科学研究。

传统量化策略是"规则堆砌"，LLM Agent 是"黑盒提示词"。本项目把两者缝合，并加上**因果**与**进化**两条学术主线：

| 维度 | 传统量化 | 本项目 |
|------|---------|--------|
| 认知 | 指标信号 | **因果图谱**（谁导致谁，置信度几何） |
| 决策 | 单一规则 | **多 Agent 辩论 + 证伪 + 反事实推演** |
| 进化 | 人工调参 | **策略基因遗传进化**（逻辑层 + 参数层双层基因） |
| 记忆 | 数据库回放 | **三层复合记忆**（瞬时 + 向量案例 + 因果图谱） |
| 验证 | 单一牛市回测 | **四环境泛化沙箱**（牛/熊/震荡/极端） |

**产品边界**：
- ✅ 做：离线仿真、因果抽取、辩论决策、策略进化、消融实验、论文级数据导出
- ❌ 不做：真实下单、实盘资金、高频交易（纯学术研究）

---

## 2. 核心架构：七层流水线

```
┌─────────────────────────────────────────────────────────────────┐
│                        L7 元进化控制层                            │
│  遗传进化(DEAP) · 双层基因(AST逻辑+参数) · HPO · 竞技场 · 蒸馏 · 元学习 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 策略基因 / 复盘
┌──────────────────────────────▼──────────────────────────────────┐
│                        L6 辩论多Agent决策层                       │
│  多空并行辩论 → 证伪校验 → 反事实推演 → 置信度仓位决策 · Regime 自适应  │
└──────────────┬───────────────────────────────┬──────────────────┘
               │ 决策                        │ 工具调用（三级权限）
┌──────────────▼──────────────┐  ┌────────────▼──────────────────┐
│      L5 三层复合记忆          │  │        L4 工具调度层            │
│ 瞬时记忆 · ChromaDB向量案例  │  │ 只读(READ) · 计算(CALC) ·      │
│ · Neo4j 因果图谱              │  │ 动作(ACT，需辩论门禁)          │
└──────┬───────────────────────┘  └────────────┬──────────────────┘
       │ 召回                         │ 数据/指标
┌──────▼───────────────────────┐  ┌────────────▼──────────────────┐
│      L3 多源因果感知层          │  │        L2 仿真沙箱层           │
│ L1/L2/L3 三时序切片 ·          │  │ 四环境(牛/熊/震荡/极端) ·       │
│ 统计因果 + LLM 因果抽取 ·       │  │ 撮合引擎 · 账户系统 · 硬风控     │
│ Granger · 异常检测             │  │ 爆仓/强平/手续费 仿真          │
└──────┬───────────────────────┘  └────────────┬──────────────────┘
       │ K线/费率/宏观                 │ 订单/成交
┌──────▼──────────────────────────────────────▼──────────────────┐
│                     L1 数据与持久层                              │
│ 多交易所采集(Binance/OKX/Bybit) · FRED · CoinGecko · Fear&Greed · │
│ 本地 PG(业务) + TimescaleDB(时序) + Neo4j + ChromaDB + Redis     │
└─────────────────────────────────────────────────────────────────┘
```

**层间数据流**：`L1 数据 → L3 感知（因果抽取写 Neo4j）→ L5 记忆召回 → L6 辩论决策 → L4 工具取数 → L2 撮合执行 → 复盘 → L7 进化 → 新基因回到 L6`

---

## 3. 十大创新点

| # | 创新点 | 落地位置 |
|---|--------|---------|
| 1 | **因果图谱推理**替代浅层向量 RAG（谁导致谁，置信度 0~1） | L3 / L5 |
| 2 | **多 Agent 辩论证伪**推理架构（Bull/Bear 并行辩论 + 证伪） | L6 |
| 3 | **反事实行情双路径推演**（"如果走势不同会怎样"） | L6 |
| 4 | **双层策略基因**（Python AST 逻辑基因 + 参数基因）进化 | L7 |
| 5 | **三级分层复盘**（trade / generation / experiment 级） | L7 |
| 6 | **时间衰减 + 负样本加权**融合召回 | L5 |
| 7 | **市场 Regime 元自适应**（趋势/震荡/高波动动态调参） | L3 / L6 |
| 8 | **工具调用自主规划 + 记忆纠偏**（LLM 规划工具序列） | L4 |
| 9 | **置信度动态仓位**机制（置信度 → 仓位缩放） | L6 |
| 10 | **多环境泛化抗过拟合沙箱**（四环境 + 泛化惩罚） | L2 / L7 |

---

## 4. 全闭环决策周期（Agent 每 2 分钟做什么）

点击 Dashboard「启动 Agent」后，后台循环每 **120 秒**执行一轮完整闭环：

```
① 感知切片      → 从 TimescaleDB 拉真实 K 线，构建 L1(5m)/L2(1h)/L3(1d) 三时序切片
② 因果抽取      → 统计(Granger/相关) + LLM 混合抽取因果三元组 → 写入 Neo4j 图谱
③ 工具取数      → 经 L4 工具注册表调用 7 个真实工具（K线/费率/宏观/指标/图谱）
④ 记忆召回      → FusionRecaller 三路融合：瞬时记忆 + ChromaDB 向量案例 + 因果路径
⑤ 并行辩论      → Bull / Bear 两个 LLM Agent 线程并行论证（P2-02 提速 50%）
⑥ 证伪校验      → 挑战多头假设，计算置信度衰减
⑦ 反事实推演    → "如果走势不同" 双路径情景
⑧ 最终决策      → action(long/short/hold) + confidence + position_size + leverage
⑨ 落库          → decision_logs(本地PG) + 案例向量(ChromaDB) + 瞬时记忆
⑩ 执行(非hold) → 硬风控检查 → 市价单撮合(滑点/手续费) → 持仓/爆仓/平仓 → trades 表
⑪ 复盘          → replay_reports 逐周期写入，供 L7 进化
```

> 决策全部基于**真实数据**（176 万根 K 线、2849 条资金费率、FRED/CoinGecko 宏观），LLM 真实调用 DeepSeek。

---

## 5. 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.12（numpy 1.26 wheel 要求 ≤3.12） |
| Agent 编排 | LangGraph（State 图 + 并行节点） |
| LLM | DeepSeek-chat（可切换 OpenAI/Claude，`llm_config.py` 统一分派） |
| 数据库 | 本地 PostgreSQL 18（业务库 5432）+ Docker TimescaleDB PG17（时序库 5433）+ Neo4j 5（因果图谱）+ ChromaDB（向量记忆）+ Redis 7 |
| 进化 | DEAP + 自研 AST 双层基因 + Optuna（HPO）+ PyTorch CPU（MAML 元学习） |
| 统计 | statsmodels（Granger/协整）、numpy/pandas/pyarrow |
| 回测 | 自研撮合引擎（滑点/手续费/爆仓/强平） |
| 前端 | Vue 3 + Vite + Naive UI + ECharts(+GL) + lightweight-charts + GSAP + Pinia + Sass |
| 后端 | FastAPI + WebSocket（长任务调度 + 实时日志流） |

---

## 6. 目录结构

```
crypto_causal_agent/
├── main.py                  # CLI 入口：check / download / backtest / evolve / export
├── config/config.yaml       # 全部配置（数据库/LLM/环境/风控/进化）
├── docker-compose.yml       # timescaledb(5433) + neo4j(7474/7687) + redis(6379)
├── db/migrations/           # SQL 初始化（hypertable + 业务表）
├── src/                     # 核心源码
│   ├── l1_env_base/         # L1 数据层：采集器/撮合引擎/账户/风控/数据导入
│   ├── l2_sandbox/          # L2 沙箱：四环境注册/Regime 数据驱动分类
│   ├── l3_perception/       # L3 感知：time_slicer / causal_extractor / anomaly_detector
│   ├── l4_tools/            # L4 工具：tool_registry(三级权限) / planner(LLM规划)
│   ├── l5_memory/           # L5 记忆：instant / case_vector / causal_graph / fusion / cleaner
│   ├── l6_agent/            # L6 决策：graph_builder / debate_agents / prompt_manager / regime_adapter
│   ├── l7_evolution/        # L7 进化：engine / gene_encoder / auto_hpo / arena / meta_learner / knowledge_distiller / convergence_analysis
│   ├── db_conn.py           # 双库连接统一入口（pg_* 业务 / ts_* 时序）
│   ├── llm_config.py        # LLM provider 分派（deepseek/openai/claude）
│   ├── config_utils.py      # 配置读取
│   ├── ablation_framework.py# 消融实验框架（7 创新点开关）
│   └── experiment_exporter.py # 论文级数据导出（CSV/JSON/Pickle）
├── dashboard/               # Agent 工作台
│   ├── server.py            # FastAPI 后端（51 端点 + WebSocket + 长任务 + Agent 循环）
│   ├── dashboard_stats.py   # 双库健康统计
│   └── frontend/            # Vue3 前端（11 页面）
├── tests/                   # 86 个测试（14 文件）
├── data/                    # 数据（raw parquet / chromadb / 实验导出）
└── doc/                     # PRD.md / TDD.md / FRONTEND_WORKBENCH.md
```

---

## 7. 数据库设计（双库 + 图谱 + 向量）

项目采用 **双库拆分**：业务数据与时序数据物理分离。

| 存储 | 端口 | 内容 | 说明 |
|------|------|------|------|
| **本地 PostgreSQL 18** | 5432 | 业务表：`decision_logs` `evolution_logs` `trades` `replay_reports` `knowledge_rules` `experiments` | 密码 `admin`，库 `crypto_agent` |
| **Docker TimescaleDB PG17** | 5433 | 时序表：`klines`(176万+) `funding_rates` `macro_data`（3 个 hypertable） | 库 `crypto_agent` |
| **Neo4j 5** | 7687 | 因果图谱：`Event` 节点 + `CAUSES` 关系（置信度/证据/时间戳） | 决策周期自动写入 |
| **ChromaDB** | 内嵌 | 交易案例向量记忆（`case_memory`） | 每周期自动累积 |
| **Redis 7** | 6379 | 任务队列/缓存 | |

> **为什么双库**：时序数据（K 线）量大且需要时间分区（TimescaleDB hypertable 压缩/分区），业务数据（决策/进化）需要传统关系语义与事务——各归其位，互不拖累。

**核心表**：
```
klines(ts, symbol, interval, o/h/l/c, volume)        -- hypertable
funding_rates(ts, symbol, rate)                      -- hypertable
macro_data(ts, indicator, value, source)             -- hypertable
decision_logs(id, cycle_id, action, confidence, debate_json, ...)
evolution_logs(id, generation, gene_id, gene_params(jsonb), fitness, ...)
trades(id, symbol, side, size, entry, exit, pnl, ...)
replay_reports(level, cycle_id, report_json)         -- trade/generation/experiment 三级
knowledge_rules(gene_id, rule_json, fidelity)        -- 蒸馏出的可解释规则
```

---

## 8. 快速开始

### 8.1 环境要求

- Windows / Linux / macOS
- Python **3.12**（⚠️ 3.13 装不了 numpy 1.26 wheel）
- Docker Desktop
- Node.js 18+ / pnpm

### 8.2 第一步：创建虚拟环境并安装全部依赖

```bash
# 必须用 Python 3.12
python3.12 -m venv .venv

# Windows (Git Bash / PowerShell)
source .venv/Scripts/activate
# Linux/macOS
# source .venv/bin/activate

# 严格按 requirements.txt 完整安装（147 个包，不跳过）
pip install -r requirements.txt
```

> 疑难：`TMP/TEMP` 指向短路径（如 `C:\tmp`）避免 pip 长路径 260 字符报错。

### 8.3 第二步：配置 .env（敏感凭证）

```env
# 复制 .env.example（如存在）或手动创建，填入真实凭证
DEEPSEEK_API_KEY=sk-xxx          # 主力 LLM（必填）
PG_PASSWORD=admin                # 本地 PG 5432 密码
NEO4J_PASSWORD=neo4j123          # Neo4j 密码
FRED_API_KEY=xxx                 # 宏观数据（免费注册）
GLASSNODE_API_KEY=               # 收费服务，留空即可（免费 Fear&Greed 替代已内置）
# HTTP_PROXY=http://127.0.0.1:7890   # 如网络受限
```

### 8.4 第三步：启动数据库（Docker）

```bash
docker compose up -d
# 启动 3 个容器：timescaledb(5433) / neo4j(7474,7687) / redis(6379)
```

**本地 PG（5432）**：需自行安装 PostgreSQL 18（`D:/PostgreSQL/18`），创建库与业务表：

```bash
# 首次：建库 + 建业务表（6 张：decision/evolution/trades/replay/rules/experiments）
psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE crypto_agent"
# 业务表结构由程序首次运行时自动建表（db/migrations + 幂等创建）
```

### 8.5 第四步：环境自检 + 下载数据

```bash
python main.py check        # 环境自检（依赖/模块/数据库连通）
python main.py download     # 下载 K线/费率/宏观/情绪（约 176 万根 1m K线）
```

### 8.6 第五步：启动 Agent 工作台

```bash
# 后端（端口 8699，AUTO_START_AGENT=1 开机自动启动决策循环）
cd dashboard && AUTO_START_AGENT=1 ../.venv/Scripts/python.exe server.py

# 前端（端口 8700）
cd dashboard/frontend && pnpm install && pnpm dev
```

浏览器打开 **http://localhost:8700** → 点击「启动 Agent」→ 全自动闭环开始。

---

## 9. 使用指南

### CLI 命令

```bash
python main.py check                     # 环境自检
python main.py download                  # 下载数据（可 --force 重下）
python main.py backtest --env all        # 四环境单策略回测
python main.py evolve --generations 30   # 跑 30 代进化实验
python main.py export --format csv json pickle   # 导出论文级实验数据
```

### 关键实验流程

**1. 进化一个策略**：`python main.py evolve --generations 30 --population 12` → 每代四环境回测评估 → 遗传进化（锦标赛选择/交叉/变异）→ 写入 evolution_logs + 收敛分析。

**2. 消融实验**（学术论文核心）：`src/ablation_framework.py` 提供 7 个创新点开关（因果图谱/辩论/证伪/反事实/记忆融合/Regime 自适应/置信度仓位），逐项关闭对比决策差异。

**3. 超参搜索**：Dashboard 进化页「HPO」或 `POST /api/hpo/start`（Optuna 贝叶斯，6 维参数空间，真实回测目标）。

**4. 对抗竞技场**：`POST /api/arena/start` 多基因四环境对抗排名，胜者进入下一代。

**5. 知识蒸馏**：`POST /api/distill` 把最优基因蒸馏为可解释 if-then 规则（knowledge_rules + fidelity）。

**6. 元学习**：`POST /api/meta/train` + `/api/meta/compare`（MAML 式快速初始化，对比随机初始化）。

---

## 10. Dashboard Agent 工作台

11 个页面，全部对接真实 API：

| 页面 | 核心能力 |
|------|---------|
| **总览** | 七层决策管道状态 / KPI / LAST DECISION / 数据库健康 / Regime 徽标 |
| **数据** | 数据源管理 / 专业 K 线（lightweight-charts）/ 增量采集 / 新鲜度 |
| **感知因果** | 三时序切片 / **因果图谱（Neo4j 力导向图 + 演化时间轴）** / Granger / 异常事件 / Regime 策略表 |
| **记忆** | 向量案例召回 / 瞬时记忆 / 因果路径 |
| **决策实验室** | 手动跑全闭环 / 辩论回放 / 决策流时间轴 |
| **回测沙箱** | 四环境回测 / 绩效摘要 |
| **进化** | 进化曲线(3D) / **收敛性分析** / **实验版本对比** / 种群浏览器 / 进化树 |
| **账户风控** | 权益曲线 / 交易记录 / 硬风控规则 |
| **自动化** | 定时任务（增量采集/记忆清洗/自动决策） |
| **监控** | 系统健康 / 数据新鲜度 / **知识库蒸馏规则** / **工具调用日志** / 实时日志流(WebSocket) |
| **设置** | 配置可视化 / 密钥状态（env 占位符真实解析）/ LLM provider |

---

## 11. API 参考

后端 FastAPI 运行于 `http://localhost:8699`，共 50+ 端点：

```
Agent:      POST /api/agent/{start,pause,resume}   GET /api/agent/status
数据:        GET /api/klines /api/data/{sources,latest}   POST /api/data/{collect,import}
感知:        GET /api/perception/{slices,granger,graph-evolution}  GET /api/causal/graph
记忆:        GET /api/memory/recall   POST /api/memory/clean
决策:        POST /api/decision/run
回测:        POST /api/backtest/run   GET /api/backtest/result
进化:        POST /api/evolution/start   GET /api/evolution/{curve,population,convergence,tree}
实验:        GET /api/experiments   GET /api/experiments/compare
工具:        GET /api/tools   POST /api/tools/{call,plan}
创新:        POST /api/hpo/start /api/arena/start /api/llm-gene/generate /api/distill /api/meta/{train,compare}
系统:        GET /api/{health,db,architecture,config,logs,tasks}   WS /ws
```

交互式文档：`http://localhost:8699/docs`（Swagger UI）。

---

## 12. 实验能力矩阵

| 能力 | 模块 | 状态 |
|------|------|------|
| P0 因果图谱激活（统计+LLM → Neo4j） | causal_extractor | ✅ |
| P0 全闭环（决策→撮合→复盘→记忆） | server.py | ✅ |
| P0-11 工具调度（三级权限+门禁） | l4_tools | ✅ |
| P1 记忆自清洗 / 导出 / 消融 / 异常检测 | l5/ablation | ✅ |
| P1-12 Auto-HPO（Optuna） | auto_hpo | ✅ |
| P1-01 对抗竞技场 | arena | ✅ |
| P1-02 LLM 创新基因生成（novelty 过滤） | llm_gene_generator | ✅ |
| P1-11 知识蒸馏（基因→规则） | knowledge_distiller | ✅ |
| P1-10 MAML 元学习（torch） | meta_learner | ✅ |
| P2 并行辩论 / 收敛分析 / 向量化回测(12x) / 实验版本管理 / 图谱演化 | 各模块 | ✅ |
| 免费数据源（Fear&Greed 替代收费 Glassnode） | data_collector | ✅ |

---

## 13. 配置说明

### config.yaml 关键段

```yaml
llm:      # provider: deepseek|openai|claude, model, api_key(${ENV}占位符)
database:
  postgresql: {port: 5432}   # 业务库（本地）
  timescaledb: {port: 5433}  # 时序库（docker）
  neo4j: {uri: bolt://localhost:7687}
data:
  kline_intervals: [1m,5m,15m,1h,4h,1d]
  glassnode: {enabled: false}      # 收费，默认关闭
  fear_greed: {enabled: true}      # 免费情绪指标
matching:   # 手续费 0.0004 / 滑点 / 初始保证金率
risk_control:  # min_confidence 0.4 / max_leverage 5.0 / 单笔风险上限
sandbox:
  environments:  # bull/bear/range/extreme 四环境日期区间（数据驱动 Regime 分类）
evolution:  # population_size / generations / mutation_rate / crossover_rate / tournament_size / elitism_count
perception:  # 三时序切片窗口
memory:     # 向量 top_k / 衰减系数
```

> `${VAR}` 占位符在 `/api/config` 返回时自动解析为环境变量实际值（未配置显示空，前端据此判定密钥状态）。

---

## 14. 测试

```bash
# 全量 86 个测试（约 60s）
python -m pytest tests/ -q

# 单模块
python -m pytest tests/test_l6_decision.py -q   # 全闭环决策（真实 DeepSeek）
python -m pytest tests/test_arena.py -q         # 对抗竞技场
python -m pytest tests/test_anomaly_detector.py -q
```

测试覆盖：数据库连通（PG/Neo4j/Chroma/Redis）、因果抽取、融合记忆、决策图、进化引擎、Regime 自适应、消融、异常检测、元学习、竞技场。

---

## 15. 常见问题

**Q1：为什么必须 Python 3.12？**
numpy 1.26.4 的 wheel 只支持 ≤3.12；3.13 只能源码编译（缺 MSVC 工具链会失败）。用 3.12 直接装二进制 wheel。

**Q2：K 线数据从哪里来？**
`python main.py download` 从 Binance/OKX/Bybit 多交易所拉取（含故障切换），落 `data/raw/*.parquet`；再经 `data_loader.import_all()` 导入 TimescaleDB。

**Q3：Glassnode 显示未配置会影响什么？**
不影响。Glassnode 高级指标收费，项目内置免费替代（Alternative.me Fear&Greed 情绪指数，无需 Key）。

**Q4：为什么决策大多是 hold？**
置信度阈值 0.4（config `risk_control.min_confidence`），LLM 决策置信度低于阈值不开仓——这是硬风控的设计（宁可错过不可错开）。

**Q5：数据库端口记不住？**
业务=5432（本地）、时序=5433（docker）、Neo4j=7687、Redis=6379、后端=8699、前端=8700。

**Q6：进化 fitness 为什么是 0 或负数？**
fitness = 平均夏普 × (1 − 泛化惩罚)，保留真实值（含负）；负收益基因在排序中自然靠后，不参与选择。0 表示最优基因不赚不亏——真实回测结果。

---

## 16. 路线图

- [x] **P0 全部 15 项**：七层架构落地、因果图谱激活、全闭环、工具调度、硬风控
- [x] **P1 全部 13 项**：消融/蒸馏/元学习/HPO/竞技场/LLM 基因/异常检测/记忆清洗/导出
- [x] **P2 8/8**：并行辩论/收敛分析/向量化回测/实验版本/图谱演化（多交易对按需扩展）
- [x] **工作台 11 页**：数据/感知/记忆/决策/回测/进化/账户/自动化/监控/设置
- [ ] 多交易对自主发现（当前专注 BTCUSDT）
- [ ] 更多免费链上数据源（CoinPaprika 等）
- [ ] 策略基因库跨项目迁移

---

> **免责声明**：本项目为纯离线仿真学术研究，不构成任何投资建议，不涉及真实资金交易。
> 详细设计见 [`doc/PRD.md`](doc/PRD.md)（产品需求）与 [`doc/TDD.md`](doc/TDD.md)（技术设计）。
