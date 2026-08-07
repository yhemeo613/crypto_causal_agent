# Crypto Causal Agent — AI 行为指导

## 项目身份
自主因果推理型加密永续合约进化 Agent，纯离线仿真学术研究项目。
七层架构：数据采集(L1) → 沙箱(L2) → 因果感知(L3) → 工具调度(L4) → 记忆(L5) → 辩论决策(L6) → 进化(L7)。

## 核心规则

### 不可绕过
- PRD/TDD 中设计的组件必须实现，不可用替代方案
- 遇到组件不可用时，告知用户需要什么，由用户决定

### 不可删除
- Docker 镜像、容器、volume、文件、数据，未经用户确认一律不许删
- `docker rm`、`docker rmi`、`docker image prune`、`docker system prune`、`Remove-Item` 等破坏性命令必须先问

### 不可模拟
- 不能用模拟数据替代真实数据
- 不能因为网络不通就跳过下载步骤
- 测试必须用真实组件跑通

### 不可检查设计
- 用户说"继续"/"进入"后，直接写代码；不输出冗长设计分析

### 遇到问题
- 先定位根因，能修就修
- 修不了就告诉用户具体缺什么，让用户决定下一步

## 技术决策
- LLM: DeepSeek 主力
- 因果抽取: LLM + 统计因果混合
- 策略基因: Python AST 操作
- 部署: 单机 CPU + 外部 LLM API

## 常用命令
```bash
python main.py check              # 环境自检
python main.py download           # 下载数据
docker compose up -d              # 启动数据库
python tests/test_l6_decision.py  # 全闭环决策测试
```
