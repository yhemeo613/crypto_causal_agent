-- crypto_causal_agent 数据库初始化
-- TimescaleDB hypertable 自动分区

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;-- 行情数据
CREATE TABLE IF NOT EXISTS klines (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      VARCHAR(20) NOT NULL,
    interval    VARCHAR(5) NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    quote_volume DOUBLE PRECISION,
    trades      INTEGER,
    PRIMARY KEY (ts, symbol, interval)
);
SELECT create_hypertable('klines', 'ts', if_not_exists => TRUE);

-- 资金费率
CREATE TABLE IF NOT EXISTS funding_rates (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      VARCHAR(20) NOT NULL,
    rate        DOUBLE PRECISION,
    PRIMARY KEY (ts, symbol)
);
SELECT create_hypertable('funding_rates', 'ts', if_not_exists => TRUE);

-- 宏观数据
CREATE TABLE IF NOT EXISTS macro_data (
    ts          TIMESTAMPTZ NOT NULL,
    source      VARCHAR(50) NOT NULL,
    indicator   VARCHAR(100) NOT NULL,
    value       DOUBLE PRECISION,
    PRIMARY KEY (ts, source, indicator)
);
SELECT create_hypertable('macro_data', 'ts', if_not_exists => TRUE);

-- 交易记录
CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    cycle_id        INTEGER NOT NULL,
    gene_id         VARCHAR(64),
    symbol          VARCHAR(20) NOT NULL,
    side            VARCHAR(10) NOT NULL,
    entry_price     DOUBLE PRECISION,
    exit_price      DOUBLE PRECISION,
    size            DOUBLE PRECISION,
    leverage        DOUBLE PRECISION,
    entry_ts        TIMESTAMPTZ NOT NULL,
    exit_ts         TIMESTAMPTZ,
    pnl             DOUBLE PRECISION,
    pnl_pct         DOUBLE PRECISION,
    exit_reason     VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id);
CREATE INDEX IF NOT EXISTS idx_trades_gene ON trades(gene_id);

-- 决策日志
CREATE TABLE IF NOT EXISTS decision_logs (
    id              SERIAL PRIMARY KEY,
    cycle_id        INTEGER NOT NULL,
    gene_id         VARCHAR(64),
    symbol          VARCHAR(20) NOT NULL,
    action          VARCHAR(10) NOT NULL,
    confidence      DOUBLE PRECISION,
    position_size   DOUBLE PRECISION,
    debate_json     JSONB,
    falsification_json JSONB,
    counterfactual_json JSONB,
    reasoning_chain TEXT,
    prompt_json     JSONB,
    ts              TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decision_logs_cycle ON decision_logs(cycle_id);

-- 进化记录
CREATE TABLE IF NOT EXISTS evolution_logs (
    id              SERIAL PRIMARY KEY,
    generation      INTEGER NOT NULL,
    gene_id         VARCHAR(64) NOT NULL,
    parent_gene_ids JSONB,
    gene_code       TEXT,
    gene_params     JSONB,
    fitness         DOUBLE PRECISION,
    env_performances JSONB,
    generalization_penalty DOUBLE PRECISION,
    innovation_score DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evolution_logs_gen ON evolution_logs(generation);

-- 复盘报告
CREATE TABLE IF NOT EXISTS replay_reports (
    id              SERIAL PRIMARY KEY,
    level           VARCHAR(20) NOT NULL,
    cycle_id        INTEGER,
    gene_id         VARCHAR(64),
    generation      INTEGER,
    report_json     JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 实验元数据
CREATE TABLE IF NOT EXISTS experiments (
    id              SERIAL PRIMARY KEY,
    experiment_name VARCHAR(200) NOT NULL,
    config_json     JSONB NOT NULL,
    status          VARCHAR(20) DEFAULT 'running',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    notes           TEXT
);
