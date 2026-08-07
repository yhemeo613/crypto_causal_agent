<template>
  <div class="pc">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">感知因果 <span>PERCEPTION</span></div>
        <div class="page-sub">三时序切片 · 统计因果 (Granger) · 因果图谱</div>
      </div>
      <n-button secondary size="small" :loading="loading" @click="loadAll">
        <template #icon><Icon icon="mdi:refresh" :width="14" /></template>刷新感知
      </n-button>
    </div>

    <!-- 概览条 -->
    <div class="pc-bar">
      <span class="pc-bar-symbol">
        <Icon icon="mdi:currency-btc" :width="15" style="vertical-align:-2px" />
        BTCUSDT
      </span>
      <span class="pc-regime" :class="regimeClass">
        <span class="pc-regime-dot"></span>{{ regimeText }}
      </span>
      <span class="pc-sep"></span>
      <div class="pc-quote" v-if="overview">
        <span class="pc-quote-label">最新价</span>
        <span class="pc-quote-val">{{ overview.price }}</span>
      </div>
      <div class="pc-quote" v-if="overview">
        <span class="pc-quote-label">区间涨跌</span>
        <span class="pc-quote-val" :class="overview.pct >= 0 ? 'up' : 'down'">{{ overview.pctText }}</span>
      </div>
      <div class="pc-quote" v-if="overview">
        <span class="pc-quote-label">波动率</span>
        <span class="pc-quote-val">{{ overview.volText }}</span>
      </div>
      <span class="pc-spacer"></span>
      <span class="pc-stamp">{{ tsText }}</span>
    </div>

    <!-- 三时序切片 -->
    <div class="pc-slices" v-if="perception">
      <div class="pc-card pc-slice" v-for="(s, key) in slices" :key="key">
        <div class="pc-slice-head">
          <span class="pc-slice-badge" :class="s.level">{{ s.level }}</span>
          <span class="pc-slice-name">{{ sliceName(key) }}</span>
          <span class="pc-slice-window">{{ s.window_days }}天</span>
        </div>

        <div class="pc-slice-price" :class="s.pct_change >= 0 ? 'up' : 'down'">
          {{ fmtPrice(s.price_current) }}
        </div>
        <div class="pc-slice-pct" :class="s.pct_change >= 0 ? 'up' : 'down'">
          {{ (s.pct_change * 100).toFixed(2) }}%
        </div>

        <div class="pc-slice-kpis">
          <div class="pc-kpi">
            <span class="pc-kpi-label">波动率</span>
            <span class="pc-kpi-val">{{ (s.volatility * 100).toFixed(1) }}%</span>
          </div>
          <div class="pc-kpi">
            <span class="pc-kpi-label">趋势强度</span>
            <span class="pc-kpi-val">{{ s.trend_strength?.toFixed(2) }}</span>
          </div>
          <div class="pc-kpi">
            <span class="pc-kpi-label">量比</span>
            <span class="pc-kpi-val">{{ s.volume_ratio?.toFixed(2) }}x</span>
          </div>
          <div class="pc-kpi">
            <span class="pc-kpi-label">趋势方向</span>
            <span class="pc-kpi-val" :class="trendClass(s.trend_direction)">{{ trendText(s.trend_direction) }}</span>
          </div>
        </div>

        <div class="pc-macro" v-if="s.macro_indicators && Object.keys(s.macro_indicators).length">
          <div class="pc-macro-label">宏观因子</div>
          <div class="pc-macro-chips">
            <span v-for="(v, k) in s.macro_indicators" :key="k" class="pc-chip">{{ k }}: {{ fmtMacro(v) }}</span>
          </div>
        </div>
      </div>

      <!-- 补充卡：局部高低点信号 -->
      <div class="pc-card pc-slice pc-signal">
        <div class="pc-slice-head">
          <span class="pc-slice-badge" style="background:rgba(255,213,79,0.1);color:var(--amber);border-color:rgba(255,213,79,0.3)">SIG</span>
          <span class="pc-slice-name">信号标记</span>
          <span class="pc-slice-window">L1 微观</span>
        </div>
        <div class="pc-signal-grid">
          <div class="pc-signal-item" :class="{ on: slices.L1?.is_local_high }">
            <Icon icon="mdi:arrow-up-bold-box" :width="22" />
            <span>局部高点</span>
          </div>
          <div class="pc-signal-item" :class="{ on: slices.L1?.is_local_low }">
            <Icon icon="mdi:arrow-down-bold-box" :width="22" />
            <span>局部低点</span>
          </div>
        </div>
        <div class="pc-signal-note">
          <Icon icon="mdi:lightbulb-outline" :width="13" style="vertical-align:-2px" />
          高/低点同现提示短期方向不明，建议观望或等待确认
        </div>
      </div>
    </div>
    <div v-else class="pc-empty">
      <Icon icon="mdi:eye-off-outline" :width="26" style="opacity:0.5" />
      <p>感知数据加载中…</p>
      <span>点击「刷新感知」或稍候自动加载</span>
    </div>

    <!-- 因果图谱 -->
    <div class="pc-card">
      <div class="pc-sec-head">
        <div class="pc-sec-title">
          <span class="pc-sec-icon"><Icon icon="mdi:graph-outline" :width="17" /></span>
          <span>因果图谱</span>
          <span class="pc-sec-sub">CAUSAL GRAPH · NEO4J</span>
        </div>
        <div class="pc-sec-meta">
          <span class="pc-meta-item"><span class="pc-meta-dot node"></span>{{ graph.nodes.length }} 节点</span>
          <span class="pc-meta-item"><span class="pc-meta-dot edge"></span>{{ graph.links.length }} 因果边</span>
          <span class="pc-meta-item"><span class="pc-meta-dot strong"></span>置信度 ≥ 0.6</span>
        </div>
        <div v-if="evolutionSteps.length" class="pc-sec-meta">
          <n-button size="tiny" quaternary :disabled="evolutionStep <= 0" @click="evolutionStep--; applyEvolutionStep(evolutionStep)">◀</n-button>
          <span style="font-size:.62rem;color:var(--faint)">演化 {{ evolutionStep + 1 }}/{{ evolutionSteps.length }} · {{ (evolutionSteps[evolutionStep]?.ts || '').slice(0, 19) }}</span>
          <n-button size="tiny" quaternary :disabled="evolutionStep >= evolutionSteps.length - 1" @click="evolutionStep++; applyEvolutionStep(evolutionStep)">▶</n-button>
        </div>
      </div>
      <v-chart :option="graphOption" autoresize style="height:440px" />
    </div>

    <!-- Granger 因果检验 -->
    <div class="pc-card">
      <div class="pc-sec-head">
        <div class="pc-sec-title">
          <span class="pc-sec-icon" style="color:var(--green);background:rgba(105,240,174,0.1)"><Icon icon="mdi:chart-box-outline" :width="17" /></span>
          <span>Granger 因果检验</span>
          <span class="pc-sec-sub">STATISTICAL CAUSALITY · GRANGER</span>
        </div>
        <n-button size="small" type="primary" ghost :loading="grangerLoading" @click="loadGranger">
          <template #icon><Icon icon="mdi:flask-outline" :width="14" /></template>运行检验
        </n-button>
      </div>

      <n-table v-if="granger.length" size="small" :bordered="false" :single-line="false" class="pc-table">
        <thead>
          <tr>
            <th>因子 → 目标</th>
            <th>p-value</th>
            <th>结论</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(t, i) in granger" :key="i">
            <td class="pc-cell-factor">
              <span class="pc-factor">{{ t.factor }}</span>
              <Icon icon="mdi:arrow-right" :width="14" style="color:var(--faint)" />
              <span class="pc-factor">{{ t.target }}</span>
            </td>
            <td class="mono">{{ Number(t.p_value).toFixed(4) }}</td>
            <td>
              <n-tag size="tiny" :type="t.p_value < 0.05 ? 'success' : 'default'" :bordered="false" round>
                {{ t.p_value < 0.05 ? '显著 (α=0.05)' : '不显著' }}
              </n-tag>
            </td>
          </tr>
        </tbody>
      </n-table>
      <div v-else class="pc-empty" style="padding:1.6rem 0">
        <Icon icon="mdi:flask-outline" :width="24" style="opacity:0.5" />
        <p>尚无检验结果</p>
        <span>运行 Granger 检验后显示（需 ≥30 天日线数据）</span>
      </div>
    </div>

    <!-- P1-13 异常事件 -->
    <div class="pc-card">
      <div class="pc-sec-head">
        <div class="pc-sec-title">
          <span class="pc-sec-icon" style="color:#ef5350;background:rgba(239,83,80,0.1)"><Icon icon="mdi:alert-decagram" :width="17" /></span>
          <span>异常事件</span>
          <span class="pc-sec-sub">P1-13 · 闪崩 / 波动尖峰 / 费率极端</span>
        </div>
        <span class="pc-chip">{{ anomalies.length }} 个</span>
      </div>
      <div v-if="anomalies.length">
        <div v-for="(a, i) in anomalies" :key="i" class="pc-anomaly" :class="a.severity">
          <Icon icon="mdi:alert" :width="15" style="flex-shrink:0" />
          <div style="flex:1">
            <div><b>{{ anomalyType(a.type) }}</b> · <span class="pc-sev">{{ a.severity }}</span></div>
            <div style="font-size:.68rem;color:var(--faint)">{{ a.detail }}</div>
          </div>
        </div>
      </div>
      <div v-else class="pc-empty" style="padding:1.4rem 0">
        <Icon icon="mdi:shield-check-outline" :width="22" style="opacity:0.5;color:var(--green)" />
        <p>当前无异常事件</p>
      </div>
    </div>

    <!-- P1-04 Regime 策略表 -->
    <div class="pc-card">
      <div class="pc-sec-head">
        <div class="pc-sec-title">
          <span class="pc-sec-icon" style="color:#ffd54f;background:rgba(255,213,79,0.1)"><Icon icon="mdi:tune-variant" :width="17" /></span>
          <span>Regime 决策策略</span>
          <span class="pc-sec-sub">P1-04 · 自适应权重调节</span>
        </div>
        <span class="pc-chip amber">当前：{{ regimeText }}</span>
      </div>
      <n-table size="small" :bordered="false" :single-line="false" class="pc-table">
        <thead>
          <tr><th>市场状态</th><th>仓位缩放</th><th>杠杆上限</th><th>置信门槛</th><th>模式</th></tr>
        </thead>
        <tbody>
          <tr v-for="(p, name) in regimePolicies" :key="name">
            <td><span class="pc-regime-mini" :class="'regime-' + name">{{ regimeTextOf(name) }}</span></td>
            <td class="mono">{{ (p.position_scale * 100).toFixed(0) }}%</td>
            <td class="mono">{{ p.max_leverage }}x</td>
            <td class="mono">{{ (p.min_confidence * 100).toFixed(0) }}%</td>
            <td>{{ p.mode }}</td>
          </tr>
        </tbody>
      </n-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import api from '../api'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([GraphChart, TooltipComponent, LegendComponent, CanvasRenderer])

const perception = ref(null)
const granger = ref([])
const graph = ref({ nodes: [], links: [] })
const evolutionSteps = ref([])
const evolutionStep = ref(0)

// P2-08 图谱演化：按时间切片切换
function applyEvolutionStep(idx) {
  const steps = evolutionSteps.value
  if (!steps.length) return
  const step = steps[Math.min(idx, steps.length - 1)]
  const nodes = new Map()
  const links = []
  for (const t of step.triplets || []) {
    nodes.set(t.cause, { id: t.cause, conf: 0.5 })
    nodes.set(t.effect, { id: t.effect, conf: 0.5 })
    links.push({ source: t.cause, target: t.effect, relation: t.relation, confidence: t.confidence })
  }
  graph.value = { nodes: [...nodes.values()], links }
}
async function loadEvolution() {
  try {
    const { data } = await api.get('/perception/graph-evolution', { params: { buckets: 6 } })
    if (data.evolution?.length) { evolutionSteps.value = data.evolution; applyEvolutionStep(evolutionStep.value) }
  } catch {}
}
const loading = ref(false)
const grangerLoading = ref(false)

const slices = computed(() => {
  if (!perception.value) return {}
  return {
    L1: perception.value.l1_micro || {},
    L2: perception.value.l2_meso || {},
    L3: perception.value.l3_macro || {},
  }
})

const anomalies = computed(() => (perception.value?.anomalies) || [])
const anomalyType = (t) => ({ flash_crash: '闪崩', vol_spike: '波动尖峰', funding_extreme: '资金费率极端' }[t] || t)
const regimePolicies = ref({})
async function loadRegimePolicy() { try { const { data } = await api.regimePolicy(); regimePolicies.value = data.policies || {} } catch {} }
const regimeTextOf = (r) => ({ trend_up: '趋势向上', trend_down: '趋势向下', range: '震荡市', high_vol: '高波动', unknown: '未知' }[r] || r)

const regime = computed(() => perception.value?.regime || 'unknown')
const regimeClass = computed(() => ({
  trend_up: 'up', trend_down: 'down', range: 'range', high_vol: 'vol', unknown: '',
}[regime.value] || ''))
const regimeText = computed(() => ({
  trend_up: '趋势向上', trend_down: '趋势向下', range: '震荡', high_vol: '高波动', unknown: '未知',
}[regime.value] || regime.value))

const overview = computed(() => {
  const l3 = slices.value.L3 || {}
  if (!l3.price_current) return null
  return {
    price: Number(l3.price_current).toLocaleString(undefined, { maximumFractionDigits: 0 }),
    pct: l3.pct_change || 0,
    pctText: `${((l3.pct_change || 0) * 100).toFixed(2)}%`,
    volText: `${((l3.volatility || 0) * 100).toFixed(1)}%`,
  }
})

const tsText = computed(() => (perception.value?.timestamp ? String(perception.value.timestamp).slice(5, 16) : ''))

const graphOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {},
  series: [{
    type: 'graph',
    layout: 'force',
    roam: true,
    draggable: true,
    data: graph.value.nodes.map((n) => ({
      id: n.id, name: n.id,
      symbolSize: 18 + (n.conf || 0.5) * 26,
      itemStyle: { color: (n.conf || 0.5) > 0.6 ? '#69f0ae' : '#4fc3f7' },
    })),
    links: graph.value.links.map((l) => ({
      source: l.source, target: l.target, value: l.confidence,
      lineStyle: { width: 1 + (l.confidence || 0.5) * 3, opacity: 0.4 + (l.confidence || 0.5) * 0.5 },
      label: { show: true, formatter: l.relation, fontSize: 9, color: 'rgba(255,255,255,0.5)' },
    })),
    force: { repulsion: 320, edgeLength: 130 },
    label: { show: true, position: 'right', fontSize: 11, color: 'rgba(255,255,255,0.85)' },
  }],
}))

const fmtPrice = (n) => (n == null ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }))
const fmtMacro = (v) => (typeof v === 'number' ? Number(v).toFixed(2) : v)
const sliceName = (k) => ({ L1: '微观切片', L2: '中期切片', L3: '宏观切片' }[k] || k)
const trendText = (d) => ({ up: '↑ 上涨', down: '↓ 下跌', neutral: '→ 中性' }[d] || d || '-')
const trendClass = (d) => ({ up: 'up', down: 'down', neutral: '' }[d] || '')

async function loadSlices() {
  try { const { data } = await api.perceptionSlices(); if (data.perception) perception.value = data.perception } catch {}
}
async function loadGranger() {
  grangerLoading.value = true
  try {
    const { data } = await api.perceptionGranger()
    granger.value = (data.triplets || []).map((t) => ({ factor: t.factor || t.source, target: t.target, p_value: t.p_value || t.pvalue }))
  } catch {} finally { grangerLoading.value = false }
}
async function loadGraph() { try { const { data } = await api.causalGraph(); graph.value = data } catch {} }
async function loadAll() {
  loading.value = true
  try { await Promise.all([loadSlices(), loadGranger(), loadGraph(), loadEvolution(), loadRegimePolicy()]) } finally { loading.value = false }
}

onMounted(loadAll)
</script>

<style scoped lang="scss">
.pc { display: flex; flex-direction: column; gap: 1.2rem; }

/* ── 概览条 ── */
.pc-bar {
  display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
  padding: 0.8rem 1.2rem; border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
}
.pc-bar-symbol { font-size: 0.85rem; font-weight: 600; letter-spacing: 0.04em; }
.pc-regime {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.18rem 0.7rem; border-radius: 999px; font-size: 0.66rem;
  color: var(--dim); background: rgba(255, 255, 255, 0.04); border: 0.5px solid var(--border);
  .pc-regime-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
  &.up { color: var(--green); border-color: rgba(105, 240, 174, 0.35); background: rgba(105, 240, 174, 0.08); .pc-regime-dot { background: var(--green); } }
  &.down { color: var(--red); border-color: rgba(239, 83, 80, 0.35); background: rgba(239, 83, 80, 0.08); .pc-regime-dot { background: var(--red); } }
  &.range { color: var(--amber); border-color: rgba(255, 213, 79, 0.35); background: rgba(255, 213, 79, 0.08); .pc-regime-dot { background: var(--amber); } }
  &.vol { color: #ce93d8; border-color: rgba(206, 147, 216, 0.35); background: rgba(206, 147, 216, 0.08); .pc-regime-dot { background: #ce93d8; } }
}
.pc-sep { width: 1px; height: 18px; background: var(--border); }
.pc-quote { display: flex; flex-direction: column; gap: 0.05rem; }
.pc-quote-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.12em; text-transform: uppercase; }
.pc-quote-val { font-family: var(--mono); font-size: 0.85rem; font-weight: 600; &.up { color: var(--green); } &.down { color: var(--red); } }
.pc-spacer { flex: 1; }
.pc-stamp { font-size: 0.6rem; color: var(--faint); font-family: var(--mono); }

/* ── 通用卡片 ── */
.pc-card {
  padding: 1.3rem 1.5rem; border-radius: 10px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
}
.pc-sec-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.pc-sec-title { display: flex; align-items: center; gap: 0.6rem; font-size: 0.82rem; font-weight: 500; }
.pc-sec-icon {
  width: 30px; height: 30px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent); background: rgba(79, 195, 247, 0.1);
}
.pc-sec-sub { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.25em; }
.pc-sec-meta { display: flex; gap: 1rem; flex-wrap: wrap; }
.pc-meta-item { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.64rem; color: var(--dim); }
.pc-meta-dot { width: 7px; height: 7px; border-radius: 50%; &.node { background: var(--accent); } &.edge { background: var(--faint); } &.strong { background: var(--green); } }

/* ── 三时序切片 ── */
.pc-slices {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.2rem;
}
.pc-slice { display: flex; flex-direction: column; gap: 0.8rem; }
.pc-slice-head { display: flex; align-items: center; gap: 0.5rem; }
.pc-slice-badge {
  padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.1em;
  color: var(--accent); background: rgba(79, 195, 247, 0.1); border: 0.5px solid rgba(79, 195, 247, 0.3);
}
.pc-slice-name { font-size: 0.72rem; color: var(--dim); }
.pc-slice-window { margin-left: auto; font-size: 0.58rem; color: var(--faint); font-family: var(--mono); }

.pc-slice-price { font-size: 1.5rem; font-weight: 700; font-family: var(--mono); &.up { color: var(--green); } &.down { color: var(--red); } }
.pc-slice-pct { font-size: 0.78rem; font-family: var(--mono); &.up { color: var(--green); } &.down { color: var(--red); } }

.pc-slice-kpis { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; }
.pc-kpi {
  padding: 0.5rem 0.6rem; border-radius: 6px;
  background: rgba(255, 255, 255, 0.03); border: 0.5px solid var(--border);
  display: flex; flex-direction: column; gap: 0.15rem;
}
.pc-kpi-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.08em; }
.pc-kpi-val { font-family: var(--mono); font-size: 0.78rem; font-weight: 600; &.up { color: var(--green); } &.down { color: var(--red); } }

.pc-macro { display: flex; flex-direction: column; gap: 0.4rem; }
.pc-macro-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.12em; text-transform: uppercase; }
.pc-macro-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.pc-chip {
  padding: 0.12rem 0.5rem; border-radius: 999px; font-size: 0.6rem;
  color: var(--amber); background: rgba(255, 213, 79, 0.08); border: 0.5px solid rgba(255, 213, 79, 0.25);
}

/* 信号卡 */
.pc-signal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
.pc-signal-item {
  display: flex; flex-direction: column; align-items: center; gap: 0.4rem;
  padding: 0.9rem 0; border-radius: 8px;
  color: var(--faint); background: rgba(255, 255, 255, 0.02); border: 0.5px solid var(--border);
  font-size: 0.66rem;
  &.on { color: var(--amber); border-color: rgba(255, 213, 79, 0.4); background: rgba(255, 213, 79, 0.06); box-shadow: 0 0 10px rgba(255, 213, 79, 0.1); }
}
.pc-signal-note { display: flex; gap: 0.35rem; font-size: 0.6rem; color: var(--faint); line-height: 1.6; }

/* 表格 */
.pc-table :deep(th) { color: var(--faint); font-weight: 500; font-size: 0.66rem; letter-spacing: 0.08em; }
.pc-cell-factor { display: flex; align-items: center; gap: 0.5rem; }
.pc-factor { font-family: var(--mono); font-size: 0.72rem; }

.pc-empty {
  text-align: center;
  color: var(--faint);
  display: flex; flex-direction: column; align-items: center; gap: 0.4rem;
}
.pc-anomaly {
  display: flex; gap: 0.6rem; align-items: flex-start;
  padding: 0.55rem 0.7rem; margin-bottom: 0.4rem; border-radius: 4px;
  background: rgba(255,213,79,0.07); border-left: 2px solid #ffd54f; font-size: 0.72rem;
}
.pc-anomaly.high { background: rgba(239,83,80,0.09); border-left-color: #ef5350; }
.pc-sev { color: var(--amber); text-transform: uppercase; font-size: 0.6rem; }
.pc-chip { font-size: 0.62rem; color: var(--faint); background: var(--surface2); padding: 0.2rem 0.6rem; border-radius: 2px; }
.pc-chip.amber { color: var(--amber); }
.pc-regime-mini { padding: 0.1rem 0.5rem; border-radius: 2px; font-size: 0.62rem; color: var(--dim); background: var(--surface2); }
.pc-regime-mini.regime-trend_up { color: #69f0ae; }
.pc-regime-mini.regime-trend_down { color: #ef5350; }
.pc-regime-mini.regime-range { color: #ffd54f; }
.pc-regime-mini.regime-high_vol { color: #ce93d8; }

@media (max-width: 1100px) {
  .pc-slices { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 700px) {
  .pc-slices { grid-template-columns: 1fr; }
}
</style>
