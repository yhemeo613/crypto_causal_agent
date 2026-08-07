<template>
  <div class="dl" ref="root">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">决策实验室 <span>DECISION LAB</span></div>
        <div class="page-sub">手动执行一轮完整决策 · 辩论回放 · 反事实推演（真实 DeepSeek LLM）</div>
      </div>
      <n-button type="primary" :loading="running" @click="run">
        <template #icon><Icon icon="mdi:brain" :width="15" /></template>
        {{ running ? '决策执行中…' : '执行完整决策' }}
      </n-button>
    </div>

    <n-alert v-if="running" type="info" style="margin-bottom:0">
      真实调用 LLM 辩论链（感知 → 记忆 → 多空辩论 → 证伪 → 反事实 → 决策），约 10-30 秒
    </n-alert>

    <!-- 结果 -->
    <template v-if="result">
      <!-- 决策结果条 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:check-decagram-outline" :width="17" /></span>
            <span>决策结果</span>
            <span class="wb-sec-sub">CYCLE #{{ result.cycle_id }}</span>
          </div>
        </div>
        <div class="dl-result">
          <div class="dl-action-col">
            <span class="dl-action-label">方向</span>
            <span class="dl-action" :class="decision.action">{{ decision.action }}</span>
          </div>
          <div class="wb-sep"></div>
          <div class="wb-stat">
            <span class="wb-stat-label">置信度</span>
            <span class="wb-stat-val" style="font-size:1.5rem">{{ (decision.confidence * 100).toFixed(0) }}%</span>
          </div>
          <div class="wb-sep"></div>
          <div class="wb-stat">
            <span class="wb-stat-label">仓位</span>
            <span class="wb-stat-val" style="font-size:1.5rem">{{ (decision.position_size_pct * 100).toFixed(0) }}%</span>
          </div>
          <div class="wb-sep"></div>
          <div class="wb-stat">
            <span class="wb-stat-label">杠杆</span>
            <span class="wb-stat-val" style="font-size:1.5rem">{{ decision.leverage }}x</span>
          </div>
          <div class="wb-spacer" style="flex:1"></div>
          <span class="wb-chip" :class="decision.action === 'long' ? 'green' : decision.action === 'short' ? 'red' : 'dim'">
            {{ decision.action === 'long' ? '做多' : decision.action === 'short' ? '做空' : '观望' }}
          </span>
        </div>
        <div class="dl-reason">
          <span class="dl-reason-label">推理链</span>
          <code class="block" style="max-height:200px">{{ decision.reasoning }}</code>
        </div>
        <div class="dl-meta-row">
          <span v-if="decision.regime_mode" class="wb-chip amber">Regime：{{ decision.regime_mode }}</span>
          <span class="wb-chip dim">辩论：并行 ⚡（P2-02）</span>
          <span v-if="result.causal_triplets" class="wb-chip dim">因果图谱 +{{ result.causal_triplets.length }}</span>
        </div>
      </div>

      <!-- 辩论 + 证伪/反事实 -->
      <div class="dl-bottom">
        <div class="wb-card">
          <div class="wb-sec-head">
            <div class="wb-sec-title">
              <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:scale-balance" :width="17" /></span>
              <span>多空辩论</span>
              <span class="wb-sec-sub">LLM ARGUMENTS</span>
            </div>
          </div>
          <div class="dl-debate">
            <div class="dl-side">
              <div class="dl-side-head bull">
                <Icon icon="mdi:trending-up" :width="15" /> Bull ({{ bull.arguments?.length || 0 }})
              </div>
              <div v-for="(a, i) in bull.arguments || []" :key="i" class="dl-arg bull">
                <span class="dl-arg-idx">{{ i + 1 }}</span>
                <span>{{ a }}</span>
              </div>
            </div>
            <div class="dl-side">
              <div class="dl-side-head bear">
                <Icon icon="mdi:trending-down" :width="15" /> Bear ({{ bear.arguments?.length || 0 }})
              </div>
              <div v-for="(a, i) in bear.arguments || []" :key="'b' + i" class="dl-arg bear">
                <span class="dl-arg-idx">{{ i + 1 }}</span>
                <span>{{ a }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="wb-card">
          <div class="wb-sec-head">
            <div class="wb-sec-title">
              <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:shield-alert-outline" :width="17" /></span>
              <span>证伪 & 反事实</span>
              <span class="wb-sec-sub">FALSIFY · CF</span>
            </div>
          </div>
          <div class="dl-falsify">
            <div class="data-row">
              <span class="data-key">是否证伪</span>
              <span class="data-val"><span class="wb-chip" :class="fals.is_falsified ? 'red' : 'green'">{{ fals.is_falsified ? '是' : '否' }}</span></span>
            </div>
            <div class="data-row">
              <span class="data-key">调整后置信度</span>
              <span class="data-val mono" style="font-size:0.9rem">{{ (fals.confidence_adjusted * 100).toFixed(0) }}%</span>
            </div>
          </div>
          <div class="dl-reason">
            <span class="dl-reason-label">证伪推理</span>
            <code class="block" style="max-height:130px">{{ fals.reasoning }}</code>
          </div>
          <div class="wb-sep" style="margin:0.8rem 0"></div>
          <div class="dl-cf" v-if="(cf.paths || []).length">
            <div class="dl-cf-row head">
              <span>情景</span><span>概率</span><span>预期收益</span><span>预期风险</span>
            </div>
            <div v-for="(p, i) in cf.paths" :key="i" class="dl-cf-row">
              <span class="dl-cf-scenario">{{ p.scenario }}</span>
              <span class="mono">{{ (p.probability * 100).toFixed(0) }}%</span>
              <span class="mono up">{{ (p.expected_return * 100).toFixed(1) }}%</span>
              <span class="mono down">{{ (p.expected_risk * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 最近决策流（决策回放） -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(129,199,132,0.1);color:#81c784"><Icon icon="mdi:history" :width="17" /></span>
          <span>最近决策流</span>
          <span class="wb-sec-sub">DECISION LOG</span>
        </div>
        <span class="wb-chip dim">{{ recentDecisions.length }} 条</span>
      </div>
      <div v-if="recentDecisions.length" class="dl-timeline">
        <div v-for="d in recentDecisions.slice(0, 8)" :key="d.cycle_id" class="dl-tl-item">
          <span class="dl-tl-dot" :class="d.action"></span>
          <span class="dl-tl-cycle">#{{ d.cycle_id }}</span>
          <span class="dl-tl-action" :class="d.action">{{ d.action }}</span>
          <span class="dl-tl-conf">{{ (d.confidence * 100).toFixed(0) }}%</span>
          <span class="dl-tl-size">{{ (d.position_size * 100).toFixed(0) }}%</span>
          <span class="dl-tl-ts mono">{{ shortTs(d.ts) }}</span>
        </div>
      </div>
      <div v-else class="wb-empty">暂无决策记录</div>
    </div>

    <div v-if="!result" class="wb-empty" style="padding:2rem 0">
      <Icon icon="mdi:brain" :width="30" style="opacity:0.5" />
      <p>点击「执行完整决策」运行一轮真实全闭环</p>
      <span>感知 → 记忆 → 多空辩论 → 证伪 → 反事实 → 决策</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useMessage } from 'naive-ui'
import api from '../api'
import gsap from 'gsap'
import { useAgentStore } from '../stores/agent'

const message = useMessage()
const root = ref(null)
const result = ref(null)
const running = ref(false)

const decision = computed(() => result.value?.decision || {})
const bull = computed(() => result.value?.bull_debate || {})
const bear = computed(() => result.value?.bear_debate || {})
const fals = computed(() => result.value?.falsification || {})
const cf = computed(() => result.value?.counterfactual || {})
const recentDecisions = computed(() => {
  try { return useAgentStore().recentDecisions || [] } catch { return [] }
})
const shortTs = (ts) => (ts ? String(ts).replace('T', ' ').slice(5, 16) : '')

async function run() {
  running.value = true
  try {
    const { data } = await api.decisionRun({ symbol: 'BTCUSDT' })
    if (data.error) message.error(`决策失败: ${data.error}`)
    else {
      result.value = data
      message.success(`决策完成: ${data.decision?.action} conf=${data.decision?.confidence?.toFixed(2)}`)
      await nextTick()
      gsap.from('.wb-card', { y: 24, opacity: 0, duration: 0.5, stagger: 0.1, ease: 'power3.out' })
    }
  } catch (e) { message.error(`决策失败: ${e.message}`) }
  finally { running.value = false }
}
</script>

<style scoped lang="scss">
.dl { display: flex; flex-direction: column; gap: 1.2rem; }

.wb-spacer { flex: 1; }

/* 决策结果 */
.dl-result { display: flex; align-items: center; gap: 1.4rem; flex-wrap: wrap; }
.dl-action-col { display: flex; flex-direction: column; gap: 0.2rem; }
.dl-action-label { font-size: 0.56rem; color: var(--faint); letter-spacing: 0.12em; text-transform: uppercase; }
.dl-action {
  font-size: 2.2rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
  &.long { color: var(--green); }
  &.short { color: var(--red); }
  &.hold { color: var(--dim); }
}

.dl-reason { margin-top: 0.9rem; }
.dl-meta-row { display: flex; gap: 0.5rem; margin-top: 0.8rem; flex-wrap: wrap; }
.dl-timeline { display: flex; flex-direction: column; gap: 0.35rem; }
.dl-tl-item { display: flex; align-items: center; gap: 0.6rem; padding: 0.35rem 0.5rem; border-radius: 3px; background: var(--surface2); font-size: 0.7rem; }
.dl-tl-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); flex-shrink: 0; }
.dl-tl-dot.long { background: #69f0ae; }
.dl-tl-dot.short { background: #ef5350; }
.dl-tl-dot.hold { background: #ffd54f; }
.dl-tl-cycle { color: var(--faint); font-family: var(--mono); }
.dl-tl-action { font-weight: 600; text-transform: uppercase; width: 48px; }
.dl-tl-action.long { color: #69f0ae; }
.dl-tl-action.short { color: #ef5350; }
.dl-tl-action.hold { color: #ffd54f; }
.dl-tl-conf, .dl-tl-size { color: var(--dim); font-family: var(--mono); }
.dl-tl-ts { color: var(--faint); margin-left: auto; }
.dl-reason-label { font-size: 0.62rem; color: var(--faint); letter-spacing: 0.1em; margin-bottom: 0.4rem; display: block; }

/* 辩论 */
.dl-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
.dl-debate { display: flex; flex-direction: column; gap: 0.8rem; }
.dl-side-head {
  display: flex; align-items: center; gap: 0.4rem;
  font-size: 0.72rem; font-weight: 600; margin-bottom: 0.5rem;
  &.bull { color: var(--green); }
  &.bear { color: var(--red); }
}
.dl-arg {
  display: flex; gap: 0.5rem; align-items: flex-start;
  padding: 0.5rem 0.6rem; border-radius: 6px; margin-bottom: 0.4rem;
  font-size: 0.7rem; line-height: 1.55;
  background: rgba(255, 255, 255, 0.02); border: 0.5px solid var(--border);
  &.bull { border-left: 2px solid var(--green); }
  &.bear { border-left: 2px solid var(--red); }
}
.dl-arg-idx {
  flex: 0 0 18px; height: 18px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.6rem; font-weight: 700;
  background: rgba(255, 255, 255, 0.06); color: var(--dim);
}

/* 证伪 */
.dl-falsify { display: flex; flex-direction: column; }
.dl-cf-row {
  display: grid; grid-template-columns: 1.4fr 0.6fr 0.8fr 0.8fr; gap: 0.5rem;
  padding: 0.45rem 0.4rem; border-bottom: 0.5px solid var(--border);
  font-size: 0.7rem;
  &.head { color: var(--faint); font-size: 0.6rem; letter-spacing: 0.08em; text-transform: uppercase; }
}
.dl-cf-scenario { color: var(--text); }
.up { color: var(--green); }
.down { color: var(--red); }

@media (max-width: 1000px) {
  .dl-bottom { grid-template-columns: 1fr; }
}
</style>
