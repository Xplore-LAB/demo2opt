<template>
  <section class="scan-panel">
    <div class="scan-title">
      <div>
        <strong>滑动窗口扫描 + 氮塞诊断输出</strong>
        <span>历史数据按时间排序后滚动计算，异常窗口进入溯源区</span>
      </div>
      <label class="file-btn">
        导入 Excel / CSV
        <input type="file" accept=".csv,.xlsx,.xls" @change="handleFile" />
      </label>
    </div>

    <div class="scan-controls">
      <label>
        时间列
        <select v-model="timeColumn">
          <option v-for="col in columns" :key="col" :value="col">{{ col }}</option>
        </select>
      </label>
      <label>
        窗口长度
        <select v-model.number="windowLengthMin">
          <option :value="30">30 min</option>
          <option :value="15">15 min</option>
          <option :value="10">10 min</option>
        </select>
      </label>
      <label>
        滑动步长
        <input v-model.number="slideStepMin" type="number" min="1" />
      </label>
      <button type="button" @click="runScan" :disabled="!sortedRows.length">执行扫描</button>
      <div class="data-state">
        <span>数据行：{{ sortedRows.length }}</span>
        <span>窗口：{{ scanResults.length }}</span>
        <span>氮塞：{{ abnormalCount }}</span>
      </div>
    </div>

    <div v-if="message" class="scan-message">{{ message }}</div>

    <div class="scan-grid">
      <div class="result-table">
        <div class="table-head">
          <span>窗口</span>
          <span>氮塞区间</span>
          <span>等级</span>
          <span>触发测点</span>
          <span>关键统计</span>
        </div>
        <button
          v-for="result in scanResults"
          :key="result.id"
          type="button"
          class="table-row"
          :class="{ active: result.id === activeResultId, danger: result.suspected }"
          @click="activeResultId = result.id"
        >
          <span>{{ result.windowLabel }}</span>
          <span>{{ result.suspected ? 'YES' : 'NO' }}</span>
          <span><em :class="result.level">{{ levelText(result.level) }}</em></span>
          <span>{{ result.triggerTags.join(', ') || '-' }}</span>
          <span>{{ result.summary }}</span>
        </button>
        <div v-if="!scanResults.length" class="empty">导入历史数据后执行滑动窗口扫描。</div>
      </div>

      <aside class="rootcause-area">
        <div class="root-title">
          <strong>溯源分析区</strong>
          <span>{{ activeResult?.suspected ? activeResult.windowLabel : '氮塞窗口触发后显示候选原因' }}</span>
        </div>
        <div v-if="activeResult" class="stats-box">
          <div class="stats-title">当前窗口关键变量统计</div>
          <div class="stats-head">
            <span>测点</span><span>均值</span><span>最小</span><span>最大</span><span>首末变化</span>
          </div>
          <div v-for="item in activeStatsRows" :key="item.tag" class="stats-row">
            <span>{{ item.tag }}</span>
            <span>{{ item.mean }}</span>
            <span>{{ item.min }}</span>
            <span>{{ item.max }}</span>
            <span>{{ item.delta }}</span>
          </div>
        </div>
        <div v-if="activeResult?.suspected" class="cause-list">
          <div v-for="cause in activeResult.rootCauses" :key="cause.category" class="cause-card">
            <div class="cause-head">
              <strong>{{ cause.category }}</strong>
              <span>可信度占位：{{ cause.confidence }}</span>
            </div>
            <div class="evidence-line">
              <span>证据测点</span>
              <strong>{{ cause.evidenceTags.join(', ') || '待补充' }}</strong>
            </div>
            <div class="evidence-line">
              <span>判断依据</span>
              <strong>{{ cause.basis }}</strong>
            </div>
            <label class="confirm-line">
              <input v-model="cause.confirmed" type="checkbox" />
              人工确认标记
            </label>
          </div>
        </div>
        <div v-else class="empty">当前选中窗口未达到轻度氮塞标准，无需进入溯源。</div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const windowLengthMin = ref(30)
const slideStepMin = ref(5)
const rawRows = ref([])
const columns = ref([])
const timeColumn = ref('')
const scanResults = ref([])
const activeResultId = ref('')
const message = ref('')

const keyTags = ['AI705', 'PDI701', 'LIC702', 'FI701', 'FIC701', 'FIQC102', 'AIAS102', 'V3', 'TD_AR_COND', 'AN_N2_AR_FRACTION']

const sortedRows = computed(() => {
  if (!timeColumn.value) return []
  return rawRows.value
    .map((row) => ({ ...row, __time: parseTime(row[timeColumn.value]) }))
    .filter((row) => Number.isFinite(row.__time))
    .sort((a, b) => a.__time - b.__time)
})

const activeResult = computed(() => scanResults.value.find((item) => item.id === activeResultId.value) || scanResults.value[0])
const abnormalCount = computed(() => scanResults.value.filter((item) => item.suspected).length)
const activeStatsRows = computed(() => {
  if (!activeResult.value?.stats) return []
  return keyTags
    .map((tag) => ({ tag, stats: activeResult.value.stats[tag] }))
    .filter((item) => item.stats?.valid)
    .map(({ tag, stats }) => ({
      tag,
      mean: formatStat(stats.mean),
      min: formatStat(stats.min),
      max: formatStat(stats.max),
      delta: formatNumber(stats.delta)
    }))
})

async function handleFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  message.value = ''
  try {
    const rows = file.name.toLowerCase().endsWith('.csv')
      ? parseCsv(await file.text())
      : await parseExcel(file)
    rawRows.value = rows
    columns.value = rows.length ? Object.keys(rows[0]) : []
    timeColumn.value = guessTimeColumn(columns.value)
    scanResults.value = []
    activeResultId.value = ''
    message.value = `已导入 ${rows.length} 行，时间列识别为 ${timeColumn.value || '未识别'}。`
  } catch (error) {
    message.value = `导入失败：${error.message}`
  } finally {
    event.target.value = ''
  }
}

async function parseExcel(file) {
  const XLSX = await loadXlsx()
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array' })
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  return XLSX.utils.sheet_to_json(sheet, { defval: '' })
}

function loadXlsx() {
  if (window.XLSX) return Promise.resolve(window.XLSX)
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
    script.onload = () => resolve(window.XLSX)
    script.onerror = () => reject(new Error('Excel 解析库加载失败，可先导入 CSV。'))
    document.head.appendChild(script)
  })
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean)
  if (!lines.length) return []
  const headers = splitCsvLine(lines[0]).map((item) => item.trim())
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line)
    return headers.reduce((row, key, index) => {
      row[key] = values[index] ?? ''
      return row
    }, {})
  })
}

function splitCsvLine(line) {
  const cells = []
  let current = ''
  let quoted = false
  for (const char of line) {
    if (char === '"') quoted = !quoted
    else if (char === ',' && !quoted) {
      cells.push(current)
      current = ''
    } else current += char
  }
  cells.push(current)
  return cells
}

function runScan() {
  if (!sortedRows.value.length) {
    message.value = '请先导入包含时间列的历史 Excel/CSV 数据。'
    return
  }
  const windows = buildWindows(sortedRows.value, windowLengthMin.value, slideStepMin.value)
  scanResults.value = windows.map(evaluateWindow)
  activeResultId.value = scanResults.value.find((item) => item.suspected)?.id || scanResults.value[0]?.id || ''
  message.value = `完成 ${scanResults.value.length} 个窗口扫描，氮塞区间 ${abnormalCount.value} 个。`
}

function buildWindows(rows, lengthMin, stepMin) {
  const lengthMs = lengthMin * 60 * 1000
  const stepMs = stepMin * 60 * 1000
  const start = rows[0].__time
  const end = rows[rows.length - 1].__time
  const windows = []
  for (let cursor = start; cursor + lengthMs <= end + 1; cursor += stepMs) {
    const slice = rows.filter((row) => row.__time >= cursor && row.__time < cursor + lengthMs)
    if (slice.length) windows.push({ start: cursor, end: cursor + lengthMs, rows: slice })
  }
  return windows
}

function evaluateWindow(windowItem, index) {
  const stats = Object.fromEntries(keyTags.map((tag) => [tag, calcStats(windowItem.rows, tag)]))
  const triggers = []
  const evidence = []
  const directN2 = stats.AN_N2_AR_FRACTION
  if (directN2.valid && directN2.max > 0.1) addTrigger(triggers, evidence, 'AN_N2_AR_FRACTION', '氩馏分含氮量 > 0.1%')
  if (stats.AI705.valid && stats.AI705.delta < 0) addTrigger(triggers, evidence, 'AI705', 'AI705窗口内持续下降')
  const aux = [
    ['PDI701', stats.PDI701.delta < 0, '粗氩塔阻力下降'],
    ['LIC702', stats.LIC702.delta > 0, '液空液位上涨'],
    ['FI701', stats.FI701.delta < 0, '氩馏分流量下降'],
    ['FIC701', stats.FIC701.delta < 0, '粗氩流量下降']
  ].filter(([tag, ok]) => stats[tag]?.valid && ok)
  aux.forEach(([tag, , basis]) => addTrigger(triggers, evidence, tag, basis))
  const mainTower = [
    ['FIQC102', stats.FIQC102.delta > 0, '氧气取出量偏高或继续上升'],
    ['AIAS102', stats.AIAS102.delta < 0, '氧气纯度下降'],
    ['V3', stats.V3.delta > 0, 'V3阀位近期增大']
  ].filter(([tag, ok]) => stats[tag]?.valid && ok)
  mainTower.forEach(([tag, , basis]) => addTrigger(triggers, evidence, tag, basis))
  const suspected = directN2.valid && directN2.max > 0.1 || (stats.AI705.valid && stats.AI705.delta < 0 && aux.length >= 2)
  const level = suspected
    ? (triggers.length >= 5 || directN2.max > 0.1 ? 'high' : 'medium')
    : (triggers.length >= 2 ? 'low' : 'normal')
  return {
    id: `window-${index}-${windowItem.start}`,
    suspected,
    level,
    triggerTags: [...new Set(triggers)],
    evidence,
    stats,
    windowLabel: `${formatTime(windowItem.start)} ~ ${formatTime(windowItem.end)}`,
    summary: buildSummary(stats),
    rootCauses: buildRootCauses(stats, aux, mainTower, evidence)
  }
}

function addTrigger(triggers, evidence, tag, basis) {
  triggers.push(tag)
  evidence.push({ tag, basis })
}

function buildRootCauses(stats, aux, mainTower, evidence) {
  const basisOf = (tags, fallback) => {
    const items = evidence.filter((item) => tags.includes(item.tag)).map((item) => `${item.tag}: ${item.basis}`)
    return items.length ? items.join('；') : fallback
  }
  return [
    {
      category: '粗氩系统',
      evidenceTags: aux.map(([tag]) => tag).concat(stats.AI705.valid && stats.AI705.delta < 0 ? ['AI705'] : []),
      basis: basisOf(['AI705', 'PDI701', 'LIC702', 'FI701', 'FIC701', 'TD_AR_COND'], '等待粗氩塔阻力、液位、流量和冷凝器温差证据。'),
      confidence: '待模型计算',
      confirmed: false
    },
    {
      category: '主塔',
      evidenceTags: mainTower.map(([tag]) => tag),
      basis: basisOf(['FIQC102', 'AIAS102', 'V3'], '等待氧气取出量、氧纯度、V3阀位联动证据。'),
      confidence: '待模型计算',
      confirmed: false
    },
    {
      category: '前端/分子筛',
      evidenceTags: [],
      basis: '预留空压机负荷、空气量、分子筛切换、CO2/H2O穿透等测点判断依据。',
      confidence: '待模型计算',
      confirmed: false
    },
    {
      category: '操作调节',
      evidenceTags: stats.V3.valid ? ['V3'] : [],
      basis: stats.V3.valid && Math.abs(stats.V3.delta) > 0 ? `V3窗口变化 ${formatNumber(stats.V3.delta)}，需结合操作票和阀位记录人工确认。` : '预留氧氮产品取出量、阀位手动调整和负荷调整记录。',
      confidence: '待模型计算',
      confirmed: false
    }
  ]
}

function calcStats(rows, tag) {
  const values = rows.map((row) => toNumber(row[tag])).filter(Number.isFinite)
  if (!values.length) return { valid: false, min: null, max: null, mean: null, first: null, last: null, delta: 0 }
  const sum = values.reduce((acc, value) => acc + value, 0)
  return {
    valid: true,
    min: Math.min(...values),
    max: Math.max(...values),
    mean: sum / values.length,
    first: values[0],
    last: values[values.length - 1],
    delta: values[values.length - 1] - values[0]
  }
}

function buildSummary(stats) {
  const parts = []
  if (stats.AI705.valid) parts.push(`AI705 Δ${formatNumber(stats.AI705.delta)}`)
  if (stats.PDI701.valid) parts.push(`PDI701 Δ${formatNumber(stats.PDI701.delta)}`)
  if (stats.LIC702.valid) parts.push(`LIC702 Δ${formatNumber(stats.LIC702.delta)}`)
  return parts.join('；') || '关键测点未完整导入'
}

function guessTimeColumn(cols) {
  return cols.find((col) => /time|date|时间|日期|timestamp/i.test(col)) || cols[0] || ''
}

function parseTime(value) {
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') {
    const excelEpoch = Date.UTC(1899, 11, 30)
    return value > 20000 && value < 80000 ? excelEpoch + value * 86400000 : value
  }
  const parsed = Date.parse(String(value).replace(/\//g, '-'))
  return Number.isFinite(parsed) ? parsed : NaN
}

function toNumber(value) {
  if (typeof value === 'number') return value
  const parsed = Number(String(value ?? '').replace('%', '').trim())
  return Number.isFinite(parsed) ? parsed : NaN
}

function formatTime(ms) {
  const date = new Date(ms)
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return '-'
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}`
}

function formatStat(value) {
  if (!Number.isFinite(value)) return '-'
  return value.toFixed(3)
}

function levelText(level) {
  return { high: '高', medium: '中', low: '低', normal: '正常' }[level] || level
}
</script>

<style scoped>
.scan-panel {
  margin: 8px;
  border: 1px solid #737b82;
  background: #dedede;
  color: #1f2529;
}

.scan-title,
.scan-controls,
.root-title,
.cause-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.scan-title {
  padding: 7px 9px;
  border-bottom: 1px solid #737b82;
  background: #c7cbce;
}

.scan-title strong,
.root-title strong,
.cause-head strong {
  display: block;
  font-size: 14px;
}

.scan-title span,
.root-title span,
.cause-head span {
  color: #4f5961;
  font-size: 12px;
}

.file-btn,
button {
  height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  font-size: 12px;
  cursor: pointer;
}

.file-btn input {
  display: none;
}

.scan-controls {
  justify-content: flex-start;
  flex-wrap: wrap;
  padding: 7px 9px;
  border-bottom: 1px solid #9aa0a5;
}

.scan-controls label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
}

select,
input {
  height: 26px;
  border: 1px solid #828a91;
  background: #f6f6f6;
  color: #1f2529;
}

.data-state {
  display: flex;
  gap: 8px;
  margin-left: auto;
  font-size: 12px;
  font-weight: 700;
}

.scan-message {
  padding: 6px 9px;
  border-bottom: 1px solid #b3b7ba;
  background: #edf2f5;
  color: #315b7c;
  font-size: 12px;
}

.scan-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(330px, .65fr);
  min-height: 320px;
}

.result-table {
  overflow: auto;
  border-right: 1px solid #8f969c;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: 180px 76px 64px 180px minmax(220px, 1fr);
  min-width: 820px;
  align-items: center;
}

.table-head {
  min-height: 30px;
  border-bottom: 1px solid #8f969c;
  background: #d4d8db;
  font-size: 12px;
  font-weight: 700;
}

.table-head span,
.table-row span {
  padding: 6px 8px;
  border-right: 1px solid #b4b9bd;
}

.table-row {
  width: 100%;
  min-height: 36px;
  border: 0;
  border-bottom: 1px solid #b4b9bd;
  background: #eeeeee;
  text-align: left;
  cursor: pointer;
}

.table-row.active {
  background: #dbeaf6;
}

.table-row.danger {
  border-left: 4px solid #b64242;
}

em {
  padding: 2px 6px;
  border: 1px solid #7b838a;
  background: #f4f4f4;
  font-style: normal;
  font-weight: 700;
}

em.high {
  border-color: #9a3737;
  color: #9a2121;
}

em.medium {
  border-color: #9a6b22;
  color: #81520e;
}

em.low {
  border-color: #557a93;
  color: #315b7c;
}

.rootcause-area {
  overflow: auto;
  background: #e3e3e3;
}

.root-title {
  min-height: 34px;
  padding: 0 9px;
  border-bottom: 1px solid #8f969c;
  background: #d4d8db;
}

.cause-list {
  display: grid;
  gap: 7px;
  padding: 8px;
}

.stats-box {
  margin: 8px;
  border: 1px solid #8f969c;
  background: #eeeeee;
}

.stats-title {
  padding: 6px 7px;
  border-bottom: 1px solid #b4b9bd;
  background: #dce0e3;
  font-size: 12px;
  font-weight: 700;
}

.stats-head,
.stats-row {
  display: grid;
  grid-template-columns: 1fr repeat(4, 72px);
  align-items: center;
  min-width: 380px;
}

.stats-head {
  background: #e5e8ea;
  font-size: 12px;
  font-weight: 700;
}

.stats-head span,
.stats-row span {
  padding: 5px 6px;
  border-right: 1px solid #c0c4c7;
  border-bottom: 1px solid #c0c4c7;
  font-size: 12px;
}

.cause-card {
  border: 1px solid #8f969c;
  background: #eeeeee;
}

.cause-head,
.evidence-line,
.confirm-line {
  padding: 7px;
  border-bottom: 1px solid #c0c4c7;
}

.evidence-line {
  display: grid;
  gap: 4px;
}

.evidence-line span {
  color: #596168;
  font-size: 12px;
}

.evidence-line strong {
  font-size: 13px;
  font-weight: 500;
}

.confirm-line {
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 0;
  font-size: 12px;
  font-weight: 700;
}

.confirm-line input {
  height: auto;
}

.empty {
  padding: 14px;
  color: #596168;
  font-size: 13px;
}

@media (max-width: 980px) {
  .scan-grid {
    grid-template-columns: 1fr;
  }

  .result-table {
    border-right: 0;
    border-bottom: 1px solid #8f969c;
  }
}
</style>
