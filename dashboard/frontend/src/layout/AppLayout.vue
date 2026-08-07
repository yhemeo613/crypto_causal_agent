<template>
  <div class="wb">
    <!-- 侧边导航 -->
    <aside class="wb-side">
      <div class="wb-brand" @click="$router.push('/')">
        <span class="wb-dot"></span>
        <span>CRYPTO CAUSAL AGENT</span>
      </div>
      <nav class="wb-nav">
        <router-link v-for="r in routes" :key="r.path" :to="r.path" class="wb-nav-item" @click="navClick">
          <Icon class="wb-nav-icon" :icon="r.meta.icon" :width="16" />
          <span>{{ r.meta.title }}</span>
        </router-link>
      </nav>
      <div class="wb-side-foot">
        <span class="wb-ws" :class="{ on: socket.connected }">
          <Icon icon="mdi:lan-connect" :width="12" style="margin-right:4px;vertical-align:-1px" />
          {{ socket.connected ? 'WS 已连接' : 'WS 断开' }}
        </span>
      </div>
    </aside>

    <!-- 主区 -->
    <div class="wb-main">
      <header class="wb-top">
        <div class="wb-top-status">
          <span class="wb-pill" :class="agent.agentStatus">
            <span class="wb-status-dot" :class="agent.agentStatus"></span>
            {{ agentStatusText }}{{ agent.state?.uptime ? ' · ' + agent.state.uptime : '' }}
          </span>
          <span class="wb-pill dim" :class="{ 'is-running': agent.agentStatus === 'running' }">Cycle #{{ agent.state?.cycle_id ?? 0 }}</span>
          <span v-if="regimeNow" class="wb-pill" :class="'regime-' + regimeNow"><Icon icon="mdi:chart-timeline-variant" :width="12" style="vertical-align:-1px" /> {{ regimeLabel(regimeNow) }}</span>
          <span class="wb-pill dim"><Icon icon="mdi:candlestick-chart" :width="12" style="vertical-align:-1px" /> K线 {{ fmtNum(agent.state?.stats?.klines) }}</span>
          <span class="wb-pill dim"><Icon icon="mdi:brain" :width="12" style="vertical-align:-1px" /> 决策 {{ agent.state?.stats?.decisions }}</span>
          <span class="wb-pill dim"><Icon icon="mdi:swap-horizontal" :width="12" style="vertical-align:-1px" /> 交易 {{ agent.state?.stats?.trades }}</span>
          <span class="wb-pill dim"><Icon icon="mdi:dna" :width="12" style="vertical-align:-1px" /> 进化 {{ agent.state?.stats?.evolutions }}</span>
        </div>
        <div class="wb-top-actions">
          <n-button size="small"
            :type="agent.agentStatus === 'running' ? 'warning' : (agent.agentStatus === 'paused' ? 'success' : 'primary')"
            @click="agent.startPause()">
            {{ agent.agentStatus === 'running' ? '暂停' : (agent.agentStatus === 'paused' ? '恢复' : '启动') }}
          </n-button>
        </div>
      </header>

      <!-- 告警条 -->
      <div v-if="agent.alerts.length" class="wb-alerts">
        <n-alert v-for="(a, i) in agent.alerts.slice(0, 3)" :key="i" :type="a.level === 'error' ? 'error' : 'warning'" size="small" closable @close="agent.alerts.splice(i, 1)">
          <b>{{ a.title }}</b> — {{ a.detail }}
        </n-alert>
      </div>

      <main class="wb-content">
        <router-view v-slot="{ Component }">
          <transition name="wb-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentStore } from '../stores/agent'
import api from '../api'
import { useSocketStore } from '../stores/socket'
import { Icon } from '@iconify/vue'
import gsap from 'gsap'

const router = useRouter()
const agent = useAgentStore()
const socket = useSocketStore()

const routes = router.options.routes

const regimeNow = ref(null)
async function loadRegime() {
  try {
    const { data } = await api.perceptionSlices()
    regimeNow.value = data.perception?.regime || null
  } catch {}
}

const agentStatusText = computed(() => ({
  idle: '空闲', running: '运行中', paused: '已暂停',
}[agent.agentStatus] || agent.agentStatus))

const fmtNum = (n) => (n == null ? '0' : Number(n).toLocaleString())
const regimeLabel = (r) => ({
  trend_up: '趋势向上', trend_down: '趋势向下', range: '震荡市', high_vol: '高波动', unknown: '未知',
}[r] || r)

// GSAP：侧边栏入场
onMounted(() => {
  agent.startPolling(4000)
  socket.connect()
  loadRegime()
  setInterval(loadRegime, 12000)
  gsap.from('.wb-side', { x: -40, opacity: 0, duration: 0.7, ease: 'power3.out' })
  gsap.from('.wb-top', { y: -20, opacity: 0, duration: 0.5, delay: 0.15, ease: 'power2.out' })
})

// GSAP：页面切换入场（fromTo 确保结束态，防 opacity 卡 0 黑屏）
watch(
  () => router.currentRoute.value.path,
  async () => {
    await nextTick()
    gsap.fromTo('.wb-content > div', { y: 24 }, { y: 0, duration: 0.5, ease: 'power3.out' })
  }
)

function navClick() {
  gsap.fromTo('.wb-content > div', { opacity: 0.6 }, { opacity: 1, duration: 0.3 })
}

onUnmounted(() => agent.stopPolling())
</script>
