<template>
  <section v-if="reportMd || reportPdf" class="panel-section">
    <div class="section-title">报告路径</div>
    <div class="path-list">
      <div class="path-item">文件名：{{ reportFileName }}</div>
      <div v-if="reportMd">{{ reportMd }}</div>
      <div v-if="reportPdf">{{ reportPdf }}</div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  reportFileName: { type: String, default: '尚未生成' },
  reportMd: { type: String, default: '' },
  reportPdf: { type: String, default: '' },
})
</script>

<style scoped>
.panel-section{padding:13px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface)}
.section-title{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:13px;font-weight:700}
.section-title::before{content:'';width:4px;height:12px;border-radius:999px;background:var(--ui-primary)}
.path-list{display:grid;gap:6px;word-break:break-all;font-size:12px;color:var(--ui-muted)}
.path-item{color:var(--ui-text);font-weight:700}
</style>
