<template>
  <div class="page-shell">
    <header class="layout-header">
      <div class="layout-header-title" data-testid="header-title">空分装置智能运行优化</div>
      <div class="layout-header-right">
        <div class="header-actions">
          <button class="header-action-btn" data-testid="toggle-settings" type="button" @click="toggleSettingsPanel">{{ settingsButtonText }}</button>
        </div>
        <div class="header-chip">
          <span>状态：</span>
          <span class="status-dot" :class="wsStatus"></span>
          <span>{{ wsStatusText }}</span>
        </div>
      </div>
    </header>

    <div class="layout-body">
      <aside class="sidebar">
        <!-- <div class="sidebar-title">空分智能优化平台</div> -->

        <section class="session-panel">
          <div class="session-panel-head">
            <div>
              <div class="section-kicker">会话列表</div>
              <!-- <div class="session-note">每个任务保留独立日志、监控和报告。</div> -->
            </div>
            <button class="session-create-btn" type="button" :disabled="hasRunningSession && !currentSession.isRunning" @click="createSessionAndSwitch">新建会话</button>
          </div>

          <div class="session-list">
            <button
              v-for="session in sessionCards"
              :key="session.id"
              class="session-item"
              :class="{ active: session.id === currentSessionId }"
              type="button"
              @click="selectSession(session.id)"
            >
              <div class="session-item-top">
                <strong>{{ session.title }}</strong>
                <span class="session-status" :class="session.statusTone">{{ session.statusText }}</span>
              </div>
              <div class="session-item-meta">{{ session.summary }}</div>
              <div class="session-item-time">{{ session.updatedLabel }}</div>
            </button>
          </div>
        </section>
      </aside>

      <main class="layout-main">
        <div
          ref="mainGridRef"
          class="main-grid"
          :class="{ resizing: isResizingWorkspace, 'workspace-collapsed': isWorkspaceCollapsed && isDesktopLayout }"
          :style="mainGridStyle"
        >
          <section class="stream-panel">
            <StreamRail
              :current-workflow-step-text="currentWorkflowStepText"
              :current-risk-level="currentRiskLevel"
              :risk-level-text="riskLevelText"
              :llm-working="llmWorking"
              :current-llm-task-label="currentLlmTaskLabel"
              :current-progress-percent="currentProgressPercent"
              :current-eta-text="currentEtaText"
              :next-action-text="nextActionText"
              :has-active-action="Boolean(activeActionCard)"
              @focus-action="focusActionCard"
            />

            <div ref="streamScroll" class="stream-body">
              <article class="message ai">
                <div class="avatar">AI</div>
                <div class="bubble intro">
                  <div class="bubble-title">开始前</div>
                  <div class="markdown">连接建立后可直接发起分析。请先在下方“添加数据”中选择上传文件或示例文件。</div>
                </div>
              </article>

              <AnalysisStepGroup
                v-for="group in stepTimelineGroups"
                :key="group.key"
                :group="group"
                :thinking-preview-limit="thinkingPreviewLimit"
                :risk-level-text="riskLevelText"
                :render-markdown="renderMarkdown"
                :get-thinking-preview="getThinkingPreview"
                @toggle-group="toggleStepGroup"
                @toggle-thinking="toggleThinkingExpanded"
                @open-thinking-detail="openThinkingDetail"
              />
            </div>

            <ActionCard
              ref="actionCardRef"
              :card="activeActionCard"
              :risk-level-text="riskLevelText"
              :render-markdown="renderMarkdown"
              :get-interaction-action-text="getInteractionActionText"
              @reply="handleInteraction"
            />

            <input
              ref="fileInput"
              data-testid="file-input"
              class="visually-hidden-input"
              type="file"
              accept=".xlsx,.xls,.csv"
              tabindex="-1"
              aria-hidden="true"
              @change="handleFileSelect"
            />

            <AnalysisComposerCard
              :is-picking-file="isPickingFile"
              :is-running="currentSession.isRunning"
              :can-start="canStart"
              :data-source="dataSource"
              :file-name="fileName"
              :selected-sample-path="selectedSamplePath"
              :selected-sample-name="selectedSampleName"
              :sample-files="sampleFiles"
              :samples-loading="samplesLoading"
              :samples-error="samplesError"
              :task-note="taskNote"
              :has-running-session-lock="hasRunningSession && !currentSession.isRunning"
              :config-error-message="configErrorMessage"
              :last-error="lastError"
              @choose-source="handleChooseDataSource"
              @select-sample="handleSampleSelect"
              @refresh-samples="refreshSampleFiles"
              @update-task-note="updateTaskNote"
              @start="startAnalysis"
            />
          </section>

          <div
            v-if="canResizeWorkspace"
            class="workspace-resizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="调整右侧面板宽度"
            tabindex="0"
            @pointerdown="startWorkspaceResize"
            @dblclick="resetWorkspaceWidth"
            @keydown="handleWorkspaceResizeKeydown"
          ></div>

          <WorkspaceCollapsedRail
            v-if="isWorkspaceCollapsed && isDesktopLayout"
            :active-tab="activeTab"
            :is-running="currentSession.isRunning"
            @expand="setWorkspaceCollapsed(false)"
            @switch-tab="switchWorkspaceFromRailTab"
          />

          <section v-else class="workspace-panel">
            <div class="workspace-toolbar">
              <div class="workspace-tabs" role="tablist" aria-label="流程导航">
                <button
                  v-for="tab in workspaceTabs"
                  :key="tab.id"
                  class="workspace-tab"
                  :data-testid="`workspace-tab-${tab.id}`"
                  :class="{ active: activeTab === tab.id }"
                  type="button"
                  :aria-pressed="activeTab === tab.id"
                  @click="switchWorkspace(tab.id)"
                >
                  <span class="workspace-tab-index">{{ tab.index }}</span>
                  <span class="workspace-tab-copy">
                    <strong>{{ tab.title }}</strong>
                    <small>{{ tab.description }}</small>
                  </span>
                </button>
              </div>
              <div class="workspace-toolbar-actions">
                <button
                  v-if="canShowWorkspaceCollapseControl"
                  class="inline-action-btn workspace-collapse-btn"
                  data-testid="toggle-workspace-collapse"
                  type="button"
                  aria-label="折叠右侧面板"
                  aria-pressed="false"
                  @click="toggleWorkspaceCollapsed"
                >
                  折叠右栏
                </button>
                <div class="workspace-stage">{{ liveStageText }}</div>
              </div>
            </div>

            <div class="workspace-head">
              <div>
                <h2>{{ activeWorkspaceMeta.title }}</h2>
                <p>{{ activeWorkspaceMeta.description }}</p>
              </div>
            </div>

            <div v-if="workspaceView === 'monitor'" class="panel compact-panel">
              <div class="panel-head">
                <div>
                  <h3>实时监控</h3>
                  <p>语义分析和决策生成阶段都会刷新监控卡片。</p>
                </div>
                <div class="time-chip">{{ monitorUpdatedAt || '尚未收到实时更新' }}</div>
              </div>

              <div class="kpi-grid">
                <div class="kpi-card"><span>监控点位数</span><strong>{{ currentData.length }}</strong></div>
                <div class="kpi-card" :class="{ danger: abnormalCount > 0 }"><span>异常指标数</span><strong>{{ abnormalCount }}</strong></div>
                <div class="kpi-card"><span>任务状态</span><strong class="compact">{{ systemStatusText }}</strong></div>
                <div class="kpi-card"><span>最新阶段</span><strong class="compact">{{ liveStageText }}</strong></div>
              </div>

              <div v-if="!currentData.length" class="panel-empty">
                <div class="empty-title">等待实时数据</div>
                <div class="empty-text">任务进入分析阶段后，这里会即时刷新当前指标和异常摘要。</div>
                <div v-if="fileName" class="empty-text">当前已加载数据文件《{{ fileName }}》，等待分析完成后生成监控快照与可视化。</div>
              </div>

              <div v-else class="monitor-layout">
                <div v-if="monitorOverviewAvailable" class="monitor-overview-stack">
                  <ReportOverviewSection :result="monitorOverviewResult" />
                  <ReportDataCurveBrowser :result="monitorOverviewResult" />
                </div>

                <div class="panel-section monitor-visual-panel">
                  <div class="section-title">数据可视化</div>
                  <div class="section-caption">按偏差百分比展示当前波动最明显的指标，便于快速定位风险点。</div>
                  <div v-if="monitorVisualItems.length" class="monitor-visual-list">
                    <div v-for="item in monitorVisualItems" :key="`${item.name}-${item.percentText}`" class="visual-row">
                      <div class="visual-meta">
                        <strong>{{ item.name }}</strong>
                        <span>当前 {{ formatNumber(item.current_value) }} / 基准 {{ formatNumber(item.baselineValue) }}</span>
                      </div>
                      <div class="visual-bar-shell">
                        <div class="visual-bar-track"></div>
                        <div class="visual-bar-fill" :class="item.tone" :style="{ width: item.barWidth }"></div>
                      </div>
                      <div class="visual-value" :class="item.tone">{{ item.percentText }}</div>
                    </div>
                  </div>
                  <div v-else class="empty-text">当前返回的数据不足以计算偏差百分比。</div>
                </div>

                <div class="monitor-bottom-grid">
                  <div class="panel-section">
                    <div class="section-title">分类指标快照</div>
                    <div v-if="monitorGroups.length" class="metric-group-list">
                      <section v-for="group in monitorGroups" :key="group.key" class="metric-group" :class="group.key">
                        <div class="metric-group-head">
                          <div class="metric-group-copy">
                            <strong>{{ group.title }}</strong>
                            <div class="metric-group-note">{{ group.description }}</div>
                          </div>
                          <div class="metric-group-summary">
                            <span class="metric-group-badge">{{ group.items.length }} 项</span>
                            <span v-if="group.abnormalCount" class="metric-group-badge danger">{{ group.abnormalCount }} 异常</span>
                            <span class="metric-group-badge">{{ group.avgPercentText }}</span>
                          </div>
                        </div>
                        <div class="sensor-grid grouped">
                          <div v-for="item in group.items" :key="`${group.key}-${item.name}-${item.current_value}`" class="sensor-card" :class="getDataStateClass(item)">
                            <div class="sensor-name">{{ item.name }}</div>
                            <div class="sensor-state">{{ item.state_desc }}</div>
                            <div class="sensor-value">{{ formatNumber(item.current_value) }}</div>
                            <div class="sensor-meta">偏差：{{ formatDiffSummary(item) }}</div>
                            <div v-if="isAbnormalState(item.state_desc) && item.rule_reason" class="sensor-note">原因：{{ item.rule_reason }}</div>
                            <div v-if="isAbnormalState(item.state_desc) && item.ai_reason" class="sensor-note ai">AI复核：{{ item.ai_reason }}</div>
                            <div v-if="isAbnormalState(item.state_desc)" class="sensor-note">窗口：{{ formatWindowSummary(item) }}</div>
                          </div>
                        </div>
                      </section>
                    </div>
                    <div v-else class="empty-text">当前监控项还不足以完成自动分类。</div>
                  </div>

                  <div class="side-stack monitor-side-stack">
                    <div class="panel-section">
                      <div class="section-title">实时异常摘要</div>
                      <div v-if="!monitorAbnormalIndicators.length" class="empty-text">当前没有需要重点跟踪的异常指标。</div>
                      <div v-else class="abnormal-detail-list">
                        <div
                          v-for="ind in monitorAbnormalIndicators"
                          :key="ind.tag_id || ind.name"
                          class="abnormal-detail-card"
                          :class="getIndicatorTone(ind)"
                        >
                          <div class="abnormal-detail-head">
                            <strong>{{ ind.name }}</strong>
                            <span class="state-tag" :class="getIndicatorTone(ind)">{{ ind.level }}</span>
                          </div>
                          <div class="abnormal-detail-meta">当前值 {{ formatNumber(ind.current_value) }} / 偏差 {{ formatDiffSummary(ind) }}</div>
                          <div class="abnormal-detail-text"><span>规则原因</span>{{ ind.rule_reason || '当前未生成规则原因' }}</div>
                          <div v-if="ind.ai_reason" class="abnormal-detail-text"><span>AI复核</span>{{ ind.ai_reason }}</div>
                          <div class="abnormal-detail-text"><span>时间窗口</span>{{ formatWindowSummary(ind) }}</div>
                          <div class="abnormal-detail-text"><span>当前快照</span>{{ formatCurrentSnapshot(ind) }}</div>
                        </div>
                      </div>
                    </div>
                    <div class="panel-section">
                      <div class="section-title">阶段说明</div>
                      <div class="empty-text">当前监控阶段：{{ liveStageText }}。语义分析完成后会先推送一次快照，决策生成后会再次刷新。</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-else class="panel compact-panel">
              <div class="panel-head">
                <div>
                  <h3>分析报告</h3>
                  <!-- <p>右侧字号和间距已压缩，方便同屏展示更多内容。</p> -->
                </div>
                <div class="report-actions">
                  <el-button data-testid="download-report" size="small" :icon="Download" :disabled="!hasReadyReport" @click="downloadReport">导出报告</el-button>
                </div>
              </div>

              <div v-if="!result.reasoning_result" class="panel-empty">
                <div class="empty-title">报告尚未生成</div>
                <div class="empty-text">完成一次分析后，这里会展示原因分析、操作建议、风险提示和报告路径。</div>
              </div>

              <div v-else class="report-layout">
                <div class="report-main">
                  <ReportOverviewSection :result="result" />
                  <ReportDataCurveBrowser :result="result" />
                  <ReportTrendOverviewPanel :result="result" />
                  <ReportVisualizationPanel :result="result" />
                  <ReportCalculationAuditPanel :result="result" />
                  <section class="panel-section">
                    <div class="section-title">原因分析</div>
                    <div class="markdown prose-card" v-html="renderReportMarkdown(result.reasoning_result)"></div>
                  </section>
                  <section class="panel-section">
                    <div class="section-title">决策建议</div>
                    <div class="markdown prose-card" v-html="renderReportMarkdown(result.decision_suggestion || result.suggestion || '')"></div>
                  </section>
                  <section v-if="result.warning" class="panel-section warning-section">
                    <div class="section-title">风险提示</div>
                    <div class="markdown prose-card" v-html="renderReportMarkdown(result.warning)"></div>
                  </section>
                </div>

                <div class="report-side">
                  <ReportAbnormalList
                    :abnormal-indicators="filteredResultAbnormalIndicators"
                    :semantic-summary="result.semantic_summary"
                    :get-indicator-tone="getIndicatorTone"
                    :format-number="formatNumber"
                    :format-diff-summary="formatDiffSummary"
                    :format-window-summary="formatWindowSummary"
                    :format-current-snapshot="formatCurrentSnapshot"
                  />
                  <ReportPaths
                    :report-file-name="reportFileName"
                    :report-md="result.report_md || ''"
                    :report-pdf="result.report_pdf || ''"
                  />
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>

    <el-dialog
      v-model="settingsOpen"
      width="960px"
      data-testid="settings-dialog"
      destroy-on-close
      class="settings-center-dialog"
      modal-class="settings-modal-overlay"
      :show-close="false"
      align-center
    >
      <div class="settings-center-shell">
        <aside class="settings-center-nav">
          <button class="settings-close-btn" type="button" aria-label="关闭设置" @click="settingsOpen = false">×</button>
          <div v-for="group in settingsNavGroups" :key="group.key" class="settings-nav-group">
            <div class="settings-nav-group-title">{{ group.label }}</div>
            <button
              v-for="item in group.items"
              :key="item.key"
              class="settings-nav-item"
              :class="{ active: settingsSection === item.key }"
              type="button"
              @click="settingsSection = item.key"
            >
              <span class="settings-nav-icon">
                <el-icon><component :is="item.icon" /></el-icon>
              </span>
              <span class="settings-nav-copy">
                <strong>{{ item.title }}</strong>
                <small>{{ item.subtitle }}</small>
              </span>
            </button>
          </div>
        </aside>

        <section class="settings-center-main">
          <div class="settings-main-head">
            <h3>{{ currentSettingsNavItem.title }}</h3>
            <p>{{ currentSettingsNavItem.description }} 配置独立展示，不占用实时监控与分析报告区域。</p>
          </div>

          <div v-show="settingsSection === 'access'" class="panel compact-panel settings-dialog-panel">
            <div class="mode-row">
              <button class="mode-btn" data-testid="mode-dify" :class="{ active: config.mode === 'dify' }" type="button" @click="config.mode = 'dify'">Dify 应用</button>
              <button class="mode-btn" data-testid="mode-direct" :class="{ active: config.mode === 'direct' }" type="button" @click="config.mode = 'direct'">直连模型</button>
            </div>

            <template v-if="config.mode === 'dify'">
              <label>知识库 API 地址</label>
              <el-input v-model="config.difyUrl" placeholder="http://localhost/v1" />
              <label>Dify API Key</label>
              <el-input v-model="config.difyKey" type="password" show-password />
            </template>

            <template v-else>
              <label data-testid="label-model-preset">模型预设</label>
              <div class="preset-row" data-testid="preset-row">
                <el-select v-model="selectedConfigId" data-testid="select-model-preset" placeholder="选择预设" @change="handleConfigChange">
                  <el-option v-for="item in llmConfigs" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
                <el-button :icon="Refresh" circle @click="refreshConfigs" />
                <el-button :icon="Plus" circle @click="openSaveConfigDialog" />
              </div>
              <label data-testid="label-model-url">模型服务地址</label>
              <el-input v-model="config.llmUrl" data-testid="input-model-url" />
              <label>模型 API Key</label>
              <el-input v-model="config.llmKey" type="password" show-password />
              <label>模型名称</label>
              <el-input v-model="config.llmModel" />
            </template>
          </div>

          <div v-show="settingsSection === 'runtime'" class="panel compact-panel settings-dialog-panel">
            <div class="settings-sub-title">推理参数</div>
            <div class="settings-sub-text">用于控制任务执行时的推理策略，支持按需开启分步推理。</div>
            <div class="checkbox-row">
              <el-checkbox v-model="config.enableCoT" label="启用分步推理（CoT）" border />
            </div>
          </div>

          <div v-show="settingsSection === 'about'" class="panel compact-panel settings-dialog-panel">
            <div class="settings-sub-title">使用说明</div>
            <div class="settings-sub-text">1. 优先在“模型接入”中确认地址、Key 与模型名。</div>
            <div class="settings-sub-text">2. 调整参数后无需额外保存，下一次分析会直接生效。</div>
            <div class="settings-sub-text">3. 关闭窗口不会影响当前实时监控与报告查看。</div>
          </div>

          <div class="settings-actions">
            <el-button data-testid="close-settings-dialog" @click="settingsOpen = false">关闭</el-button>
          </div>
        </section>
      </div>
    </el-dialog>

    <el-dialog v-model="dialogVisible" title="保存模型配置" width="420px">
      <el-input v-model="configForm.name" placeholder="请输入配置名称" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSaveConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="thinkingDetailOpen"
      title="过程详情"
      width="720px"
      destroy-on-close
      class="thinking-detail-dialog"
    >
      <div v-if="thinkingDetailState.item" class="thinking-detail-shell">
        <div class="thinking-detail-meta">
          <div class="thinking-detail-title-row">
            <strong>{{ thinkingDetailState.groupTitle || '当前步骤' }}</strong>
            <span class="thinking-detail-badge">{{ thinkingDetailEntryCount }} 条过程记录</span>
          </div>
          <div class="thinking-detail-summary">{{ thinkingDetailState.item.summary || '阶段过程摘要' }}</div>
          <div class="thinking-detail-submeta">
            <span v-if="thinkingDetailState.stepLabel">{{ thinkingDetailState.stepLabel }}</span>
            <span v-if="thinkingDetailState.item.time">最后更新 {{ thinkingDetailState.item.time }}</span>
          </div>
        </div>

        <div v-if="thinkingDetailEntries.length" class="thinking-detail-list">
          <article
            v-for="(entry, idx) in thinkingDetailEntries"
            :key="`${thinkingDetailState.item.timestampMs || 'thinking'}-${idx}`"
            class="thinking-detail-entry"
          >
            <div class="thinking-detail-entry-head">
              <span>过程 {{ idx + 1 }}</span>
              <span>{{ entry.time || '未记录时间' }}</span>
            </div>
            <div class="markdown" v-html="renderMarkdown(entry.text || '')"></div>
          </article>
        </div>
        <div v-else class="empty-text">当前没有可回看的过程消息。</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { Connection, Cpu, Download, InfoFilled, Plus, Refresh } from '@element-plus/icons-vue'
import AnalysisStepGroup from '../components/AnalysisStepGroup.vue'
import ActionCard from '../components/ActionCard.vue'
import AnalysisComposerCard from '../components/AnalysisComposerCard.vue'
import StreamRail from '../components/StreamRail.vue'
import WorkspaceCollapsedRail from '../components/WorkspaceCollapsedRail.vue'
import ReportOverviewSection from '../components/ReportOverviewSection.vue'
import ReportDataCurveBrowser from '../components/ReportDataCurveBrowser.vue'
import ReportTrendOverviewPanel from '../components/ReportTrendOverviewPanel.vue'
import ReportVisualizationPanel from '../components/ReportVisualizationPanel.vue'
import ReportCalculationAuditPanel from '../components/ReportCalculationAuditPanel.vue'
import ReportAbnormalList from '../components/ReportAbnormalList.vue'
import ReportPaths from '../components/ReportPaths.vue'
import { useWorkspaceLayout } from '../composables/useWorkspaceLayout'
import {
  workflowStepTitleMap,
  normalizeRiskLevel,
  riskLevelText,
  compareRiskLevel,
  maxRiskLevel,
  normalizeWorkflowStepId,
  resolveWorkflowFromPhaseUpdate,
  resolveWorkflowFromInteraction,
  formatWorkflowStepLabel,
  resolvePhaseStepState,
} from '../composables/useTimelineSession'

const ws = ref(null)
const streamScroll = ref(null)
const fileInput = ref(null)
const actionCardRef = ref(null)
const mainGridRef = ref(null)
const wsStatus = ref('disconnected')
const activeTab = ref('monitor')
const settingsOpen = ref(false)
const settingsSection = ref('access')
const dialogVisible = ref(false)
const thinkingDetailOpen = ref(false)
const thinkingDetailState = reactive({
  item: null,
  groupTitle: '',
  stepLabel: '',
})
const configForm = reactive({ name: '' })
const llmConfigs = ref([])
const selectedConfigId = ref('')
const isPickingFile = ref(false)
const {
  isDesktopLayout,
  isWorkspaceCollapsed,
  isResizingWorkspace,
  canResizeWorkspace,
  canShowWorkspaceCollapseControl,
  mainGridStyle,
  toggleWorkspaceCollapsed,
  setWorkspaceCollapsed,
  startWorkspaceResize,
  handleWorkspaceResizeKeydown,
  resetWorkspaceWidth,
  initializeWorkspaceLayout,
  disposeWorkspaceLayout,
  switchWorkspaceFromRail,
} = useWorkspaceLayout({ mainGridRef })
const thinkingPreviewLimit = 3
const thinkingMinPendingMs = 900
const llmMinVisibleMs = 700
const llmSettleDelayMs = 200
const stepTypewriterQuietWindowMs = 1500
const stepTypewriterCharMs = 100
const stepTypewriterHoldMs = 700
const stepTypewriterSettleMs = 200
const stepTickIntervalMs = 120
const llmConfigCacheKey = 'demo2opt.llm-configs'
const uxMetricsEndpoint = '/ux-metrics'
const systemStepGroupKey = 'system'
const stepTypewriterTemplates = {
  1: ['正在读取数据文件...', '正在校验字段结构与时间列...', '正在整理可用记录并准备范围确认...'],
  2: ['正在锁定最新时刻快照...', '正在汇总快照指标与采样点...', '正在准备进入规则预筛...'],
  3: ['正在执行规则预筛...', '正在进行语义复核...', '正在等待语义复核结果返回...'],
  4: ['正在生成工况总览...', '正在提取关键风险点...', '正在准备工况确认卡...'],
  5: ['正在提取时序特征...', '正在复核异常候选项...', '正在整理候选异常确认信息...'],
  6: ['正在检索知识库索引...', '正在对齐工况关键词...', '正在返回候选手段...'],
  7: ['正在进行根因诊断推理...', '正在交叉验证规则与知识依据...', '正在输出根因解释...'],
  8: ['正在生成决策建议...', '正在进行效果推演与验证...', '正在整理报告正文...'],
}
const fallbackLlmConfigs = typeof __FALLBACK_LLM_CONFIGS__ !== 'undefined' && Array.isArray(__FALLBACK_LLM_CONFIGS__) ? __FALLBACK_LLM_CONFIGS__ : []
const workspaceTabs = [
  { id: 'monitor', index: '01', title: '实时监控', description: ''},
  { id: 'report', index: '02', title: '分析报告', description: ''},
]
const settingsNavGroups = [
  {
    key: 'core',
    label: '核心设置',
    items: [
      { key: 'access', title: '模型接入', subtitle: '接口与预设配置', description: '集中管理 Dify 与直连模型接入参数。', icon: Connection },
      { key: 'runtime', title: '推理参数', subtitle: '执行策略开关', description: '控制推理行为与步骤执行策略。', icon: Cpu },
    ],
  },
  {
    key: 'help',
    label: '帮助信息',
    items: [
      { key: 'about', title: '使用说明', subtitle: '配置与流程建议', description: '查看配置建议与操作说明。', icon: InfoFilled },
    ],
  },
]
const settingsNavItemMap = Object.fromEntries(settingsNavGroups.flatMap((group) => group.items.map((item) => [item.key, item])))
const monitorCategoryMeta = [
  {
    key: 'cooling_capacity',
    title: '制冷量',
    description: '关注膨胀机、冷量供给与制冷能力相关指标。',
    keywords: ['制冷量', '冷量', '膨胀机', '膨胀量', 'expander'],
  },
  {
    key: 'loss_energy',
    title: '冷损（能耗）',
    description: '关注主换、冷箱、泵耗与单耗等冷损和能耗相关指标。',
    keywords: ['冷损', '冷耗', '主换', '主换热', '冷箱', '单耗', '能耗', '电耗', '气耗', '汽耗', '蒸汽', '水耗', '泵', '压缩机'],
  },
  {
    key: 'extraction',
    title: '提取',
    description: '关注提取率、回收率、纯度与产品产量相关指标。',
    keywords: ['提取', '收率', '回收', '纯度', '提纯', '产量', '液氧产量', '液氩产量', '液氮产量', '氧提取', '氩提取', '氮提取'],
  },
  {
    key: 'load',
    title: '负荷',
    description: '关注机组负荷、处理量与关键流量水平。',
    keywords: ['负荷', '处理量', '进气量', '流量', '空压', '增压机', '吞吐'],
  },
  {
    key: 'other',
    title: '其他',
    description: '暂未命中上述四类的监控项。',
    keywords: [],
  },
]

const preferredMonitorCategoryMeta = [
  {
    key: 'cooling_capacity',
    title: '制冷量',
    description: '关注膨胀机、冷量供给与制冷能力相关指标。',
    keywords: ['制冷量', '冷量', '膨胀机', '膨胀量', 'expander'],
  },
  {
    key: 'loss_energy',
    title: '冷损（能耗）',
    description: '关注主换、冷箱、泵耗与单耗等冷损和能耗相关指标。',
    keywords: ['冷损', '冷耗', '主换', '主换热', '冷箱', '单耗', '能耗', '电耗', '气耗', '汽耗', '蒸汽', '水耗', '泵', '压缩机'],
  },
  {
    key: 'extraction',
    title: '提取',
    description: '关注提取率、回收率、纯度与产品产量相关指标。',
    keywords: ['提取', '收率', '回收', '纯度', '提纯', '产量', '液氧产量', '液氩产量', '液氮产量', '氧提取', '氩提取', '氮提取'],
  },
  {
    key: 'load',
    title: '负荷',
    description: '关注机组负荷、处理量与关键流量水平。',
    keywords: ['负荷', '处理量', '进气量', '流量', '空压', '增压机', '吞吐'],
  },
  {
    key: 'other',
    title: '其他',
    description: '暂未命中上述四类的监控项。',
    keywords: [],
  },
]
let wsConnectPromise = null
let wsReconnectEnabled = false
let sessionSeed = 1
let filePickerUnlockTimer = 0
let filePickerWatchdogTimer = 0
let filePickerFocusHandler = null
let nowTickTimer = 0
const thinkingSettleTimers = new Map()
const llmTaskSettleTimers = new Map()

const runningSessionId = ref(null)
const nowTick = ref(Date.now())

const config = reactive({
  mode: 'direct',
  difyUrl: 'http://localhost/v1',
  difyKey: '',
  llmUrl: 'https://api.openai.com/v1',
  llmKey: '',
  llmModel: 'gpt-4o-mini',
  enableCoT: true,
})

const createPhases = () => ({ init: { status: 'pending' }, analysis: { status: 'pending' }, report: { status: 'pending' } })
const createSession = (title) => ({
  id: `session-${Date.now()}-${sessionSeed++}`,
  title: title || `新会话 ${sessionSeed - 1}`,
  streamItems: [],
  stepStates: {},
  stepExpanded: {},
  currentPhase: 'system',
  workflowStepId: null,
  workflowStepTitle: '',
  activeLlmTasks: {},
  lastLlmTaskLabel: '',
  progressPercent: 0,
  etaSec: null,
  highestRiskLevel: 'low',
  result: {},
  currentData: [],
  liveAbnormalIndicators: [],
  monitorVisualizationContext: {},
  monitorOverallJudgement: {},
  monitorSemanticSummary: {},
  monitorDataOverview: {},
  monitorUpdatedAt: '',
  liveStage: 'idle',
  lastError: '',
  isRunning: false,
  phases: createPhases(),
  dataSource: 'none',
  selectedSamplePath: '',
  selectedSampleName: '',
  sampleFiles: [],
  samplesLoading: false,
  samplesError: '',
  fileName: '',
  fileData: null,
  taskNote: '',
  uxMarks: { taskStartedAt: null, keyActionCardRendered: false, finishedLogged: false },
  updatedAt: Date.now(),
})

const sessions = ref([createSession()])
const currentSessionId = ref(sessions.value[0].id)

function getSessionById(id = currentSessionId.value) {
  return sessions.value.find((item) => item.id === id) || sessions.value[0]
}

function touchSession(id = currentSessionId.value) {
  const session = getSessionById(id)
  if (session) session.updatedAt = Date.now()
}

function bindSession(key) {
  return computed({
    get: () => currentSession.value[key],
    set: (value) => {
      currentSession.value[key] = value
      touchSession()
    },
  })
}

const currentSession = computed(() => getSessionById())
const streamItems = bindSession('streamItems')
const result = bindSession('result')
const currentData = bindSession('currentData')
const liveAbnormalIndicators = bindSession('liveAbnormalIndicators')
const monitorUpdatedAt = bindSession('monitorUpdatedAt')
const liveStage = bindSession('liveStage')
const currentPhase = bindSession('currentPhase')
const progressPercent = bindSession('progressPercent')
const highestRiskLevel = bindSession('highestRiskLevel')
const lastError = bindSession('lastError')
const dataSource = bindSession('dataSource')
const selectedSamplePath = bindSession('selectedSamplePath')
const selectedSampleName = bindSession('selectedSampleName')
const sampleFiles = bindSession('sampleFiles')
const samplesLoading = bindSession('samplesLoading')
const samplesError = bindSession('samplesError')
const fileName = bindSession('fileName')
const fileData = bindSession('fileData')
const taskNote = bindSession('taskNote')
const phases = computed(() => currentSession.value.phases)
const workspaceView = computed(() => activeTab.value)
const currentSettingsNavItem = computed(() => settingsNavItemMap[settingsSection.value] || settingsNavItemMap.access)
const hasRunningSession = computed(() => Boolean(runningSessionId.value))

const trimTrailingSlash = (value = '') => value.replace(/\/+$/, '')
const getApiBaseUrl = () => trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || '') || '/api'

function getApiHealthUrl() {
  const envUrl = trimTrailingSlash(import.meta.env.VITE_API_HEALTH_URL || '')
  if (envUrl) return envUrl
  const envBase = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || '')
  if (envBase) return `${envBase}/health`
  const protocol = window.location.protocol
  const host = import.meta.env.VITE_API_HOST || window.location.hostname
  const port = import.meta.env.VITE_API_PORT || '5000'
  return `${protocol}//${host}:${port}/api/health`
}

function getWebSocketUrl() {
  const envUrl = trimTrailingSlash(import.meta.env.VITE_WS_URL || '')
  if (envUrl) return envUrl
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.VITE_WS_HOST || window.location.hostname
  const port = import.meta.env.VITE_WS_PORT || '8001'
  return `${protocol}//${host}:${port}`
}

const apiBaseUrl = getApiBaseUrl()
const apiHealthUrl = getApiHealthUrl()
const wsStatusText = computed(() => (wsStatus.value === 'connected' ? '已连接' : wsStatus.value === 'connecting' ? '连接中' : '未连接'))
const settingsButtonText = computed(() => '设置')
const configErrorMessage = computed(() => {
  if (!config.difyUrl.trim()) return '知识检索步骤缺少知识库 API 地址。'
  if (config.mode === 'dify') return ''
  if (!config.llmUrl.trim()) return '直连模型模式缺少服务地址。'
  if (!config.llmKey.trim()) return '直连模型模式缺少 API Key。'
  if (!config.llmModel.trim()) return '直连模型模式缺少模型名称。'
  return ''
})
const canStartConfig = computed(() => !configErrorMessage.value)
const canStartDataSource = computed(() => {
  if (dataSource.value === 'upload') return Boolean(fileData.value && fileName.value)
  if (dataSource.value === 'sample') return Boolean(selectedSamplePath.value)
  return false
})
const canStart = computed(() => canStartConfig.value && canStartDataSource.value)

const parseTimeMs = (value) => {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function createDefaultStepState(stepId, title = '') {
  return {
    stepId,
    title: title || workflowStepTitleMap[stepId] || '',
    state: 'pending',
    startedAt: '',
    endedAt: '',
    startedMs: 0,
    endedMs: 0,
    phase: 'analysis',
  }
}

function ensureSessionStepState(session, stepId, title = '') {
  if (!session || !stepId) return null
  if (!session.stepStates || typeof session.stepStates !== 'object') session.stepStates = {}
  if (!session.stepStates[stepId]) session.stepStates[stepId] = createDefaultStepState(stepId, title)
  if (title && !session.stepStates[stepId].title) session.stepStates[stepId].title = title
  return session.stepStates[stepId]
}

function upsertSessionStepState(session, stepId, { state = '', title = '', phase = '', startedAt = '', endedAt = '' } = {}) {
  if (!session || !stepId) return
  const step = ensureSessionStepState(session, stepId, title)
  if (!step) return
  if (title) step.title = title
  if (phase) step.phase = phase

  if (state === 'started' || state === 'running') {
    const startIso = startedAt || new Date().toISOString()
    step.state = 'running'
    step.startedAt = startIso
    step.startedMs = parseTimeMs(startIso) || Date.now()
    step.endedAt = ''
    step.endedMs = 0
    return
  }

  if (state === 'completed' || state === 'failed') {
    const endIso = endedAt || new Date().toISOString()
    if (!step.startedMs) {
      const fallbackStart = startedAt || endIso
      step.startedAt = fallbackStart
      step.startedMs = parseTimeMs(fallbackStart) || Date.now()
    }
    step.state = state
    step.endedAt = endIso
    step.endedMs = parseTimeMs(endIso) || Date.now()
  }
}

function formatDurationText(totalSeconds) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return '已运行 00:00'
  const minute = Math.floor(totalSeconds / 60)
  const second = Math.floor(totalSeconds % 60)
  return `已运行 ${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`
}

function stepStateText(state = 'pending') {
  if (state === 'running') return '进行中'
  if (state === 'completed') return '已完成'
  if (state === 'failed') return '失败'
  return '待执行'
}

function getThinkingEntryTimestamp(item = {}) {
  if (!Array.isArray(item.entries) || !item.entries.length) return item.timestampMs || 0
  const latest = item.entries[item.entries.length - 1]
  return latest?.timestampMs || item.timestampMs || 0
}

function getGroupLastEventTimestamp(group) {
  if (!group?.items?.length) return group?.startedMs || 0
  return group.items.reduce((latest, item) => {
    const itemTime = item.type === 'thinking' ? getThinkingEntryTimestamp(item) : (item.timestampMs || 0)
    return itemTime > latest ? itemTime : latest
  }, group.startedMs || 0)
}

function buildStepTypewriterText(group) {
  const stepId = normalizeWorkflowStepId(group?.stepId)
  if (!stepId || group.state !== 'running') return ''
  if (activeActionCard.value?.blocking && !activeActionCard.value?.answered) return ''

  const templates = (stepTypewriterTemplates[stepId] || []).slice(0, 6)
  if (!templates.length) return ''

  const lastRealEventMs = getGroupLastEventTimestamp(group)
  const silentMs = nowTick.value - lastRealEventMs
  if (silentMs < stepTypewriterQuietWindowMs) return ''

  const startedMs = group.startedMs || lastRealEventMs || nowTick.value
  if (nowTick.value < startedMs) return ''

  const lineDurations = templates.map((line) => (line.length * stepTypewriterCharMs) + stepTypewriterHoldMs + stepTypewriterSettleMs)
  const animationMs = silentMs - stepTypewriterQuietWindowMs
  let cursor = animationMs
  for (let i = 0; i < templates.length; i += 1) {
    const line = templates[i]
    const duration = lineDurations[i]
    if (cursor <= duration) {
      const typeMs = line.length * stepTypewriterCharMs
      if (cursor <= typeMs) {
        const count = Math.max(1, Math.min(line.length, Math.floor(cursor / stepTypewriterCharMs) + 1))
        return line.slice(0, count)
      }
      return line
    }
    cursor -= duration
  }

  return templates[templates.length - 1]
}
function normalizeAbnormalIndicator(item = {}) {
  const currentValue = item.current_value ?? item.value ?? null
  const level = item.level || item.state_desc || item.status || ''
  return {
    ...item,
    value: currentValue,
    current_value: currentValue,
    level,
    state_desc: item.state_desc || level,
    rule_reason: item.rule_reason || '',
    ai_reason: item.ai_reason || '',
    window: item.window || {},
    snapshot_timestamp: item.snapshot_timestamp || '',
    diff: item.diff ?? 0,
    diff_percent: item.diff_percent ?? null,
  }
}

function filterAbnormalIndicators(indicators = []) {
  return indicators
    .map((item) => normalizeAbnormalIndicator(item))
    .filter((item) => isAbnormalState(item.level || item.state_desc || item.status || ''))
}

const filteredLiveAbnormalIndicators = computed(() => filterAbnormalIndicators(liveAbnormalIndicators.value || []))
const filteredResultAbnormalIndicators = computed(() => filterAbnormalIndicators(result.value.abnormal_indicators || []))
function buildIndicatorDetailMap(items = []) {
  return new Map(items.map((item) => [item.tag_id || item.name, item]))
}

const liveAbnormalIndicatorMap = computed(() => buildIndicatorDetailMap(filteredLiveAbnormalIndicators.value))
const resultAbnormalIndicatorMap = computed(() => buildIndicatorDetailMap(filteredResultAbnormalIndicators.value))
const monitorDataItems = computed(() => currentData.value.map((item) => {
  const detail = liveAbnormalIndicatorMap.value.get(item.tag_id || item.name)
  if (!detail) return item
  return { ...item, ...detail, current_value: detail.current_value ?? item.current_value, state_desc: detail.level || detail.state_desc || item.state_desc }
}))
const monitorAbnormalIndicators = computed(() => {
  if (currentData.value.length) return filteredLiveAbnormalIndicators.value
  if (filteredResultAbnormalIndicators.value.length) return filteredResultAbnormalIndicators.value
  return filteredLiveAbnormalIndicators.value
})
const monitorOverviewResult = computed(() => ({
  data_overview: currentSession.value.monitorDataOverview || {},
  overall_judgement: currentSession.value.monitorOverallJudgement || {},
  semantic_summary: currentSession.value.monitorSemanticSummary || {},
  visualization_context: currentSession.value.monitorVisualizationContext || {},
}))
const monitorOverviewAvailable = computed(() => {
  const monitorResult = monitorOverviewResult.value || {}
  const curveGroups = monitorResult.visualization_context?.data_curve_overview?.categories
  if (Array.isArray(curveGroups) && curveGroups.length) return true
  const overall = monitorResult.overall_judgement || {}
  return Boolean(Object.keys(overall).length)
})
const abnormalCount = computed(() => (currentData.value.length ? monitorAbnormalIndicators.value.length : filteredResultAbnormalIndicators.value.length))
const systemStatusText = computed(() => (currentSession.value.isRunning ? '运行中' : lastError.value ? '失败' : result.value.reasoning_result ? '已完成' : '空闲'))
const llmWorking = computed(() => getSessionActiveLlmTasks(currentSession.value).length > 0)
const currentLlmTaskLabel = computed(() => {
  const tasks = getSessionActiveLlmTasks(currentSession.value)
  if (!tasks.length) return currentSession.value.lastLlmTaskLabel || '模型推理'
  const latestTask = tasks.sort((left, right) => (right.startedAt || 0) - (left.startedAt || 0))[0]
  return latestTask?.taskLabel || currentSession.value.lastLlmTaskLabel || '模型推理'
})
const liveStageText = computed(() => ({
  idle: '等待任务',
  submitted: '任务已提交',
  semantic_ready: '语义分析完成，监控已刷新',
  decision_ready: '决策建议已生成，监控已刷新',
  result_ready: '最终结果已返回',
}[liveStage.value] || liveStage.value))
const hasReadyReport = computed(() => Boolean(result.value.reasoning_result || result.value.report_md || result.value.report_pdf))
const reportFileName = computed(() => (result.value.report_md || result.value.report_pdf || '').split(/[\\/]/).pop() || '尚未生成')
const activeWorkspaceMeta = computed(() => ({
  config: { title: '系统配置', description: '通过设置管理模型接入方式、预设与推理参数。' },
  monitor: { title: '实时监控', description: `查看当前会话“${currentSession.value.title}”的指标快照、异常摘要与阶段状态。` },
  report: { title: '分析报告', description: `查看当前会话“${currentSession.value.title}”的原因分析、决策建议和报告路径。` },
}[workspaceView.value]))

const formatClock = (value) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const getSessionStatusText = (session) => (session.isRunning ? '进行中' : session.lastError ? '失败' : session.result.reasoning_result ? '已完成' : '待开始')
const getSessionStatusTone = (session) => (session.isRunning ? 'running' : session.lastError ? 'error' : session.result.reasoning_result ? 'done' : 'idle')
const getSessionSummary = (session) => (
  session.fileName
  || session.lastError
  || (session.result.report_pdf || session.result.report_md
    ? '已生成原因分析、建议与报告文件'
    : session.streamItems.length
      ? '保留当前任务的日志和交互记录'
      : '空白会话，等待新任务')
)
const sessionCards = computed(() => sessions.value.map((session) => ({
  id: session.id,
  title: session.title,
  statusText: getSessionStatusText(session),
  statusTone: getSessionStatusTone(session),
  summary: getSessionSummary(session),
  updatedLabel: formatClock(session.updatedAt),
})))
const activeActionCard = computed(() => {
  const unresolved = streamItems.value.filter((item) => item.type === 'interaction' && !item.answered)
  if (!unresolved.length) return null
  return unresolved.sort((a, b) => {
    if (a.blocking !== b.blocking) return a.blocking ? -1 : 1
    return compareRiskLevel(b.riskLevel, a.riskLevel)
  })[0]
})
const stepTimelineGroups = computed(() => {
  const session = currentSession.value
  const groups = new Map()
  const stepExpanded = session.stepExpanded || {}
  const currentStepId = normalizeWorkflowStepId(session.workflowStepId)
  const stepStates = session.stepStates || {}

  Object.keys(stepStates).forEach((rawStepId) => {
    const stepId = normalizeWorkflowStepId(rawStepId)
    if (!stepId) return
    const stepState = stepStates[stepId]
    groups.set(stepId, {
      key: String(stepId),
      stepId,
      title: formatWorkflowStepLabel(stepId, stepState?.title || workflowStepTitleMap[stepId]),
      state: stepState?.state || 'pending',
      stateText: stepStateText(stepState?.state || 'pending'),
      startedMs: stepState?.startedMs || 0,
      endedMs: stepState?.endedMs || 0,
      items: [],
      eventCount: 0,
      isCurrent: stepId === currentStepId,
      runtimeText: '已运行 00:00',
      typewriterText: '',
      isExpanded: false,
    })
  })

  streamItems.value.forEach((item) => {
    const stepId = normalizeWorkflowStepId(item.workflowStepId) || currentStepId
    const groupKey = stepId || systemStepGroupKey
    if (!groups.has(groupKey)) {
      if (groupKey === systemStepGroupKey) {
        groups.set(groupKey, {
          key: systemStepGroupKey,
          stepId: null,
          title: '系统消息',
          state: 'running',
          stateText: '进行中',
          startedMs: 0,
          endedMs: 0,
          items: [],
          eventCount: 0,
          isCurrent: !currentStepId,
          runtimeText: '实时',
          typewriterText: '',
          isExpanded: true,
        })
      } else {
        const fallbackState = (session.stepStates || {})[groupKey] || createDefaultStepState(groupKey, item.workflowStepTitle || workflowStepTitleMap[groupKey])
        groups.set(groupKey, {
          key: String(groupKey),
          stepId: groupKey,
          title: formatWorkflowStepLabel(groupKey, fallbackState?.title || workflowStepTitleMap[groupKey]),
          state: fallbackState?.state || 'running',
          stateText: stepStateText(fallbackState?.state || 'running'),
          startedMs: fallbackState?.startedMs || item.timestampMs || Date.now(),
          endedMs: fallbackState?.endedMs || 0,
          items: [],
          eventCount: 0,
          isCurrent: groupKey === currentStepId,
          runtimeText: '已运行 00:00',
          typewriterText: '',
          isExpanded: true,
        })
      }
    }
    const group = groups.get(groupKey)
    group.items.push(item)
    group.eventCount += item.type === 'thinking' ? (item.entries?.length || 1) : 1
  })

  const sortedGroups = Array.from(groups.values()).sort((left, right) => {
    if (left.key === systemStepGroupKey) return 1
    if (right.key === systemStepGroupKey) return -1
    return Number(left.stepId) - Number(right.stepId)
  })

  return sortedGroups.map((group) => {
    const defaultExpanded = group.isCurrent || group.state === 'running' || group.key === systemStepGroupKey
    const manualExpanded = stepExpanded[group.key]
    const isExpanded = typeof manualExpanded === 'boolean' ? manualExpanded : defaultExpanded

    const endMs = group.state === 'running' ? nowTick.value : (group.endedMs || nowTick.value)
    const elapsedSec = group.startedMs ? Math.max(0, Math.floor((endMs - group.startedMs) / 1000)) : 0
    const runtimeText = group.key === systemStepGroupKey ? '实时' : formatDurationText(elapsedSec)

    return {
      ...group,
      isExpanded,
      runtimeText,
      typewriterText: buildStepTypewriterText(group),
    }
  })
})
const currentRiskLevel = computed(() => maxRiskLevel(highestRiskLevel.value, activeActionCard.value?.riskLevel || 'low'))
const currentProgressPercent = computed(() => Number.isFinite(Number(progressPercent.value)) ? Math.max(0, Math.min(100, Number(progressPercent.value))) : 0)
const currentEtaText = computed(() => (currentSession.value.etaSec || currentSession.value.etaSec === 0 ? `预计 ${currentSession.value.etaSec}s` : ''))
const nextActionText = computed(() => activeActionCard.value?.recommendedAction || '等待下一步动作')
const currentWorkflowStep = computed(() => {
  const cardStepId = normalizeWorkflowStepId(activeActionCard.value?.workflowStepId)
  if (cardStepId) {
    return {
      id: cardStepId,
      title: activeActionCard.value?.workflowStepTitle || workflowStepTitleMap[cardStepId] || '',
    }
  }
  const sessionStepId = normalizeWorkflowStepId(currentSession.value.workflowStepId)
  if (sessionStepId) {
    return {
      id: sessionStepId,
      title: currentSession.value.workflowStepTitle || workflowStepTitleMap[sessionStepId] || '',
    }
  }
  return null
})
const currentWorkflowStepText = computed(() => {
  if (!currentWorkflowStep.value) return '未进入步骤'
  return formatWorkflowStepLabel(currentWorkflowStep.value.id, currentWorkflowStep.value.title)
})

function focusStreamPanel() {
  nextTick(() => {
    if (streamScroll.value) streamScroll.value.scrollTop = 0
  })
}

function focusActionCard() {
  nextTick(() => {
    actionCardRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}

function toggleStepGroup(group) {
  const session = currentSession.value
  if (!session) return
  const groupKey = group?.key
  if (!groupKey) return
  if (!session.stepExpanded || typeof session.stepExpanded !== 'object') session.stepExpanded = {}
  session.stepExpanded[groupKey] = !group.isExpanded
  touchSession()
}

function toggleThinkingExpanded(item) {
  if (!item || item.type !== 'thinking') return
  item.isExpanded = !item.isExpanded
}

function openThinkingDetail(item, group = null) {
  if (!item || item.type !== 'thinking') return
  thinkingDetailState.item = item
  thinkingDetailState.groupTitle = group?.title || ''
  thinkingDetailState.stepLabel = item.workflowStepId ? formatWorkflowStepLabel(item.workflowStepId, item.workflowStepTitle) : ''
  thinkingDetailOpen.value = true
}

function createSessionAndSwitch() {
  if (hasRunningSession.value && !currentSession.value.isRunning) {
    ElMessage.warning('当前已有任务在运行，请等待完成后再创建并执行新会话。')
    return
  }
  const session = createSession()
  sessions.value.unshift(session)
  currentSessionId.value = session.id
  activeTab.value = 'monitor'
}

function selectSession(id) {
  currentSessionId.value = id
}

function switchWorkspace(tab) {
  activeTab.value = tab
}

function switchWorkspaceFromRailTab(tab) {
  switchWorkspaceFromRail(tab, switchWorkspace)
}

function toggleSettingsPanel() {
  const next = !settingsOpen.value
  settingsOpen.value = next
  if (next) settingsSection.value = 'access'
}

function getThinkingBubble(sessionId = currentSessionId.value, phase = null, workflowStepId = null) {
  const session = getSessionById(sessionId)
  if (!session) return null
  const normalizedStepId = normalizeWorkflowStepId(workflowStepId)
  for (let index = session.streamItems.length - 1; index >= 0; index -= 1) {
    const item = session.streamItems[index]
    if (item?.type !== 'thinking' || item.role !== 'ai') continue
    if (phase && item.phase && item.phase !== phase) continue
    if (normalizedStepId && normalizeWorkflowStepId(item.workflowStepId) !== normalizedStepId) continue
    return item
  }
  return null
}

function createThinkingBubble(
  sessionId = currentSessionId.value,
  phase = currentSession.value.currentPhase || 'system',
  workflowStepId = normalizeWorkflowStepId(currentSession.value.workflowStepId),
  workflowStepTitle = '',
) {
  const session = getSessionById(sessionId)
  if (!session) return null
  const nowMs = Date.now()
  const normalizedStepId = normalizeWorkflowStepId(workflowStepId)
  const bubble = {
    role: 'ai',
    type: 'thinking',
    level: 'info',
    phase,
    time: formatClock(nowMs),
    summary: '过程消息已合并',
    entries: [],
    pending: true,
    isExpanded: false,
    pendingUntil: nowMs + thinkingMinPendingMs,
    timestampMs: nowMs,
    workflowStepId: normalizedStepId,
    workflowStepTitle: workflowStepTitle || (normalizedStepId ? workflowStepTitleMap[normalizedStepId] : ''),
  }
  session.streamItems.push(bubble)
  return bubble
}

function clearThinkingSettleTimer(sessionId = currentSessionId.value) {
  const timerId = thinkingSettleTimers.get(sessionId)
  if (!timerId) return
  window.clearTimeout(timerId)
  thinkingSettleTimers.delete(sessionId)
}

function getLlmTaskTimerKey(sessionId, eventId) {
  return `${sessionId}:${eventId}`
}

function clearLlmTaskSettleTimer(sessionId, eventId) {
  const timerKey = getLlmTaskTimerKey(sessionId, eventId)
  const timerId = llmTaskSettleTimers.get(timerKey)
  if (!timerId) return
  window.clearTimeout(timerId)
  llmTaskSettleTimers.delete(timerKey)
}

function clearLlmTaskSettleTimersForSession(sessionId) {
  for (const [timerKey, timerId] of llmTaskSettleTimers.entries()) {
    if (!timerKey.startsWith(`${sessionId}:`)) continue
    window.clearTimeout(timerId)
    llmTaskSettleTimers.delete(timerKey)
  }
}

function getSessionActiveLlmTasks(session) {
  return Object.values(session?.activeLlmTasks || {})
}

function markThinkingPending(sessionId, phase = 'analysis', workflowStepId = null, workflowStepTitle = '') {
  const bubble = getThinkingBubble(sessionId, phase, workflowStepId) || createThinkingBubble(sessionId, phase, workflowStepId, workflowStepTitle)
  if (!bubble) return
  clearThinkingSettleTimer(sessionId)
  bubble.pending = true
  bubble.pendingUntil = Date.now() + thinkingMinPendingMs
}

function clearLlmTaskState(sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return
  clearLlmTaskSettleTimersForSession(sessionId)
  session.activeLlmTasks = {}
  touchSession(sessionId)
}

function applyLlmActivity(payload = {}, sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return
  const eventId = `${payload.event_id || ''}`.trim()
  if (!eventId) return
  const status = `${payload.status || ''}`.toLowerCase()
  const taskLabel = `${payload.task_label || ''}`.trim() || '模型推理'
  const phase = payload.phase || session.currentPhase || 'analysis'
  const workflowStepId = normalizeWorkflowStepId(payload.workflow_step_id)
  const workflowStepTitle = payload.workflow_step_title || (workflowStepId ? workflowStepTitleMap[workflowStepId] : '')

  if (status === 'started') {
    clearLlmTaskSettleTimer(sessionId, eventId)
    if (workflowStepId) {
      session.workflowStepId = workflowStepId
      session.workflowStepTitle = workflowStepTitle || workflowStepTitleMap[workflowStepId] || ''
      upsertSessionStepState(session, workflowStepId, {
        state: 'started',
        title: workflowStepTitle,
        phase,
        startedAt: payload.timestamp || new Date().toISOString(),
      })
    }
    session.activeLlmTasks = {
      ...(session.activeLlmTasks || {}),
      [eventId]: {
        eventId,
        taskKey: payload.task_key || '',
        taskLabel,
        status,
        phase,
        provider: payload.provider || '',
        model: payload.model || '',
        workflowStepId,
        workflowStepTitle,
        startedAt: Date.now(),
      },
    }
    session.lastLlmTaskLabel = taskLabel
    markThinkingPending(sessionId, phase, workflowStepId, workflowStepTitle)
    touchSession(sessionId)
    return
  }

  if (status !== 'completed' && status !== 'failed') return
  const currentTask = session.activeLlmTasks?.[eventId]
  session.lastLlmTaskLabel = taskLabel
  if (!currentTask) {
    if (!getSessionActiveLlmTasks(session).length) window.setTimeout(() => settleThinkingBubble(sessionId), llmSettleDelayMs)
    touchSession(sessionId)
    return
  }

  const elapsed = Date.now() - (currentTask.startedAt || Date.now())
  const delay = Math.max(llmMinVisibleMs - elapsed, 0)
  const timerKey = getLlmTaskTimerKey(sessionId, eventId)
  clearLlmTaskSettleTimer(sessionId, eventId)
  const timerId = window.setTimeout(() => {
    const targetSession = getSessionById(sessionId)
    if (!targetSession) {
      llmTaskSettleTimers.delete(timerKey)
      return
    }
    if (!targetSession.activeLlmTasks?.[eventId]) {
      llmTaskSettleTimers.delete(timerKey)
      return
    }
    const nextTasks = { ...(targetSession.activeLlmTasks || {}) }
    delete nextTasks[eventId]
    targetSession.activeLlmTasks = nextTasks
    if (!getSessionActiveLlmTasks(targetSession).length) {
      window.setTimeout(() => {
        if (!getSessionActiveLlmTasks(getSessionById(sessionId) || {}).length) settleThinkingBubble(sessionId)
      }, llmSettleDelayMs)
    }
    touchSession(sessionId)
    llmTaskSettleTimers.delete(timerKey)
  }, delay)
  llmTaskSettleTimers.set(timerKey, timerId)
}

function appendThinkingEntry(
  text,
  sessionId = currentSessionId.value,
  {
    pending = true,
    phase = currentSession.value.currentPhase || 'system',
    expand = false,
    workflowStepId = normalizeWorkflowStepId(currentSession.value.workflowStepId),
    workflowStepTitle = '',
  } = {},
) {
  const session = getSessionById(sessionId)
  if (!session || !text) return
  const normalizedStepId = normalizeWorkflowStepId(workflowStepId)
  const bubble = getThinkingBubble(sessionId, phase, normalizedStepId) || createThinkingBubble(sessionId, phase, normalizedStepId, workflowStepTitle)
  if (!bubble) return
  const nowMs = Date.now()
  const latestEntry = bubble.entries[bubble.entries.length - 1]
  if (normalizedStepId && !bubble.workflowStepId) bubble.workflowStepId = normalizedStepId
  if (workflowStepTitle && !bubble.workflowStepTitle) bubble.workflowStepTitle = workflowStepTitle
  clearThinkingSettleTimer(sessionId)
  if (
    latestEntry
    && latestEntry.rawText === text
    && (nowMs - (latestEntry.timestampMs || 0)) <= 3000
  ) {
    const repeat = (latestEntry.repeat || 1) + 1
    latestEntry.repeat = repeat
    latestEntry.timestampMs = nowMs
    latestEntry.time = formatClock(nowMs)
    latestEntry.text = `${latestEntry.rawText}（x${repeat}）`
  } else {
    bubble.entries.push({
      text,
      rawText: text,
      repeat: 1,
      timestampMs: nowMs,
      time: formatClock(nowMs),
    })
  }
  const lastEntry = bubble.entries[bubble.entries.length - 1]
  bubble.time = lastEntry?.time || formatClock(nowMs)
  bubble.timestampMs = nowMs
  const mergedCount = bubble.entries.reduce((sum, entry) => sum + (entry.repeat || 1), 0)
  bubble.summary = `阶段过程摘要（${mergedCount}）`
  if (expand) bubble.isExpanded = true
  if (pending) {
    bubble.pending = true
    bubble.pendingUntil = Date.now() + thinkingMinPendingMs
    return
  }
  settleThinkingBubble(sessionId)
}

function settleThinkingBubble(sessionId = currentSessionId.value) {
  const bubble = getThinkingBubble(sessionId)
  if (!bubble) return

  clearThinkingSettleTimer(sessionId)
  const remaining = Math.max((bubble.pendingUntil || 0) - Date.now(), 0)
  if (remaining <= 0) {
    bubble.pending = false
    bubble.pendingUntil = 0
    return
  }

  const timerId = window.setTimeout(() => {
    bubble.pending = false
    bubble.pendingUntil = 0
    thinkingSettleTimers.delete(sessionId)
  }, remaining)
  thinkingSettleTimers.set(sessionId, timerId)
}

function pushStreamItem(item, sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return
  const nowMs = Date.now()
  const itemStepId = normalizeWorkflowStepId(item.workflowStepId || item.workflow_step_id) || normalizeWorkflowStepId(session.workflowStepId)
  const normalizedItem = {
    ...item,
    role: item.role || 'ai',
    phase: item.phase || session.currentPhase || 'system',
    riskLevel: normalizeRiskLevel(item.riskLevel || item.risk_level || 'low'),
    workflowStepId: itemStepId,
    workflowStepTitle: item.workflowStepTitle || item.workflow_step_title || (itemStepId ? workflowStepTitleMap[itemStepId] : ''),
    rawText: item.rawText || item.text || '',
    time: formatClock(nowMs),
    timestampMs: nowMs,
  }
  if (normalizedItem.workflowStepId) {
    session.workflowStepId = normalizedItem.workflowStepId
    session.workflowStepTitle = normalizedItem.workflowStepTitle || workflowStepTitleMap[normalizedItem.workflowStepId] || ''
    if (!session.stepStates?.[normalizedItem.workflowStepId] && session.isRunning) {
      upsertSessionStepState(session, normalizedItem.workflowStepId, {
        state: 'started',
        title: normalizedItem.workflowStepTitle,
        phase: normalizedItem.phase,
        startedAt: new Date(nowMs).toISOString(),
      })
    }
  }

  if (normalizedItem.type === 'text' && normalizedItem.role === 'ai' && normalizedItem.level === 'info' && session.isRunning) {
    appendThinkingEntry(normalizedItem.text, sessionId, {
      pending: true,
      phase: normalizedItem.phase,
      workflowStepId: normalizedItem.workflowStepId,
      workflowStepTitle: normalizedItem.workflowStepTitle,
    })
  } else {
    const lastItem = session.streamItems[session.streamItems.length - 1]
    if (
      normalizedItem.type === 'text'
      && normalizedItem.role === 'ai'
      && lastItem
      && lastItem.type === 'text'
      && lastItem.role === 'ai'
      && (lastItem.rawText || lastItem.text) === (normalizedItem.rawText || normalizedItem.text)
      && normalizeWorkflowStepId(lastItem.workflowStepId) === normalizeWorkflowStepId(normalizedItem.workflowStepId)
      && (nowMs - (lastItem.timestampMs || 0)) <= 3000
    ) {
      const repeat = (lastItem.repeat || 1) + 1
      lastItem.repeat = repeat
      lastItem.timestampMs = nowMs
      lastItem.time = normalizedItem.time
      lastItem.text = `${normalizedItem.rawText || normalizedItem.text}（x${repeat}）`
      touchSession(sessionId)
      return
    }
    if ((normalizedItem.role === 'user' || normalizedItem.level === 'success' || normalizedItem.level === 'error') && !getSessionActiveLlmTasks(session).length) {
      settleThinkingBubble(sessionId)
    }
    if (normalizedItem.riskLevel && compareRiskLevel(normalizedItem.riskLevel, session.highestRiskLevel) > 0) session.highestRiskLevel = normalizedItem.riskLevel
    if (normalizedItem.type === 'interaction' && compareRiskLevel(normalizedItem.riskLevel, 'high') >= 0) {
      const bubble = getThinkingBubble(sessionId, normalizedItem.phase, normalizedItem.workflowStepId)
      if (bubble) bubble.isExpanded = true
    }
    if (normalizedItem.level === 'warning' || normalizedItem.level === 'error') {
      const bubble = getThinkingBubble(sessionId, normalizedItem.phase, normalizedItem.workflowStepId)
      if (bubble) bubble.isExpanded = true
    }
    session.streamItems.push(normalizedItem)
  }
  touchSession(sessionId)
  if (sessionId === currentSessionId.value) {
    nextTick(() => {
      if (streamScroll.value) streamScroll.value.scrollTop = streamScroll.value.scrollHeight
    })
  }
}

marked.setOptions({ gfm: true, breaks: true })

function normalizeReportLinks(text = '') {
  if (!text) return ''
  const plainUrlPattern = /https?:\/\/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+/g
  return text.replace(plainUrlPattern, (url) => `<${url}>`)
}

function normalizeReportText(text = '') {
  if (!text) return ''
  // Keep report markdown readable without aggressive structural rewrites.
  const compact = text.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
  return normalizeReportLinks(compact)
}
const renderMarkdown = (text) => (text ? marked.parse(text) : '')
const renderReportMarkdown = (text) => (text ? marked.parse(normalizeReportText(text)) : '')
const getThinkingPreview = (item) => (item?.isExpanded ? item.entries : item.entries.slice(-thinkingPreviewLimit))
const thinkingDetailEntries = computed(() => Array.isArray(thinkingDetailState.item?.entries) ? thinkingDetailState.item.entries : [])
const thinkingDetailEntryCount = computed(() => thinkingDetailEntries.value.length)
const formatNumber = (value) => (typeof value === 'number' ? value.toFixed(2) : value ?? '-')
function getDiffPercentValue(item = {}) {
  const diff = Number(item.diff)
  if (!Number.isFinite(diff)) return null

  const current = Number(item.current_value)
  const baseline = current - diff
  let percentBase = baseline
  if (!Number.isFinite(percentBase) || Math.abs(percentBase) < 1e-6) percentBase = current
  if (!Number.isFinite(percentBase) || Math.abs(percentBase) < 1e-6) return null

  return (diff / percentBase) * 100
}

const formatPercent = (value) => (Number.isFinite(value) ? ((value >= 0 ? '+' : '') + Number(value).toFixed(1) + '%') : '-')

function formatDiffSummary(item = {}) {
  const diff = Number(item.diff)
  if (!Number.isFinite(diff)) return '-'
  const percent = getDiffPercentValue(item)
  if (percent == null) return String(formatNumber(diff))
  return String(formatNumber(diff)) + ' (' + (percent >= 0 ? '+' : '') + Number(percent).toFixed(1) + '%)'
}
function formatWindowSummary(item = {}) {
  const windowInfo = item.window || {}
  const start = windowInfo.start
  const end = windowInfo.end
  if (!start || !end) return '时间窗口未识别'
  return windowInfo.is_ongoing ? `${start} 至当前快照` : `${start} 至 ${end}`
}

function formatCurrentSnapshot(item = {}) {
  return item.snapshot_timestamp || result.value.data_overview?.latest_timestamp || '未记录'
}

function isAbnormalState(stateDesc = '') {
  return ['异常', '较差', '差', '偏差较大', '偏离显著', '偏高', '偏低', '严重偏高', '严重偏低'].includes(stateDesc)
}

const getDataStateClass = (item) => {
  if (isAbnormalState(item.state_desc)) return 'abnormal'
  if (item.state_desc === '一般') return 'warning'
  return 'normal'
}
function getIndicatorTone(indicator = {}) {
  const levelText = `${indicator.level || indicator.status || indicator.state_desc || ''}`.trim().toLowerCase()
  if (!levelText) return 'info'

  const positiveWords = ['优秀', '良好', '正常', '稳定', '健康', '安全', 'ok', 'good', 'excellent', 'normal']
  const dangerWords = ['异常', '告警', '报警', '高', '偏高', '过高', '低', '偏低', '过低', '严重', '风险', '危险', 'critical', 'high', 'low', 'error']
  const warningWords = ['关注', '提醒', '波动', '一般', '轻微', 'warning', 'medium']

  if (positiveWords.some((word) => levelText.includes(word))) return 'ok'
  if (dangerWords.some((word) => levelText.includes(word))) return 'danger'
  if (warningWords.some((word) => levelText.includes(word))) return 'warn'
  return 'info'
}
function classifyMonitorMetric(item = {}) {
  const normalizedName = `${item.name || ''}`.replace(/\s+/g, '')
  const normalizedTag = `${item.tag || ''}`.replace(/\s+/g, '')
  const priorityKeys = ['load', 'extraction', 'loss_energy', 'cooling_capacity']
  const matchesGroup = (group, haystack) => group.keywords.some((keyword) => haystack.includes(keyword.replace(/\s+/g, '')))

  for (const key of priorityKeys) {
    const group = preferredMonitorCategoryMeta.find((entry) => entry.key === key)
    if (group && matchesGroup(group, normalizedName)) return group.key
  }
  for (const key of priorityKeys) {
    const group = preferredMonitorCategoryMeta.find((entry) => entry.key === key)
    if (group && matchesGroup(group, normalizedTag)) return group.key
  }
  return 'other'
}

function buildMonitorGroup(meta) {
  const items = monitorDataItems.value.filter((item) => classifyMonitorMetric(item) === meta.key)
  const abnormalCount = items.filter((item) => getDataStateClass(item) === 'abnormal').length
  const percents = items.map((item) => getDiffPercentValue(item)).filter((value) => Number.isFinite(value))
  const avgPercent = percents.length ? percents.reduce((sum, value) => sum + Math.abs(value), 0) / percents.length : null

  return {
    ...meta,
    items,
    abnormalCount,
    avgPercent,
    avgPercentText: avgPercent == null ? '偏差待计算' : `平均偏差 ${avgPercent.toFixed(1)}%`,
  }
}

const monitorGroups = computed(() => preferredMonitorCategoryMeta.map((meta) => buildMonitorGroup(meta)).filter((group) => group.items.length))
const monitorVisualItems = computed(() => {
  const items = monitorDataItems.value
    .map((item) => {
      const percent = getDiffPercentValue(item)
      const baselineValue = Number(item.current_value) - Number(item.diff || 0)
      return {
        ...item,
        percent,
        percentText: formatPercent(percent),
        baselineValue: Number.isFinite(baselineValue) ? baselineValue : null,
      }
    })
    .filter((item) => Number.isFinite(item.percent))
    .sort((a, b) => Math.abs(b.percent) - Math.abs(a.percent))
    .slice(0, 8)

  const maxAbsPercent = Math.max(...items.map((item) => Math.abs(item.percent)), 1)

  return items.map((item) => ({
    ...item,
    barWidth: `${Math.max((Math.abs(item.percent) / maxAbsPercent) * 100, 10)}%`,
    tone: item.percent >= 0 ? 'up' : 'down',
  }))
})

function getPreferredDirectConfig() {
  const customConfig = llmConfigs.value.find((item) => item.id !== 'system_default' && item.base_url && (item.api_key_full || item.api_key) && item.model)
  if (customConfig) return customConfig
  return llmConfigs.value.find((item) => item.id === 'system_default') || llmConfigs.value.find((item) => item.base_url && (item.api_key_full || item.api_key) && item.model) || null
}

function dedupeConfigs(items = []) {
  const seen = new Set()
  return items.filter((item) => {
    const key = item.id || `${item.name}-${item.base_url}-${item.model}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function readCachedConfigs() {
  try {
    const raw = window.localStorage.getItem(llmConfigCacheKey)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeCachedConfigs(items = []) {
  try {
    window.localStorage.setItem(llmConfigCacheKey, JSON.stringify(items))
  } catch {
    // ignore local cache failures
  }
}

function applyDirectConfig(item) {
  if (!item) return
  selectedConfigId.value = item.id
  config.llmUrl = item.base_url || ''
  config.llmKey = item.api_key_full || item.api_key || ''
  config.llmModel = item.model || ''
}

function ensureDirectConfigSelected() {
  if (config.mode === 'direct' && (!config.llmUrl.trim() || !config.llmKey.trim() || !config.llmModel.trim())) {
    applyDirectConfig(getPreferredDirectConfig())
  }
}

function applyConfigList(items = []) {
  llmConfigs.value = dedupeConfigs(items)
  ensureDirectConfigSelected()
}

function getFallbackConfigList() {
  return dedupeConfigs([...fallbackLlmConfigs, ...readCachedConfigs()])
}

function resetRunState(sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return
  clearThinkingSettleTimer(sessionId)
  clearLlmTaskState(sessionId)
  session.streamItems = []
  session.lastError = ''
  session.result = {}
  session.currentData = []
  session.liveAbnormalIndicators = []
  session.monitorVisualizationContext = {}
  session.monitorOverallJudgement = {}
  session.monitorSemanticSummary = {}
  session.monitorDataOverview = {}
  session.monitorUpdatedAt = ''
  session.liveStage = 'idle'
  session.currentPhase = 'system'
  session.stepStates = {}
  session.stepExpanded = {}
  session.workflowStepId = null
  session.workflowStepTitle = ''
  session.activeLlmTasks = {}
  session.lastLlmTaskLabel = ''
  session.progressPercent = 0
  session.etaSec = null
  session.highestRiskLevel = 'low'
  session.isRunning = false
  session.phases = createPhases()
  session.uxMarks = { taskStartedAt: null, keyActionCardRendered: false, finishedLogged: false }
  touchSession(sessionId)
}

function updateMonitorSnapshot(payload = {}, sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return
  session.currentData = payload.semantic_data || session.currentData
  session.liveAbnormalIndicators = filterAbnormalIndicators(payload.abnormal_indicators || session.liveAbnormalIndicators)
  session.monitorVisualizationContext = payload.visualization_context || session.monitorVisualizationContext || {}
  session.monitorOverallJudgement = payload.overall_judgement || session.monitorOverallJudgement || {}
  session.monitorSemanticSummary = payload.semantic_summary || session.monitorSemanticSummary || {}
  session.monitorDataOverview = payload.data_overview || session.monitorDataOverview || {}
  const highest = session.liveAbnormalIndicators.reduce((acc, item) => maxRiskLevel(acc, normalizeRiskLevel(item.level || item.state_desc || 'low')), session.highestRiskLevel || 'low')
  session.highestRiskLevel = highest
  if (payload.stage) session.liveStage = payload.stage
  session.monitorUpdatedAt = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  touchSession(sessionId)
}

function clearFilePickerFocusListener() {
  if (!filePickerFocusHandler) return
  window.removeEventListener('focus', filePickerFocusHandler)
  filePickerFocusHandler = null
}

function releaseFilePickerLock(delay = 0) {
  clearFilePickerFocusListener()
  if (filePickerUnlockTimer) window.clearTimeout(filePickerUnlockTimer)
  if (filePickerWatchdogTimer) {
    window.clearTimeout(filePickerWatchdogTimer)
    filePickerWatchdogTimer = 0
  }
  filePickerUnlockTimer = window.setTimeout(() => {
    isPickingFile.value = false
    filePickerUnlockTimer = 0
  }, delay)
}

async function fetchSampleFiles({ force = false, sessionId = currentSessionId.value } = {}) {
  const session = getSessionById(sessionId)
  if (!session) return []
  if (session.samplesLoading) return session.sampleFiles || []
  if (!force && Array.isArray(session.sampleFiles) && session.sampleFiles.length) return session.sampleFiles

  session.samplesLoading = true
  session.samplesError = ''
  touchSession(sessionId)
  try {
    const response = await fetch(`${apiBaseUrl}/samples`, { cache: 'no-store' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data?.success) throw new Error(data?.error || '加载示例列表失败。')
    session.sampleFiles = Array.isArray(data.data) ? data.data : []
    if (!session.sampleFiles.length) {
      session.samplesError = '示例库暂无可用 Excel 文件。'
    }
    return session.sampleFiles
  } catch (error) {
    session.sampleFiles = []
    session.samplesError = error?.message || '加载示例列表失败。'
    return []
  } finally {
    session.samplesLoading = false
    touchSession(sessionId)
  }
}

function clearSelectedSample() {
  selectedSamplePath.value = ''
  selectedSampleName.value = ''
  samplesError.value = ''
}

function clearUploadedFile() {
  fileName.value = ''
  fileData.value = null
}

async function handleChooseDataSource(command) {
  if (command === 'upload') {
    dataSource.value = 'upload'
    clearSelectedSample()
    clearUploadedFile()
    await nextTick()
    openFilePicker()
    return
  }

  if (command === 'sample') {
    dataSource.value = 'sample'
    clearUploadedFile()
    clearSelectedSample()
    await fetchSampleFiles()
  }
}

async function refreshSampleFiles() {
  await fetchSampleFiles({ force: true })
}

function updateTaskNote(value) {
  taskNote.value = value
}

function handleSampleSelect(path) {
  if (dataSource.value !== 'sample') dataSource.value = 'sample'
  if (!path) {
    clearSelectedSample()
    return
  }

  const selected = (sampleFiles.value || []).find((item) => item.path === path)
  selectedSamplePath.value = path
  selectedSampleName.value = selected?.name || path.split(/[\\/]/).pop() || path
  fileName.value = selectedSampleName.value
  fileData.value = null
  samplesError.value = ''

  if (currentSession.value.title.startsWith('新会话')) {
    currentSession.value.title = selectedSampleName.value.replace(/\.[^.]+$/, '') || currentSession.value.title
  }
}

function handleFileSelect(event) {
  const input = event.target
  const file = input.files?.[0]

  if (!file) {
    releaseFilePickerLock()
    return
  }

  dataSource.value = 'upload'
  clearSelectedSample()
  fileName.value = file.name
  if (currentSession.value.title.startsWith('新会话')) currentSession.value.title = file.name.replace(/\.[^.]+$/, '') || currentSession.value.title

  const reader = new FileReader()
  reader.onload = (loadEvent) => {
    fileData.value = loadEvent.target?.result?.split(',')[1] || null
    pushStreamItem({ type: 'text', text: `已加载数据文件：**${file.name}**`, level: 'success' })
    input.value = ''
    releaseFilePickerLock()
  }
  reader.onerror = () => {
    input.value = ''
    ElMessage.error('读取数据文件失败，请重试。')
    releaseFilePickerLock()
  }
  reader.readAsDataURL(file)
}

function openFilePicker() {
  const input = fileInput.value
  if (!input || isPickingFile.value) return

  isPickingFile.value = true
  input.value = ''

  if (filePickerWatchdogTimer) window.clearTimeout(filePickerWatchdogTimer)
  filePickerWatchdogTimer = window.setTimeout(() => {
    releaseFilePickerLock()
  }, 2500)

  clearFilePickerFocusListener()
  filePickerFocusHandler = () => {
    releaseFilePickerLock(180)
  }
  window.addEventListener('focus', filePickerFocusHandler, { once: true })

  try {
    if (typeof input.showPicker === 'function') input.showPicker()
    else input.click()
  } catch {
    try {
      input.click()
    } catch {
      releaseFilePickerLock()
    }
  }
}

function getMessageTargetSessionId() {
  return runningSessionId.value || currentSessionId.value
}

async function reportUxMetric(eventName, sessionId = currentSessionId.value, extra = {}) {
  try {
    await fetch(`${apiBaseUrl}${uxMetricsEndpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_name: eventName,
        session_id: sessionId,
        client_time: new Date().toISOString(),
        ...extra,
      }),
    })
  } catch {
    // metric upload errors should not interrupt workflow
  }
}

function getInteractionActionText(item = {}, value = 'yes') {
  const title = `${item.rawTitle || item.title || ''}`.trim()
  const checkpointKey = `${item.checkpointKey || item.checkpoint_key || ''}`
  if (value === 'no') return checkpointKey.includes('data_range') || title.includes('数据范围') ? '重新选择文件' : '停止任务'
  if (checkpointKey.includes('data_range') || title.includes('数据范围')) return '确认范围并继续'
  if (checkpointKey.includes('overview') || title.includes('工况总览')) return '继续异常复核'
  if (checkpointKey.includes('candidate') || title.includes('异常候选')) return '继续 AI 诊断'
  if (checkpointKey.includes('high_risk') || title.includes('高风险')) return '继续高风险复核'
  return item.recommendedAction || item.recommended_action || '继续分析'
}

function finishSessionRun(sessionId, errorMessage = '') {
  const session = getSessionById(sessionId)
  if (!session) return
  const endIso = new Date().toISOString()
  Object.values(session.stepStates || {}).forEach((step) => {
    if (step?.state !== 'running') return
    step.state = errorMessage ? 'failed' : 'completed'
    step.endedAt = endIso
    step.endedMs = Date.now()
  })
  clearLlmTaskState(sessionId)
  session.isRunning = false
  if (errorMessage) session.lastError = errorMessage
  if (runningSessionId.value === sessionId) runningSessionId.value = null
  settleThinkingBubble(sessionId)
  if (!session.uxMarks?.finishedLogged) {
    session.uxMarks.finishedLogged = true
    reportUxMetric('task_finished', sessionId, {
      status: errorMessage ? 'failed' : 'completed',
      risk_level: session.highestRiskLevel || 'low',
      progress_percent: session.progressPercent || 0,
    })
  }
  touchSession(sessionId)
}

function handleInteraction(interactionItem, value) {
  const sessionId = getMessageTargetSessionId()
  const interactionId = typeof interactionItem === 'string' ? interactionItem : interactionItem?.id
  const item = getSessionById(sessionId)?.streamItems.find((entry) => entry.type === 'interaction' && entry.id === interactionId)
  const actionText = getInteractionActionText(item || interactionItem || {}, value)
  if (item) {
    item.answered = true
    item.answerText = actionText
  }
  if (ws.value?.readyState === WebSocket.OPEN) ws.value.send(JSON.stringify({ type: 'interaction_response', id: interactionId, value }))
  reportUxMetric('interaction_answered', sessionId, {
    interaction_id: interactionId,
    answer: value,
    checkpoint_key: item?.checkpointKey || '',
    risk_level: item?.riskLevel || 'low',
  })
  pushStreamItem({ role: 'user', type: 'text', text: actionText }, sessionId)
  if (value === 'no') finishSessionRun(sessionId)
}

function applyPhaseUpdate(payload = {}, sessionId = currentSessionId.value) {
  const session = getSessionById(sessionId)
  if (!session) return

  const phase = payload.phase || session.currentPhase || 'system'
  const status = payload.status || 'running'
  const stepId = normalizeWorkflowStepId(payload.workflowStepId)
  const stepTitle = payload.workflowStepTitle || (stepId ? workflowStepTitleMap[stepId] : '')
  const stepState = resolvePhaseStepState(payload)
  const stepStartedAt = payload.step_started_at || ''
  const eventTimestamp = payload.timestamp || new Date().toISOString()

  session.currentPhase = phase
  if (Number.isFinite(Number(payload.progress_percent))) session.progressPercent = Number(payload.progress_percent)
  if (Number.isFinite(Number(payload.eta_sec))) session.etaSec = Number(payload.eta_sec)
  if (session.phases[phase]) session.phases[phase].status = status
  if (phase === 'init' && status === 'running') session.liveStage = 'submitted'

  if (stepId) {
    session.workflowStepId = stepId
    session.workflowStepTitle = stepTitle || workflowStepTitleMap[stepId] || ''
    if (stepState === 'started') {
      upsertSessionStepState(session, stepId, {
        state: 'started',
        title: stepTitle,
        phase,
        startedAt: stepStartedAt || eventTimestamp,
      })
    } else if (stepState === 'completed' || stepState === 'failed') {
      upsertSessionStepState(session, stepId, {
        state: stepState,
        title: stepTitle,
        phase,
        startedAt: stepStartedAt,
        endedAt: eventTimestamp,
      })
    } else if (!session.stepStates?.[stepId] && status === 'running') {
      upsertSessionStepState(session, stepId, {
        state: 'started',
        title: stepTitle,
        phase,
        startedAt: stepStartedAt || eventTimestamp,
      })
    }
  }

  if (status === 'error') {
    const errorText = stepId ? `${formatWorkflowStepLabel(stepId, stepTitle)} 执行异常` : '阶段执行异常'
    pushStreamItem({
      type: 'text',
      text: errorText,
      level: 'error',
      phase,
      workflowStepId: stepId,
      workflowStepTitle: stepTitle,
    }, sessionId)
  } else {
    touchSession(sessionId)
  }
}

function normalizeWsEvent(data, session) {
  if (!data?.type || !session) return null

  if (data.type === 'log') {
    const workflowStepId = normalizeWorkflowStepId(data.workflow_step_id) || normalizeWorkflowStepId(session.workflowStepId)
    const workflowStepTitle = data.workflow_step_title || (workflowStepId ? workflowStepTitleMap[workflowStepId] : '')
    const phase = data.phase || session.currentPhase || (workflowStepId ? 'analysis' : 'system')
    return {
      kind: 'stream_item',
      item: {
        type: 'text',
        text: data.message,
        level: data.level || 'info',
        category: data.category || 'system',
        phase,
        workflowStepId,
        workflowStepTitle,
      },
    }
  }

  if (data.type === 'phase_update') {
    const phase = data.phase || session.currentPhase || 'system'
    const workflowStep = resolveWorkflowFromPhaseUpdate(data, session)
    return {
      kind: 'phase_update',
      payload: {
        phase,
        status: data.status || 'running',
        step: data.step,
        progress_percent: data.progress_percent,
        eta_sec: data.eta_sec,
        workflowStepId: workflowStep.id,
        workflowStepTitle: workflowStep.title,
        workflow_step_state: data.workflow_step_state || '',
        step_started_at: data.step_started_at || '',
        timestamp: data.timestamp || '',
      },
    }
  }

  if (data.type === 'interaction') {
    const phase = data.phase || session.currentPhase || 'analysis'
    const riskLevel = normalizeRiskLevel(data.risk_level || 'medium')
    const workflowStep = resolveWorkflowFromInteraction(data, session)
    if (workflowStep.id) {
      session.workflowStepId = workflowStep.id
      session.workflowStepTitle = workflowStep.title || workflowStepTitleMap[workflowStep.id] || ''
    }
    const rawTitle = data.title || '人工确认'
    const displayTitle = workflowStep.id ? `[步骤 ${workflowStep.id}/8] ${rawTitle}` : rawTitle
    return {
      kind: 'stream_item',
      item: {
        type: 'interaction',
        id: data.id,
        title: displayTitle,
        rawTitle,
        desc: data.desc,
        phase,
        checkpointKey: data.checkpoint_key || '',
        impactScope: Array.isArray(data.impact_scope) ? data.impact_scope : [],
        recommendedAction: data.recommended_action || getInteractionActionText({ title: rawTitle }, 'yes'),
        blocking: data.blocking !== false,
        riskLevel,
        answered: false,
        workflowStepId: workflowStep.id,
        workflowStepTitle: workflowStep.title,
      },
    }
  }

  if (data.type === 'llm_activity') {
    return {
      kind: 'llm_activity',
      payload: {
        event_id: data.event_id,
        task_key: data.task_key || '',
        task_label: data.task_label || '',
        status: data.status || '',
        phase: data.phase || session.currentPhase || 'analysis',
        provider: data.provider || '',
        model: data.model || '',
        workflow_step_id: data.workflow_step_id,
        workflow_step_title: data.workflow_step_title || '',
        message: data.message || '',
      },
    }
  }

  return { kind: data.type, payload: data }
}

function handleWsMessage(data) {
  const sessionId = getMessageTargetSessionId()
  const session = getSessionById(sessionId)
  if (!session) return

  const normalized = normalizeWsEvent(data, session)
  if (!normalized) return

  if (normalized.kind === 'llm_activity') {
    applyLlmActivity(normalized.payload, sessionId)
    return
  }

  if (normalized.kind === 'phase_update') {
    applyPhaseUpdate(normalized.payload, sessionId)
    if (normalized.payload.status === 'error') finishSessionRun(sessionId, '阶段执行失败')
    return
  }

  if (normalized.kind === 'stream_item') {
    pushStreamItem(normalized.item, sessionId)
    if (data.type === 'log' && data.level === 'error') {
      finishSessionRun(sessionId, data.message)
      ElMessage.error(data.message)
    }
    if (data.type === 'interaction') {
      session.highestRiskLevel = maxRiskLevel(session.highestRiskLevel, normalized.item.riskLevel)
      reportUxMetric('interaction_prompt_shown', sessionId, {
        interaction_id: data.id,
        checkpoint_key: normalized.item.checkpointKey,
        risk_level: normalized.item.riskLevel,
      })
    }
    return
  }

  if (data.type === 'monitor_update') {
    updateMonitorSnapshot(data.data, sessionId)
    if (sessionId === currentSessionId.value && activeTab.value !== 'report') switchWorkspace('monitor')
    return
  }

  if (data.type === 'result') {
    session.result = {
      ...data.data,
      abnormal_indicators: filterAbnormalIndicators(data.data.abnormal_indicators || []),
    }
    updateMonitorSnapshot({
      semantic_data: data.data.semantic_data || [],
      abnormal_indicators: data.data.abnormal_indicators || [],
      stage: 'result_ready',
      visualization_context: data.data.visualization_context || {},
      overall_judgement: data.data.overall_judgement || {},
      semantic_summary: data.data.semantic_summary || {},
      data_overview: data.data.data_overview || {},
    }, sessionId)
    session.progressPercent = 100
    session.currentPhase = 'report'
    session.workflowStepId = 8
    session.workflowStepTitle = workflowStepTitleMap[8]
    upsertSessionStepState(session, 8, {
      state: 'completed',
      title: workflowStepTitleMap[8],
      phase: 'report',
      endedAt: new Date().toISOString(),
    })
    finishSessionRun(sessionId)
    if (sessionId === currentSessionId.value) switchWorkspace('report')
    appendThinkingEntry('分析已完成，结果已经返回。', sessionId, { pending: false, phase: 'report' })
  }
}
function connectWebSocket({ reconnect = false } = {}) {
  if (ws.value?.readyState === WebSocket.OPEN) return Promise.resolve(true)
  if (wsConnectPromise) return wsConnectPromise

  wsReconnectEnabled = reconnect
  wsStatus.value = 'connecting'

  wsConnectPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(getWebSocketUrl())
    let settled = false
    const timeoutId = window.setTimeout(() => {
      if (settled) return
      settled = true
      wsConnectPromise = null
      socket.close()
      wsStatus.value = 'disconnected'
      reject(new Error('WebSocket 连接超时'))
    }, 2500)

    ws.value = socket
    socket.onopen = () => {
      if (settled) return
      settled = true
      window.clearTimeout(timeoutId)
      wsConnectPromise = null
      wsStatus.value = 'connected'
      resolve(true)
    }
    socket.onerror = () => {
      if (settled) return
      settled = true
      window.clearTimeout(timeoutId)
      wsConnectPromise = null
      wsStatus.value = 'disconnected'
      reject(new Error('WebSocket 连接失败'))
    }
    socket.onclose = () => {
      window.clearTimeout(timeoutId)
      wsConnectPromise = null
      wsStatus.value = 'disconnected'
      sessions.value.forEach((session) => clearLlmTaskState(session.id))
      if (wsReconnectEnabled) window.setTimeout(() => connectWebSocket({ reconnect: true }).catch(() => {}), 3000)
    }
    socket.onmessage = (event) => handleWsMessage(JSON.parse(event.data))
  })

  return wsConnectPromise
}

function buildPayload(options = {}) {
  const autoConfirm = Boolean(options.autoConfirm)
  const payload = { type: 'start', mode: config.mode, enable_cot: config.enableCoT, auto_confirm: autoConfirm }
  if (dataSource.value === 'upload' && fileData.value) {
    payload.data_source = 'upload'
    payload.file_data = fileData.value
    payload.file_name = fileName.value
  } else if (dataSource.value === 'sample' && selectedSamplePath.value) {
    payload.data_source = 'sample'
    payload.sample_file = selectedSamplePath.value
  }
  if (taskNote.value.trim()) payload.task_note = taskNote.value.trim()
  payload.dify_config = { api_url: config.difyUrl.trim(), api_key: config.difyKey.trim() }
  if (config.mode === 'direct') payload.llm_config = { base_url: config.llmUrl.trim(), api_key: config.llmKey.trim(), model: config.llmModel.trim() }
  return payload
}

async function checkBackendReady() {
  try {
    const response = await fetch(apiHealthUrl, { cache: 'no-store' })
    if (!response.ok) return false
    const data = await response.json()
    return Boolean(data?.success)
  } catch {
    return false
  }
}

async function startAnalysis(options = {}) {
  const autoConfirm = Boolean(options?.autoConfirm)
  if (hasRunningSession.value && runningSessionId.value !== currentSessionId.value) return ElMessage.warning('当前已有其他会话正在执行任务，请等待完成后再启动新任务。')
  if (currentSession.value.isRunning) return
  if (config.mode === 'direct') ensureDirectConfigSelected()
  if (configErrorMessage.value) return ElMessage.error(configErrorMessage.value)
  if (!canStartDataSource.value) return ElMessage.warning('请先选择数据来源并完成文件/示例选择。')
  if (!(await checkBackendReady())) return ElMessage.error('后端服务未启动，请先运行 start_all.bat 或启动后端服务。')

  if (ws.value?.readyState !== WebSocket.OPEN) {
    try {
      await connectWebSocket({ reconnect: true })
    } catch {
      return ElMessage.error('WebSocket 尚未连接，请先启动后端服务。')
    }
  }

  resetRunState(currentSessionId.value)
  currentSession.value.isRunning = true
  currentSession.value.liveStage = 'submitted'
  currentSession.value.currentPhase = 'init'
  currentSession.value.workflowStepId = 1
  currentSession.value.workflowStepTitle = workflowStepTitleMap[1]
  currentSession.value.stepStates = {
    1: {
      ...createDefaultStepState(1, workflowStepTitleMap[1]),
      state: 'running',
      phase: 'init',
      startedAt: new Date().toISOString(),
      startedMs: Date.now(),
    },
  }
  currentSession.value.stepExpanded = {}
  currentSession.value.progressPercent = 1
  currentSession.value.highestRiskLevel = 'low'
  currentSession.value.uxMarks.taskStartedAt = Date.now()
  currentSession.value.uxMarks.keyActionCardRendered = false
  currentSession.value.uxMarks.finishedLogged = false
  runningSessionId.value = currentSessionId.value
  if (!currentSession.value.fileName && currentSession.value.title.startsWith('新会话')) currentSession.value.title = `默认数据任务 ${formatClock(Date.now())}`
  switchWorkspace('monitor')
  if (autoConfirm) {
    pushStreamItem({ type: 'text', text: '已启用快速直出：系统将自动跳过中间确认节点并直接生成结果。', level: 'info' }, currentSessionId.value)
  }
  if (taskNote.value.trim()) pushStreamItem({ role: 'user', type: 'text', text: `任务备注：${taskNote.value.trim()}` }, currentSessionId.value)
  pushStreamItem({ type: 'text', text: '分析任务已提交。', level: 'info' }, currentSessionId.value)
  reportUxMetric('task_started', currentSessionId.value, {
    mode: config.mode,
    auto_confirm: autoConfirm,
    has_file: Boolean(dataSource.value === 'upload' ? fileData.value : selectedSamplePath.value),
    data_source: dataSource.value,
  })
  ws.value.send(JSON.stringify(buildPayload({ autoConfirm })))
}

async function fetchConfigs({ silentFallback = false } = {}) {
  try {
    const response = await fetch(`${apiBaseUrl}/configs`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (!data.success) throw new Error(data.error || '读取模型预设失败。')
    writeCachedConfigs(data.data || [])
    applyConfigList(data.data || [])
  } catch {
    const fallbackConfigs = getFallbackConfigList()
    if (fallbackConfigs.length) {
      applyConfigList(fallbackConfigs)
      if (!silentFallback) ElMessage.warning('模型预设接口不可用，已加载本地预设。')
      return
    }
    ElMessage.error('读取模型预设失败。')
  }
}

function handleConfigChange() {
  applyDirectConfig(llmConfigs.value.find((entry) => entry.id === selectedConfigId.value))
}

function openSaveConfigDialog() {
  dialogVisible.value = true
}

async function confirmSaveConfig() {
  try {
    const response = await fetch(`${apiBaseUrl}/configs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: configForm.name, base_url: config.llmUrl, api_key: config.llmKey, model: config.llmModel }),
    })
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

function refreshConfigs() {
  fetchConfigs({ silentFallback: false })
}

function downloadReport() {
  if (!hasReadyReport.value) {
    ElMessage.warning('报告尚未生成，无法导出。')
    return
  }

  const formalReportPath = result.value.report_pdf || result.value.report_md
  if (formalReportPath) {
    const link = document.createElement('a')
    link.href = `${apiBaseUrl}/reports/download?path=${encodeURIComponent(formalReportPath)}`
    link.download = formalReportPath.split(/[\\/]/).pop() || (result.value.report_pdf ? 'analysis-report.pdf' : 'analysis-report.md')
    link.click()
    return
  }

  const content = [
    '# 分析摘要',
    '',
    '## 任务概览',
    `- 数据文件：${result.value.data_overview?.file_name || '未记录'}`,
    `- 时间点数：${result.value.data_overview?.timepoint_count ?? '-'}`,
    `- 监测点数：${result.value.data_overview?.sensor_count ?? '-'}`,
    `- 有效记录数：${result.value.data_overview?.effective_record_count ?? '-'}`,
    `- 时间范围：${result.value.data_overview?.time_range_start || '未记录'} 至 ${result.value.data_overview?.time_range_end || '未记录'}`,
    '',
    '## 分析步骤',
    ...((result.value.analysis_steps || []).map((step) => `${step.step}. ${step.title}\n${step.summary}`)),
    '',
    '## 原因分析',
    result.value.reasoning_result || '',
    '',
    '## 决策建议',
    result.value.decision_suggestion || result.value.suggestion || '',
    '',
    '## 风险提示',
    result.value.warning || '',
  ].join('\n')
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'analysis-summary.md'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

onMounted(() => {
  const initialConfigs = getFallbackConfigList()
  if (initialConfigs.length) applyConfigList(initialConfigs)
  fetchConfigs({ silentFallback: true })
  nowTickTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, stepTickIntervalMs)
  nextTick(() => {
    initializeWorkspaceLayout()
  })
})

onBeforeUnmount(() => {
  disposeWorkspaceLayout()
  wsReconnectEnabled = false
  if (ws.value?.readyState === WebSocket.OPEN || ws.value?.readyState === WebSocket.CONNECTING) ws.value.close()
  clearFilePickerFocusListener()
  if (filePickerUnlockTimer) window.clearTimeout(filePickerUnlockTimer)
  if (filePickerWatchdogTimer) window.clearTimeout(filePickerWatchdogTimer)
  if (nowTickTimer) {
    window.clearInterval(nowTickTimer)
    nowTickTimer = 0
  }
  thinkingSettleTimers.forEach((timerId) => window.clearTimeout(timerId))
  thinkingSettleTimers.clear()
  llmTaskSettleTimers.forEach((timerId) => window.clearTimeout(timerId))
  llmTaskSettleTimers.clear()
})

watch(() => config.mode, (mode) => {
  if (mode === 'direct') ensureDirectConfigSelected()
}, { immediate: true })

watch(() => activeActionCard.value?.id, (id) => {
  const session = currentSession.value
  if (!id || !session?.isRunning || session.uxMarks?.keyActionCardRendered) return
  session.uxMarks.keyActionCardRendered = true
  reportUxMetric('key_action_card_rendered', currentSessionId.value, {
    interaction_id: id,
    risk_level: activeActionCard.value?.riskLevel || 'low',
  })
})
</script>

<style scoped>
.page-shell{--ui-surface:#fff;--ui-surface-soft:#f8fafc;--ui-surface-tint:#eff6ff;--ui-border:#e5e7eb;--ui-text:#111827;--ui-muted:#6b7280;--ui-primary:#2563eb;--ui-success:#16a34a;--ui-warning:#c2410c;--ui-danger:#dc2626;height:100vh;height:100dvh;display:grid;grid-template-rows:48px minmax(0,1fr);overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.94),rgba(247,248,250,.98));color:var(--ui-text)}
.layout-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 14px;border-bottom:1px solid var(--ui-border);background:rgba(255,255,255,.92)}
.layout-header-title{font-size:18px;font-weight:700}
.layout-header-right,.header-actions{display:flex;align-items:center;gap:12px}
.header-action-btn,.session-create-btn,.inline-action-btn,.ghost-btn,.start-btn,.mode-btn,.workspace-tab{border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface);cursor:pointer}
.header-action-btn{min-height:34px;padding:0 14px;font-size:13px;font-weight:600}
.header-action-btn.primary,.start-btn{background:var(--ui-primary);border-color:var(--ui-primary);color:#fff}
.header-action-btn:disabled,.session-create-btn:disabled,.ghost-btn:disabled,.start-btn:disabled{opacity:.48;cursor:not-allowed}
.header-chip,.header-badge,.workspace-stage,.time-chip{display:inline-flex;align-items:center;gap:8px;min-height:28px;padding:0 10px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface);color:var(--ui-muted);font-size:12px;font-weight:600;white-space:nowrap}
.status-dot{width:10px;height:10px;border-radius:999px;background:#9ca3af}
.status-dot.connected{background:var(--ui-success)}
.status-dot.connecting{background:var(--ui-warning)}
.layout-body{min-height:0;display:grid;grid-template-columns:248px minmax(0,1fr)}
.sidebar{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:18px;padding:20px 16px;border-right:1px solid var(--ui-border);background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.98))}
.sidebar-title{padding-bottom:12px;border-bottom:1px solid var(--ui-border);color:var(--ui-muted);font-size:22px;font-weight:700;line-height:1.2}
.section-kicker,.session-note,.session-item-meta,.session-item-time,.bubble-meta,.bubble-time,.sensor-meta,.file-name,.message-line,.empty-text,.sensor-name,.path-list,.workspace-tab-copy small{color:var(--ui-muted)}
.section-kicker{font-size:12px;font-weight:700}
.session-panel,.session-list{display:grid;gap:10px}
.session-panel-head,.panel-head,.stream-header,.workspace-toolbar,.workspace-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.session-create-btn,.inline-action-btn{min-height:32px;padding:0 12px;color:var(--ui-primary);font-size:12px;font-weight:700}
.session-note,.session-item-meta,.session-item-time,.workspace-tab-copy small{font-size:12px;line-height:1.45}
.session-item{position:relative;width:100%;text-align:left;display:grid;gap:2px;padding:12px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);cursor:pointer}
.session-item:hover{background:var(--ui-surface-tint)}
.session-item.active{border-color:var(--ui-border);background:var(--ui-surface-tint)}
.session-item.active::before{content:'';position:absolute;left:-1px;top:8px;bottom:8px;width:3px;border-radius:999px;background:var(--ui-primary)}
.session-item-top{display:flex;align-items:center;justify-content:space-between;gap:10px}
.session-item-top strong{font-size:14px;line-height:1.25}
.session-status{display:inline-flex;align-items:center;min-height:22px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:700}
.session-status.idle{background:#f3f4f6;color:#6b7280}
.session-status.running{background:#eff6ff;color:var(--ui-primary)}
.session-status.done{background:#f0fdf4;color:var(--ui-success)}
.session-status.error{background:#fef2f2;color:var(--ui-danger)}
.layout-main{box-sizing:border-box;min-width:0;min-height:0;overflow:hidden;padding:10px;background:linear-gradient(rgba(148,163,184,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.08) 1px,transparent 1px);background-size:24px 24px}
.main-grid{width:100%;height:100%;min-height:0;display:grid;grid-template-columns:minmax(0,1.7fr) minmax(330px,.95fr);gap:10px;align-items:stretch;transition:grid-template-columns .2s ease,gap .2s ease}
.stream-panel,.workspace-panel{min-width:0;min-height:0;height:100%;display:flex;flex-direction:column;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);overflow:hidden;position:relative}
.stream-panel::before,.workspace-panel::before{content:'';position:absolute;inset:0 0 auto 0;height:3px;background:linear-gradient(90deg,var(--ui-primary),rgba(37,99,235,.12))}
.workspace-resizer{position:relative;height:100%;cursor:col-resize;touch-action:none;border-radius:999px;outline:none}
.workspace-resizer::before{content:'';position:absolute;left:50%;top:12px;bottom:12px;width:2px;transform:translateX(-50%);border-radius:999px;background:rgba(148,163,184,.45);transition:background .18s ease,box-shadow .18s ease}
.workspace-resizer:hover::before,.workspace-resizer:focus-visible::before,.main-grid.resizing .workspace-resizer::before{background:rgba(37,99,235,.72);box-shadow:0 0 0 4px rgba(37,99,235,.12)}
.stream-header,.workspace-head,.workspace-toolbar{padding:9px 12px;background:linear-gradient(180deg,rgba(239,246,255,.56),rgba(255,255,255,.74))}
.stream-header{border-bottom:1px solid var(--ui-border)}
.workspace-toolbar{border-bottom:1px solid var(--ui-border);align-items:center}
.workspace-head{border-bottom:1px solid var(--ui-border);padding-top:7px;padding-bottom:7px}
.stream-header h1{margin:0;font-size:18px;line-height:1.2}
.workspace-head h2{margin:0;font-size:18px;line-height:1.2}
.stream-header p,.workspace-head p,.panel-head p{margin:3px 0 0;color:var(--ui-muted);line-height:1.35}
.workspace-toolbar-actions{display:flex;align-items:center;gap:8px}
.workspace-collapse-btn{min-height:28px;padding:0 10px}
.workspace-tabs{display:flex;flex:1 1 auto;gap:8px;min-width:0}
.workspace-tab{display:grid;grid-template-columns:28px 1fr;gap:8px;align-items:center;min-width:0;padding:6px 8px;background:rgba(255,255,255,.82);text-align:left}
.workspace-tab.active{border-color:#bfdbfe;background:var(--ui-surface-tint);box-shadow:inset 0 0 0 1px rgba(147,197,253,.3)}
.workspace-tab-index{width:28px;height:28px;display:flex;align-items:center;justify-content:center;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface);color:var(--ui-primary);font-size:11px;font-weight:700}
.workspace-tab-copy{display:grid;gap:2px;min-width:0}
.workspace-tab-copy strong{font-size:13px;line-height:1.15}
.workspace-tab-copy small{font-size:11px;line-height:1.2}
.stream-body,.panel{min-height:0;overflow:auto}
.stream-body{flex:1 1 0;padding:10px 12px 6px}
.message{display:flex;align-items:flex-start;gap:12px;margin-bottom:12px}
.message.user{flex-direction:row-reverse}
.message-main{display:flex;align-items:flex-end;gap:10px;max-width:min(92%,760px)}
.message.user .message-main{flex-direction:row-reverse}
.avatar{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface-tint);color:var(--ui-primary);font-size:12px;font-weight:700}
.message.user .avatar{background:#f0fdf4;color:var(--ui-success)}
.bubble{width:fit-content;max-width:min(100%,660px);padding:10px 12px 9px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);line-height:1.58}
.message.ai .bubble{font-size:13px}
.message.user .bubble{background:var(--ui-surface-tint);border-color:#bfdbfe}
.bubble.info,.bubble.phase,.bubble.intro{background:var(--ui-surface-soft)}
.bubble.success{background:#f0fdf4;border-color:#bbf7d0}
.bubble.error{background:#fef2f2;border-color:#fecaca}
.bubble.interaction{background:var(--ui-surface-tint);border-color:#bfdbfe}
.bubble.thinking{background:linear-gradient(180deg,#f8fbff,#eef6ff);border-color:#c7dcff}
.bubble-title,.section-title,.empty-title{margin-bottom:6px;font-weight:700}
.interaction-meta{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.bubble-actions{display:flex;gap:10px;margin-top:12px}
.bubble-time{flex:0 0 auto;padding-bottom:2px;font-size:11px;line-height:1;color:var(--ui-muted);white-space:nowrap}
.thinking-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.thinking-list{display:grid;gap:8px}
.thinking-overflow{font-size:11px;color:var(--ui-muted)}
.thinking-line{padding:6px 8px;border:1px dashed rgba(37,99,235,.18);border-radius:6px;background:rgba(255,255,255,.58)}
.inline-link-btn{margin-top:8px;border:none;background:none;color:var(--ui-primary);cursor:pointer;font-size:12px;padding:0}
.composer{padding:12px 16px;border-top:1px solid var(--ui-border);background:linear-gradient(180deg,rgba(249,250,251,.96),#fff)}
.composer-row{display:grid;grid-template-columns:120px 1fr 120px;gap:12px;align-items:center}
.composer-note{margin-top:12px}
.composer-note label{margin-top:0}
.ghost-btn,.start-btn{min-height:40px;padding:0 14px;font-weight:600}
.ghost-btn{color:var(--ui-primary)}
.file-name{min-height:40px;display:flex;align-items:center;padding:0 14px;border:1px dashed #cbd5e1;border-radius:6px;background:var(--ui-surface-tint);line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.warning-text{margin-top:10px;color:var(--ui-warning)}
.error-text{margin-top:10px;color:var(--ui-danger)}
.panel{flex:1 1 auto;min-width:0;padding:12px;background:linear-gradient(180deg,rgba(255,255,255,.82),rgba(249,250,251,.9))}
.compact-panel{font-size:13px}
.panel-head{margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--ui-border)}
.panel h3{margin:0;font-size:17px;line-height:1.2}
.mode-row{display:flex;gap:10px;margin-bottom:14px}
.mode-btn{padding:10px 14px;color:var(--ui-muted);font-weight:600}
.mode-btn.active{background:var(--ui-surface-tint);border-color:#bfdbfe;color:var(--ui-primary)}
.preset-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;margin-bottom:14px}
.checkbox-row,label{margin-top:14px}
label{display:block;margin-bottom:8px;color:var(--ui-muted);font-size:12px;font-weight:600}
.kpi-grid,.monitor-layout,.report-layout,.report-main,.report-side,.side-stack,.monitor-bottom-grid,.monitor-overview-stack{display:grid;gap:12px;min-width:0}
.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.monitor-layout{grid-template-columns:1fr;align-content:start}
.monitor-bottom-grid{grid-template-columns:1fr;align-items:start}
.report-layout{grid-template-columns:minmax(0,1fr);align-content:start}
.report-main,.report-side{align-content:start}
.kpi-card,.sensor-card,.state-tag,.panel-section,.panel-empty{border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface)}
.kpi-card{display:flex;flex-direction:column;gap:6px;padding:14px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.kpi-card span{color:var(--ui-muted);font-size:12px;font-weight:600}
.kpi-card strong{font-size:22px;line-height:1.15}
.kpi-card .compact{font-size:14px;line-height:1.45}
.kpi-card.danger,.state-tag.danger,.sensor-card.abnormal{background:#fef2f2;border-color:#fecaca}
.sensor-card.warning{background:#fff7ed;border-color:#fdba74}
.panel-empty,.panel-section{padding:11px}
.section-title{display:flex;align-items:center;gap:8px;font-size:13px}
.section-title::before{content:'';width:4px;height:12px;border-radius:999px;background:var(--ui-primary)}
.section-caption{margin-top:6px;color:var(--ui-muted);font-size:12px;line-height:1.5}
.sensor-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
.sensor-grid.grouped{margin-top:10px}
.sensor-card{padding:12px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.sensor-state{margin-top:4px;font-size:11px;color:var(--ui-warning)}
.sensor-value{margin-top:8px;font-size:18px;font-weight:800}
.sensor-note{margin-top:6px;font-size:11px;line-height:1.5;color:var(--ui-muted)}
.sensor-note.ai{color:#1d4ed8}
.monitor-visual-panel{grid-column:1 / -1}
.monitor-visual-list,.metric-group-list{display:grid;gap:10px}
.visual-row{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 12px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(248,250,252,.9))}
.visual-meta{display:grid;gap:4px;min-width:0}
.visual-meta strong{font-size:13px;line-height:1.3}
.visual-meta span{color:var(--ui-muted);font-size:11px;line-height:1.45}
.visual-bar-shell{position:relative;height:10px;border-radius:999px;background:#eef2f7;overflow:hidden}
.visual-bar-track{position:absolute;inset:0;background:linear-gradient(90deg,rgba(148,163,184,.14),rgba(148,163,184,.24))}
.visual-bar-fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px}
.visual-bar-fill.up{background:linear-gradient(90deg,#fb923c,#f97316)}
.visual-bar-fill.down{background:linear-gradient(90deg,#60a5fa,#2563eb)}
.visual-value{font-size:12px;font-weight:700;white-space:nowrap}
.visual-value.up{color:#c2410c}
.visual-value.down{color:#1d4ed8}
.metric-group{padding:12px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.metric-group.yield{border-color:#bfdbfe;background:linear-gradient(180deg,rgba(239,246,255,.88),rgba(255,255,255,.96))}
.metric-group.consumption{border-color:#fde68a;background:linear-gradient(180deg,rgba(255,251,235,.92),rgba(255,255,255,.96))}
.metric-group.stability{border-color:#bbf7d0;background:linear-gradient(180deg,rgba(240,253,244,.9),rgba(255,255,255,.96))}
.metric-group-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.metric-group-copy{min-width:0}
.metric-group-head strong{font-size:13px;line-height:1.3}
.metric-group-note{margin-top:4px;color:var(--ui-muted);font-size:11px;line-height:1.45}
.metric-group-summary{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:flex-start;gap:8px;max-width:220px}
.metric-group-badge{display:inline-flex;align-items:center;min-height:24px;padding:0 8px;border:1px solid var(--ui-border);border-radius:999px;background:rgba(255,255,255,.82);font-size:11px;font-weight:700;color:var(--ui-muted)}
.metric-group-badge.danger{border-color:#fecaca;background:#fef2f2;color:var(--ui-danger)}
.tag-list{display:flex;flex-direction:column;gap:8px}
.abnormal-detail-list{display:grid;gap:10px}
.abnormal-detail-card{display:grid;gap:8px;padding:12px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.abnormal-detail-card.ok{border-color:#bbf7d0;background:#f0fdf4}
.abnormal-detail-card.warn{border-color:#fdba74;background:#fff7ed}
.abnormal-detail-card.danger{border-color:#fecaca;background:#fef2f2}
.abnormal-detail-card.info{border-color:#bfdbfe;background:#eff6ff}
.abnormal-detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.abnormal-detail-head strong{min-width:0;font-size:13px;line-height:1.4}
.abnormal-detail-meta{font-size:12px;font-weight:600;color:var(--ui-text)}
.abnormal-detail-text{display:grid;gap:2px;font-size:11px;line-height:1.55;color:var(--ui-text)}
.abnormal-detail-text span{color:var(--ui-muted);font-weight:700}
.state-tag{padding:9px 10px;font-size:12px}
.state-tag.ok{background:#f0fdf4;border-color:#bbf7d0}
.state-tag.warn{background:#fff7ed;border-color:#fdba74;color:#c2410c}
.state-tag.info{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
.state-tag.danger{color:var(--ui-danger)}
.prose-card{font-size:12.5px;line-height:1.72;color:var(--ui-text)}
.prose-card :deep(h1),.prose-card :deep(h2),.prose-card :deep(h3),.prose-card :deep(h4){margin:14px 0 8px;color:var(--ui-text);font-weight:800;line-height:1.35}
.prose-card :deep(h3){font-size:14px}
.prose-card :deep(strong){color:var(--ui-text);font-weight:800}
.prose-card :deep(ul),.prose-card :deep(ol){display:grid;gap:6px}
.prose-card :deep(li){line-height:1.7}
.prose-card :deep(li::marker){color:var(--ui-primary)}
.warning-section{background:#fff7ed;border-color:#fdba74}
.path-list{display:grid;gap:6px;word-break:break-all;font-size:12px}
.path-item{color:var(--ui-text);font-weight:700}
.detail-list,.step-list{display:grid;gap:10px}
.detail-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px dashed var(--ui-border);font-size:12px}
.detail-row:last-child{padding-bottom:0;border-bottom:none}
.detail-row span{color:var(--ui-muted)}
.detail-row strong{font-weight:700;color:var(--ui-text);text-align:right}
.detail-row.stacked{display:grid;gap:4px}
.detail-row.stacked strong{text-align:left;line-height:1.55}
.step-card{display:grid;gap:5px;padding:11px 12px;border:1px solid var(--ui-border);border-radius:8px;background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(248,250,252,.92))}
.step-index{font-size:11px;font-weight:700;color:var(--ui-primary)}
.step-title{font-size:13px;font-weight:700;color:var(--ui-text)}
.step-summary{font-size:12px;line-height:1.6;color:var(--ui-muted)}
.visually-hidden-input{position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none}
.markdown :deep(p){margin:0 0 6px}
.markdown :deep(p:last-child){margin-bottom:0}
.markdown :deep(ul),.markdown :deep(ol){margin:0 0 8px;padding-left:18px}
.markdown :deep(table){width:100%;max-width:100%;margin:0 0 10px;border-collapse:collapse;table-layout:fixed}
.markdown :deep(th),.markdown :deep(td){padding:8px 10px;border:1px solid var(--ui-border);vertical-align:top;text-align:left;white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.markdown :deep(th){background:#f8fafc;color:var(--ui-muted);font-size:12px;font-weight:700}
.markdown :deep(code){padding:2px 6px;border-radius:4px;background:var(--ui-surface-tint);color:var(--ui-primary)}
.panel :deep(.el-input__wrapper),.panel :deep(.el-select__wrapper){min-height:40px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface);box-shadow:none}
.panel :deep(.el-input__wrapper.is-focus),.panel :deep(.el-select__wrapper.is-focused){border-color:#93c5fd;box-shadow:none}
.panel :deep(.el-checkbox.is-bordered){min-height:40px;padding:0 12px;border-radius:6px;border-color:var(--ui-border);background:var(--ui-surface)}
.panel :deep(.el-button){border-radius:6px;font-weight:600}
.preset-row :deep(.el-button.is-circle){width:40px;height:40px;border:1px solid var(--ui-border);background:var(--ui-surface);color:var(--ui-primary)}
:global(.settings-modal-overlay){background:rgba(15,23,42,.28) !important;backdrop-filter:blur(4px)}
:deep(.settings-center-dialog){max-width:calc(100vw - 48px);border:none;border-radius:18px;background:#fff;box-shadow:0 28px 72px rgba(15,23,42,.24);overflow:hidden}
:deep(.settings-center-dialog .el-dialog__header){display:none}
:deep(.settings-center-dialog .el-dialog__body){padding:0}
.settings-center-shell{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:620px;max-height:78vh;background:linear-gradient(180deg,#fbfcfe,#f7f9fc)}
.settings-center-nav{display:flex;flex-direction:column;gap:6px;padding:14px 10px;border-right:1px solid var(--ui-border);background:linear-gradient(180deg,#f7f8fb,#f1f3f8)}
.settings-close-btn{width:36px;height:36px;display:flex;align-items:center;justify-content:center;border:none;border-radius:10px;background:#fff;color:#111827;cursor:pointer;font-size:24px;line-height:1}
.settings-nav-group{display:grid;gap:4px}
.settings-nav-group-title{padding:6px 10px 2px;color:#6b7280;font-size:11px;font-weight:700;letter-spacing:.02em}
.settings-nav-item{min-height:44px;display:flex;align-items:center;gap:10px;padding:8px 10px;border:none;border-radius:10px;background:transparent;color:#374151;cursor:pointer;text-align:left}
.settings-nav-item:hover{background:#eef2f7}
.settings-nav-item.active{background:#e9edf5;color:#0f172a}
.settings-nav-icon{width:22px;height:22px;display:flex;align-items:center;justify-content:center;border-radius:7px;background:#fff;color:#4b5563;font-size:14px;flex:0 0 auto}
.settings-nav-item.active .settings-nav-icon{background:#dbe7ff;color:#1d4ed8}
.settings-nav-copy{display:grid;gap:1px;min-width:0}
.settings-nav-copy strong{font-size:13px;line-height:1.2}
.settings-nav-copy small{font-size:11px;color:#6b7280;line-height:1.25}
.settings-center-main{min-width:0;min-height:0;display:flex;flex-direction:column;background:#fff}
.settings-main-head{padding:20px 24px 14px;border-bottom:1px solid var(--ui-border)}
.settings-main-head h3{margin:0;font-size:22px;line-height:1.2}
.settings-main-head p{margin:8px 0 0;color:var(--ui-muted);font-size:13px;line-height:1.5}
.settings-dialog-panel{flex:1 1 auto;min-height:0;overflow:auto;padding:18px 24px 10px;background:#fff;border:none}
.settings-sub-title{font-size:15px;font-weight:700;color:var(--ui-text)}
.settings-sub-text{margin-top:8px;font-size:13px;color:var(--ui-muted);line-height:1.6}
.settings-actions{display:flex;justify-content:flex-end;gap:10px;padding:12px 24px;border-top:1px solid var(--ui-border);background:#fff}
.thinking-detail-shell{display:grid;gap:14px}
.thinking-detail-meta{display:grid;gap:8px;padding:4px 0 6px}
.thinking-detail-title-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.thinking-detail-title-row strong{font-size:15px;color:var(--ui-text)}
.thinking-detail-badge{display:inline-flex;align-items:center;min-height:22px;padding:0 10px;border-radius:999px;background:#eef6ff;color:#1d4ed8;font-size:12px;font-weight:700}
.thinking-detail-summary{font-size:13px;color:var(--ui-text);line-height:1.6}
.thinking-detail-submeta{display:flex;flex-wrap:wrap;gap:12px;color:var(--ui-muted);font-size:12px}
.thinking-detail-list{display:grid;gap:10px;max-height:min(62vh,680px);overflow:auto;padding-right:4px}
.thinking-detail-entry{display:grid;gap:8px;padding:12px 14px;border:1px solid var(--ui-border);border-radius:10px;background:linear-gradient(180deg,#fbfdff,#f8fbff)}
.thinking-detail-entry-head{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--ui-muted);font-size:12px}
:deep(.thinking-detail-dialog .el-dialog__body){padding-top:10px}
:deep(.el-dialog){border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);box-shadow:none}
:deep(.el-dialog__header){margin-right:0;padding:22px 24px 8px}
:deep(.el-dialog__body){padding:12px 24px 8px}
:deep(.el-dialog__footer){padding:12px 24px 24px}
:deep(.settings-center-dialog.el-dialog){border:none;border-radius:18px;background:#fff;box-shadow:0 28px 72px rgba(15,23,42,.24)}
:deep(.settings-center-dialog .el-dialog__header){display:none}
:deep(.settings-center-dialog .el-dialog__body){padding:0}
:global(body.workspace-resizing){user-select:none;cursor:col-resize}
.sidebar::-webkit-scrollbar,.stream-body::-webkit-scrollbar,.panel::-webkit-scrollbar{width:10px}
.sidebar::-webkit-scrollbar-thumb,.stream-body::-webkit-scrollbar-thumb,.panel::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:999px}
@media (max-width:1220px){.layout-body{grid-template-columns:1fr}.sidebar{display:none}.main-grid{grid-template-columns:minmax(0,1.45fr) minmax(320px,.95fr)}}
@media (max-width:980px){.page-shell{grid-template-rows:52px minmax(0,1fr)}.layout-body{min-height:0}.main-grid{grid-template-columns:1fr !important;grid-template-rows:minmax(0,1fr) minmax(0,1fr);height:100%}.workspace-resizer{display:none}.layout-main,.stream-panel,.workspace-panel{height:100%;min-height:0;overflow:hidden}.stream-body,.panel{overflow:auto;height:auto;min-height:0}.panel{flex:1 1 auto}.workspace-toolbar{align-items:center}.workspace-tabs{width:100%}.workspace-head{display:none}}
@media (max-width:980px){.monitor-bottom-grid{grid-template-columns:1fr}.visual-row{grid-template-columns:1fr}.metric-group-head{flex-direction:column}.metric-group-summary{justify-content:flex-start;max-width:none}}
@media (max-width:980px){:deep(.settings-center-dialog){max-width:calc(100vw - 20px)}.settings-center-shell{grid-template-columns:1fr;min-height:auto;max-height:84vh}.settings-center-nav{flex-direction:row;flex-wrap:wrap;align-items:flex-start;border-right:none;border-bottom:1px solid var(--ui-border);padding:10px}.settings-close-btn{order:-1}.settings-nav-group{min-width:180px}.settings-nav-group-title{padding:4px 6px 2px}.settings-nav-item{min-height:40px;padding:8px}.settings-main-head{padding:14px 16px}.settings-main-head h3{font-size:20px}.settings-dialog-panel{padding:14px 16px 8px}.settings-actions{padding:10px 16px}}
@media (max-width:760px){.stream-header,.panel-head,.session-panel-head{flex-direction:column;align-items:flex-start}.page-shell{grid-template-rows:50px minmax(0,1fr)}.layout-header{min-height:0;padding:6px 10px}.layout-header-title{font-size:15px}.layout-header-right{gap:6px;min-width:0}.header-actions{gap:6px}.header-action-btn{min-height:28px;padding:0 8px;font-size:12px}.header-chip{min-height:28px;padding:0 8px;font-size:11px}.layout-main{padding:6px;background-size:18px 18px}.main-grid{gap:6px}.stream-header h1{font-size:18px}.panel h3{font-size:16px}.stream-body,.composer,.panel,.workspace-toolbar{padding-left:9px;padding-right:9px}.composer-row,.preset-row,.kpi-grid{grid-template-columns:1fr}.mode-row{flex-direction:column}.bubble{max-width:100%}.workspace-tabs{display:grid;gap:6px}.workspace-tab{grid-template-columns:24px 1fr;padding:5px 7px}.workspace-tab-index{width:24px;height:24px}.workspace-tab-copy small{display:none}.sensor-grid{grid-template-columns:1fr}}
</style>




