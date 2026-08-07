import { defineStore } from 'pinia'
import axios from 'axios'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    state: null,
    architecture: null,
    dbStats: null,
    connected: false,
    lastUpdate: null,
    polling: null,
  }),
  actions: {
    async fetchState() {
      try {
        const { data } = await axios.get('/api/state')
        this.state = data.state
        this.connected = true
        this.lastUpdate = data.ts
      } catch { this.connected = false }
    },
    async fetchArchitecture() { try { const { data } = await axios.get('/api/architecture'); this.architecture = data } catch {} },
    async fetchDbStats() { try { const { data } = await axios.get('/api/db'); this.dbStats = data.db } catch {} },
    startPolling(interval = 3000) {
      this.fetchState()
      this.fetchArchitecture()
      this.fetchDbStats()
      this.polling = setInterval(() => {
        this.fetchState()
        this.fetchDbStats()
      }, interval)
    },
    stopPolling() { if (this.polling) { clearInterval(this.polling); this.polling = null } }
  }
})
