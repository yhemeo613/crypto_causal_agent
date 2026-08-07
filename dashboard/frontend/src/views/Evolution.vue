<template>
  <div class="ev" ref="root">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">进化 <span>EVOLUTION</span></div>
        <div class="page-sub">DEAP 遗传进化 · 种群管理 · 3D 适应度景观</div>
      </div>
    </div>

    <!-- 状态条 -->
    <div class="wb-bar">
      <span class="ev-status" :class="running ? 'running' : 'idle'">
        <span class="ev-status-dot"></span>
        {{ running ? `进化中 · 任务 #${runningTaskId}` : '空闲' }}
      </span>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">已完成代数</span>
        <span class="wb-stat-val">{{ maxGeneration }} 代</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">最优适应度</span>
        <span class="wb-stat-val" :class="bestFitness > 0 ? 'up' : ''">{{ bestFitness.toFixed(4) }}</span>
      </div>
      <span class="wb-spacer" style="flex:1"></span>
      <span class="wb-chip green"><Icon icon="mdi:dna" :width="13" />DEAP 引擎</span>
    </div>

    <!-- 参数 + 预设 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:dna" :width="17" /></span>
          <span>进化参数</span>
          <span class="wb-sec-sub">PARAMETERS</span>
        </div>
        <n-space :size="6">
          <n-button v-for="p in presets" :key="p.name" size="tiny" quaternary :type="preset === p.name ? 'primary' : 'default'" @click="applyPreset(p.name)">
            {{ p.label }}
          </n-button>
        </n-space>
      </div>
      <div class="ev-config">
        <div class="ev-field">
          <label class="wb-bar-label">代数</label>
          <n-input-number v-model:value="form.generations" size="small" style="width:90px" :min="1" :max="200" />
        </div>
        <div class="ev-field">
          <label class="wb-bar-label">种群</label>
          <n-input-number v-model:value="form.population_size" size="small" style="width:90px" :min="2" :max="50" />
        </div>
        <div class="ev-field">
          <label class="wb-bar-label">变异率</label>
          <n-input-number v-model:value="form.mutation_rate" size="small" style="width:90px" :min="0" :max="1" :step="0.05" />
        </div>
        <div class="ev-field">
          <label class="wb-bar-label">交叉率</label>
          <n-input-number v-model:value="form.crossover_rate" size="small" style="width:90px" :min="0" :max="1" :step="0.05" />
        </div>
        <div class="ev-field">
          <label class="wb-bar-label">锦标赛</label>
          <n-input-number v-model:value="form.tournament_size" size="small" style="width:90px" :min="1" :max="10" />
        </div>
        <div class="ev-field" style="margin-left:auto">
          <n-space :size="8">
            <n-button type="primary" :loading="running" @click="start">
              <template #icon><Icon icon="mdi:play" :width="15" /></template>开始进化
            </n-button>
            <n-button v-if="runningTaskId" type="warning" @click="pause">
              <template #icon><Icon icon="mdi:pause" :width="15" /></template>暂停
            </n-button>
          </n-space>
        </div>
      </div>
    </div>

    <!-- 曲线 + 3D -->
    <div class="ev-grid">
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon"><Icon icon="mdi:chart-line" :width="17" /></span>
            <span>适应度曲线</span>
            <span class="wb-sec-sub">FITNESS</span>
          </div>
          <span class="wb-chip green">{{ curve.length }} 点</span>
        </div>
        <v-chart :option="curveOption" autoresize style="height:300px" />
      </div>
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(255,213,79,0.12);color:#ffd54f"><Icon icon="mdi:chart-bell-curve-cumulative" :width="17" /></span>
            <span>收敛性分析</span>
            <span class="wb-sec-sub">P2-04</span>
          </div>
          <n-button size="tiny" quaternary @click="loadConvergence()">刷新</n-button>
        </div>
        <div v-if="convergence && !convergence.error" class="evo-conv-grid">
          <div class="evo-conv-item"><span class="evo-conv-label">代数</span><span class="evo-conv-val">{{ convergence.generations }}</span></div>
          <div class="evo-conv-item"><span class="evo-conv-label">收敛</span><span class="evo-conv-val" :style="{ color: convergence.converged ? 'var(--green)' : 'var(--amber)' }">{{ convergence.converged ? '已收敛' : '未收敛' }}</span></div>
          <div class="evo-conv-item"><span class="evo-conv-label">收敛代</span><span class="evo-conv-val">{{ convergence.converged_at_generation ?? '—' }}</span></div>
          <div class="evo-conv-item"><span class="evo-conv-label">基因多样性</span><span class="evo-conv-val">{{ (convergence.gene_diversity_ratio * 100).toFixed(0) }}%</span></div>
          <div class="evo-conv-item"><span class="evo-conv-label">适应度方差</span><span class="evo-conv-val mono">{{ convergence.fitness_variance_tail }}</span></div>
          <div class="evo-conv-item"><span class="evo-conv-label">末代 best</span><span class="evo-conv-val mono">{{ convergence.best_fitness }}</span></div>
        </div>
        <div v-else class="wb-empty">{{ convergence?.error || '加载中…' }}</div>
      </div>
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(79,195,247,0.12);color:#4fc3f7"><Icon icon="mdi:source-branch-compare" :width="17" /></span>
            <span>实验版本对比</span>
            <span class="wb-sec-sub">P2-07</span>
          </div>
          <n-button size="tiny" quaternary @click="loadExperiments()">刷新</n-button>
        </div>
        <div v-if="experiments.length" class="evo-exp">
          <n-select size="small" v-model:value="expA" :options="expOptions" placeholder="实验 A" style="width:150px" />
          <span style="color:var(--faint)">vs</span>
          <n-select size="small" v-model:value="expB" :options="expOptions" placeholder="实验 B" style="width:150px" />
          <n-button size="small" type="primary" ghost :disabled="!expA || !expB" @click="compareExps()">对比</n-button>
          <span v-if="expCompare" class="evo-compare-result" :class="{ win: expCompare.better !== 'B', lose: expCompare.better === 'B' }">
            {{ expCompare.better }} 更优 · Δ{{ expCompare.best_diff }}
          </span>
        </div>
        <div v-else class="wb-empty">暂无实验记录（运行进化后产生 experiment_id）</div>
      </div>
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(129,199,132,0.12);color:#81c784"><Icon icon="mdi:sitemap" :width="17" /></span>
            <span>基因进化树</span>
            <span class="wb-sec-sub">P2-03 · 父子关系</span>
          </div>
          <n-button size="tiny" quaternary @click="fetchTree()">刷新</n-button>
        </div>
        <v-chart v-if="treeNodes.length" :option="treeOption" autoresize style="height:320px" />
        <div v-else class="wb-empty">暂无进化树数据（先运行进化实验）</div>
      </div>
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:chart-scatter-plot" :width="17" /></span>
            <span>3D 适应度景观</span>
            <span class="wb-sec-sub">ECHARTS-GL</span>
          </div>
        </div>
        <div ref="gl3d" style="height:300px"></div>
      </div>
    </div>

    <!-- 最佳个体 + 种群浏览器 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:trophy-outline" :width="17" /></span>
          <span>最佳个体</span>
          <span class="wb-sec-sub">BEST GENE</span>
        </div>
        <span v-if="bestGene" class="wb-chip green">fitness {{ bestGene.fitness?.toFixed(4) }}</span>
      </div>
      <div v-if="bestGene?.gene_params" class="ev-best">
        <div class="ev-best-params">
          <div v-for="(v, k) in bestGene.gene_params" :key="k" class="ev-best-param">
            <span class="ev-best-key">{{ k }}</span>
            <span class="ev-best-val mono">{{ v }}</span>
          </div>
        </div>
        <div class="ev-best-side">
          <span class="ev-best-label">来源</span>
          <span class="wb-chip dim mono">#{{ bestGene.generation }} 代 · {{ bestGene.gene_id }}</span>
          <span class="ev-best-label" style="margin-top:0.5rem">亲本</span>
          <span class="wb-chip dim mono">{{ parentText }}</span>
        </div>
      </div>
      <div v-else class="wb-empty" style="padding:1.2rem 0">
        <span>运行进化后将展示每代最优个体的参数</span>
      </div>
    </div>

    <!-- 种群浏览器 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon"><Icon icon="mdi:format-list-bulleted" :width="17" /></span>
          <span>种群浏览器</span>
          <span class="wb-sec-sub">POPULATION · {{ population.length }}</span>
        </div>
        <n-button size="tiny" quaternary type="primary" @click="loadPopulation">
          <template #icon><Icon icon="mdi:refresh" :width="13" /></template>刷新
        </n-button>
      </div>
      <n-table v-if="population.length" size="small" :bordered="false" :single-line="false">
        <thead>
          <tr>
            <th style="width:70px">代数</th>
            <th>基因 ID</th>
            <th>参数</th>
            <th style="width:110px">适应度</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in population.slice(-20).reverse()" :key="i">
            <td><span class="wb-badge">G{{ r.generation }}</span></td>
            <td class="mono dim">{{ r.gene_id }}</td>
            <td class="mono" style="font-size:0.62rem;color:var(--dim)">{{ paramsText(r.gene_params) }}</td>
            <td>
              <span class="wb-chip" :class="r.fitness > 0 ? 'green' : 'dim'">{{ Number(r.fitness).toFixed(4) }}</span>
            </td>
          </tr>
        </tbody>
      </n-table>
      <div v-else class="wb-empty" style="padding:1.6rem 0">
        <Icon icon="mdi:account-group-outline" :width="26" style="opacity:0.5" />
        <p>种群暂无记录</p>
        <span>进化任务完成后个体记录将写入 evolution_logs</span>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:progress-clock" :width="17" /></span>
          <span>最近进化任务</span>
          <span class="wb-sec-sub">TASKS</span>
        </div>
      </div>
      <div v-if="evoTasks.length" class="ev-tasks">
        <div v-for="t in evoTasks" :key="t.id" class="ev-task" :class="t.status">
          <div class="ev-task-top">
            <span class="ev-task-dot" :class="t.status"></span>
            <span class="ev-task-name">{{ t.name }}</span>
            <span class="ev-task-id">#{{ t.id }}</span>
            <span class="wb-spacer" style="flex:1"></span>
            <span class="wb-chip" :class="taskChip(t.status)">{{ t.status }} {{ t.progress }}%</span>
          </div>
          <n-progress type="line" :percentage="Math.round(t.progress)" :height="5"
            :status="t.status === 'failed' ? 'error' : t.status === 'done' ? 'success' : undefined"
            :show-indicator="false" :border-radius="3" />
          <div class="ev-task-msg">{{ t.message }}</div>
        </div>
      </div>
      <div v-else class="wb-empty">
        <Icon icon="mdi:dna" :width="26" style="opacity:0.5" />
        <p>暂无进化任务</p>
        <span>点击「开始进化」后在此查看实时进度</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useMessage } from 'naive-ui'
import api from '../api'
import { useSocketStore } from '../stores/socket'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, ScatterChart, TreeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import gsap from 'gsap'

use([LineChart, ScatterChart, TreeChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const message = useMessage()
const socket = useSocketStore()
const root = ref(null)
const gl3d = ref(null)

const presets = [
  { name: 'quick', label: '快速', generations: 5, population_size: 8, mutation_rate: 0.25, crossover_rate: 0.7, tournament_size: 3 },
  { name: 'standard', label: '标准', generations: 30, population_size: 12, mutation_rate: 0.2, crossover_rate: 0.7, tournament_size: 3 },
  { name: 'deep', label: '深度', generations: 100, population_size: 20, mutation_rate: 0.15, crossover_rate: 0.8, tournament_size: 5 },
]
const preset = ref('standard')
const form = ref({ generations: 30, population_size: 12, mutation_rate: 0.2, crossover_rate: 0.7, tournament_size: 3 })
const curve = ref([])
const population = ref([])
const evoTasks = ref([])
const running = ref(false)
const runningTaskId = ref(null)
let glChart = null

const maxGeneration = computed(() => (curve.value.length ? Math.max(...curve.value.map((c) => c.generation)) : 0))
const bestFitness = computed(() => (curve.value.length ? Math.max(...curve.value.map((c) => c.fitness)) : 0))
const bestGene = computed(() => {
  if (!population.value.length) return null
  return [...population.value].sort((a, b) => (b.fitness || 0) - (a.fitness || 0))[0]
})
const parentText = computed(() => {
  const p = bestGene.value?.parent_gene_ids
  if (!p) return '—'
  return Array.isArray(p) ? p.join(', ') : String(p)
})

const curveOption = computed(() => {
  // 按代数聚合 best（取每代最大 fitness）
  const byGen = {}
  curve.value.forEach((c) => {
    byGen[c.generation] = Math.max(byGen[c.generation] || 0, c.fitness)
  })
  const gens = Object.keys(byGen).map(Number).sort((a, b) => a - b)
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 16, top: 24, bottom: 30 },
    xAxis: { type: 'category', data: gens, axisLabel: { color: 'rgba(255,255,255,0.35)' }, name: '代数' },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }, axisLabel: { color: 'rgba(255,255,255,0.35)' } },
    series: [{
      name: 'best', type: 'line', data: gens.map((g) => byGen[g]),
      smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#69f0ae', width: 2 }, itemStyle: { color: '#69f0ae' },
      areaStyle: { color: 'rgba(105,240,174,0.08)' },
    }],
  }
})

function render3d() {
  if (!gl3d.value) return
  // 动态加载 echarts + echarts-gl（静态副作用导入会拖垮懒加载模块 → 黑屏）
  Promise.all([
    import('echarts').then((m) => (m.default || m)),
    import('echarts-gl'),
  ]).then(([echarts]) => {
    if (!glChart) {
      try { glChart = echarts.init(gl3d.value) } catch (e) { console.warn('[3d] init:', e); return }
    }
    _draw(echarts)
  }).catch((e) => console.warn('[3d] load skipped:', e?.message))
}

function _draw(echarts) {
  const pts = curve.value.map((c, gi) => ({ value: [gi, 0, c.fitness] }))
  if (!pts.length) { if (glChart) glChart.clear(); return }
  glChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {},
    visualMap: { show: false, dimension: 2, inRange: { color: ['#1a2b3c', '#4fc3f7', '#69f0ae'] } },
    xAxis3D: { type: 'value', name: 'gen', axisLabel: { color: 'rgba(255,255,255,0.3)' } },
    yAxis3D: { type: 'value', name: 'pop', axisLabel: { color: 'rgba(255,255,255,0.3)' } },
    zAxis3D: { type: 'value', name: 'fit', axisLabel: { color: 'rgba(255,255,255,0.3)' } },
    grid3D: {
      boxWidth: 120, boxDepth: 60, boxHeight: 80,
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      axisPointer: { show: false },
      viewControl: { autoRotate: true, autoRotateSpeed: 6, distance: 200 },
      light: { main: { intensity: 1.2 }, ambient: { intensity: 0.4 } },
    },
    series: [{ type: 'scatter3D', data: pts, symbolSize: 7, itemStyle: { opacity: 0.9 } }],
  })
}

function applyPreset(name) {
  const p = presets.find((x) => x.name === name)
  if (!p) return
  preset.value = name
  form.value = { generations: p.generations, population_size: p.population_size, mutation_rate: p.mutation_rate, crossover_rate: p.crossover_rate, tournament_size: p.tournament_size }
}

function paramsText(params) {
  if (!params) return '—'
  return Object.entries(params).map(([k, v]) => `${k}=${v}`).join('  ')
}

async function start() {
  running.value = true
  try {
    const { data } = await api.evolutionStart(form.value)
    runningTaskId.value = data.task_id
    socket.clearEvolution()
    message.success(`进化任务已提交: #${data.task_id}`)
    await loadCurve()
    await nextTick(); render3d()
  } catch (e) { message.error(`启动失败: ${e.message}`); running.value = false }
}
async function pause() {
  if (!runningTaskId.value) return
  await api.evolutionPause(runningTaskId.value)
  message.info('已请求暂停')
  running.value = false
  runningTaskId.value = null
}
async function loadCurve() { try { const { data } = await api.evolutionCurve(); curve.value = data.curve || [] } catch {} }
async function loadPopulation() { try { const { data } = await api.evolutionPopulation(); population.value = data.population || [] } catch {} }
const treeNodes = ref([])
async function fetchTree() { try { const { data } = await api.get('/evolution/tree'); treeNodes.value = data.tree || [] } catch {} }
const convergence = ref(null)
async function loadConvergence() { try { const { data } = await api.evolutionConvergence(); convergence.value = data } catch {} }
const experiments = ref([])
const expA = ref(null)
const expB = ref(null)
const expCompare = ref(null)
const expOptions = computed(() => experiments.value.map((e) => ({ label: `${e.experiment_id} · best ${Number(e.best_fitness).toFixed(3)}`, value: e.experiment_id })))
async function loadExperiments() { try { const { data } = await api.experiments(); experiments.value = data.experiments || [] } catch {} }
async function compareExps() { try { const { data } = await api.experimentsCompare({ a: expA.value, b: expB.value }); expCompare.value = data } catch {} }
const treeOption = computed(() => ({
  tooltip: { trigger: 'item', triggerOn: 'mousemove' },
  series: [{
    type: 'tree', data: treeNodes.value, top: '8%', left: '8%', bottom: '8%', right: '20%',
    symbolSize: 7, orient: 'LR', expandAndCollapse: true,
    label: { position: 'left', verticalAlign: 'middle', align: 'right', fontSize: 9, color: '#aab2c8' },
    leaves: { label: { position: 'right', verticalAlign: 'middle', align: 'left' } },
    emphasis: { focus: 'descendant' },
    animationDuration: 400, animationDurationUpdate: 750,
  }],
}))
async function loadTasks() { try { const { data } = await api.tasks(); evoTasks.value = (data.background || []).filter((t) => t.kind === 'evolution').slice(0, 6) } catch {} }

function taskChip(s) { return { done: 'green', running: 'blue', failed: 'red', cancelled: 'dim' }[s] || 'dim' }

onMounted(() => {
  Promise.all([loadCurve(), loadPopulation(), loadTasks(), fetchTree(), loadConvergence(), loadExperiments()]).then(() => { render3d() })
  socket.on('evolution.generation', async () => { await loadCurve(); render3d(); await loadPopulation(); await loadTasks(); await fetchTree() })
  socket.on('task.update', loadTasks)
  // 入场动画：仅位移不透明度（fromTo 确保结束态 opacity=1，避免黑屏）
  gsap.fromTo(root.value, { y: 16 }, { y: 0, duration: 0.5, ease: 'power2.out' })
})
onBeforeUnmount(() => { if (glChart) { glChart.dispose(); glChart = null } })
</script>

<style scoped lang="scss">
.evo-conv-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
.evo-conv-item { background: var(--surface2); border-radius: 4px; padding: 0.55rem 0.7rem; display: flex; flex-direction: column; gap: 0.2rem; }
.evo-conv-label { font-size: 0.6rem; color: var(--faint); letter-spacing: 0.08em; }
.evo-conv-val { font-size: 1rem; color: var(--dim); font-weight: 600; }
.evo-exp { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
.evo-compare-result { font-size: 0.72rem; padding: 0.25rem 0.6rem; border-radius: 3px; }
.evo-compare-result.win { background: rgba(105,240,174,0.1); color: var(--green); }
.evo-compare-result.lose { background: rgba(239,83,80,0.1); color: #ef5350; }

.ev { display: flex; flex-direction: column; gap: 1.2rem; }

.wb-spacer { flex: 1; }

.ev-status {
  display: inline-flex; align-items: center; gap: 0.5rem;
  font-size: 0.72rem; letter-spacing: 0.1em;
  &.running { color: var(--accent); }
  &.idle { color: var(--faint); }
}
.ev-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--faint);
}
.ev-status.running .ev-status-dot {
  background: var(--accent); box-shadow: 0 0 10px var(--accent);
  animation: evPulse 1.4s infinite;
}
@keyframes evPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.ev-config { display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap; }
.ev-field { display: flex; flex-direction: column; gap: 0.35rem; }

.ev-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }

/* 最佳个体 */
.ev-best { display: flex; gap: 1.2rem; flex-wrap: wrap; }
.ev-best-params { display: flex; flex-wrap: wrap; gap: 0.5rem; flex: 1; min-width: 240px; }
.ev-best-param {
  padding: 0.4rem 0.6rem; border-radius: 6px;
  background: rgba(105, 240, 174, 0.05); border: 0.5px solid rgba(105, 240, 174, 0.2);
  display: flex; flex-direction: column; gap: 0.1rem;
}
.ev-best-key { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.06em; }
.ev-best-val { font-size: 0.8rem; color: var(--green); font-weight: 600; }
.ev-best-side { display: flex; flex-direction: column; gap: 0.3rem; }
.ev-best-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.1em; text-transform: uppercase; }

/* 任务 */
.ev-tasks { display: flex; flex-direction: column; gap: 0.7rem; }
.ev-task {
  padding: 0.75rem 0.9rem 0.75rem 1rem;
  border-radius: 8px; border: 0.5px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  display: flex; flex-direction: column; gap: 0.3rem;
  &.running { border-color: rgba(79, 195, 247, 0.35); background: rgba(79, 195, 247, 0.04); }
  &.failed { border-color: rgba(239, 83, 80, 0.3); }
}
.ev-task-top { display: flex; align-items: center; gap: 0.5rem; }
.ev-task-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--faint);
  &.running { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: evPulse 1.4s infinite; }
  &.done { background: var(--green); }
  &.failed { background: var(--red); }
}
.ev-task-name { font-size: 0.74rem; font-weight: 500; }
.ev-task-id { font-size: 0.58rem; color: var(--faint); font-family: var(--mono); }
.ev-task-msg { font-size: 0.62rem; color: var(--faint); }

@media (max-width: 1000px) {
  .ev-grid { grid-template-columns: 1fr; }
}
</style>
