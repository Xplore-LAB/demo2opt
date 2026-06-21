export const workflowStepTitleMap = {
  1: '数据加载与范围确认',
  2: '最新时刻快照提取',
  3: '规则预筛与语义复核',
  4: '工况总览判断',
  5: '时序特征提取与候选复核',
  6: '外挂知识库 API 检索手段',
  7: 'AI 根因诊断',
  8: '决策验证与报告生成',
}

const riskLevelOrder = { low: 1, medium: 2, high: 3, critical: 4 }
const riskLabelMap = { low: '低', medium: '中', high: '高', critical: '极高' }

const phaseStepToWorkflowMap = {
  init: { running: { 0: 1, 1: 1 }, completed: 2 },
  analysis: { running: { 0: 3, 1: 3, 2: 4, 3: 5, 4: 7 }, completed: 8 },
  report: { running: { 0: 8 }, completed: 8 },
}

const checkpointToWorkflowMap = {
  init_data_range_confirm: 1,
  analysis_overview_confirm: 4,
  analysis_candidate_confirm: 5,
  analysis_high_risk_confirm: 7,
}

const phaseDefaultWorkflowStep = { init: 1, analysis: 5, report: 8 }

export const normalizeRiskLevel = (value = '') => {
  const raw = `${value || ''}`.toLowerCase()
  if (riskLevelOrder[raw]) return raw
  if (raw.includes('critical') || raw.includes('严重')) return 'critical'
  if (raw.includes('high') || raw.includes('危险') || raw.includes('高')) return 'high'
  if (raw.includes('medium') || raw.includes('warning') || raw.includes('偏')) return 'medium'
  return 'low'
}

export const riskLevelText = (value = 'low') => riskLabelMap[normalizeRiskLevel(value)] || riskLabelMap.low
export const compareRiskLevel = (left = 'low', right = 'low') => riskLevelOrder[normalizeRiskLevel(left)] - riskLevelOrder[normalizeRiskLevel(right)]
export const maxRiskLevel = (left = 'low', right = 'low') => (compareRiskLevel(left, right) >= 0 ? normalizeRiskLevel(left) : normalizeRiskLevel(right))

export const normalizeWorkflowStepId = (value) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return null
  const rounded = Math.round(parsed)
  if (rounded < 1 || rounded > 8) return null
  return rounded
}

export function resolveWorkflowFromPhaseUpdate(data = {}, session = null) {
  const payloadStepId = normalizeWorkflowStepId(data.workflow_step_id)
  if (payloadStepId) {
    return {
      id: payloadStepId,
      title: data.workflow_step_title || workflowStepTitleMap[payloadStepId] || '',
    }
  }

  const phase = data.phase || session?.currentPhase || 'system'
  const status = data.status || 'running'
  const phaseConfig = phaseStepToWorkflowMap[phase]
  let fallbackStepId = null
  if (phaseConfig) {
    const statusConfig = phaseConfig[status]
    if (typeof statusConfig === 'number') {
      fallbackStepId = statusConfig
    } else if (statusConfig && data.step !== undefined && data.step !== null) {
      fallbackStepId = statusConfig[data.step] ?? null
    }
  }
  if (!fallbackStepId) fallbackStepId = phaseDefaultWorkflowStep[phase] || null
  if (!fallbackStepId) return { id: null, title: '' }
  return { id: fallbackStepId, title: workflowStepTitleMap[fallbackStepId] || '' }
}

export function resolveWorkflowFromInteraction(data = {}, session = null) {
  const payloadStepId = normalizeWorkflowStepId(data.workflow_step_id)
  if (payloadStepId) {
    return {
      id: payloadStepId,
      title: data.workflow_step_title || workflowStepTitleMap[payloadStepId] || '',
    }
  }
  const checkpointKey = `${data.checkpoint_key || ''}`.trim()
  const mappedStepId = checkpointToWorkflowMap[checkpointKey]
  if (mappedStepId) return { id: mappedStepId, title: workflowStepTitleMap[mappedStepId] || '' }
  const phase = data.phase || session?.currentPhase || 'analysis'
  const fallbackStepId = phaseDefaultWorkflowStep[phase] || null
  if (!fallbackStepId) return { id: null, title: '' }
  return { id: fallbackStepId, title: workflowStepTitleMap[fallbackStepId] || '' }
}

export const formatWorkflowStepLabel = (stepId, stepTitle) => {
  const normalizedStepId = normalizeWorkflowStepId(stepId)
  if (!normalizedStepId) return stepTitle || '未进入步骤'
  const normalizedTitle = stepTitle || workflowStepTitleMap[normalizedStepId] || ''
  return normalizedTitle ? `步骤 ${normalizedStepId}/8 · ${normalizedTitle}` : `步骤 ${normalizedStepId}/8`
}

export function resolvePhaseStepState(payload = {}) {
  const explicitState = `${payload.workflow_step_state || ''}`.toLowerCase()
  if (explicitState === 'started' || explicitState === 'completed' || explicitState === 'failed') return explicitState
  const status = `${payload.status || ''}`.toLowerCase()
  const phase = `${payload.phase || ''}`.toLowerCase()
  const stepId = normalizeWorkflowStepId(payload.workflowStepId)
  if (status === 'completed' && phase === 'analysis' && stepId === 8) return ''
  if (status === 'completed') return 'completed'
  if (status === 'error') return 'failed'
  if (status === 'running') return 'started'
  return ''
}
