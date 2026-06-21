<template>
  <Teleport to="body">
    <div v-if="visible" class="chart-lightbox" @click.self="emit('close')">
      <div class="chart-lightbox-dialog" role="dialog" aria-modal="true" :aria-label="title || '图表放大预览'">
        <div class="chart-lightbox-head">
          <div class="chart-lightbox-copy">
            <strong>{{ title || '图表放大预览' }}</strong>
            <span v-if="subtitle">{{ subtitle }}</span>
          </div>
          <button class="chart-lightbox-close" type="button" @click="emit('close')">关闭</button>
        </div>
        <div class="chart-lightbox-body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
})

const emit = defineEmits(['close'])

function handleKeydown(event) {
  if (event.key === 'Escape' && props.visible) emit('close')
}

watch(
  () => props.visible,
  (visible) => {
    document.body.classList.toggle('chart-lightbox-open', visible)
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.body.classList.remove('chart-lightbox-open')
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.chart-lightbox{position:fixed;inset:0;z-index:1200;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(15,23,42,.56);backdrop-filter:blur(5px)}
.chart-lightbox-dialog{width:min(1120px,calc(100vw - 32px));max-height:calc(100vh - 32px);display:grid;grid-template-rows:auto minmax(0,1fr);border:1px solid rgba(148,163,184,.22);border-radius:18px;background:#fff;box-shadow:0 30px 80px rgba(15,23,42,.28);overflow:hidden}
.chart-lightbox-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:16px 18px;border-bottom:1px solid rgba(226,232,240,.9);background:linear-gradient(180deg,rgba(239,246,255,.72),rgba(255,255,255,.96))}
.chart-lightbox-copy{display:grid;gap:4px;min-width:0}
.chart-lightbox-copy strong{font-size:16px;line-height:1.35;color:#0f172a}
.chart-lightbox-copy span{font-size:12px;line-height:1.5;color:#64748b}
.chart-lightbox-close{min-height:34px;padding:0 12px;border:1px solid #dbe4f0;border-radius:8px;background:#fff;color:#1d4ed8;font-size:12px;font-weight:700;cursor:pointer}
.chart-lightbox-body{min-height:0;overflow:auto;padding:18px;background:linear-gradient(180deg,#fbfdff,#f8fafc)}
@media (max-width: 720px){
  .chart-lightbox{padding:12px}
  .chart-lightbox-dialog{width:calc(100vw - 16px);max-height:calc(100vh - 16px);border-radius:14px}
  .chart-lightbox-head{padding:14px}
}
</style>
