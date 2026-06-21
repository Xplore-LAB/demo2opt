<template>
  <section v-if="cards.length || overallAbnormalGroups.length" class="panel-section viz-section">
    <div class="section-header">
      <div class="section-title">时间对比可视化</div>
      <div v-if="cards.length && overallAbnormalGroups.length" class="viz-view-switch">
        <button
          class="viz-view-switch-btn"
          :class="{ active: activeView === 'comparison' }"
          type="button"
          @click="activeView = 'comparison'"
        >
          重点时间对比
        </button>
        <button
          class="viz-view-switch-btn"
          :class="{ active: activeView === 'overall' }"
          type="button"
          @click="activeView = 'overall'"
        >
          整体数据当前异常
        </button>
      </div>
    </div>
    <div class="viz-note">
      <template v-if="activeView === 'comparison'">
        以下图卡仅展示当前值、历史位置和目标/优态参考的对比关系，不等于根因确认。
      </template>
      <template v-else>
        以下内容把当前异常映射回整体数据曲线分类，便于结合全量历史和负荷参照线观察联动与相关性。
      </template>
    </div>

    <div v-if="activeView === 'comparison'" class="viz-card-list">
      <article
        v-for="card in cards"
        :key="cardKey(card)"
        class="viz-card"
        :class="{ active: openCardKey === cardKey(card) }"
      >
        <button class="viz-card-toggle" type="button" @click="toggleCard(card)">
          <div class="viz-card-head">
            <div>
              <div class="viz-rank">TOP {{ card.rank }}</div>
              <strong>{{ card.indicator_name }}</strong>
            </div>
            <div class="viz-state">
              <span class="viz-state-pill">{{ card.state_desc || '异常' }}</span>
              <span class="viz-state-score">severity {{ formatSeverity(card.severity_score) }}</span>
            </div>
          </div>
        </button>

        <div v-if="openCardKey === cardKey(card)" class="viz-card-body">
          <div class="viz-metrics">
            <div class="viz-metric">
              <span>当前值</span>
              <strong>{{ formatMetric(card.current_value, card.unit) }}</strong>
            </div>
            <div class="viz-metric">
              <span>历史中位</span>
              <strong>{{ formatMetric(card.history_stats?.median, card.unit) }}</strong>
            </div>
            <div class="viz-metric">
              <span>目标参考</span>
              <strong>{{ formatMetric(card.references?.target_reference, card.unit) }}</strong>
            </div>
            <div class="viz-metric">
              <span>优态参考</span>
              <strong>{{ formatMetric(card.references?.optimal_reference, card.unit) }}</strong>
            </div>
            <div class="viz-metric">
              <span>历史百分位</span>
              <strong>{{ formatPercentile(card.history_stats?.percentile_rank) }}</strong>
            </div>
          </div>

          <div class="timeline-block">
            <div class="timeline-head">
              <span>全程位置条</span>
              <span>{{ compactTimestamp(card.full_timeline?.series_start) }} -> {{ compactTimestamp(card.full_timeline?.series_end) }}</span>
            </div>
            <div class="timeline-bar">
              <div class="timeline-track"></div>
              <div
                v-if="hasFinite(card.full_timeline?.abnormal_start_ratio) && hasFinite(card.full_timeline?.abnormal_end_ratio)"
                class="timeline-window"
                :style="timelineWindowStyle(card)"
              ></div>
              <div
                v-if="hasFinite(card.full_timeline?.current_ratio)"
                class="timeline-current"
                :style="timelineCurrentStyle(card)"
              ></div>
            </div>
            <div class="timeline-foot">
              <span>异常开始：{{ compactTimestamp(card.full_timeline?.abnormal_start) }}</span>
              <span>当前：{{ compactTimestamp(card.latest_timestamp) }}</span>
            </div>
          </div>

          <div class="trend-head">
            <span>近窗趋势图</span>
            <div class="trend-head-actions">
              <span>{{ compactTimestamp(card.recent_trend?.window_start) }} -> {{ compactTimestamp(card.recent_trend?.window_end) }}</span>
              <button class="chart-expand-btn" type="button" @click.stop="openPreview(card)">放大查看</button>
              <button
                v-if="card.tag_id"
                class="chart-link-btn"
                type="button"
                @click.stop="focusOverallCurve('', card.tag_id)"
              >
                切到整体曲线
              </button>
            </div>
          </div>
          <div class="trend-canvas-wrap clickable" @click="openPreview(card)">
            <canvas :ref="setCanvasRef(cardKey(card))"></canvas>
          </div>

          <div class="viz-insights">
            <div class="viz-summary-grid">
              <div v-for="row in summaryRows(card)" :key="row.label" class="viz-summary-item">
                <span>{{ row.label }}</span>
                <strong>{{ row.value }}</strong>
              </div>
            </div>
            <div v-if="referenceNotes(card).length" class="viz-reference-notes">
              <span v-for="note in referenceNotes(card)" :key="note" class="viz-reference-note">{{ note }}</span>
            </div>
            <div v-if="card.recent_trend?.abnormal_start_outside_window" class="viz-window-note">异常开始早于当前图窗。</div>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="viz-overall-view">
      <div class="viz-overall-head">
        <span>当前异常已按整体数据主题分类汇总。</span>
        <button class="chart-link-btn" type="button" @click="focusOverallCurve()">跳到数据曲线总览</button>
      </div>

      <article v-for="group in overallAbnormalGroups" :key="group.key" class="viz-overall-group">
        <div class="viz-overall-group-head">
          <div>
            <strong>{{ group.title }}</strong>
            <p>{{ group.description }}</p>
          </div>
          <span class="viz-overall-count">{{ group.items.length }} 项当前异常</span>
        </div>

        <div class="viz-overall-grid">
          <article v-for="item in group.items" :key="item.tag_id || item.indicator_name" class="viz-overall-item">
            <div class="viz-overall-item-head">
              <div>
                <strong>{{ item.indicator_name }}</strong>
                <p>{{ item.state_desc || '异常' }}</p>
              </div>
              <span class="viz-state-pill">{{ formatSeverity(item.severity_score) }}</span>
            </div>
            <div class="viz-overall-item-meta">
              <span>当前 {{ formatMetric(item.current_value, item.unit) }}</span>
              <span>{{ item.reference_label || '参考值' }} {{ formatMetric(item.reference_value, item.unit) }}</span>
              <span>偏差 {{ formatDelta(item.current_delta_percent) }}</span>
            </div>
            <div class="viz-overall-item-actions">
              <button class="chart-link-btn" type="button" @click="focusOverallCurve(group.key, item.tag_id)">
                切到该分类整体曲线
              </button>
            </div>
          </article>
        </div>
      </article>
    </div>
  </section>

  <section v-else-if="showFallback" class="panel-section viz-fallback">
    <div class="section-title">时间对比可视化</div>
    <div class="viz-note">当前未生成可用的历史对比图。</div>
  </section>

  <ChartLightbox
    :visible="previewVisible"
    :title="previewCard?.indicator_name || '近窗趋势图'"
    :subtitle="previewCard ? `${compactTimestamp(previewCard.recent_trend?.window_start)} -> ${compactTimestamp(previewCard.recent_trend?.window_end)}` : ''"
    @close="closePreview"
  >
    <div class="trend-lightbox-wrap">
      <canvas ref="previewCanvasRef"></canvas>
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

const cards = computed(() => {
  const items = props.result?.visualization_context?.top_indicator_cards
  return Array.isArray(items) ? items.filter((item) => item && typeof item === 'object') : []
})
const activeView = ref('comparison')
const showFallback = computed(() => Boolean(props.result?.reasoning_result || props.result?.report_md || props.result?.report_pdf))
const openCardKey = ref('')
const previewKey = ref('')
const previewCanvasRef = ref(null)
const previewVisible = computed(() => Boolean(previewKey.value))
const canvasRefs = new Map()
const chartRefs = new Map()
let previewChartRef = null

const abnormalTagSet = computed(() => {
  const tags = new Set()
  const abnormalIndicators = Array.isArray(props.result?.abnormal_indicators) ? props.result.abnormal_indicators : []
  abnormalIndicators.forEach((item) => {
    const tag = `${item?.tag_id || ''}`.trim()
    if (tag) tags.add(tag)
  })
  if (tags.size) return tags
  const semanticRows = Array.isArray(props.result?.semantic_data) ? props.result.semantic_data : []
  semanticRows.forEach((item) => {
    const tag = `${item?.tag_id || ''}`.trim()
    const isAbnormal = Number(item?.severity_score || 0) > 0 || Boolean(item?.is_abnormal)
    if (tag && isAbnormal) tags.add(tag)
  })
  return tags
})

const overallAbnormalGroups = computed(() => {
  const rows = Array.isArray(props.result?.visualization_context?.data_curve_overview?.categories)
    ? props.result.visualization_context.data_curve_overview.categories
    : []
  const abnormalTags = abnormalTagSet.value
  return rows
    .map((category) => {
      const items = Array.isArray(category?.items) ? category.items : []
      const filteredItems = items.filter((item) => {
        const tag = `${item?.tag_id || ''}`.trim()
        return abnormalTags.size ? abnormalTags.has(tag) : Number(item?.severity_score || 0) > 0
      })
      if (!filteredItems.length) return null
      return {
        key: category.key,
        title: category.title || category.key || '整体数据',
        description: category.description || '',
        items: filteredItems,
      }
    })
    .filter(Boolean)
})

function cardKey(card = {}) {
  return String(card.tag_id || card.indicator_name || card.rank || Math.random())
}

function setCanvasRef(key) {
  return (el) => {
    if (el) canvasRefs.set(key, el)
    else canvasRefs.delete(key)
  }
}

function toggleCard(card) {
  const key = cardKey(card)
  openCardKey.value = openCardKey.value === key ? '' : key
}

function focusOverallCurve(categoryKey = '', tagId = '') {
  window.dispatchEvent(new CustomEvent('report:focus-curve-category', { detail: { categoryKey, tagId } }))
}

function destroyCharts() {
  chartRefs.forEach((chart) => chart.destroy())
  chartRefs.clear()
  if (previewChartRef) {
    previewChartRef.destroy()
    previewChartRef = null
  }
}

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

function formatPercentile(value) {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(1)}%位` : '-'
}

function formatDelta(value) {
  const n = Number(value)
  return Number.isFinite(n) ? `${n >= 0 ? '+' : ''}${n.toFixed(1)}%` : '-'
}

function formatSeverity(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(3) : '-'
}

function summaryRows(card = {}) {
  const rows = Array.isArray(card.summary_rows) ? card.summary_rows : []
  return rows.filter((row) => row && row.label && row.value)
}

function referenceNotes(card = {}) {
  const notes = card.recent_trend?.chart_display?.reference_notes
  return Array.isArray(notes) ? notes.filter(Boolean) : []
}

function hasFinite(value) {
  return Number.isFinite(Number(value))
}

function timelineWindowStyle(card) {
  const start = Math.max(0, Math.min(100, Number(card.full_timeline?.abnormal_start_ratio || 0) * 100))
  const end = Math.max(start, Math.min(100, Number(card.full_timeline?.abnormal_end_ratio || 0) * 100))
  return { left: `${start}%`, width: `${Math.max(end - start, 1.5)}%` }
}

function timelineCurrentStyle(card) {
  const current = Math.max(0, Math.min(100, Number(card.full_timeline?.current_ratio || 0) * 100))
  return { left: `${current}%` }
}

function createChart(card, canvas) {
  const labels = Array.isArray(card.recent_trend?.timestamps) ? card.recent_trend.timestamps.map((item) => compactTimestamp(item)) : []
  const values = Array.isArray(card.recent_trend?.values) ? card.recent_trend.values.map((item) => Number(item)) : []
  const chartDisplay = card.recent_trend?.chart_display || {}
  const visibleReferenceLines = chartDisplay.visible_reference_lines || {}
  const keyPoints = card.recent_trend?.key_points || {}
  const p10 = Number(visibleReferenceLines.history_p10)
  const p90 = Number(visibleReferenceLines.history_p90)
  const abnormalStartIndex = Number.isFinite(Number(keyPoints.abnormal_start_index)) ? Number(keyPoints.abnormal_start_index) : null
  const lowestIndex = Number.isFinite(Number(keyPoints.lowest_index)) ? Number(keyPoints.lowest_index) : null
  const currentIndex = Number.isFinite(Number(keyPoints.current_index)) ? Number(keyPoints.current_index) : values.length - 1

  const abnormalWindowPlugin = {
    id: `abnormal-window-${cardKey(card)}`,
    beforeDatasetsDraw(chart) {
      if (!Number.isInteger(abnormalStartIndex) || !Number.isInteger(currentIndex) || !chart.chartArea) return
      const { ctx, chartArea, scales } = chart
      const left = scales.x.getPixelForValue(abnormalStartIndex) - 8
      const right = scales.x.getPixelForValue(currentIndex) + 8
      ctx.save()
      ctx.fillStyle = 'rgba(239, 68, 68, 0.10)'
      ctx.fillRect(left, chartArea.top, Math.max(0, right - left), chartArea.bottom - chartArea.top)
      ctx.restore()
    },
  }

  const datasets = []
  if (Number.isFinite(p10) && Number.isFinite(p90) && labels.length) {
    datasets.push({
      label: '历史下界',
      data: labels.map(() => p10),
      borderColor: 'rgba(147,197,253,0.95)',
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false,
      showInLegend: false,
    })
    datasets.push({
      label: '历史区间',
      data: labels.map(() => p90),
      borderColor: 'rgba(147,197,253,0.95)',
      borderDash: [4, 4],
      backgroundColor: 'rgba(59,130,246,0.14)',
      pointRadius: 0,
      fill: '-1',
      showInLegend: true,
    })
  }

  const referenceColors = {
    target_reference: '#dc2626',
    history_baseline: '#0f766e',
  }
  const referenceLabels = {
    target_reference: '目标参考',
    history_baseline: '历史中位',
  }
  Object.keys(referenceLabels).forEach((key) => {
    const value = Number(visibleReferenceLines[key])
    if (!Number.isFinite(value) || !labels.length) return
    datasets.push({
      label: referenceLabels[key],
      data: labels.map(() => value),
      borderColor: referenceColors[key],
      borderDash: [6, 4],
      borderWidth: 1.2,
      pointRadius: 0,
      fill: false,
      showInLegend: true,
    })
  })

  datasets.push({
    label: '当前趋势',
    data: values,
    borderColor: '#2563eb',
    backgroundColor: '#2563eb',
    borderWidth: 2.2,
    tension: 0.22,
    pointRadius: 0,
    pointHoverRadius: 4,
    fill: false,
    showInLegend: true,
  })

  if (Number.isInteger(abnormalStartIndex) && labels[abnormalStartIndex]) {
    datasets.push({
      label: '异常起点',
      data: labels.map((_, index) => (index === abnormalStartIndex ? values[index] : null)),
      type: 'line',
      showLine: false,
      pointRadius: 4,
      pointHoverRadius: 5,
      pointBackgroundColor: '#dc2626',
      pointBorderColor: '#ffffff',
      pointBorderWidth: 1,
      showInLegend: false,
    })
  }

  if (Number.isInteger(lowestIndex) && labels[lowestIndex]) {
    datasets.push({
      label: '最低点',
      data: labels.map((_, index) => (index === lowestIndex ? values[index] : null)),
      type: 'line',
      showLine: false,
      pointRadius: 4.5,
      pointHoverRadius: 5.5,
      pointBackgroundColor: '#b91c1c',
      pointBorderColor: '#ffffff',
      pointBorderWidth: 1,
      showInLegend: false,
    })
  }

  if (Number.isInteger(currentIndex) && labels[currentIndex]) {
    datasets.push({
      label: '当前点',
      data: labels.map((_, index) => (index === currentIndex ? values[index] : null)),
      type: 'line',
      showLine: false,
      pointRadius: 5,
      pointHoverRadius: 6,
      pointBackgroundColor: '#111827',
      pointBorderColor: '#ffffff',
      pointBorderWidth: 1.1,
      showInLegend: false,
      order: 1,
    })
  }

  return new Chart(canvas, {
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
          filter(item, data) {
            const dataset = data.datasets?.[item.datasetIndex]
            return Boolean(dataset?.showInLegend)
          },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = Number(context.raw)
              return `${context.dataset.label}: ${Number.isFinite(value) ? value.toFixed(3) : '-'}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            autoSkip: true,
            maxTicksLimit: 6,
          },
        },
        y: {
          beginAtZero: false,
          grid: { color: 'rgba(148,163,184,0.18)' },
          min: Number.isFinite(Number(chartDisplay.plot_min)) ? Number(chartDisplay.plot_min) : undefined,
          max: Number.isFinite(Number(chartDisplay.plot_max)) ? Number(chartDisplay.plot_max) : undefined,
        },
      },
    },
  })
}

const previewCard = computed(() => cards.value.find((card) => cardKey(card) === previewKey.value) || null)

async function openPreview(card) {
  previewKey.value = cardKey(card)
  await nextTick()
  renderPreviewChart()
}

function closePreview() {
  previewKey.value = ''
  if (previewChartRef) {
    previewChartRef.destroy()
    previewChartRef = null
  }
}

function renderPreviewChart() {
  if (previewChartRef) {
    previewChartRef.destroy()
    previewChartRef = null
  }
  if (!previewCard.value || !previewCanvasRef.value) return
  previewChartRef = createChart(previewCard.value, previewCanvasRef.value)
}

async function refreshCharts() {
  destroyCharts()
  await nextTick()
  cards.value.forEach((card) => {
    const key = cardKey(card)
    if (openCardKey.value !== key) return
    const canvas = canvasRefs.get(key)
    if (!canvas) return
    chartRefs.set(key, createChart(card, canvas))
  })
}

watch(
  cards,
  async (nextCards) => {
    if (nextCards.length) {
      const preferred = cardKey(nextCards[0])
      if (!nextCards.some((card) => cardKey(card) === openCardKey.value)) openCardKey.value = preferred
    } else {
      openCardKey.value = ''
    }
    await refreshCharts()
  },
  { immediate: true, deep: true },
)

watch(
  () => [cards.value.length, overallAbnormalGroups.value.length],
  ([comparisonCount, overallCount]) => {
    if (activeView.value === 'comparison' && !comparisonCount && overallCount) {
      activeView.value = 'overall'
      return
    }
    if (activeView.value === 'overall' && !overallCount && comparisonCount) {
      activeView.value = 'comparison'
    }
  },
  { immediate: true },
)

watch(openCardKey, async () => {
  await refreshCharts()
})

watch(previewCard, async (card) => {
  if (!card) return
  await nextTick()
  renderPreviewChart()
})

onBeforeUnmount(() => {
  destroyCharts()
})
</script>

<style scoped>
.panel-section { padding: 13px; border: 1px solid var(--ui-border); border-radius: 8px; background: var(--ui-surface); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.section-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
.section-title::before { content: ''; width: 4px; height: 12px; border-radius: 999px; background: var(--ui-primary); }
.viz-section { display: grid; gap: 12px; }
.viz-card-list { display: grid; gap: 12px; }
.viz-note { padding: 10px 12px; border: 1px dashed rgba(37, 99, 235, 0.24); border-radius: 8px; background: rgba(37, 99, 235, 0.05); font-size: 12px; line-height: 1.6; color: var(--ui-muted); }
.viz-view-switch { display: flex; flex-wrap: wrap; gap: 8px; }
.viz-view-switch-btn { min-height: 30px; padding: 0 12px; border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 999px; background: #fff; color: var(--ui-text); font-size: 12px; cursor: pointer; }
.viz-view-switch-btn.active { border-color: rgba(37, 99, 235, 0.35); background: rgba(37, 99, 235, 0.08); color: #1d4ed8; font-weight: 700; }
.viz-card { border: 1px solid var(--ui-border); border-radius: 10px; background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.92)); }
.viz-card.active { border-color: rgba(37, 99, 235, 0.28); box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06); }
.viz-card-toggle { width: 100%; padding: 12px 14px; background: none; border: none; text-align: left; cursor: pointer; }
.viz-card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.viz-rank { font-size: 11px; letter-spacing: 0.08em; color: #2563eb; font-weight: 800; }
.viz-card-head strong { display: block; margin-top: 4px; font-size: 14px; line-height: 1.45; color: var(--ui-text); }
.viz-state { display: grid; gap: 6px; justify-items: end; }
.viz-state-pill { display: inline-flex; align-items: center; padding: 5px 8px; border-radius: 999px; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.22); font-size: 11px; color: #b91c1c; }
.viz-state-score { font-size: 11px; color: var(--ui-muted); }
.viz-card-body { display: grid; gap: 12px; padding: 0 14px 14px; }
.viz-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.viz-metric { display: grid; gap: 5px; padding: 10px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.viz-metric span { font-size: 11px; color: var(--ui-muted); }
.viz-metric strong { font-size: 13px; color: var(--ui-text); }
.timeline-block { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.timeline-head, .timeline-foot, .trend-head, .viz-delta-row { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; font-size: 11px; color: var(--ui-muted); }
.trend-head-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.chart-expand-btn { min-height: 28px; padding: 0 10px; border: 1px solid rgba(37,99,235,.18); border-radius: 999px; background: rgba(37,99,235,.08); color: #1d4ed8; font-size: 11px; font-weight: 700; cursor: pointer; }
.chart-link-btn { min-height: 28px; padding: 0 10px; border: 1px solid rgba(15,118,110,.18); border-radius: 999px; background: rgba(15,118,110,.08); color: #0f766e; font-size: 11px; font-weight: 700; cursor: pointer; }
.timeline-bar { position: relative; height: 20px; }
.timeline-track { position: absolute; left: 0; right: 0; top: 7px; height: 6px; border-radius: 999px; background: #cbd5e1; }
.timeline-window { position: absolute; top: 7px; height: 6px; border-radius: 999px; background: #ef4444; }
.timeline-current { position: absolute; top: 2px; width: 14px; height: 14px; border-radius: 999px; background: #111827; transform: translateX(-50%); box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.12); }
.trend-canvas-wrap { height: 260px; padding: 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.trend-canvas-wrap.clickable { cursor: zoom-in; }
.trend-lightbox-wrap { height: min(72vh, 760px); min-height: 420px; padding: 14px; border: 1px solid var(--ui-border); border-radius: 12px; background: #fff; }
.viz-insights { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: linear-gradient(180deg, #fff, #f8fafc); }
.viz-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.viz-summary-item { display: grid; gap: 4px; padding: 10px; border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 8px; background: rgba(248, 250, 252, 0.92); }
.viz-summary-item span { font-size: 11px; color: var(--ui-muted); }
.viz-summary-item strong { font-size: 13px; color: var(--ui-text); }
.viz-reference-notes { display: flex; flex-wrap: wrap; gap: 8px; }
.viz-reference-note { display: inline-flex; align-items: center; padding: 5px 8px; border-radius: 999px; background: rgba(15, 23, 42, 0.04); border: 1px solid rgba(148, 163, 184, 0.22); font-size: 11px; color: #475569; }
.viz-window-note { font-size: 11px; color: #b91c1c; }
.viz-overall-view { display: grid; gap: 12px; }
.viz-overall-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 10px 12px; border: 1px solid var(--ui-border); border-radius: 8px; background: rgba(248,250,252,.85); color: var(--ui-muted); font-size: 12px; }
.viz-overall-group { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--ui-border); border-radius: 10px; background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92)); }
.viz-overall-group-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.viz-overall-group-head strong { font-size: 14px; color: var(--ui-text); }
.viz-overall-group-head p { margin: 4px 0 0; font-size: 12px; color: var(--ui-muted); line-height: 1.55; }
.viz-overall-count { display: inline-flex; align-items: center; padding: 4px 8px; border-radius: 999px; background: rgba(239,68,68,.08); color: #b91c1c; font-size: 11px; }
.viz-overall-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.viz-overall-item { display: grid; gap: 10px; padding: 12px; border: 1px solid rgba(148,163,184,.18); border-radius: 8px; background: #fff; }
.viz-overall-item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.viz-overall-item-head strong { font-size: 13px; color: var(--ui-text); }
.viz-overall-item-head p { margin: 4px 0 0; font-size: 11px; color: var(--ui-muted); }
.viz-overall-item-meta { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: var(--ui-muted); }
.viz-overall-item-actions { display: flex; justify-content: flex-end; }
.viz-fallback { display: grid; gap: 6px; }
@media (max-width: 1080px) {
  .viz-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .viz-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .viz-overall-grid { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .viz-metrics { grid-template-columns: 1fr; }
  .viz-summary-grid { grid-template-columns: 1fr; }
  .trend-canvas-wrap { height: 220px; }
}
</style>
