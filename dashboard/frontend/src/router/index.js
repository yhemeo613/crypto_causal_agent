import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'

const routes = [
  { path: '/', name: 'overview', component: () => import('../views/Overview.vue'), meta: { title: '总览', icon: 'mdi:view-dashboard-outline' } },
  { path: '/data', name: 'data', component: () => import('../views/DataView.vue'), meta: { title: '数据', icon: 'mdi:database-outline' } },
  { path: '/perception', name: 'perception', component: () => import('../views/Perception.vue'), meta: { title: '感知因果', icon: 'mdi:graph-outline' } },
  { path: '/memory', name: 'memory', component: () => import('../views/Memory.vue'), meta: { title: '记忆', icon: 'mdi:memory' } },
  { path: '/decision', name: 'decision', component: () => import('../views/DecisionLab.vue'), meta: { title: '决策实验室', icon: 'mdi:brain' } },
  { path: '/sandbox', name: 'sandbox', component: () => import('../views/Sandbox.vue'), meta: { title: '回测沙箱', icon: 'mdi:flask-outline' } },
  { path: '/evolution', name: 'evolution', component: () => import('../views/Evolution.vue'), meta: { title: '进化', icon: 'mdi:dna' } },
  { path: '/account', name: 'account', component: () => import('../views/Account.vue'), meta: { title: '账户风控', icon: 'mdi:shield-account-outline' } },
  { path: '/automation', name: 'automation', component: () => import('../views/Automation.vue'), meta: { title: '自动化', icon: 'mdi:refresh-auto' } },
  { path: '/monitor', name: 'monitor', component: () => import('../views/Monitor.vue'), meta: { title: '监控', icon: 'mdi:monitor-dashboard' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '设置', icon: 'mdi:cog-outline' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

NProgress.configure({ showSpinner: false, trickleSpeed: 120 })
router.beforeEach(() => { NProgress.start() })
router.afterEach((to) => {
  NProgress.done()
  document.title = to.meta.title ? `${to.meta.title} · Agent 工作台` : 'Agent 工作台'
})

export default router
