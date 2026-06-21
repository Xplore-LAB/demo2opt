<template>
  <section v-if="card" ref="rootRef" class="action-card" data-testid="action-card">
    <div class="action-card-head">
      <strong>{{ card.title }}</strong>
      <span class="risk-pill" :class="`risk-${card.riskLevel || 'low'}`">风险 {{ riskLevelText(card.riskLevel || 'low') }}</span>
    </div>
    <div class="action-card-desc" v-html="renderMarkdown(card.desc || '')"></div>
    <div v-if="card.impactScope?.length" class="action-card-scope">影响范围：{{ card.impactScope.join(' / ') }}</div>
    <div class="action-card-recommend">推荐动作：{{ card.recommendedAction || getInteractionActionText(card, 'yes') }}</div>
    <div class="action-card-actions">
      <el-button data-testid="action-continue" size="small" type="primary" @click="$emit('reply', card, 'yes')">{{ getInteractionActionText(card, 'yes') }}</el-button>
      <el-button data-testid="action-stop" size="small" @click="$emit('reply', card, 'no')">{{ getInteractionActionText(card, 'no') }}</el-button>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  card: { type: Object, default: null },
  riskLevelText: { type: Function, required: true },
  renderMarkdown: { type: Function, required: true },
  getInteractionActionText: { type: Function, required: true },
})

defineEmits(['reply'])

const rootRef = ref(null)

defineExpose({
  scrollIntoView(options) {
    rootRef.value?.scrollIntoView(options)
  },
})
</script>

<style scoped>
.action-card{margin:0 20px 14px;padding:12px;border:1px solid #bfdbfe;border-radius:8px;background:linear-gradient(180deg,#eff6ff,#dbeafe)}
.action-card-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.action-card-desc{margin-top:8px;line-height:1.58}
.action-card-scope,.action-card-recommend{margin-top:6px;font-size:12px;color:var(--ui-muted)}
.action-card-actions{margin-top:10px;display:flex;gap:10px}
.risk-pill{display:inline-flex;align-items:center;min-height:20px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:700}
.risk-pill.risk-low{background:#ecfdf3;color:#15803d}
.risk-pill.risk-medium{background:#fffbeb;color:#b45309}
.risk-pill.risk-high{background:#fff7ed;color:#c2410c}
.risk-pill.risk-critical{background:#fef2f2;color:#b91c1c}
@media (max-width:980px){.action-card{margin-left:14px;margin-right:14px}}
@media (max-width:760px){.action-card-actions{flex-direction:column}}
</style>
