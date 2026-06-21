<template>
  <main class="tree-viewer">
    <div class="toolbar">
      <div class="search">
        <input v-model="filters.keyword" placeholder="按节点名称或测点搜索" />
        <select v-model="filters.node_type">
          <option value="">全部类型</option>
          <option value="top_event">top_event</option>
          <option value="gate">gate</option>
          <option value="intermediate_event">intermediate_event</option>
          <option value="cause">cause</option>
          <option value="evidence">evidence</option>
          <option value="action">action</option>
          <option value="risk">risk</option>
        </select>
        <select v-model="filters.branch">
          <option value="">全部分支</option>
          <option v-for="branch in branches" :key="branch" :value="branch">{{ branch }}</option>
        </select>
        <select v-model="filters.enabled">
          <option value="">全部状态</option>
          <option value="true">启用</option>
          <option value="false">停用</option>
        </select>
      </div>
      <div class="actions">
        <button type="button" @click="$emit('expand-all')">展开全部</button>
        <button type="button" @click="$emit('collapse-all')">收起全部</button>
        <button type="button" @click="$emit('mermaid')">生成 Mermaid 图</button>
      </div>
    </div>
    <div v-if="tree" class="tree-meta">
      <div><span>名称</span><input :value="tree.tree_name" @input="updateTree('tree_name', $event.target.value)" /></div>
      <div><span>版本</span><input :value="tree.version" @input="updateTree('version', $event.target.value)" /></div>
      <div><span>领域</span><input :value="tree.domain" @input="updateTree('domain', $event.target.value)" /></div>
      <div><span>状态</span>
        <select :value="tree.status" @change="updateTree('status', $event.target.value)">
          <option value="draft">草稿</option>
          <option value="published">已发布</option>
          <option value="disabled">停用</option>
        </select>
      </div>
    </div>
    <div class="tree-canvas">
      <ul v-if="roots.length">
        <FaultTreeNodeItem
          v-for="root in roots"
          :key="root.node_id"
          :node="root"
          :children-map="childrenMap"
          :selected-id="selectedId"
          :expanded-ids="expandedIds"
          @select="$emit('select-node', $event)"
          @toggle="$emit('toggle-node', $event)"
          @add-child="(...args) => $emit('add-child', ...args)"
          @copy="$emit('copy-node', $event)"
          @move="(...args) => $emit('move-node', ...args)"
          @remove="$emit('delete-node', $event)"
        />
      </ul>
      <div v-else class="empty">暂无节点。</div>
    </div>
  </main>
</template>

<script setup>
import { computed, reactive } from 'vue'
import FaultTreeNodeItem from './FaultTreeNodeItem.vue'

const props = defineProps({
  tree: { type: Object, default: null },
  selectedId: { type: String, default: '' },
  expandedIds: { required: true }
})
const emit = defineEmits(['select-node', 'toggle-node', 'add-child', 'copy-node', 'move-node', 'delete-node', 'expand-all', 'collapse-all', 'mermaid', 'update-tree'])

const filters = reactive({ keyword: '', node_type: '', branch: '', enabled: '' })

const branches = computed(() => [...new Set((props.tree?.nodes || []).map((node) => node.branch).filter(Boolean))])

const filteredIds = computed(() => {
  const nodes = props.tree?.nodes || []
  return new Set(nodes.filter((node) => {
    const keyword = filters.keyword.trim().toLowerCase()
    const keywordOk = !keyword || node.node_name.toLowerCase().includes(keyword) || (node.related_tags || []).join(',').toLowerCase().includes(keyword)
    const typeOk = !filters.node_type || node.node_type === filters.node_type
    const branchOk = !filters.branch || node.branch === filters.branch
    const enabledOk = !filters.enabled || String(Boolean(node.enabled)) === filters.enabled
    return keywordOk && typeOk && branchOk && enabledOk
  }).map((node) => node.node_id))
})

const visibleNodes = computed(() => {
  const nodes = props.tree?.nodes || []
  if (!filters.keyword && !filters.node_type && !filters.branch && !filters.enabled) return nodes
  const keep = new Set(filteredIds.value)
  let changed = true
  while (changed) {
    changed = false
    nodes.forEach((node) => {
      if (keep.has(node.node_id) && node.parent_id && !keep.has(node.parent_id)) {
        keep.add(node.parent_id)
        changed = true
      }
    })
  }
  return nodes.filter((node) => keep.has(node.node_id))
})

const childrenMap = computed(() => {
  const map = {}
  visibleNodes.value.forEach((node) => {
    const key = node.parent_id || '__root__'
    if (!map[key]) map[key] = []
    map[key].push(node)
  })
  return map
})

const roots = computed(() => childrenMap.value.__root__ || [])

const updateTree = (field, value) => emit('update-tree', { ...props.tree, [field]: value })
</script>

<style scoped>
.tree-viewer {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-width: 0;
  background: #d2d2d2;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px;
  border-bottom: 1px solid #777;
  background: #c7cbce;
}

.search,
.actions,
.tree-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

input,
select,
button {
  height: 28px;
  border: 1px solid #747b82;
  background: #f2f2f2;
  color: #1f2529;
  font-size: 12px;
}

button {
  cursor: pointer;
}

.search input {
  width: 220px;
}

.tree-meta {
  padding: 7px;
  border-bottom: 1px solid #8f9498;
  background: #dddddd;
}

.tree-meta div {
  display: flex;
  align-items: center;
  gap: 5px;
}

.tree-meta span {
  color: #4b5359;
  font-size: 12px;
  font-weight: 700;
}

.tree-canvas {
  overflow: auto;
  padding: 8px;
}

ul {
  margin: 0;
  padding: 0;
}

.empty {
  padding: 14px;
  color: #555;
}
</style>
