<template>
  <section v-if="overviewReady" class="panel-section trend-overview-section">
    <div class="section-title">运行趋势总览</div>
    <div class="overview-note">
      先看整体曲线，再看单指标细节。以下曲线已统一换算为相对各自参考值的偏差百分比，便于不同指标同屏比较。
    </div>

    <div class="overview-kpis">
      <div class="overview-kpi">
        <span>纳入指标</span>
        <strong>{{ overview.indicator_count }}</strong>
      </div>
      <div class="overview-kpi">
        <span>观察窗口</span>
        <strong>{{ overview.window_point_count }} 点</strong>
      </div>
      <div class="overview-kpi">
        <span>异常起点</span>
        <strong>{{ compactTimestamp(overview.abnormal_start) }}</strong>
      </div>
      <div class="overview-kpi">
        <span>最新快照</span>
        <strong>{{ compactTimestamp(overview.latest_timestamp) }}</strong>
      </div>
    </div>

    <div class="overview-series-list">
      <article v-for="series in orderedSeries" :key="series.tag_id || series.indicator_name" class="overview-series-chip">
        <span class="series-dot" :style="{ backgroundColor: colorForSeries(series) }"></span>
        <div class="series-copy">
          <strong>{{ series.indicator_name }}</strong>
          <span>{{ series.reference_label }} | 当前 {{ formatMetric(series.current_value, series.unit) }}</span>
        </div>
        <div class="series-delta" :class="deltaTone(series.current_relative_percent)">
          {{ formatDelta(series.current_relative_percent) }}
        </div>
      </article>
    </div>

    <div class="overview-chart-head">
      <span>{{ overview.y_axis_label }}</span>
      <div class="overview-chart-actions">
        <span>{{ compactTimestamp(overview.window_start) }} -> {{ compactTimestamp(overview.window_end) }}</span>
        <button class="chart-expand-btn" type="button" @click="openLightbox">放大查看</button>
      </div>
    </div>
    <div class="overview-chart-wrap clickable" @click="openLightbox">
      <canvas ref="canvasRef"></canvas>
    </div>

    <div v-if="overview.insight_lines?.length" class="overview-insights">
      <div v-for="line in overview.insight_lines" :key="line" class="overview-insight-line">{{ line }}</div>
    </div>
  </section>

  <ChartLightbox
    :visible="lightboxVisible"
    title="运行趋势总览"
    :subtitle="`${compactTimestamp(overview.window_start)} -> ${compactTimestamp(overview.window_end)}`"
    @close="closeLightbox"
  >
    <div class="lightbox-chart-wrap">
      <canvas ref="lightboxCanvasRef"></canvas>
    </div>
  </ChartLightbox>
</template>

<script setup>
import { Chart, CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip } from 'chart.js'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import ChartLightbox from './ChartLightbox.vue'

Chart.register(CategoryScale, LinearScale, LineController, LineElement, PointElement, Filler, Legend, Tooltip)

const props = defineProps({
  result: { type: Object, required: true },
})

const SERIES_COLORS = ['#2563eb', '#dc2626', '#0f766e', '#7c3aed', '#ea580c']

const canvasRef = ref(null)
const lightboxCanvasRef = ref(null)
const lightboxVisible = ref(false)
let chartRef = null
let lightboxChartRef = null

const overview = computed(() => {
  const raw = props.result?.visualization_context?.overview_card
  return raw && typeof raw === 'object' ? raw : {}
})

const orderedSeries = computed(() => {
  const rows = Array.isArray(overview.value.series) ? [...overview.value.series] : []
  return rows.sort((a, b) => Number(b?.severity_score || 0) - Number(a?.severity_score || 0))
})

const overviewReady = computed(() => {
  return Boolean(overview.value?.timestamps?.length && orderedSeries.value.length)
})

function compactTimestamp(value) {
  const text = `${value || ''}`.trim()
  if (!text) return '-'
  if (text.includes('T')) {
    const [datePart, timePart] = text.split('T')
    return `${datePart} ${timePart.slice(0, 5)}`
  }
  return text.slice(0, 16)
}

function formatMetric(value, unit = '') {
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  const rendered = Math.abs(n) >= 100 ? n.toFixed(1) : Math.abs(n) >= 10 ? n.toFixed(2) : n.toFixed(3)
  return `${rendered}${unit ? ` ${unit}` : ''}`
}

function formatDelta(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function deltaTone(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'neutral'
  if (n > 0) return 'up'
  if (n < 0) return 'down'
  return 'neutral'
}

function colorForSeries(series) {
  const index = orderedSeries.value.findIndex((item) => item === series)
  return SERIES_COLORS[index >= 0 ? index % SERIES_COLORS.length : 0]
}

function destroyChart() {
  if (chartRef) {
    chartRef.destroy()
    chartRef = null
  }
  if (lightboxChartRef) {
    lightboxChartRef.destroy()
    lightboxChartRef = null
  }
}

function buildChart(targetCanvas) {
  if (!overviewReady.value || !targetCanvas) return null
  const timestamps = Array.isArray(overview.value.timestamps) ? overview.value.timestamps : []
  const labels = timestamps.map((item) => compactTimestamp(item))
  const chartDisplay = overview.value.chart_display || {}
  const abnormalStartIndex = Number.isInteger(Number(chartDisplay.abnormal_start_index))
    ? Number(chartDisplay.abnormal_start_index)
    : null
  const latestIndex = Number.isInteger(Number(chartDisplay.latest_index))
    ? Number(chartDisplay.latest_index)
    : labels.length - 1

  const abnormalWindowPlugin = {
    id: 'overview-abnormal-window',
    beforeDatasetsDraw(chart) {
      if (!Number.isInteger(abnormalStartIndex) || !Number.isInteger(latestIndex) || !chart.chartArea) return
      const { ctx, chartArea, scales } = chart
      const left = scales.x.getPixelForValue(abnormalStartIndex) - 8
      const right = scales.x.getPixelForValue(latestIndex) + 8
      ctx.save()
      ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'
      ctx.fillRect(left, chartArea.top, Math.max(0, right - left), chartArea.bottom - chartArea.top)
      ctx.restore()
    },
  }

  const datasets = [
    {
      label: '参考基线',
      data: labels.map(() => 0),
      borderColor: 'rgba(100, 116, 139, 0.7)',
      borderDash: [6, 4],
      borderWidth: 1.1,
      pointRadius: 0,
      fill: false,
    },
    ...orderedSeries.value.map((series, index) => ({
      label: series.indicator_name,
      data: Array.isArray(series.values_percent) ? series.values_percent : [],
      borderColor: SERIES_COLORS[index % SERIES_COLORS.length],
      backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length],
      borderWidth: 2.2,
      tension: 0.22,
      pointRadius: 0,
      pointHoverRadius: 4,
      spanGaps: true,
      fill: false,
    })),
  ]

  return new Chart(targetCanvas, {
    type: 'line',
    plugins: [abnormalWindowPlugin],
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          align: 'start',
          labels: { boxWidth: 10, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = Number(context.raw)
              return `${context.dataset.label}: ${Number.isFinite(value) ? value.toFixed(1) : '-'}%`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { autoSkip: true, maxTicksLimit: 6 },
        },
        y: {
          title: {
            display: true,
            text: overview.value.y_axis_label || '相对参考偏差 (%)',
          },
          grid: { color: 'rgba(148,163,184,0.18)' },
          min: Number.isFinite(Number(chartDisplay.plot_min)) ? Number(chartDisplay.plot_min) : undefined,
          max: Number.isFinite(Number(chartDisplay.plot_max)) ? Number(chartDisplay.plot_max) : undefined,
        },
      },
    },
  })
}

function renderCharts() {
  if (chartRef) {
    chartRef.destroy()
    chartRef = null
  }
  if (lightboxChartRef) {
    lightboxChartRef.destroy()
    lightboxChartRef = null
  }
  if (overviewReady.value && canvasRef.value) {
    chartRef = buildChart(canvasRef.value)
  }
  if (overviewReady.value && lightboxVisible.value && lightboxCanvasRef.value) {
    lightboxChartRef = buildChart(lightboxCanvasRef.value)
  }
}

async function openLightbox() {
  lightboxVisible.value = true
  await nextTick()
  renderCharts()
}

function closeLightbox() {
  lightboxVisible.value = false
  if (lightboxChartRef) {
    lightboxChartRef.destroy()
    lightboxChartRef = null
  }
}

watch(
  overviewReady,
  async (ready) => {
    if (!ready) {
      destroyChart()
      return
    }
    await nextTick()
    renderCharts()
  },
  { immediate: true },
)

watch(
  overview,
  async () => {
    if (!overviewReady.value) return
    await nextTick()
    renderCharts()
  },
  { deep: true },
)

watch(lightboxVisible, async (visible) => {
  if (!visible) return
  await nextTick()
  renderCharts()
})

onBeforeUnmount(() => {
  destroyChart()
})
</script>

<style scoped>
.panel-section { padding: 13px; border: 1px solid var(--ui-border); border-radius: 8px; background: var(--ui-surface); }
.section-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
.section-title::before { content: ''; width: 4px; height: 12px; border-radius: 999px; background: var(--ui-primary); }
.trend-overview-section { display: grid; gap: 12px; }
.overview-note { padding: 10px 12px; border: 1px dashed rgba(37, 99, 235, 0.24); border-radius: 8px; background: rgba(37, 99, 235, 0.05); font-size: 12px; line-height: 1.6; color: var(--ui-muted); }
.overview-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.overview-kpi { display: grid; gap: 4px; padding: 10px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.overview-kpi span { font-size: 11px; color: var(--ui-muted); }
.overview-kpi strong { font-size: 13px; color: var(--ui-text); }
.overview-series-list { display: grid; gap: 8px; }
.overview-series-chip { display: grid; grid-template-columns: 14px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92)); }
.series-dot { width: 10px; height: 10px; border-radius: 999px; }
.series-copy { display: grid; gap: 4px; min-width: 0; }
.series-copy strong { font-size: 13px; line-height: 1.4; color: var(--ui-text); }
.series-copy span { font-size: 11px; line-height: 1.5; color: var(--ui-muted); }
.series-delta { font-size: 13px; font-weight: 800; white-space: nowrap; }
.series-delta.up { color: #c2410c; }
.series-delta.down { color: #1d4ed8; }
.series-delta.neutral { color: var(--ui-text); }
.overview-chart-head { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; font-size: 11px; color: var(--ui-muted); }
.overview-chart-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.chart-expand-btn { min-height: 28px; padding: 0 10px; border: 1px solid rgba(37,99,235,.18); border-radius: 999px; background: rgba(37,99,235,.08); color: #1d4ed8; font-size: 11px; font-weight: 700; cursor: pointer; }
.overview-chart-wrap { height: 320px; padding: 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.overview-chart-wrap.clickable { cursor: zoom-in; }
.lightbox-chart-wrap { height: min(72vh, 760px); min-height: 420px; padding: 14px; border: 1px solid var(--ui-border); border-radius: 12px; background: #fff; }
.overview-insights { display: grid; gap: 8px; }
.overview-insight-line { padding: 8px 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.04); border: 1px solid rgba(148, 163, 184, 0.18); font-size: 11px; line-height: 1.55; color: #475569; }
@media (max-width: 1080px) {
  .overview-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .overview-kpis { grid-template-columns: 1fr; }
  .overview-series-chip { grid-template-columns: 14px minmax(0, 1fr); }
  .series-delta { grid-column: 2; }
  .overview-chart-wrap { height: 260px; }
}
</style>
