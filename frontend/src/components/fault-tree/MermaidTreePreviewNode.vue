<template>
  <div class="preview-node">
    <div class="preview-card">
      <span>{{ node.node_type }}</span>
      <strong>{{ node.node_name }}</strong>
      <em v-if="gateText">{{ gateText }}</em>
    </div>
    <div v-if="children.length" class="preview-children">
      <MermaidTreePreviewNode
        v-for="child in children"
        :key="child.node_id"
        :node="child"
        :children-map="childrenMap"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  childrenMap: { type: Object, required: true }
})

const children = computed(() => props.childrenMap[props.node.node_id] || [])
const gateText = computed(() => {
  if (!props.node.gate_type || props.node.gate_type === 'NONE') return ''
  if (props.node.gate_type === 'K_OUT_OF_N') return `${props.node.k || 0}/${children.value.length}`
  return props.node.gate_type
})
</script>

<style scoped>
.preview-node {
  display: grid;
  gap: 6px;
}

.preview-card {
  display: inline-grid;
  grid-template-columns: auto minmax(160px, max-content) auto;
  gap: 6px;
  align-items: center;
  justify-self: start;
  padding: 6px 8px;
  border: 1px solid #8a8f93;
  background: #f7f7f7;
}

.preview-card span,
.preview-card em {
  padding: 2px 5px;
  border: 1px solid #8a8f93;
  background: #eef2f4;
  color: #315b7c;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
}

.preview-card strong {
  font-size: 12px;
}

.preview-card em {
  font-style: normal;
}

.preview-children {
  display: grid;
  gap: 6px;
  margin-left: 24px;
  padding-left: 12px;
  border-left: 1px solid #9ca3a8;
}
</style>
