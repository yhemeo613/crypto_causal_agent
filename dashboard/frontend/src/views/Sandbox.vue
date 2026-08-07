<template>
  <div class="sb">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">回测沙箱 <span>SANDBOX</span></div>
        <div class="page-sub">四环境真实数据回测 · 策略基因绩效</div>
      </div>
    </div>

    <!-- 配置条 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:flask-outline" :width="17" /></span>
          <span>回测配置</span>
          <span class="wb-sec-sub">BACKTEST CONFIG</span>
        </div>
      </div>
      <div class="sb-config">
        <div class="sb-field">
          <label class="wb-bar-label">环境</label>
          <n-select v-model:value="form.env" :options="envOptions" size="small" style="width:130px" />
        </div>
        <div class="sb-field">
          <label class="wb-bar-label">周期</label>
          <n-select v-model:value="form.interval" :options="intervalOptions" size="small" style="width:90px" />
        </div>
        <div class="sb-field">
          <label class="wb-bar-label">MA 短窗</label>
          <n-input-number v-model:value="form.params.ma_short_window" size="small" style="width:80px" :min="2" />
        </div>
        <div class="sb-field">
          <label class="wb-bar-label">MA 长窗</label>
          <n-input-number v-model:value="form.params.ma_long_window" size="small" style="width:80px" :min="5" />
        </div>
        <div class="sb-field">
          <label class="wb-bar-label">量比阈值</label>
          <n-input-number v-model:value="form.params.vol_threshold" size="small" style="width:80px" :min="0" :step="0.1" />
        </div>
        <div class="sb-field" style="margin-left:auto">
          <n-button type="primary" :loading="running" @click="run">
            <template #icon><Icon icon="mdi:play" :width="15" /></template>运行回测
          </n-button>
        </div>
      </div>
    </div>

    <!-- 结果 -->
    <template v-if="result">
      <!-- 绩效条 -->
      <div class="wb-bar">
        <div class="wb-stat">
          <span class="wb-stat-label">区间涨跌</span>
          <span class="wb-stat-val" :class="perfClass(result.summary.pct_change)">{{ result.summary.pct_change }}%</span>
        </div>
        <span class="wb-sep"></span>
        <div class="wb-stat">
          <span class="wb-stat-label">最大回撤</span>
          <span class="wb-stat-val down">{{ result.summary.max_drawdown_pct }}%</span>
        </div>
        <span class="wb-sep"></span>
        <div class="wb-stat">
          <span class="wb-stat-label">年化波动</span>
          <span class="wb-stat-val">{{ result.summary.volatility_annualized }}%</span>
        </div>
        <span class="wb-sep"></span>
        <div class="wb-stat">
          <span class="wb-stat-label">策略收益</span>
          <span class="wb-stat-val" :class="perfClass(strategyPct)">{{ strategyPctText }}</span>
        </div>
        <span class="wb-spacer" style="flex:1"></span>
        <span class="wb-chip" :class="envChipClass">{{ result.summary.regime }}</span>
      </div>

      <!-- 环境摘要 + 说明 -->
      <div class="sb-bottom">
        <div class="wb-card">
          <div class="wb-sec-head">
            <div class="wb-sec-title">
              <span class="wb-sec-icon"><Icon icon="mdi:chart-timeline-variant" :width="17" /></span>
              <span>环境摘要</span>
              <span class="wb-sec-sub">{{ result.summary.name }}</span>
            </div>
          </div>
          <div class="sb-summary">
            <div class="data-row"><span class="data-key">K 线数</span><span class="data-val mono">{{ result.summary.bars }}</span></div>
            <div class="data-row"><span class="data-key">区间</span><span class="data-val mono dim">{{ result.summary.date_start?.slice(0, 10) }} → {{ result.summary.date_end?.slice(0, 10) }}</span></div>
            <div class="data-row"><span class="data-key">起始价格</span><span class="data-val mono">{{ fmt(result.summary.price_start) }}</span></div>
            <div class="data-row"><span class="data-key">结束价格</span><span class="data-val mono">{{ fmt(result.summary.price_end) }}</span></div>
            <div class="data-row"><span class="data-key">最高 / 最低</span><span class="data-val mono">{{ fmt(result.summary.max_price) }} / {{ fmt(result.summary.min_price) }}</span></div>
          </div>
        </div>

        <div class="wb-card">
          <div class="wb-sec-head">
            <div class="wb-sec-title">
              <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:lightbulb-on-outline" :width="17" /></span>
              <span>说明</span>
              <span class="wb-sec-sub">NOTES</span>
            </div>
          </div>
          <div class="sb-notes">
            <p><Icon icon="mdi:check-circle-outline" :width="13" style="vertical-align:-2px" /> 数据来自本地真实 K 线（data/raw → TimescaleDB）</p>
            <p><Icon icon="mdi:check-circle-outline" :width="13" style="vertical-align:-2px" /> 策略：MA 交叉信号 → 方向持仓 → 逐 bar 收益（扣 0.04% 手续费）</p>
            <p><Icon icon="mdi:information-outline" :width="13" style="vertical-align:-2px" /> 负收益基因在进化引擎中按设计归零（max(fitness, 0)）</p>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="wb-empty" style="padding:4rem 0">
      <Icon icon="mdi:flask-outline" :width="30" style="opacity:0.5" />
      <p>配置参数后点击「运行回测」</p>
      <span>支持 bull / bear / range / extreme 四环境真实数据回测</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useMessage } from 'naive-ui'
import api from '../api'

const message = useMessage()
const form = ref({ env: 'bull', interval: '1h', params: { ma_short_window: 20, ma_long_window: 60, vol_threshold: 1.0 } })
const result = ref(null)
const running = ref(false)

const envOptions = ['bull', 'bear', 'range', 'extreme'].map((v) => ({ label: v, value: v }))
const intervalOptions = ['1h', '4h', '1d'].map((v) => ({ label: v, value: v }))

const strategyPct = computed(() => {
  const p = result.value?.performance
  return p ? p[form.value.env] ?? null : null
})
const strategyPctText = computed(() => (strategyPct.value === null ? '未评估' : `${(strategyPct.value * 100).toFixed(2)}%`))
const envChipClass = computed(() => ({ trend_up: 'green', trend_down: 'red', range: 'amber' }[result.value?.summary?.regime] || 'dim'))
const perfClass = (v) => (v != null && v >= 0 ? 'up' : 'down')

async function run() {
  running.value = true
  try {
    const { data } = await api.backtestRun({ env: form.value.env, interval: form.value.interval, params: form.value.params })
    if (data.error) message.error(`回测失败: ${data.error}`)
    else result.value = data
  } catch (e) { message.error(`回测失败: ${e.message}`) } finally { running.value = false }
}
const fmt = (n) => (n == null ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }))
</script>

<style scoped lang="scss">
.sb { display: flex; flex-direction: column; gap: 1.2rem; }

.sb-config { display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap; }
.sb-field { display: flex; flex-direction: column; gap: 0.35rem; }

.sb-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
.sb-summary { display: flex; flex-direction: column; }

.sb-notes {
  display: flex; flex-direction: column; gap: 0.6rem;
  p { font-size: 0.72rem; color: var(--dim); display: flex; gap: 0.4rem; align-items: flex-start; line-height: 1.6; }
}

.wb-spacer { flex: 1; }

@media (max-width: 1000px) {
  .sb-bottom { grid-template-columns: 1fr; }
}
</style>
