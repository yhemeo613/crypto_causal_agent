import { defineStore } from 'pinia'
import { useAgentStore } from './agent'

/**
 * WebSocket 订阅：/ws 事件 → 更新 agent store / 页面可 watch
 * 事件：agent.status / agent.decision / db.updated / task.update / evolution.generation / alert
 */
export const useSocketStore = defineStore('socket', {
  state: () => ({
    ws: null,
    connected: false,
    lastEvent: null,
    taskEvents: [],        // 最近任务事件
    logEvents: [],         // 实时日志流
    evolutionPoints: [],   // 实时进化曲线点
    listeners: {},
  }),
  actions: {
    connect() {
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      this.ws = ws
      ws.onopen = () => { this.connected = true }
      ws.onclose = () => { this.connected = false; setTimeout(() => this.connect(), 5000) }
      ws.onerror = () => { this.connected = false }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          this.lastEvent = msg
          const agent = useAgentStore()
          if (msg.event === 'agent.status') agent.state = msg.data
          if (msg.event === 'agent.decision') {
            agent.fetchAgentStatus()
            agent.fetchDb()
          }
          if (msg.event === 'db.updated') agent.fetchDb()
          if (msg.event === 'task.update') {
            this.taskEvents.unshift(msg.data)
            if (this.taskEvents.length > 50) this.taskEvents.pop()
          }
          if (msg.event === 'log') {
            this.logEvents.unshift(msg.data)
            if (this.logEvents.length > 400) this.logEvents.pop()
          }
          if (msg.event === 'evolution.generation') this.evolutionPoints.push(msg.data)
          if (msg.event === 'alert') agent.pushAlert(msg.data.level, msg.data.title, msg.data.detail)
          const cbs = this.listeners[msg.event] || []
          cbs.forEach((cb) => cb(msg.data))
        } catch { /* ignore */ }
      }
    },
    on(event, cb) {
      if (!this.listeners[event]) this.listeners[event] = []
      this.listeners[event].push(cb)
    },
    clearEvolution() { this.evolutionPoints = [] },
  },
})
