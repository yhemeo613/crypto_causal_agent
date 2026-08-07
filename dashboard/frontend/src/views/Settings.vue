<template>
  <div class="st">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">设置 <span>SETTINGS</span></div>
        <div class="page-sub">配置查看 · 密钥管理 · 系统信息</div>
      </div>
    </div>

    <!-- 关键配置 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon"><Icon icon="mdi:tune-variant" :width="17" /></span>
          <span>关键配置</span>
          <span class="wb-sec-sub">CONFIG.YAML</span>
        </div>
      </div>
      <div class="st-grid" v-if="cfg">
        <div class="st-group">
          <div class="st-group-title">
            <Icon icon="mdi:robot-outline" :width="14" style="vertical-align:-2px" /> LLM <span class="st-provider" :class="'p-' + (cfg.llm?.provider || 'deepseek')">{{ cfg.llm?.provider || 'deepseek' }}</span>
          </div>
          <div class="data-row" v-for="(v, k) in cfg.llm || {}" :key="'llm' + k">
            <span class="data-key">{{ k }}</span>
            <span class="data-val mono dim">{{ maskKey(k, v) }}</span>
          </div>
          <div class="st-provider-tip">
            <Icon icon="mdi:information-outline" :width="13" style="vertical-align:-2px" />
            切换 provider：在 config.yaml 的 llm 段改 provider/model（deepseek/openai/claude），改后重启后端生效
          </div>
        </div>
        <div class="st-group">
          <div class="st-group-title">
            <Icon icon="mdi:shield-lock-outline" :width="14" style="vertical-align:-2px" /> 风控
          </div>
          <div class="data-row" v-for="(v, k) in cfg.risk_control || {}" :key="'rc' + k">
            <span class="data-key">{{ k }}</span>
            <span class="data-val mono">{{ fmtCfg(v) }}</span>
          </div>
        </div>
        <div class="st-group">
          <div class="st-group-title">
            <Icon icon="mdi:dna" :width="14" style="vertical-align:-2px" /> 进化
          </div>
          <div class="data-row" v-for="(v, k) in cfg.evolution || {}" :key="'ev' + k">
            <span class="data-key">{{ k }}</span>
            <span class="data-val mono">{{ v }}</span>
          </div>
        </div>
        <div class="st-group">
          <div class="st-group-title">
            <Icon icon="mdi:eye-outline" :width="14" style="vertical-align:-2px" /> 感知 / 沙箱
          </div>
          <div class="data-row">
            <span class="data-key">因果方法</span>
            <span class="data-val mono">{{ (cfg.perception?.causal_extraction?.statistical_methods || []).join(', ') }}</span>
          </div>
          <div class="data-row">
            <span class="data-key">沙箱环境</span>
            <span class="data-val mono">{{ Object.keys(cfg.sandbox?.environments || {}).join(', ') }}</span>
          </div>
        </div>
      </div>
      <div v-else class="wb-empty">
        <Icon icon="mdi:cog-refresh-outline" :width="26" style="opacity:0.5" />
        <p>配置加载中…</p>
      </div>
    </div>

    <!-- 密钥 + 系统 -->
    <div class="st-bottom">
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:key-outline" :width="17" /></span>
            <span>密钥状态</span>
            <span class="wb-sec-sub">API KEYS</span>
          </div>
        </div>
        <div class="data-row">
          <span class="data-key">DeepSeek API</span>
          <span class="data-val"><span class="wb-chip" :class="hasDeepseek ? 'green' : 'red'">{{ hasDeepseek ? '已配置' : '未配置' }}</span></span>
        </div>
        <div class="data-row">
          <span class="data-key">FRED API</span>
          <span class="data-val"><span class="wb-chip" :class="hasFred ? 'green' : 'red'">{{ hasFred ? '已配置' : '未配置' }}</span></span>
        </div>
        <div class="data-row">
          <span class="data-key">Glassnode API <span class="st-note">收费·可选</span></span>
          <span class="data-val"><span class="wb-chip" :class="hasGlass ? 'green' : 'dim'">{{ hasGlass ? '已配置（链上指标）' : '未配置 → 免费替代已启用' }}</span></span>
        </div>
        <div class="data-row">
          <span class="data-key">Fear&amp;Greed 情绪 <span class="st-note">免费</span></span>
          <span class="data-val"><span class="wb-chip green">已内置（无需 Key）</span></span>
        </div>
      </div>

      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:server-outline" :width="17" /></span>
            <span>系统信息</span>
            <span class="wb-sec-sub">SYSTEM</span>
          </div>
        </div>
        <div class="data-row"><span class="data-key">后端 API</span><span class="data-val mono">FastAPI :8699</span></div>
        <div class="data-row"><span class="data-key">前端</span><span class="data-val mono">Vite :8700</span></div>
        <div class="data-row">
          <span class="data-key">WebSocket</span>
          <span class="data-val"><span class="wb-chip" :class="socket.connected ? 'green' : 'red'">{{ socket.connected ? '已连接' : '断开' }}</span></span>
        </div>
        <div class="data-row"><span class="data-key">数据目录</span><span class="data-val mono">data/raw/*.parquet</span></div>
        <div class="data-row"><span class="data-key">K 线入库</span><span class="data-val mono">{{ fmtNum(dbStats?.timescale?.klines) }} 条</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import api from '../api'
import { useAgentStore } from '../stores/agent'
import { useSocketStore } from '../stores/socket'

const socket = useSocketStore()
const agent = useAgentStore()
const cfg = ref(null)

const dbStats = computed(() => agent.dbStats)
const hasDeepseek = computed(() => !!cfg.value?.llm?.api_key)
const hasFred = computed(() => !!cfg.value?.data?.fred?.api_key)
const hasGlass = computed(() => !!cfg.value?.data?.glassnode?.api_key)

function maskKey(k, v) {
  if (!v) return '(空)'
  if (typeof v !== 'string') return v
  if (/key|password|token/i.test(k) && v.length > 8) return `${v.slice(0, 4)}…${v.slice(-4)}`
  return v
}
const fmtCfg = (v) => (typeof v === 'number' && v < 1 && v > 0 ? `${(v * 100).toFixed(0)}%` : v)
const fmtNum = (n) => (n == null ? 0 : Number(n)).toLocaleString()

onMounted(async () => {
  try { const { data } = await api.config(); cfg.value = data } catch {}
  agent.fetchDb()
})
</script>

<style scoped lang="scss">
.st-provider { font-size: 0.6rem; margin-left: 0.4rem; padding: 0.1rem 0.5rem; border-radius: 2px; text-transform: uppercase; letter-spacing: 0.05em; }
.st-provider.p-deepseek { background: rgba(105,240,174,0.14); color: #69f0ae; }
.st-provider.p-openai { background: rgba(79,195,247,0.14); color: #4fc3f7; }
.st-provider.p-claude { background: rgba(255,213,79,0.14); color: #ffd54f; }
.st-provider-tip { margin-top: 0.6rem; font-size: 0.62rem; color: var(--faint); display: flex; gap: 0.3rem; align-items: flex-start; line-height: 1.5; }
.st-note { font-size: 0.56rem; color: var(--faint); background: var(--surface2); padding: 0.05rem 0.35rem; border-radius: 2px; margin-left: 0.25rem; }

.st { display: flex; flex-direction: column; gap: 1.2rem; }

.st-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.2rem 2rem; }
.st-group { display: flex; flex-direction: column; }
.st-group-title {
  font-size: 0.66rem; color: var(--accent); letter-spacing: 0.15em;
  text-transform: uppercase; margin-bottom: 0.4rem;
  display: flex; align-items: center; gap: 0.35rem;
}

.st-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }

@media (max-width: 1000px) {
  .st-grid, .st-bottom { grid-template-columns: 1fr; }
}
</style>
