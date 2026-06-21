<template>
  <div class="json-panel">
    <button type="button" @click="$emit('save-local')">保存到本地</button>
    <button type="button" @click="$emit('load-local')">从本地加载</button>
    <button type="button" @click="$emit('export-json')">导出 JSON</button>
    <label class="import-btn">
      导入 JSON
      <input type="file" accept="application/json,.json" @change="readFile" />
    </label>
  </div>
</template>

<script setup>
const emit = defineEmits(['save-local', 'load-local', 'export-json', 'import-json'])

const readFile = (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => emit('import-json', String(reader.result || ''))
  reader.readAsText(file)
  event.target.value = ''
}
</script>

<style scoped>
.json-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 7px;
  border-top: 1px solid #777;
  background: #c7cbce;
}

button,
.import-btn {
  height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border: 1px solid #586069;
  background: #e8ecef;
  color: #1f2529;
  font-size: 12px;
  cursor: pointer;
}

input {
  display: none;
}
</style>
