<template>
  <div class="ov">
    <!-- ══ Hero 状态区 ══ -->
    <section class="ov-hero">
      <div class="ov-hero-left">
        <div class="ov-hero-status">
          <span class="ov-status-badge" :class="agent.agentStatus">
            <span class="ov-status-dot"></span>
            {{ agentStatusText }}
          </span>
          <span class="ov-hero-meta">Cycle #{{ agent.state?.cycle_id ?? 0 }}</span>
          <span v-if="agent.state?.uptime" class="ov-hero-meta">运行 {{ agent.state.uptime }}</span>
        </div>
        <h1 class="ov-hero-title">
          <span class="ov-hl">CRYPTO CAUSAL</span> AGENT
        </h1>
        <p class="ov-hero-sub">感知市场 → 理解因果 → 辩论推理 → 反事实推演 → 策略创新 → 自我进化</p>
      </div>
      <div class="ov-hero-right" v-if="lastDecision">
        <div class="ov-last-decision">
          <div class="ov-ld-label">LAST DECISION · #{{ lastDecision.cycle_id }}</div>
          <div class="ov-ld-main">
            <span class="ov-ld-action" :class="lastDecision.action">{{ lastDecision.action }}</span>
            <div class="ov-ld-conf">
              <span class="ov-ld-conf-num">{{ (lastDecision.confidence * 100).toFixed(0) }}</span>
              <span class="ov-ld-conf-unit">%</span>
              <span class="ov-ld-conf-label">置信度</span>
            </div>
          </div>
          <div class="ov-ld-foot">{{ shortTs(lastDecision.ts) }} · 风控阈值 {{ (riskThreshold * 100).toFixed(0) }}%</div>
          <div v-if="lastDecision.regime_mode" class="ov-ld-foot" style="color:var(--amber)">
            Regime 模式：{{ lastDecision.regime_mode }}
          </div>
        </div>
      </div>
    </section>

    <!-- ══ KPI 指标卡 ══ -->
    <section class="ov-kpis">
      <div class="ov-kpi" v-for="k in kpis" :key="k.label">
        <div class="ov-kpi-label">{{ k.label }}</div>
        <div class="ov-kpi-value" :class="k.tone">{{ k.value }}</div>
        <div class="ov-kpi-foot">{{ k.foot }}</div>
      </div>
    </section>

    <!-- ══ 决策管道 ══ -->
    <section class="ov-card">
      <div class="ov-card-head">
        <span class="ov-card-title">决策管道</span>
        <span class="ov-card-meta">DECISION PIPELINE</span>
      </div>
      <div class="ov-flow" v-if="steps.length">
        <div v-for="(s, i) in steps" :key="i" class="ov-flow-step" :class="s.status">
          <div class="ov-flow-node">
            <Icon :icon="s.icon" :width="16" />
          </div>
          <div class="ov-flow-name">{{ s.name }}</div>
          <div class="ov-flow-detail">{{ s.detail }}</div>
          <div v-if="i < steps.length - 1" class="ov-flow-line"></div>
        </div>
      </div>
      <div v-else class="ov-empty">尚无决策记录 — 在「决策实验室」执行一轮完整决策</div>
    </section>

    <!-- ══ 三栏数据 ══ -->
    <section class="ov-grid3">
      <div class="ov-card">
        <div class="ov-card-head">
          <span class="ov-card-title">最近决策</span>
          <span class="ov-card-meta">{{ agent.recentDecisions.length }} RECORDS</span>
        </div>
        <table class="wb-table" v-if="agent.recentDecisions.length">
          <tr><th>Cycle</th><th>方向</th><th>置信度</th><th>时间</th></tr>
          <tr v-for="d in agent.recentDecisions.slice(0, 5)" :key="d.cycle_id">
            <td class="mono dim">#{{ d.cycle_id }}</td>
            <td><span class="tag" :class="tagClass(d.action)">{{ d.action }}</span></td>
            <td class="mono">{{ d.confidence?.toFixed(2) }}</td>
            <td class="dim" style="font-size:0.64rem">{{ shortTs(d.ts) }}</td>
          </tr>
        </table>
        <div v-else class="ov-empty">暂无决策</div>
      </div>

      <div class="ov-card">
        <div class="ov-card-head">
          <span class="ov-card-title">系统健康</span>
          <span class="ov-card-meta">DATABASES</span>
        </div>
        <div class="ov-health" v-for="d in dbCards" :key="d.name">
          <span class="ov-health-icon" :class="d.on ? 'on' : ''">
            <Icon :icon="d.icon" :width="15" />
          </span>
          <span class="ov-health-name">{{ d.name }}</span>
          <span class="ov-health-text" :class="d.on ? 'on' : 'off'">{{ d.text }}</span>
        </div>
      </div>

      <div class="ov-card">
        <div class="ov-card-head">
          <span class="ov-card-title">运行统计</span>
          <span class="ov-card-meta">STATS</span>
        </div>
        <div class="data-row"><span class="data-key">K 线数据</span><span class="data-val mono">{{ fmtNum(agent.state?.stats?.klines) }}</span></div>
        <div class="data-row"><span class="data-key">资金费率</span><span class="data-val mono">{{ fmtNum(dbStats?.timescale?.funding_rates) }}</span></div>
        <div class="data-row"><span class="data-key">决策次数</span><span class="data-val mono">{{ agent.state?.stats?.decisions }}</span></div>
        <div class="data-row"><span class="data-key">交易次数</span><span class="data-val mono">{{ agent.state?.stats?.trades }}</span></div>
        <div class="data-row"><span class="data-key">进化记录</span><span class="data-val mono">{{ agent.state?.stats?.evolutions }}</span></div>
        <div class="data-row"><span class="data-key">WebSocket</span><span class="data-val"><span class="tag" :class="socket.connected ? 'green' : 'red'">{{ socket.connected ? '已连接' : '断开' }}</span></span></div>
      </div>
    </section>

    <!-- ══ 数据库图表 ══ -->
    <section class="ov-grid4">
      <div v-for="db in dbChartCards" :key="db.name" class="ov-card ov-db">
        <div class="ov-db-head">
          <Icon :icon="db.icon" :width="16" />
          <span>{{ db.name }}</span>
        </div>
        <v-chart :option="db.chart" autoresize style="height:150px" />
        <div class="ov-db-foot">{{ db.status }}</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api'
import { useAgentStore } from '../stores/agent'
import { useSocketStore } from '../stores/socket'
import { Icon } from '@iconify/vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, GaugeChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import gsap from 'gsap'

use([BarChart, GaugeChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const agent = useAgentStore()
const socket = useSocketStore()

const agentStatusText = computed(() => ({ idle: '空闲', running: '运行中', paused: '已暂停' }[agent.agentStatus] || agent.agentStatus))
const lastDecision = computed(() => agent.recentDecisions[0] || null)
const dbStats = computed(() => agent.dbStats)
// 风控阈值：从后端 config 读取真实值（不再硬编码 0.4）
const riskThreshold = ref(0.4)
async function loadRiskConfig() {
  try {
    const { data } = await api.config()
    riskThreshold.value = data.risk_control?.min_confidence ?? 0.4
  } catch {}
}

const kpis = computed(() => {
  const s = agent.state?.stats || {}
  const d = dbStats.value?.timescale
  return [
    { label: 'K 线数据', value: compactNum(s.klines), foot: `${d?.funding_rates ?? 0} 条资金费率`, tone: '' },
    { label: '决策次数', value: s.decisions ?? 0, foot: `当前 Cycle #${agent.state?.cycle_id ?? 0}`, tone: '' },
    { label: '进化记录', value: s.evolutions ?? 0, foot: 'DEAP 遗传进化', tone: '' },
    { label: '交易次数', value: s.trades ?? 0, foot: '本地撮合仿真', tone: '' },
  ]
})

const steps = computed(() => {
  const last = agent.state?.last_decision
  const running = agent.agentStatus === 'running'
  // 感知/记忆/辩论/证伪/反事实：Agent 运行中即视为该阶段真实执行过（有 recent_decisions 佐证）
  const executed = agent.state?.stats?.decisions > 0
  const st = (done) => (running && executed) || done ? 'done' : 'pending'
  const defs = [
    { name: '感知', icon: 'mdi:eye-outline', status: st(executed), detail: '三时序切片' },
    { name: '记忆', icon: 'mdi:memory', status: st(executed), detail: '三层召回' },
    { name: '多空辩论', icon: 'mdi:scale-balance', status: st(executed), detail: 'Bull / Bear 论证' },
    { name: '证伪', icon: 'mdi:shield-alert-outline', status: st(executed), detail: '置信度校验' },
    { name: '反事实', icon: 'mdi:chart-timeline-variant', status: st(executed), detail: '情景推演' },
    { name: '决策', icon: 'mdi:check-decagram-outline', status: last ? 'active' : 'pending', detail: last ? `${last.action} conf=${last.confidence?.toFixed(2)}` : '等待决策' },
  ]
  return defs
})

const dbCards = computed(() => {
  const d = agent.dbStats
  if (!d) return []
  return [
    { name: 'TimescaleDB', icon: 'mdi:database-outline', on: d.timescale?.hypertables > 0, text: `${fmtNum(d.timescale?.klines)} K线 · ${fmtNum(d.timescale?.funding_rates)} 费率` },
    { name: 'Neo4j', icon: 'mdi:graph-outline', on: d.neo4j?.connected, text: d.neo4j?.connected ? `${d.neo4j.nodes} 节点 · ${d.neo4j.triplets} 因果边` : '离线' },
    { name: 'Redis', icon: 'mdi:database-cog-outline', on: d.redis?.connected, text: d.redis?.connected ? '已连接' : '离线' },
    { name: 'ChromaDB', icon: 'mdi:database-search-outline', on: d.chromadb?.connected, text: d.chromadb?.connected ? `${d.chromadb.cases} 案例` : '离线' },
  ]
})

const dbChartCards = computed(() => {
  const d = agent.dbStats
  if (!d) return []
  const t = { textStyle: { color: 'rgba(255,255,255,0.45)' } }
  return [
    { icon: 'mdi:database-outline', name: 'PostgreSQL', status: `${d.pg?.total_trades || 0} 交易 · ${d.pg?.total_decisions || 0} 决策`,
      chart: { ...t, grid: { top: 6, bottom: 4, left: 30, right: 6 }, xAxis: { type: 'value', axisLabel: { fontSize: 8 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
        yAxis: { type: 'category', data: ['进化', '决策', '交易'], axisLabel: { fontSize: 9 } },
        series: [{ type: 'bar', data: [d.pg?.total_evolutions || 0, d.pg?.total_decisions || 0, d.pg?.total_trades || 0], itemStyle: { color: '#4fc3f7', borderRadius: [0, 3, 3, 0] }, barWidth: 8 }] } },
    { icon: 'mdi:candlestick-chart', name: 'TimescaleDB', status: `${fmtNum(d.timescale?.klines)} K线`,
      chart: { ...t, series: [{ type: 'gauge', radius: '92%', center: ['50%', '58%'], startAngle: 220, endAngle: -40, min: 0, max: 2000000,
        data: [{ value: d.timescale?.klines || 0, name: '' }],
        axisLine: { lineStyle: { width: 6, color: [[0.5, '#69f0ae'], [1, '#4fc3f7']] } }, axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { show: false }, pointer: { width: 2 }, detail: { fontSize: 12, color: '#fff', offsetCenter: [0, 58], formatter: (v) => `${(v / 10000).toFixed(0)}万` } }] } },
    { icon: 'mdi:graph-outline', name: 'Neo4j', status: d.neo4j?.connected ? `${d.neo4j.nodes} 节点` : '离线',
      chart: { ...t, series: [{ type: 'pie', radius: ['52%', '78%'], center: ['50%', '58%'], label: { show: false },
        data: [{ value: d.neo4j?.triplets || 1, name: '因果边', itemStyle: { color: '#4fc3f7' } }, { value: Math.max((d.neo4j?.nodes || 0) - (d.neo4j?.triplets || 0), 1), name: '其他', itemStyle: { color: 'rgba(79,195,247,0.22)' } }] }] } },
    { icon: 'mdi:database-search-outline', name: 'ChromaDB', status: d.chromadb?.connected ? `${d.chromadb.cases} 案例` : '离线',
      chart: { ...t, grid: { top: 10, bottom: 10, left: 10, right: 10 }, xAxis: { show: false, max: Math.max(300, d.chromadb?.cases || 0) }, yAxis: { show: false },
        series: [{ type: 'bar', data: [d.chromadb?.cases || 0], itemStyle: { color: '#69f0ae', borderRadius: 4 }, barWidth: 16,
          label: { show: true, position: 'right', fontSize: 16, color: '#fff', formatter: '{c}' } }] } },
  ]
})

function fmtNum(n) { return (n == null ? 0 : Number(n)).toLocaleString() }
function compactNum(n) {
  n = n || 0
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}
function shortTs(ts) { return ts ? String(ts).slice(5, 16) : '' }
function tagClass(a) { return { long: 'green', short: 'red', hold: 'dim' }[a] || 'dim' }

onMounted(() => {
  loadRiskConfig()
  gsap.from('.ov-hero', { y: -18, opacity: 0, duration: 0.6, ease: 'power3.out' })
  gsap.from('.ov-kpi', { y: 16, opacity: 0, duration: 0.5, stagger: 0.08, delay: 0.15, ease: 'power2.out' })
  gsap.from('.ov-card', { y: 20, opacity: 0, duration: 0.5, stagger: 0.08, delay: 0.3, ease: 'power2.out' })
})
</script>

<style scoped lang="scss">
.ov {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

/* ── Hero ── */
.ov-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 2rem;
  padding: 2rem 2.2rem;
  border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  background:
    radial-gradient(1200px 300px at 15% -20%, rgba(79, 195, 247, 0.14), transparent 60%),
    radial-gradient(900px 260px at 90% 130%, rgba(105, 240, 174, 0.08), transparent 60%),
    rgba(255, 255, 255, 0.02);
  position: relative;
  overflow: hidden;
}
.ov-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 30%, rgba(79, 195, 247, 0.06) 50%, transparent 70%);
  pointer-events: none;
}

.ov-hero-status { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.9rem; }

.ov-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.9rem;
  border-radius: 999px;
  font-size: 0.72rem;
  letter-spacing: 0.2em;
  background: rgba(255, 255, 255, 0.04);
  border: 0.5px solid rgba(255, 255, 255, 0.1);

  .ov-status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--faint);
  }
  &.running { color: var(--green); border-color: rgba(105, 240, 174, 0.35); background: rgba(105, 240, 174, 0.08);
    .ov-status-dot { background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 1.6s infinite; } }
  &.paused { color: var(--amber); border-color: rgba(255, 213, 79, 0.35); background: rgba(255, 213, 79, 0.08);
    .ov-status-dot { background: var(--amber); } }
}

.ov-hero-meta { font-size: 0.66rem; color: var(--faint); letter-spacing: 0.1em; }

.ov-hero-title {
  font-size: 2.1rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  .ov-hl { color: var(--accent); }
}

.ov-hero-sub { margin-top: 0.5rem; font-size: 0.78rem; color: var(--dim); letter-spacing: 0.06em; }

/* 上次决策 */
.ov-last-decision {
  min-width: 280px;
  padding: 1.1rem 1.3rem;
  border-radius: 10px;
  border: 0.5px solid rgba(79, 195, 247, 0.18);
  background: rgba(79, 195, 247, 0.05);
}
.ov-ld-label { font-size: 0.6rem; color: var(--faint); letter-spacing: 0.25em; margin-bottom: 0.6rem; }
.ov-ld-main { display: flex; align-items: center; gap: 1.2rem; }
.ov-ld-action {
  font-size: 1.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  &.long { color: var(--green); }
  &.short { color: var(--red); }
  &.hold { color: var(--dim); }
}
.ov-ld-conf { display: flex; align-items: baseline; gap: 0.25rem; }
.ov-ld-conf-num { font-size: 2rem; font-weight: 700; font-family: var(--mono); color: #fff; }
.ov-ld-conf-unit { font-size: 0.9rem; color: var(--accent); }
.ov-ld-conf-label { margin-left: 0.5rem; font-size: 0.6rem; color: var(--faint); }
.ov-ld-foot { margin-top: 0.5rem; font-size: 0.62rem; color: var(--faint); }

/* ── KPI ── */
.ov-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  overflow: hidden;
  border: 0.5px solid rgba(255, 255, 255, 0.06);
}
.ov-kpi {
  padding: 1.2rem 1.5rem;
  background: rgba(255, 255, 255, 0.02);
  transition: background 0.25s;
  &:hover { background: rgba(255, 255, 255, 0.04); }
}
.ov-kpi-label { font-size: 0.62rem; color: var(--faint); letter-spacing: 0.2em; text-transform: uppercase; }
.ov-kpi-value {
  margin-top: 0.5rem;
  font-size: 1.8rem;
  font-weight: 700;
  font-family: var(--mono);
  &.green { color: var(--green); }
  &.red { color: var(--red); }
}
.ov-kpi-foot { margin-top: 0.25rem; font-size: 0.62rem; color: var(--faint); }

/* ── 通用卡片 ── */
.ov-card {
  padding: 1.4rem 1.6rem;
  border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}
.ov-card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1.1rem;
}
.ov-card-title { font-size: 0.78rem; font-weight: 500; letter-spacing: 0.12em; }
.ov-card-meta { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.25em; }

.ov-empty { text-align: center; color: var(--faint); font-size: 0.72rem; padding: 1.8rem 0; }

/* ── 决策管道 ── */
.ov-flow { display: flex; gap: 0; padding: 0.6rem 0; }
.ov-flow-step {
  flex: 1;
  position: relative;
  padding: 0.8rem 0.5rem 0.5rem;
  text-align: center;
}
.ov-flow-node {
  width: 38px; height: 38px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--faint);
  transition: all 0.3s;
  position: relative;
  z-index: 2;
}
.ov-flow-step.done .ov-flow-node { border-color: rgba(105, 240, 174, 0.5); color: var(--green); background: rgba(105, 240, 174, 0.08); }
.ov-flow-step.active .ov-flow-node { border-color: rgba(79, 195, 247, 0.6); color: var(--accent); background: rgba(79, 195, 247, 0.12); box-shadow: 0 0 16px rgba(79, 195, 247, 0.25); }
.ov-flow-name { margin-top: 0.55rem; font-size: 0.68rem; color: var(--dim); }
.ov-flow-step.done .ov-flow-name { color: var(--text); }
.ov-flow-step.active .ov-flow-name { color: var(--accent); font-weight: 500; }
.ov-flow-detail { margin-top: 0.2rem; font-size: 0.58rem; color: var(--faint); line-height: 1.4; }
.ov-flow-line {
  position: absolute;
  top: 27px;
  left: calc(50% + 24px);
  right: calc(-50% + 24px);
  height: 1px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.04));
  z-index: 1;
}
.ov-flow-step.done .ov-flow-line { background: linear-gradient(90deg, rgba(105, 240, 174, 0.4), rgba(105, 240, 174, 0.08)); }

/* ── 三栏 ── */
.ov-grid3 {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 1.2rem;
}
.ov-health {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.55rem 0;
  border-bottom: 0.5px solid var(--border);
  font-size: 0.74rem;
  &:last-child { border-bottom: none; }
}
.ov-health-icon {
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px;
  background: var(--surface2);
  color: var(--faint);
  &.on { color: var(--accent); background: rgba(79, 195, 247, 0.1); }
}
.ov-health-name { flex: 1; }
.ov-health-text { font-size: 0.66rem; &.on { color: var(--green); } &.off { color: var(--red); } }

/* ── 数据库 ── */
.ov-grid4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.2rem;
}
.ov-db { text-align: center; }
.ov-db-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.7rem;
  color: var(--dim);
  letter-spacing: 0.15em;
  margin-bottom: 0.4rem;
}
.ov-db-foot { margin-top: 0.3rem; font-size: 0.6rem; color: var(--faint); }

@media (max-width: 1100px) {
  .ov-kpis, .ov-grid4 { grid-template-columns: repeat(2, 1fr); }
  .ov-grid3 { grid-template-columns: 1fr; }
  .ov-hero { flex-direction: column; align-items: flex-start; }
}
</style>
