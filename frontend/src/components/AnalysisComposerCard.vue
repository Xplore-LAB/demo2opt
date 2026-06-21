<template>
  <footer class="composer-card">
    <div class="composer-primary-row">
      <el-dropdown trigger="click" @command="handleSourceCommand">
        <button class="ghost-btn add-data-btn" data-testid="add-data-trigger" type="button" :disabled="isPickingFile || isRunning">
          添加数据
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="upload" data-testid="source-upload">上传本地文件</el-dropdown-item>
            <el-dropdown-item command="sample" data-testid="source-sample">从示例库选择</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <div class="source-status" :class="sourceStatusTone">
        <span class="status-label">{{ sourceStatusText }}</span>
      </div>

      <div class="run-actions">
        <button
          class="start-btn"
          data-testid="start-analysis"
          type="button"
          :disabled="!canStart || isRunning"
          @click="$emit('start', { autoConfirm: false })"
        >
          开始分析
        </button>
        <button
          class="quick-run-btn"
          data-testid="start-analysis-auto"
          type="button"
          :disabled="!canStart || isRunning"
          title="跳过中间确认节点，直接生成结果"
          @click="$emit('start', { autoConfirm: true })"
        >
          快速直出
        </button>
      </div>
    </div>

    <div class="note-row">
      <span class="note-label">任务备注</span>
      <el-input
        :model-value="taskNote"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 4 }"
        resize="none"
        placeholder="补充本次分析重点，例如主换冷损、负荷波动，或希望 AI 优先解释的现象。"
        @update:model-value="(value) => $emit('update-task-note', value)"
      />
    </div>

    <div v-if="hasRunningSessionLock" class="message-line warning-text">当前已有其他会话正在执行任务，请等待完成后再启动新任务。</div>
    <div v-if="configErrorMessage" class="message-line warning-text">{{ configErrorMessage }}</div>
    <div v-if="lastError" class="message-line error-text">{{ lastError }}</div>
  </footer>

  <el-dialog
    v-model="sampleDialogVisible"
    width="560px"
    title="选择示例文件"
    append-to-body
    data-testid="sample-file-dialog"
  >
    <div class="sample-dialog-tip">从示例库选择 Excel 文件，确认后回填到当前会话。</div>
    <div class="sample-dialog-main">
      <el-select
        v-model="pendingSamplePath"
        data-testid="sample-select"
        placeholder="请选择示例文件"
        :loading="samplesLoading"
        :disabled="isRunning"
      >
        <el-option
          v-for="item in sampleFiles"
          :key="item.path"
          :label="item.name"
          :value="item.path"
        />
      </el-select>
      <button class="inline-btn" type="button" :disabled="samplesLoading || isRunning" @click="$emit('refresh-samples')">刷新</button>
    </div>
    <div v-if="samplesError" class="message-line error-text">{{ samplesError }}</div>
    <div v-else-if="!samplesLoading && !sampleFiles.length" class="message-line warning-text">示例库暂无可用 Excel 文件。</div>
    <template #footer>
      <el-button @click="sampleDialogVisible = false">取消</el-button>
      <el-button
        data-testid="confirm-sample-select"
        type="primary"
        :disabled="!canConfirmSample || isRunning"
        @click="confirmSampleSelection"
      >
        确认选择
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  isPickingFile: { type: Boolean, default: false },
  isRunning: { type: Boolean, default: false },
  canStart: { type: Boolean, default: false },
  dataSource: { type: String, default: 'none' },
  fileName: { type: String, default: '' },
  selectedSamplePath: { type: String, default: '' },
  selectedSampleName: { type: String, default: '' },
  sampleFiles: { type: Array, default: () => [] },
  samplesLoading: { type: Boolean, default: false },
  samplesError: { type: String, default: '' },
  taskNote: { type: String, default: '' },
  hasRunningSessionLock: { type: Boolean, default: false },
  configErrorMessage: { type: String, default: '' },
  lastError: { type: String, default: '' },
})

const emit = defineEmits(['choose-source', 'select-sample', 'refresh-samples', 'update-task-note', 'start'])
const sampleDialogVisible = ref(false)
const pendingSamplePath = ref('')

const sourceStatusText = computed(() => {
  if (props.dataSource === 'upload') {
    return props.fileName ? `已选择：上传文件 / ${props.fileName}` : '已选择：上传文件 / 尚未添加文件'
  }
  if (props.dataSource === 'sample') {
    return props.selectedSampleName
      ? `已选择：示例文件 / ${props.selectedSampleName}`
      : '已选择：示例文件 / 尚未选择具体示例'
  }
  return '请先选择数据来源（上传文件或示例文件）'
})

const sourceStatusTone = computed(() => {
  if (props.dataSource === 'upload' || props.dataSource === 'sample') return 'active'
  return 'idle'
})

const canConfirmSample = computed(() => Boolean(pendingSamplePath.value))

watch(
  () => props.selectedSamplePath,
  (value) => {
    if (!sampleDialogVisible.value) pendingSamplePath.value = value || ''
  },
)

watch(sampleDialogVisible, (open) => {
  if (open) pendingSamplePath.value = props.selectedSamplePath || ''
})

function handleSourceCommand(command) {
  emit('choose-source', command)
  if (command === 'sample') sampleDialogVisible.value = true
  else sampleDialogVisible.value = false
}

function confirmSampleSelection() {
  if (!pendingSamplePath.value) return
  emit('select-sample', pendingSamplePath.value)
  sampleDialogVisible.value = false
}
</script>

<style scoped>
.composer-card{padding:9px 12px;border-top:1px solid var(--ui-border);background:linear-gradient(180deg,rgba(249,250,251,.96),#fff);display:grid;gap:8px}
.composer-primary-row{display:grid;grid-template-columns:112px 1fr minmax(216px,236px);gap:8px;align-items:center}
.ghost-btn,.start-btn,.quick-run-btn,.inline-btn{border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);cursor:pointer}
.ghost-btn,.start-btn,.quick-run-btn{min-height:34px;padding:0 12px;font-size:13px;font-weight:700}
.ghost-btn{color:var(--ui-primary)}
.start-btn{background:var(--ui-primary);border-color:var(--ui-primary);color:#fff}
.quick-run-btn{background:#fff7ed;border-color:#fdba74;color:#c2410c}
.run-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.start-btn:disabled,.quick-run-btn:disabled,.ghost-btn:disabled,.inline-btn:disabled{opacity:.5;cursor:not-allowed}
.source-status{min-height:34px;display:flex;align-items:center;padding:0 12px;border:1px dashed #cbd5e1;border-radius:8px;background:rgba(239,246,255,.55)}
.source-status.idle{background:#f8fafc;border-style:dashed}
.status-label{font-size:13px;color:var(--ui-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.source-status.active .status-label{color:#334155}
.inline-btn{min-height:36px;padding:0 12px;color:var(--ui-primary);font-size:12px;font-weight:700}
.note-row{display:grid;grid-template-columns:64px 1fr;gap:8px;align-items:flex-start;padding:6px 8px;border:1px solid var(--ui-border);border-radius:8px;background:rgba(255,255,255,.82)}
.note-label{padding-top:7px;color:var(--ui-muted);font-size:12px;font-weight:700}
.message-line{font-size:12px;line-height:1.5}
.warning-text{color:var(--ui-warning)}
.error-text{color:var(--ui-danger)}
.sample-dialog-tip{margin-bottom:8px;color:var(--ui-muted);font-size:13px;line-height:1.5}
.sample-dialog-main{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}
@media (max-width:980px){.composer-primary-row{grid-template-columns:1fr}.run-actions{grid-template-columns:1fr 1fr}.note-row{grid-template-columns:1fr}.note-label{padding-top:0}}
@media (max-width:760px){.sample-dialog-main{grid-template-columns:1fr}}
@media (max-width:640px){.composer-card{padding:7px 9px;gap:6px}.composer-primary-row{gap:6px}.ghost-btn,.start-btn,.quick-run-btn{min-height:30px;font-size:12px}.source-status{min-height:30px}.status-label{font-size:12px}.note-row{display:none}.run-actions{grid-template-columns:1fr 1fr;gap:6px}}
</style>
