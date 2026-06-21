import externalCompressionBalanceCoefficients from '../config/externalCompressionBalanceCoefficients.json'

export const availableTags = [
  'AI705',
  'AI701',
  'AIAS704',
  'FI702',
  'FIQC701',
  'LIC701',
  'FIC101',
  'FIQC102',
  'FIC103',
  'FI131',
  'FIC8',
  'FI105',
  'FIC1',
  'TEMP',
  'PdI2',
  'PdI1',
  'AIAS102',
  'V3',
  'BALANCE'
]

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export function lowerBoundTime(items, timeMs) {
  let left = 0
  let right = items.length
  while (left < right) {
    const mid = Math.floor((left + right) / 2)
    if (items[mid].timeMs < timeMs) left = mid + 1
    else right = mid
  }
  return left
}

export function formatTime(ms) {
  if (!Number.isFinite(ms)) return '-'
  const date = new Date(ms)
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function formatDelta(value) {
  if (!Number.isFinite(value)) return '-'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

export function buildChartRows(sourceRows, widthPx, selectedTags = ['AI705']) {
  if (sourceRows.length <= 2) return sourceRows
  const safeWidth = Math.max(360, Math.round(widthPx || 0))
  const focusTags = selectedTags.length ? selectedTags : ['AI705']
  const perBucketBudget = Math.max(4, Math.min(10, 2 + focusTags.length * 2))
  const densityFactor = sourceRows.length <= 5000 ? 2.6 : 1.8
  const targetPoints = clamp(Math.round(safeWidth * densityFactor), 320, sourceRows.length)
  if (sourceRows.length <= targetPoints) return sourceRows

  const bucketCount = Math.max(1, Math.floor(targetPoints / perBucketBudget))
  const pickedIndexes = new Set()

  for (let bucket = 0; bucket < bucketCount; bucket += 1) {
    const startIndex = Math.floor((bucket * sourceRows.length) / bucketCount)
    const endIndex = Math.min(sourceRows.length - 1, Math.floor(((bucket + 1) * sourceRows.length) / bucketCount) - 1)
    if (endIndex < startIndex) continue
    pickedIndexes.add(startIndex)
    pickedIndexes.add(endIndex)

    focusTags.forEach((tag) => {
      let minIndex = startIndex
      let maxIndex = startIndex
      for (let index = startIndex; index <= endIndex; index += 1) {
        const currentValue = sourceRows[index].metrics[tag]
        const minValue = sourceRows[minIndex].metrics[tag]
        const maxValue = sourceRows[maxIndex].metrics[tag]
        if (Number.isFinite(currentValue) && (!Number.isFinite(minValue) || currentValue < minValue)) minIndex = index
        if (Number.isFinite(currentValue) && (!Number.isFinite(maxValue) || currentValue > maxValue)) maxIndex = index
      }
      pickedIndexes.add(minIndex)
      pickedIndexes.add(maxIndex)
    })
  }

  return Array.from(pickedIndexes)
    .sort((a, b) => a - b)
    .map((index) => sourceRows[index])
}

export function mergeWindowBands(windows, slideStepMin) {
  if (!windows.length) return []
  const sorted = [...windows].sort((a, b) => a.startMs - b.startMs)
  const merged = [{ startMs: sorted[0].startMs, endMs: sorted[0].endMs }]
  const allowedGapMs = slideStepMin * 60 * 1000

  for (let index = 1; index < sorted.length; index += 1) {
    const current = sorted[index]
    const last = merged[merged.length - 1]
    if (current.startMs <= last.endMs + allowedGapMs) {
      last.endMs = Math.max(last.endMs, current.endMs)
    } else {
      merged.push({ startMs: current.startMs, endMs: current.endMs })
    }
  }

  return merged
}

export function buildWindows(sourceRows, windowLengthMin, slideStepMin) {
  if (!sourceRows.length) return []
  const lengthMs = windowLengthMin * 60 * 1000
  const stepMs = slideStepMin * 60 * 1000
  const start = sourceRows[0].timeMs
  const end = sourceRows[sourceRows.length - 1].timeMs
  const windows = []
  let left = 0
  let right = 0
  for (let cursor = start; cursor + lengthMs <= end + 1; cursor += stepMs) {
    const windowEnd = cursor + lengthMs
    while (left < sourceRows.length && sourceRows[left].timeMs < cursor) left += 1
    while (right < sourceRows.length && sourceRows[right].timeMs < windowEnd) right += 1
    if (right - left >= 2) {
      windows.push({ startMs: cursor, endMs: windowEnd, rows: sourceRows.slice(left, right) })
    }
  }
  return windows
}

export function evaluateWindows(sourceRows, options) {
  const { windowLengthMin, slideStepMin } = options
  const windows = buildWindows(sourceRows, windowLengthMin, slideStepMin)
  const scanResults = windows.map((windowItem, index) => evaluateWindow(windowItem, index, sourceRows))
  const suspectedBands = mergeWindowBands(scanResults.filter((item) => item.suspected), slideStepMin)
  return { scanResults, suspectedBands }
}

export function buildNormalCauses() {
  return buildCauses({
    argonEvidence: [],
    mainTowerEvidence: [],
    frontEvidence: [],
    operationEvidence: []
  })
}

function calcStats(windowRows, tag) {
  const values = windowRows.map((row) => row.metrics[tag]).filter(Number.isFinite)
  if (!values.length) return { valid: false, delta: 0, mean: NaN, min: NaN, max: NaN }
  const sum = values.reduce((total, value) => total + value, 0)
  return {
    valid: true,
    first: values[0],
    last: values[values.length - 1],
    delta: values[values.length - 1] - values[0],
    mean: sum / values.length,
    median: median(values),
    min: Math.min(...values),
    max: Math.max(...values)
  }
}

function average(values) {
  if (!values.length) return NaN
  return values.reduce((total, value) => total + value, 0) / values.length
}

function median(values) {
  const numericValues = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!numericValues.length) return NaN
  const mid = Math.floor(numericValues.length / 2)
  return numericValues.length % 2 ? numericValues[mid] : (numericValues[mid - 1] + numericValues[mid]) / 2
}

function quantile(values, ratio) {
  const numericValues = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!numericValues.length) return NaN
  const position = (numericValues.length - 1) * clamp(ratio, 0, 1)
  const lower = Math.floor(position)
  const upper = Math.ceil(position)
  if (lower === upper) return numericValues[lower]
  return numericValues[lower] + (numericValues[upper] - numericValues[lower]) * (position - lower)
}

function medianAbsoluteDeviation(values, center) {
  if (!Number.isFinite(center)) return NaN
  return median(values.map((value) => Math.abs(value - center)))
}

function estimateSampleStepMs(rows) {
  const diffs = []
  for (let index = 1; index < rows.length; index += 1) {
    const diff = rows[index].timeMs - rows[index - 1].timeMs
    if (Number.isFinite(diff) && diff > 0) diffs.push(diff)
  }
  return median(diffs) || 60 * 1000
}

function rollingMedian(values, windowSize) {
  const size = Math.max(1, Math.round(windowSize))
  const half = Math.floor(size / 2)
  return values.map((_, index) => {
    const start = Math.max(0, index - half)
    const end = Math.min(values.length, index + half + 1)
    return median(values.slice(start, end))
  })
}

function groupTimeIntervals(pairs) {
  if (!pairs.length) return []
  const diffs = []
  for (let index = 1; index < pairs.length; index += 1) {
    const diff = pairs[index].timeMs - pairs[index - 1].timeMs
    if (Number.isFinite(diff) && diff > 0) diffs.push(diff)
  }
  const expectedStep = median(diffs) || 60 * 1000
  const intervals = []
  let current = { startMs: pairs[0].timeMs, endMs: pairs[0].timeMs, count: 1 }
  for (let index = 1; index < pairs.length; index += 1) {
    const previous = pairs[index - 1]
    const item = pairs[index]
    if (item.timeMs - previous.timeMs <= expectedStep * 1.5) {
      current.endMs = item.timeMs
      current.count += 1
    } else {
      intervals.push(current)
      current = { startMs: item.timeMs, endMs: item.timeMs, count: 1 }
    }
  }
  intervals.push(current)
  return intervals
}

function estimateAi705Workpoint(sourceRows, windowItem, fallbackValues) {
  const endMs = windowItem?.endMs ?? sourceRows[sourceRows.length - 1]?.timeMs
  const startMs = Number.isFinite(endMs) ? endMs - 6 * 60 * 60 * 1000 : -Infinity
  const historyPairs = sourceRows
    .filter((row) => row.timeMs >= startMs && row.timeMs <= endMs)
    .map((row) => ({ timeMs: row.timeMs, value: row.metrics.AI705 }))
    .filter((item) => Number.isFinite(item.timeMs) && Number.isFinite(item.value))
  const historyValues = historyPairs.map((item) => item.value)
  const values = historyValues.length >= 6 ? historyValues : fallbackValues.filter(Number.isFinite)
  if (!values.length) {
    return {
      workpoint: NaN,
      normalBand: { lower: NaN, upper: NaN, halfWidth: NaN },
      normalNoise: NaN,
      sampleCount: 0,
      baselineMethod: 'insufficient_data',
      baselineWindow: { startMs: NaN, endMs: NaN },
      excludedIntervals: [],
      baselineConfidence: 'low'
    }
  }

  const q25 = quantile(values, 0.25)
  const q75 = quantile(values, 0.75)
  const center = median(values)
  const robustNoise = Math.max(
    0.03,
    Number.isFinite(q75 - q25) ? (q75 - q25) / 1.349 : 0,
    (medianAbsoluteDeviation(values, center) || 0) * 1.4826
  )
  const highStableValues = values
    .filter((value) => value >= center - Math.max(0.24, robustNoise * 3))
    .sort((a, b) => a - b)
  const stableCutoff = center - Math.max(0.24, robustNoise * 3)
  const excludedPairs = historyPairs.length >= 6
    ? historyPairs.filter((item) => item.value < stableCutoff)
    : []
  const stableValues = highStableValues.length >= Math.min(6, values.length)
    ? highStableValues
    : [...values].sort((a, b) => a - b)
  const workpoint = quantile(stableValues, stableValues.length >= 8 ? 0.6 : 0.5)
  const stableQ25 = quantile(stableValues, 0.25)
  const stableQ75 = quantile(stableValues, 0.75)
  const normalNoise = Math.max(0.03, Number.isFinite(stableQ75 - stableQ25) ? (stableQ75 - stableQ25) / 1.349 : robustNoise)
  const halfWidth = Math.max(0.08, Math.min(0.45, normalNoise * 2))

  return {
    workpoint,
    baselineValue: workpoint,
    baselineMethod: historyPairs.length >= 6 ? 'stable_segment_quantile_after_dip_exclusion' : 'window_rolling_median_fallback',
    baselineWindow: {
      startMs: historyPairs[0]?.timeMs ?? startMs,
      endMs: historyPairs[historyPairs.length - 1]?.timeMs ?? endMs
    },
    excludedIntervals: groupTimeIntervals(excludedPairs).slice(0, 8),
    baselineConfidence: stableValues.length >= 24 && stableValues.length / values.length >= 0.55
      ? 'high'
      : stableValues.length >= 8
      ? 'medium'
      : 'low',
    normalBand: {
      lower: workpoint - halfWidth,
      upper: workpoint + halfWidth,
      halfWidth
    },
    normalNoise,
    sampleCount: stableValues.length
  }
}

function detectDipCandidates(series, boundaryThreshold, entryThreshold, sampleStepMs) {
  const candidates = []
  let index = 0
  while (index < series.length) {
    if (!series[index] || series[index].depth < boundaryThreshold) {
      index += 1
      continue
    }
    const startIndex = index
    let endIndex = index
    let minIndex = index
    while (endIndex + 1 < series.length && series[endIndex + 1].depth >= boundaryThreshold) {
      endIndex += 1
      if (series[endIndex].smooth < series[minIndex].smooth) minIndex = endIndex
    }
    const dipDepth = series[minIndex].depth
    const durationMin = Math.max(sampleStepMs / 60000, (series[endIndex].timeMs - series[startIndex].timeMs) / 60000)
    if (dipDepth >= entryThreshold) {
      candidates.push({ startIndex, endIndex, minIndex, dipDepth, durationMin })
    }
    index = endIndex + 1
  }
  return candidates
}

function countValleys(series, startIndex, endIndex, depthThreshold) {
  const valleys = []
  const safeStart = clamp(startIndex, 0, series.length - 1)
  const safeEnd = clamp(endIndex, safeStart, series.length - 1)
  for (let index = safeStart; index <= safeEnd; index += 1) {
    const current = series[index]
    if (!current || current.depth < depthThreshold) continue
    const prev = series[Math.max(safeStart, index - 1)]?.smooth ?? Infinity
    const next = series[Math.min(safeEnd, index + 1)]?.smooth ?? Infinity
    if (current.smooth <= prev && current.smooth <= next) {
      const previousValley = valleys[valleys.length - 1]
      if (previousValley && index - previousValley.index <= 2) {
        if (current.smooth < previousValley.value) {
          previousValley.index = index
          previousValley.timeMs = current.timeMs
          previousValley.value = current.smooth
          previousValley.depth = current.depth
        }
      } else {
        valleys.push({ index, timeMs: current.timeMs, value: current.smooth, depth: current.depth })
      }
    }
  }
  return valleys
}

function shapeTypeText(type) {
  return {
    multi_valley: '多谷下凹',
    single_valley: '单谷下凹',
    low_plateau: '连续低位',
    short_wave: '短时波动',
    incomplete: '形态不完整',
    none: '未成形'
  }[type] || '待识别'
}

function relativeDeltaPercent(current, baseline) {
  if (!Number.isFinite(current) || !Number.isFinite(baseline) || baseline === 0) return NaN
  return ((current - baseline) / Math.abs(baseline)) * 100
}

function ratioPercent(delta, baseline) {
  if (!Number.isFinite(delta) || !Number.isFinite(baseline) || baseline === 0) return NaN
  return (delta / Math.abs(baseline)) * 100
}

function formatMaybe(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : '-'
}

function formatPct(value) {
  if (!Number.isFinite(value)) return '-'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function buildAi705DeviceStandard(workpointContext, sampleStepMs, windowDurationMin) {
  const noise = Number.isFinite(workpointContext.normalNoise) ? workpointContext.normalNoise : 0.03
  const halfWidth = Number.isFinite(workpointContext.normalBand?.halfWidth) ? workpointContext.normalBand.halfWidth : noise * 2
  const mildDrop = Math.max(0.18, Math.min(0.45, Math.max(noise * 3, halfWidth * 1.35)))
  const moderateDrop = Math.max(mildDrop * 2.2, Math.min(0.9, mildDrop + 0.45))
  const severeDrop = Math.max(1.2, moderateDrop * 1.8, mildDrop * 4.5)
  const stepMin = Math.max(1, sampleStepMs / 60000)
  const mildDurationMin = Math.max(stepMin, Math.min(10, windowDurationMin * 0.25))
  const moderateDurationMin = Math.max(mildDurationMin * 2, Math.min(30, windowDurationMin * 0.55))
  const severeDurationMin = Math.max(moderateDurationMin * 2, Math.min(60, windowDurationMin * 0.75))

  return {
    source: 'adaptive_device_baseline',
    baselineValue: workpointContext.baselineValue,
    baselineMethod: workpointContext.baselineMethod,
    baselineConfidence: workpointContext.baselineConfidence,
    normalNoise: noise,
    normalBandHalfWidth: halfWidth,
    mildDrop,
    moderateDrop,
    severeDrop,
    mildDurationMin,
    moderateDurationMin,
    severeDurationMin,
    basis: `本设备按当前6h稳定基线和噪声计算标准：轻度≥${mildDrop.toFixed(2)}且≥${mildDurationMin.toFixed(0)}min，中度≥${moderateDrop.toFixed(2)}且≥${moderateDurationMin.toFixed(0)}min，重度≥${severeDrop.toFixed(2)}且≥${severeDurationMin.toFixed(0)}min`
  }
}

function getRowsBefore(sourceRows, startMs, lookbackMin) {
  const earliestMs = startMs - lookbackMin * 60 * 1000
  return sourceRows.filter((row) => row.timeMs >= earliestMs && row.timeMs < startMs)
}

function classifyOperatingMode(stats, previousRows) {
  const load = stats.FIC101
  if (!load?.valid) {
    return {
      mode: 'unknown',
      label: '负荷状态待确认',
      dynamic: true,
      basis: '缺少 FIC101 原料空气总量，无法判断当前是否固定负荷运行。'
    }
  }

  const previousLoad = calcStats(previousRows, 'FIC101')
  const windowSwingPct = ratioPercent(load.max - load.min, load.mean)
  const windowDeltaPct = ratioPercent(load.delta, load.first)
  const previousShiftPct = previousLoad.valid ? relativeDeltaPercent(load.mean, previousLoad.mean) : NaN
  const dynamic = Math.abs(windowDeltaPct || 0) > 0.8 || Math.abs(windowSwingPct || 0) > 1.2 || Math.abs(previousShiftPct || 0) > 1.5

  return {
    mode: dynamic ? 'dynamic_load' : 'steady_load',
    label: dynamic ? '变负荷/动态过程' : '固定负荷/稳态窗口',
    dynamic,
    basis: dynamic
      ? `FIC101窗口变化 ${formatPct(windowDeltaPct)}、波动 ${formatPct(windowSwingPct)}、较前段均值 ${formatPct(previousShiftPct)}，静态物料平衡仅作提示。`
      : `FIC101窗口变化 ${formatPct(windowDeltaPct)}、波动 ${formatPct(windowSwingPct)}，可按固定负荷做稳态复核。`,
    loadMean: load.mean,
    previousLoadMean: previousLoad.mean,
    windowDeltaPct,
    windowSwingPct,
    previousShiftPct
  }
}

const diagnosticRules = {
  AI705: { low: 0.45, high: Infinity, riskLow: '粗氩含氮量相对本设备工作点形成下凹形态，触发轻/中/重氮塞主事件。', riskHigh: '' },
  AI701: { low: 1.25, high: 1.25, riskLow: 'AI701出现同窗口组分联动，是重要表现信号，需结合空气、氧气、氮气和阀门共同判断。', riskHigh: 'AI701氩馏分纯度偏高或短时高高，是主塔负荷分配扰动后的重要表现信号。' },
  AIAS704: { low: 1.25, high: 1.25, riskLow: '粗氩氧含量偏低，提示粗氩塔组分状态变化。', riskHigh: '粗氩氧含量偏高，提示粗氩塔组分扰动。' },
  FI702: { low: Infinity, high: 1.25, riskLow: '', riskHigh: 'FI702氩馏分流量偏高，进入粗氩塔的氩馏分负荷偏高，可能增加氮塞风险。' },
  FIQC701: { low: 1.25, high: Infinity, riskLow: 'FIC701/粗氩流量偏低，粗氩抽出不足可能造成系统内组分积累，增加氮塞风险。', riskHigh: '' },
  LIC701: { low: 1.25, high: 1.25, riskLow: '粗氩冷凝器液位偏低，需核对冷凝负荷和液位控制。', riskHigh: '粗氩冷凝器液位偏高，需核对换热和液位控制。' },
  FIQC102: { low: Infinity, high: 1.25, riskLow: '', riskHigh: '氧气取出量偏高，可能改变主塔物料分配并诱发粗氩侧扰动。' },
  FIC103: { low: 1.25, high: Infinity, riskLow: '氮气抽取偏少，可能改变全塔物料分配并增加氮塞风险。', riskHigh: '' },
  FIC8: { low: 1.25, high: 1.25, riskLow: '液氮产量偏低，需结合目标液氮负荷核对物料分配。', riskHigh: '液氮产量偏高，可能改变冷量和产品抽取节奏。' },
  FI105: { low: 1.25, high: Infinity, riskLow: '膨胀空气旁通量/增压端空气偏少，可能影响冷量和塔内状态，增加氮塞风险。', riskHigh: '' },
  FIC1: { low: 1.25, high: Infinity, riskLow: '膨胀空气进上塔流量偏低，可能影响冷量和塔内状态，增加氮塞风险。', riskHigh: '' },
  PdI2: { low: 1.25, high: 1.25, riskLow: '上塔阻力偏低，需核对塔内负荷和精馏状态。', riskHigh: '上塔阻力偏高，需核对主塔阻力异常。' },
  PdI1: { low: 1.25, high: 1.25, riskLow: '下塔阻力偏低，需核对塔内负荷和精馏状态。', riskHigh: '下塔阻力偏高，需核对主塔阻力异常。' },
  AIAS102: { low: 0.05, high: Infinity, riskLow: '氧气纯度偏低，提示主塔精馏状态受扰动。', riskHigh: '' },
  FIC101: { low: 1.25, high: 1.25, riskLow: '空气少进，可能改变主塔负荷分配并增加氮塞风险。', riskHigh: '空气量偏高，可能是升负荷过程或前端扰动。' },
  V3: { low: Infinity, high: 1.25, riskLow: '', riskHigh: 'V3阀开过大，需按主塔分支核对液氮至上塔调节影响。' },
  BALANCE: { low: 1.25, high: 1.25, riskLow: '物料平衡偏差偏低，需核对产品取出量或计量。', riskHigh: '物料平衡偏差偏高，需核对进塔空气量和产品取出量。' }
}

const defaultAllowedDeviationPct = 1.25
const dryAirComposition = {
  N2: 0.78084,
  O2: 0.20946,
  Ar: 0.00934
}
const materialBalanceStepPosition = '氮塞识别完成 → 判断稳态/动态 → 物料平衡复核 → 方向性原因打分 → 故障树分支排序'
const materialBalanceInputTags = ['FIC101', 'FIQC102', 'FIC103', 'FI131', 'FIC8', 'FI702', 'FIQC701', 'FI105', 'FIC1', 'V3', 'BALANCE']
const externalCompressionFormulaText = [
  'EGOX = GOX - 125/136 × LIN + 114/136 × (GAR - GARBase)',
  'PAIR = p1 × EGOX² + p2 × EGOX + p3（PAIR vs. EGOX，.sfit poly2）',
  'GAN = p1 × EGOX + p2（FIC103AVG vs. EGOX，.sfit poly1）',
  'FAR = p1 × PAIR + p2；CAR = p1 × PAIR + p2；FIC1 = p1 × EGOX + p2（.sfit poly1）',
  'AIR = PAIR + FIC1_model'
].join('；')
const externalCompressionModelSteps = [
  '读取交付包导出的 sfit_coefficients_exported.json。',
  '按 GOX、LIN、GAR、GARBase 计算 EGOX。',
  '用 .sfit 二次多项式计算 PAIR。',
  '用 .sfit 一次多项式计算 GAN、FAR、CAR、FIC1。',
  '按 AIR = PAIR + FIC1_model 得到总空气模型值。',
  '把 AIR/FAR/CAR/GAN 模型值与现场均值做残差和偏差语义化。'
]
const materialBalanceOutputRoles = {
  FIC101: { name: '进塔空气量', role: '负荷基准', abnormalLow: '空气少进可能改变主塔负荷分配，增加粗氩侧氮塞风险。', abnormalHigh: '空气量偏高可能对应升负荷过程，需要核对负荷调整节奏。' },
  FIQC102: { name: '氧气取出量', role: '氧产品抽取', abnormalHigh: '氧气多抽可能改变主塔物料分配，并把扰动传递到粗氩侧。' },
  FIC103: { name: '氮气取出量', role: '氮产品抽取', abnormalLow: '氮气少抽可能造成全塔物料分配偏移，增加粗氩侧异常风险。' },
  FI131: { name: '中压氮气去用户流量', role: 'GAR/EGOX输入', abnormalLow: '中压氮气外送偏低会改变EGOX修正量，需核对氮气外送和基准。', abnormalHigh: '中压氮气外送偏高会改变EGOX修正量，需核对氮气外送和基准。' },
  FIC8: { name: '液氮产量', role: '液氮负荷', abnormalLow: '液氮产量偏低时需核对目标液氮负荷和冷量分配。', abnormalHigh: '液氮产量偏高可能改变冷量和产品抽取节奏。' },
  FI702: { name: '粗氩塔氩馏分流量', role: '粗氩塔负荷', abnormalHigh: '粗氩塔氩馏分负荷偏高，可能带入更多氮并增加氮塞风险。' },
  FIQC701: { name: '粗氩抽出流量', role: '粗氩抽取', abnormalLow: '粗氩抽出不足可能造成系统内组分积累。' },
  FI105: { name: '膨胀空气旁通量', role: '冷量/塔内状态', abnormalLow: '膨胀空气偏低可能影响冷量和塔内状态。' },
  FIC1: { name: '膨胀空气进上塔流量', role: '冷量/塔内状态', abnormalLow: '膨胀空气进上塔偏低可能影响冷量和塔内状态。' },
  V3: { name: 'V3阀位', role: '液氮至上塔调节', abnormalHigh: 'V3阀开度偏高时需核对液氮至上塔调节影响。' },
  BALANCE: { name: '总量平衡残差', role: '总量复核', abnormalLow: '残差偏低时需核对产品取出量、废氮/污氮或计量。', abnormalHigh: '残差偏高时需核对进塔空气量和已知产品取出量。' }
}

function classifyRiskLevel(deviationPct, limitPct = defaultAllowedDeviationPct) {
  const absDeviation = Math.abs(deviationPct || 0)
  if (!Number.isFinite(absDeviation) || absDeviation <= limitPct) return 'normal'
  if (absDeviation <= limitPct * 2) return 'low'
  if (absDeviation <= limitPct * 4) return 'medium'
  return 'high'
}

function riskTextByLevel(level) {
  return {
    low: '低风险',
    medium: '中风险',
    high: '高风险',
    normal: '正常'
  }[level] || '待判别'
}

function buildLoadMatchedBaseline(sourceRows, windowItem, stats) {
  const loadMean = stats.FIC101?.mean
  const historyRows = getRowsBefore(sourceRows, windowItem.startMs, 6 * 60)
  const previousRows = getRowsBefore(sourceRows, windowItem.startMs, 30)
  const loadTolerance = Number.isFinite(loadMean) ? Math.max(Math.abs(loadMean) * 0.02, 60) : Infinity
  const matchedRows = Number.isFinite(loadMean)
    ? historyRows.filter((row) => Number.isFinite(row.metrics.FIC101) && Math.abs(row.metrics.FIC101 - loadMean) <= loadTolerance)
    : []
  const baselineRows = matchedRows.length >= 6 ? matchedRows : historyRows.slice(-Math.max(12, windowItem.rows.length))
  return {
    previousRows,
    baselineRows,
    basis: matchedRows.length >= 6
      ? `历史同负荷样本 ${matchedRows.length} 点，FIC101允许偏差 ±${loadTolerance.toFixed(0)} Nm3/h。`
      : `同负荷样本不足，使用窗口前 ${baselineRows.length} 点作为临时基准。`
  }
}

function buildDirectionalChecks(stats, baselineContext) {
  return availableTags.map((tag) => {
    const current = stats[tag]
    const baseline = calcStats(baselineContext.baselineRows, tag)
    const previous = calcStats(baselineContext.previousRows, tag)
    const rule = diagnosticRules[tag] || { low: 1, high: 1, riskLow: '变量偏低风险。', riskHigh: '变量偏高风险。' }
    const deviationPct = relativeDeltaPercent(current.mean, baseline.mean)
    const previousDeviationPct = relativeDeltaPercent(current.mean, previous.mean)
    const allowedDeviationPct = defaultAllowedDeviationPct
    const lowerLimit = Number.isFinite(baseline.mean) ? baseline.mean * (1 - allowedDeviationPct / 100) : NaN
    const upperLimit = Number.isFinite(baseline.mean) ? baseline.mean * (1 + allowedDeviationPct / 100) : NaN
    const riskLevel = classifyRiskLevel(deviationPct, allowedDeviationPct)
    let direction = 'normal'
    let directionText = '基本稳定'
    let riskText = '未超出当前负荷下的合理波动范围'
    let triggered = false

    if (!current.valid || !baseline.valid) {
      direction = 'unknown'
      directionText = '待补数据'
      riskText = '当前值或基准值不足，暂不能判断偏高/偏低风险'
    } else if (Number.isFinite(deviationPct) && deviationPct <= -rule.low) {
      direction = 'low'
      directionText = '偏低风险'
      riskText = rule.riskLow || `${tag} 低于当前负荷基准。`
      triggered = true
    } else if (Number.isFinite(deviationPct) && deviationPct >= rule.high) {
      direction = 'high'
      directionText = '偏高风险'
      riskText = rule.riskHigh || `${tag} 高于当前负荷基准。`
      triggered = true
    }

    return {
      tag,
      currentMean: current.mean,
      currentMedian: current.median,
      baselineMean: baseline.mean,
      baselineMedian: baseline.median,
      previousMean: previous.mean,
      previousMedian: previous.median,
      lowerLimit,
      upperLimit,
      currentDelta: current.delta,
      deviationPct,
      previousDeviationPct,
      allowedDeviationPct,
      thresholdPct: direction === 'high' ? rule.high : rule.low,
      direction,
      directionText,
      triggered,
      riskLevel: triggered ? riskLevel : 'normal',
      riskLevelText: triggered ? riskTextByLevel(riskLevel) : '正常',
      riskText,
      basis: `基准 ${formatMaybe(baseline.mean)}，合理范围 ${formatMaybe(lowerLimit)} - ${formatMaybe(upperLimit)}，当前 ${formatMaybe(current.mean)}，前段 ${formatMaybe(previous.mean)}，较基准 ${formatPct(deviationPct)}，较前段 ${formatPct(previousDeviationPct)}，语义判断：${directionText}${triggered ? ` / ${riskTextByLevel(riskLevel)}` : ''}。`
    }
  })
}

function directionalByTag(directionalChecks, tag) {
  return directionalChecks.find((item) => item.tag === tag)
}

function buildMaterialBalanceInputs(directionalChecks) {
  return materialBalanceInputTags.map((tag) => {
    const check = directionalByTag(directionalChecks, tag) || {}
    const meta = materialBalanceOutputRoles[tag] || { name: tag, role: '过程变量' }
    return {
      tag,
      name: meta.name,
      role: meta.role,
      baseline: check.baselineMean,
      range: [check.lowerLimit, check.upperLimit],
      current: check.currentMean,
      previous: check.previousMean,
      deviationPct: check.deviationPct,
      direction: check.direction || 'unknown',
      directionText: check.directionText || '待补数据',
      risk: check.riskLevelText || '待判别',
      explanation: check.direction === 'low'
        ? (meta.abnormalLow || check.riskText)
        : check.direction === 'high'
        ? (meta.abnormalHigh || check.riskText)
        : check.riskText
    }
  })
}

function buildComponentInputs(airIn) {
  if (!Number.isFinite(airIn)) return {}
  return {
    O2_in: airIn * dryAirComposition.O2,
    N2_in: airIn * dryAirComposition.N2,
    Ar_in: airIn * dryAirComposition.Ar
  }
}

function sumKnownProductOutputs(directionalChecks) {
  return ['FIQC102', 'FIC103', 'FIC8', 'FI702']
    .map((tag) => directionalByTag(directionalChecks, tag)?.currentMean)
    .filter(Number.isFinite)
    .reduce((total, value) => total + value, 0)
}

function ratioFromConfig(ratioConfig, fallback) {
  const numerator = Number(ratioConfig?.numerator)
  const denominator = Number(ratioConfig?.denominator)
  return Number.isFinite(numerator) && Number.isFinite(denominator) && denominator !== 0
    ? numerator / denominator
    : fallback
}

function fitByDataName(modelConfig, dataName) {
  const fits = modelConfig?.fits
  if (fits && !Array.isArray(fits)) return fits[dataName] || null
  if (Array.isArray(fits)) return fits.find((item) => item.data_name === dataName || item.dataName === dataName) || null
  return null
}

function poly1Fit(fit, x) {
  if (!Number.isFinite(x)) return NaN
  const coeffs = fit?.coefficients || {}
  return (Number(coeffs.p1) || 0) * x + (Number(coeffs.p2) || 0)
}

function poly2Fit(fit, x) {
  if (!Number.isFinite(x)) return NaN
  const coeffs = fit?.coefficients || {}
  return (Number(coeffs.p1) || 0) * x * x + (Number(coeffs.p2) || 0) * x + (Number(coeffs.p3) || 0)
}

function relativeResidualPercent(measured, model) {
  if (!Number.isFinite(measured) || !Number.isFinite(model) || model === 0) return NaN
  return ((measured - model) / model) * 100
}

function semanticFromDeviation(deviationPct, limitPct = defaultAllowedDeviationPct) {
  if (!Number.isFinite(deviationPct)) return '待补数据'
  if (deviationPct > limitPct) return '偏高'
  if (deviationPct < -limitPct) return '偏低'
  return '正常'
}

function hasModelInput(value) {
  return Number.isFinite(value) || (value && typeof value === 'object')
}

function finiteConfigNumber(value) {
  if (value === null || value === undefined || value === '') return NaN
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : NaN
}

function buildExternalCompressionBalanceModel(directionalChecks) {
  const readCurrent = (tag) => directionalByTag(directionalChecks, tag)?.currentMean
  const readCurrentMedian = (tag) => directionalByTag(directionalChecks, tag)?.currentMedian
  const readBase = (tag) => directionalByTag(directionalChecks, tag)?.baselineMean
  const readPrevious = (tag) => directionalByTag(directionalChecks, tag)?.previousMean
  const firstFinite = (...values) => values.find(Number.isFinite)
  const modelConfig = externalCompressionBalanceCoefficients || {}
  const baseParameters = modelConfig.baseParameters || {}
  const linToEgoxRatio = ratioFromConfig(modelConfig.fixedRatios?.LIN_TO_EGOX, 125 / 136)
  const garDeltaToEgoxRatio = ratioFromConfig(modelConfig.fixedRatios?.GAR_DELTA_TO_EGOX, 114 / 136)
  const pairFit = fitByDataName(modelConfig, 'PAIR vs. EGOX')
  const ganFit = fitByDataName(modelConfig, 'FIC103AVG vs. EGOX')
  const farFit = fitByDataName(modelConfig, 'FI702AVG vs. PAIR')
  const carFit = fitByDataName(modelConfig, 'FIC701AVG vs. PAIR')
  const fic1Fit = fitByDataName(modelConfig, 'FIC1AVG vs. EGOX')
  const totalAirMeasured = readCurrent('FIC101')
  const GOXRaw = readCurrent('FIQC102')
  const LINRaw = readCurrent('FIC8')
  const GARRaw = readCurrent('FI131')
  const GOX = firstFinite(GOXRaw, Number.isFinite(totalAirMeasured) ? totalAirMeasured * dryAirComposition.O2 : NaN)
  const LIN = firstFinite(LINRaw, readBase('FIC8'), 0)
  const GAR = firstFinite(GARRaw, readBase('FI131'), readCurrent('FIC103'), readBase('FIC103'), Number.isFinite(totalAirMeasured) ? Math.max(0, totalAirMeasured * dryAirComposition.N2 - (Number.isFinite(LIN) ? LIN : 0)) : NaN)
  const configuredGARBase = finiteConfigNumber(baseParameters.GARBase)
  const GARBase = firstFinite(configuredGARBase, readCurrentMedian('FI131'), readBase('FI131'), readPrevious('FI131'), GAR)
  const FIC1Actual = readCurrent('FIC1')
  const GANActual = readCurrent('FIC103')
  const missingCoreInputs = [
    ['GOX', GOX, 'FIQC102氧气产量'],
    ['LIN', LIN, 'FIC8液氮流量或V8估算'],
    ['GAR', GAR, 'FI131中压氮气去用户流量'],
    ['GARBase', GARBase, '窗口GAR中位数或配置基准'],
    ['PAIR_FIT', pairFit, 'PAIR vs. EGOX .sfit系数'],
    ['GAN_FIT', ganFit, 'FIC103AVG vs. EGOX .sfit系数'],
    ['FAR_FIT', farFit, 'FI702AVG vs. PAIR .sfit系数'],
    ['CAR_FIT', carFit, 'FIC701AVG vs. PAIR .sfit系数'],
    ['FIC1_FIT', fic1Fit, 'FIC1AVG vs. EGOX .sfit系数']
  ].filter(([, value]) => !hasModelInput(value))
  const hasCoreInputs = missingCoreInputs.length === 0
  const EGOX = hasCoreInputs ? GOX - linToEgoxRatio * LIN + garDeltaToEgoxRatio * (GAR - GARBase) : NaN
  const PAIRModel = hasCoreInputs ? poly2Fit(pairFit, EGOX) : NaN
  const GANModel = hasCoreInputs ? poly1Fit(ganFit, EGOX) : NaN
  const FARModel = Number.isFinite(PAIRModel) ? poly1Fit(farFit, PAIRModel) : NaN
  const CARModel = Number.isFinite(PAIRModel) ? poly1Fit(carFit, PAIRModel) : NaN
  const FIC1Model = hasCoreInputs ? poly1Fit(fic1Fit, EGOX) : NaN
  const AIRModel = Number.isFinite(PAIRModel) && Number.isFinite(FIC1Model) ? PAIRModel + FIC1Model : NaN
  const PAIRActual = Number.isFinite(totalAirMeasured) && Number.isFinite(FIC1Actual)
    ? totalAirMeasured - FIC1Actual
    : NaN
  const FARActual = readCurrent('FI702')
  const CARActual = readCurrent('FIQC701')
  const recoveredInputs = []
  if (!Number.isFinite(GOXRaw) && Number.isFinite(GOX)) recoveredInputs.push('GOX用进塔空气量×20.946%临时估算')
  if (!Number.isFinite(LINRaw) && Number.isFinite(LIN)) recoveredInputs.push(Number.isFinite(readBase('FIC8')) ? 'LIN使用同负荷基准临时兜底' : 'LIN缺测，Demo按0临时估算')
  if (!Number.isFinite(GARRaw) && Number.isFinite(GAR)) recoveredInputs.push('FI131缺测，GAR临时使用产品氮气或空气氮组分兜底')
  if (!Number.isFinite(configuredGARBase) && Number.isFinite(GARBase)) recoveredInputs.push('GARBase按当前窗口FI131中位数/均值兜底，等价于交付包未传gar_base时的默认口径')
  const modelStatus = hasCoreInputs ? (recoveredInputs.length ? 'demo_estimated' : 'demo_ready') : 'missing_inputs'
  const residuals = [
    { key: 'AIR', measured: totalAirMeasured, model: AIRModel },
    { key: 'FAR', measured: FARActual, model: FARModel },
    { key: 'CAR', measured: CARActual, model: CARModel },
    { key: 'GAN', measured: GANActual, model: GANModel }
  ].map((item) => {
    const deviationPct = relativeResidualPercent(item.measured, item.model)
    return {
      ...item,
      residual: Number.isFinite(item.measured) && Number.isFinite(item.model) ? item.measured - item.model : NaN,
      deviationPct,
      semantic: semanticFromDeviation(deviationPct)
    }
  })
  const variables = [
    { key: 'GOX', name: '氧气产量', value: GOX, source: 'FIQC102' },
    { key: 'LIN', name: '液氮流量', value: LIN, source: 'FIC8' },
    { key: 'GAR', name: '中压氮气去用户流量', value: GAR, source: Number.isFinite(GARRaw) ? 'FI131' : 'FI131缺测兜底' },
    { key: 'GARBase', name: 'GAR基准', value: GARBase, source: Number.isFinite(configuredGARBase) ? '配置基准' : '窗口FI131中位数/兜底值' },
    { key: 'EGOX', name: '等效全液氧工况氧气产量', value: EGOX, source: '外压缩方程①' },
    { key: 'PAIR', name: '进塔分离空气流量', value: PAIRModel, source: 'PAIR vs. EGOX / .sfit poly2' },
    { key: 'PAIR_actual', name: '进塔分离空气实测估算', value: PAIRActual, source: 'FIC101 - FIC1' },
    { key: 'GAN', name: '产品氮气模型值', value: GANModel, source: 'FIC103AVG vs. EGOX / .sfit poly1' },
    { key: 'GAN_actual', name: '产品氮气实测', value: GANActual, source: 'FIC103' },
    { key: 'FIC1_model', name: '膨胀空气进上塔模型值', value: FIC1Model, source: 'FIC1AVG vs. EGOX / .sfit poly1' },
    { key: 'FIC1_actual', name: '膨胀空气进上塔实测', value: FIC1Actual, source: 'FIC1' },
    { key: 'FAR', name: '氩馏分流量', value: FARModel, source: 'FI702AVG vs. PAIR / .sfit poly1' },
    { key: 'FAR_actual', name: '氩馏分流量实测', value: FARActual, source: 'FI702' },
    { key: 'CAR', name: '粗氩流量', value: CARModel, source: 'FIC701AVG vs. PAIR / .sfit poly1' },
    { key: 'CAR_actual', name: '粗氩流量实测', value: CARActual, source: 'FIQC701' },
    { key: 'AIR', name: '总空气流量', value: AIRModel, source: 'PAIR + FIC1_model' },
    { key: 'AIR_actual', name: '总空气流量实测', value: totalAirMeasured, source: 'FIC101' }
  ]
  return {
    name: '外压缩物料平衡.sfit模型',
    status: modelStatus,
    coefficientStatus: 'configured',
    coefficientSource: 'frontend/src/config/externalCompressionBalanceCoefficients.json',
    coefficientNote: '系数来自交付包 material_balance_python/data/sfit_coefficients_exported.json；计算逻辑对齐 compute_sfit_demo_balance()。',
    missingCoreInputs: missingCoreInputs.map(([key, , label]) => ({ key, label })),
    missingForProduction: [
      'FI131作为GAR输入；缺失时当前Demo会降级用产品氮气/空气氮组分兜底。',
      'GARBase建议后续由确认的稳态基准传入；未配置时按交付包默认使用窗口GAR中位数。',
      '若MATLAB .sfit重新拟合，需要重新导出并替换当前JSON系数。'
    ],
    recoveredInputs,
    formulaText: externalCompressionFormulaText,
    steps: externalCompressionModelSteps,
    correctionNotes: [
      '当前前端按窗口均值/中位数调用，与Python交付包的1分钟重采样后窗口汇总口径保持一致。',
      'AIR/FAR/CAR/GAN残差口径为 measured - model，偏差为 residual / model。',
      '当前.sfit模型是经验软测量模型，用于氮塞诊断中的物料平衡辅助复核。'
    ],
    inputs: { GOX, LIN, GAR, GARBase },
    variables,
    residuals,
    primaryResidual: residuals.find((item) => item.key === 'AIR'),
    primaryOutputText: Number.isFinite(EGOX)
      ? `EGOX ${formatMaybe(EGOX)}，PAIR模型值 ${formatMaybe(PAIRModel)}，AIR模型值 ${formatMaybe(AIRModel)}，FAR模型值 ${formatMaybe(FARModel)}，CAR模型值 ${formatMaybe(CARModel)}，GAN模型值 ${formatMaybe(GANModel)}。`
      : `缺少${missingCoreInputs.map(([key]) => key).join('/')}，外压缩模型等待补齐输入。`
  }
}

function evaluateAi705Primary(windowRows, stats, sourceRows = windowRows, windowItem = null) {
  const pairs = windowRows
    .map((row, rowIndex) => ({ rowIndex, timeMs: row.timeMs, raw: row.metrics.AI705 }))
    .filter((item) => Number.isFinite(item.raw) && Number.isFinite(item.timeMs))
  const values = pairs.map((item) => item.raw)
  if (!stats?.valid || values.length < 3) {
    return {
      triggered: false,
      nearTriggered: false,
      severity: 'none',
      severityText: '未触发',
      shapeType: 'none',
      shapeText: '未成形',
      basis: 'AI705有效点不足，暂不能做下凹形态识别'
    }
  }

  const sampleStepMs = estimateSampleStepMs(windowRows)
  const smoothWindowSize = sampleStepMs >= 5 * 60 * 1000
    ? 1
    : Math.max(3, Math.round((5 * 60 * 1000) / sampleStepMs))
  const smoothedValues = rollingMedian(values, smoothWindowSize)
  const workpointContext = estimateAi705Workpoint(sourceRows, windowItem, values)
  const baseline = Number.isFinite(workpointContext.workpoint)
    ? workpointContext.workpoint
    : average(values)
  const rawMinValue = Math.min(...values)
  const rawMinIndex = values.indexOf(rawMinValue)
  const rawDipDepth = baseline - rawMinValue
  const rawLeftPeak = rawMinIndex > 0 ? Math.max(...values.slice(0, rawMinIndex)) : values[0]
  const rawRightPeak = rawMinIndex < values.length - 1 ? Math.max(...values.slice(rawMinIndex + 1)) : values[values.length - 1]
  const rawLeftDrop = rawLeftPeak - rawMinValue
  const rawRightRecovery = rawRightPeak - rawMinValue
  const series = pairs.map((item, index) => ({
    ...item,
    smooth: smoothedValues[index],
    depth: baseline - smoothedValues[index]
  }))
  const globalMinValue = Math.min(...smoothedValues)
  const globalMinIndex = smoothedValues.indexOf(globalMinValue)
  const maxDepth = baseline - globalMinValue
  const boundaryThreshold = Math.max(0.08, Math.min(0.24, Math.max(workpointContext.normalNoise * 1.5, maxDepth * 0.18)))
  const entryThreshold = Math.max(0.2, Math.min(0.3, Math.max(workpointContext.normalNoise * 2.2, 0.2)))
  const dipCandidates = detectDipCandidates(series, boundaryThreshold, entryThreshold, sampleStepMs)
  const primaryCandidate = dipCandidates
    .slice()
    .sort((a, b) => (b.dipDepth * 10 + b.durationMin * 0.03) - (a.dipDepth * 10 + a.durationMin * 0.03))[0]
  let minIndex = primaryCandidate?.minIndex ?? globalMinIndex
  let minValue = smoothedValues[minIndex]
  let startIndex = primaryCandidate?.startIndex ?? minIndex
  let endIndex = primaryCandidate?.endIndex ?? minIndex
  if (!primaryCandidate) {
    while (startIndex > 0 && series[startIndex - 1].depth >= boundaryThreshold) startIndex -= 1
    while (endIndex < series.length - 1 && series[endIndex + 1].depth >= boundaryThreshold) endIndex += 1
  }

  const leftPeak = minIndex > 0 ? Math.max(...smoothedValues.slice(0, minIndex)) : smoothedValues[0]
  const rightPeak = minIndex < smoothedValues.length - 1 ? Math.max(...smoothedValues.slice(minIndex + 1)) : smoothedValues[smoothedValues.length - 1]
  const dipDepth = baseline - minValue
  const leftDrop = leftPeak - minValue
  const rightRecovery = rightPeak - minValue
  const shapeThreshold = Math.max(0.12, Math.min(0.45, Math.max(workpointContext.normalNoise * 2, dipDepth * 0.3)))
  const sustainedThreshold = baseline - Math.max(0.16, dipDepth * 0.45)
  let sustainedCount = 0
  let longestSustainedCount = 0
  let maxSingleStepDrop = 0
  let maxRawSingleStepDrop = 0
  let dipArea = 0

  for (let index = 0; index < smoothedValues.length; index += 1) {
    if (smoothedValues[index] <= sustainedThreshold) {
      sustainedCount += 1
      longestSustainedCount = Math.max(longestSustainedCount, sustainedCount)
    } else {
      sustainedCount = 0
    }

    if (index > 0) {
      maxSingleStepDrop = Math.max(maxSingleStepDrop, smoothedValues[index - 1] - smoothedValues[index])
      maxRawSingleStepDrop = Math.max(maxRawSingleStepDrop, values[index - 1] - values[index])
    }
    dipArea += Math.max(0, series[index].depth) * (sampleStepMs / 60000)
  }

  const startTimeMs = series[startIndex]?.timeMs
  const valleyTimeMs = series[minIndex]?.timeMs
  const endTimeMs = series[endIndex]?.timeMs
  const durationMin = Number.isFinite(startTimeMs) && Number.isFinite(endTimeMs)
    ? Math.max(sampleStepMs / 60000, (endTimeMs - startTimeMs) / 60000)
    : 0
  const recoveryRatio = dipDepth > 0 ? clamp((series[endIndex].smooth - minValue) / dipDepth, 0, 1) : 0
  const valleyDepthThreshold = Math.max(0.18, dipDepth * 0.42, workpointContext.normalNoise * 2)
  let valleys = countValleys(series, startIndex, endIndex, valleyDepthThreshold)
  if (!valleys.length && dipDepth >= entryThreshold) {
    valleys = [{ index: minIndex, timeMs: valleyTimeMs, value: minValue, depth: dipDepth }]
  }
  const rawShapeThreshold = Math.max(0.18, workpointContext.normalNoise * 3)
  const hasRawShortValley = rawMinIndex > 0 &&
    rawMinIndex < values.length - 1 &&
    rawDipDepth >= Math.max(0.3, workpointContext.normalNoise * 4) &&
    rawLeftDrop >= rawShapeThreshold &&
    rawRightRecovery >= rawShapeThreshold
  if (hasRawShortValley && rawDipDepth > dipDepth) {
    valleys = [{ index: rawMinIndex, timeMs: pairs[rawMinIndex].timeMs, value: rawMinValue, depth: rawDipDepth }]
  }
  const valleyCount = valleys.length
  const candidateCount = dipCandidates.length || (dipDepth >= entryThreshold ? 1 : 0)
  const hasValleyShape = minIndex > 0 && minIndex < smoothedValues.length - 1 && leftDrop >= shapeThreshold && (rightRecovery >= shapeThreshold || recoveryRatio >= 0.25)
  const hasDipCandidate = dipDepth >= entryThreshold && durationMin >= sampleStepMs / 60000
  const windowDurationMin = Math.max(sampleStepMs / 60000, (windowRows[windowRows.length - 1].timeMs - windowRows[0].timeMs) / 60000)
  const deviceStandard = buildAi705DeviceStandard(workpointContext, sampleStepMs, windowDurationMin)
  const shapeQualified = hasValleyShape || hasDipCandidate || hasRawShortValley
  const mildTriggered = shapeQualified &&
    dipDepth >= deviceStandard.mildDrop &&
    durationMin >= deviceStandard.mildDurationMin
  const repeatedSmallDipTriggered = shapeQualified &&
    candidateCount >= 2 &&
    dipDepth >= deviceStandard.mildDrop &&
    windowDurationMin >= deviceStandard.moderateDurationMin
  const moderateTriggered = shapeQualified && (
    (dipDepth >= deviceStandard.moderateDrop && durationMin >= deviceStandard.moderateDurationMin && recoveryRatio >= 0.2) ||
    (repeatedSmallDipTriggered && dipDepth >= deviceStandard.mildDrop * 1.8)
  )
  const severeTriggered = shapeQualified &&
    dipDepth >= deviceStandard.severeDrop &&
    (durationMin >= deviceStandard.severeDurationMin || recoveryRatio < 0.5 || candidateCount >= 2)
  const spikeTriggered = hasValleyShape && maxSingleStepDrop >= 0.28 && dipDepth >= 0.35
  const rawSpikeTriggered = hasRawShortValley && maxRawSingleStepDrop >= 0.18
  const nearTriggered = false
  const triggered = mildTriggered || moderateTriggered || severeTriggered || spikeTriggered || rawSpikeTriggered || repeatedSmallDipTriggered
  const severity = severeTriggered ? 'severe' : moderateTriggered ? 'moderate' : triggered ? 'mild' : 'none'
  const severityText = {
    severe: '重度氮塞',
    moderate: '中度氮塞',
    mild: '轻度氮塞',
    none: '未触发'
  }[severity]
  const shapeType = rawSpikeTriggered
    ? 'short_wave'
    : !hasDipCandidate
    ? 'none'
    : valleyCount >= 2 || candidateCount >= 2
    ? 'multi_valley'
    : hasValleyShape && recoveryRatio >= 0.45
    ? 'single_valley'
    : durationMin >= 20 && recoveryRatio < 0.35
    ? 'low_plateau'
    : hasValleyShape
    ? 'short_wave'
    : 'incomplete'
  const shapeText = shapeTypeText(shapeType)
  const visualConfidence = clamp(
    0.35 +
      (hasValleyShape || hasRawShortValley ? 0.22 : 0) +
      (Math.max(dipDepth, rawDipDepth) >= 0.3 ? 0.14 : 0) +
      (durationMin >= 10 ? 0.12 : 0) +
      (recoveryRatio >= 0.45 ? 0.1 : 0) +
      (valleyCount >= 2 || candidateCount >= 2 ? 0.07 : 0),
    0,
    0.96
  )

  const displayMinValue = rawSpikeTriggered && rawDipDepth > dipDepth ? rawMinValue : minValue
  const displayDipDepth = rawSpikeTriggered && rawDipDepth > dipDepth ? rawDipDepth : dipDepth
  const displayStartTimeMs = rawSpikeTriggered && rawDipDepth > dipDepth ? pairs[Math.max(0, rawMinIndex - 1)]?.timeMs : startTimeMs
  const displayValleyTimeMs = rawSpikeTriggered && rawDipDepth > dipDepth ? pairs[rawMinIndex]?.timeMs : valleyTimeMs
  const displayEndTimeMs = rawSpikeTriggered && rawDipDepth > dipDepth ? pairs[Math.min(pairs.length - 1, rawMinIndex + 1)]?.timeMs : endTimeMs
  const displayDurationMin = rawSpikeTriggered && rawDipDepth > dipDepth
    ? Math.max(sampleStepMs / 60000, (displayEndTimeMs - displayStartTimeMs) / 60000)
    : durationMin
  let basis = `自适应工作点 ${baseline.toFixed(2)}，最低 ${displayMinValue.toFixed(2)}，相对下凹 ${displayDipDepth.toFixed(2)}，持续 ${displayDurationMin.toFixed(0)} min，恢复 ${(recoveryRatio * 100).toFixed(0)}%；未形成完整“下凹-谷底-回升”形态`
  if (triggered) {
    basis = `按6h窗口剔除下凹点估计工作点 ${baseline.toFixed(2)}，识别到${shapeText}；开始 ${formatTime(displayStartTimeMs)}，谷底 ${formatTime(displayValleyTimeMs)}，结束 ${formatTime(displayEndTimeMs)}，最低 ${displayMinValue.toFixed(2)}，相对下凹 ${displayDipDepth.toFixed(2)}，持续 ${displayDurationMin.toFixed(0)} min，恢复 ${(recoveryRatio * 100).toFixed(0)}%，小谷 ${valleyCount} 个，候选下凹 ${candidateCount} 段，${deviceStandard.basis} 分级：${severityText}`
  }

  return {
    triggered,
    nearTriggered,
    severity,
    severityText,
    baseline,
    workpoint: baseline,
    normalBand: workpointContext.normalBand,
    normalNoise: workpointContext.normalNoise,
    sampleCount: workpointContext.sampleCount,
    baseline_value: workpointContext.baselineValue,
    baseline_method: workpointContext.baselineMethod,
    baseline_window: workpointContext.baselineWindow,
    excluded_intervals: workpointContext.excludedIntervals,
    baseline_confidence: workpointContext.baselineConfidence,
    deviceStandard,
    minValue: displayMinValue,
    valleyValue: displayMinValue,
    startMs: displayStartTimeMs,
    valleyMs: displayValleyTimeMs,
    endMs: displayEndTimeMs,
    dipDepth: displayDipDepth,
    durationMin: displayDurationMin,
    recoveryRatio,
    valleyCount,
    candidateCount,
    candidateIntervals: dipCandidates.map((item) => ({
      startMs: series[item.startIndex]?.timeMs,
      endMs: series[item.endIndex]?.timeMs,
      valleyMs: series[item.minIndex]?.timeMs,
      dipDepth: item.dipDepth,
      durationMin: item.durationMin
    })),
    valleys: valleys.map((item, index) => ({ ...item, label: `V${index + 1}` })),
    shapeType,
    shapeText,
    dipArea,
    visualConfidence,
    maxSingleStepDrop,
    maxRawSingleStepDrop,
    longestSustainedCount,
    basis
  }
}

function evaluateMaterialBalance(stats, operatingMode, baselineContext, directionalChecks) {
  const semanticTags = materialBalanceInputTags
  const semanticChecks = semanticTags
    .map((tag) => directionalByTag(directionalChecks, tag))
    .filter(Boolean)
    .map((check) => ({
      tag: check.tag,
      baselineMean: check.baselineMean,
      lowerLimit: check.lowerLimit,
      upperLimit: check.upperLimit,
      currentMean: check.currentMean,
      deviationPct: check.deviationPct,
      direction: check.direction,
      directionText: check.directionText,
      riskLevel: check.riskLevel,
      riskLevelText: check.riskLevelText,
      riskText: check.riskText,
      basis: check.basis,
      role: materialBalanceOutputRoles[check.tag]?.role || '过程变量',
      name: materialBalanceOutputRoles[check.tag]?.name || check.tag
    }))
  const loadCheck = directionalByTag(directionalChecks, 'FIC101')
  const oxygenCheck = directionalByTag(directionalChecks, 'FIQC102')
  const nitrogenCheck = directionalByTag(directionalChecks, 'FIC103')
  const liquidNitrogenCheck = directionalByTag(directionalChecks, 'FIC8')
  const balanceCheck = directionalByTag(directionalChecks, 'BALANCE')
  const inputs = buildMaterialBalanceInputs(directionalChecks)
  const externalModel = buildExternalCompressionBalanceModel(directionalChecks)
  const airIn = loadCheck?.currentMean
  const componentInputs = buildComponentInputs(airIn)
  const knownOutputTotal = sumKnownProductOutputs(directionalChecks)
  const totalResidualPct = Number.isFinite(airIn) && airIn !== 0
    ? ((airIn - knownOutputTotal) / airIn) * 100
    : NaN
  const abnormalInputs = inputs.filter((item) => item.direction !== 'normal' && item.direction !== 'unknown')
  const outputSummary = abnormalInputs.length
    ? abnormalInputs.slice(0, 4).map((item) => `${item.name}${item.directionText}`).join('、')
    : '关键取出量处于同负荷合理范围'

  if (!stats?.valid) {
    return {
      triggered: false,
      summary: '物料平衡测点不足',
      mean: NaN,
      delta: NaN,
      semanticChecks,
      formulaStatus: 'implemented',
      formulaName: 'external_compression_sfit_material_balance',
      formulaText: externalCompressionFormulaText,
      stepPosition: materialBalanceStepPosition,
      mode: operatingMode?.mode || 'unknown',
      inputs,
      externalModel,
      outputs: {
        load_basis: baselineContext?.basis || '',
        allowed_band: `±${defaultAllowedDeviationPct}%`,
        external_model: externalModel,
        checks: inputs
      }
    }
  }
  const swing = stats.max - stats.min
  const triggered = !operatingMode?.dynamic && (
    Math.abs(balanceCheck?.deviationPct || 0) > defaultAllowedDeviationPct ||
    semanticChecks.some((item) => ['medium', 'high'].includes(item.riskLevel))
  )
  const dynamicBlocked = Boolean(operatingMode?.dynamic)
  const rangeText = `${formatMaybe(balanceCheck?.lowerLimit)}% - ${formatMaybe(balanceCheck?.upperLimit)}%`
  return {
    triggered,
    staticApplicable: !dynamicBlocked,
    formulaStatus: 'implemented',
    formulaName: 'external_compression_sfit_material_balance',
    formulaText: externalCompressionFormulaText,
    stepPosition: materialBalanceStepPosition,
    mode: operatingMode?.mode || 'unknown',
    summary: dynamicBlocked
      ? `当前为${operatingMode.label}，静态物料平衡暂不作为原因定位依据；${operatingMode.basis}`
      : `目标负荷 ${formatMaybe(loadCheck?.baselineMean)}，目标氧气 ${formatMaybe(oxygenCheck?.baselineMean)}，目标氮气 ${formatMaybe(nitrogenCheck?.baselineMean)}，目标液氮 ${formatMaybe(liquidNitrogenCheck?.baselineMean)}；物料平衡基准 ${formatMaybe(balanceCheck?.baselineMean)}%，合理范围 ${rangeText}，当前均值 ${stats.mean.toFixed(2)}%，较基准 ${formatPct(balanceCheck?.deviationPct)}，方向证据：${outputSummary}。`,
    baselineBasis: baselineContext?.basis || '',
    loadBasis: baselineContext?.basis || '',
    allowedBand: `±${defaultAllowedDeviationPct}%`,
    mean: stats.mean,
    delta: stats.delta,
    swing,
    allowedDeviationPct: defaultAllowedDeviationPct,
    dryAirComposition,
    externalModel,
    componentInputs,
    knownOutputTotal,
    totalResidualPct,
    inputs,
    semanticChecks,
    targets: {
      load: loadCheck?.baselineMean,
      oxygen: oxygenCheck?.baselineMean,
      nitrogen: nitrogenCheck?.baselineMean,
      liquidNitrogen: liquidNitrogenCheck?.baselineMean
    },
    outputs: {
      mode: dynamicBlocked ? 'dynamic' : 'steady',
      load_basis: baselineContext?.basis || '',
      allowed_band: `±${defaultAllowedDeviationPct}%`,
      total_residual_pct: stats.mean,
      simplified_total_residual_pct: totalResidualPct,
      external_model: externalModel,
      component_inputs: componentInputs,
      checks: inputs,
      abnormal_checks: abnormalInputs
    },
    baselineMean: balanceCheck?.baselineMean,
    lowerLimit: balanceCheck?.lowerLimit,
    upperLimit: balanceCheck?.upperLimit,
    previousMean: balanceCheck?.previousMean,
    deviationPct: balanceCheck?.deviationPct,
    direction: dynamicBlocked ? 'dynamic' : (balanceCheck?.direction || 'normal'),
    directionText: dynamicBlocked ? '动态过程' : (balanceCheck?.directionText || '基本稳定'),
    conclusion: dynamicBlocked
      ? '先按变负荷过程单独标记，后续需使用动态模型或操作记录复核。'
      : triggered
      ? '物料平衡复核发现负荷或取出量偏离，需要把这些方向性证据送入故障树排序。'
      : '物料平衡未超出当前负荷合理波动范围，可降低全流程负荷扰动解释优先级。'
  }
}

function mapAi705SeverityToLevel(severity) {
  if (severity === 'severe') return 'high'
  if (severity === 'moderate') return 'medium'
  if (severity === 'mild') return 'low'
  return 'normal'
}

function nitrogenLevelText(level) {
  return {
    high: '重度氮塞',
    medium: '中度氮塞',
    low: '轻度氮塞',
    normal: '正常'
  }[level] || '待判别'
}

function buildRecognitionSummary(stats, ai705Primary, level) {
  if (!ai705Primary?.triggered && !ai705Primary?.nearTriggered) return 'AI705未形成相对工作点的明确下凹形态'
  const parts = []
  parts.push('AI705下凹形态触发')
  if (ai705Primary.shapeText) parts.push(`形态 ${ai705Primary.shapeText}`)
  if (Number.isFinite(ai705Primary.workpoint)) parts.push(`工作点 ${formatMaybe(ai705Primary.workpoint)}`)
  if (Number.isFinite(ai705Primary.minValue)) parts.push(`最低 ${formatMaybe(ai705Primary.minValue)}`)
  if (Number.isFinite(ai705Primary.dipDepth)) parts.push(`相对下凹 ${formatMaybe(ai705Primary.dipDepth)}`)
  if (Number.isFinite(ai705Primary.durationMin)) parts.push(`持续 ${ai705Primary.durationMin.toFixed(0)} min`)
  if (Number.isFinite(ai705Primary.candidateCount)) parts.push(`候选下凹 ${ai705Primary.candidateCount} 段`)
  if (ai705Primary.deviceStandard?.basis) parts.push(ai705Primary.deviceStandard.basis)
  if (ai705Primary.baseline_confidence) parts.push(`基线可信度 ${ai705Primary.baseline_confidence}`)
  parts.push(`等级 ${nitrogenLevelText(level)}`)
  if (stats.AI705.valid) parts.push(`AI705 ${formatDelta(stats.AI705.delta)}`)
  return parts.join('；')
}

function buildCauses(groups) {
  return [
    {
      id: 'argon',
      branch: '粗氩塔',
      name: '粗氩塔负荷或抽出异常',
      confidence: groups.argonEvidence.length ? '高' : '待确认',
      evidence: groups.argonEvidence,
      advice: groups.argonEvidence.length ? '按粗氩塔分支核对 FI702 是否偏高、FIC701 是否偏低，并补充粗氩塔阻力、液位和冷凝负荷。' : '保留粗氩塔分支，等待 FI702、FIC701、阻力和冷凝负荷证据。',
      risk: '粗氩塔侧重点看进料负荷偏高和粗氩抽出偏低，不把 AI705 本身当作原因。'
    },
    {
      id: 'main',
      branch: '主塔',
      name: '主塔物料分配异常',
      confidence: groups.mainTowerEvidence.length ? '中' : '待确认',
      evidence: groups.mainTowerEvidence,
      advice: groups.mainTowerEvidence.length ? '复核氧气多抽、氮气少抽、V3阀开过大和 AI701 长时间偏高/短时间高高，并用物料平衡方程做二次验证。' : '当前窗口主塔支撑信息不足，继续并行保留。',
      risk: '物料平衡方程用于语义化偏高/偏低和低/中/高偏离程度，不能单独确认主塔原因。'
    },
    {
      id: 'front',
      branch: '空气系统',
      name: '空气量或膨胀空气异常',
      confidence: groups.frontEvidence.length ? '中' : '待确认',
      evidence: groups.frontEvidence,
      advice: groups.frontEvidence.length ? '检查空气少进、膨胀空气旁通量是否偏少，并区分稳态偏离和变负荷过程。' : '预留原料空气量、膨胀空气旁通量和空气系统负荷变化确认项。',
      risk: '空气系统侧重点看空气少进和膨胀空气偏少，需结合稳态/动态运行模式判断。'
    },
    {
      id: 'operation',
      branch: '事件',
      name: '分子筛切换或变负荷事件',
      confidence: groups.operationEvidence.length ? '中' : '待确认',
      evidence: groups.operationEvidence,
      advice: groups.operationEvidence.length ? '核对分子筛切换记录、负荷调整速率和切换后半小时内 AI705 变化。' : '需人工核对分子筛切换时间、切换是否平稳以及是否处于变负荷过程。',
      risk: '事件分支不与主塔阀位重复，重点判断分子筛切换不平稳或动态变负荷导致的氮塞。'
    }
  ]
}

function formatEvidenceValue(check, stats) {
  if (!stats?.valid) return '-'
  if (!check) return `均值 ${stats.mean.toFixed(2)}，变化 ${formatDelta(stats.delta)}`
  return `${check.directionText}；${check.basis}`
}

function evaluateWindow(windowItem, index, sourceRows = windowItem.rows) {
  const stats = Object.fromEntries(availableTags.map((tag) => [tag, calcStats(windowItem.rows, tag)]))
  const baselineContext = buildLoadMatchedBaseline(sourceRows, windowItem, stats)
  const operatingMode = classifyOperatingMode(stats, baselineContext.previousRows)
  const directionalChecks = buildDirectionalChecks(stats, baselineContext)
  const balance = evaluateMaterialBalance(stats.BALANCE, operatingMode, baselineContext, directionalChecks)
  const ai705Primary = evaluateAi705Primary(windowItem.rows, stats.AI705, sourceRows, windowItem)
  const evidence = []
  const addEvidence = (tag, basis) => {
    const direction = directionalByTag(directionalChecks, tag)
    evidence.push({
      tag,
      value: formatEvidenceValue(direction, stats[tag]),
      basis: basis || direction?.riskText || '',
      direction: direction?.direction || 'unknown',
      directionText: direction?.directionText || '待补数据',
      riskLevel: direction?.riskLevel || 'normal',
      riskLevelText: direction?.riskLevelText || '待判别',
      baselineMean: direction?.baselineMean,
      lowerLimit: direction?.lowerLimit,
      upperLimit: direction?.upperLimit,
      currentMean: direction?.currentMean,
      previousMean: direction?.previousMean,
      deviationPct: direction?.deviationPct,
      riskText: direction?.riskText || basis || ''
    })
  }

  if (ai705Primary.triggered || ai705Primary.nearTriggered) addEvidence('AI705', ai705Primary.basis)
  if (['low', 'high'].includes(directionalByTag(directionalChecks, 'AI701')?.direction) || (stats.AI701.valid && Math.abs(stats.AI701.delta) > 0.18)) addEvidence('AI701', 'AI701是重要表现信号，需结合空气、氧气、氮气和阀门共同判断')
  if (directionalByTag(directionalChecks, 'FI702')?.direction === 'high' || (stats.FI702.valid && stats.FI702.delta > 3.5)) addEvidence('FI702', 'FI702偏高表示进入粗氩塔的氩馏分负荷偏高，可能增加氮塞风险')
  if (directionalByTag(directionalChecks, 'FIQC701')?.direction === 'low' || (stats.FIQC701.valid && stats.FIQC701.delta < -3)) addEvidence('FIQC701', '粗氩流量偏低')
  if (directionalByTag(directionalChecks, 'FIQC102')?.direction === 'high' || (stats.FIQC102.valid && stats.FIQC102.delta > 25)) addEvidence('FIQC102', '氧气取出量偏高，需结合主塔负荷判断')
  if (directionalByTag(directionalChecks, 'FIC103')?.direction === 'low' || (stats.FIC103.valid && stats.FIC103.delta < -25)) addEvidence('FIC103', '氮气抽取偏少，可能改变全塔物料分配')
  if (directionalByTag(directionalChecks, 'FI105')?.direction === 'low' || (stats.FI105.valid && stats.FI105.delta < -25)) addEvidence('FI105', '膨胀空气旁通量/增压端空气偏少，可能影响冷量和塔内状态')
  if (directionalByTag(directionalChecks, 'FIC1')?.direction === 'low' || (stats.FIC1.valid && stats.FIC1.delta < -25)) addEvidence('FIC1', '膨胀空气进上塔流量偏低，可能影响冷量和塔内状态')
  if (directionalByTag(directionalChecks, 'AIAS102')?.direction === 'low' || (stats.AIAS102.valid && stats.AIAS102.delta < -0.06)) addEvidence('AIAS102', '氧气纯度偏低')
  if (directionalByTag(directionalChecks, 'FIC101')?.triggered || (stats.FIC101.valid && Math.abs(stats.FIC101.delta) > 55)) addEvidence('FIC101', operatingMode.dynamic ? '负荷处于动态变化，静态诊断降级' : '进塔空气量偏离当前负荷基准')
  if (directionalByTag(directionalChecks, 'V3')?.direction === 'high' || (stats.V3.valid && stats.V3.delta > 1.3)) addEvidence('V3', 'V3阀位偏高，需核对操作记录')
  const argonEvidence = evidence.filter((item) => ['AIAS704', 'FI702', 'FIQC701', 'LIC701'].includes(item.tag))
  const mainTowerEvidence = evidence.filter((item) => ['AI701', 'FIQC102', 'FIC103', 'FIC8', 'AIAS102', 'PdI2', 'PdI1', 'V3'].includes(item.tag))
  const frontEvidence = evidence.filter((item) => ['FIC101', 'FI105', 'FIC1'].includes(item.tag))
  const operationEvidence = operatingMode.dynamic ? evidence.filter((item) => ['FIC101', 'FIQC102', 'FIC103'].includes(item.tag)) : []
  const recognitionEvidence = evidence.filter((item) => item.tag === 'AI705')
  const suspected = ai705Primary.triggered || ai705Primary.nearTriggered
  const primaryOnly = suspected
  const level = suspected ? mapAi705SeverityToLevel(ai705Primary.severity) : 'normal'

  return {
    id: `window-${index}-${windowItem.startMs}`,
    startMs: windowItem.startMs,
    endMs: windowItem.endMs,
    windowLabel: `${formatTime(windowItem.startMs)} - ${formatTime(windowItem.endMs)}`,
    suspected,
    primaryOnly,
    level,
    triggerTags: recognitionEvidence.map((item) => item.tag),
    summary: buildRecognitionSummary(stats, ai705Primary, level),
    ai705Primary,
    operatingMode,
    baseline: {
      baseline_value: ai705Primary.baseline_value,
      baseline_method: ai705Primary.baseline_method,
      baseline_window: ai705Primary.baseline_window,
      excluded_intervals: ai705Primary.excluded_intervals,
      baseline_confidence: ai705Primary.baseline_confidence,
      ai705_workpoint: ai705Primary.workpoint,
      basis: baselineContext.basis,
      sampleCount: baselineContext.baselineRows.length,
      previousSampleCount: baselineContext.previousRows.length
    },
    directionalChecks,
    balance,
    causes: buildCauses({ argonEvidence, mainTowerEvidence, frontEvidence, operationEvidence })
  }
}
