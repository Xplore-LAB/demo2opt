<template>
  <section v-if="hasAudit" class="panel-section audit-panel">
    <div class="section-title">中间计算审计</div>

    <div class="audit-hero">
      <div class="audit-hero-copy">
        <span class="audit-kicker">Data Intake + Hybrid Audit</span>
        <strong>{{ intakeHeadline }}</strong>
        <p>{{ intakeReason }}</p>
      </div>
      <div class="audit-kpi-grid">
        <div class="audit-kpi">
          <span>装置状态</span>
          <strong>{{ plantStateText }}</strong>
        </div>
        <div class="audit-kpi">
          <span>风险等级</span>
          <strong>{{ riskLevelText }}</strong>
        </div>
        <div class="audit-kpi">
          <span>异常占比</span>
          <strong>{{ formatRatioPercent(plant.abnormal_ratio) }}</strong>
        </div>
        <div class="audit-kpi">
          <span>混合最大严重度</span>
          <strong>{{ formatNumber(plant.hybrid_max_severity ?? plant.max_severity, 3) }}</strong>
        </div>
      </div>
    </div>

    <div class="audit-grid">
      <article class="audit-card">
        <div class="audit-card-head">
          <strong>数据接入口径</strong>
          <span class="audit-badge">{{ layoutText }}</span>
        </div>
        <div class="audit-meta-list">
          <div class="audit-meta-row">
            <span>数据起始行</span>
            <strong>{{ safeText(intake.data_start_row) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>设计参考值行</span>
            <strong>{{ safeText(intake.design_ref_row, '未识别') }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>时间范围</span>
            <strong>{{ timeRangeText }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>门禁后记录数</span>
            <strong>{{ safeText(intake.record_count_after_gate) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>门禁后时间点数</span>
            <strong>{{ safeText(intake.timepoint_count_after_gate) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>监测点数</span>
            <strong>{{ safeText(intake.sensor_count) }}</strong>
          </div>
        </div>
        <div v-if="droppedRowsText" class="audit-note-block">
          <span>排除行</span>
          <p>{{ droppedRowsText }}</p>
        </div>
      </article>

      <article class="audit-card">
        <div class="audit-card-head">
          <strong>历史模型</strong>
          <span class="audit-badge">{{ safeText(historyMeta.profile_source, 'runtime') }}</span>
        </div>
        <div class="audit-meta-list">
          <div class="audit-meta-row">
            <span>工况锚点</span>
            <strong>{{ safeText(historyMeta.anchor_tag) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>当前工况档位</span>
            <strong>{{ safeText(historyMeta.selected_regime) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>全局回退</span>
            <strong>{{ yesNo(historyMeta.global_fallback_used) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>风险升级开关</span>
            <strong>{{ yesNo(historyMeta.hybrid_aggregation_enabled) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>低/高分位切点</span>
            <strong>{{ regimeCutText }}</strong>
          </div>
        </div>
      </article>
    </div>

    <div class="audit-grid">
      <article class="audit-card">
        <div class="audit-card-head">
          <strong>装置聚合</strong>
          <span class="audit-badge">{{ plantBranchText }}</span>
        </div>
        <div class="audit-meta-list">
          <div class="audit-meta-row">
            <span>装置状态分支</span>
            <strong>{{ safeText(plant.plant_state_branch) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>风险分支</span>
            <strong>{{ safeText(plant.risk_branch) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>规则最大严重度</span>
            <strong>{{ formatNumber(plant.max_severity, 3) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>历史 warning/high</span>
            <strong>{{ safeText(plant.history_warning_count, 0) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>规则/历史不一致</span>
            <strong>{{ safeText(plant.conflict_indicator_count, 0) }}</strong>
          </div>
          <div class="audit-meta-row">
            <span>风险是否升级</span>
            <strong>{{ yesNo(plant.risk_upgrade_applied) }}</strong>
          </div>
        </div>
        <div v-if="dominantAnomalyText" class="audit-note-block">
          <span>主导异常</span>
          <p>{{ dominantAnomalyText }}</p>
        </div>
        <div v-if="temporalText" class="audit-note-block">
          <span>时间先后性</span>
          <p>{{ temporalText }}</p>
        </div>
        <div v-if="mainContradictionText" class="audit-note-block">
          <span>主导矛盾</span>
          <p>{{ mainContradictionText }}</p>
        </div>
      </article>

      <article class="audit-card">
        <div class="audit-card-head">
          <strong>统计判断摘要</strong>
          <span class="audit-badge">{{ historySummaryText }}</span>
        </div>
        <div class="audit-note-stack">
          <div v-for="item in historyHighlights" :key="item.key" class="audit-note-block">
            <span>{{ item.title }}</span>
            <p>{{ item.text }}</p>
          </div>
        </div>
      </article>
    </div>

    <article v-if="subsystems.length" class="audit-card">
      <div class="audit-card-head">
        <strong>子系统聚合输入</strong>
        <span class="audit-badge">{{ subsystems.length }} 个子系统</span>
      </div>
      <div class="subsystem-list">
        <div v-for="item in subsystems" :key="item.name || item.state" class="subsystem-item">
          <div class="subsystem-head">
            <strong>{{ item.name || '未命名子系统' }}</strong>
            <span class="subsystem-state">{{ item.state || 'unknown' }}</span>
          </div>
          <div class="subsystem-meta">
            异常 {{ safeText(item.abnormal_count) }}/{{ safeText(item.total_count) }}
            · 占比 {{ formatRatioPercent(item.abnormal_ratio) }}
            · 规则均值 {{ formatNumber(item.avg_severity, 3) }}
            · 混合均值 {{ formatNumber(item.hybrid_avg_severity, 3) }}
          </div>
          <div class="subsystem-meta muted">
            历史 warning/high {{ safeText(item.history_warning_count, 0) }}
            · 不一致 {{ safeText(item.conflict_indicator_count, 0) }}
          </div>
          <div v-if="item.members?.length" class="subsystem-members">{{ item.members.join('、') }}</div>
          <div v-if="item.triggered_by?.length" class="subsystem-trigger">命中分支：{{ item.triggered_by.join('；') }}</div>
        </div>
      </div>
    </article>

    <article v-if="indicatorRows.length" class="audit-card">
      <div class="audit-card-head">
        <strong>单指标审计表</strong>
        <span class="audit-badge">{{ indicatorRows.length }} 项</span>
      </div>
      <div class="audit-table-wrap">
        <table class="audit-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>当前值</th>
              <th>目标参考</th>
              <th>历史中位</th>
              <th>优态基线</th>
              <th>工况档位</th>
              <th>统计判断</th>
              <th>状态</th>
              <th>严重度</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in indicatorRows" :key="item.key">
              <td class="name-cell">
                <strong>{{ item.name }}</strong>
                <span class="row-sub">{{ item.subtext }}</span>
              </td>
              <td>{{ item.current }}</td>
              <td>{{ item.target }}</td>
              <td>{{ item.history }}</td>
              <td>{{ item.optimal }}</td>
              <td>{{ item.regime }}</td>
              <td>
                <span>{{ item.statState }}</span>
                <span class="row-sub">{{ item.statScore }}</span>
                <span class="row-sub" :class="item.agreementTone">{{ item.agreement }}</span>
              </td>
              <td>
                <span>{{ item.state }}</span>
                <span class="row-sub" :class="item.diffTone">{{ item.diff }}</span>
              </td>
              <td>
                <span>{{ item.severity }}</span>
                <span class="row-sub">hybrid {{ item.hybridSeverity }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <div v-if="auditPath" class="audit-trace">
      <span>审计文件</span>
      <code>{{ auditPath }}</code>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const audit = computed(() => {
  const direct = props.result?.calculation_audit
  if (direct && typeof direct === 'object') return direct
  const nested = props.result?.overall_judgement?.calculation_audit
  return nested && typeof nested === 'object' ? nested : {}
})

const intake = computed(() => audit.value?.data_intake || {})
const plant = computed(() => audit.value?.plant || {})
const subsystems = computed(() => Array.isArray(audit.value?.subsystems) ? audit.value.subsystems : [])
const indicators = computed(() => Array.isArray(audit.value?.indicators) ? audit.value.indicators : [])
const historyMeta = computed(() => audit.value?.history_model_metadata || props.result?.history_model_metadata || {})
const dominant = computed(() => plant.value?.dominant_anomaly || {})
const auditPath = computed(() => props.result?.traceability?.trace_files?.calculation_audit || '')

const hasAudit = computed(() => {
  return Boolean(
    Object.keys(intake.value).length
    || Object.keys(plant.value).length
    || subsystems.value.length
    || indicators.value.length
  )
})

function asNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function safeText(value, fallback = '-') {
  if (value === null || value === undefined || value === '') return fallback
  return `${value}`
}

function formatNumber(value, digits = 2) {
  const parsed = asNumber(value)
  return parsed == null ? '-' : parsed.toFixed(digits)
}

function formatRatioPercent(value) {
  const parsed = asNumber(value)
  return parsed == null ? '-' : `${(parsed * 100).toFixed(1)}%`
}

function formatSignedPercent(value) {
  const parsed = asNumber(value)
  if (parsed == null) return '-'
  const sign = parsed >= 0 ? '+' : ''
  return `${sign}${parsed.toFixed(1)}%`
}

function yesNo(value) {
  return value ? '是' : '否'
}

const layoutText = computed(() => safeText(intake.value.layout_detected, '未记录'))
const timeRangeText = computed(() => {
  const first = safeText(intake.value.first_included_timestamp, '未记录')
  const last = safeText(intake.value.last_included_timestamp, '未记录')
  return `${first} 至 ${last}`
})
const intakeHeadline = computed(() => {
  const count = safeText(intake.value.timepoint_count_after_gate, '-')
  const sensors = safeText(intake.value.sensor_count, '-')
  return `${layoutText.value} · ${count} 个时间点 · ${sensors} 个指标`
})
const intakeReason = computed(() => safeText(intake.value.count_change_reason, '当前未记录口径变化原因。'))
const droppedRowsText = computed(() => {
  const rows = Array.isArray(intake.value.dropped_rows) ? intake.value.dropped_rows : []
  if (!rows.length) return ''
  return rows
    .map((row) => `row=${safeText(row?.row_index)}, reason=${safeText(row?.reason)}`)
    .join('；')
})

const plantStateText = computed(() => safeText(plant.value.plant_state_label || plant.value.plant_state, '未记录'))
const riskLevelText = computed(() => safeText(plant.value.risk_level_label || plant.value.risk_level, '未记录'))
const plantBranchText = computed(() => {
  const risk = safeText(plant.value.risk_branch, 'unknown')
  const state = safeText(plant.value.plant_state_branch, 'unknown')
  return `${risk} / ${state}`
})
const mainContradictionText = computed(() => safeText(plant.value.main_contradiction, ''))
const dominantAnomalyText = computed(() => {
  const name = safeText(dominant.value.indicator_name, '')
  const label = safeText(dominant.value.candidate_label, '')
  return [name, label].filter(Boolean).join(' · ')
})
const temporalText = computed(() => safeText(dominant.value.temporal_precedence_explanation, ''))

const regimeCutText = computed(() => {
  const cuts = historyMeta.value?.regime_cut_points || {}
  return `low<=${formatNumber(cuts.low_max)} / high>=${formatNumber(cuts.high_min)}`
})

const historySummaryText = computed(() => {
  const warning = safeText(plant.value.history_warning_count, 0)
  const conflict = safeText(plant.value.conflict_indicator_count, 0)
  return `warning/high ${warning} · 冲突 ${conflict}`
})

const historyHighlights = computed(() => {
  return indicators.value
    .slice()
    .sort((left, right) => (asNumber(right?.statistical_anomaly_score) || 0) - (asNumber(left?.statistical_anomaly_score) || 0))
    .slice(0, 3)
    .map((item, index) => ({
      key: item?.tag_id || `history-${index}`,
      title: safeText(item?.name, '未命名指标'),
      text: `regime=${safeText(item?.selected_regime)}；state=${safeText(item?.statistical_state)}；score=${formatNumber(item?.statistical_anomaly_score, 3)}；agreement=${safeText(item?.agreement_flag)}；hybrid=${formatNumber(item?.hybrid_severity_score, 3)}`,
    }))
})

const indicatorRows = computed(() => {
  return indicators.value
    .slice()
    .sort((left, right) => {
      const rightScore = asNumber(right?.hybrid_severity_score) ?? asNumber(right?.severity_score) ?? 0
      const leftScore = asNumber(left?.hybrid_severity_score) ?? asNumber(left?.severity_score) ?? 0
      return rightScore - leftScore
    })
    .map((item, index) => {
      const diff = asNumber(item?.diff_percent)
      const agreement = safeText(item?.agreement_flag, '-')
      return {
        key: item?.tag_id || item?.name || `indicator-${index}`,
        name: safeText(item?.name, '未命名指标'),
        current: formatNumber(item?.current_value),
        target: formatNumber(item?.target_reference),
        history: formatNumber(item?.history_baseline),
        optimal: formatNumber(item?.optimal_reference),
        regime: safeText(item?.selected_regime, '-'),
        statState: safeText(item?.statistical_state, '-'),
        statScore: `score ${formatNumber(item?.statistical_anomaly_score, 3)}`,
        agreement,
        agreementTone: agreement === 'agree' ? '' : 'tone-warn',
        basis: safeText(item?.final_grade_basis_label || item?.final_grade_basis, '-'),
        state: safeText(item?.state_label, '-'),
        diff: formatSignedPercent(diff),
        diffTone: diff == null ? '' : diff >= 0 ? 'tone-up' : 'tone-down',
        severity: formatNumber(item?.severity_score, 3),
        hybridSeverity: formatNumber(item?.hybrid_severity_score, 3),
        subtext: `basis ${safeText(item?.final_grade_basis_label || item?.final_grade_basis, '-')}`,
      }
    })
})
</script>

<style scoped>
.panel-section{padding:13px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface)}
.section-title{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px;font-weight:700}
.section-title::before{content:'';width:4px;height:12px;border-radius:999px;background:var(--ui-primary)}
.audit-panel{display:grid;gap:12px}
.audit-hero{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:12px}
.audit-hero-copy,.audit-kpi,.audit-card,.audit-trace{min-width:0;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.audit-hero-copy{display:grid;gap:6px;padding:14px 15px}
.audit-kicker{font-size:11px;font-weight:700;letter-spacing:.02em;text-transform:uppercase;color:var(--ui-primary)}
.audit-hero-copy strong{font-size:18px;line-height:1.3;color:var(--ui-text)}
.audit-hero-copy p{margin:0;font-size:12px;line-height:1.6;color:var(--ui-muted)}
.audit-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.audit-kpi{display:grid;gap:4px;padding:12px}
.audit-kpi span{font-size:11px;color:var(--ui-muted)}
.audit-kpi strong{font-size:15px;line-height:1.35;color:var(--ui-text)}
.audit-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.audit-card{display:grid;gap:10px;padding:13px}
.audit-card-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;min-width:0}
.audit-card-head strong{min-width:0;font-size:13px;line-height:1.4;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.audit-badge{display:inline-flex;align-items:center;min-height:24px;max-width:100%;padding:0 8px;border:1px solid rgba(37,99,235,.16);border-radius:999px;background:rgba(37,99,235,.08);font-size:11px;font-weight:700;color:#1e3a8a;overflow-wrap:anywhere;word-break:break-word}
.audit-meta-list{display:grid;gap:8px}
.audit-meta-row{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px dashed var(--ui-border);font-size:12px;min-width:0}
.audit-meta-row:last-child{padding-bottom:0;border-bottom:none}
.audit-meta-row span{flex:0 1 110px;color:var(--ui-muted);overflow-wrap:anywhere;word-break:break-word}
.audit-meta-row strong{flex:1 1 180px;min-width:0;text-align:right;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.audit-note-block{display:grid;gap:3px;padding:10px;border-radius:8px;background:rgba(241,245,249,.78)}
.audit-note-block span{font-size:11px;font-weight:700;color:var(--ui-muted)}
.audit-note-block p{margin:0;font-size:12px;line-height:1.6;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.audit-note-stack{display:grid;gap:8px}
.subsystem-list{display:grid;gap:10px}
.subsystem-item{display:grid;gap:6px;padding:11px;border:1px solid var(--ui-border);border-radius:8px;background:rgba(255,255,255,.8)}
.subsystem-head{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;min-width:0}
.subsystem-head strong{min-width:0;font-size:13px;line-height:1.35;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.subsystem-state{font-size:11px;font-weight:700;color:#1d4ed8;overflow-wrap:anywhere;word-break:break-word}
.subsystem-meta,.subsystem-members,.subsystem-trigger{font-size:11px;line-height:1.55;overflow-wrap:anywhere;word-break:break-word}
.subsystem-meta{color:var(--ui-text)}
.subsystem-meta.muted,.subsystem-members,.subsystem-trigger{color:var(--ui-muted)}
.audit-table-wrap{overflow:auto;border:1px solid var(--ui-border);border-radius:8px}
.audit-table{width:100%;table-layout:fixed;border-collapse:collapse;min-width:1080px;background:#fff}
.audit-table th,.audit-table td{padding:10px 12px;border-bottom:1px solid rgba(226,232,240,.9);font-size:12px;line-height:1.55;text-align:left;vertical-align:top;white-space:normal;overflow-wrap:anywhere;word-break:break-word;hyphens:auto}
.audit-table th{position:sticky;top:0;background:#f8fafc;color:var(--ui-muted);font-size:11px;font-weight:700;letter-spacing:.01em;z-index:1}
.audit-table tbody tr:hover{background:rgba(239,246,255,.58)}
.audit-table th:nth-child(1),.audit-table td:nth-child(1){width:19%}
.audit-table th:nth-child(2),.audit-table td:nth-child(2),
.audit-table th:nth-child(3),.audit-table td:nth-child(3),
.audit-table th:nth-child(4),.audit-table td:nth-child(4),
.audit-table th:nth-child(5),.audit-table td:nth-child(5),
.audit-table th:nth-child(6),.audit-table td:nth-child(6){width:8%}
.audit-table th:nth-child(7),.audit-table td:nth-child(7){width:14%}
.audit-table th:nth-child(8),.audit-table td:nth-child(8){width:13%}
.audit-table th:nth-child(9),.audit-table td:nth-child(9){width:14%}
.name-cell{min-width:0}
.name-cell strong{display:block;font-size:12px;line-height:1.5;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.row-sub{display:block;margin-top:3px;font-size:11px;color:var(--ui-muted);overflow-wrap:anywhere;word-break:break-word}
.tone-up{color:#c2410c;font-weight:700}
.tone-down{color:#1d4ed8;font-weight:700}
.tone-warn{color:#b45309;font-weight:700}
.audit-trace{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:11px 13px}
.audit-trace span{font-size:11px;font-weight:700;color:var(--ui-muted)}
.audit-trace code{padding:4px 8px;border-radius:6px;background:var(--ui-surface-tint);font-size:11px;line-height:1.5;color:var(--ui-text);word-break:break-all}

@media (max-width: 1100px){
  .audit-hero,.audit-grid{grid-template-columns:1fr}
}

@media (max-width: 760px){
  .audit-kpi-grid{grid-template-columns:1fr 1fr}
}

@media (max-width: 640px){
  .audit-kpi-grid{grid-template-columns:1fr}
}
</style>
