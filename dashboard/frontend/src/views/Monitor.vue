<template>
  <div class="mon">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">监控 <span>MONITOR</span></div>
        <div class="page-sub">系统完整性体检 · 实时日志流</div>
      </div>
      <n-button secondary size="small" :loading="loading" @click="loadHealth">
        <template #icon><Icon icon="mdi:stethoscope" :width="14" /></template>重新体检
      </n-button>
    </div>

    <!-- 健康状态条 -->
    <div class="wb-bar">
      <span class="mon-overall" :class="health?.status">
        <span class="mon-overall-dot"></span>
        {{ health?.status === 'healthy' ? '系统健康' : '存在异常' }}
      </span>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">日志量</span>
        <span class="wb-stat-val">{{ health?.log_count ?? 0 }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">后台任务</span>
        <span class="wb-stat-val">{{ health?.components?.tasks?.background ?? 0 }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">运行中</span>
        <span class="wb-stat-val" :class="runningCount ? 'up' : ''">{{ runningCount }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">WS 客户端</span>
        <span class="wb-stat-val">{{ health?.components?.websocket_clients ?? 0 }}</span>
      </div>
      <span class="wb-spacer" style="flex:1"></span>
      <span class="wb-chip" :class="socket.connected ? 'green' : 'red'">
        <Icon icon="mdi:lan-connect" :width="13" />{{ socket.connected ? 'WS 已连接' : 'WS 断开' }}
      </span>
    </div>

    <!-- 组件矩阵 -->
    <div class="mon-grid">
      <!-- 数据库 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon"><Icon icon="mdi:database-outline" :width="17" /></span>
            <span>数据库</span>
            <span class="wb-sec-sub">DATABASES</span>
          </div>
        </div>
        <div v-for="(v, k) in health?.components?.databases || {}" :key="k" class="mon-row">
          <span class="mon-row-name" :class="{ off: !v.ok }">
            <span class="mon-row-dot" :class="v.ok ? 'on' : 'off'"></span>
            {{ k }}
          </span>
          <span class="mon-row-detail mono">{{ dbDetail(k, v) }}</span>
          <span class="wb-chip" :class="v.ok ? 'green' : 'red'">{{ v.ok ? '正常' : '异常' }}</span>
        </div>
      </div>

      <!-- 七层架构 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:layers-triple-outline" :width="17" /></span>
            <span>七层架构</span>
            <span class="wb-sec-sub">L1-L7</span>
          </div>
        </div>
        <div class="mon-layers">
          <div v-for="(v, k) in health?.components?.layers || {}" :key="k" class="mon-layer" :class="{ ok: v === 'ok' }">
            <span class="mon-layer-id">{{ k }}</span>
            <span class="mon-layer-status">{{ v === 'ok' ? '✓' : '✗' }}</span>
          </div>
        </div>
      </div>

      <!-- 数据新鲜度 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:clock-fast" :width="17" /></span>
            <span>数据新鲜度</span>
            <span class="wb-sec-sub">LATENCY MIN</span>
          </div>
        </div>
        <div class="mon-fresh">
          <div v-for="(age, iv) in health?.components?.data_freshness_minutes || {}" :key="iv" class="mon-fresh-item">
            <span class="wb-badge">{{ iv }}</span>
            <n-progress
              type="line" :percentage="Math.min(age / 300 * 100, 100)" :height="6"
              :status="age < 30 ? 'success' : age < 300 ? 'warning' : 'error'"
              :show-indicator="false" :border-radius="3" style="flex:1"
            />
            <span class="mon-fresh-age" :class="age < 30 ? 'green' : age < 300 ? 'amber' : 'red'">
              {{ age < 60 ? age + ' 分前' : (age / 60).toFixed(1) + ' 时前' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 知识库规则流 + 工具日志 -->
    <div class="mon-grid-2">
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:book-open-variant" :width="17" /></span>
            <span>知识库蒸馏规则</span>
            <span class="wb-sec-sub">P1-11 · DISTILLED RULES</span>
          </div>
          <n-button size="tiny" quaternary @click="loadRules()">刷新</n-button>
        </div>
        <div v-if="rules.length" class="mon-rules">
          <div v-for="(r, i) in rules" :key="i" class="mon-rule">
            <div class="mon-rule-head">
              <span class="mon-rule-idx">#{{ r.id }}</span>
              <span class="mon-rule-gene mono">{{ r.gene_id }}</span>
              <span class="mon-rule-fid">fidelity {{ Number(r.fidelity).toFixed(2) }}</span>
            </div>
            <div class="mon-rule-body">
              <span class="mon-rule-cond">{{ r.rule_json?.condition }}</span>
              <span class="mon-rule-arrow">→</span>
              <span class="mon-rule-action" :class="r.rule_json?.action">{{ r.rule_json?.action }}</span>
            </div>
          </div>
        </div>
        <div v-else class="wb-empty">暂无蒸馏规则（/api/distill 生成）</div>
      </div>

      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(79,195,247,0.12);color:#4fc3f7"><Icon icon="mdi:wrench-outline" :width="17" /></span>
            <span>工具调用日志</span>
            <span class="wb-sec-sub">P0-11 · 三级权限</span>
          </div>
          <n-button size="tiny" quaternary @click="loadTools()">刷新</n-button>
        </div>
        <div v-if="toolLog.length" class="mon-tools">
          <div v-for="(t, i) in toolLog" :key="i" class="mon-tool" :class="{ denied: !t.allowed }">
            <span class="mon-tool-perm" :class="t.permission">{{ t.permission }}</span>
            <span class="mon-tool-name mono">{{ t.tool }}</span>
            <span class="mon-tool-status">{{ t.allowed ? '✓' : '✗ ' + (t.reason || '') }}</span>
          </div>
        </div>
        <div v-else class="wb-empty">暂无工具调用（/api/tools/call 触发）</div>
      </div>
    </div>

    <!-- 实时日志 -->
    <div class="wb-card mon-log-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:console-line" :width="17" /></span>
          <span>实时日志流</span>
          <span class="wb-sec-sub">LIVE LOGS · {{ displayLogs.length }}</span>
        </div>
        <n-space :size="8" align="center">
          <n-radio-group v-model:value="levelFilter" size="small">
            <n-radio-button v-for="lv in ['ALL', 'INFO', 'WARNING', 'ERROR']" :key="lv" :value="lv" :label="lv" />
          </n-radio-group>
          <n-switch v-model:value="autoScroll" size="small">
            <template #checked>滚动</template>
            <template #unchecked>滚动</template>
          </n-switch>
          <n-button size="tiny" quaternary type="primary" @click="clearLogs">
            <template #icon><Icon icon="mdi:delete-sweep-outline" :width="13" /></template>清屏
          </n-button>
        </n-space>
      </div>

      <div ref="logBox" class="mon-log">
        <div v-if="!displayLogs.length" class="mon-log-empty">等待日志…（任务/决策/增量采集将实时推送）</div>
        <div
          v-for="(l, i) in displayLogs" :key="i"
          class="mon-log-line" :class="l.level.toLowerCase()"
        >
          <span class="mon-log-ts mono">{{ l.ts }}</span>
          <span class="mon-log-lv" :class="l.level.toLowerCase()">{{ l.level.slice(0, 4) }}</span>
          <span class="mon-log-src mono">{{ l.source }}</span>
          <span class="mon-log-msg">{{ l.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import api from '../api'
import { useSocketStore } from '../stores/socket'

const socket = useSocketStore()
const health = ref(null)
const loading = ref(false)
const levelFilter = ref('ALL')
const autoScroll = ref(true)
const logBox = ref(null)
let timer = null

const runningCount = computed(() => health.value?.components?.tasks?.running ?? 0)
const displayLogs = computed(() => {
  const logs = socket.logEvents
  if (levelFilter.value === 'ALL') return logs
  return logs.filter((l) => l.level === levelFilter.value)
})

const rules = ref([])
const toolLog = ref([])
async function loadRules() { try { const { data } = await api.knowledgeRules(); rules.value = (data.rules || []).map((r) => ({ ...r, rule_json: typeof r.rule_json === 'string' ? (JSON.parse(r.rule_json) || {}) : (r.rule_json || {}) })) } catch {} }
async function loadTools() { try { const { data } = await api.tools(); toolLog.value = (data.call_log || []).slice().reverse() } catch {} }

const dbDetail = (k, v) => {
  if (k === 'timescaledb') return `${v.klines?.toLocaleString()} K线`
  if (k === 'neo4j') return `${v.nodes} 节点`
  if (k === 'chromadb') return `${v.cases} 案例`
  return ''
}

async function loadHealth() {
  loading.value = true
  try {
    const { data } = await api.get('/health')
    health.value = data
  } finally { loading.value = false }
}
function clearLogs() { socket.logEvents = [] }
function scrollToBottom() {
  if (!autoScroll.value || !logBox.value) return
  logBox.value.scrollTop = logBox.value.scrollHeight
}

watch(() => socket.logEvents.length, () => { nextTick(scrollToBottom) })

onMounted(() => {
  loadHealth()
  loadRules()
  loadTools()
  timer = setInterval(() => { loadHealth() }, 15000)
  nextTick(scrollToBottom)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped lang="scss">
.mon { display: flex; flex-direction: column; gap: 1.2rem; }

.wb-spacer { flex: 1; }

.mon-overall {
  display: inline-flex; align-items: center; gap: 0.5rem;
  font-size: 0.8rem; font-weight: 600; letter-spacing: 0.1em;
  &.healthy { color: var(--green); }
  &.degraded { color: var(--amber); }
}
.mon-overall-dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 10px var(--green);
  animation: monPulse 2s infinite;
}
@keyframes monPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.mon-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1.2rem; }

.mon-row {
  display: flex; align-items: center; gap: 0.7rem;
  padding: 0.5rem 0; border-bottom: 0.5px solid var(--border);
  font-size: 0.74rem;
  &:last-child { border-bottom: none; }
}
.mon-row-name { display: flex; align-items: center; gap: 0.4rem; width: 110px; &.off { color: var(--red); } }
.mon-row-dot { width: 7px; height: 7px; border-radius: 50%; &.on { background: var(--green); } &.off { background: var(--red); } }
.mon-row-detail { flex: 1; font-size: 0.62rem; color: var(--faint); text-align: right; }

.mon-layers { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; }
.mon-layer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0.5rem 0.7rem; border-radius: 6px;
  background: rgba(239, 83, 80, 0.05); border: 0.5px solid rgba(239, 83, 80, 0.25);
  &.ok { background: rgba(105, 240, 174, 0.05); border-color: rgba(105, 240, 174, 0.25); }
}
.mon-layer-id { font-size: 0.72rem; font-weight: 600; color: var(--dim); }
.mon-layer-status { font-size: 0.8rem; &.ok { color: var(--green); } }

.mon-fresh { display: flex; flex-direction: column; gap: 0.5rem; }
.mon-fresh-item { display: flex; align-items: center; gap: 0.6rem; }
.mon-fresh-age { font-family: var(--mono); font-size: 0.66rem; width: 80px; text-align: right; &.green { color: var(--green); } &.amber { color: var(--amber); } &.red { color: var(--red); } }

/* 日志流 */
.mon-log-card { padding-bottom: 0; }
.mon-log {
  height: 420px; overflow-y: auto;
  background: #0a0c10; border-radius: 8px;
  border: 0.5px solid var(--border);
  padding: 0.6rem 0.8rem;
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 0.66rem;
}
.mon-log-empty { color: var(--faint); text-align: center; padding: 3rem 0; }
.mon-log-line {
  display: flex; gap: 0.6rem; align-items: baseline;
  padding: 0.22rem 0; border-bottom: 0.5px solid rgba(255, 255, 255, 0.02);
  color: var(--dim);
  &.info { color: rgba(255, 255, 255, 0.6); }
  &.warning { color: var(--amber); }
  &.error { color: var(--red); }
}
.mon-log-ts { color: var(--faint); flex: 0 0 60px; }
.mon-log-lv {
  flex: 0 0 34px; font-weight: 700;
  &.info { color: var(--accent); }
  &.warn { color: var(--amber); }
  &.error { color: var(--red); }
}
.mon-log-src { flex: 0 0 200px; color: rgba(255, 255, 255, 0.35); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mon-log-msg { flex: 1; word-break: break-all; }
.mon-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
.mon-rules { display: flex; flex-direction: column; gap: 0.4rem; max-height: 260px; overflow-y: auto; }
.mon-rule { background: var(--surface2); border-radius: 4px; padding: 0.45rem 0.6rem; }
.mon-rule-head { display: flex; gap: 0.5rem; align-items: center; font-size: 0.6rem; color: var(--faint); margin-bottom: 0.2rem; }
.mon-rule-gene { color: var(--dim); }
.mon-rule-fid { margin-left: auto; color: #ce93d8; }
.mon-rule-body { display: flex; gap: 0.4rem; align-items: center; font-size: 0.68rem; }
.mon-rule-cond { color: var(--dim); flex: 1; }
.mon-rule-arrow { color: var(--faint); }
.mon-rule-action { font-weight: 700; text-transform: uppercase; }
.mon-rule-action.long { color: #69f0ae; }
.mon-rule-action.short { color: #ef5350; }
.mon-rule-action.hold { color: #ffd54f; }
.mon-tools { display: flex; flex-direction: column; gap: 0.3rem; max-height: 260px; overflow-y: auto; }
.mon-tool { display: flex; gap: 0.5rem; align-items: center; font-size: 0.68rem; padding: 0.3rem 0.5rem; background: var(--surface2); border-radius: 3px; }
.mon-tool.denied { background: rgba(239,83,80,0.07); }
.mon-tool-perm { font-size: 0.56rem; padding: 0.1rem 0.4rem; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.05em; }
.mon-tool-perm.read { background: rgba(79,195,247,0.15); color: #4fc3f7; }
.mon-tool-perm.calc { background: rgba(255,213,79,0.15); color: #ffd54f; }
.mon-tool-perm.act { background: rgba(239,83,80,0.15); color: #ef5350; }
.mon-tool-name { color: var(--dim); }
.mon-tool-status { margin-left: auto; color: var(--faint); font-size: 0.62rem; }

@media (max-width: 1100px) {
  .mon-grid { grid-template-columns: 1fr; }
}
</style>
