<template>
  <div class="stream-rail">
    <div class="rail-chip">当前步骤：{{ currentWorkflowStepText }}</div>
    <div class="rail-chip">
      风险：
      <span class="risk-pill" :class="`risk-${currentRiskLevel}`">{{ riskLevelText(currentRiskLevel) }}</span>
    </div>
    <div v-if="llmWorking" class="rail-chip rail-llm-chip" data-testid="rail-llm-working">
      <span class="thinking-spinner active"></span>
      <span>模型处理中 · {{ currentLlmTaskLabel }}</span>
    </div>
    <div class="rail-progress">
      <div class="rail-progress-label">进度 {{ currentProgressPercent }}% <span v-if="currentEtaText">{{ currentEtaText }}</span></div>
      <div class="rail-progress-track"><span class="rail-progress-fill" :style="{ width: `${currentProgressPercent}%` }"></span></div>
    </div>
    <button class="rail-action-btn" data-testid="rail-next-action" type="button" :disabled="!hasActiveAction" @click="$emit('focus-action')">{{ nextActionText }}</button>
  </div>
</template>

<script setup>
defineProps({
  currentWorkflowStepText: { type: String, default: '未进入步骤' },
  currentRiskLevel: { type: String, default: 'low' },
  riskLevelText: { type: Function, required: true },
  llmWorking: { type: Boolean, default: false },
  currentLlmTaskLabel: { type: String, default: '' },
  currentProgressPercent: { type: Number, default: 0 },
  currentEtaText: { type: String, default: '' },
  nextActionText: { type: String, default: '等待下一步动作' },
  hasActiveAction: { type: Boolean, default: false },
})

defineEmits(['focus-action'])
</script>

<style scoped>
.stream-rail{display:grid;grid-template-columns:auto auto auto 1fr auto;gap:10px;align-items:center;padding:10px 20px;border-bottom:1px solid var(--ui-border);background:rgba(248,250,252,.9)}
.rail-chip{display:inline-flex;align-items:center;gap:6px;min-height:30px;padding:0 10px;border:1px solid var(--ui-border);border-radius:999px;font-size:12px;color:var(--ui-muted);background:var(--ui-surface)}
.rail-llm-chip{border-color:#bfdbfe;background:#eff6ff;color:#1d4ed8;font-weight:600}
.rail-progress{display:grid;gap:6px;min-width:0}
.rail-progress-label{font-size:12px;color:var(--ui-muted);display:flex;gap:8px;align-items:center}
.rail-progress-track{height:8px;border-radius:999px;background:#e5e7eb;overflow:hidden}
.rail-progress-fill{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#60a5fa)}
.rail-action-btn{min-height:32px;padding:0 12px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface);font-size:12px;font-weight:600;cursor:pointer}
.rail-action-btn:disabled{opacity:.48;cursor:not-allowed}
.thinking-spinner{width:12px;height:12px;border:2px solid rgba(37,99,235,.22);border-top-color:var(--ui-primary);border-radius:999px}
.thinking-spinner.active{animation:stream-spin .8s linear infinite}
.risk-pill{display:inline-flex;align-items:center;min-height:20px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:700}
.risk-pill.risk-low{background:#ecfdf3;color:#15803d}
.risk-pill.risk-medium{background:#fffbeb;color:#b45309}
.risk-pill.risk-high{background:#fff7ed;color:#c2410c}
.risk-pill.risk-critical{background:#fef2f2;color:#b91c1c}
@keyframes stream-spin{to{transform:rotate(360deg)}}
@media (max-width:980px){.stream-rail{grid-template-columns:1fr}}
</style>
