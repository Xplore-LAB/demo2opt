<template>
  <aside class="node-editor">
    <div class="panel-title">节点详情编辑</div>
    <div v-if="!node" class="empty">请选择中间故障树节点。</div>
    <form v-else class="editor-form" @submit.prevent>
      <label>节点ID<input v-model="draft.node_id" disabled /></label>
      <label>节点名称<input v-model="draft.node_name" @input="commit" /></label>
      <label>节点类型
        <select v-model="draft.node_type" @change="commit">
          <option value="top_event">top_event</option>
          <option value="gate">gate</option>
          <option value="intermediate_event">intermediate_event</option>
          <option value="cause">cause</option>
          <option value="evidence">evidence</option>
          <option value="action">action</option>
          <option value="risk">risk</option>
        </select>
      </label>
      <label>所属分支<input v-model="draft.branch" @input="commit" /></label>
      <label>父节点<input v-model="draft.parent_id" disabled /></label>
      <label>逻辑门类型
        <select v-model="draft.gate_type" @change="commit">
          <option value="NONE">NONE</option>
          <option value="AND">AND</option>
          <option value="OR">OR</option>
          <option value="K_OUT_OF_N">K_OUT_OF_N</option>
        </select>
      </label>
      <label v-if="draft.gate_type === 'K_OUT_OF_N'">K值
        <input type="number" min="1" v-model.number="draft.k" @input="commit" />
        <small>当前为 {{ draft.k || 0 }}/{{ childCount }} 表决门</small>
      </label>
      <label>相关测点<input :value="tagsText" @input="updateTags($event.target.value)" placeholder="FIQC102, AI705" /></label>
      <label class="wide">机理说明<textarea v-model="draft.mechanism" @input="commit"></textarea></label>
      <label class="wide">操作建议<textarea v-model="draft.recommended_action" @input="commit"></textarea></label>
      <label class="wide">风险提示<textarea v-model="draft.risk_note" @input="commit"></textarea></label>
      <label class="wide">数据缺失提示<textarea v-model="draft.missing_data_note" @input="commit"></textarea></label>
      <label>来源<input v-model="draft.source" @input="commit" /></label>
      <label class="wide">备注<textarea v-model="draft.remark" @input="commit"></textarea></label>
      <label class="enabled"><input type="checkbox" v-model="draft.enabled" @change="commit" /> 启用状态</label>
      <RuleEditorTable v-if="draft.node_type === 'evidence'" v-model="draft.evidence_rules" @update:model-value="commit" />
    </form>
  </aside>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import RuleEditorTable from './RuleEditorTable.vue'

const props = defineProps({
  node: { type: Object, default: null },
  childCount: { type: Number, default: 0 }
})
const emit = defineEmits(['update'])

const draft = reactive({})

watch(() => props.node, (value) => {
  Object.keys(draft).forEach((key) => delete draft[key])
  if (value) Object.assign(draft, JSON.parse(JSON.stringify(value)))
}, { immediate: true })

const tagsText = computed(() => (draft.related_tags || []).join(', '))

const commit = () => {
  emit('update', JSON.parse(JSON.stringify(draft)))
}

const updateTags = (value) => {
  draft.related_tags = value.split(',').map((item) => item.trim()).filter(Boolean)
  commit()
}
</script>

<style scoped>
.node-editor {
  min-width: 360px;
  border-left: 1px solid #777;
  background: #dedede;
  overflow: auto;
}

.panel-title {
  height: 34px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border-bottom: 1px solid #777;
  background: #c7cbce;
  font-weight: 700;
}

.empty {
  padding: 16px;
  color: #555;
}

.editor-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px;
}

label {
  display: grid;
  gap: 4px;
  color: #3c4246;
  font-size: 12px;
  font-weight: 700;
}

.wide,
.enabled,
.rule-editor {
  grid-column: 1 / -1;
}

input,
select,
textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #8a8f93;
  background: #f7f7f7;
  color: #111;
  font: inherit;
  font-weight: 400;
}

textarea {
  min-height: 64px;
  resize: vertical;
}

small {
  color: #2e658f;
  font-weight: 400;
}

.enabled {
  display: flex;
  align-items: center;
  gap: 6px;
}

.enabled input {
  width: auto;
}
</style>
