<template>
  <aside class="workspace-collapsed-rail" data-testid="workspace-collapsed-rail" aria-label="右侧面板已折叠">
    <button
      class="rail-expand-btn"
      data-testid="expand-workspace"
      type="button"
      aria-label="展开右侧面板"
      @click="$emit('expand')"
    >
      展开
    </button>

    <div class="rail-tabs" role="tablist" aria-label="折叠导航">
      <button
        class="rail-tab"
        :class="{ active: props.activeTab === 'monitor' }"
        type="button"
        role="tab"
        :aria-selected="String(props.activeTab === 'monitor')"
        aria-label="实时监控"
        @click="$emit('switch-tab', 'monitor')"
      >
        <span class="rail-tab-short">监</span>
        <small>监控</small>
      </button>
      <button
        class="rail-tab"
        :class="{ active: props.activeTab === 'report' }"
        type="button"
        role="tab"
        :aria-selected="String(props.activeTab === 'report')"
        aria-label="分析报告"
        @click="$emit('switch-tab', 'report')"
      >
        <span class="rail-tab-short">报</span>
        <small>报告</small>
      </button>
    </div>

    <div class="rail-status">
      <span class="rail-status-dot" :class="{ running: props.isRunning }"></span>
      <span>{{ props.isRunning ? '运行中' : '空闲' }}</span>
    </div>
  </aside>
</template>

<script setup lang="ts">
const props = defineProps<{
  activeTab: 'monitor' | 'report'
  isRunning: boolean
}>()

defineEmits<{
  (event: 'expand'): void
  (event: 'switch-tab', tab: 'monitor' | 'report'): void
}>()
</script>

<style scoped>
.workspace-collapsed-rail {
  position: relative;
  min-width: 56px;
  width: 56px;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 10px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.workspace-collapsed-rail::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: linear-gradient(90deg, #2563eb, rgba(37, 99, 235, 0.12));
}

.rail-expand-btn,
.rail-tab {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  color: #374151;
  cursor: pointer;
}

.rail-expand-btn {
  min-height: 32px;
  font-size: 12px;
  font-weight: 700;
}

.rail-tabs {
  width: 100%;
  display: grid;
  gap: 8px;
}

.rail-tab {
  display: grid;
  justify-items: center;
  gap: 2px;
  padding: 6px 4px;
}

.rail-tab.active {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.rail-tab-short {
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}

.rail-tab small {
  font-size: 10px;
  line-height: 1;
}

.rail-status {
  margin-top: auto;
  display: grid;
  justify-items: center;
  gap: 4px;
  font-size: 10px;
  color: #6b7280;
}

.rail-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #9ca3af;
}

.rail-status-dot.running {
  background: #16a34a;
}
</style>
