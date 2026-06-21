<template>
  <div class="rule-editor">
    <div class="editor-title">
      <span>证据规则</span>
      <button type="button" @click="addRule">新增规则</button>
    </div>
    <div class="rule-table">
      <div class="rule-head">
        <span>ID</span><span>测点</span><span>变量</span><span>窗口</span><span>统计</span><span>判据</span><span>阈值</span><span>单位</span><span>趋势</span><span>说明</span><span></span>
      </div>
      <div v-for="(rule, index) in modelValue" :key="rule.rule_id || index" class="rule-row">
        <input v-model="rule.rule_id" @input="emitChange" />
        <input v-model="rule.tag" @input="emitChange" />
        <input v-model="rule.variable_name" @input="emitChange" />
        <input v-model="rule.window" @input="emitChange" />
        <select v-model="rule.statistic" @change="emitChange">
          <option>last</option>
          <option>mean</option>
          <option>max</option>
          <option>min</option>
          <option>slope</option>
          <option>delta</option>
        </select>
        <select v-model="rule.operator" @change="emitChange">
          <option>&gt;</option>
          <option>&lt;</option>
          <option>&gt;=</option>
          <option>&lt;=</option>
          <option>=</option>
          <option>between</option>
          <option>trend_up</option>
          <option>trend_down</option>
        </select>
        <input v-model="rule.threshold" @input="emitChange" />
        <input v-model="rule.unit" @input="emitChange" />
        <select v-model="rule.trend" @change="emitChange">
          <option value="">无</option>
          <option value="up">up</option>
          <option value="down">down</option>
          <option value="high">high</option>
          <option value="low">low</option>
        </select>
        <input v-model="rule.description" @input="emitChange" />
        <button type="button" class="danger" @click="removeRule(index)">删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const emitChange = () => emit('update:modelValue', [...props.modelValue])

const addRule = () => {
  emit('update:modelValue', [
    ...props.modelValue,
    {
      rule_id: `R_${Date.now().toString(36).toUpperCase()}`,
      tag: '',
      variable_name: '',
      window: '30min',
      statistic: 'mean',
      operator: '>',
      threshold: '',
      unit: '',
      trend: '',
      description: ''
    }
  ])
}

const removeRule = (index) => {
  emit('update:modelValue', props.modelValue.filter((_, idx) => idx !== index))
}
</script>

<style scoped>
.rule-editor {
  border: 1px solid #8a8f93;
  background: #ececec;
}

.editor-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 30px;
  padding: 0 8px;
  border-bottom: 1px solid #9ba0a4;
  background: #d7dadd;
  font-weight: 700;
}

.rule-table {
  overflow-x: auto;
}

.rule-head,
.rule-row {
  display: grid;
  grid-template-columns: 86px 92px 108px 76px 82px 92px 78px 60px 78px minmax(180px, 1fr) 58px;
  min-width: 990px;
  border-bottom: 1px solid #c0c3c5;
}

.rule-head {
  background: #e1e4e6;
  color: #43484c;
  font-size: 12px;
  font-weight: 700;
}

.rule-head span,
.rule-row > * {
  min-width: 0;
  padding: 5px;
  border-right: 1px solid #c0c3c5;
}

input,
select {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #9ca3a8;
  background: #fff;
  color: #1f2529;
  font-size: 12px;
}

button {
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  cursor: pointer;
}

button.danger {
  border-color: #954a4a;
  color: #8a2222;
}
</style>
