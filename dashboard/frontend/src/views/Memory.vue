<template>
  <div class="mem">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">记忆 <span>MEMORY</span></div>
        <div class="page-sub">瞬时窗口 · 向量案例 (ChromaDB) · 因果图谱 (Neo4j) 三层记忆</div>
      </div>
      <n-button secondary size="small" @click="recall">
        <template #icon><Icon icon="mdi:refresh" :width="14" /></template>刷新记忆
      </n-button>
    </div>

    <!-- 检索栏 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:file-search-outline" :width="17" /></span>
          <span>检索实验</span>
          <span class="wb-sec-sub">SEMANTIC RETRIEVAL</span>
        </div>
      </div>
      <div style="display:flex;gap:0.8rem;align-items:center;flex-wrap:wrap">
        <n-input v-model:value="query" size="medium" clearable placeholder="输入查询场景，如：trend_up up vol 1.2 pct 10%" style="flex:1;min-width:240px">
          <template #prefix><Icon icon="mdi:magnify" :width="15" style="color:var(--faint)" /></template>
        </n-input>
        <n-button type="primary" :loading="loading" @click="recall">
          <template #icon><Icon icon="mdi:file-search" :width="15" /></template>检索
        </n-button>
      </div>
    </div>

    <!-- 三层记忆 -->
    <div class="mem-grid">
      <!-- 向量记忆 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(79,195,247,0.1)"><Icon icon="mdi:database-search-outline" :width="17" /></span>
            <span>向量记忆</span>
            <span class="wb-sec-sub">CHROMADB</span>
          </div>
          <span class="wb-chip">{{ recallResult.vector?.length || 0 }} 条</span>
        </div>
        <div v-if="recallResult.vector?.length" class="mem-list">
          <div v-for="(r, i) in recallResult.vector" :key="i" class="mem-item">
            <div class="mem-item-doc">{{ (r.document || r.content || '').slice(0, 80) }}</div>
            <div class="mem-item-meta">
              <span class="wb-chip dim mono">{{ (r.score ?? r.distance ?? 0).toFixed(3) }}</span>
              <span class="wb-chip amber mono">{{ r.metadata?.action || '—' }}</span>
            </div>
          </div>
        </div>
        <div v-else class="wb-empty">
          <Icon icon="mdi:database-off-outline" :width="24" style="opacity:0.5" />
          <p>暂无向量案例</p>
          <span>运行决策后案例将自动写入 ChromaDB</span>
        </div>
      </div>

      <!-- 瞬时记忆 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(255,213,79,0.1);color:var(--amber)"><Icon icon="mdi:timeline-clock-outline" :width="17" /></span>
            <span>瞬时记忆</span>
            <span class="wb-sec-sub">SLIDING WINDOW</span>
          </div>
          <span class="wb-chip amber">{{ recallResult.instant?.length || 0 }} 条</span>
        </div>
        <div v-if="recallResult.instant?.length" class="mem-list">
          <div v-for="(e, i) in recallResult.instant" :key="i" class="mem-item mem-instant">
            <span class="wb-badge">#{{ e.cycle_id }}</span>
            <span class="mem-action" :class="e.action">{{ e.action }}</span>
            <span class="wb-spacer"></span>
            <span class="mem-pnl" :class="e.pnl >= 0 ? 'up' : 'down'">{{ e.pnl }}</span>
          </div>
        </div>
        <div v-else class="wb-empty">
          <Icon icon="mdi:timeline-remove-outline" :width="24" style="opacity:0.5" />
          <p>暂无瞬时记忆</p>
          <span>滑动窗口将记录最近 N 次决策行为</span>
        </div>
      </div>

      <!-- 因果记忆 -->
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:graph-outline" :width="17" /></span>
            <span>因果记忆</span>
            <span class="wb-sec-sub">NEO4J PATHS</span>
          </div>
          <span class="wb-chip dim">{{ recallResult.causal?.length || 0 }} 路径</span>
        </div>
        <div v-if="recallResult.causal?.length" class="mem-list">
          <div v-for="(c, i) in recallResult.causal" :key="i" class="mem-item">
            <code class="mem-path">{{ JSON.stringify(c).slice(0, 110) }}</code>
          </div>
        </div>
        <div v-else class="wb-empty">
          <Icon icon="mdi:graph-off-outline" :width="24" style="opacity:0.5" />
          <p>暂无因果路径</p>
          <span>因果抽取结果将存入 Neo4j 图谱</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import api from '../api'

const query = ref('BTCUSDT market regime')
const recallResult = ref({})
const loading = ref(false)

async function recall() {
  loading.value = true
  try {
    const { data } = await api.memoryRecall({ query: query.value, top_k: 5 })
    recallResult.value = data
  } finally { loading.value = false }
}
onMounted(recall)
</script>

<style scoped lang="scss">
.mem { display: flex; flex-direction: column; gap: 1.2rem; }

.mem-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2rem; }

.wb-spacer { flex: 1; }

.mem-list { display: flex; flex-direction: column; gap: 0.5rem; }
.mem-item {
  padding: 0.6rem 0.7rem;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  border: 0.5px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.mem-item-doc { font-size: 0.7rem; color: var(--text); line-height: 1.5; }
.mem-item-meta { display: flex; gap: 0.4rem; }

.mem-instant { flex-direction: row; align-items: center; }
.mem-action {
  font-size: 0.74rem; font-weight: 600; text-transform: uppercase;
  &.long { color: var(--green); }
  &.short { color: var(--red); }
  &.hold { color: var(--dim); }
}
.mem-pnl { font-family: var(--mono); font-size: 0.78rem; &.up { color: var(--green); } &.down { color: var(--red); } }
.mem-path { font-size: 0.62rem; color: var(--dim); white-space: pre-wrap; word-break: break-all; line-height: 1.6; }

@media (max-width: 1000px) {
  .mem-grid { grid-template-columns: 1fr; }
}
</style>
