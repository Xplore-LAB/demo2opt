<template>
  <section class="panel-section">
    <div class="section-title">异常指标</div>
    <div v-if="abnormalIndicators?.length" class="abnormal-detail-list">
      <div
        v-for="ind in abnormalIndicators"
        :key="ind.tag_id || ind.name"
        class="abnormal-detail-card"
        :class="getIndicatorTone(ind)"
      >
        <div class="abnormal-detail-head">
          <strong>{{ ind.name }}</strong>
          <span class="state-tag" :class="getIndicatorTone(ind)">{{ ind.level }}</span>
        </div>
        <div class="abnormal-detail-meta">当前值 {{ formatNumber(ind.current_value) }} / 偏差 {{ formatDiffSummary(ind) }}</div>
        <div class="abnormal-detail-text"><span>时间窗口</span>{{ formatWindowSummary(ind) }}</div>
        <div class="abnormal-detail-text"><span>规则原因</span>{{ ind.rule_reason || '当前未生成规则原因' }}</div>
        <div v-if="ind.ai_reason" class="abnormal-detail-text"><span>AI复核</span>{{ ind.ai_reason }}</div>
        <div class="abnormal-detail-text"><span>当前快照</span>{{ formatCurrentSnapshot(ind) }}</div>
      </div>
    </div>
    <div v-else class="state-tag ok">当前未发现异常指标。</div>
  </section>

  <section v-if="semanticSummary" class="panel-section">
    <div class="section-title">规则复核摘要</div>
    <div class="detail-list">
      <div v-if="Object.keys(semanticSummary.state_counts || {}).length" class="detail-row stacked">
        <span>状态分布</span>
        <strong>{{ Object.entries(semanticSummary.state_counts || {}).map(([state, count]) => `${state} ${count}`).join(' / ') }}</strong>
      </div>
      <div v-if="Object.keys(semanticSummary.trend_counts || {}).length" class="detail-row stacked">
        <span>趋势分布</span>
        <strong>{{ Object.entries(semanticSummary.trend_counts || {}).map(([trend, count]) => `${trend} ${count}`).join(' / ') }}</strong>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  abnormalIndicators: { type: Array, default: () => [] },
  semanticSummary: { type: Object, default: null },
  getIndicatorTone: { type: Function, required: true },
  formatNumber: { type: Function, required: true },
  formatDiffSummary: { type: Function, required: true },
  formatWindowSummary: { type: Function, required: true },
  formatCurrentSnapshot: { type: Function, required: true },
})
</script>

<style scoped>
.panel-section{padding:13px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface)}
.section-title{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px;font-weight:700}
.section-title::before{content:'';width:4px;height:12px;border-radius:999px;background:var(--ui-primary)}
.abnormal-detail-list{display:grid;gap:10px}
.abnormal-detail-card{display:grid;gap:8px;padding:12px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.abnormal-detail-card.ok{border-color:#bbf7d0;background:#f0fdf4}
.abnormal-detail-card.warn{border-color:#fdba74;background:#fff7ed}
.abnormal-detail-card.danger{border-color:#fecaca;background:#fef2f2}
.abnormal-detail-card.info{border-color:#bfdbfe;background:#eff6ff}
.abnormal-detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.abnormal-detail-head strong{min-width:0;font-size:13px;line-height:1.4}
.abnormal-detail-meta{font-size:12px;font-weight:600;color:var(--ui-text)}
.abnormal-detail-text{display:grid;gap:2px;font-size:11px;line-height:1.55;color:var(--ui-text)}
.abnormal-detail-text span{color:var(--ui-muted);font-weight:700}
.state-tag{display:inline-flex;align-items:center;padding:9px 10px;border:1px solid var(--ui-border);border-radius:8px;font-size:12px}
.state-tag.ok{background:#f0fdf4;border-color:#bbf7d0}
.state-tag.warn{background:#fff7ed;border-color:#fdba74;color:#c2410c}
.state-tag.info{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
.state-tag.danger{color:#dc2626}
.detail-list{display:grid;gap:10px}
.detail-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px dashed var(--ui-border);font-size:12px}
.detail-row:last-child{padding-bottom:0;border-bottom:none}
.detail-row span{color:var(--ui-muted)}
.detail-row strong{font-weight:700;color:var(--ui-text);text-align:right}
.detail-row.stacked{display:grid;gap:4px}
.detail-row.stacked strong{text-align:left;line-height:1.55}
</style>
