<template>
  <li>
    <div class="node-line" :class="{ selected, disabled: !node.enabled }" @click="$emit('select', node.node_id)">
      <button v-if="children.length" type="button" class="toggle" @click.stop="$emit('toggle', node.node_id)">
        {{ expanded ? '-' : '+' }}
      </button>
      <span v-else class="toggle ghost"></span>
      <span class="type-tag" :class="node.node_type">{{ node.node_type }}</span>
      <strong>{{ node.node_name }}</strong>
      <span v-if="node.gate_type && node.gate_type !== 'NONE'" class="gate">{{ gateLabel }}</span>
      <span v-if="node.related_tags?.length" class="tags">{{ node.related_tags.join(', ') }}</span>
      <div class="node-actions">
        <button type="button" @click.stop="$emit('add-child', node.node_id, 'cause')">原因</button>
        <button type="button" @click.stop="$emit('add-child', node.node_id, 'evidence')">证据</button>
        <button type="button" @click.stop="$emit('add-child', node.node_id, 'gate')">门</button>
        <button type="button" @click.stop="$emit('copy', node.node_id)">复制</button>
        <button type="button" @click.stop="$emit('move', node.node_id, -1)">上移</button>
        <button type="button" @click.stop="$emit('move', node.node_id, 1)">下移</button>
        <button type="button" class="danger" @click.stop="$emit('remove', node.node_id)">删除</button>
      </div>
    </div>
    <ul v-if="children.length && expanded">
      <FaultTreeNodeItem
        v-for="child in children"
        :key="child.node_id"
        :node="child"
        :children-map="childrenMap"
        :selected-id="selectedId"
        :expanded-ids="expandedIds"
        @select="$emit('select', $event)"
        @toggle="$emit('toggle', $event)"
        @add-child="(...args) => $emit('add-child', ...args)"
        @copy="$emit('copy', $event)"
        @move="(...args) => $emit('move', ...args)"
        @remove="$emit('remove', $event)"
      />
    </ul>
  </li>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  childrenMap: { type: Object, required: true },
  selectedId: { type: String, default: '' },
  expandedIds: { required: true }
})
defineEmits(['select', 'toggle', 'add-child', 'copy', 'move', 'remove'])

const children = computed(() => props.childrenMap[props.node.node_id] || [])
const selected = computed(() => props.selectedId === props.node.node_id)
const expanded = computed(() => props.expandedIds.has(props.node.node_id))
const gateLabel = computed(() => props.node.gate_type === 'K_OUT_OF_N' ? `${props.node.k || 0}/${children.value.length}` : props.node.gate_type)
</script>

<style scoped>
li {
  list-style: none;
}

ul {
  margin: 0 0 0 23px;
  padding: 0;
  border-left: 1px solid #aab0b5;
}

.node-line {
  display: grid;
  grid-template-columns: 24px 108px minmax(170px, 1fr) auto minmax(90px, 210px) auto;
  gap: 6px;
  align-items: center;
  min-height: 34px;
  margin: 3px 0;
  padding: 3px 6px;
  border: 1px solid #9aa0a5;
  background: #eeeeee;
  color: #1d2429;
  cursor: pointer;
}

.node-line.selected {
  border-color: #2e75b6;
  background: #dbeaf6;
}

.node-line.disabled {
  opacity: .58;
}

.toggle,
.ghost {
  width: 22px;
  height: 22px;
  border: 1px solid #7c8389;
  background: #f4f4f4;
  text-align: center;
}

.ghost {
  display: block;
  border-color: transparent;
  background: transparent;
}

.type-tag,
.gate {
  padding: 2px 6px;
  border: 1px solid #78818a;
  background: #f7f7f7;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.type-tag.top_event {
  border-color: #9a5c2f;
  color: #8f3d16;
}

.type-tag.gate {
  border-color: #2f618e;
  color: #245984;
}

.type-tag.cause {
  border-color: #876f25;
  color: #6f5614;
}

.type-tag.evidence {
  border-color: #357548;
  color: #23663a;
}

.gate {
  border-color: #2e75b6;
  background: #edf5fb;
  color: #1e5e91;
}

.tags {
  overflow: hidden;
  color: #596168;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-actions {
  display: flex;
  gap: 3px;
  justify-content: flex-end;
}

button {
  border: 1px solid #747b82;
  background: #e7eaec;
  color: #1f2529;
  cursor: pointer;
}

.node-actions button {
  font-size: 11px;
}

.danger {
  border-color: #954a4a;
  color: #8a2222;
}
</style>
