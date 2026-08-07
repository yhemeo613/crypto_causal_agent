# Crypto Causal Agent

自主因果推理型加密永续合约进化 Agent — 纯离线仿真学术研究项目。

## 概述

构建一个 AI Agent，让 AI 像人类研究员一样——感知市场 → 理解因果 → 辩论推理 → 反事实推演 → 自主策略创新 → 自我复盘进化。

## 架构

```
L1 环境底座层    · 多交易所数据采集 · 本地撮合仿真 · 账户系统 · 硬风控
L2 仿真沙箱层    · 牛/熊/震荡/极端 四环境沙箱
L3 因果感知层    · 三时序切片 · LLM因果抽取 · Granger统计因果
L4 工具调度层    · 只读 · 计算 · 动作 三级权限工具
L5 复合记忆层    · 瞬时滑动窗口 · ChromaDB向量 · Neo4j因果图谱
L6 辩论决策层    · LangGraph 多空辩论 → 证伪 → 反事实 → 置信度仓位
L7 元进化控制层  · Python AST 双层基因 · DEAP 遗传进化 · 三级复盘
```

## 快速开始

```bash
# 1. 环境要求
Python 3.11+ · Docker Desktop · Node 20+ · pnpm

# 2. 克隆
git clone https://gitee.com/dzy_gitee/crypto_causal_agent.git
cd crypto_causal_agent

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 4. 安装 Python 依赖
pip install -r requirements.txt

# 5. 启动数据库
docker compose up -d

# 6. 运行自检
python main.py check

# 7. 下载历史数据（需要代理）
python main.py download

# 8. 启动 Dashboard
cd dashboard && python server.py &
cd dashboard/frontend && pnpm install && pnpm dev
```

## 运行测试

```bash
python tests/test_matching_engine.py   # 撮合引擎
python tests/test_account_risk.py      # 账户+风控
python tests/test_sandbox.py           # 四环境沙箱
python tests/test_perception.py        # 感知+因果抽取
python tests/test_memory.py            # 三层记忆融合
python tests/test_l6_decision.py       # LangGraph 全闭环决策
python tests/test_evolution.py         # 遗传进化引擎
```

## 技术栈

| 层 | 技术 |
|---|------|
| LLM | DeepSeek · LangGraph · LangChain |
| 数据 | ccxt · Binance/OKX/Bybit |
| 数据库 | PostgreSQL 18 · TimescaleDB · Neo4j 5 · Redis 7 · ChromaDB |
| 进化 | DEAP · Optuna · Python AST |
| 统计 | statsmodels · numpy · pandas |
| 前端 | Vue 3 · Pinia · Vite · ECharts |
| 基础设施 | Docker · pnpm |

## 文档

- [PRD.md](doc/PRD.md) — 产品需求文档
- [TDD.md](doc/TDD.md) — 技术设计文档

## 项目状态

- [x] Phase 1: 底座环境层
- [x] Phase 2: 因果感知层
- [x] Phase 3: 记忆检索层
- [x] Phase 4: 辩论决策层
- [x] Phase 5: 元进化层
