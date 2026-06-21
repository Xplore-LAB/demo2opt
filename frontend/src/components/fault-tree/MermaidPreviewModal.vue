<template>
  <div v-if="visible" class="modal-mask">
    <section class="modal">
      <header>
        <strong>Mermaid 预览</strong>
        <button type="button" @click="$emit('close')">关闭</button>
      </header>
      <div class="modal-body">
        <div class="source">
          <div class="sub-title">
            <span>源码</span>
            <button type="button" @click="copy">复制 Mermaid 源码</button>
          </div>
          <textarea readonly :value="source"></textarea>
        </div>
        <div class="preview">
          <div class="sub-title">图形预览</div>
          <div class="preview-tree">
            <div v-if="tree" class="visual-tree">
              <MermaidTreePreviewNode v-for="root in roots" :key="root.node_id" :node="root" :children-map="childrenMap" />
            </div>
            <pre v-else>{{ source }}</pre>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MermaidTreePreviewNode from './MermaidTreePreviewNode.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  source: { type: String, default: '' },
  tree: { type: Object, default: null }
})
defineEmits(['close'])

const copy = async () => {
  await navigator.clipboard?.writeText(props.source)
}

const childrenMap = computed(() => {
  const map = {}
  ;(props.tree?.nodes || []).forEach((node) => {
    const key = node.parent_id || '__root__'
    if (!map[key]) map[key] = []
    map[key].push(node)
  })
  return map
})

const roots = computed(() => childrenMap.value.__root__ || [])

</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  background: rgba(20, 24, 27, .38);
}

.modal {
  width: min(1080px, calc(100vw - 28px));
  height: min(720px, calc(100vh - 28px));
  display: grid;
  grid-template-rows: 36px minmax(0, 1fr);
  border: 1px solid #50575d;
  background: #dedede;
  box-shadow: 0 16px 40px rgba(0, 0, 0, .28);
}

header,
.sub-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  border-bottom: 1px solid #8a8f93;
  background: #c7cbce;
}

.modal-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 0;
}

.source,
.preview {
  display: grid;
  grid-template-rows: 32px minmax(0, 1fr);
  min-width: 0;
}

.source {
  border-right: 1px solid #8a8f93;
}

textarea,
pre {
  margin: 0;
  padding: 10px;
  overflow: auto;
  border: 0;
  background: #f8f8f8;
  color: #1b2227;
  font-family: Consolas, monospace;
  font-size: 12px;
}

textarea {
  resize: none;
}

.preview-tree {
  overflow: auto;
  padding: 10px;
}

.visual-tree {
  display: grid;
  gap: 8px;
  min-width: 520px;
}

button {
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  cursor: pointer;
}

@media (max-width: 760px) {
  .modal-body {
    grid-template-columns: 1fr;
  }
}
</style>
