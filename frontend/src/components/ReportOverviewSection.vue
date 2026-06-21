<template>
  <section v-if="result?.data_overview" class="panel-section">
    <div class="section-title">任务概览</div>
    <div class="detail-list">
      <div class="detail-row"><span>数据文件</span><strong>{{ result.data_overview.file_name || '未记录' }}</strong></div>
      <div class="detail-row"><span>时间点数</span><strong>{{ result.data_overview.timepoint_count ?? '-' }}</strong></div>
      <div class="detail-row"><span>监测点数</span><strong>{{ result.data_overview.sensor_count ?? '-' }}</strong></div>
      <div class="detail-row"><span>有效记录数</span><strong>{{ result.data_overview.effective_record_count ?? '-' }}</strong></div>
      <div class="detail-row"><span>时间范围</span><strong>{{ result.data_overview.time_range_start || '未记录' }} 至 {{ result.data_overview.time_range_end || '未记录' }}</strong></div>
      <div class="detail-row"><span>最新快照时刻</span><strong>{{ result.data_overview.latest_timestamp || '未记录' }}</strong></div>
      <div v-if="sanitizeMeaningfulText(result.data_overview.task_note)" class="detail-row stacked"><span>任务备注</span><strong>{{ sanitizeMeaningfulText(result.data_overview.task_note) }}</strong></div>
    </div>
  </section>

  <section v-if="targetDefinitionItems.length" class="panel-section">
    <div class="section-title">目标定义</div>
    <div class="detail-list">
      <div v-for="item in targetDefinitionItems" :key="item.label" class="detail-row" :class="{ stacked: item.stacked }">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
  </section>

  <section v-if="hasOverview" class="panel-section overview-section">
    <div class="section-title">
      加载后工况总览判断
      <span :class="['status-pill', statusTone]">{{ statusText }}</span>
    </div>
    <div v-if="overviewStats.length" class="overview-kpis">
      <div v-for="item in overviewStats" :key="item.label" class="kpi-item">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
    <div class="detail-list">
      <div class="detail-row stacked">
        <span>总体结论</span>
        <strong>{{ overviewSummary }}</strong>
      </div>
      <div v-if="overviewRiskPoints.length" class="detail-row stacked">
        <span>重点风险</span>
        <div class="risk-list">
          <span v-for="(line, idx) in overviewRiskPoints" :key="`risk-point-${idx}`" class="risk-chip">{{ line }}</span>
        </div>
      </div>
      <div v-for="(line, idx) in overviewHighlights" :key="`overall-highlight-${idx}`" class="detail-row stacked">
        <span>补充说明</span>
        <strong>{{ line }}</strong>
      </div>
    </div>
  </section>

  <section v-if="result?.analysis_steps?.length" class="panel-section">
    <div class="section-title">分析步骤</div>
    <div class="step-list">
      <article v-for="step in result.analysis_steps" :key="`${step.step}-${step.title}`" class="step-card">
        <div class="step-index">步骤 {{ step.step }}</div>
        <div class="step-title">{{ step.title }}</div>
        <div class="step-summary">{{ step.summary }}</div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const STATUS_MAP = {
  stable: { text: '稳定', tone: 'ok' },
  attention: { text: '需关注', tone: 'warn' },
  warning: { text: '预警', tone: 'danger' },
  critical: { text: '高风险', tone: 'danger' },
}

const PLACEHOLDER_PATTERNS = [/^total indicators=/i, /rule-based summary generated/i]

const asFiniteNumber = (value) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

const isPlaceholderText = (line) => {
  const text = `${line || ''}`.trim()
  if (!text) return true
  const normalized = text.replace(/？/g, '?').replace(/\s+/g, '')
  const normalizedPlaceholder = normalized.replace(/[?/／、,，;；:：|｜\\\-_()（）\[\]【】]+/g, '')
  if (normalizedPlaceholder && /^[?]+$/.test(normalizedPlaceholder)) return true
  return PLACEHOLDER_PATTERNS.some((pattern) => pattern.test(text))
}

const sanitizeMeaningfulText = (value) => {
  const text = `${value || ''}`.trim()
  return isPlaceholderText(text) ? '' : text
}

const overview = computed(() => props.result?.overall_judgement || {})
const semanticRows = computed(() => {
  const directRows = Array.isArray(props.result?.semantic_data) ? props.result.semantic_data : []
  if (directRows.length) {
    return directRows.map((item) => `${item?.state_desc || item?.semantic_state || ''}`.trim()).filter(Boolean)
  }
  const semanticEngineRows = overview.value?.three_level_state_engine?.variable_semantics
  return Array.isArray(semanticEngineRows)
    ? semanticEngineRows.map((item) => `${item?.semantic_state || item?.state_label || ''}`.trim()).filter(Boolean)
    : []
})
const statusMeta = computed(() => STATUS_MAP[`${overview.value.status_level || ''}`.toLowerCase()] || STATUS_MAP.attention)
const statusTone = computed(() => statusMeta.value.tone)
const statusText = computed(() => `${overview.value.status_text || statusMeta.value.text || '需关注'}`)

const derivedCounts = computed(() => {
  const rows = semanticRows.value
  if (!rows.length) return null
  let good = 0
  let normal = 0
  let abnormal = 0
  rows.forEach((state) => {
    if (['优秀', '良好', '待机备用'].includes(state)) {
      good += 1
      return
    }
    if (['一般', '正常'].includes(state)) {
      normal += 1
      return
    }
    abnormal += 1
  })
  return {
    total: rows.length,
    good,
    normal,
    abnormal,
  }
})

const targetDefinitionItems = computed(() => {
  const taskNote = sanitizeMeaningfulText(props.result?.data_overview?.task_note || props.result?.task_note || '')
  const primaryGoal = taskNote || (derivedCounts.value?.abnormal ? '异常诊断与状态复核' : '装置运行状态复核')
  const focusNames = Array.isArray(props.result?.abnormal_indicators)
    ? props.result.abnormal_indicators.map((item) => `${item?.name || ''}`.trim()).filter(Boolean)
    : []
  const focusScope = focusNames.length
    ? focusNames.slice(0, 3).join('；')
    : `${overview.value.main_contradiction || overview.value.summary || '围绕当前装置主导矛盾开展复核。'}`
  return [
    { label: '本轮目标', value: primaryGoal, stacked: true },
    { label: '目标来源', value: taskNote ? '用户任务备注 + 当前装置工况' : '系统按当前工况自动归纳', stacked: false },
    {
      label: '判断标准',
      value: '单指标最终判级按目标参考值执行；历史运行基线用于判断是否偏离常态；优态基线用于衡量优化空间。',
      stacked: true,
    },
    { label: '重点范围', value: focusScope, stacked: true },
  ].filter((item) => `${item.value || ''}`.trim())
})

const overviewRiskPoints = computed(() => {
  return (overview.value.risk_points || []).map((line) => `${line || ''}`.trim()).filter((line) => line && !isPlaceholderText(line))
})

const overviewHighlights = computed(() => {
  const riskSet = new Set(overviewRiskPoints.value)
  return (overview.value.highlights || [])
    .map((line) => `${line || ''}`.trim())
    .filter((line) => line && !isPlaceholderText(line) && !riskSet.has(line))
})

const overviewSummary = computed(() => {
  const raw = `${overview.value.summary || ''}`.trim()
  if (raw && !isPlaceholderText(raw)) return raw
  const total = asFiniteNumber(overview.value.total_count)
  const abnormal = asFiniteNumber(overview.value.abnormal_count)
  if (total != null && abnormal != null) {
    const ratio = total > 0 ? ((abnormal / total) * 100).toFixed(1) : '0.0'
    return `本次共评估 ${total} 项指标，识别异常 ${abnormal} 项（${ratio}%），当前风险等级为「${statusText.value}」。`
  }
  return '本轮未生成可用的总体结论，请查看分析步骤和异常明细。'
})

const overviewStats = computed(() => {
  const derived = derivedCounts.value
  const total = derived?.total ?? asFiniteNumber(overview.value.total_count)
  const abnormal = derived?.abnormal ?? asFiniteNumber(overview.value.abnormal_count)
  const good = derived?.good ?? asFiniteNumber(overview.value.good_count)
  const normal = derived?.normal ?? asFiniteNumber(overview.value.normal_count)
  const items = [
    { label: '总指标', value: total },
    { label: '异常数', value: abnormal },
    { label: '良好数', value: good },
    { label: '一般数', value: normal },
  ]
  const ratio = asFiniteNumber(overview.value.risk_ratio) ?? (total ? (Number(abnormal || 0) / total) * 100 : null)
  if (ratio != null) items.push({ label: '异常占比', value: `${ratio.toFixed(1)}%` })
  return items.filter((item) => item.value != null)
})

const hasOverview = computed(() => {
  return Boolean(overviewSummary.value || overviewRiskPoints.value.length || overviewHighlights.value.length)
})
</script>

<style scoped>
.panel-section{padding:13px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface)}
.section-title{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px;font-weight:700}
.section-title::before{content:'';width:4px;height:12px;border-radius:999px;background:var(--ui-primary)}
.detail-list,.step-list{display:grid;gap:10px}
.detail-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px dashed var(--ui-border);font-size:12px}
.detail-row:last-child{padding-bottom:0;border-bottom:none}
.detail-row span{color:var(--ui-muted)}
.detail-row strong{font-weight:700;color:var(--ui-text);text-align:right}
.detail-row.stacked{display:grid;gap:4px}
.detail-row.stacked strong{text-align:left;line-height:1.55}
.overview-section{display:grid;gap:10px}
.status-pill{margin-left:auto;padding:2px 8px;border-radius:999px;font-size:11px;line-height:1.4;border:1px solid transparent}
.status-pill.ok{color:#0f766e;background:rgba(16,185,129,.12);border-color:rgba(16,185,129,.24)}
.status-pill.warn{color:#a16207;background:rgba(245,158,11,.14);border-color:rgba(245,158,11,.28)}
.status-pill.danger{color:#b91c1c;background:rgba(239,68,68,.14);border-color:rgba(239,68,68,.3)}
.overview-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}
.kpi-item{display:grid;gap:4px;padding:8px 9px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.kpi-item span{font-size:11px;color:var(--ui-muted)}
.kpi-item strong{font-size:14px;font-weight:800;color:var(--ui-text)}
.risk-list{display:flex;flex-wrap:wrap;gap:6px}
.risk-chip{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;background:rgba(37,99,235,.08);border:1px solid rgba(37,99,235,.18);color:#1e3a8a;font-size:11px;line-height:1.45}
.step-card{display:grid;gap:5px;padding:11px 12px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.step-index{font-size:11px;font-weight:700;color:var(--ui-primary)}
.step-title{font-size:13px;font-weight:700;color:var(--ui-text)}
.step-summary{font-size:12px;line-height:1.6;color:var(--ui-muted)}
@media (max-width: 960px){
  .overview-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
