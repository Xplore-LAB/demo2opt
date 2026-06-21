<template>
  <div class="page-shell">
    <aside class="sidebar">
      <div class="eyebrow">Industrial AI Console</div>
      <div class="brand-title">空分装置智能运行优化</div>
      <p class="brand-copy">面向运行诊断、异常确认、原因分析和操作建议生成的演示工作台。</p>

      <div class="status-card">
        <div class="status-row"><span class="status-dot" :class="wsStatus"></span>{{ wsStatusText }}</div>
        <div class="mini-label">当前阶段</div>
        <div class="status-main">{{ liveStageText }}</div>
        <div class="mini-label">任务状态</div>
        <div class="status-sub">{{ systemStatusText }}</div>
      </div>

      <div class="status-card">
        <div class="mini-label">监控说明</div>
        <p class="sidebar-note">实时监控会在语义分析完成后立即刷新，并在决策生成后再次更新，不必等待最终报告。</p>
      </div>
    </aside>

    <main class="main-grid">
      <section class="stream-panel">
        <header class="stream-header">
          <div>
            <h1>分析对话流</h1>
            <p>上传数据后，这里会持续显示日志、阶段变化和人工确认。</p>
          </div>
          <div class="header-badge">{{ currentProcessText }}</div>
        </header>

        <div ref="streamScroll" class="stream-body">
          <article class="message ai">
            <div class="avatar">AI</div>
            <div class="bubble intro">
              <div class="bubble-title">开始前</div>
              <div class="markdown">连接建立后可直接发起分析。未选择文件时，后端会尝试读取默认示例数据。</div>
            </div>
          </article>

          <article v-for="(item, idx) in streamItems" :key="`${item.type}-${idx}`" class="message" :class="item.role">
            <div class="avatar">{{ item.role === 'user' ? '你' : 'AI' }}</div>
            <div class="bubble" :class="[item.level || 'info', item.type]">
              <div v-if="item.title" class="bubble-title">{{ item.title }}</div>
              <template v-if="item.type === 'interaction'">
                <div class="markdown">{{ item.desc }}</div>
                <div v-if="!item.answered" class="bubble-actions">
                  <el-button size="small" type="primary" @click="handleInteraction(item.id, 'yes')">继续分析</el-button>
                  <el-button size="small" @click="handleInteraction(item.id, 'no')">停止任务</el-button>
                </div>
                <div v-else class="bubble-meta">已回复：{{ item.answerText }}</div>
              </template>
              <template v-else-if="item.type === 'phase'">
                <div class="bubble-meta">{{ item.detail }}</div>
              </template>
              <template v-else>
                <div class="markdown" v-html="renderMarkdown(item.text)"></div>
              </template>
              <div class="bubble-time">{{ item.time }}</div>
            </div>
          </article>
        </div>

        <footer class="composer">
          <input ref="fileInput" type="file" class="hidden" accept=".xlsx,.xls,.csv" @change="handleFileSelect" />
          <div class="composer-row">
            <button class="ghost-btn" @click="openFilePicker">选择数据</button>
            <div class="file-name">{{ fileName || '未选择文件时，将尝试使用后端默认示例数据。' }}</div>
            <button class="start-btn" :disabled="!canStart || isRunning" @click="startAnalysis">开始分析</button>
          </div>
          <div v-if="configErrorMessage" class="message-line warning-text">{{ configErrorMessage }}</div>
          <div v-if="lastError" class="message-line error-text">{{ lastError }}</div>
        </footer>
      </section>

      <section class="workspace-panel">
        <div class="tabs">
          <button :class="{ active: activeTab === 'config' }" @click="activeTab = 'config'">系统配置</button>
          <button :class="{ active: activeTab === 'monitor' }" @click="activeTab = 'monitor'">实时监控</button>
          <button :class="{ active: activeTab === 'report' }" @click="activeTab = 'report'">分析报告</button>
        </div>

        <div v-if="activeTab === 'config'" class="panel">
          <h3>运行配置</h3>
          <div class="mode-row">
            <button class="mode-btn" :class="{ active: config.mode === 'dify' }" @click="config.mode = 'dify'">Dify 应用</button>
            <button class="mode-btn" :class="{ active: config.mode === 'direct' }" @click="config.mode = 'direct'">直连模型</button>
          </div>
          <template v-if="config.mode === 'dify'">
            <label>Dify 接口地址</label>
            <el-input v-model="config.difyUrl" placeholder="http://localhost/v1/chat-messages" />
            <label>Dify API Key</label>
            <el-input v-model="config.difyKey" type="password" show-password />
          </template>
          <template v-else>
            <label>模型预设</label>
            <div class="preset-row">
              <el-select v-model="selectedConfigId" placeholder="选择预设" @change="handleConfigChange">
                <el-option v-for="item in llmConfigs" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
              <el-button :icon="Refresh" circle @click="refreshConfigs" />
              <el-button :icon="Plus" circle @click="openSaveConfigDialog" />
            </div>
            <label>模型服务地址</label>
            <el-input v-model="config.llmUrl" />
            <label>模型 API Key</label>
            <el-input v-model="config.llmKey" type="password" show-password />
            <label>模型名称</label>
            <el-input v-model="config.llmModel" />
          </template>
          <div class="checkbox-row"><el-checkbox v-model="config.enableCoT" label="启用分步推理（CoT）" border /></div>
        </div>

        <div v-if="activeTab === 'monitor'" class="panel">
          <div class="panel-head">
            <div>
              <h3>实时监控</h3>
              <p>语义分析和决策生成阶段都会触发刷新，不再只依赖最终报告。</p>
            </div>
            <div class="time-chip">{{ monitorUpdatedAt || '尚未收到实时更新' }}</div>
          </div>
          <div class="kpi-grid">
            <div class="kpi-card"><span>监控点位数</span><strong>{{ currentData.length }}</strong></div>
            <div class="kpi-card" :class="{ danger: abnormalCount > 0 }"><span>异常指标数</span><strong>{{ abnormalCount }}</strong></div>
            <div class="kpi-card"><span>任务状态</span><strong class="compact">{{ systemStatusText }}</strong></div>
            <div class="kpi-card"><span>最新阶段</span><strong class="compact">{{ liveStageText }}</strong></div>
          </div>
          <div v-if="!currentData.length" class="empty-card">
            <div class="empty-title">等待实时数据</div>
            <div class="empty-text">当前尚未收到语义分析结果。任务进入分析阶段后，这里会即时刷新当前指标和异常摘要。</div>
          </div>
          <div v-else class="monitor-layout">
            <div class="card-section">
              <div class="section-title">最新指标快照</div>
              <div class="sensor-grid">
                <div v-for="item in currentData" :key="`${item.name}-${item.current_value}`" class="sensor-card" :class="getDataStateClass(item)">
                  <div class="sensor-name">{{ item.name }}</div>
                  <div class="sensor-state">{{ item.state_desc }}</div>
                  <div class="sensor-value">{{ formatNumber(item.current_value) }}</div>
                  <div class="sensor-meta">偏差：{{ formatNumber(item.diff) }}</div>
                </div>
              </div>
            </div>
            <div class="side-stack">
              <div class="card-section">
                <div class="section-title">实时异常摘要</div>
                <div v-if="!liveAbnormalIndicators.length" class="empty-text">当前没有需要重点跟踪的异常指标。</div>
                <div v-else class="tag-list">
                  <div v-for="ind in liveAbnormalIndicators" :key="ind.name" class="state-tag danger">{{ ind.name }} / {{ formatNumber(ind.value) }} / {{ ind.level }}</div>
                </div>
              </div>
              <div class="card-section">
                <div class="section-title">阶段说明</div>
                <div class="empty-text">当前监控阶段：{{ liveStageText }}。语义分析完成后会先推送一次快照，决策生成后会再次刷新。</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="activeTab === 'report'" class="panel">
          <div class="panel-head">
            <div>
              <h3>分析报告</h3>
              <p>报告内容统一使用简体中文，便于直接展示和汇报。</p>
            </div>
            <div class="report-actions"><el-button size="small" :icon="Download" @click="downloadReport">导出摘要</el-button></div>
          </div>
          <div v-if="!result.reasoning_result" class="empty-card">
            <div class="empty-title">报告尚未生成</div>
            <div class="empty-text">完成一次分析后，这里会展示原因分析、操作建议、风险提示和报告文件路径。</div>
          </div>
          <div v-else class="report-layout">
            <div class="summary-grid">
              <div class="summary-card"><span>异常指标</span><strong>{{ abnormalCount }}</strong></div>
              <div class="summary-card"><span>输出语言</span><strong class="compact">简体中文</strong></div>
              <div class="summary-card"><span>报告文件</span><strong class="compact">{{ reportFileName }}</strong></div>
            </div>
            <div class="report-grid">
              <div class="report-main">
                <section class="card-section"><div class="section-title">原因分析</div><div class="markdown prose-card" v-html="renderMarkdown(result.reasoning_result)"></div></section>
                <section class="card-section"><div class="section-title">决策建议</div><div class="markdown prose-card" v-html="renderMarkdown(result.decision_suggestion || result.suggestion || '')"></div></section>
                <section v-if="result.warning" class="card-section warning-section"><div class="section-title">风险提示</div><div class="markdown prose-card" v-html="renderMarkdown(result.warning)"></div></section>
              </div>
              <div class="report-side">
                <section class="card-section">
                  <div class="section-title">异常指标</div>
                  <div v-if="result.abnormal_indicators?.length" class="tag-list">
                    <div v-for="ind in result.abnormal_indicators" :key="ind.name" class="state-tag danger">{{ ind.name }} / {{ formatNumber(ind.value) }} / {{ ind.level }}</div>
                  </div>
                  <div v-else class="state-tag ok">当前未发现异常指标。</div>
                </section>
                <section v-if="result.report_md || result.report_pdf" class="card-section">
                  <div class="section-title">报告路径</div>
                  <div class="path-list">
                    <div v-if="result.report_md">{{ result.report_md }}</div>
                    <div v-if="result.report_pdf">{{ result.report_pdf }}</div>
                  </div>
                </section>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <el-dialog v-model="dialogVisible" title="保存模型配置" width="420px">
      <el-input v-model="configForm.name" placeholder="请输入配置名称" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSaveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { Download, Plus, Refresh } from '@element-plus/icons-vue'

const activeTab = ref('config')
const ws = ref(null)
const streamScroll = ref(null)
const fileInput = ref(null)
const wsStatus = ref('disconnected')
const isRunning = ref(false)
const lastError = ref('')
const liveStage = ref('idle')
const monitorUpdatedAt = ref('')
const liveAbnormalIndicators = ref([])
const fileName = ref('')
const fileData = ref(null)
const currentData = ref([])
const result = ref({})
const dialogVisible = ref(false)
const configForm = reactive({ name: '' })
const llmConfigs = ref([])
const selectedConfigId = ref('')
const streamItems = ref([])
const apiBaseUrl = 'http://localhost:5000/api'

const config = reactive({
  mode: 'dify',
  difyUrl: 'http://localhost/v1/chat-messages',
  difyKey: '',
  llmUrl: 'https://api.openai.com/v1',
  llmKey: '',
  llmModel: 'gpt-4o-mini',
  enableCoT: true,
})

const phases = reactive({
  init: { status: 'pending' },
  analysis: { status: 'pending' },
  report: { status: 'pending' },
})

const wsStatusText = computed(() => wsStatus.value === 'connected' ? '已连接' : wsStatus.value === 'connecting' ? '连接中' : '未连接')
const configErrorMessage = computed(() => {
  if (config.mode === 'dify') {
    if (!config.difyUrl.trim()) return 'Dify 模式缺少接口地址。'
    if (!config.difyKey.trim()) return 'Dify 模式缺少 API Key。'
    return ''
  }
  if (!config.llmUrl.trim()) return '直连模型模式缺少服务地址。'
  if (!config.llmKey.trim()) return '直连模型模式缺少 API Key。'
  if (!config.llmModel.trim()) return '直连模型模式缺少模型名称。'
  return ''
})
const canStart = computed(() => wsStatus.value === 'connected' && !configErrorMessage.value)
const abnormalCount = computed(() => result.value.abnormal_indicators?.length || liveAbnormalIndicators.value.length || 0)
const systemStatusText = computed(() => isRunning.value ? '运行中' : lastError.value ? '失败' : result.value.reasoning_result ? '已完成' : '空闲')
const currentProcessText = computed(() => phases.report.status === 'running' ? '正在生成报告' : phases.analysis.status === 'running' ? '正在执行推理' : phases.init.status === 'running' ? '正在准备数据' : '等待任务')
const liveStageText = computed(() => ({ idle: '等待任务', submitted: '任务已提交', semantic_ready: '语义分析完成，监控已刷新', decision_ready: '决策建议已生成，监控已刷新', result_ready: '最终结果已返回' }[liveStage.value] || liveStage.value))
const reportFileName = computed(() => (result.value.report_md || result.value.report_pdf || '').split(/[\\/]/).pop() || '尚未生成')

function pushStreamItem(item) {
  streamItems.value.push({ ...item, role: item.role || 'ai', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) })
  nextTick(() => {
    if (streamScroll.value) streamScroll.value.scrollTop = streamScroll.value.scrollHeight
  })
}

function renderMarkdown(text) { return text ? marked.parse(text) : '' }
function formatNumber(value) { return typeof value === 'number' ? value.toFixed(2) : value ?? '-' }
function getDataStateClass(item) { return item.state_desc && item.state_desc !== '正常' && item.state_desc !== 'Unknown' ? 'abnormal' : 'normal' }
function getPreferredDirectConfig() { return llmConfigs.value.find((item) => item.id === 'system_default') || llmConfigs.value.find((item) => item.base_url && (item.api_key_full || item.api_key) && item.model) || null }

function applyDirectConfig(item) {
  if (!item) return
  selectedConfigId.value = item.id
  config.llmUrl = item.base_url || ''
  config.llmKey = item.api_key_full || item.api_key || ''
  config.llmModel = item.model || ''
}

function ensureDirectConfigSelected() {
  if (config.mode === 'direct' && (!config.llmUrl.trim() || !config.llmKey.trim() || !config.llmModel.trim())) applyDirectConfig(getPreferredDirectConfig())
}

function resetRunState() {
  lastError.value = ''
  result.value = {}
  currentData.value = []
  liveAbnormalIndicators.value = []
  monitorUpdatedAt.value = ''
  liveStage.value = 'idle'
  Object.values(phases).forEach((phase) => { phase.status = 'pending' })
}

function updateMonitorSnapshot(payload = {}) {
  currentData.value = payload.semantic_data || currentData.value
  liveAbnormalIndicators.value = payload.abnormal_indicators || liveAbnormalIndicators.value
  if (payload.stage) liveStage.value = payload.stage
  monitorUpdatedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (!file) return
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (loadEvent) => {
    fileData.value = loadEvent.target?.result?.split(',')[1]
    pushStreamItem({ type: 'text', text: `已加载数据文件 **${file.name}**`, level: 'success' })
  }
  reader.readAsDataURL(file)
}

function openFilePicker() { fileInput.value?.click() }

function handleInteraction(id, value) {
  const item = streamItems.value.find((entry) => entry.type === 'interaction' && entry.id === id)
  if (item) {
    item.answered = true
    item.answerText = value === 'yes' ? '继续分析' : '停止任务'
  }
  if (ws.value?.readyState === WebSocket.OPEN) ws.value.send(JSON.stringify({ type: 'interaction_response', id, value }))
  pushStreamItem({ role: 'user', type: 'text', text: value === 'yes' ? '继续分析' : '停止任务' })
  if (value === 'no') isRunning.value = false
}

function handleWsMessage(data) {
  if (data.type === 'log') {
    pushStreamItem({ type: 'text', text: data.message, level: data.level || 'info' })
    if (data.level === 'error') {
      lastError.value = data.message
      isRunning.value = false
      ElMessage.error(data.message)
    }
    return
  }
  if (data.type === 'phase_update') {
    const titleMap = { init: '数据加载与校验', analysis: '原因分析与决策建议', report: '报告生成' }
    if (phases[data.phase]) phases[data.phase].status = data.status
    if (data.phase === 'init' && data.status === 'running') liveStage.value = 'submitted'
    if (data.status === 'error') isRunning.value = false
    pushStreamItem({ type: 'phase', title: titleMap[data.phase] || data.phase, detail: data.step !== undefined ? `步骤 ${data.step}` : data.status, level: data.status === 'error' ? 'error' : 'info' })
    return
  }
  if (data.type === 'interaction') {
    pushStreamItem({ type: 'interaction', id: data.id, title: data.title, desc: data.desc, answered: false })
    return
  }
  if (data.type === 'monitor_update') {
    updateMonitorSnapshot(data.data)
    if (activeTab.value !== 'report') activeTab.value = 'monitor'
    return
  }
  if (data.type === 'result') {
    result.value = data.data
    updateMonitorSnapshot({ semantic_data: data.data.semantic_data || [], abnormal_indicators: data.data.abnormal_indicators || [], stage: 'result_ready' })
    isRunning.value = false
    activeTab.value = 'report'
    pushStreamItem({ type: 'text', text: '分析已完成，结果已经返回。', level: 'success' })
  }
}

function connectWebSocket() {
  wsStatus.value = 'connecting'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws.value = new WebSocket(`${protocol}//${window.location.hostname}:8001`)
  ws.value.onopen = () => { wsStatus.value = 'connected' }
  ws.value.onclose = () => { wsStatus.value = 'disconnected'; setTimeout(connectWebSocket, 3000) }
  ws.value.onmessage = (event) => handleWsMessage(JSON.parse(event.data))
}

function buildPayload() {
  const payload = { type: 'start', mode: config.mode, enable_cot: config.enableCoT }
  if (fileData.value) { payload.file_data = fileData.value; payload.file_name = fileName.value }
  if (config.mode === 'dify') payload.dify_config = { api_url: config.difyUrl.trim(), api_key: config.difyKey.trim() }
  else payload.llm_config = { base_url: config.llmUrl.trim(), api_key: config.llmKey.trim(), model: config.llmModel.trim() }
  return payload
}

function startAnalysis() {
  if (isRunning.value) return
  if (!canStart.value) return ElMessage.error(configErrorMessage.value || 'WebSocket 尚未连接。')
  if (ws.value?.readyState !== WebSocket.OPEN) return ElMessage.error('WebSocket 尚未连接。')
  resetRunState()
  isRunning.value = true
  activeTab.value = 'monitor'
  liveStage.value = 'submitted'
  pushStreamItem({ type: 'text', text: '分析任务已提交。', level: 'info' })
  ws.value.send(JSON.stringify(buildPayload()))
}

async function fetchConfigs() {
  try {
    const response = await fetch(`${apiBaseUrl}/configs`)
    const data = await response.json()
    if (data.success) { llmConfigs.value = data.data; ensureDirectConfigSelected() }
  } catch {
    ElMessage.error('读取模型预设失败。')
  }
}

function handleConfigChange() { applyDirectConfig(llmConfigs.value.find((entry) => entry.id === selectedConfigId.value)) }
function openSaveConfigDialog() { dialogVisible.value = true }

async function confirmSaveConfig() {
  try {
    const response = await fetch(`${apiBaseUrl}/configs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: configForm.name, base_url: config.llmUrl, api_key: config.llmKey, model: config.llmModel }) })
    const data = await response.json()
    if (!data.success) throw new Error(data.error || '保存失败')
    dialogVisible.value = false
    configForm.name = ''
    fetchConfigs()
    ElMessage.success('模型配置已保存。')
  } catch (error) {
    ElMessage.error(error.message || '保存模型配置失败。')
  }
}

function refreshConfigs() { fetchConfigs() }

function downloadReport() {
  const content = ['# 分析摘要', '', '## 原因分析', result.value.reasoning_result || '', '', '## 决策建议', result.value.decision_suggestion || result.value.suggestion || '', '', '## 风险提示', result.value.warning || ''].join('\n')
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'analysis-summary.md'
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(() => { connectWebSocket(); fetchConfigs() })
watch(() => config.mode, (mode) => { if (mode === 'direct') ensureDirectConfigSelected() }, { immediate: true })
</script>
<style scoped>
.page-shell{height:100vh;display:grid;grid-template-columns:280px 1fr;overflow:hidden;background:radial-gradient(circle at top left,rgba(29,78,216,.08),transparent 28%),linear-gradient(180deg,#f7f7f3 0%,#f2f4f1 46%,#eef1ed 100%);color:#1f2937}
.sidebar{height:100vh;overflow:auto;padding:28px 22px;border-right:1px solid #e4e7df;background:rgba(248,249,244,.92)}
.eyebrow{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#6b7280}.brand-title{margin-top:8px;font-size:28px;font-weight:800;line-height:1.15}
.brand-copy,.sidebar-note,.stream-header p,.panel-head p,.empty-text,.bubble-meta,.bubble-time,.sensor-meta,.file-name,.message-line{color:#667085}
.status-card,.panel,.card-section,.kpi-card,.summary-card,.sensor-card,.state-tag{border:1px solid #e4e7df;border-radius:20px;background:#fff}
.status-card{padding:16px;margin-top:16px}.status-row{display:flex;align-items:center;gap:8px;margin-bottom:16px;font-weight:600}.status-dot{width:10px;height:10px;border-radius:999px;background:#c4c8c2}.status-dot.connected{background:#10a37f}.status-dot.connecting{background:#f59e0b}.mini-label{margin-top:10px;font-size:12px;color:#6b7280}.status-main{margin-top:6px;font-size:18px;font-weight:700}.status-sub{margin-top:6px;font-size:14px;font-weight:600}
.main-grid{height:100vh;min-width:0;display:grid;grid-template-columns:minmax(420px,540px) 1fr}.stream-panel{height:100vh;display:flex;flex-direction:column;border-right:1px solid #e4e7df;background:rgba(255,255,255,.88)}.workspace-panel{height:100vh;min-width:0;display:flex;flex-direction:column;padding:26px;overflow:hidden}
.stream-header{display:flex;justify-content:space-between;gap:16px;padding:24px;border-bottom:1px solid #ecefe8}.stream-header h1,.panel h3{margin:0;font-size:22px}.header-badge,.time-chip{height:fit-content;padding:10px 12px;border-radius:999px;background:#eff5f1;color:#3f4c46;font-size:12px;font-weight:700}
.stream-body{flex:1;overflow:auto;padding:22px 20px 12px}.message{display:flex;align-items:flex-start;gap:12px;margin-bottom:18px}.message.user{flex-direction:row-reverse}.avatar{width:34px;height:34px;border-radius:12px;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:#ecefe8;color:#46515c;font-size:12px;font-weight:700}
.bubble{width:fit-content;max-width:min(88%,620px);padding:14px 16px 10px;border-radius:20px;border:1px solid #ecefe8;background:#f7f7f8;box-sizing:border-box;line-height:1.72}.message.user .bubble{background:#e8f6f1;border-color:#cdeee3}.bubble.info,.bubble.phase,.bubble.intro{background:#f5f7f5}.bubble.success{background:#edf8f4;border-color:#cdeee3}.bubble.error{background:#fff2f2;border-color:#ffd6d6}.bubble.interaction{background:#fffaf0;border-color:#f2deb4}.bubble-title,.section-title,.empty-title{font-weight:700;margin-bottom:8px}.bubble-actions{display:flex;gap:8px;margin-top:12px}.bubble-time{margin-top:8px;font-size:11px}
.composer{padding:16px 18px 24px;border-top:1px solid #ecefe8;background:rgba(255,255,255,.94)}.composer-row{display:grid;grid-template-columns:96px 1fr 96px;gap:10px;align-items:center}.ghost-btn,.start-btn,.tabs button,.mode-btn{border:none;cursor:pointer;transition:.2s ease}.ghost-btn,.start-btn{border-radius:12px;padding:10px 12px}.ghost-btn{background:#fff;color:#111827;border:1px solid #d7ddd6}.start-btn{background:#10a37f;color:#fff;font-weight:700}.start-btn:disabled{opacity:.45;cursor:not-allowed}.warning-text{margin-top:10px;color:#b7791f}.error-text{margin-top:10px;color:#dc2626}
.tabs{display:flex;gap:8px;margin-bottom:18px;flex-shrink:0}.tabs button,.mode-btn{padding:10px 16px;border-radius:999px;background:#eef1eb;color:#4b5563}.tabs button.active,.mode-btn.active{background:#fff;border:1px solid #d7dbd3;box-shadow:0 12px 28px rgba(15,23,42,.06);color:#111827;font-weight:700}
.panel{flex:1;min-height:0;overflow:auto;padding:24px;box-shadow:0 18px 44px rgba(15,23,42,.08)}.mode-row{display:flex;gap:10px;margin-bottom:16px}.preset-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;margin-bottom:16px}.checkbox-row,label{margin-top:16px}label{display:block;margin-bottom:8px;color:#5f6672;font-size:13px}.panel-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:18px}.kpi-card,.summary-card{padding:18px;display:flex;flex-direction:column;gap:8px}.kpi-card strong,.summary-card strong{font-size:28px}.kpi-card .compact,.summary-card .compact{font-size:17px;line-height:1.5}.kpi-card.danger{background:#fff5f5;border-color:#f3c3c3}
.empty-card{padding:20px;border-radius:20px;border:1px solid #e3e8df;background:linear-gradient(135deg,#fbfcf9,#f2f8f3)}.monitor-layout,.report-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(260px,.9fr);gap:18px}.card-section{padding:18px}.sensor-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}.sensor-card{padding:16px}.sensor-card.abnormal{background:#fff7f7;border-color:#f3c3c3}.sensor-name{font-size:13px;color:#5f6672}.sensor-state{margin-top:6px;font-size:12px;color:#b7791f}.sensor-value{margin-top:10px;font-size:22px;font-weight:700}.side-stack,.report-side{display:grid;gap:16px;align-content:start}
.tag-list{display:flex;flex-direction:column;gap:8px}.state-tag{padding:10px 12px}.state-tag.danger{background:#fff3f3}.state-tag.ok{background:#edf8f4}.report-layout{display:flex;flex-direction:column;gap:18px}.report-actions{display:flex;justify-content:flex-end}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.report-main{display:grid;gap:18px}.warning-section{background:#fff9ef;border-color:#f1d3a6}.path-list{display:grid;gap:8px;word-break:break-all;color:#4b5563}.markdown :deep(p){margin:0 0 10px}.hidden{display:none}
.sidebar::-webkit-scrollbar,.stream-body::-webkit-scrollbar,.panel::-webkit-scrollbar{width:10px}.sidebar::-webkit-scrollbar-thumb,.stream-body::-webkit-scrollbar-thumb,.panel::-webkit-scrollbar-thumb{background:#d5dad1;border-radius:999px}
@media (max-width:1180px){.page-shell,.main-grid,.kpi-grid,.monitor-layout,.report-grid,.summary-grid{grid-template-columns:1fr}.sidebar{display:none}}
</style>
