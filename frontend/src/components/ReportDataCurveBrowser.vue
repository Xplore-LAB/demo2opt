<template>
  <section v-if="overviewReady" ref="sectionRef" class="panel-section curve-browser-section">
    <div class="section-title">数据曲线总览</div>
    <div class="curve-browser-note">
      先按业务主题看全量曲线，再展开单个指标查看历史走势。这一层只做整体印象建立，不直接用于根因确认。
    </div>

    <div class="curve-browser-meta">
      <div class="curve-browser-meta-card">
        <span>分类数</span>
        <strong>{{ overview.category_count }}</strong>
      </div>
      <div class="curve-browser-meta-card">
        <span>指标数</span>
        <strong>{{ overview.indicator_count }}</strong>
      </div>
      <div class="curve-browser-meta-card wide">
        <span>时间范围</span>
        <strong>{{ compactTimestamp(overview.time_range_start) }} -> {{ compactTimestamp(overview.time_range_end) }}</strong>
      </div>
    </div>

    <div class="curve-browser-tabs" role="tablist" aria-label="数据曲线分类">
      <button
        v-for="category in categories"
        :key="category.key"
        class="curve-browser-tab"
        :class="{ active: category.key === selectedCategoryKey }"
        type="button"
        @click="selectCategory(category.key)"
      >
        <span>{{ category.title }}</span>
        <small>{{ category.indicator_count }} 项</small>
        <em v-if="category.abnormal_count">{{ category.abnormal_count }} 异常</em>
      </button>
    </div>

    <div v-if="selectedCategory" class="curve-browser-category">
      <div class="curve-browser-category-head">
        <div>
          <strong>{{ selectedCategory.title }}</strong>
          <p>{{ selectedCategory.description }}</p>
        </div>
        <div class="curve-browser-category-summary">
          <span>{{ selectedCategory.indicator_count }} 条曲线</span>
          <span v-if="selectedCategory.abnormal_count">{{ selectedCategory.abnormal_count }} 条异常</span>
          <span v-if="selectedCategoryLoadContextItems.length">叠加 {{ selectedCategoryLoadContextItems.length }} 条负荷参照</span>
        </div>
      </div>
      <div v-if="selectedCategoryLoadContextItems.length" class="curve-browser-load-note">
        虚线表示负荷参照曲线，右侧坐标轴显示相对各自参考值的偏差百分比，便于辅助判断该指标与装置负荷的联动关系。
      </div>

      <article
        v-for="item in selectedCategory.items"
        :key="itemKey(item)"
        class="curve-browser-item"
        :class="{ active: isOpen(item) }"
      >
        <button class="curve-browser-item-toggle" type="button" @click="toggleItem(item)">
          <div class="curve-browser-item-copy">
            <div class="curve-browser-item-title">
              <strong>{{ item.indicator_name }}</strong>
              <span class="curve-browser-state" :class="toneClass(item)">{{ item.state_desc || '未见异常' }}</span>
            </div>
            <div class="curve-browser-item-meta">
              <span>当前 {{ formatMetric(item.current_value, item.unit) }}</span>
              <span>{{ item.reference_label || '参考' }} {{ formatMetric(item.reference_value, item.unit) }}</span>
              <span>{{ item.display_point_count }}/{{ item.point_count }} 点</span>
            </div>
          </div>
          <div class="curve-browser-item-side" :class="toneClass(item)">
            <div class="curve-browser-item-delta">{{ formatDelta(item.current_delta_percent) }}</div>
            <div class="curve-browser-item-toggle-text">{{ isOpen(item) ? '收起' : '展开曲线' }}</div>
          </div>
        </button>

        <div v-if="isOpen(item)" class="curve-browser-item-body">
          <div class="curve-browser-stream-strip" :class="{ complete: streamState(item).complete }">
            <div class="curve-browser-stream-copy">
              <span class="stream-dot"></span>
              <strong>{{ streamState(item).label }}</strong>
              <span>{{ streamState(item).visible }}/{{ streamState(item).total }} 点</span>
            </div>
            <div class="curve-browser-stream-meter" aria-hidden="true">
              <span :style="{ width: streamState(item).progress }"></span>
            </div>
            <button class="stream-replay-btn" type="button" @click.stop="restartStream(item)">重播刷点</button>
          </div>
          <div class="curve-browser-chart-head">
            <div class="curve-browser-chart-head-copy">
              <span>{{ compactTimestamp(item.time_range_start) }} -> {{ compactTimestamp(item.time_range_end) }}</span>
              <span v-if="item.abnormal_start">异常起点：{{ compactTimestamp(item.abnormal_start) }}</span>
              <span class="curve-browser-zoom-label">{{ zoomRangeLabel(item) }}</span>
            </div>
            <div class="curve-browser-chart-actions">
              <button
                v-if="isZoomed(item)"
                class="chart-reset-btn"
                type="button"
                @click.stop="resetTimeZoom(item)"
              >
                恢复全时段
              </button>
              <button class="chart-expand-btn" type="button" @click="openPreview(item)">放大查看</button>
            </div>
          </div>
          <div
            class="curve-browser-chart-wrap clickable"
            @click="openPreview(item)"
            @wheel.prevent.stop="handleChartWheel($event, item)"
          >
            <canvas :ref="setCanvasRef(itemKey(item))"></canvas>
          </div>
          <div class="curve-browser-summary-grid">
            <div class="curve-browser-summary-item">
              <span>最小值</span>
              <strong>{{ formatMetric(item.summary?.min, item.unit) }}</strong>
            </div>
            <div class="curve-browser-summary-item">
              <span>中位值</span>
              <strong>{{ formatMetric(item.summary?.median, item.unit) }}</strong>
            </div>
            <div class="curve-browser-summary-item">
              <span>最大值</span>
              <strong>{{ formatMetric(item.summary?.max, item.unit) }}</strong>
            </div>
            <div class="curve-browser-summary-item">
              <span>{{ item.reference_label || '参考值' }}</span>
              <strong>{{ formatMetric(item.reference_value, item.unit) }}</strong>
            </div>
          </div>
          <div v-if="item.chart?.display?.reference_note" class="curve-browser-reference-note">
            {{ item.chart.display.reference_note }}
          </div>
        </div>
      </article>
    </div>
  </section>

  <section v-else-if="showFallback" class="panel-section curve-browser-fallback">
    <div class="section-title">数据曲线总览</div>
    <div class="curve-browser-note">当前还没有可用的全量历史曲线数据。</div>
  </section>

  <ChartLightbox
    :visible="previewVisible"
    :title="previewItem?.indicator_name || '数据曲线放大预览'"
    :subtitle="previewItem ? `${compactTimestamp(previewItem.time_range_start)} -> ${compactTimestamp(previewItem.time_range_end)}` : ''"
    @close="closePreview"
  >
    <div class="curve-browser-lightbox-wrap">
      <canvas ref="previewCanvasRef"></canvas>
    </div>
  </ChartLightbox>
</template>

<script setup>
import { Chart, CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip } from 'chart.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ChartLightbox from './ChartLightbox.vue'

Chart.register(CategoryScale, LinearScale, LineController, LineElement, PointElement, Filler, Legend, Tooltip)

const props = defineProps({
  result: { type: Object, required: true },
})

const selectedCategoryKey = ref('')
const openItemKeys = ref([])
const previewItemKey = ref('')
const previewCanvasRef = ref(null)
const sectionRef = ref(null)
const streamStates = ref({})
const zoomStates = ref({})
const canvasRefs = new Map()
const chartRefs = new Map()
const streamTimers = new Map()
let previewChartRef = null

const STREAM_FRAME_MS = 90
const STREAM_MIN_CHUNK = 3
const ZOOM_MIN_POINTS = 8

const overview = computed(() => {
  const raw = props.result?.visualization_context?.data_curve_overview
  return raw && typeof raw === 'object' ? raw : {}
})

const categories = computed(() => {
  const rows = Array.isArray(overview.value.categories) ? overview.value.categories : []
  return rows.filter((item) => item && item.key && Array.isArray(item.items) && item.items.length)
})

const selectedCategory = computed(() => categories.value.find((item) => item.key === selectedCategoryKey.value) || categories.value[0] || null)
const selectedCategoryLoadContextItems = computed(() => Array.isArray(selectedCategory.value?.load_context_items) ? selectedCategory.value.load_context_items : [])
const overviewReady = computed(() => Boolean(categories.value.length))
const showFallback = computed(() => Boolean(props.result?.reasoning_result || props.result?.report_md || props.result?.report_pdf))
const previewItem = computed(() => {
  const rows = categories.value.flatMap((category) => Array.isArray(category.items) ? category.items : [])
  return rows.find((item) => itemKey(item) === previewItemKey.value) || null
})
const previewVisible = computed(() => Boolean(previewItem.value))

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
  if (!Number.isFinite(n)) return '参考待补齐'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function itemKey(item = {}) {
  return String(item.tag_id || item.indicator_name || Math.random())
}

function toneClass(item = {}) {
  const severity = Number(item.severity_score || 0)
  if (severity >= 1) return 'danger'
  if (severity > 0) return 'warn'
  return 'normal'
}

function getCategoryForItem(item = {}) {
  const key = itemKey(item)
  return categories.value.find((category) => Array.isArray(category.items) && category.items.some((entry) => itemKey(entry) === key)) || null
}

function getLoadOverlayItems(item = {}) {
  const category = getCategoryForItem(item)
  return Array.isArray(category?.load_context_items) ? category.load_context_items : []
}

function buildRelativePercentMap(sourceItem = {}) {
  const chart = sourceItem.chart || {}
  const timestamps = Array.isArray(chart.timestamps) ? chart.timestamps : []
  const values = Array.isArray(chart.values) ? chart.values : []
  const reference = Number(sourceItem.reference_value)
  const fallbackMedian = Number(sourceItem.summary?.median)
  const base = Number.isFinite(reference) && Math.abs(reference) > 1e-6
    ? reference
    : (Number.isFinite(fallbackMedian) && Math.abs(fallbackMedian) > 1e-6 ? fallbackMedian : null)
  if (!base) return new Map()
  const mapped = new Map()
  for (let index = 0; index < Math.min(timestamps.length, values.length); index += 1) {
    const value = Number(values[index])
    if (!Number.isFinite(value)) continue
    mapped.set(String(timestamps[index]), ((value - base) / Math.abs(base)) * 100)
  }
  return mapped
}

function selectCategory(key) {
  selectedCategoryKey.value = key
  openItemKeys.value = []
}

async function focusCurveCategory(detail = {}) {
  const nextCategoryKey = `${detail?.categoryKey || ''}`.trim()
  const nextTagId = `${detail?.tagId || ''}`.trim()

  if (nextCategoryKey && categories.value.some((item) => item.key === nextCategoryKey)) {
    selectedCategoryKey.value = nextCategoryKey
    openItemKeys.value = []
  }

  await nextTick()

  if (nextTagId) {
    const targetItem = (selectedCategory.value?.items || []).find((item) => `${item?.tag_id || ''}`.trim() === nextTagId)
    if (targetItem) {
      openItemKeys.value = [itemKey(targetItem)]
      await nextTick()
    }
  }

  sectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function isOpen(item) {
  return openItemKeys.value.includes(itemKey(item))
}

function toggleItem(item) {
  const key = itemKey(item)
  if (isOpen(item)) {
    openItemKeys.value = openItemKeys.value.filter((value) => value !== key)
    destroyChart(key)
    return
  }
  openItemKeys.value = [...openItemKeys.value, key]
}

function setCanvasRef(key) {
  return (el) => {
    if (el) canvasRefs.set(key, el)
    else canvasRefs.delete(key)
  }
}

function destroyChart(key) {
  const chart = chartRefs.get(key)
  if (chart) {
    chart.destroy()
    chartRefs.delete(key)
  }
  stopStream(key)
}

function destroyAllCharts() {
  streamTimers.forEach((timer) => clearTimeout(timer))
  streamTimers.clear()
  chartRefs.forEach((chart) => chart.destroy())
  chartRefs.clear()
  if (previewChartRef) {
    previewChartRef.destroy()
    previewChartRef = null
  }
}

function chartPointCount(item = {}) {
  const timestamps = item.chart?.timestamps
  const values = item.chart?.values
  return Math.min(Array.isArray(timestamps) ? timestamps.length : 0, Array.isArray(values) ? values.length : 0)
}

function getZoomState(item = {}) {
  const key = itemKey(item)
  const total = chartPointCount(item)
  const saved = zoomStates.value[key] || {}
  const start = Math.max(0, Math.min(total - 1, Number.isFinite(Number(saved.start)) ? Number(saved.start) : 0))
  const fallbackEnd = total
  const end = Math.max(start + 1, Math.min(total, Number.isFinite(Number(saved.end)) ? Number(saved.end) : fallbackEnd))
  return { start, end, total }
}

function isZoomed(item = {}) {
  const state = getZoomState(item)
  return state.total > 0 && (state.start > 0 || state.end < state.total)
}

function zoomRangeLabel(item = {}) {
  const state = getZoomState(item)
  if (!state.total) return '滚轮缩放时间尺度'
  if (!isZoomed(item)) return '滚轮缩放时间尺度'
  const timestamps = Array.isArray(item.chart?.timestamps) ? item.chart.timestamps : []
  const startLabel = compactTimestamp(timestamps[state.start])
  const endLabel = compactTimestamp(timestamps[state.end - 1])
  return `当前窗口 ${startLabel} -> ${endLabel}，${state.end - state.start}/${state.total} 点`
}

function setZoomState(key, patch) {
  const current = zoomStates.value[key] || {}
  zoomStates.value = {
    ...zoomStates.value,
    [key]: { ...current, ...patch },
  }
}

function applyTimeZoom(item = {}) {
  const key = itemKey(item)
  const chart = chartRefs.get(key)
  if (!chart) return
  const { start, end, total } = getZoomState(item)
  const xScale = chart.options.scales?.x
  if (!xScale) return
  if (!total || (start <= 0 && end >= total)) {
    delete xScale.min
    delete xScale.max
  } else {
    xScale.min = start
    xScale.max = end - 1
  }
  chart.update('none')
}

function resetTimeZoom(item = {}) {
  const key = itemKey(item)
  const total = chartPointCount(item)
  setZoomState(key, { start: 0, end: total })
  applyTimeZoom(item)
}

function handleChartWheel(event, item = {}) {
  const total = chartPointCount(item)
  if (total <= ZOOM_MIN_POINTS) return
  const key = itemKey(item)
  const current = getZoomState(item)
  const currentSize = Math.max(1, current.end - current.start)
  const rect = event.currentTarget?.getBoundingClientRect()
  const ratio = rect?.width ? Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) : 0.5
  const center = current.start + ratio * Math.max(1, currentSize - 1)
  const zoomingIn = event.deltaY < 0
  const targetSize = zoomingIn
    ? Math.max(ZOOM_MIN_POINTS, Math.round(currentSize * 0.72))
    : Math.min(total, Math.round(currentSize * 1.35))

  let nextStart = Math.round(center - targetSize * ratio)
  let nextEnd = nextStart + targetSize
  if (nextStart < 0) {
    nextEnd -= nextStart
    nextStart = 0
  }
  if (nextEnd > total) {
    nextStart -= nextEnd - total
    nextEnd = total
  }
  nextStart = Math.max(0, nextStart)
  nextEnd = Math.min(total, Math.max(nextStart + 1, nextEnd))
  setZoomState(key, { start: nextStart, end: nextEnd })
  applyTimeZoom(item)
}

function streamState(item = {}) {
  const key = itemKey(item)
  const total = chartPointCount(item)
  const current = streamStates.value[key]
  const visible = Math.max(0, Math.min(total, Number(current?.visible || 0)))
  const complete = total > 0 && visible >= total
  return {
    visible,
    total,
    complete,
    progress: total ? `${Math.round((visible / total) * 100)}%` : '0%',
    label: complete ? '实时动态显示完成' : '模拟加载中，正在刷入采样点',
  }
}

function setStreamState(key, patch) {
  const current = streamStates.value[key] || {}
  streamStates.value = {
    ...streamStates.value,
    [key]: { ...current, ...patch },
  }
}

function stopStream(key) {
  const timer = streamTimers.get(key)
  if (timer) clearTimeout(timer)
  streamTimers.delete(key)
}

function visibleSeries(values = [], visibleCount = values.length) {
  return values.map((value, index) => (index < visibleCount ? value : null))
}

function updateChartStreamData(item = {}) {
  const key = itemKey(item)
  const chart = chartRefs.get(key)
  if (!chart) return
  const state = streamState(item)
  const visibleCount = state.visible
  const chartPayload = item.chart || {}
  const values = Array.isArray(chartPayload.values) ? chartPayload.values.map((value) => Number(value)) : []
  const timestamps = Array.isArray(chartPayload.timestamps) ? chartPayload.timestamps : []
  const labels = timestamps.map((value) => compactTimestamp(value))
  const currentVisibleIndex = visibleCount > 0 ? visibleCount - 1 : -1

  chart.data.datasets.forEach((dataset) => {
    if (dataset.streamRole === 'reference') {
      dataset.data = labels.map((_, index) => (index < visibleCount ? dataset.streamReferenceValue : null))
      return
    }
    if (dataset.streamRole === 'load') {
      dataset.data = visibleSeries(dataset.streamFullData || [], visibleCount)
      return
    }
    if (dataset.streamRole === 'main') {
      dataset.data = visibleSeries(values, visibleCount)
      return
    }
    if (dataset.streamRole === 'current') {
      dataset.data = labels.map((_, index) => (index === currentVisibleIndex ? values[index] : null))
    }
  })
  chart.update('none')
}

function startStream(item = {}, { restart = false } = {}) {
  const key = itemKey(item)
  const total = chartPointCount(item)
  if (!total) return
  stopStream(key)
  const existing = streamStates.value[key]
  if (!restart && existing?.visible >= total) {
    updateChartStreamData(item)
    return
  }

  const initialVisible = restart ? 0 : Math.max(0, Math.min(total, Number(existing?.visible || 0)))
  setStreamState(key, { visible: initialVisible, total })
  updateChartStreamData(item)

  const chunkSize = Math.max(STREAM_MIN_CHUNK, Math.ceil(total / 28))
  const tick = () => {
    const state = streamState(item)
    if (state.visible >= total) {
      setStreamState(key, { visible: total, total })
      updateChartStreamData(item)
      streamTimers.delete(key)
      return
    }
    setStreamState(key, { visible: Math.min(total, state.visible + chunkSize), total })
    updateChartStreamData(item)
    streamTimers.set(key, window.setTimeout(tick, STREAM_FRAME_MS))
  }

  streamTimers.set(key, window.setTimeout(tick, STREAM_FRAME_MS))
}

function restartStream(item) {
  startStream(item, { restart: true })
}

function createChart(item, canvas) {
  const key = itemKey(item)
  if (!canvas) return null

  const chartPayload = item.chart || {}
  const labels = Array.isArray(chartPayload.timestamps) ? chartPayload.timestamps.map((value) => compactTimestamp(value)) : []
  const values = Array.isArray(chartPayload.values) ? chartPayload.values.map((value) => Number(value)) : []
  const visibleCount = streamState(item).visible || 0
  const display = chartPayload.display || {}
  const currentIndex = visibleCount > 0 ? Math.max(0, Math.min(values.length - 1, visibleCount - 1)) : null
  const abnormalStartIndex = Number.isInteger(Number(chartPayload.abnormal_start_index)) ? Number(chartPayload.abnormal_start_index) : null
  const visibleReferenceLine = Number(display.visible_reference_line)

  const abnormalWindowPlugin = {
    id: `curve-browser-window-${key}`,
    beforeDatasetsDraw(chart) {
      if (!Number.isInteger(abnormalStartIndex) || !Number.isInteger(currentIndex) || !chart.chartArea) return
      const { ctx, chartArea, scales } = chart
      const left = scales.x.getPixelForValue(abnormalStartIndex) - 8
      const right = scales.x.getPixelForValue(currentIndex) + 8
      ctx.save()
      ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'
      ctx.fillRect(left, chartArea.top, Math.max(0, right - left), chartArea.bottom - chartArea.top)
      ctx.restore()
    },
  }

  const datasets = []
  const loadOverlayItems = getLoadOverlayItems(item)
  if (Number.isFinite(visibleReferenceLine) && labels.length) {
    datasets.push({
      label: item.reference_label || '参考线',
      data: labels.map(() => visibleReferenceLine),
      borderColor: '#dc2626',
      borderDash: [6, 4],
      borderWidth: 1.2,
      pointRadius: 0,
      fill: false,
      streamRole: 'reference',
      streamReferenceValue: visibleReferenceLine,
    })
  }
  loadOverlayItems.forEach((overlayItem, overlayIndex) => {
    const relativeMap = buildRelativePercentMap(overlayItem)
    if (!relativeMap.size) return
    const overlayValues = (Array.isArray(chartPayload.timestamps) ? chartPayload.timestamps : []).map((timestamp) => {
      const value = relativeMap.get(String(timestamp))
      return Number.isFinite(value) ? value : null
    })
    if (!overlayValues.some((value) => Number.isFinite(value))) return
    datasets.push({
      label: `负荷参照·${overlayItem.indicator_name || `负荷${overlayIndex + 1}`}`,
      data: visibleSeries(overlayValues, visibleCount),
      borderColor: '#0f172a',
      backgroundColor: '#0f172a',
      borderWidth: 1.5,
      borderDash: [6, 4],
      tension: 0.18,
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: false,
      yAxisID: 'yLoad',
      streamRole: 'load',
      streamFullData: overlayValues,
    })
  })
  datasets.push({
    label: item.indicator_name,
    data: visibleSeries(values, visibleCount),
    borderColor: '#2563eb',
    backgroundColor: '#2563eb',
    borderWidth: 2.1,
    tension: 0.18,
    pointRadius(context) {
      const currentVisible = streamState(item).visible
      const index = context.dataIndex
      return index >= Math.max(0, currentVisible - 4) && index < currentVisible ? 2.4 : 0
    },
    pointHoverRadius: 4,
    fill: false,
    streamRole: 'main',
  })
  if (Number.isInteger(currentIndex) && labels[currentIndex]) {
    datasets.push({
      label: '实时刷入点',
      data: labels.map((_, index) => (index === currentIndex ? values[index] : null)),
      type: 'line',
      showLine: false,
      pointRadius: 4.5,
      pointHoverRadius: 5.5,
      pointBackgroundColor: '#0f172a',
      pointBorderColor: '#ffffff',
      pointBorderWidth: 1,
      streamRole: 'current',
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
        },
        tooltip: {
          callbacks: {
            label(context) {
              const raw = Number(context.raw)
              const suffix = context.dataset?.yAxisID === 'yLoad' ? '%' : (item.unit ? ` ${item.unit}` : '')
              return `${context.dataset.label}: ${Number.isFinite(raw) ? raw.toFixed(2) : '-'}${suffix}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { autoSkip: true, maxTicksLimit: 7 },
          min: isZoomed(item) ? getZoomState(item).start : undefined,
          max: isZoomed(item) ? getZoomState(item).end - 1 : undefined,
        },
        y: {
          grid: { color: 'rgba(148,163,184,0.16)' },
          min: Number.isFinite(Number(display.plot_min)) ? Number(display.plot_min) : undefined,
          max: Number.isFinite(Number(display.plot_max)) ? Number(display.plot_max) : undefined,
        },
        yLoad: {
          position: 'right',
          display: Boolean(loadOverlayItems.length),
          grid: { drawOnChartArea: false },
          ticks: {
            callback(value) {
              const raw = Number(value)
              return Number.isFinite(raw) ? `${raw.toFixed(0)}%` : ''
            },
          },
          title: {
            display: Boolean(loadOverlayItems.length),
            text: '负荷偏差 (%)',
          },
        },
      },
    },
  })
}

function buildChart(item) {
  const key = itemKey(item)
  const canvas = canvasRefs.get(key)
  if (!canvas) return
  destroyChart(key)
  const total = chartPointCount(item)
  if (!streamStates.value[key]) setStreamState(key, { visible: 0, total })
  const chart = createChart(item, canvas)
  if (chart) chartRefs.set(key, chart)
  startStream(item)
}

async function openPreview(item) {
  previewItemKey.value = itemKey(item)
  await nextTick()
  renderPreviewChart()
}

function closePreview() {
  previewItemKey.value = ''
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
  if (!previewItem.value || !previewCanvasRef.value) return
  previewChartRef = createChart(previewItem.value, previewCanvasRef.value)
}

async function rebuildOpenCharts() {
  const items = selectedCategory.value?.items || []
  const openItems = items.filter((item) => isOpen(item))
  if (!openItems.length) {
    destroyAllCharts()
    return
  }
  await nextTick()
  const visibleKeys = new Set(openItems.map((item) => itemKey(item)))
  Array.from(chartRefs.keys()).forEach((key) => {
    if (!visibleKeys.has(key)) destroyChart(key)
  })
  openItems.forEach((item) => buildChart(item))
}

watch(
  categories,
  (rows) => {
    if (!rows.length) {
      selectedCategoryKey.value = ''
      openItemKeys.value = []
      destroyAllCharts()
      return
    }
    if (!rows.some((item) => item.key === selectedCategoryKey.value)) {
      selectedCategoryKey.value = rows[0].key
      openItemKeys.value = []
    }
  },
  { immediate: true, deep: true },
)

watch(
  [selectedCategory, openItemKeys],
  async () => {
    await rebuildOpenCharts()
  },
  { deep: true },
)

watch(previewItem, async (item) => {
  if (!item) return
  await nextTick()
  renderPreviewChart()
})

function handleFocusCurveCategory(event) {
  focusCurveCategory(event?.detail || {})
}

onMounted(() => {
  window.addEventListener('report:focus-curve-category', handleFocusCurveCategory)
})

onBeforeUnmount(() => {
  window.removeEventListener('report:focus-curve-category', handleFocusCurveCategory)
  destroyAllCharts()
})
</script>

<style scoped>
.panel-section { padding: 13px; border: 1px solid var(--ui-border); border-radius: 8px; background: var(--ui-surface); }
.section-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; font-weight: 700; }
.section-title::before { content: ''; width: 4px; height: 12px; border-radius: 999px; background: var(--ui-primary); }
.curve-browser-section { display: grid; gap: 12px; }
.curve-browser-note { padding: 10px 12px; border: 1px dashed rgba(15, 118, 110, 0.22); border-radius: 8px; background: rgba(15, 118, 110, 0.05); font-size: 12px; line-height: 1.6; color: var(--ui-muted); }
.curve-browser-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.curve-browser-meta-card { display: grid; gap: 4px; padding: 10px; border: 1px solid var(--ui-border); border-radius: 8px; background: #fff; }
.curve-browser-meta-card.wide { grid-column: span 1; }
.curve-browser-meta-card span { font-size: 11px; color: var(--ui-muted); }
.curve-browser-meta-card strong { font-size: 13px; color: var(--ui-text); }
.curve-browser-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.curve-browser-tab { display: inline-flex; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid var(--ui-border); border-radius: 999px; background: #fff; color: var(--ui-text); cursor: pointer; transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease; }
.curve-browser-tab small { color: var(--ui-muted); }
.curve-browser-tab em { padding: 2px 6px; border-radius: 999px; background: rgba(239, 68, 68, 0.1); color: #b91c1c; font-size: 11px; font-style: normal; }
.curve-browser-tab.active { border-color: rgba(37, 99, 235, 0.35); background: rgba(37, 99, 235, 0.07); box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08); }
.curve-browser-category { display: grid; gap: 10px; }
.curve-browser-category-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 4px 2px; }
.curve-browser-category-head strong { font-size: 14px; color: var(--ui-text); }
.curve-browser-category-head p { margin: 4px 0 0; font-size: 12px; line-height: 1.5; color: var(--ui-muted); }
.curve-browser-category-summary { display: flex; flex-wrap: wrap; gap: 8px; color: var(--ui-muted); font-size: 12px; }
.curve-browser-load-note { padding: 8px 10px; border-radius: 8px; background: rgba(15, 23, 42, 0.05); color: #475569; font-size: 12px; line-height: 1.55; }
.curve-browser-item { border: 1px solid var(--ui-border); border-radius: 10px; background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.92)); overflow: hidden; }
.curve-browser-item.active { border-color: rgba(37, 99, 235, 0.28); box-shadow: 0 14px 30px rgba(15, 23, 42, 0.06); }
.curve-browser-item-toggle { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 12px 14px; border: 0; background: transparent; text-align: left; cursor: pointer; }
.curve-browser-item-copy { min-width: 0; display: grid; gap: 6px; }
.curve-browser-item-title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.curve-browser-item-title strong { font-size: 13px; color: var(--ui-text); }
.curve-browser-state { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 999px; font-size: 11px; }
.curve-browser-state.normal { background: rgba(15, 118, 110, 0.1); color: #0f766e; }
.curve-browser-state.warn { background: rgba(217, 119, 6, 0.12); color: #b45309; }
.curve-browser-state.danger { background: rgba(239, 68, 68, 0.1); color: #b91c1c; }
.curve-browser-item-meta { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: var(--ui-muted); }
.curve-browser-item-side { display: grid; justify-items: end; gap: 4px; }
.curve-browser-item-delta { font-size: 13px; font-weight: 700; }
.curve-browser-item-side.normal .curve-browser-item-delta { color: #0f766e; }
.curve-browser-item-side.warn .curve-browser-item-delta { color: #b45309; }
.curve-browser-item-side.danger .curve-browser-item-delta { color: #b91c1c; }
.curve-browser-item-toggle-text { font-size: 11px; color: var(--ui-muted); }
.curve-browser-item-body { display: grid; gap: 10px; padding: 0 14px 14px; }
.curve-browser-chart-head { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; color: var(--ui-muted); font-size: 12px; }
.curve-browser-chart-head-copy { display: flex; gap: 10px; flex-wrap: wrap; min-width: 0; }
.curve-browser-chart-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.curve-browser-zoom-label { color: #0f766e; font-weight: 700; }
.chart-expand-btn { min-height: 28px; padding: 0 10px; border: 1px solid rgba(37,99,235,.18); border-radius: 999px; background: rgba(37,99,235,.08); color: #1d4ed8; font-size: 11px; font-weight: 700; cursor: pointer; }
.chart-reset-btn { min-height: 28px; padding: 0 10px; border: 1px solid rgba(15,118,110,.18); border-radius: 999px; background: rgba(15,118,110,.08); color: #0f766e; font-size: 11px; font-weight: 700; cursor: pointer; }
.curve-browser-stream-strip { display: grid; grid-template-columns: minmax(180px, auto) minmax(120px, 1fr) auto; gap: 10px; align-items: center; padding: 9px 10px; border: 1px solid rgba(37, 99, 235, 0.16); border-radius: 8px; background: rgba(37, 99, 235, 0.05); }
.curve-browser-stream-strip.complete { border-color: rgba(15, 118, 110, 0.18); background: rgba(15, 118, 110, 0.05); }
.curve-browser-stream-copy { display: inline-flex; align-items: center; gap: 8px; min-width: 0; color: #475569; font-size: 11px; }
.curve-browser-stream-copy strong { color: var(--ui-text); font-size: 12px; white-space: nowrap; }
.stream-dot { width: 8px; height: 8px; border-radius: 999px; background: #2563eb; box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.12); animation: stream-pulse 1.2s ease-in-out infinite; }
.curve-browser-stream-strip.complete .stream-dot { background: #0f766e; box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.12); animation: none; }
.curve-browser-stream-meter { position: relative; height: 6px; overflow: hidden; border-radius: 999px; background: rgba(148, 163, 184, 0.22); }
.curve-browser-stream-meter span { position: absolute; inset: 0 auto 0 0; border-radius: inherit; background: linear-gradient(90deg, #2563eb, #0f766e); transition: width 120ms ease; }
.stream-replay-btn { min-height: 26px; padding: 0 9px; border: 1px solid rgba(15, 118, 110, 0.18); border-radius: 999px; background: rgba(15, 118, 110, 0.08); color: #0f766e; font-size: 11px; font-weight: 700; cursor: pointer; }
.curve-browser-chart-wrap { height: 250px; border: 1px solid rgba(148, 163, 184, 0.16); border-radius: 10px; background: #fff; padding: 10px; }
.curve-browser-chart-wrap.clickable { cursor: zoom-in; }
.curve-browser-chart-wrap:hover { border-color: rgba(15, 118, 110, 0.28); box-shadow: inset 0 0 0 1px rgba(15, 118, 110, 0.08); }
.curve-browser-lightbox-wrap { height: min(72vh, 760px); min-height: 420px; padding: 14px; border: 1px solid var(--ui-border); border-radius: 12px; background: #fff; }
.curve-browser-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.curve-browser-summary-item { display: grid; gap: 4px; padding: 10px; border: 1px solid var(--ui-border); border-radius: 8px; background: rgba(255,255,255,0.92); }
.curve-browser-summary-item span { font-size: 11px; color: var(--ui-muted); }
.curve-browser-summary-item strong { font-size: 12px; color: var(--ui-text); }
.curve-browser-reference-note { padding: 8px 10px; border-radius: 8px; background: rgba(148, 163, 184, 0.1); color: #475569; font-size: 12px; line-height: 1.5; }

@media (max-width: 900px) {
  .curve-browser-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .curve-browser-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .curve-browser-meta { grid-template-columns: 1fr; }
  .curve-browser-item-toggle { grid-template-columns: 1fr; }
  .curve-browser-item-side { justify-items: start; }
  .curve-browser-summary-grid { grid-template-columns: 1fr; }
  .curve-browser-stream-strip { grid-template-columns: 1fr; }
  .curve-browser-stream-copy strong { white-space: normal; }
  .curve-browser-chart-wrap { height: 220px; }
}

@keyframes stream-pulse {
  0%, 100% { transform: scale(1); opacity: 0.88; }
  50% { transform: scale(1.35); opacity: 1; }
}
</style>
