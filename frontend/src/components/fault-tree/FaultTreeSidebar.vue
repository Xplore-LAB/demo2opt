<template>
  <aside class="tree-sidebar">
    <div class="panel-title">
      <span>故障树目录</span>
      <button type="button" @click="$emit('create')">新增</button>
    </div>
    <div class="tree-list">
      <button
        v-for="tree in trees"
        :key="tree.tree_id"
        type="button"
        class="tree-card"
        :class="{ active: tree.tree_id === activeId }"
        @click="$emit('select', tree.tree_id)"
      >
        <strong>{{ tree.tree_name }}</strong>
        <span>{{ tree.version }} · {{ tree.updated_at }}</span>
        <em :class="tree.status">{{ statusText(tree.status) }}</em>
      </button>
    </div>
    <div class="side-actions">
      <button type="button" @click="$emit('duplicate')">复制新版本</button>
      <button type="button" @click="$emit('delete')" class="danger">删除故障树</button>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  trees: { type: Array, default: () => [] },
  activeId: { type: String, default: '' }
})
defineEmits(['select', 'create', 'duplicate', 'delete'])

const statusText = (status) => ({ draft: '草稿', published: '已发布', disabled: '停用' }[status] || status)
</script>

<style scoped>
.tree-sidebar {
  min-width: 260px;
  border-right: 1px solid #777;
  background: #d8d8d8;
  overflow: auto;
}

.panel-title,
.side-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid #777;
  background: #c7cbce;
  font-weight: 700;
}

.tree-list {
  display: grid;
  gap: 6px;
  padding: 8px;
}

.tree-card {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 8px;
  border: 1px solid #8a8f93;
  background: #e7e7e7;
  color: #1f2529;
  text-align: left;
  cursor: pointer;
}

.tree-card.active {
  border-color: #2e75b6;
  background: #dce9f4;
}

.tree-card strong {
  font-size: 14px;
}

.tree-card span {
  color: #596168;
  font-size: 12px;
}

.tree-card em {
  justify-self: start;
  padding: 2px 6px;
  border: 1px solid #7d858c;
  background: #f2f2f2;
  font-size: 12px;
  font-style: normal;
}

.tree-card em.published {
  border-color: #2d7a42;
  color: #1e6d34;
}

.tree-card em.disabled {
  border-color: #8a4b4b;
  color: #8a2222;
}

button {
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  cursor: pointer;
}

.side-actions {
  position: sticky;
  bottom: 0;
}

.danger {
  border-color: #954a4a;
  color: #8a2222;
}
</style>
