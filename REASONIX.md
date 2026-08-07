# Crypto Causal Agent — Reasonix 专用指令

本项目运行在 Reasonix MCP 环境中。

## 行为规范
- AGENTS.md 中的规则自动适用（不可绕过/不可删除/不可模拟/不可检查设计）
- 破坏性命令（rm/prune/delete）必须先请求用户确认
- 用户说"继续"后直接写代码，不输出设计分析
- 遇到无法解决的问题，告诉用户需要什么，不自行替代

## 技术栈速查
- Shell: PowerShell（不是 bash）· 包管理: pip/pnpm · 容器: docker compose
- 核心依赖: langgraph, langchain, pydantic, chromadb, neo4j, deap, statsmodels 0.14.6
- 端口: PG-5432, TimescaleDB-5433, Neo4j-7687, Redis-6379, Backend-8699, Frontend-8700

## 服务启动
```powershell
# 数据库
cd D:\自己的项目\crypto_causal_agent
docker compose up -d

# Dashboard 后端
cd dashboard && python server.py

# Dashboard 前端
cd dashboard/frontend && pnpm dev
```
