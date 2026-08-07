<template>
  <div class="au">
    <!-- 页头 -->
    <div class="page-head">
      <div>
        <div class="page-title">自动化 <span>AUTOMATION</span></div>
        <div class="page-sub">定时任务 · 一键实验流 · 通知告警</div>
      </div>
    </div>

    <!-- 新建任务 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(105,240,174,0.1);color:var(--green)"><Icon icon="mdi:plus-circle-outline" :width="17" /></span>
          <span>新建定时任务</span>
          <span class="wb-sec-sub">SCHEDULE</span>
        </div>
      </div>
      <div class="au-create">
        <div class="au-field">
          <label class="wb-bar-label">任务类型</label>
          <n-select v-model:value="form.kind" :options="kindOptions" size="small" style="width:140px" />
        </div>
        <div class="au-field">
          <label class="wb-bar-label">间隔（秒）</label>
          <n-input-number v-model:value="form.interval_seconds" size="small" style="width:110px" :min="0" :step="60" />
        </div>
        <div class="au-field" style="flex:1;min-width:160px">
          <label class="wb-bar-label">名称（可选）</label>
          <n-input v-model:value="form.name" size="small" placeholder="自动任务" />
        </div>
        <n-button type="primary" @click="create">
          <template #icon><Icon icon="mdi:calendar-plus" :width="15" /></template>创建任务
        </n-button>
      </div>
      <div class="au-hint">
        <Icon icon="mdi:information-outline" :width="13" style="vertical-align:-2px" />
        间隔 0 = 一次性任务；由后端调度器执行（采集 / 导入 / 自动决策 / 回测）
      </div>
    </div>

    <!-- 定时任务 + 实验流 -->
    <div class="au-bottom">
      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon"><Icon icon="mdi:calendar-clock-outline" :width="17" /></span>
            <span>定时任务</span>
            <span class="wb-sec-sub">SCHEDULED · {{ scheduled.length }}</span>
          </div>
        </div>
        <n-table v-if="scheduled.length" size="small" :bordered="false" :single-line="false">
          <thead>
            <tr><th>名称</th><th>类型</th><th>间隔</th><th>状态</th><th style="text-align:right">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in scheduled" :key="t.id">
              <td>{{ t.name }}</td>
              <td><span class="wb-chip">{{ t.kind }}</span></td>
              <td class="mono dim">{{ t.interval_seconds }}s</td>
              <td><span class="wb-chip" :class="t.status === 'active' ? 'green' : 'dim'">{{ t.status }}</span></td>
              <td style="text-align:right">
                <n-button size="tiny" type="error" quaternary @click="remove(t.id)">
                  <template #icon><Icon icon="mdi:trash-can-outline" :width="13" /></template>删除
                </n-button>
              </td>
            </tr>
          </tbody>
        </n-table>
        <div v-else class="wb-empty">
          <Icon icon="mdi:calendar-blank-outline" :width="26" style="opacity:0.5" />
          <p>暂无定时任务</p>
          <span>创建后由后端调度器按间隔自动执行</span>
        </div>
      </div>

      <div class="wb-card">
        <div class="wb-sec-head">
          <div class="wb-sec-title">
            <span class="wb-sec-icon" style="background:rgba(206,147,216,0.12);color:#ce93d8"><Icon icon="mdi:ray-start-arrow" :width="17" /></span>
            <span>一键实验流</span>
            <span class="wb-sec-sub">PIPELINE</span>
          </div>
        </div>
        <div class="au-pipe">
          <div class="au-pipe-step">
            <span class="au-pipe-num">①</span><span class="au-pipe-name">采集</span>
            <span class="au-pipe-desc">binance BTCUSDT → parquet</span>
          </div>
          <div class="au-pipe-step">
            <span class="au-pipe-num">②</span><span class="au-pipe-name">导入</span>
            <span class="au-pipe-desc">parquet → TimescaleDB</span>
          </div>
          <div class="au-pipe-step">
            <span class="au-pipe-num">③</span><span class="au-pipe-name">决策</span>
            <span class="au-pipe-desc">真实 LLM 全闭环</span>
          </div>
          <div class="au-pipe-step">
            <span class="au-pipe-num">④</span><span class="au-pipe-name">进化</span>
            <span class="au-pipe-desc">DEAP 后台任务</span>
          </div>
          <div class="au-pipe-actions">
            <n-button type="primary" size="small" @click="$router.push('/decision')">去决策实验室 →</n-button>
            <n-button secondary size="small" @click="$router.push('/evolution')">去进化控制台 →</n-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 告警 -->
    <div class="wb-card">
      <div class="wb-sec-head">
        <div class="wb-sec-title">
          <span class="wb-sec-icon" style="background:rgba(239,83,80,0.1);color:var(--red)"><Icon icon="mdi:bell-ring-outline" :width="17" /></span>
          <span>最近告警</span>
          <span class="wb-sec-sub">ALERTS</span>
        </div>
        <span class="wb-chip" :class="agent.alerts.length ? 'amber' : 'green'">{{ agent.alerts.length }} 条</span>
      </div>
      <div v-if="agent.alerts.length" class="au-alerts">
        <div v-for="(a, i) in agent.alerts" :key="i" class="au-alert" :class="a.level">
          <span class="wb-chip" :class="a.level === 'error' ? 'red' : 'amber'">{{ a.level }}</span>
          <span class="au-alert-title">{{ a.title }}</span>
          <span class="au-alert-detail">{{ a.detail }}</span>
          <span class="wb-spacer" style="flex:1"></span>
          <span class="au-alert-time">{{ shortTs(a.ts) }}</span>
        </div>
      </div>
      <div v-else class="wb-empty">
        <Icon icon="mdi:bell-sleep-outline" :width="26" style="opacity:0.5" />
        <p>暂无告警</p>
        <span>任务失败 / 回撤超限等事件将在此通知</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useMessage } from 'naive-ui'
import api from '../api'
import { useAgentStore } from '../stores/agent'

const router = useRouter()
const message = useMessage()
const agent = useAgentStore()
const scheduled = ref([])
const form = ref({ kind: 'collect', interval_seconds: 3600, name: '' })

const kindOptions = [
  { label: '数据采集', value: 'collect' },
  { label: '数据导入', value: 'import' },
  { label: '自动决策', value: 'decision' },
  { label: '自动回测', value: 'backtest' },
]

async function load() { try { const { data } = await api.tasks(); scheduled.value = data.scheduled || [] } catch {} }
async function create() {
  await api.taskCreate({ kind: form.value.kind, name: form.value.name || form.value.kind, interval_seconds: form.value.interval_seconds })
  message.success('任务已创建')
  form.value.name = ''
  await load()
}
async function remove(id) { await api.taskDelete(id); message.info('任务已删除'); await load() }
const shortTs = (ts) => (ts ? String(ts).slice(0, 19) : '')

onMounted(load)
</script>

<style scoped lang="scss">
.au { display: flex; flex-direction: column; gap: 1.2rem; }

.wb-spacer { flex: 1; }

.au-create { display: flex; gap: 1rem; align-items: flex-end; flex-wrap: wrap; }
.au-field { display: flex; flex-direction: column; gap: 0.35rem; }
.au-hint {
  margin-top: 0.8rem; font-size: 0.62rem; color: var(--faint);
  display: flex; align-items: center; gap: 0.35rem;
}

.au-bottom { display: grid; grid-template-columns: 1.2fr 1fr; gap: 1.2rem; }

.au-pipe { display: flex; flex-direction: column; gap: 0.5rem; }
.au-pipe-step {
  display: flex; align-items: center; gap: 0.6rem;
  padding: 0.5rem 0.7rem; border-radius: 6px;
  background: rgba(255, 255, 255, 0.02); border: 0.5px solid var(--border);
}
.au-pipe-num { font-size: 0.8rem; color: var(--accent); }
.au-pipe-name { font-size: 0.74rem; font-weight: 500; width: 44px; }
.au-pipe-desc { font-size: 0.64rem; color: var(--faint); }
.au-pipe-actions { display: flex; gap: 0.6rem; margin-top: 0.6rem; }

.au-alerts { display: flex; flex-direction: column; gap: 0.5rem; }
.au-alert {
  display: flex; align-items: center; gap: 0.7rem;
  padding: 0.55rem 0.7rem; border-radius: 6px;
  background: rgba(255, 213, 79, 0.04); border: 0.5px solid rgba(255, 213, 79, 0.2);
  &.error { background: rgba(239, 83, 80, 0.04); border-color: rgba(239, 83, 80, 0.2); }
}
.au-alert-title { font-size: 0.72rem; font-weight: 500; }
.au-alert-detail { font-size: 0.66rem; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.au-alert-time { font-size: 0.58rem; color: var(--faint); font-family: var(--mono); }

@media (max-width: 1000px) {
  .au-bottom { grid-template-columns: 1fr; }
}
</style>
