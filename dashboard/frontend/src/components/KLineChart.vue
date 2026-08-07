<template>
  <div ref="el" class="klc" :style="{ height }">
    <div v-if="error" class="klc-error">{{ error }}</div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  data: { type: Array, default: () => [] },   // [{ts, open, high, low, close, volume}]
  height: { type: String, default: '520px' },
})

const el = ref(null)
const error = ref('')
let chart = null
let candle = null
let ma20 = null
let ma60 = null
let vol = null
let timer = null

function sma(values, period) {
  return values.map((_, i) => {
    if (i < period - 1) return null
    let s = 0
    for (let j = i - period + 1; j <= i; j++) s += values[j]
    return s / period
  })
}

function render() {
  if (!chart || !candle || !props.data.length) return
  try {
    const list = props.data
    const time = (r) => Math.floor(new Date(r.ts).getTime() / 1000)
    candle.setData(list.map((r) => ({
      time: time(r), open: r.open, high: r.high, low: r.low, close: r.close,
    })))

    const closes = list.map((r) => r.close)
    const times = list.map((r) => time(r))
    const toPts = (arr) => arr.map((v, i) => (v === null ? null : { time: times[i], value: +v.toFixed(2) })).filter(Boolean)
    ma20.setData(toPts(sma(closes, 20)))
    ma60.setData(toPts(sma(closes, 60)))

    vol.setData(list.map((r) => ({
      time: time(r), value: r.volume,
      color: r.close >= r.open ? 'rgba(105,240,174,0.45)' : 'rgba(239,83,80,0.45)',
    })))

    chart.timeScale().fitContent()
  } catch (e) {
    console.warn('[kline] render:', e?.message)
  }
}

async function ensureChart() {
  if (chart) return true
  const host = el.value
  if (!host) return false
  if ((host.offsetWidth || 0) < 2 || (host.offsetHeight || 0) < 2) return false
  try {
    const m = await import('lightweight-charts')
    const {
      createChart, ColorType, CrosshairMode,
      CandlestickSeries, LineSeries, HistogramSeries,
    } = m.default || m
    if (typeof createChart !== 'function') {
      error.value = 'lightweight-charts 加载异常'
      return false
    }
    chart = createChart(host, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'rgba(255,255,255,0.6)',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.06)' },
        horzLines: { color: 'rgba(255,255,255,0.06)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(79,195,247,0.5)', labelBackgroundColor: '#4fc3f7' },
        horzLine: { color: 'rgba(79,195,247,0.5)', labelBackgroundColor: '#4fc3f7' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.15)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.15)', timeVisible: true, secondsVisible: false, rightOffset: 6 },
    })

    // v5 统一入口 addSeries(SeriesDefinition, options) —— 导出为大写常量
    candle = chart.addSeries(CandlestickSeries, {
      upColor: '#69f0ae', downColor: '#ef5350',
      wickUpColor: '#69f0ae', wickDownColor: '#ef5350',
      borderVisible: false,
    })
    ma20 = chart.addSeries(LineSeries, { color: '#ffd54f', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    ma60 = chart.addSeries(LineSeries, { color: '#4fc3f7', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })

    render()
    return true
  } catch (e) {
    error.value = `K 线初始化失败: ${e.message}`
    console.error('[kline] init:', e)
    return false
  }
}

onMounted(() => {
  const t0 = Date.now()
  timer = setInterval(async () => {
    const ok = await ensureChart()
    if (ok || Date.now() - t0 > 6000) clearInterval(timer)
  }, 250)
})

watch(() => props.data, () => render(), { deep: true })

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  try { if (chart) { chart.remove(); chart = null } } catch {}
})

defineExpose({ chart: () => chart })
</script>

<style scoped>
.klc { width: 100%; background: transparent; position: relative; }
.klc-error {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255, 255, 255, 0.4); font-size: 0.75rem; letter-spacing: 0.05em;
}
</style>
