import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 120000 })

export default {
  // agent
  agentStatus: () => api.get('/agent/status'),
  agentStart: () => api.post('/agent/start'),
  agentPause: () => api.post('/agent/pause'),
  agentResume: () => api.post('/agent/resume'),
  // db / arch
  db: () => api.get('/db'),
  architecture: () => api.get('/architecture'),
  // data
  klines: (params) => api.get('/klines', { params }),
  dataSources: () => api.get('/data/sources'),
  dataLatest: (symbol) => api.get('/data/latest', { params: { symbol } }),
  dataCollect: (body) => api.post('/data/collect', body),
  dataImport: () => api.post('/data/import'),
  // perception / causal
  perceptionSlices: (symbol) => api.get('/perception/slices', { params: { symbol } }),
  perceptionGranger: (symbol) => api.get('/perception/granger', { params: { symbol } }),
  causalGraph: () => api.get('/causal/graph'),
  // memory
  memoryRecall: (params) => api.get('/memory/recall', { params }),
  // decision
  decisionRun: (body) => api.post('/decision/run', body),
  decisionDetail: (cycleId) => api.get(`/decision/${cycleId}`),
  // backtest
  backtestRun: (body) => api.post('/backtest/run', body),
  backtestResult: (params) => api.get('/backtest/result', { params }),
  // evolution
  evolutionStart: (body) => api.post('/evolution/start', body),
  evolutionPause: (taskId) => api.post(`/evolution/${taskId}/pause`),
  evolutionCurve: () => api.get('/evolution/curve'),
  evolutionPopulation: () => api.get('/evolution/population'),
  evolutionConvergence: () => api.get('/evolution/convergence'),
  evolutionTree: () => api.get('/evolution/tree'),
  experiments: () => api.get('/experiments'),
  experimentsCompare: (params) => api.get('/experiments/compare', { params }),
  // account
  account: () => api.get('/account'),
  accountHistory: () => api.get('/account/history'),
  // config
  config: () => api.get('/config'),
  configUpdate: (data) => api.put('/config', { data }),
  // regime / knowledge / tools
  regimePolicy: () => api.get('/regime/policy'),
  knowledgeRules: () => api.get('/knowledge/rules'),
  tools: () => api.get('/tools'),
  // tasks
  tasks: () => api.get('/tasks'),
  taskCreate: (body) => api.post('/tasks', body),
  taskDelete: (id) => api.delete(`/tasks/${id}`),
}
