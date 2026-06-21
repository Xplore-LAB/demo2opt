<template>
  <div class="pi-analysis dcs-page">
    <header class="dcs-topbar">
      <div class="topbar-title-block">
        <router-link to="/" class="back-btn" aria-label="返回首页">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </router-link>
        <div>
          <h1>空分装置运行分析 Demo</h1>
          <div class="topbar-subtitle">加载数据 · 选点 · 趋势 · 预警</div>
        </div>
      </div>
      <div class="status-strip">
        <div class="status-cell wide">
          <span class="cell-label">当前装置</span>
          <strong>ASU-1 号空分装置</strong>
        </div>
        <div class="status-cell">
          <span class="cell-label">数据源状态</span>
          <strong>{{ viewState.totalRows > 0 ? '历史数据模拟' : '未接入' }}</strong>
        </div>
        <div class="status-cell">
          <span class="cell-label">当前状态</span>
          <span class="state-label" :class="dcsStatusTone"><i></i>{{ dcsStatusLabel }}</span>
        </div>
        <div class="status-cell wide">
          <span class="cell-label">最新时间</span>
          <strong>{{ latestTimeText }}</strong>
        </div>
        <div class="status-cell">
          <span class="cell-label">当前预警数量</span>
          <strong>{{ dcsWarningCount }}</strong>
        </div>
        <div class="status-cell">
          <span class="cell-label">数据质量</span>
          <span class="state-label" :class="dataQualityTone"><i></i>{{ dataQualityText }}</span>
        </div>
        <label class="dcs-button primary upload-btn">
          加载数据
          <input ref="fileInput" type="file" accept=".xlsx,.xls,.csv" class="hidden-input" @change="handleFileSelect"/>
        </label>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">
      <span>报警：{{ errorMessage }}</span>
      <button type="button" @click="errorMessage = ''">确认</button>
    </div>

    <div v-if="showMapping" class="mapping-overlay">
      <div class="mapping-dialog dcs-panel">
        <div class="panel-title">数据流映射配置</div>
        <div class="mapping-body">
          <div class="mapping-field">
            <label>时间列</label>
            <el-select v-model="mapping.time" placeholder="选择时间列" size="large">
              <el-option v-for="h in headers" :key="h" :label="h" :value="h"/>
            </el-select>
          </div>
          <div class="mapping-field">
            <label>初始显示列</label>
            <el-select
              v-model="mapping.values"
              placeholder="选择要展示的指标列"
              size="large"
              multiple
              collapse-tags
              collapse-tags-tooltip
            >
              <el-option v-for="h in availableMetrics" :key="h" :label="h" :value="h"/>
            </el-select>
          </div>
          <el-button type="primary" size="large" :loading="isProcessing" @click="confirmMapping">
            确认映射并生成趋势
          </el-button>
        </div>
      </div>
    </div>

    <main class="dcs-grid">
      <aside class="dcs-panel left-nav">
        <div class="panel-title">点位</div>
        <div class="tree-list">
          <section v-for="group in pointTree" :key="group.name" class="tree-group">
            <div class="tree-group-title">
              <span class="tree-expander">▾</span>
              <strong>{{ group.name }}</strong>
              <span>{{ group.points.length }}</span>
            </div>
            <label v-for="point in group.points" :key="point.tag" class="point-row">
              <input v-model="selectedMetricIds" type="checkbox" :value="point.tag" :disabled="!availableMetrics.includes(point.tag)"/>
              <span class="point-tag">{{ point.tag }}</span>
              <span class="point-name">{{ point.name }}</span>
            </label>
          </section>
        </div>
        <div class="nav-footer">
          <span>关联点位</span>
          <strong>{{ selectedMetricIds.length }} / {{ availableMetrics.length || defaultPointCount }}</strong>
        </div>
      </aside>

      <section class="main-monitor">
        <div class="process-and-tags">
          <section class="dcs-panel process-panel">
            <div class="panel-title">工艺画面</div>
            <DcsProcessDiagram class="process-canvas" v-bind="processDiagram" />
          </section>

          <section class="dcs-panel tag-panel">
            <div class="panel-title">关键测点框</div>
            <div class="tag-grid">
              <article v-for="box in keyTagBoxes" :key="box.tag" class="tag-box" :class="box.tone">
                <div class="tag-top">
                  <strong>{{ box.tag }}</strong>
                  <span class="state-label mini" :class="box.tone"><i></i>{{ box.status }}</span>
                </div>
                <div class="tag-name">{{ box.name }}</div>
                <div class="tag-value">
                  <span>{{ box.value }}</span>
                  <em>{{ box.unit }}</em>
                </div>
              </article>
            </div>
          </section>
        </div>

        <section class="dcs-panel trend-panel">
          <div class="panel-title trend-title">
            <span>趋势</span>
            <span class="trend-context">{{ activeMetricLabel }} / {{ timeRangeText }}</span>
          </div>
          <div class="trend-tabs">
            <button
              v-for="tab in trendTabs"
              :key="tab.id"
              type="button"
              class="dcs-tab"
              :class="{ active: activeTrendTab === tab.id }"
              @click="activeTrendTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>
          <div class="trend-controls">
            <div v-if="selectedMetricIds.length > 1" class="metric-selector compact">
              <span class="selector-label">主指标</span>
              <el-radio-group v-model="activeMetricId" size="small">
                <el-radio-button v-for="metric in selectedMetricIds" :key="metric" :label="metric">{{ metric }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="time-range-btns">
              <el-button
                v-for="btn in timeRangeButtons"
                :key="btn.id"
                size="small"
                :type="timeRange === btn.id && zoomHistory.length === 0 ? 'primary' : ''"
                @click="handleTimeRangeChange(btn.id)"
              >
                {{ btn.label }}
              </el-button>
              <el-button v-if="zoomHistory.length > 0" size="small" @click="zoomOut">返回上层</el-button>
              <el-button v-if="zoomHistory.length > 0" size="small" type="danger" @click="zoomReset">还原全景</el-button>
            </div>
          </div>
          <div v-if="viewState.totalRows > 0" class="chart-wrapper" ref="chartWrapper" @wheel.prevent="handleChartWheel">
            <div class="abnormal-band observe"></div>
            <div class="abnormal-band alarm"></div>
            <canvas ref="chartCanvas" @mousedown="handleMouseDown" @mousemove="handleMouseMove" @mouseup="handleMouseUp" @mouseleave="handleMouseUp"></canvas>
            <div v-if="refAreaLeft && refAreaRight" class="selection-overlay" :style="selectionStyle"></div>
          </div>
          <div v-else class="empty-state">
            <div class="empty-title">NO DATA</div>
            <div class="empty-text">加载 Excel / CSV 后显示趋势</div>
          </div>
        </section>
      </section>

      <aside class="right-assist">
        <section class="dcs-panel warning-panel">
          <div class="panel-title">预警</div>
          <div class="warning-list">
            <div v-for="item in warningList" :key="item.id" class="warning-row" :class="item.tone">
              <span class="alarm-level">{{ item.level }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.desc }}</p>
              </div>
              <time>{{ item.time }}</time>
            </div>
          </div>
        </section>

        <section class="dcs-panel evidence-panel">
          <div class="panel-title">判据</div>
          <div class="evidence-block">
            <strong>窗口</strong>
            <p>{{ activeWindowText }}</p>
          </div>
          <div class="evidence-block">
            <strong>氮塞</strong>
            <p>{{ nitrogenResult ? `${nitrogenResult.riskLabel} / ${nitrogenResult.matchScore}` : '未执行' }}</p>
          </div>
          <div v-for="item in activeEvidenceRows" :key="item.tag" class="evidence-block">
            <strong>{{ item.tag }} {{ item.name }}</strong>
            <p>{{ item.current }} / {{ item.normalRange }} / {{ item.deviation }}</p>
          </div>
        </section>

        <section class="dcs-panel operation-panel">
          <SlidingWindowDiagnosisPanel />
          <div class="panel-title">窗口扫描</div>
          <div class="scan-control-grid">
            <label>
              <span>窗口长度</span>
              <select v-model.number="windowLengthMin">
                <option :value="30">30 min</option>
                <option :value="15">15 min</option>
              </select>
            </label>
            <label>
              <span>滑动步长</span>
              <select v-model.number="slideStepMin">
                <option :value="5">5 min</option>
                <option :value="10">10 min</option>
              </select>
            </label>
          </div>
          <div class="operation-step">
            <span>1 LOAD</span>
            <p>导入历史数据</p>
          </div>
          <div class="operation-step">
            <span>2 TAG</span>
            <p>选择监测点位</p>
          </div>
          <div class="operation-step">
            <span>3 TREND</span>
            <p>查看窗口趋势</p>
          </div>
          <div class="operation-step">
            <span>4 ALARM</span>
            <p>异常窗口进入 {{ activeRootCauseModule }}</p>
          </div>
          <el-button type="primary" :icon="TrendCharts" :loading="analyzing" @click="runRollingScan">
            执行滚动扫描
          </el-button>
          <div class="advice-box">
            <strong>建议</strong>
            <p>{{ operationAdvice }}</p>
          </div>
        </section>
      </aside>

      <section class="dcs-panel bottom-events">
        <div class="operator-clock left-clock">{{ latestTimeText }}</div>
        <div class="operator-nav">
          <button type="button">◀</button>
          <span>{{ timeRange === 'all' ? '全景' : timeRangeText }}</span>
          <button type="button">▶</button>
        </div>
        <button class="operator-now" type="button" @click="handleTimeRangeChange('all')">现在</button>
        <div class="bottom-column">
          <div class="panel-title">事件</div>
          <div class="event-line">
            <div v-for="event in eventTimeline" :key="event.time + event.text" class="event-item">
              <time>{{ event.time }}</time>
              <span>{{ event.text }}</span>
            </div>
          </div>
        </div>
        <div class="bottom-column">
          <div class="panel-title">历史</div>
          <table class="dcs-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>等级</th>
                <th>异常说明</th>
                <th>恢复观察</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="record in historyWarnings" :key="record.id || (record.time + record.desc)" @click="record.index !== undefined && setActiveWindow(record.index)">
                <td>{{ record.time }}</td>
                <td><span class="state-label mini" :class="record.tone"><i></i>{{ record.level }}</span></td>
                <td>{{ record.desc }}</td>
                <td>{{ record.recover }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="bottom-column case-json">
          <div class="panel-title">当前任务</div>
          <div class="task-summary">
            <span>DATA</span><strong>{{ viewState.totalRows ? viewState.totalRows : '-' }}</strong>
            <span>TAG</span><strong>{{ activeMetricLabel }}</strong>
            <span>ALARM</span><strong>{{ dcsWarningCount }}</strong>
          </div>
        </div>
      </section>
    </main>

    <div v-if="isProcessing" class="loading-state">
      <div class="loading-spinner"></div>
      <p>正在解析运行数据...</p>
      <div v-if="parseProgress > 0" class="parse-progress">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: parseProgress + '%' }"></div>
        </div>
        <span class="progress-text">{{ parseProgress }}%</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import SlidingWindowDiagnosisPanel from '../components/SlidingWindowDiagnosisPanel.vue'
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts } from '@element-plus/icons-vue'
import { Chart, registerables } from 'chart.js'
import DcsProcessDiagram from '../components/dcs/DcsProcessDiagram.vue'

const metricColorPalette = ['#1F4E79', '#8064A2', '#1FA64A', '#E67E22', '#8B5A2B', '#8A8A8A', '#2E75B6', '#D64541']
const fixedMetricColors = {
  FIC101: '#1F4E79',
  FIC1: '#8064A2',
  AI705: '#D64541',
  AI701: '#2E75B6',
  FIQC102: '#1FA64A',
  FI702: '#E67E22',
  FIQC701: '#8B5A2B',
  EGOX预测值: '#8A8A8A',
  EGOX实际值: '#2E75B6',
  残差率: '#D64541'
}

const chartCrosshairPlugin = {
  id: 'pi-crosshair',
  afterDatasetsDraw(chart) {
    const activeElements = chart.tooltip?.getActiveElements?.() || []
    if (!activeElements.length) return

    const preferred = activeElements.find((item) => chart.data.datasets[item.datasetIndex]?.metricId === activeMetricId.value) || activeElements[0]
    const point = preferred?.element
    const chartArea = chart.chartArea
    if (!point || !chartArea) return

    const { ctx } = chart
    ctx.save()
    ctx.setLineDash([6, 6])
    ctx.lineWidth = 1
    ctx.strokeStyle = 'rgba(46, 117, 182, 0.55)'

    ctx.beginPath()
    ctx.moveTo(point.x, chartArea.top)
    ctx.lineTo(point.x, chartArea.bottom)
    ctx.stroke()

    ctx.beginPath()
    ctx.moveTo(chartArea.left, point.y)
    ctx.lineTo(chartArea.right, point.y)
    ctx.stroke()
    ctx.restore()
  }
}

Chart.register(...registerables, chartCrosshairPlugin)

const fileInput = ref(null)
const chartCanvas = ref(null)
const chartWrapper = ref(null)

let mainChart = null
let fullData = []

const isProcessing = ref(false)
const errorMessage = ref('')
const rawArrayBuffer = ref(null)
const headers = ref([])
const availableMetrics = ref([])
const showMapping = ref(false)
const mapping = ref({ time: '', values: [] })
const timeRange = ref('all')
const analyzing = ref(false)
const windowLengthMin = ref(30)
const slideStepMin = ref(5)
const rollingResults = ref([])
const activeWindowIndex = ref(-1)
const selectedMetricIds = ref([])
const activeMetricId = ref('')
const activeTrendTab = ref('raw')

const refAreaLeft = ref(null)
const refAreaRight = ref(null)
const zoomHistory = ref([])

const MIN_WHEEL_ZOOM_POINTS = 24
const LAZY_ANALYSIS_DELAY = 320

const analysisCatalog = [
  {
    id: 'basic',
    label: '基础统计',
    description: '汇总当前可视范围的关键统计值',
    loadMode: 'eager'
  },
  {
    id: 'trend',
    label: '趋势分析',
    description: '基于可视范围采样判断变化方向和波动强度',
    loadMode: 'eager'
  },
  {
    id: 'distribution',
    label: '分布分析',
    description: '查看有效值占比、离散程度和分布跨度',
    loadMode: 'lazy'
  },
  {
    id: 'nitrogen',
    label: '氮塞识别',
    description: '按需触发规则识别，后续可扩展到模型分析',
    loadMode: 'manual'
  }
]

const analysisModeText = {
  eager: '即时',
  lazy: '按需加载',
  manual: '手动触发'
}

const selectedAnalysisIds = ref(analysisCatalog.map(item => item.id))
const loadedAnalysisIds = ref(analysisCatalog.filter(item => item.loadMode !== 'lazy').map(item => item.id))
const loadingAnalysisIds = ref([])

const activeMetricLabel = computed(() => activeMetricId.value || selectedMetricIds.value[0] || '-')

const selectionStyle = computed(() => {
  if (!refAreaLeft.value || !refAreaRight.value || !chartCanvas.value || !mainChart) return null
  const chartArea = mainChart.chartArea
  const rect = chartCanvas.value.getBoundingClientRect()

  const leftDataIdx = viewState.value.chartData.findIndex(d => d._absIdx === refAreaLeft.value.absIdx)
  const rightDataIdx = viewState.value.chartData.findIndex(d => d._absIdx === refAreaRight.value.absIdx)

  if (leftDataIdx === -1 || rightDataIdx === -1) return null

  const step = (chartArea.right - chartArea.left) / (viewState.value.chartData.length - 1 || 1)
  const leftX = chartArea.left + leftDataIdx * step
  const rightX = chartArea.left + rightDataIdx * step

  return {
    left: Math.min(leftX, rightX) + 'px',
    width: Math.abs(rightX - leftX) + 'px',
    top: chartArea.top + 'px',
    height: (chartArea.bottom - chartArea.top) + 'px'
  }
})

const viewState = ref({
  chartData: [],
  stats: { max: 0, min: 0, avg: 0 },
  totalRows: 0,
  filteredRows: 0
})

const timeRangeButtons = computed(() => {
  const total = viewState.value.totalRows
  const label = (id, suffix) => {
    if (id === 'all') return `全量(${total})`
    return `${suffix}`
  }
  return [
    { id: 'all', label: label('all', '') },
    { id: '5m', label: '5M' },
    { id: '30m', label: '30M' },
    { id: '1h', label: '1H' },
    { id: '2h', label: '2H' },
    { id: '5h', label: '5H' },
    { id: '12h', label: '12H' },
    { id: '24h', label: '24H' }
  ]
})

const timeRangeText = computed(() => {
  const data = viewState.value.chartData
  if (!data.length) return '-'
  return `${data[0]?.time || ''} ~ ${data[data.length - 1]?.time || ''}`
})

const nitrogenResult = ref(null)
const parseProgress = ref(0)

const activeRollingResult = computed(() => {
  if (activeWindowIndex.value < 0) return rollingResults.value[rollingResults.value.length - 1] || null
  return rollingResults.value[activeWindowIndex.value] || null
})

const activeWindowText = computed(() => {
  const result = activeRollingResult.value
  if (!result) return `${windowLengthMin.value} min / step ${slideStepMin.value} min`
  return `${result.window.start} ~ ${result.window.end}`
})

const activeEvidenceRows = computed(() => activeRollingResult.value?.evidence || [])

const activeRootCauseModule = computed(() => activeRollingResult.value?.rootCause?.module || '粗氩系统溯源')

const visibleAnalysisItems = computed(() => (
  analysisCatalog.filter(item => selectedAnalysisIds.value.includes(item.id))
))

const visibleValues = computed(() => (
  viewState.value.chartData
    .map(item => item.metrics?.[activeMetricId.value] ?? null)
    .filter(value => Number.isFinite(value))
))

const visibleSeriesStats = computed(() => {
  const values = visibleValues.value
  const validCount = values.length
  const totalCount = viewState.value.filteredRows || viewState.value.chartData.length
  const nullCount = Math.max(0, totalCount - validCount)
  const validRatio = totalCount > 0 ? (validCount / totalCount) * 100 : 0

  return {
    values,
    validCount,
    totalCount,
    nullCount,
    validRatio
  }
})

const trendStats = computed(() => {
  const values = visibleSeriesStats.value.values
  if (!values.length) {
    return {
      direction: '暂无数据',
      delta: NaN,
      recentAvg: NaN,
      volatilityLabel: '暂无数据',
      summary: '当前可视范围内没有足够有效值可用于趋势判断。',
      windowHint: '可缩放图表或切换时间范围后重新观察。'
    }
  }

  const first = values[0]
  const last = values[values.length - 1]
  const delta = last - first
  const recentWindow = values.slice(-Math.min(values.length, 12))
  const recentAvg = recentWindow.reduce((sum, value) => sum + value, 0) / recentWindow.length
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length
  const range = Math.max(...values) - Math.min(...values)
  const stdDev = getStandardDeviation(values)
  const movementRatio = Math.abs(delta) / Math.max(Math.abs(avg), 1)

  let direction = '基本持平'
  if (delta > 0.5) direction = '整体上升'
  if (delta < -0.5) direction = '整体下降'

  let volatilityLabel = '平稳'
  if (stdDev > 1 || range > 3) volatilityLabel = '中等波动'
  if (stdDev > 2.5 || range > 8) volatilityLabel = '高波动'

  return {
    direction,
    delta,
    recentAvg,
    volatilityLabel,
    summary: `当前窗口首末变化 ${formatSignedNumber(delta)}，整体呈${direction}。`,
    windowHint: movementRatio > 0.08 ? '短窗均值偏离较明显，建议继续缩放局部查看。' : '短窗均值与整体均值接近，当前趋势较连续。'
  }
})

const distributionStats = computed(() => {
  const values = [...visibleSeriesStats.value.values].sort((a, b) => a - b)
  if (!values.length) {
    return {
      validRatio: 0,
      stdDev: NaN,
      range: NaN,
      iqrText: '-',
      summary: '当前没有可用值进行分布分析。',
      completeness: '请先加载数据或切换到有有效值的时间范围。'
    }
  }

  const q1 = getPercentile(values, 0.25)
  const q3 = getPercentile(values, 0.75)
  const range = values[values.length - 1] - values[0]
  const stdDev = getStandardDeviation(values)

  return {
    validRatio: visibleSeriesStats.value.validRatio,
    stdDev,
    range,
    iqrText: `${formatNumber(q1)} ~ ${formatNumber(q3)}`,
    summary: stdDev > 2 ? '分布较分散，离散程度偏高。' : '分布相对集中，离散程度可控。',
    completeness: `当前可视范围有效值 ${visibleSeriesStats.value.validCount} 个，缺失 ${visibleSeriesStats.value.nullCount} 个。`
  }
})

const analysisSummaryCards = computed(() => [
  {
    id: 'selected',
    label: '已选指标',
    value: `${selectedMetricIds.value.length} 条`,
    note: selectedMetricIds.value.join(' / ') || '未选择'
  },
  {
    id: 'trend',
    label: '趋势判断',
    value: trendStats.value.direction,
    note: `${activeMetricLabel.value}：${trendStats.value.summary}`
  },
  {
    id: 'distribution',
    label: '有效值占比',
    value: formatPercent(distributionStats.value.validRatio),
    note: distributionStats.value.completeness
  },
  {
    id: 'nitrogen',
    label: '氮塞状态',
    value: nitrogenResult.value ? (nitrogenResult.value.riskLevel === 'high' ? '高风险' : '未见异常') : '待触发',
    note: nitrogenResult.value ? nitrogenResult.value.matchScore : '点击下方“氮塞识别”模块可执行分析'
  }
])

const defaultPointTree = [
  { name: '空气系统', points: [{ tag: 'FIC101', name: '空气进塔流量' }, { tag: 'PI101', name: '空压机出口压力' }] },
  { name: '主塔系统', points: [{ tag: 'FIC1', name: '下塔回流流量' }, { tag: 'TI301', name: '主塔温度' }, { tag: 'AI701', name: '上塔/氩馏分关联纯度' }] },
  { name: '氩系统', points: [{ tag: 'AI705', name: '粗氩含氩量' }, { tag: 'FI702', name: '粗氩流量' }, { tag: 'FIQC701', name: '氩馏分流量' }] },
  { name: '产品系统', points: [{ tag: 'FIQC102', name: '氧产品流量' }, { tag: 'EGOX实际值', name: '氧产品电耗实际值' }] },
  { name: '膨胀系统', points: [{ tag: 'EXP101', name: '膨胀机负荷' }, { tag: 'TI501', name: '膨胀后温度' }] },
  { name: '主换热器', points: [{ tag: 'EGOX预测值', name: '氧产品电耗预测值' }, { tag: '残差率', name: '模型残差率' }] }
]

const defaultPointCount = defaultPointTree.reduce((sum, group) => sum + group.points.length, 0)

const pointTree = computed(() => {
  if (!availableMetrics.value.length) return defaultPointTree
  const knownTags = new Set(defaultPointTree.flatMap(group => group.points.map(point => point.tag)))
  const dynamicPoints = availableMetrics.value
    .filter(metric => !knownTags.has(metric))
    .map(metric => ({ tag: metric, name: '导入测点' }))

  return [
    ...defaultPointTree.map(group => ({
      ...group,
      points: group.points.map(point => ({
        ...point,
        name: availableMetrics.value.includes(point.tag) ? point.name : `${point.name}（未导入）`
      }))
    })),
    ...(dynamicPoints.length ? [{ name: '导入数据列', points: dynamicPoints }] : [])
  ]
})

const trendTabs = [
  { id: 'raw', label: '原始变量趋势' },
  { id: 'derived', label: '派生指标趋势' },
  { id: 'residual', label: '模型残差趋势' }
]

const latestTimeText = computed(() => {
  const data = viewState.value.chartData
  return data.length ? data[data.length - 1]?.time || '-' : '-'
})

const dataQualityText = computed(() => {
  if (!viewState.value.totalRows) return '数据无效'
  if (visibleSeriesStats.value.validRatio >= 95) return '有效'
  if (visibleSeriesStats.value.validRatio >= 80) return '观察'
  return '数据无效'
})

const dataQualityTone = computed(() => {
  if (!viewState.value.totalRows) return 'invalid'
  if (visibleSeriesStats.value.validRatio >= 95) return 'ok'
  if (visibleSeriesStats.value.validRatio >= 80) return 'observe'
  return 'invalid'
})

const dcsStatusTone = computed(() => {
  if (nitrogenResult.value?.riskLevel === 'high') return 'alarm'
  if (nitrogenResult.value?.riskLevel === 'medium') return 'warning'
  if (trendStats.value.volatilityLabel === '高波动') return 'warning'
  if (trendStats.value.volatilityLabel === '中等波动') return 'observe'
  return viewState.value.totalRows ? 'ok' : 'invalid'
})

const dcsStatusLabel = computed(() => {
  const map = {
    ok: '正常',
    observe: '观察',
    warning: '预警',
    alarm: '报警',
    invalid: '数据无效'
  }
  return map[dcsStatusTone.value] || '数据无效'
})

const dcsWarningCount = computed(() => {
  let count = 0
  if (dcsStatusTone.value === 'observe' || dcsStatusTone.value === 'warning' || dcsStatusTone.value === 'alarm') count += 1
  if (dataQualityTone.value !== 'ok' && viewState.value.totalRows > 0) count += 1
  return count
})

const keyTagBoxes = computed(() => {
  const defaults = [
    { tag: 'FIC101', name: '空气进塔流量', unit: 'Nm3/h' },
    { tag: 'FIC1', name: '下塔回流流量', unit: 'Nm3/h' },
    { tag: 'AI705', name: '粗氩含氩量', unit: '%' },
    { tag: 'AI701', name: '氩馏分关联纯度', unit: '%' },
    { tag: 'FI702', name: '粗氩流量', unit: 'Nm3/h' },
    { tag: 'FIQC701', name: '氩馏分流量', unit: 'Nm3/h' },
    { tag: 'FIQC102', name: '氧产品流量', unit: 'Nm3/h' }
  ]
  const dynamic = selectedMetricIds.value.slice(0, 6).map(metric => ({ tag: metric, name: '导入测点', unit: 'unit' }))
  const source = dynamic.length ? dynamic : defaults

  return source.map((item, index) => {
    const value = getMetricValue(viewState.value.chartData.at(-1), item.tag)
    const tone = !viewState.value.totalRows || value === null ? 'invalid' : (index === 0 ? dcsStatusTone.value : 'ok')
    return {
      ...item,
      value: formatNumber(value),
      status: tone === 'ok' ? '正常' : tone === 'observe' ? '观察' : tone === 'warning' ? '预警' : tone === 'alarm' ? '报警' : '无效',
      tone
    }
  })
})

const processDiagram = computed(() => {
  const tagMap = Object.fromEntries(keyTagBoxes.value.map(item => [item.tag, item]))
  const valueOf = (tag, fallback = '-') => tagMap[tag]?.value || fallback
  const toneOf = (tag) => tagMap[tag]?.tone || 'invalid'

  return {
    title: '粗氩精馏 DCS process overview',
    lines: [
      { id: 'feed-air', tone: 'white', x: 6, y: 18, length: 48 },
      { id: 'reflux-air', tone: 'white', x: 6, y: 37, length: 44, rotate: 180 },
      { id: 'column-top-signal', tone: 'signal', x: 47, y: 23, length: 22, dashed: true, arrow: false },
      { id: 'argon-feed', tone: 'magenta', x: 6, y: 68, length: 52 },
      { id: 'product-gas', tone: 'magenta', x: 64, y: 43, length: 26 },
      { id: 'product-gas-drop', tone: 'magenta', x: 64, y: 43, length: 16, rotate: 90, arrow: false },
      { id: 'waste-line', tone: 'magenta', x: 6, y: 84, length: 38, rotate: 180 },
      { id: 'bottom-return', tone: 'magenta', x: 58, y: 82, length: 18, rotate: 180 },
    ],
    labels: [
      { id: 'l1', text: '空气来自提升气总管', x: 6, y: 10, centered: false },
      { id: 'l2', text: '液空蒸汽回流去上塔', x: 6, y: 30, centered: false },
      { id: 'l3', text: '氩馏分来自上塔', x: 6, y: 60, centered: false },
      { id: 'l4', text: '粗氩气去纯氩塔', x: 77, y: 36, centered: false },
      { id: 'l5', text: '排液', x: 6, y: 76, centered: false },
    ],
    vessels: [
      {
        id: 'c701',
        x: 61,
        y: 49,
        width: '7.5%',
        height: '74%',
        type: 'tower',
        pack: true,
        liquid: '13%',
        sections: [
          { id: 'e701', label: 'E701', className: 'upper' },
          { id: 'c701', label: 'C701', className: 'lower' },
        ],
      },
    ],
    valves: [
      { id: 'hv123', label: 'HV123', tone: 'green', x: 21, y: 18 },
      { id: 'pv712', label: 'PV712', tone: dcsStatusTone.value === 'alarm' ? 'red' : 'green', x: 75, y: 43 },
      { id: 'pv502', label: 'PV502A/B', tone: 'green', x: 25, y: 68 },
      { id: 'hv501', label: 'HV501A/B', tone: 'green', x: 65, y: 84 },
      { id: 'hv507', label: 'HV507A/B', tone: 'gray', x: 13, y: 84 },
    ],
    junctions: [
      { id: 'j-feed', tone: 'green', x: 21, y: 18 },
      { id: 'j-argon', tone: 'green', x: 25, y: 68 },
      { id: 'j-product', tone: dcsStatusTone.value === 'alarm' ? 'red' : 'green', x: 75, y: 43 },
      { id: 'j-bottom', tone: 'green', x: 65, y: 84 },
      { id: 'j-waste', tone: 'white', x: 14, y: 84 },
    ],
    instruments: [
      { id: 'hc123', tag: 'HC123', value: '1.0', unit: '%', x: 26, y: 24 },
      { id: 'pic709', tag: 'PIC709', value: '30.64', unit: 'kPa', x: 38, y: 15 },
      { id: 'ti704', tag: 'TI704', value: '-189.0', unit: '℃', x: 38, y: 35 },
      { id: 'fi702', tag: 'FI702', value: valueOf('FI702'), unit: 'Nm3/h', tone: toneOf('FI702'), x: 26, y: 62 },
      { id: 'fic701', tag: 'FIC701', value: valueOf('FIQC701'), unit: 'Nm3/h', tone: toneOf('FIQC701'), x: 72, y: 49 },
      { id: 'ai705', tag: 'AI705', value: '99.93', unit: '%Ar', x: 69, y: 26 },
      { id: 'li702', tag: 'LI702', value: '1100', unit: 'mm', x: 70, y: 77 },
      { id: 'pdi702', tag: 'PDI702', value: '7.08', unit: 'kPa', x: 53, y: 55 },
    ],
  }
})

const warningList = computed(() => {
  if (!viewState.value.totalRows) {
    return [{ id: 'no-data', level: '提示', title: 'NO DATA', desc: '等待导入', time: '-' , tone: 'invalid' }]
  }

  const items = []
  if (nitrogenResult.value?.riskLevel === 'high' || nitrogenResult.value?.riskLevel === 'medium') {
    items.push({
      id: 'nitrogen-plug',
      level: nitrogenResult.value.riskLabel,
      title: '疑似粗氩塔氮塞',
      desc: `${activeRootCauseModule.value}：${nitrogenResult.value.triggerVariables?.join(' / ') || '关键变量'}`,
      time: activeRollingResult.value?.window?.end || latestTimeText.value,
      tone: nitrogenResult.value.riskLevel === 'high' ? 'alarm' : 'warning'
    })
  }
  if (dcsStatusTone.value !== 'ok') {
    items.push({
      id: 'trend',
      level: dcsStatusLabel.value,
      title: `${activeMetricLabel.value} ${trendStats.value.volatilityLabel}`,
      desc: trendStats.value.direction,
      time: latestTimeText.value,
      tone: dcsStatusTone.value
    })
  }
  if (dataQualityTone.value !== 'ok') {
    items.push({
      id: 'quality',
      level: '观察',
      title: 'DATA QUALITY',
      desc: `${visibleSeriesStats.value.validRatio.toFixed(0)}%`,
      time: latestTimeText.value,
      tone: dataQualityTone.value
    })
  }
  if (!items.length) {
    items.push({ id: 'normal', level: '正常', title: 'NO ALARM', desc: '监视中', time: latestTimeText.value, tone: 'ok' })
  }
  return items
})

const nitrogenMechanismText = computed(() => {
  if (activeRollingResult.value?.rootCause?.reasonRank?.length) return activeRollingResult.value.rootCause.reasonRank.join('；')
  if (nitrogenResult.value?.features?.length) return nitrogenResult.value.features.join('；')
  return '氮塞识别未触发，建议结合氩馏分、主塔压力、产品流量变化进行确认。'
})

const operationAdvice = computed(() => {
  if (activeRollingResult.value?.advice?.length) return activeRollingResult.value.advice.join('；')
  if (nitrogenResult.value?.riskLevel === 'high') return '保持负荷调整幅度受控，优先核对氩系统与主塔回流，必要时按现场规程降低扰动。'
  if (dcsStatusTone.value === 'warning' || dcsStatusTone.value === 'observe') return '维持当前工况，缩小趋势时间窗，复核关联点位是否同步偏移。'
  return '保持监视，按班组巡检要求记录当前状态。'
})

const eventTimeline = computed(() => [
  { time: latestTimeText.value, text: viewState.value.totalRows ? 'TREND READY' : 'WAIT DATA' },
  { time: activeRollingResult.value?.window?.end || latestTimeText.value, text: rollingResults.value.length ? `SCAN ${rollingResults.value.length} WINDOWS` : 'SCAN READY' },
  { time: latestTimeText.value, text: `STATUS ${dcsStatusLabel.value}` },
  { time: latestTimeText.value, text: `QUALITY ${dataQualityText.value}` }
])

const historyWarnings = computed(() => {
  if (rollingResults.value.length) {
    return rollingResults.value.slice(-8).reverse().map(result => ({
      id: result.id,
      index: result.index,
      time: result.window.end,
      level: result.riskLabel,
      desc: `${result.rootCause.module} / ${result.triggerVariables.join(', ') || '未触发'}`,
      recover: result.isAbnormal ? 'TRACE' : 'DONE',
      tone: result.tone
    }))
  }
  return [
    { time: latestTimeText.value, level: dcsStatusLabel.value, desc: warningList.value[0]?.title || 'NO ALARM', recover: dcsStatusTone.value === 'ok' ? 'DONE' : 'WATCH', tone: dcsStatusTone.value },
    { time: '-', level: '正常', desc: 'CASE SLOT', recover: 'DONE', tone: 'ok' }
  ]
})

const caseJsonText = computed(() => JSON.stringify({
  device: 'ASU-1',
  current_status: dcsStatusLabel.value,
  data_quality: dataQualityText.value,
  active_metric: activeMetricLabel.value,
  warning_count: dcsWarningCount.value,
  latest_time: latestTimeText.value,
  scan_window_min: windowLengthMin.value,
  slide_step_min: slideStepMin.value,
  active_window: activeWindowText.value,
  trace_module: activeRootCauseModule.value,
  output_fields: ['window', 'riskLevel', 'triggerVariables', 'rootCause', 'evidence', 'advice']
}, null, 2))

function getMetricColor(metricId, index = 0) {
  if (fixedMetricColors[metricId]) return fixedMetricColors[metricId]
  const baseIndex = availableMetrics.value.indexOf(metricId)
  const paletteIndex = baseIndex >= 0 ? baseIndex : index
  return metricColorPalette[paletteIndex % metricColorPalette.length]
}

function getMetricValue(row, metricId) {
  return row?.metrics?.[metricId] ?? null
}

function coerceNumericValue(value) {
  const parsed = value !== null && value !== undefined ? parseFloat(value) : null
  return parsed === 0 || Number.isNaN(parsed) ? null : parsed
}

function syncActiveMetric(preferredMetric) {
  if (preferredMetric && selectedMetricIds.value.includes(preferredMetric)) {
    activeMetricId.value = preferredMetric
    return
  }
  if (selectedMetricIds.value.includes(activeMetricId.value)) return
  activeMetricId.value = selectedMetricIds.value[0] || ''
}

function formatNumber(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : '-'
}

function formatSignedNumber(value, digits = 2) {
  if (!Number.isFinite(value)) return '-'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${value.toFixed(digits)}`
}

function formatPercent(value, digits = 1) {
  return Number.isFinite(value) ? `${value.toFixed(digits)}%` : '-'
}

function getStandardDeviation(values) {
  if (!values.length) return NaN
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length
  return Math.sqrt(variance)
}

function getPercentile(sortedValues, percentile) {
  if (!sortedValues.length) return NaN
  const index = (sortedValues.length - 1) * percentile
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  if (lower === upper) return sortedValues[lower]
  const weight = index - lower
  return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight
}

function parseRowTime(row) {
  const time = Date.parse(row?.t)
  return Number.isFinite(time) ? time : null
}

function getWindowRows(startMs, endMs) {
  return fullData.filter(row => {
    const time = parseRowTime(row)
    return time !== null && time >= startMs && time < endMs
  })
}

function getTagValues(rows, tag) {
  return rows
    .map(row => row.metrics?.[tag])
    .filter(value => Number.isFinite(value))
}

function getTagStats(rows, tag) {
  const values = getTagValues(rows, tag)
  if (!values.length) {
    return { tag, count: 0, current: null, avg: null, min: null, max: null, delta: null, range: null, stdDev: null }
  }
  const sum = values.reduce((acc, value) => acc + value, 0)
  return {
    tag,
    count: values.length,
    current: values[values.length - 1],
    avg: sum / values.length,
    min: Math.min(...values),
    max: Math.max(...values),
    delta: values[values.length - 1] - values[0],
    range: Math.max(...values) - Math.min(...values),
    stdDev: getStandardDeviation(values)
  }
}

function getRollingWindows() {
  const timedRows = fullData
    .map(row => ({ row, time: parseRowTime(row) }))
    .filter(item => item.time !== null)
  if (!timedRows.length) return []

  const dataStart = timedRows[0].time
  const dataEnd = timedRows[timedRows.length - 1].time
  const windowMs = windowLengthMin.value * 60 * 1000
  const stepMs = slideStepMin.value * 60 * 1000
  const windows = []
  for (let start = dataStart; start + windowMs <= dataEnd + 1; start += stepMs) {
    const end = start + windowMs
    const rows = getWindowRows(start, end)
    if (rows.length) windows.push({ startMs: start, endMs: end, rows })
  }
  return windows
}

function formatWindowTime(ms) {
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

function buildEvidence(tag, name, stats, normalRange, direction) {
  const current = stats.current
  const deviation = direction === 'down'
    ? (Number.isFinite(stats.delta) ? `下降 ${formatNumber(Math.abs(Math.min(stats.delta, 0)))}` : '-')
    : (direction === 'up' && Number.isFinite(stats.delta) ? `上升 ${formatNumber(Math.max(stats.delta, 0))}` : `波动 ${formatNumber(stats.range)}`)
  return {
    tag,
    name,
    current: formatNumber(current),
    normalRange,
    deviation
  }
}

function evaluateNitrogenWindow(windowItem, index) {
  const rows = windowItem.rows
  const ai705 = getTagStats(rows, 'AI705')
  const ai701 = getTagStats(rows, 'AI701')
  const fi702 = getTagStats(rows, 'FI702')
  const fiqc701 = getTagStats(rows, 'FIQC701')
  const active = getTagStats(rows, activeMetricId.value)
  const evidence = []
  const triggerVariables = []

  let score = 0
  if (Number.isFinite(ai705.delta) && ai705.delta <= -0.08) {
    score += 3
    triggerVariables.push('AI705')
    evidence.push(buildEvidence('AI705', '粗氩含氩量', ai705, '窗口内应稳定或缓慢变化', 'down'))
  }
  if (Number.isFinite(ai701.delta) && ai701.delta <= -0.05) {
    score += 2
    triggerVariables.push('AI701')
    evidence.push(buildEvidence('AI701', '氩馏分关联纯度', ai701, '窗口内不应持续下降', 'down'))
  }
  if (Number.isFinite(fiqc701.range) && fiqc701.range >= Math.max(Math.abs(fiqc701.avg || 0) * 0.04, 1)) {
    score += 2
    triggerVariables.push('FIQC701')
    evidence.push(buildEvidence('FIQC701', '氩馏分流量', fiqc701, '滑动平均波动不超过 4%', 'range'))
  }
  if (Number.isFinite(fi702.delta) && fi702.delta <= -Math.max(Math.abs(fi702.avg || 0) * 0.03, 1)) {
    score += 1
    triggerVariables.push('FI702')
    evidence.push(buildEvidence('FI702', '粗氩流量', fi702, '不应随纯度下降同步萎缩', 'down'))
  }
  if (!triggerVariables.length && Number.isFinite(active.range) && active.range > Math.max(Math.abs(active.avg || 0) * 0.12, 10)) {
    score += 1
    triggerVariables.push(activeMetricId.value)
    evidence.push(buildEvidence(activeMetricId.value, '当前主指标', active, '窗口内波动需复核', 'range'))
  }

  const riskLevel = score >= 5 ? 'high' : score >= 3 ? 'medium' : 'low'
  const isAbnormal = riskLevel !== 'low'
  const rootCause = isAbnormal
    ? {
        module: triggerVariables.includes('AI705') || triggerVariables.includes('FIQC701') ? '粗氩系统溯源' : '主塔/前端负荷溯源',
        branches: ['粗氩系统', '主塔', '前端负荷', '操作调节'],
        reasonRank: triggerVariables.includes('FIQC701')
          ? ['氩馏分抽取或流量调节扰动', '上塔氩馏分含氮升高', '粗氩塔冷凝负荷不足']
          : ['氩馏分组成偏移', '主塔回流比变化', '负荷调整造成短时扰动']
      }
    : { module: '无需溯源', branches: [], reasonRank: ['窗口内未触发氮塞规则'] }

  return {
    id: `scan-${index}-${windowItem.startMs}`,
    index,
    window: {
      start: formatWindowTime(windowItem.startMs),
      end: formatWindowTime(windowItem.endMs),
      lengthMin: windowLengthMin.value,
      stepMin: slideStepMin.value,
      sampleCount: rows.length
    },
    riskLevel,
    riskLabel: riskLevel === 'high' ? '严重' : riskLevel === 'medium' ? '观察' : '正常',
    tone: riskLevel === 'high' ? 'alarm' : riskLevel === 'medium' ? 'warning' : 'ok',
    isAbnormal,
    matchScore: `${score}/8`,
    triggerVariables,
    evidence,
    rootCause,
    advice: isAbnormal
      ? ['暂停扩大负荷调整，先稳定 1 个窗口', '核对 AI705、AI701 与 FIQC701 是否同步偏移', '进入粗氩系统溯源并人工确认阀位/流量调节记录']
      : ['继续按 5 min 步长滚动扫描', '保留本窗口诊断记录']
  }
}

function setActiveWindow(index) {
  const result = rollingResults.value[index]
  if (!result) return
  activeWindowIndex.value = index
  nitrogenResult.value = result
}

function isAnalysisLoaded(id) {
  return loadedAnalysisIds.value.includes(id)
}

function isAnalysisLoading(id) {
  return loadingAnalysisIds.value.includes(id)
}

function ensureAnalysisLoaded(id) {
  const item = analysisCatalog.find(entry => entry.id === id)
  if (!item || item.loadMode !== 'lazy' || isAnalysisLoaded(id) || isAnalysisLoading(id)) return

  loadingAnalysisIds.value = [...loadingAnalysisIds.value, id]
  window.setTimeout(() => {
    loadingAnalysisIds.value = loadingAnalysisIds.value.filter(entry => entry !== id)
    loadedAnalysisIds.value = [...loadedAnalysisIds.value, id]
  }, LAZY_ANALYSIS_DELAY)
}

const loadXLSX = () => {
  return new Promise((resolve) => {
    if (window.XLSX) {
      resolve(window.XLSX)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js'
    script.onload = () => resolve(window.XLSX)
    document.head.appendChild(script)
  })
}

function handleFileSelect(event) {
  const file = event.target.files[0]
  if (!file) return

  console.log('[PIAnalysis] handleFileSelect - 文件选择:', file.name)
  errorMessage.value = ''
  isProcessing.value = true
  zoomHistory.value = []

  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      console.log('[PIAnalysis] handleFileSelect - 开始解析表头')
      const XLSX = await loadXLSX()
      const workbook = XLSX.read(e.target.result, { type: 'array', sheetRows: 1, cellDates: false, cellFormula: false, cellHTML: false, cellStyles: false })
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
      const range = XLSX.utils.sheet_to_json(firstSheet, { header: 1 })

      if (range && range.length > 0) {
        const rawHeaders = range[0]
        console.log('[PIAnalysis] handleFileSelect - 原始表头:', rawHeaders)
        
        const headerMap = []
        rawHeaders.forEach((h, i) => {
          const trimmed = (h !== undefined && h !== null) ? String(h).trim() : ''
          if (trimmed !== '') {
            const existing = headerMap.find(item => item.name === trimmed)
            if (!existing) {
              headerMap.push({ name: trimmed, colIdx: i })
            }
          }
        })
        
        const foundHeaders = headerMap.map(item => item.name)
        console.log('[PIAnalysis] handleFileSelect - headerMap:', headerMap)
        console.log('[PIAnalysis] handleFileSelect - 去重后列:', foundHeaders)
        
        const timeColIdx = headerMap.length > 0 && headerMap[0].name ? 0 : (headerMap.length > 1 ? 1 : 0)
        const valColIdx = headerMap.findIndex((item, i) => i !== timeColIdx && /705|PV|AI|TI|FI|PI/i.test(item.name))
        
        headers.value = foundHeaders
        rawArrayBuffer.value = e.target.result
        const metricCandidates = headerMap
          .filter((_, index) => index !== timeColIdx)
          .map(item => item.name)
        const preferredMetric = valColIdx >= 0 ? headerMap[valColIdx].name : (metricCandidates[0] || '')
        const nitrogenTags = ['AI705', 'AI701', 'FI702', 'FIQC701']
        const initialMetrics = metricCandidates.filter(name => nitrogenTags.includes(name) || name === preferredMetric || metricCandidates.indexOf(name) < 3).slice(0, 6)
        availableMetrics.value = metricCandidates
        mapping.value = {
          time: headerMap[timeColIdx]?.name || '时间',
          values: initialMetrics.length ? initialMetrics : (preferredMetric ? [preferredMetric] : metricCandidates.slice(0, 1))
        }
        console.log('[PIAnalysis] handleFileSelect - 原始列索引: timeColIdx=', headerMap[timeColIdx]?.colIdx, 'valColIdx=', valColIdx >= 0 ? headerMap[valColIdx].colIdx : 'N/A')
        console.log('[PIAnalysis] handleFileSelect - 映射配置:', mapping.value)
        showMapping.value = true
      }
    } catch (err) {
      console.error('[PIAnalysis] handleFileSelect - 错误:', err)
      errorMessage.value = '读取表头失败'
    } finally {
      isProcessing.value = false
    }
  }
  reader.readAsArrayBuffer(file)
  event.target.value = ''
}

function updateView(rangeId, currentZoom) {
  console.log('[PIAnalysis] updateView - rangeId:', rangeId, 'currentZoom:', currentZoom)
  if (!fullData || fullData.length === 0) {
    console.log('[PIAnalysis] updateView - 无数据')
    return
  }

  let filtered = fullData
  let baseStartIndex = 0

  if (rangeId !== 'all') {
    const rowMap = {
      '5m': 12 * 5,
      '30m': 12 * 30,
      '1h': 12 * 60,
      '2h': 12 * 120,
      '5h': 12 * 300,
      '12h': 12 * 720,
      '24h': 12 * 1440
    }
    const takeCount = rowMap[rangeId] || fullData.length
    baseStartIndex = Math.max(0, fullData.length - takeCount)
  }

  if (currentZoom) {
    baseStartIndex = currentZoom[0]
    filtered = fullData.slice(currentZoom[0], currentZoom[1] + 1)
  } else {
    filtered = fullData.slice(baseStartIndex)
  }

  let max = -Infinity, min = Infinity, sum = 0, validCount = 0
  for (let i = 0; i < filtered.length; i++) {
    const val = getMetricValue(filtered[i], activeMetricId.value)
    if (val !== null) {
      if (val > max) max = val
      if (val < min) min = val
      sum += val
      validCount++
    }
  }

  const stats = {
    max: max === -Infinity ? 0 : max,
    min: min === Infinity ? 0 : min,
    avg: validCount === 0 ? 0 : (sum / validCount)
  }

  const maxPoints = 1500
  let sampled = []

  if (filtered.length <= maxPoints) {
    sampled = filtered.map((d, i) => ({
      time: d.t,
      raw: getMetricValue(d, activeMetricId.value),
      metrics: d.metrics,
      _absIdx: baseStartIndex + i
    }))
  } else {
    const step = Math.max(1, Math.floor(filtered.length / maxPoints))
    for (let i = 0; i < filtered.length; i += step) {
      sampled.push({
        time: filtered[i].t,
        raw: getMetricValue(filtered[i], activeMetricId.value),
        metrics: filtered[i].metrics,
        _absIdx: baseStartIndex + i
      })
    }
  }

  viewState.value = {
    chartData: sampled,
    stats,
    totalRows: fullData.length,
    filteredRows: filtered.length
  }
}

async function confirmMapping() {
  if (!rawArrayBuffer.value) return
  if (!mapping.value.time || !availableMetrics.value.length) {
    errorMessage.value = '请先选择时间列和至少一个数值列'
    return
  }
  if (!mapping.value.values.length) {
    errorMessage.value = '请至少选择一个初始显示指标'
    return
  }
  console.log('[PIAnalysis] confirmMapping - 开始解析数据')
  isProcessing.value = true
  errorMessage.value = ''
  parseProgress.value = 5
  nitrogenResult.value = null
  rollingResults.value = []
  activeWindowIndex.value = -1

  requestAnimationFrame(async () => {
    try {
      console.log('[PIAnalysis] confirmMapping - 加载 XLSX 库')
      const XLSX = await loadXLSX()

      const workbook = XLSX.read(rawArrayBuffer.value, {
        type: 'array',
        cellDates: false,
        cellFormula: false,
        cellHTML: false,
        cellStyles: false
      })

      const worksheet = workbook.Sheets[workbook.SheetNames[0]]
      const rawHeaders = XLSX.utils.sheet_to_json(worksheet, { header: 1 })[0] || []
      const timeColIdx = rawHeaders.findIndex(h => h !== undefined && h !== null && String(h).trim() === mapping.value.time)
      const metricColumns = availableMetrics.value
        .map((name) => ({
          name,
          colIdx: rawHeaders.findIndex(h => h !== undefined && h !== null && String(h).trim() === name)
        }))
        .filter(item => item.colIdx >= 0)
      console.log('[PIAnalysis] confirmMapping - 原始列索引:', { timeColIdx, metricColumns })

      parseProgress.value = 20

      const allRows = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: null, raw: false })
      const totalRows = allRows.length
      console.log('[PIAnalysis] confirmMapping - 总行数:', totalRows)

      const slimData = []
      const batchSize = 5000
      let processed = 0
      let lastYield = performance.now()

      for (let r = 1; r < totalRows; r++) {
        const row = allRows[r]
        if (!row) continue

        const timeCell = row[timeColIdx]
        const metrics = {}
        let hasAnyMetric = false
        metricColumns.forEach(({ name, colIdx }) => {
          const value = coerceNumericValue(row[colIdx])
          metrics[name] = value
          if (value !== null) hasAnyMetric = true
        })

        if (!timeCell && !hasAnyMetric) continue

        slimData.push({
          t: timeCell !== null && timeCell !== undefined ? String(timeCell) : String(r),
          metrics
        })

        processed++
        if (processed % batchSize === 0) {
          parseProgress.value = 20 + Math.floor((processed / totalRows) * 60)
        }

        if (performance.now() - lastYield > 16) {
          await new Promise(resolve => requestAnimationFrame(resolve))
          lastYield = performance.now()
        }
      }

      parseProgress.value = 85

      let max = -Infinity, min = Infinity, sum = 0, validCount = 0
      for (let i = 0; i < slimData.length; i++) {
        const val = getMetricValue(slimData[i], activeMetricId.value || mapping.value.values[0] || metricColumns[0]?.name)
        if (val !== null) {
          if (val > max) max = val
          if (val < min) min = val
          sum += val
          validCount++
        }
      }

      const stats = {
        max: max === -Infinity ? 0 : max,
        min: min === Infinity ? 0 : min,
        avg: validCount === 0 ? 0 : (sum / validCount)
      }

      parseProgress.value = 95

      fullData = slimData
      selectedMetricIds.value = mapping.value.values.filter(name => availableMetrics.value.includes(name))
      if (!selectedMetricIds.value.length) {
        selectedMetricIds.value = availableMetrics.value.slice(0, 1)
      }
      syncActiveMetric(selectedMetricIds.value[0] || metricColumns[0]?.name || '')
      showMapping.value = false
      zoomHistory.value = []
      isProcessing.value = false
      parseProgress.value = 0
      console.log('[PIAnalysis] confirmMapping - 解析完成, 数据点数:', slimData.length)

      updateView(timeRange.value, null)
      nextTick(() => renderChart())

    } catch (err) {
      console.error('[PIAnalysis] confirmMapping - 解析错误:', err)
      errorMessage.value = '解析失败: ' + err.message
      isProcessing.value = false
    }
  })
}

function renderChart() {
  console.log('[PIAnalysis] renderChart - 开始渲染')
  if (!chartCanvas.value || !chartWrapper.value) {
    console.log('[PIAnalysis] renderChart - canvas 或 wrapper 不存在')
    return
  }

  if (mainChart) {
    mainChart.destroy()
  }

  const ctx = chartCanvas.value.getContext('2d')
  console.log('[PIAnalysis] renderChart - 数据点数:', viewState.value.chartData.length)
  const datasets = selectedMetricIds.value.map((metricId, index) => {
    const color = getMetricColor(metricId, index)
    const isActive = metricId === activeMetricId.value
    return {
      metricId,
      label: metricId,
      data: viewState.value.chartData.map(d => ({ x: d.time, y: d.metrics?.[metricId] ?? null })),
      borderColor: color,
      backgroundColor: isActive ? `${color}22` : `${color}10`,
      borderWidth: isActive ? 2.5 : 2,
      borderDash: metricId === 'EGOX预测值' ? [6, 4] : [],
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.16,
      fill: false,
      spanGaps: true
    }
  })

  mainChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: viewState.value.chartData.map(d => d.time),
      datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index'
      },
      plugins: {
        legend: {
          display: datasets.length > 1,
          position: 'bottom',
          labels: {
            usePointStyle: true,
            boxWidth: 8,
            boxHeight: 8,
            color: '#475569',
            font: { size: 11, weight: 'bold', family: 'Arial' }
          }
        },
        tooltip: {
          enabled: true,
          backgroundColor: '#e3e3e3',
          titleColor: '#1f1f1f',
          bodyColor: '#1f1f1f',
          borderColor: '#4f4f4f',
          borderWidth: 1,
          titleFont: { weight: 'bold', size: 11, family: 'Arial' },
          bodyFont: { weight: 'bold', size: 13, family: 'Arial' },
          padding: 8,
          cornerRadius: 2,
          callbacks: {
            title: (items) => items[0]?.label || '',
            label: (item) => {
              const value = Number(item.parsed?.y)
              return ` ${item.dataset.label}: ${Number.isFinite(value) ? value.toFixed(2) : '-'} units`
            }
          }
        }
      },
      scales: {
        x: {
          display: true,
          grid: {
            color: '#d0d0d0'
          },
          ticks: {
            maxTicksLimit: 10,
            font: { size: 10, weight: 'bold' },
            color: '#4b4b4b'
          }
        },
        y: {
          display: true,
          grid: {
            color: '#d0d0d0'
          },
          ticks: {
            font: { size: 10, weight: 'bold' },
            color: '#4b4b4b'
          }
        }
      }
    }
  })
}

function handleMouseDown(e) {
  if (!chartCanvas.value) return
  const rect = chartCanvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const chartArea = mainChart?.chartArea
  if (!chartArea || x < chartArea.left || x > chartArea.right || y < chartArea.top || y > chartArea.bottom) return

  const absIdx = getAbsIdxFromX(e.clientX)
  const dataPoint = viewState.value.chartData.find(d => d._absIdx === absIdx)
  if (dataPoint) {
    refAreaLeft.value = { absIdx, time: dataPoint.time }
  }
}

function handleMouseMove(e) {
  if (!refAreaLeft.value || !chartCanvas.value) return
  const rect = chartCanvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const absIdx = getAbsIdxFromX(e.clientX)
  const dataPoint = viewState.value.chartData.find(d => d._absIdx === absIdx)
  if (dataPoint) {
    refAreaRight.value = { absIdx, time: dataPoint.time }
  }
}

function handleMouseUp() {
  if (refAreaLeft.value && refAreaRight.value) {
    let leftIdx = refAreaLeft.value.absIdx
    let rightIdx = refAreaRight.value.absIdx

    if (leftIdx > rightIdx) {
      [leftIdx, rightIdx] = [rightIdx, leftIdx]
    }

    if (rightIdx - leftIdx > 5) {
      zoomHistory.value = [...zoomHistory.value, [leftIdx, rightIdx]]
    }
  }
  refAreaLeft.value = null
  refAreaRight.value = null
}

function getTimeRangeBaseBounds() {
  if (!fullData.length) return [0, 0]
  if (timeRange.value === 'all') return [0, fullData.length - 1]
  const rowMap = {
    '5m': 12 * 5,
    '30m': 12 * 30,
    '1h': 12 * 60,
    '2h': 12 * 120,
    '5h': 12 * 300,
    '12h': 12 * 720,
    '24h': 12 * 1440
  }
  const takeCount = rowMap[timeRange.value] || fullData.length
  const start = Math.max(0, fullData.length - takeCount)
  return [start, fullData.length - 1]
}

function getCurrentZoomBounds() {
  if (zoomHistory.value.length > 0) return zoomHistory.value[zoomHistory.value.length - 1]
  return getTimeRangeBaseBounds()
}

function setWheelZoomBounds(leftIdx, rightIdx) {
  const [baseLeft, baseRight] = getTimeRangeBaseBounds()
  const nextLeft = Math.max(baseLeft, Math.min(baseRight, Math.round(leftIdx)))
  const nextRight = Math.max(nextLeft, Math.min(baseRight, Math.round(rightIdx)))
  const nextRange = [nextLeft, nextRight]
  if (nextLeft <= baseLeft && nextRight >= baseRight) {
    zoomHistory.value = []
    return
  }
  if (zoomHistory.value.length > 0) {
    zoomHistory.value = [...zoomHistory.value.slice(0, -1), nextRange]
  } else {
    zoomHistory.value = [nextRange]
  }
}

function handleChartWheel(e) {
  if (!mainChart || !chartCanvas.value || !fullData.length) return
  const chartArea = mainChart.chartArea
  if (!chartArea) return

  const rect = chartCanvas.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  if (x < chartArea.left || x > chartArea.right || y < chartArea.top || y > chartArea.bottom) return

  const [baseLeft, baseRight] = getTimeRangeBaseBounds()
  const [currentLeft, currentRight] = getCurrentZoomBounds()
  const baseSize = Math.max(1, baseRight - baseLeft + 1)
  const currentSize = Math.max(1, currentRight - currentLeft + 1)
  if (baseSize <= MIN_WHEEL_ZOOM_POINTS) return

  const ratio = Math.max(0, Math.min(1, (x - chartArea.left) / Math.max(1, chartArea.right - chartArea.left)))
  const center = currentLeft + ratio * Math.max(1, currentSize - 1)
  const zoomingIn = e.deltaY < 0
  const targetSize = zoomingIn
    ? Math.max(MIN_WHEEL_ZOOM_POINTS, Math.round(currentSize * 0.72))
    : Math.min(baseSize, Math.round(currentSize * 1.35))

  let nextLeft = Math.round(center - targetSize * ratio)
  let nextRight = nextLeft + targetSize - 1
  if (nextLeft < baseLeft) {
    nextRight += baseLeft - nextLeft
    nextLeft = baseLeft
  }
  if (nextRight > baseRight) {
    nextLeft -= nextRight - baseRight
    nextRight = baseRight
  }
  setWheelZoomBounds(nextLeft, nextRight)
}

function getAbsIdxFromX(clientX) {
  if (!chartCanvas.value || !mainChart) return 0
  const rect = chartCanvas.value.getBoundingClientRect()
  const x = clientX - rect.left
  const chartArea = mainChart.chartArea
  const totalWidth = chartArea.right - chartArea.left
  const ratio = (x - chartArea.left) / totalWidth
  const dataIdx = Math.floor(ratio * viewState.value.chartData.length)
  const clampedIdx = Math.max(0, Math.min(viewState.value.chartData.length - 1, dataIdx))
  return viewState.value.chartData[clampedIdx]?._absIdx || 0
}

function handleTimeRangeChange(id) {
  zoomHistory.value = []
  timeRange.value = id
}

function zoomOut() {
  zoomHistory.value = zoomHistory.value.slice(0, -1)
}

function zoomReset() {
  zoomHistory.value = []
}

async function runRollingScan() {
  analyzing.value = true
  nitrogenResult.value = null

  try {
    if (!fullData.length) {
      errorMessage.value = '请先导入历史时序数据'
      return
    }
    if (windowLengthMin.value < 10) {
      errorMessage.value = '稳态判断窗口不能小于 10 min，建议 15 min 或 30 min'
      return
    }

    const windows = getRollingWindows()
    if (!windows.length) {
      errorMessage.value = '数据时长不足，无法形成完整分析窗口'
      return
    }

    const results = windows.map((windowItem, index) => evaluateNitrogenWindow(windowItem, index))
    rollingResults.value = results
    const firstAbnormal = results.find(item => item.isAbnormal)
    const active = firstAbnormal || results[results.length - 1]
    activeWindowIndex.value = active.index
    nitrogenResult.value = active
    ElMessage.success(`完成 ${results.length} 个窗口扫描，异常窗口 ${results.filter(item => item.isAbnormal).length} 个`)
  } catch (error) {
    errorMessage.value = `滚动扫描失败: ${error.message}`
  } finally {
    analyzing.value = false
  }
}

watch(selectedAnalysisIds, (ids) => {
  ids.forEach(id => ensureAnalysisLoaded(id))
}, { immediate: true })

watch(selectedMetricIds, (ids, previous = []) => {
  if (!ids.length) {
    const fallback = previous?.[0] || availableMetrics.value[0]
    if (fallback) {
      selectedMetricIds.value = [fallback]
      ElMessage.warning('至少保留一个显示指标')
    }
    return
  }
  syncActiveMetric(ids[0])
  if (fullData.length > 0) {
    const currentZoom = zoomHistory.value.length > 0 ? zoomHistory.value[zoomHistory.value.length - 1] : null
    updateView(timeRange.value, currentZoom)
    nextTick(() => renderChart())
  }
}, { deep: true })

watch([timeRange, zoomHistory, activeMetricId], () => {
  console.log('[PIAnalysis] watch - timeRange/zoomHistory/activeMetric 变化', { timeRange: timeRange.value, zoomHistory: zoomHistory.value, activeMetric: activeMetricId.value })
  if (fullData.length > 0) {
    const currentZoom = zoomHistory.value.length > 0 ? zoomHistory.value[zoomHistory.value.length - 1] : null
    updateView(timeRange.value, currentZoom)
    nextTick(() => renderChart())
  }
}, { deep: true })

onMounted(() => {
  visibleAnalysisItems.value.forEach(item => ensureAnalysisLoaded(item.id))
})
</script>

<style scoped>
.dcs-page {
  --dcs-bg: #061b2b;
  --dcs-screen: #082c42;
  --dcs-panel: #0b344d;
  --dcs-head: #123f5b;
  --dcs-line: #5f8298;
  --dcs-text: #d9edf8;
  --dcs-muted: #91adbf;
  --dcs-blue: #1d5d89;
  --dcs-button: #d8d7d1;
  height: 100vh;
  height: 100dvh;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  background: var(--dcs-bg);
  color: var(--dcs-text);
  font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
  font-size: 13px;
}

.dcs-topbar {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 4px;
  padding: 5px 6px;
  background: #041525;
  border-bottom: 2px solid #000;
}

.topbar-title-block,
.status-strip,
.dcs-panel {
  border: 1px solid var(--dcs-line);
  border-radius: 0;
  background: var(--dcs-panel);
}

.topbar-title-block {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 7px 10px;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.03);
}

.back-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #89a9bd;
  border-radius: 0;
  background: #0d2f46;
  color: var(--dcs-text);
}

.back-btn svg {
  width: 17px;
  height: 17px;
}

h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.15;
}

.topbar-subtitle,
.cell-label,
.tag-name,
.point-name,
.warning-row p,
.evidence-block p,
.operation-step p,
.empty-text {
  color: var(--dcs-muted);
}

.topbar-subtitle {
  margin-top: 3px;
  font-size: 12px;
}

.status-strip {
  display: grid;
  grid-template-columns: 1.1fr .9fr .8fr 1fr .75fr .8fr auto;
  align-items: stretch;
  min-width: 0;
}

.status-cell {
  display: grid;
  align-content: center;
  gap: 3px;
  min-width: 0;
  padding: 5px 10px;
  border-right: 1px solid var(--dcs-line);
}

.status-cell strong {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-label {
  font-size: 11px;
}

.dcs-button,
.upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 31px;
  padding: 0 13px;
  border: 1px solid #89a9bd;
  border-radius: 0;
  background: #123a54;
  color: var(--dcs-text);
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.dcs-button.primary,
.upload-btn {
  background: #2f7fbd;
  color: #fff;
}

.hidden-input {
  display: none;
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 8px 0;
  padding: 7px 10px;
  border: 1px solid #a00000;
  background: #f4d0cf;
  color: #a00000;
  font-weight: 700;
}

.error-banner button {
  border: 1px solid #4f4f4f;
  background: #dcdcdc;
  color: #1f1f1f;
  cursor: pointer;
}

.dcs-grid {
  display: grid;
  grid-template-columns: 200px minmax(760px, 1fr) 280px;
  grid-template-rows: minmax(0, 1fr) 168px;
  gap: 4px;
  min-height: 0;
  height: 100%;
  padding: 4px 6px 6px;
  box-sizing: border-box;
  overflow: hidden;
}

.dcs-panel {
  min-width: 0;
  min-height: 0;
  border-radius: 0;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.025);
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 26px;
  padding: 0 8px;
  border-bottom: 1px solid var(--dcs-line);
  background: var(--dcs-head);
  color: #edf7ff;
  font-size: 14px;
  font-weight: 700;
}

.left-nav,
.right-assist,
.main-monitor {
  min-height: 0;
}

.left-nav {
  display: flex;
  flex-direction: column;
  grid-row: 1 / 2;
}

.tree-list {
  flex: 1;
  overflow: auto;
  padding: 5px;
  scrollbar-width: thin;
  scrollbar-color: #b9c3c8 #173a4e;
}

.tree-group {
  margin-bottom: 5px;
  border: 1px solid #3f657a;
  background: #0b3048;
}

.tree-group-title {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 6px;
  align-items: center;
  padding: 5px 6px;
  border-bottom: 1px solid #3f657a;
  background: #143f59;
  font-size: 13px;
}

.point-row {
  display: grid;
  grid-template-columns: 18px 56px 1fr;
  gap: 5px;
  align-items: center;
  min-height: 25px;
  padding: 2px 6px;
  border-bottom: 1px solid rgba(86, 113, 132, .55);
  cursor: pointer;
}

.point-row:last-child {
  border-bottom: none;
}

.point-row input {
  accent-color: #2e75b6;
}

.point-row input:disabled + .point-tag,
.point-row input:disabled ~ .point-name {
  color: #8a8a8a;
}

.point-tag {
  font-family: Arial, "Segoe UI", sans-serif;
  font-weight: 700;
}

.nav-footer {
  display: flex;
  justify-content: space-between;
  padding: 7px;
  border-top: 1px solid var(--dcs-line);
  background: var(--dcs-head);
}

.main-monitor {
  display: grid;
  grid-template-rows: minmax(360px, 1.35fr) minmax(150px, .65fr);
  gap: 4px;
  min-height: 0;
}

.process-and-tags {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
  min-height: 0;
}

.process-panel,
.tag-panel,
.trend-panel {
  overflow: hidden;
}

.tag-panel {
  display: none;
}

.process-canvas {
  position: relative;
  height: calc(100% - 27px);
  min-height: 0;
  overflow: hidden;
}

.dcs-line {
  position: absolute;
  height: 3px;
  transform-origin: left center;
}

.dcs-line::after {
  content: '';
  position: absolute;
  right: -1px;
  top: -4px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 18px solid currentColor;
}

.dcs-line.white { background: #d7e8f5; color: #d7e8f5; box-shadow: 0 0 2px rgba(255,255,255,.35); }
.dcs-line.magenta { background: #e000d7; color: #e000d7; }
.feed-air { left: 5%; top: 17%; width: 53%; }
.reflux-air { left: 5%; top: 36%; width: 52%; transform: rotate(180deg); }
.argon-feed { left: 5%; top: 69%; width: 54%; }
.product-gas { left: 64%; top: 43%; width: 30%; }
.waste-line { left: 5%; top: 84%; width: 43%; transform: rotate(180deg); }

.line-label {
  position: absolute;
  color: var(--dcs-text);
  font-size: 12px;
  font-weight: 700;
  text-shadow: 0 1px 0 #000;
}

.l1 { left: 5%; top: 9%; }
.l2 { left: 5%; top: 29%; }
.l3 { left: 5%; top: 61%; }
.l4 { right: 4%; top: 36%; }
.l5 { left: 5%; top: 76%; }

.tower {
  position: absolute;
  left: 57%;
  top: 14%;
  width: 74px;
  height: 72%;
  border-radius: 40px;
  background: #b9bec0;
  border: 2px solid #7e8689;
  color: #101820;
  overflow: hidden;
  box-shadow: 0 0 0 1px #000;
}

.tower-top,
.tower-section,
.tower-pack,
.tower-liquid {
  position: absolute;
  left: 0;
  right: 0;
}

.tower-top { top: 0; height: 18%; border-bottom: 2px solid #697174; }
.tower-section { top: 18%; height: 24%; display: grid; place-items: center; font-weight: 800; }
.tower-section.lower { top: 62%; height: 25%; border-top: 2px solid #697174; }
.tower-pack { top: 42%; height: 20%; border-top: 2px solid #697174; border-bottom: 2px solid #697174; background: linear-gradient(135deg, transparent 47%, #697174 48%, #697174 52%, transparent 53%), linear-gradient(45deg, transparent 47%, #697174 48%, #697174 52%, transparent 53%); }
.tower-liquid { left: 25%; right: 25%; bottom: 8%; height: 13%; background: #d300c8; border: 1px solid #555; }

.valve {
  position: absolute;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.valve::before,
.valve::after {
  content: '';
  position: absolute;
  top: 4px;
  width: 0;
  height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
}

.valve::before { left: 1px; border-right: 9px solid currentColor; }
.valve::after { right: 1px; border-left: 9px solid currentColor; }
.valve.green { color: #00ff28; background: #00ff28; }
.valve.red { color: #ff1717; background: #ff1717; }
.valve.gray { color: #c0c4c7; background: #c0c4c7; }
.v1 { left: 21%; top: 17%; }
.v2 { left: 26%; top: 69%; }
.v3 { left: 82%; top: 43%; }
.v4 { left: 70%; top: 84%; }
.v5 { left: 14%; top: 84%; }

.instrument {
  position: absolute;
  display: grid;
  grid-template-columns: 1fr auto;
  min-width: 74px;
  color: var(--dcs-text);
  font-family: Arial, "Segoe UI", sans-serif;
  font-size: 11px;
}

.instrument span {
  grid-column: 1 / 3;
  color: #88a8bd;
  font-weight: 700;
}

.instrument strong {
  min-width: 42px;
  padding: 2px 6px;
  background: var(--dcs-blue);
  color: var(--dcs-text);
  text-align: center;
}

.instrument em {
  padding-left: 5px;
  color: var(--dcs-text);
  font-style: normal;
}

.i1 { left: 22%; top: 19%; }
.i2 { left: 35%; top: 12%; }
.i3 { left: 34%; top: 34%; }
.i4 { left: 20%; top: 62%; }
.i5 { left: 72%; top: 48%; }
.i6 { left: 66%; top: 23%; }
.i7 { left: 68%; top: 76%; }
.i8 { left: 50%; top: 54%; }

.tag-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px;
  padding: 5px;
}

.tag-box {
  min-height: 60px;
  padding: 5px 6px;
  border: 1px solid var(--dcs-line);
  background: #0b3048;
}

.tag-box.warning,
.tag-box.alarm {
  border-color: #a00000;
}

.tag-top,
.tag-value,
.trend-controls,
.trend-tabs,
.warning-row {
  display: flex;
  align-items: center;
}

.tag-top,
.tag-value {
  justify-content: space-between;
  gap: 8px;
}

.tag-top strong,
.tag-value span {
  font-family: Arial, "Segoe UI", sans-serif;
}

.tag-top strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-name {
  margin-top: 5px;
  font-size: 12px;
}

.tag-value {
  margin-top: 7px;
}

.tag-value span {
  font-size: 19px;
  font-weight: 700;
}

.tag-value em {
  font-style: normal;
  color: var(--dcs-muted);
}

.state-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
}

.state-label i {
  width: 9px;
  height: 9px;
  border: 1px solid #89a9bd;
  background: #8a8a8a;
}

.state-label.ok i,
.tag-box.ok .state-label i { background: #1fa64a; }
.state-label.observe i,
.tag-box.observe .state-label i { background: #d9a300; }
.state-label.warning i,
.tag-box.warning .state-label i { background: #e67e22; }
.state-label.alarm i,
.tag-box.alarm .state-label i { background: #d64541; }
.state-label.invalid i,
.tag-box.invalid .state-label i { background: #8a8a8a; }
.state-label.mini { font-size: 11px; }

.trend-panel {
  display: flex;
  flex-direction: column;
}

.trend-title {
  gap: 8px;
}

.trend-context {
  color: var(--dcs-muted);
  font-size: 12px;
  font-weight: 400;
}

.trend-tabs {
  gap: 4px;
  padding: 5px 6px 0;
}

.dcs-tab {
  min-height: 26px;
  padding: 0 11px;
  border: 1px solid var(--dcs-line);
  border-radius: 0;
  background: #123a54;
  color: var(--dcs-text);
  cursor: pointer;
  font-weight: 700;
}

.dcs-tab.active {
  background: #2f7fbd;
  border-color: #2f7fbd;
  color: #fff;
}

.trend-controls {
  justify-content: space-between;
  gap: 8px;
  padding: 5px 6px;
  border-bottom: 1px solid var(--dcs-line);
}

.metric-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.selector-label {
  white-space: nowrap;
  color: var(--dcs-muted);
  font-weight: 700;
}

.time-range-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.chart-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 5px;
  border: 1px solid var(--dcs-line);
  background: var(--dcs-screen);
}

.chart-wrapper canvas {
  position: relative;
  z-index: 2;
  cursor: crosshair;
}

.abnormal-band {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 1;
  pointer-events: none;
}

.abnormal-band.observe {
  left: 62%;
  width: 11%;
  background: rgba(217, 163, 0, .18);
}

.abnormal-band.alarm {
  left: 80%;
  width: 8%;
  background: rgba(214, 69, 65, .16);
}

.selection-overlay {
  position: absolute;
  z-index: 3;
  background: rgba(46, 117, 182, .16);
  border: 1px dashed #2e75b6;
  pointer-events: none;
}

.right-assist {
  display: grid;
  grid-template-rows: .55fr .78fr 1.67fr;
  gap: 4px;
  min-height: 0;
}

.warning-list,
.evidence-panel,
.operation-panel {
  overflow: auto;
}

.warning-list {
  display: grid;
  gap: 5px;
  padding: 5px;
}

.warning-row {
  display: grid;
  grid-template-columns: 50px 1fr auto;
  gap: 7px;
  align-items: start;
  padding: 5px;
  border: 1px solid var(--dcs-line);
  background: #0d3148;
}

.warning-row.observe { background: #3d360c; }
.warning-row.warning { background: #4a280b; }
.warning-row.alarm { background: #4a1518; }
.warning-row.invalid { color: #6f6f6f; }

.alarm-level {
  display: inline-flex;
  justify-content: center;
  border: 1px solid #89a9bd;
  background: var(--dcs-head);
  font-weight: 700;
}

.warning-row strong,
.warning-row p {
  display: block;
  margin: 0;
  line-height: 1.45;
  min-width: 0;
  overflow-wrap: anywhere;
}

.warning-row time {
  color: var(--dcs-muted);
  font-family: Arial, "Segoe UI", sans-serif;
  font-size: 11px;
}

.evidence-block,
.operation-step {
  margin: 4px 5px;
  padding: 5px 6px;
  border: 1px solid var(--dcs-line);
  background: #0d3148;
}

.evidence-block strong,
.operation-step span {
  display: block;
  margin-bottom: 3px;
  font-weight: 700;
}

.evidence-block p,
.operation-step p {
  margin: 0;
  line-height: 1.38;
  font-size: 12px;
}

.operation-panel :deep(.el-button) {
  min-height: 30px;
  margin: 4px 5px;
  width: calc(100% - 10px);
}

.scan-control-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  padding: 5px;
}

.scan-control-grid label {
  display: grid;
  gap: 3px;
  color: var(--dcs-muted);
  font-size: 12px;
  font-weight: 700;
}

.scan-control-grid select {
  min-width: 0;
  height: 28px;
  border: 1px solid #8e9aa0;
  background: #d8dde0;
  color: #17222a;
  font-weight: 800;
}

.advice-box {
  margin: 5px;
  padding: 6px;
  border: 1px solid #2e5368;
  background: #0d3148;
}

.advice-box strong {
  display: block;
  margin-bottom: 4px;
}

.advice-box p {
  margin: 0;
  line-height: 1.4;
  font-size: 12px;
}

.bottom-events {
  grid-column: 1 / 4;
  display: grid;
  grid-template-columns: 1fr 1.35fr .85fr;
  grid-template-rows: minmax(0, 1fr) 34px;
  gap: 0;
  overflow: hidden;
  position: relative;
}

.bottom-column {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  border-right: 1px solid var(--dcs-line);
}

.bottom-column:last-child {
  border-right: none;
}

.event-line {
  padding: 5px 6px;
}

.event-item {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 8px;
  min-height: 24px;
  align-items: center;
  border-bottom: 1px solid #2e5368;
}

.event-item time,
.dcs-table td:first-child {
  font-family: Arial, "Segoe UI", sans-serif;
  color: var(--dcs-muted);
}

.dcs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.dcs-table th,
.dcs-table td {
  padding: 4px 7px;
  border: 1px solid #2e5368;
  text-align: left;
}

.dcs-table th {
  background: var(--dcs-head);
  font-weight: 700;
}

.case-json pre {
  margin: 0;
  padding: 6px 8px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 10px;
  line-height: 1.12;
  white-space: pre-wrap;
}

.task-summary {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px 10px;
  padding: 14px 16px;
  font-family: Arial, "Segoe UI", sans-serif;
}

.task-summary span {
  color: var(--dcs-muted);
  font-weight: 800;
}

.task-summary strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dcs-text);
  font-size: 16px;
}

.operator-clock,
.operator-nav,
.operator-now {
  min-height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-top: 1px solid var(--dcs-line);
  background: #08263c;
  color: var(--dcs-text);
  font-family: Arial, "Segoe UI", sans-serif;
  font-weight: 700;
}

.operator-clock {
  grid-column: 1 / 2;
  grid-row: 2 / 3;
  margin: 3px 8px 0;
  border: 1px solid #1b5c78;
  background: #0a3853;
}

.operator-nav {
  grid-column: 2 / 3;
  grid-row: 2 / 3;
  gap: 8px;
  border-left: 1px solid var(--dcs-line);
  border-right: 1px solid var(--dcs-line);
}

.operator-nav button,
.operator-now {
  min-width: 54px;
  height: 28px;
  border: 1px solid #8e9aa0;
  border-radius: 0;
  background: var(--dcs-button);
  color: #17222a;
  cursor: pointer;
}

.operator-now {
  grid-column: 3 / 4;
  grid-row: 2 / 3;
  justify-self: center;
  align-self: center;
  min-width: 74px;
  background: #22a63d;
  color: #fff;
}

.dcs-page :deep(.el-button),
.dcs-page :deep(.el-radio-button__inner),
.dcs-page :deep(.el-input__wrapper),
.dcs-page :deep(.el-select__wrapper) {
  border-radius: 0;
}

.dcs-page :deep(.el-button) {
  min-height: 28px;
  border-color: #8e9aa0;
  background: var(--dcs-button);
  color: #17222a;
  font-weight: 800;
}

.dcs-page :deep(.el-button--primary),
.dcs-page :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: #2f7fbd;
  background: #2f7fbd;
  color: #fff;
}

.tree-list::-webkit-scrollbar,
.warning-list::-webkit-scrollbar,
.evidence-panel::-webkit-scrollbar,
.operation-panel::-webkit-scrollbar,
.bottom-column::-webkit-scrollbar {
  width: 12px;
}

.tree-list::-webkit-scrollbar-track,
.warning-list::-webkit-scrollbar-track,
.evidence-panel::-webkit-scrollbar-track,
.operation-panel::-webkit-scrollbar-track,
.bottom-column::-webkit-scrollbar-track {
  background: #173a4e;
}

.tree-list::-webkit-scrollbar-thumb,
.warning-list::-webkit-scrollbar-thumb,
.evidence-panel::-webkit-scrollbar-thumb,
.operation-panel::-webkit-scrollbar-thumb,
.bottom-column::-webkit-scrollbar-thumb {
  border: 2px solid #173a4e;
  background: #b9c3c8;
}

.empty-state {
  display: grid;
  place-content: center;
  min-height: 220px;
  text-align: center;
}

.empty-title {
  margin-bottom: 5px;
  font-size: 16px;
  font-weight: 700;
}

.mapping-overlay,
.loading-state {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(79, 79, 79, .38);
}

.mapping-dialog {
  width: min(520px, calc(100vw - 32px));
}

.mapping-body {
  display: grid;
  gap: 14px;
  padding: 12px;
}

.mapping-field label {
  display: block;
  margin-bottom: 5px;
  color: #4b4b4b;
  font-weight: 700;
}

.loading-state {
  flex-direction: column;
  gap: 12px;
  font-weight: 700;
}

.loading-spinner {
  width: 42px;
  height: 42px;
  border: 5px solid #dcdcdc;
  border-top-color: #2e75b6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.parse-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 240px;
}

.progress-bar {
  flex: 1;
  height: 10px;
  border: 1px solid #4f4f4f;
  background: #dcdcdc;
}

.progress-fill {
  height: 100%;
  background: #2e75b6;
}

@media (max-width: 940px) {
  .dcs-topbar,
  .dcs-grid,
  .process-and-tags,
  .bottom-events {
    grid-template-columns: 1fr;
  }

  .status-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .dcs-grid {
    grid-template-rows: auto;
  }

  .bottom-events {
    grid-column: auto;
  }

  .left-nav,
  .main-monitor,
  .right-assist,
  .bottom-events {
    grid-column: auto;
  }
}

@media (max-width: 760px) {
  .status-strip {
    grid-template-columns: 1fr;
  }

  .main-monitor {
    grid-template-rows: auto;
  }

  .tag-grid {
    grid-template-columns: 1fr;
  }

  .trend-controls {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
