import { defineStore } from 'pinia'
import api from '../api'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    state: null,           // /api/agent/status -> state
    dbStats: null,         // /api/db -> db
    architecture: null,
    regime: null,          // 当前市场 Regime（感知切片）
    connected: false,
    lastUpdate: null,
    wsConnected: false,
    alerts: [],
    polling: null,
  }),
  getters: {
    agentStatus: (s) => s.state?.status || 'idle',
    recentDecisions: (s) => s.state?.recent_decisions || [],
  },
  actions: {
    async fetchAgentStatus() {
      try {
        const { data } = await api.agentStatus()
        this.state = data.state
        this.connected = true
        this.lastUpdate = data.ts
      } catch { this.connected = false }
    },
    async fetchDb() { try { const { data } = await api.db(); this.dbStats = data.db } catch {} },
    async fetchRegime() {
      try {
        const { data } = await api.perceptionSlices()
        this.regime = data.perception?.regime || null
      } catch {}
    },
    async fetchArchitecture() { try { const { data } = await api.architecture(); this.architecture = data } catch {} },
    pushAlert(level, title, detail) {
      this.alerts.unshift({ level, title, detail, ts: new Date().toISOString() })
      if (this.alerts.length > 30) this.alerts.pop()
    },
    async startPause() {
      if (this.agentStatus === 'running') await api.agentPause()
      else if (this.agentStatus === 'paused') await api.agentResume()
      else await api.agentStart()
      await this.fetchAgentStatus()
    },
    async step() { await api.agentStatus() },
    startPolling(interval = 4000) {
      this.fetchAgentStatus()
      this.fetchDb()
      this.fetchArchitecture()
      this.fetchRegime()
      this.polling = setInterval(() => {
        this.fetchAgentStatus()
        this.fetchDb()
        this.fetchRegime()
      }, interval)
    },
    stopPolling() { if (this.polling) { clearInterval(this.polling); this.polling = null } },
  },
})
