# crypto_causal_agent

自主因果推理型加密永续合约进化 Agent —— 纯离线仿真学术研究项目。

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制环境变量文件并填入 API Key
copy .env.example .env

# 4. 环境自检
python main.py check

# 5. 启动数据库（需要 Docker）
docker compose up -d

# 6. 下载历史数据
python main.py download --symbol BTCUSDT

# 7. 运行单策略回测
python main.py backtest --env bull

# 8. 运行进化实验
python main.py evolve --generations 30
```

## 架构

```
L1 环境底座 → L2 仿真沙箱 → L3 因果感知 → L5 复合记忆 → L6 辩论决策 → L7 元进化
                                      ↘ L4 工具调度 ↗
```

详见 [PRD.md](../agent学习/PRD.md) 和 [TDD.md](../agent学习/TDD.md)。

## 技术栈

Python 3.11+ · LangGraph · LangChain · Pydantic v2 · DEAP · Optuna · PyTorch · ChromaDB · Neo4j · PostgreSQL/TimescaleDB · Redis
