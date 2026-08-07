<template>
  <div class="app" v-if="store.architecture">
    <nav class="nav">
      <div class="nav-brand"><span class="nav-dot"></span>CRYPTO CAUSAL AGENT</div>
      <div class="nav-right">
        <span class="nav-status" :class="{ on: store.connected }">{{ store.connected ? '在线' : '离线' }}</span>
      </div>
    </nav>

    <section class="hero">
      <div class="hero-label">CONCEPT STUDIO · 概念研究平台</div>
      <h1>
        <span class="t-light">自主</span>
        <span class="t-bold">因果推理</span><br>
        <span class="t-accent">进化智能体</span>
      </h1>
      <p class="hero-desc">感知市场 → 理解因果 → 辩论推理 → 反事实推演 → 策略创新 → 自我进化</p>
    </section>

    <!-- 七层架构 -->
    <section class="arch">
      <h2 class="sec-label"><span>//</span> 系统架构</h2>
      <div class="arch-track">
        <div v-for="(l, i) in store.architecture.layers" :key="l.id" class="arch-item"
             :class="{ active: l.status === 'active' }" :style="{ animationDelay: i * 0.08 + 's' }">
          <div class="arch-badge">{{ l.id }}</div>
          <div class="arch-name">{{ l.cn }}</div>
          <div class="arch-line" v-if="i < 6"></div>
        </div>
      </div>
    </section>

    <!-- 决策管道 -->
    <section class="flow">
      <h2 class="sec-label"><span>//</span> 决策管道</h2>
      <div class="flow-track" v-if="store.state">
        <div v-for="(s, i) in store.state.steps" :key="i" class="flow-step" :class="s.status"
             :style="{ animationDelay: i * 0.1 + 's' }">
          <div class="flow-dot"></div>
          <div class="flow-line" v-if="i < store.state.steps.length - 1"></div>
          <div class="flow-name">{{ s.name }}</div>
          <div class="flow-detail">{{ s.detail }}</div>
        </div>
      </div>
    </section>

    <!-- 三列数据面板 -->
    <section class="panels">
      <h2 class="sec-label"><span>//</span> 实时数据</h2>
      <div class="panel-grid-3col">
        <div class="panel glass" v-if="store.state?.perception">
          <div class="panel-head">感知层</div>
          <div class="data-row" v-for="(v, k) in store.state.perception" :key="k">
            <span class="data-key">{{ k }}</span>
            <span class="data-val" v-if="typeof v === 'object'">
              <template v-for="(vv, kk) in v" :key="kk">{{ kk }}: <em>{{ vv }}</em> </template>
            </span>
          </div>
        </div>
        <div class="panel glass" v-if="store.state?.memory">
          <div class="panel-head">记忆召回</div>
          <div class="data-row"><span class="data-key">瞬时</span><span class="data-val">{{ store.state.memory.instant }} 条 · 滑动窗口</span></div>
          <div class="data-row"><span class="data-key">向量</span><span class="data-val">ChromaDB · {{ store.state.memory.vector }} 匹配</span></div>
          <div class="data-row"><span class="data-key">因果</span><span class="data-val">Neo4j · {{ store.state.memory.causal }} 路径</span></div>
        </div>
        <div class="panel glass" v-if="store.state?.account">
          <div class="panel-head">账户</div>
          <div class="data-row"><span class="data-key">权益</span><span class="data-val big">${{ store.state.account.equity?.toLocaleString() }}</span></div>
          <div class="data-row"><span class="data-key">回撤</span><span class="data-val">{{ (store.state.account.drawdown * 100).toFixed(2) }}%</span></div>
        </div>
      </div>
    </section>

    <!-- 数据库可视化 -->
    <section class="dbviz">
      <h2 class="sec-label"><span>//</span> 数据库</h2>
      <div class="db-grid">
        <div class="db-card glass" v-for="db in databaseCards" :key="db.name">
          <div class="db-card-head">{{ db.icon }} · {{ db.name }}</div>
          <v-chart :option="db.chart" autoresize style="height:180px" />
          <div class="db-card-footer">{{ db.status }}</div>
        </div>
      </div>
    </section>

    <footer class="footer">
      <div class="footer-line">自主因果推理进化智能体 · 学术研究平台 · {{ new Date().getFullYear() }}</div>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useAgentStore } from './stores/agent.js'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, PieChart, GaugeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([BarChart, PieChart, GaugeChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const store = useAgentStore()
onMounted(() => store.startPolling(3000))
onUnmounted(() => store.stopPolling())

const chartTheme = {
  textStyle: { color: 'rgba(255,255,255,0.6)' },
}

const databaseCards = computed(() => {
  const db = store.dbStats
  if (!db) return []
  return [
    {
      icon: 'PG', name: 'PostgreSQL',
      status: `${Object.keys(db.pg?.tables || {}).length} 表 · ${(db.pg?.total_trades || 0) + (db.pg?.total_decisions || 0) + (db.pg?.total_evolutions || 0)} 行`,
      chart: {
        ...chartTheme,
        tooltip: { trigger: 'axis' },
        grid: { top: 8, right: 8, bottom: 8, left: 40 },
        xAxis: { type: 'value', axisLabel: { color: 'rgba(255,255,255,0.3)', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } },
        yAxis: { type: 'category', data: Object.keys(db.pg?.tables || {}).slice(0, 7).map(t => t.replace('_',' ')), axisLabel: { fontSize: 9, color: 'rgba(255,255,255,0.5)' } },
        series: [{ type: 'bar', data: Object.values(db.pg?.tables || {}).slice(0, 7),
          itemStyle: { color: '#4fc3f7', borderRadius: [0, 2, 2, 0] }, barWidth: 10 }]
      }
    },
    {
      icon: 'TS', name: 'TimescaleDB',
      status: `${db.timescale?.hypertables || 0} hypertable · ${(db.timescale?.klines || 0).toLocaleString()} K 线`,
      chart: {
        ...chartTheme,
        series: [{
          type: 'gauge', radius: '85%', center: ['50%', '55%'],
          startAngle: 220, endAngle: -40, min: 0, max: 100,
          data: [{ value: Math.min(100, (db.timescale?.klines || 0) / 1000), name: 'K 线' }],
          axisLine: { lineStyle: { width: 8, color: [[0.3, '#69f0ae'], [0.7, '#4fc3f7'], [1, '#ffd54f']] } },
          axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { fontSize: 8, color: 'rgba(255,255,255,0.3)' },
          detail: { fontSize: 16, color: '#fff', offsetCenter: [0, 65], formatter: '{value}k' },
          pointer: { length: '60%', width: 3 }
        }]
      }
    },
    {
      icon: 'N4', name: 'Neo4j',
      status: db.neo4j?.connected ? `${db.neo4j.nodes} 节点 · ${db.neo4j.triplets} 因果边` : '离线',
      chart: {
        ...chartTheme,
        series: [{
          type: 'pie', radius: ['55%', '80%'], center: ['50%', '55%'], avoidLabelOverlap: false,
          label: { show: false },
          data: [
            { value: db.neo4j?.triplets || 0, name: '因果边', itemStyle: { color: '#4fc3f7' } },
            { value: (db.neo4j?.nodes || 0) - (db.neo4j?.triplets || 0), name: '节点', itemStyle: { color: 'rgba(79,195,247,0.3)' } },
          ]
        }]
      }
    },
    {
      icon: 'CH', name: 'ChromaDB',
      status: db.chromadb?.connected ? `${db.chromadb.cases} 案例` : '离线',
      chart: {
        ...chartTheme,
        grid: { top: 10, right: 10, bottom: 10, left: 30 },
        xAxis: { show: false, max: 100 },
        yAxis: { show: false },
        series: [{
          type: 'bar', data: [db.chromadb?.cases || 0],
          itemStyle: { color: '#69f0ae', borderRadius: 4 }, barWidth: 20,
          label: { show: true, position: 'right', fontSize: 24, color: '#fff', formatter: '{c}' }
        }]
      }
    },
  ]
})
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700&family=Noto+Sans+SC:wght@200;300;400;500;700&display=swap');

:root {
  --bg: #060708;
  --surface: rgba(255,255,255,0.025);
  --border: rgba(255,255,255,0.05);
  --text: rgba(255,255,255,0.85);
  --dim: rgba(255,255,255,0.35);
  --faint: rgba(255,255,255,0.14);
  --accent: #4fc3f7;
  --green: #69f0ae;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:'Inter','Noto Sans SC',system-ui,sans-serif; font-weight:300; line-height:1.5; overflow-x:hidden; }
.app { min-height:100vh; background: radial-gradient(ellipse 70% 50% at 50% 0%, rgba(79,195,247,0.05) 0%, transparent 60%), var(--bg); }

.nav { position:fixed; top:0; left:0; right:0; z-index:100; display:flex; justify-content:space-between; align-items:center; padding:1.5rem 4rem; background:rgba(6,7,8,0.75); backdrop-filter:blur(20px) saturate(180%); -webkit-backdrop-filter:blur(20px); border-bottom:0.5px solid var(--border); }
.nav-brand { font-size:0.7rem; letter-spacing:0.35em; font-weight:500; display:flex; align-items:center; gap:0.6rem; color:var(--dim); }
.nav-dot { width:6px; height:6px; border-radius:50%; background:var(--accent); box-shadow:0 0 8px var(--accent); animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.nav-status { padding:0.2rem 0.8rem; border-radius:2px; font-size:0.55rem; letter-spacing:0.25em; background:rgba(255,0,0,0.12); color:#ef5350; }
.nav-status.on { background:rgba(79,195,247,0.12); color:var(--accent); }

.hero { padding:12rem 4rem 8rem; max-width:1400px; margin:0 auto; animation:fadeUp 1.2s cubic-bezier(0.16,1,0.3,1); }
@keyframes fadeUp { from{opacity:0;transform:translateY(40px)} to{opacity:1;transform:translateY(0)} }
.hero-label { font-size:0.55rem; letter-spacing:0.5em; color:var(--dim); margin-bottom:2.5rem; }
.hero h1 { font-size:clamp(4rem, 10vw, 9rem); line-height:0.9; font-weight:200; margin-bottom:2.5rem; }
.t-light { font-weight:200; }
.t-bold { font-weight:700; }
.t-accent { font-weight:300; color:var(--accent); }
.hero-desc { font-size:1.2rem; color:var(--dim); max-width:680px; line-height:1.8; }

section { padding:6rem 4rem; max-width:1400px; margin:0 auto; }
.sec-label { font-size:0.65rem; letter-spacing:0.3em; color:var(--dim); margin-bottom:3rem; font-weight:500; }
.sec-label span { color:var(--faint); margin-right:0.5rem; }

/* Architecture */
.arch-track { display:flex; gap:0; overflow-x:auto; padding-bottom:1rem; }
.arch-item { flex:1; min-width:140px; text-align:center; position:relative; animation:fadeUp 0.6s both; padding:1rem 0; }
.arch-badge { width:48px; height:48px; border-radius:50%; margin:0 auto 1rem; display:flex; align-items:center; justify-content:center; font-size:0.9rem; font-weight:700; background:var(--surface); border:1px solid var(--border); transition:all 0.6s; }
.arch-item.active .arch-badge { background:rgba(79,195,247,0.12); border-color:var(--accent); color:var(--accent); box-shadow:0 0 20px rgba(79,195,247,0.15); }
.arch-name { font-size:1rem; font-weight:500; }
.arch-line { position:absolute; top:24px; left:70%; width:60%; height:1px; background:var(--border); }

/* Flow */
.flow-track { display:flex; gap:2.5rem; overflow-x:auto; padding-bottom:1rem; }
.flow-step { flex:0 0 200px; position:relative; padding-top:2rem; animation:fadeUp 0.6s both; }
.flow-dot { width:12px; height:12px; border-radius:50%; position:absolute; top:0; left:0; background:var(--faint); transition:all 0.6s; }
.flow-step.done .flow-dot { background:var(--green); box-shadow:0 0 12px var(--green); }
.flow-step.active .flow-dot { background:var(--accent); box-shadow:0 0 16px var(--accent); animation:pulse 1s infinite; }
.flow-line { position:absolute; top:5px; left:12px; width:calc(100% + 2.5rem); height:1px; background:linear-gradient(90deg,var(--faint) 50%,transparent); z-index:-1; }
.flow-step.done .flow-line { background:linear-gradient(90deg,var(--green) 50%,transparent); }
.flow-name { font-size:0.95rem; font-weight:500; margin-top:1.2rem; }
.flow-step.active .flow-name { color:var(--accent); }
.flow-detail { font-size:0.65rem; color:var(--dim); margin-top:0.4rem; line-height:1.6; max-width:180px; }

/* Panels */
.panel-grid-3col { display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--border); }
.panel { padding:2.5rem; background:var(--surface); }
.panel-head { font-size:0.6rem; letter-spacing:0.3em; color:var(--dim); margin-bottom:1.5rem; font-weight:500; text-transform:uppercase; }
.data-row { display:flex; justify-content:space-between; align-items:center; padding:0.6rem 0; border-bottom:0.5px solid var(--border); }
.data-row:last-child { border-bottom:none; }
.data-key { font-size:0.7rem; color:var(--faint); }
.data-val { font-size:0.75rem; color:var(--text); text-align:right; }
.data-val em { font-style:normal; color:var(--accent); }
.data-val.big { font-size:1.3rem; font-weight:600; font-family:'SF Mono','Fira Code',monospace; }

/* DB Viz */
.db-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--border); }
.db-card { padding:1.5rem; background:var(--surface); text-align:center; }
.db-card-head { font-size:0.65rem; letter-spacing:0.2em; color:var(--dim); margin-bottom:0.5rem; }
.db-card-footer { font-size:0.55rem; color:var(--faint); margin-top:0.5rem; }

.footer { padding:4rem; text-align:center; max-width:1400px; margin:0 auto; border-top:0.5px solid var(--border); }
.footer-line { font-size:0.6rem; color:var(--faint); letter-spacing:0.3em; }

.glass { background:rgba(255,255,255,0.02); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); border:0.5px solid rgba(255,255,255,0.04); }

::-webkit-scrollbar { width:3px; height:3px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--border); }

@media (max-width:900px) {
  .panel-grid-3col, .db-grid { grid-template-columns:1fr; }
  .nav, .hero, section { padding-left:1.5rem; padding-right:1.5rem; }
  .hero h1 { font-size:3rem; }
}
</style>
