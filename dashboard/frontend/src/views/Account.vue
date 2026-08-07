<template>
  <div class="acc">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">账户风控 <span>ACCOUNT</span></div>
        <div class="page-sub">账户快照 · 交易记录 · 风控规则</div>
      </div>
      <n-button secondary size="small" @click="loadAll">
        <template #icon><Icon icon="mdi:refresh" :width="14" /></template>刷新
      </n-button>
    </div>

    <!-- 账户概览条 -->
    <div class="wb-bar" v-if="account">
      <div class="wb-stat">
        <span class="wb-stat-label">初始资金</span>
        <span class="wb-stat-val">{{ fmt(account.initial_balance) }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">当前权益</span>
        <span class="wb-stat-val" :class="account.equity >= account.initial_balance ? 'up' : 'down'">{{ fmt(account.equity) }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">回撤</span>
        <span class="wb-stat-val down">{{ pct(account.drawdown_pct) }}</span>
      </div>
      <span class="wb-sep"></span>
      <div class="wb-stat">
        <span class="wb-stat-label">交易 / 决策</span>
        <span class="wb-stat-val">{{ account.total_trades }} / {{ account.total_decisions }}</span>
      </div>
      <span class="wb-spacer" style="flex:1"></span>
      <span class="wb-chip green"><Icon icon="mdi:shield-check-outline" :width="13" />风控启用</span>
    </div>

    <!-- 交易记录 + 风控规则 -->
    <div class="acc-bottom">
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(79,195,247,0.12);color:#4fc3f7"><Icon icon="mdi:chart-line" :width="17" /></span>
            <span>账户权益曲线</span>
            <span class="wb-sec-sub">EQUITY · REPLAY SNAPSHOTS</span>
          </div>
          <n-button size="tiny" quaternary @click="loadHistory()">刷新</n-button>
        </div>
        <v-chart v-if="equityHistory.length" :option="equityOption" autoresize style="height:220px" />
        <div v-else class="wb-empty">暂无权益快照（决策周期运行后产生）</div>
      </div>

      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:swap-horizontal-bold" :width="17" /></span>
            <span>交易记录</span>
            <span class="wb-sec-sub">TRADES · {{ account?.trades?.length || 0 }}</span>
          </div>
        </div>
        <n-table v-if="account?.trades?.length" size="small" :bordered="false" :single-line="false">
          <thead>
            <tr><th>方向</th><th>盈亏</th><th>收益率</th><th>时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="(t, i) in account.trades.slice(0, 20)" :key="i">
              <td><n-tag size="tiny" :type="t.side === 'long' ? 'success' : 'error'" :bordered="false" round>{{ t.side }}</n-tag></td>
              <td class="mono" :class="(t.pnl || 0) >= 0 ? 'up' : 'down'">{{ t.pnl?.toFixed(2) }}</td>
              <td class="mono" :class="(t.pnl_pct || 0) >= 0 ? 'up' : 'down'">{{ ((t.pnl_pct || 0) * 100).toFixed(2) }}%</td>
              <td class="dim" style="font-size:0.66rem">{{ shortTs(t.entry_ts) }}</td>
            </tr>
          </tbody>
        </n-table>
        <div v-else class="wb-empty">
          <Icon icon="mdi:swap-horizontal" :width="26" style="opacity:0.5" />
          <p>暂无交易记录</p>
          <span>回测 / 进化运行后将产生逐笔交易</span>
        </div>
      </div>

      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:shield-lock-outline" :width="17" /></span>
            <span>硬风控规则</span>
            <span class="wb-sec-sub">RISK CONTROL</span>
          </div>
          <n-button size="tiny" quaternary type="primary" @click="$router.push('/settings')">前往设置</n-button>
        </div>
        <div class="acc-rules" v-if="riskRules.length">
          <div v-for="r in riskRules" :key="r[0]" class="acc-rule">
            <span class="acc-rule-key">{{ r[0] }}</span>
            <span class="wb-spacer" style="flex:1"></span>
            <span class="acc-rule-val mono">{{ fmtRule(r[1]) }}</span>
          </div>
        </div>
        <div v-else class="wb-empty">
          <Icon icon="mdi:shield-off-outline" :width="26" style="opacity:0.5" />
          <p>规则加载中…</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import api from '../api'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const account = ref(null)
const riskRules = ref([])
const equityHistory = ref([])
const equityOption = computed(() => ({
  backgroundColor: 'transparent',
  grid: { left: 52, right: 16, top: 20, bottom: 28 },
  tooltip: { trigger: 'axis', backgroundColor: '#1a1f2c', borderColor: 'rgba(255,255,255,0.08)', textStyle: { color: '#aab2c8', fontSize: 11 } },
  xAxis: { type: 'category', data: equityHistory.value.map((h) => h.ts), axisLabel: { color: '#5a6275', fontSize: 10 } },
  yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }, axisLabel: { color: '#5a6275', fontSize: 10 } },
  series: [{
    type: 'line', data: equityHistory.value.map((h) => h.balance), smooth: true, symbol: 'circle', symbolSize: 5,
    lineStyle: { color: '#4fc3f7', width: 2 }, itemStyle: { color: '#4fc3f7' },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(79,195,247,0.25)' }, { offset: 1, color: 'rgba(79,195,247,0)' }] } },
  }],
}))
async function loadHistory() { try { const { data } = await api.accountHistory(); equityHistory.value = data.history || [] } catch {} }

const fmt = (n) => (n == null ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }))
const pct = (n) => (n == null ? '-' : `${(n * 100).toFixed(2)}%`)
const shortTs = (ts) => (ts ? String(ts).slice(0, 16) : '')
const fmtRule = (v) => (typeof v === 'number' && v < 1 && v > 0 ? `${(v * 100).toFixed(0)}%` : v)

async function loadAll() {
  try { const { data } = await api.account(); account.value = data } catch {}
  try { await loadHistory() } catch {}
  try {
    const { data } = await api.config()
    riskRules.value = Object.entries(data.risk_control || {})
  } catch {}
}
onMounted(loadAll)
</script>

<style scoped lang="scss">
.acc { display: flex; flex-direction: column; gap: 1.2rem; }

.wb-spacer { flex: 1; }
.up { color: var(--green); }
.down { color: var(--red); }

.acc-bottom { display: grid; grid-template-columns: 1.3fr 1fr; gap: 1.2rem; }

.acc-rules { display: flex; flex-direction: column; }
.acc-rule {
  display: flex; align-items: center; gap: 0.8rem;
  padding: 0.55rem 0; border-bottom: 0.5px solid var(--border);
  &:last-child { border-bottom: none; }
}
.acc-rule-key { font-size: 0.74rem; color: var(--dim); }
.acc-rule-val { font-size: 0.78rem; color: var(--text); }

@media (max-width: 1000px) {
  .acc-bottom { grid-template-columns: 1fr; }
}
</style>
