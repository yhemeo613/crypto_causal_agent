<template>
  <div class="dv">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">数据 <span>DATA</span></div>
        <div class="page-sub">专业 K 线 · 数据源 · 采集与导入</div>
      </div>
      <n-space :size="10">
        <n-button secondary size="small" @click="loadSources">
          <template #icon><Icon icon="mdi:refresh" :width="14" /></template>刷新数据源
        </n-button>
        <n-button type="primary" size="small" :loading="importing" @click="doImport">
          <template #icon><Icon icon="mdi:database-import-outline" :width="14" /></template>导入 parquet
        </n-button>
      </n-space>
    </div>

    <!-- 数据源状态条 -->
    <div class="dv-bar">
      <span class="dv-bar-label">交易所</span>
      <span v-for="ex in (sources?.exchanges || [])" :key="ex" class="dv-chip">{{ ex }}</span>
      <span class="dv-sep"></span>
      <span class="dv-bar-label">本地数据</span>
      <span class="dv-chip dim">{{ sources?.parquet_files?.length || 0 }} 个 parquet</span>
      <span class="dv-spacer"></span>
      <span class="dv-ok">
        <Icon icon="mdi:check-circle" :width="13" style="vertical-align:-2px" />
        TimescaleDB · {{ fmtNum(dbStats?.timescale?.klines) }} K线
      </span>
    </div>

    <!-- K 线工作区 -->
    <div class="dv-card">
      <div class="dv-card-head">
        <div class="dv-card-title">
          <Icon icon="mdi:candlestick-chart" :width="16" style="vertical-align:-2px;color:var(--accent);margin-right:6px" />
          {{ kline.symbol }}
          <span class="dv-card-sub">TradingView Lightweight Charts</span>
        </div>
        <n-space :size="8" align="center">
          <n-radio-group :value="kline.interval" size="small" @update:value="(v) => { kline.interval = v; loadKlines() }">
            <n-radio-button v-for="iv in intervals" :key="iv" :value="iv" :label="iv" />
          </n-radio-group>
          <n-select
            :value="kline.limit"
            :options="[200, 500, 1000, 2000].map(n => ({ label: n + ' 根', value: n }))"
            size="small" style="width:110px"
            @update:value="(v) => { kline.limit = v; loadKlines() }"
          />
          <n-switch v-model:value="realtime" size="small">
            <template #checked><span style="font-size:11px">实时</span></template>
            <template #unchecked><span style="font-size:11px">实时</span></template>
          </n-switch>
        </n-space>
      </div>

      <KLineChart :data="klines" height="520px" />

      <div class="dv-foot" v-if="klines.length">
        <div v-for="q in quotes" :key="q.label" class="dv-quote">
          <span class="dv-quote-label">{{ q.label }}</span>
          <span class="dv-quote-val" :class="q.tone">{{ q.value }}</span>
        </div>
        <span class="dv-spacer" style="flex:1"></span>
        <span class="dv-fresh" :class="freshClass">
          <Icon icon="mdi:clock-outline" :width="13" style="vertical-align:-2px" />
          最新 {{ freshText }}{{ realtime ? ' · 实时刷新中' : '' }}
        </span>
        <span class="dv-meta">共 {{ klines.length }} 根 · {{ kline.interval }}</span>
      </div>
    </div>

    <!-- 采集任务 + 后台任务 -->
    <div class="dv-bottom">
      <!-- 采集任务 -->
      <div class="dv-card">
        <div class="dv-sec-head">
          <div class="dv-sec-title">
            <span class="dv-sec-icon collect"><Icon icon="mdi:download-box-outline" :width="17" /></span>
            <span>采集任务</span>
            <span class="dv-sec-sub">COLLECT</span>
          </div>
        </div>

        <div class="dv-form">
          <div class="dv-field">
            <label class="dv-label">交易对</label>
            <n-input v-model:value="collect.symbol" placeholder="BTCUSDT" clearable>
              <template #prefix><Icon icon="mdi:currency-btc" :width="14" style="color:var(--faint)" /></template>
            </n-input>
          </div>

          <div class="dv-field">
            <div class="dv-label-row">
              <label class="dv-label">周期</label>
              <div class="dv-label-actions">
                <a class="dv-link" @click="selectAll">全选</a>
                <a class="dv-link" @click="clearAll">清空</a>
              </div>
            </div>
            <div class="dv-intervals">
              <div
                v-for="iv in intervals" :key="iv"
                class="dv-iv" :class="{ on: collect.intervals.includes(iv) }"
                @click="toggleInterval(iv)"
              >{{ iv }}</div>
            </div>
          </div>

          <n-button type="primary" :loading="collecting" size="medium" block @click="doCollect">
            <template #icon><Icon icon="mdi:download" :width="16" /></template>
            开始采集
          </n-button>
          <n-button secondary :loading="collectingIncr" size="small" block @click="doCollectIncremental">
            <template #icon><Icon icon="mdi:sync" :width="14" /></template>
            增量采集（实时更新）
          </n-button>

          <div class="dv-form-hint">
            <Icon icon="mdi:information-outline" :width="13" style="vertical-align:-2px" />
            采集结果保存至 <code>data/raw/*.parquet</code>，随后可在「导入 parquet」写入 TimescaleDB
          </div>
        </div>
      </div>

      <!-- 后台任务 -->
      <div class="dv-card">
        <div class="dv-sec-head">
          <div class="dv-sec-title">
            <span class="dv-sec-icon task"><Icon icon="mdi:progress-clock" :width="17" /></span>
            <span>后台任务</span>
            <span class="dv-sec-sub">TASKS · {{ runningCount }} RUNNING</span>
          </div>
        </div>

        <div v-if="tasks.length" class="dv-tasks">
          <div
            v-for="t in tasks" :key="t.id"
            class="dv-task" :class="[t.status, { active: t.status === 'running' }]"
          >
            <div class="dv-task-top">
              <span class="dv-task-dot" :class="t.status"></span>
              <span class="dv-task-name">{{ t.name }}</span>
              <span class="dv-task-id">#{{ t.id }}</span>
              <span class="dv-spacer"></span>
              <n-tag size="tiny" :type="taskType(t.status)" :bordered="false" round>{{ taskText(t.status) }}</n-tag>
            </div>
            <div class="dv-task-bar">
              <n-progress
                type="line" :percentage="Math.round(t.progress)" :height="5"
                :status="t.status === 'failed' ? 'error' : t.status === 'done' ? 'success' : undefined"
                :show-indicator="false" :border-radius="3"
              />
            </div>
            <div class="dv-task-bottom">
              <span class="dv-task-msg" :class="{ err: t.status === 'failed' }">{{ t.message }}</span>
              <span class="dv-task-time">{{ shortTs(t.created_at) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="dv-empty">
          <Icon icon="mdi:clipboard-text-clock-outline" :width="26" style="opacity:0.5" />
          <p>暂无后台任务</p>
          <span>采集 / 导入提交后在此查看实时进度</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useMessage } from 'naive-ui'
import api from '../api'
import { useAgentStore } from '../stores/agent'
import { useSocketStore } from '../stores/socket'
import KLineChart from '../components/KLineChart.vue'

const message = useMessage()
const agent = useAgentStore()
const socket = useSocketStore()

const intervals = ['1m', '5m', '15m', '1h', '4h', '1d']
const sources = ref(null)
const klines = ref([])
const tasks = ref([])
const importing = ref(false)
const collecting = ref(false)
const collectingIncr = ref(false)
const realtime = ref(false)
const freshness = ref({})
const collect = ref({ symbol: 'BTCUSDT', intervals: ['1h', '4h', '1d'] })
const kline = ref({ symbol: 'BTCUSDT', interval: '1h', limit: 500 })
let realtimeTimer = null

const dbStats = computed(() => agent.dbStats)
const runningCount = computed(() => tasks.value.filter((t) => t.status === 'running').length)

const quotes = computed(() => {
  const d = klines.value
  if (!d.length) return []
  const last = d[d.length - 1]
  const prev = d.length > 1 ? d[d.length - 2].close : last.open
  const pct = ((last.close - prev) / prev) * 100
  const fmt = (n) => n.toLocaleString(undefined, { maximumFractionDigits: 1 })
  return [
    { label: '最新价', value: fmt(last.close), tone: '' },
    { label: '涨跌', value: `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`, tone: pct >= 0 ? 'up' : 'down' },
    { label: '最高', value: fmt(Math.max(...d.slice(-100).map((r) => r.high))), tone: 'up' },
    { label: '最低', value: fmt(Math.min(...d.slice(-100).map((r) => r.low))), tone: 'down' },
  ]
})

const fmtNum = (n) => (n == null ? 0 : Number(n)).toLocaleString()
const shortTs = (ts) => (ts ? String(ts).slice(11, 19) : '')

const freshInfo = computed(() => freshness.value[kline.value.interval] || null)
const freshText = computed(() => {
  const f = freshInfo.value
  if (!f) return '—'
  return `${String(f.latest_ts).slice(5, 16)} (${f.age_minutes < 60 ? f.age_minutes + ' 分前' : (f.age_minutes / 60).toFixed(1) + ' 小时前'})`
})
const freshClass = computed(() => {
  const f = freshInfo.value
  if (!f) return ''
  return f.age_minutes < 30 ? 'green' : f.age_minutes < 300 ? 'amber' : 'stale'
})

function toggleInterval(iv) {
  const i = collect.value.intervals.indexOf(iv)
  if (i >= 0) collect.value.intervals.splice(i, 1)
  else collect.value.intervals.push(iv)
}
function selectAll() { collect.value.intervals = [...intervals] }
function clearAll() { collect.value.intervals = [] }

async function loadKlines() {
  try {
    const { data } = await api.klines({ symbol: kline.value.symbol, interval: kline.value.interval, limit: kline.value.limit })
    klines.value = data.data || []
    if (!klines.value.length) message.info('该周期暂无数据')
  } catch (e) {
    message.error(`K 线加载失败: ${e.message}`)
  }
}
async function loadSources() { try { const { data } = await api.dataSources(); sources.value = data } catch {} }
async function loadTasks() { try { const { data } = await api.tasks(); tasks.value = (data.background || []).slice(0, 6) } catch {} }
async function loadLatest() { try { const { data } = await api.dataLatest(kline.value.symbol); freshness.value = data.freshness || {} } catch {} }

async function doCollectIncremental() {
  if (!collect.value.intervals.length) { message.warning('请至少选择一个周期'); return }
  collectingIncr.value = true
  try {
    const { data } = await api.dataCollect({ symbol: collect.value.symbol, intervals: collect.value.intervals, incremental: true })
    message.success(`增量采集已提交: #${data.task_id}，完成后自动入库`)
    await loadTasks()
  } catch (e) { message.error(`提交失败: ${e.message}`) } finally { collectingIncr.value = false }
}

async function doCollect() {
  if (!collect.value.intervals.length) { message.warning('请至少选择一个周期'); return }
  collecting.value = true
  try {
    const { data } = await api.dataCollect({ symbol: collect.value.symbol, intervals: collect.value.intervals })
    message.success(`采集任务已提交: #${data.task_id}`)
    await loadTasks()
  } catch (e) { message.error(`提交失败: ${e.message}`) } finally { collecting.value = false }
}
async function doImport() {
  importing.value = true
  try {
    const { data } = await api.dataImport()
    message.success(`导入任务已提交: #${data.task_id}`)
    await loadTasks()
  } catch (e) { message.error(`导入失败: ${e.message}`) } finally { importing.value = false }
}

function taskType(s) { return { done: 'success', running: 'info', failed: 'error', cancelled: 'default' }[s] || 'default' }
function taskText(s) { return { done: '完成', running: '运行中', failed: '失败', cancelled: '已取消', queued: '排队中' }[s] || s }

onMounted(() => {
  loadKlines(); loadSources(); loadTasks(); loadLatest()
  socket.on('task.update', loadTasks)
  socket.on('db.updated', () => { loadTasks(); agent.fetchDb(); loadLatest(); if (realtime.value) loadKlines() })
  // 实时刷新：每 20s 重新拉取最新 K 线 + 新鲜度
  realtimeTimer = setInterval(() => {
    if (realtime.value) { loadKlines(); loadLatest() }
  }, 20000)
})

onBeforeUnmount(() => { if (realtimeTimer) clearInterval(realtimeTimer) })
</script>

<style scoped lang="scss">
.dv { display: flex; flex-direction: column; gap: 1.2rem; }

/* ── 数据源状态条 ── */
.dv-bar {
  display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
  padding: 0.8rem 1.2rem; border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
}
.dv-bar-label { font-size: 0.62rem; color: var(--faint); letter-spacing: 0.15em; text-transform: uppercase; }
.dv-chip {
  padding: 0.16rem 0.6rem; border-radius: 999px; font-size: 0.66rem;
  color: var(--accent); background: rgba(79, 195, 247, 0.08);
  border: 0.5px solid rgba(79, 195, 247, 0.25);
  &.dim { color: var(--dim); background: rgba(255, 255, 255, 0.04); border-color: var(--border); }
}
.dv-sep { width: 1px; height: 16px; background: var(--border); margin: 0 0.4rem; }
.dv-spacer { flex: 1; }
.dv-ok { font-size: 0.66rem; color: var(--green); }

/* ── K 线工作区 ── */
.dv-card {
  padding: 1.3rem 1.5rem; border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
}
.dv-card-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.8rem; }
.dv-card-title { display: flex; align-items: center; font-size: 0.85rem; font-weight: 500; }
.dv-card-sub { margin-left: 0.6rem; font-size: 0.6rem; color: var(--faint); font-weight: 300; }

.dv-foot { display: flex; align-items: center; gap: 1.6rem; flex-wrap: wrap; margin-top: 0.7rem; padding-top: 0.7rem; border-top: 0.5px solid var(--border); }
.dv-quote { display: flex; flex-direction: column; gap: 0.1rem; }
.dv-quote-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.12em; text-transform: uppercase; }
.dv-quote-val { font-family: var(--mono); font-size: 0.95rem; font-weight: 600; &.up { color: var(--green); } &.down { color: var(--red); } }
.dv-meta { font-size: 0.62rem; color: var(--faint); }
.dv-fresh {
  display: inline-flex; align-items: center; gap: 0.3rem;
  font-size: 0.64rem;
  &.green { color: var(--green); }
  &.amber { color: var(--amber); }
  &.stale { color: var(--red); }
}

/* ── 底部两栏 ── */
.dv-bottom { display: grid; grid-template-columns: 360px 1fr; gap: 1.2rem; }

/* 区块 header */
.dv-sec-head { margin-bottom: 1.1rem; }
.dv-sec-title { display: flex; align-items: center; gap: 0.6rem; font-size: 0.82rem; font-weight: 500; }
.dv-sec-icon {
  width: 30px; height: 30px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  &.collect { color: var(--accent); background: rgba(79, 195, 247, 0.1); }
  &.task { color: var(--green); background: rgba(105, 240, 174, 0.1); }
}
.dv-sec-sub { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.25em; }

/* ── 采集任务表单 ── */
.dv-form { display: flex; flex-direction: column; gap: 1rem; }
.dv-field { display: flex; flex-direction: column; gap: 0.4rem; }
.dv-label { font-size: 0.66rem; color: var(--faint); letter-spacing: 0.1em; }
.dv-label-row { display: flex; justify-content: space-between; align-items: center; }
.dv-label-actions { display: flex; gap: 0.6rem; }
.dv-link { font-size: 0.62rem; color: var(--accent); cursor: pointer; text-decoration: none; opacity: 0.8; &:hover { opacity: 1; text-decoration: underline; } }

.dv-intervals { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.4rem; }
.dv-iv {
  text-align: center; padding: 0.42rem 0; border-radius: 6px; cursor: pointer;
  font-family: var(--mono); font-size: 0.7rem; user-select: none;
  color: var(--dim); background: rgba(255, 255, 255, 0.03);
  border: 0.5px solid var(--border);
  transition: all 0.18s;
  &:hover { border-color: rgba(79, 195, 247, 0.4); color: var(--text); }
  &.on {
    color: var(--accent); background: rgba(79, 195, 247, 0.1);
    border-color: rgba(79, 195, 247, 0.45);
    box-shadow: 0 0 8px rgba(79, 195, 247, 0.15);
  }
}
.dv-form-hint {
  display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;
  font-size: 0.62rem; color: var(--faint); line-height: 1.6;
  code { color: var(--accent); background: rgba(79, 195, 247, 0.08); padding: 0 0.3rem; border-radius: 3px; }
}

/* ── 后台任务列表 ── */
.dv-tasks { display: flex; flex-direction: column; gap: 0.7rem; }
.dv-task {
  position: relative;
  padding: 0.75rem 0.9rem 0.75rem 1rem;
  border-radius: 8px;
  border: 0.5px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  transition: all 0.2s;
  overflow: hidden;

  &.active {
    border-color: rgba(79, 195, 247, 0.35);
    background: rgba(79, 195, 247, 0.04);
    box-shadow: 0 0 14px rgba(79, 195, 247, 0.08);
  }
  &.failed { border-color: rgba(239, 83, 80, 0.3); }
}
.dv-task-top { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.dv-task-dot {
  width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px;
  background: var(--faint);
  &.running { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: dvPulse 1.4s infinite; }
  &.done { background: var(--green); }
  &.failed { background: var(--red); }
}
.dv-task-name { font-size: 0.74rem; font-weight: 500; }
.dv-task-id { font-size: 0.58rem; color: var(--faint); font-family: var(--mono); }
.dv-task-bar { margin-bottom: 0.3rem; }
.dv-task-bottom { display: flex; justify-content: space-between; align-items: center; gap: 0.8rem; }
.dv-task-msg { font-size: 0.62rem; color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; &.err { color: var(--red); } }
.dv-task-time { font-size: 0.58rem; color: var(--faint); font-family: var(--mono); flex: 0 0 auto; }

.dv-empty {
  display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
  padding: 2.4rem 0; color: var(--faint);
  p { font-size: 0.78rem; color: var(--dim); margin-top: 0.4rem; }
  span { font-size: 0.62rem; }
}

@keyframes dvPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (max-width: 1000px) {
  .dv-bottom { grid-template-columns: 1fr; }
  .dv-intervals { grid-template-columns: repeat(3, 1fr); }
}
</style>
