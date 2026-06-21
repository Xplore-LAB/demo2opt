<template>
  <div class="nitrogen-demo">
    <header class="demo-header">
      <div class="header-copy">
        <span class="header-kicker">空分运行诊断 Agent</span>
        <div class="header-title-row">
          <h1>氮塞图形识别与原因分析工作台</h1>
          <span class="header-status-pill" :class="agentStageClass">{{ agentStageText }}</span>
        </div>
        <p>{{ pageStatusText }}</p>
      </div>
      <div class="header-toolbar">
        <div class="primary-actions">
          <label class="upload-btn">
            导入数据
            <input type="file" accept=".csv,.xlsx,.xls" @change="handleFileSelect" />
          </label>
          <button type="button" class="primary-flow-btn" :disabled="!rows.length || scanLoading" @click="identifyNitrogenPlug">
            {{ scanLoading ? '识别中...' : '识别氮塞' }}
          </button>
          <button type="button" class="primary-flow-btn cause-btn" :disabled="!canAnalyzeCause" @click="analyzeSelectedCause">
            {{ agentLoading ? '原因分析中...' : agentAnalysis ? '重新分析原因' : '分析原因' }}
          </button>
        </div>
        <div class="recognition-inline-note">
          识别逻辑：数据窗口 → 基线估计 → 下凹形态识别 → 相对下降幅度 → 持续时间 → 等级划分 → 自动标注 → 原因分析。
        </div>
      </div>
    </header>

    <main class="demo-main">
      <section class="summary-bar">
        <span>当前显示：{{ visibleRangeText }}</span>
        <span>状态：{{ summaryStatusText }}</span>
        <span>识别方式：自适应基线 + 下凹回升形态 + 轻度/中度/重度氮塞分级</span>
      </section>

      <section class="recognition-note">
        <div>
          <strong>识别说明</strong>
          <p>基于 AI705 当前工作点的下凹形态识别，点击分析原因后再联看多测点证据。</p>
        </div>
        <div class="recognition-rule-grid">
          <span><b>工作点</b>按近 6 h 稳定段估计，剔除明显下凹点，适配校表和工况差异。</span>
          <span><b>图形</b>标出开始、谷底、结束、恢复比例和单谷/多谷形态。</span>
          <span><b>分级</b>按相对下凹幅度、持续时间和恢复情况判断，联动证据仅用于原因分析。</span>
        </div>
      </section>

      <section v-if="selectedDemoCases.length" class="selected-case-strip">
        <button
          v-for="caseItem in selectedDemoCases"
          :key="caseItem.event_id"
          type="button"
          class="selected-case-card"
          :class="{ active: activeDemoEventId === caseItem.event_id }"
          @click="selectDemoCase(caseItem.event_id)"
        >
          <strong>{{ caseItem.event_id }}</strong>
          <span>{{ caseItem.case_type }}</span>
          <em>{{ demoSummaryById[caseItem.event_id]?.初步归类 || caseItem.purpose }}</em>
        </button>
      </section>

      <section class="workbench-grid" :class="{ 'analysis-expanded': analysisModeActive }">
        <aside class="panel tag-panel">
          <div class="panel-title">测点分组</div>
          <div class="primary-trigger">
            <div class="tag-group-head">
              <strong>主触发</strong>
            </div>
            <label class="tag-check primary-trigger-check">
              <input :checked="selectedTags.includes(primaryTriggerTag)" type="checkbox" @change="toggleTag(primaryTriggerTag)" />
              <span>
                <strong>{{ primaryTriggerTag }}</strong>
                <em>{{ tagNames[primaryTriggerTag] || primaryTriggerTag }}{{ tagUnits[primaryTriggerTag] ? ` · ${tagUnits[primaryTriggerTag]}` : '' }}</em>
              </span>
            </label>
          </div>
          <div class="tag-groups">
            <div v-for="group in tagGroups" :key="group.name" class="tag-group">
              <div class="tag-group-head">
                <strong>{{ group.name }}</strong>
              </div>
              <label v-for="tag in group.tags" :key="tag" class="tag-check">
                <input :checked="selectedTags.includes(tag)" type="checkbox" @change="toggleTag(tag)" />
                <span>
                  <strong>{{ displayTagCode(tag) }}</strong>
                  <em>{{ tagNames[tag] || tag }}{{ tagUnits[tag] ? ` · ${tagUnits[tag]}` : '' }}</em>
                </span>
              </label>
            </div>
          </div>
        </aside>

        <section class="panel trend-panel" :class="{ 'trend-overlay': showTrendOverlay }">
          <div class="panel-title">
            <span>关键测点趋势</span>
            <div class="trend-toolbar">
              <button
                v-if="analysisModeActive"
                type="button"
                class="ghost-btn"
                :class="{ active: showTrendOverlay }"
                @click="toggleTrendOverlay"
              >
                {{ showTrendOverlay ? '收起趋势图' : '回看趋势图' }}
              </button>
              <span class="muted">{{ selectedMetricText }}</span>
              <label class="mode-select">
                <span>显示方式</span>
                <select v-model="chartDisplayMode">
                  <option value="normalized">归一化趋势</option>
                  <option value="raw">原始值</option>
                  <option value="grouped">分组小图</option>
                </select>
              </label>
            </div>
          </div>
          <div class="trend-legend">
            <span><i class="legend-dot danger"></i>氮塞识别区间</span>
            <span><i class="legend-dot current"></i>本次下凹核心段</span>
            <span><i class="legend-line workpoint"></i>自适应基线</span>
            <span><i class="legend-line marker"></i>开始 / 谷底 / 结束</span>
            <span><i class="legend-dot neutral"></i>固定尺度 / 进度条定位</span>
          </div>
          <div v-if="activeDemoCase" class="case-evidence-band">
            <img v-if="activeDemoFigureUrl" :src="activeDemoFigureUrl" :alt="`${activeDemoEventId} AI705趋势图`" />
            <div class="case-evidence-copy">
              <strong>{{ activeDemoEventId }} · {{ activeDemoCase.case_type }}</strong>
              <p>{{ activeDemoCase.purpose }}</p>
              <div class="case-metric-grid">
                <span v-for="metric in activeDemoMetrics" :key="metric.label">
                  <b>{{ metric.value }}</b>
                  <em>{{ metric.label }}</em>
                </span>
              </div>
            </div>
          </div>
          <div ref="chartBoxRef" class="chart-box">
            <div
              ref="chartStageRef"
              class="chart-stage"
              :class="{ clickable: suspectedEvents.length }"
              @click="handleChartStageClick"
            >
              <canvas ref="chartCanvas"></canvas>
              <div
                v-if="chartEventPrompt"
                ref="chartEventPopoverRef"
                class="chart-event-popover"
                :class="{ collapsed: chartEventPromptCollapsed, dragging: chartEventPromptDragging }"
                :style="{ left: `${chartEventPrompt.left}px`, top: `${chartEventPrompt.top}px` }"
                @click.stop
              >
                <div class="chart-event-popover-header" @pointerdown="startChartEventPromptDrag">
                  <div class="chart-event-popover-summary">
                    <strong>{{ chartEventPrompt.event.eventNo }} · {{ levelText(chartEventPrompt.event.level) }}</strong>
                    <span class="chart-event-popover-window">{{ chartEventPrompt.event.windowLabel }}</span>
                  </div>
                  <button
                    type="button"
                    class="ghost-btn compact-action chart-event-toggle"
                    @click="toggleChartEventPromptCollapsed"
                  >{{ chartEventPromptCollapsed ? '展开' : '收起' }}</button>
                </div>
                <template v-if="!chartEventPromptCollapsed">
                  <div class="chart-event-popover-grid">
                  <small>识别基线 {{ chartEventPrompt.event.workpointText }}</small>
                  <small>谷底值 {{ chartEventPrompt.event.minText }}</small>
                  <small>下凹幅度 {{ chartEventPrompt.event.dipDepthText }}</small>
                  <small>持续时间 {{ chartEventPrompt.event.durationText }}</small>
                  <small>回升比例 {{ chartEventPrompt.event.recoveryText }}</small>
                  <small>候选下凹 {{ chartEventPrompt.event.candidateCountText }}</small>
                  <small class="wide">设备标准 {{ chartEventPrompt.event.deviceStandardText }}</small>
                  <small>原因分析状态 {{ chartEventPrompt.event.analysisText }}</small>
                  </div>
                  <p class="chart-event-popover-note">红色区间表示已按本设备标准识别的氮塞区间，蓝色区间表示本次下凹核心段，用于计算持续时间、谷底和恢复比例。</p>
                  <div class="chart-event-popover-actions">
                    <button
                      type="button"
                      class="ghost-btn compact-action"
                      :class="{ active: isChartEventFocusActive }"
                      @click="toggleChartEventFocus"
                    >{{ isChartEventFocusActive ? '恢复全窗' : '聚焦本次' }}</button>
                    <button type="button" class="ghost-btn compact-action" @click="closeChartEventPrompt">取消</button>
                    <button type="button" class="primary compact-action" :disabled="agentLoading" @click="confirmChartEventAnalysis">分析原因</button>
                  </div>
                </template>
              </div>
            </div>
          </div>
          <div class="time-slider-bar">
            <button type="button" class="ghost-btn compact-action" :disabled="!demoRowCount" @click="stepStreamMinutes(-30)">前移30分钟</button>
            <span class="time-slider-edge">{{ demoRowCount ? formatTime(demoMinTimeMs) : '-' }}</span>
            <div
              ref="timeSliderTrackRef"
              class="time-slider-track"
              @mousemove="handleTimeSliderHover"
              @mouseleave="clearTimeSliderHover"
              @click="handleTimeSliderTrackClick"
            >
              <input
                class="time-slider-input"
                type="range"
                :min="demoMinTimeMs"
                :max="demoMaxTimeMs"
                :step="streamSliderStepMs"
                :value="streamCursorIndex"
                :disabled="!demoRowCount"
                @input="handleStreamSliderInput"
                @change="handleStreamSliderCommit"
              />
              <div
                v-if="timeSliderHover && demoRowCount"
                class="time-slider-tooltip"
                :style="{ left: `${timeSliderHover.ratio * 100}%` }"
              >
                {{ timeSliderHover.label }}
              </div>
            </div>
            <span class="time-slider-edge">{{ demoRowCount ? formatTime(demoMaxTimeMs) : '-' }}</span>
            <button type="button" class="ghost-btn compact-action" :disabled="!demoRowCount" @click="stepStreamMinutes(30)">后移30分钟</button>
          </div>
          <div class="time-slider-meta">
            <span>当前位置：{{ streamProgressText }}</span>
            <span>当前窗口：{{ horizonHintText }}，{{ streamHorizonLimitText }}</span>
          </div>
          <div class="time-scale-options">
            <span>常用尺度</span>
            <button
              v-for="option in streamHorizonOptions"
              :key="option.hours"
              type="button"
              class="time-scale-btn"
              :class="{ active: isStreamHorizonOptionActive(option.hours) }"
              :disabled="!demoRowCount"
              @click="setStreamHorizonHours(option.hours)"
            >
              {{ option.label }}
            </button>
          </div>
        </section>

        <aside class="panel agent-panel" :class="activeResult?.level || 'normal'">
          <div class="panel-title">
            <span>{{ agentPanelTitle }}</span>
            <div class="agent-panel-actions">
              <button
                v-if="analysisModeActive"
                type="button"
                class="ghost-btn"
                :class="{ active: showTrendOverlay }"
                @click="toggleTrendOverlay"
              >
                {{ showTrendOverlay ? '收起趋势图' : '回看趋势图' }}
              </button>
            </div>
          </div>
          <div class="agent-scroll">
            <div class="agent-banner">{{ agentBannerText }}</div>
            <p v-if="agentError" class="agent-error">{{ agentError }}</p>
            <div v-if="!scanResults.length" class="agent-section">
              <h3>当前状态</h3>
              <div class="advice-box waiting">
                <strong>等待识别氮塞</strong>
                <p>点击“识别氮塞”后，右侧只展示本次按设备标准识别得到的轻/中/重氮塞区间和图形证据。</p>
              </div>
            </div>
            <div v-if="shouldShowCompactEventSection" class="agent-section compact-event-section">
              <h3>氮塞识别区间</h3>
              <div class="compact-event-card">
                <div class="compact-event-summary">
                  <strong>{{ suspectedEvents.length ? `${suspectedEvents.length} 个氮塞区间` : '未识别到氮塞区间' }}</strong>
                  <span>{{ selectedSuspectedEvent ? selectedSuspectedEvent.windowLabel : '当前窗口未识别到氮塞区间，可调整时间窗口后重新识别。' }}</span>
                </div>
                <div v-if="compactSuspectedEvents.length" class="compact-event-list">
                  <button
                    v-for="event in compactSuspectedEvents"
                    :key="event.id"
                    type="button"
                    class="compact-event-item"
                    :class="{ active: event.active }"
                    @click="setActiveWindow(event.index)"
                  >
                    <strong>{{ event.eventNo }}</strong>
                    <span>{{ event.windowLabel }}</span>
                    <em>{{ levelText(event.level) }}</em>
                    <div class="event-shape-grid">
                      <small>下凹形态 {{ event.shapeText }}</small>
                      <small>识别基线 {{ event.workpointText }}</small>
                      <small>谷底值 {{ event.minText }}</small>
                      <small>下凹幅度 {{ event.dipDepthText }}</small>
                      <small>持续时间 {{ event.durationText }}</small>
                      <small>回升比例 {{ event.recoveryText }}</small>
                      <small>局部小谷/候选 {{ event.valleyCountText }} / {{ event.candidateCountText }}</small>
                      <small>设备标准 {{ event.deviceStandardText }}</small>
                      <small>原因分析状态 {{ event.analysisText }}</small>
                    </div>
                  </button>
                </div>
              </div>
            </div>
            <div v-if="agentLoading || agentAnalysis" class="agent-section analysis-progress-section">
              <h3>分析过程</h3>
              <div class="analysis-progress-card">
                <div class="analysis-progress-head">
                  <strong>{{ agentLoading ? '正在分析当前区间' : '分析完成' }}</strong>
                  <span>{{ agentLoading ? llmTraceDetail : agentSummaryText }}</span>
                  <div v-if="agentLoading" class="analysis-loading-banner">
                    <i class="analysis-loading-spinner"></i>
                    <div>
                      <b>{{ currentLoadingStageText }}</b>
                      <em>{{ currentTraceStageMeta?.detail || '正在分析当前区间。' }}</em>
                    </div>
                    <mark>{{ analysisLoadingPercent }}%</mark>
                  </div>
                  <div v-if="agentLoading" class="analysis-progress-track">
                    <i :style="{ width: `${analysisLoadingPercent}%` }"></i>
                  </div>
                </div>
                <div class="analysis-step-list">
                  <div
                    v-for="step in analysisProcessSteps"
                    :key="step.id"
                    class="analysis-step-item"
                    :class="step.state"
                  >
                    <div class="analysis-step-index">{{ step.index }}</div>
                    <div class="analysis-step-copy">
                      <div class="analysis-step-head">
                        <strong>{{ step.title }}</strong>
                        <mark class="status-chip" :class="step.badgeClass">{{ step.stateText }}</mark>
                      </div>
                      <p>{{ step.detail }}</p>
                      <div v-if="step.items.length" class="analysis-step-detail-grid">
                        <div v-for="item in step.items" :key="`${step.id}-${item.label}`" class="analysis-step-detail-row">
                          <b>{{ item.label }}</b>
                          <span>{{ item.text }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-if="llmTraceLogLines.length" class="analysis-log-list">
                  <p v-for="(line, index) in llmTraceLogLines.slice(-4)" :key="`analysis-log-${index}`">{{ line }}</p>
                </div>
                <div v-if="agentAnalysis?.report_md" class="analysis-report-card">
                  <div>
                    <strong>报告归档已生成</strong>
                    <span>{{ agentAnalysis.report_md }}</span>
                  </div>
                  <a class="ghost-btn compact-action" :href="reportDownloadUrl" target="_blank" rel="noreferrer">下载报告</a>
                </div>
              </div>
            </div>
            <div v-if="(agentLoading || agentAnalysis) && activeResult" class="agent-section diagnosis-findings-section">
              <h3>稳态诊断复核</h3>
              <div class="diagnosis-status-grid">
                <div class="diagnosis-status-card" :class="operatingModeCard.level">
                  <strong>运行状态</strong>
                  <mark class="status-chip" :class="operatingModeCard.level">{{ operatingModeCard.status }}</mark>
                  <p>{{ operatingModeCard.detail }}</p>
                </div>
                <div class="diagnosis-status-card" :class="materialBalanceCard.level">
                  <strong>物料平衡</strong>
                  <mark class="status-chip" :class="materialBalanceCard.level">{{ materialBalanceCard.status }}</mark>
                  <p>{{ materialBalanceCard.detail }}</p>
                  <em>{{ materialBalanceCard.note }}</em>
                </div>
              </div>
              <div v-if="materialBalanceIOItems.length" class="material-balance-io-card">
                <div v-for="item in materialBalanceIOItems" :key="item.label" class="material-balance-io-row">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.value }}</span>
                </div>
              </div>
              <div v-if="materialBalanceTrace" class="material-balance-trace-card">
                <div class="trace-card-head">
                  <div>
                    <strong>物料平衡计算链路</strong>
                    <span>{{ materialBalanceTrace.statusText }}</span>
                  </div>
                  <mark class="status-chip" :class="materialBalanceTrace.statusClass">{{ materialBalanceTrace.statusLabel }}</mark>
                </div>
                <div class="formula-substitution-card">
                  <b>{{ materialBalanceTrace.primaryFormula.label }}</b>
                  <p>{{ materialBalanceTrace.primaryFormula.text }}</p>
                </div>
                <div class="balance-pipeline">
                  <div v-for="step in materialBalanceTrace.steps" :key="step.key" class="balance-pipeline-step">
                    <small>{{ step.index }}</small>
                    <strong>{{ step.title }}</strong>
                    <span>{{ step.value }}</span>
                    <em>{{ step.note }}</em>
                  </div>
                </div>
                <div v-if="materialBalanceTrace.comparisons.length" class="model-comparison-grid">
                  <div v-for="item in materialBalanceTrace.comparisons" :key="item.key" class="model-comparison-item" :class="item.level">
                    <strong>{{ item.key }}</strong>
                    <span>模型 {{ item.model }}</span>
                    <span>实测 {{ item.actual }}</span>
                    <em>{{ item.diffText }}</em>
                  </div>
                </div>
              </div>
              <div class="variable-deviation-list">
                <div v-for="row in directionalRiskRows" :key="row.tag" class="variable-deviation-row" :class="row.level">
                  <div>
                    <strong>{{ row.name }}</strong>
                    <span>{{ row.directionText }}</span>
                  </div>
                  <p>{{ row.basis }}</p>
                  <em>{{ row.riskText }}</em>
                </div>
              </div>
              <div class="cause-finding-list">
                <div v-for="card in supportedCauseCards" :key="card.id" class="cause-finding-card" :class="card.level">
                  <strong>{{ card.title }}</strong>
                  <p>{{ card.reason }}</p>
                  <div v-if="card.evidence.length" class="cause-evidence-tags">
                    <span v-for="item in card.evidence" :key="`${card.id}-${item.tag}`">{{ item.label }}</span>
                  </div>
                </div>
              </div>
            </div>
            <template v-if="agentAnalysis && !agentLoading">
              <div class="agent-section expert-conclusion-section">
                <h3>专家结论</h3>
                <div class="expert-conclusion-card">
                  <strong>{{ expertConclusionCard.headline }}</strong>
                  <p>{{ expertConclusionCard.judgement }}</p>
                  <div class="expert-conclusion-block">
                    <b>原因构成</b>
                    <span>{{ expertConclusionCard.causeSummary }}</span>
                  </div>
                  <div class="expert-conclusion-block">
                    <b>建议对策</b>
                    <span>{{ expertConclusionCard.actionSummary }}</span>
                  </div>
                </div>
              </div>
              <div class="agent-section">
                <div class="section-head">
                  <h3>异常节点追踪</h3>
                  <button type="button" class="ghost-btn compact-action section-toggle" @click="faultTreeCollapsed = !faultTreeCollapsed">
                    {{ faultTreeCollapsed ? '展开故障树' : '收起故障树' }}
                  </button>
                </div>
                <template v-if="!faultTreeCollapsed">
                  <div class="advice-box">
                    <strong>{{ topEventJudgement.title }}：{{ topEventJudgement.status }}</strong>
                    <p>{{ agentSummaryText }}</p>
                    <p class="logic-text">{{ topEventJudgement.logic }}</p>
                  </div>
                  <div class="tree-focus-card" :class="[statusClass(focusTreeCard.status), traceVisualClass(focusTreeCard.id)]">
                    <span v-if="trailBadgeFor(focusTreeCard.id).text" class="node-trail-badge card-badge" :class="trailBadgeFor(focusTreeCard.id).class" :title="trailBadgeFor(focusTreeCard.id).title">{{ trailBadgeFor(focusTreeCard.id).icon }}</span>
                    <div class="tree-focus-head">
                      <div>
                        <strong>{{ focusTreeCard.id }}</strong>
                        <span>{{ focusTreeCard.title }}</span>
                      </div>
                      <mark class="status-chip" :class="statusClass(focusTreeCard.status)">{{ focusTreeCard.status }}</mark>
                    </div>
                    <p>{{ focusTreeCard.reason }}</p>
                    <div v-if="focusTreeCard.evidence.length" class="tree-bullet-list">
                      <div v-for="item in focusTreeCard.evidence" :key="`${focusTreeCard.id}-${item.label}`" class="tree-bullet">
                        <mark class="status-chip" :class="statusClass(item.status)">{{ item.status }}</mark>
                        <span>{{ item.label }}：{{ item.text }}</span>
                      </div>
                    </div>
                  </div>
                  <div class="tree-branch-grid">
                    <div
                      v-for="card in branchTreeCards"
                      :key="card.id"
                      class="tree-branch-card"
                      :class="[statusClass(card.status), traceVisualClass(card.id)]"
                    >
                      <span v-if="trailBadgeFor(card.id).text" class="node-trail-badge card-badge" :class="trailBadgeFor(card.id).class" :title="trailBadgeFor(card.id).title">{{ trailBadgeFor(card.id).icon }}</span>
                      <div class="tree-branch-head">
                        <strong>{{ card.id }}</strong>
                        <span>{{ card.title }}</span>
                        <mark class="status-chip" :class="statusClass(card.status)">{{ card.status }}</mark>
                      </div>
                      <p>{{ card.reason }}</p>
                      <div v-if="card.evidence.length" class="tree-inline-list">
                        <span v-for="item in card.evidence" :key="`${card.id}-${item.label}`">{{ item.label }}</span>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
              <div v-if="!faultTreeCollapsed" class="agent-section">
                <h3>待补节点</h3>
                <div class="tree-bullet-list tree-bullet-list-compact">
                  <div v-for="item in pendingTreeNodes" :key="`${item.node}-${item.label}`" class="tree-bullet">
                    <mark class="status-chip pending">{{ item.node }}</mark>
                    <span>{{ item.label }}：{{ item.text }}</span>
                  </div>
                </div>
              </div>
              <div class="agent-section">
                <h3>当前建议</h3>
                <div class="note-list">
                  <div v-for="(item, index) in agentInspectionList" :key="item" class="note-row note-row-numbered">
                    <span class="note-index">{{ index + 1 }}</span>
                    <span>{{ item }}</span>
                  </div>
                </div>
                <div class="verify-tags">
                  <span v-for="tag in agentReviewTags" :key="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="agent-section">
                <h3>人工确认</h3>
                <p class="review-status">{{ caseDecisionText }}</p>
              </div>
            </template>
          </div>
          <div v-if="agentAnalysis && !agentLoading" class="case-actions">
            <button
              v-for="action in activeCaseActions"
              :key="action.value"
              type="button"
              :class="{ active: caseDecision === action.value }"
              @click="confirmCase(action.value)"
            >
              {{ action.label }}
            </button>
          </div>
        </aside>
      </section>
      <div v-if="showTrendOverlay" class="trend-overlay-backdrop" @click="toggleTrendOverlay(false)"></div>

    </main>
  </div>
</template>

<script setup>
import { Chart, registerables } from 'chart.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createOrUpdateLineChart, buildChartDatasets } from '../utils/chartUpdate'
import { availableTags, buildChartRows, buildNormalCauses, clamp, formatTime, lowerBoundTime } from '../utils/nitrogenCore'
import NitrogenScanWorker from '../workers/nitrogenScan.worker.js?worker'

Chart.register(...registerables)

const chartCanvas = ref(null)
const chartBoxRef = ref(null)
const chartStageRef = ref(null)
const chartEventPopoverRef = ref(null)
const timeSliderTrackRef = ref(null)
const archiveRows = ref([])
const localArchiveRows = ref([])
const selectedDemoCases = ref([])
const demoSummaryRows = ref([])
const demoDetailRows = ref([])
const activeDemoEventId = ref('')
const demoRowCount = ref(0)
const demoMinTimeMs = ref(0)
const demoMaxTimeMs = ref(0)
const usingSqliteApi = ref(false)
const selectedTags = ref(['AI705'])
const chartDisplayMode = ref('raw')
const windowLengthMin = ref(30)
const streamHorizonOptions = [
  { label: '1h', hours: 1 },
  { label: '6h', hours: 6 },
  { label: '12h', hours: 12 },
  { label: '24h', hours: 24 },
  { label: '48h', hours: 48 },
  { label: '72h', hours: 72 },
  { label: '7d', hours: 24 * 7 }
]
const slideStepMin = ref(5)
const maxVisibleRows = ref(2000)
const streamHorizonHours = ref(12)
const streamStepMin = ref(30)
const streamCursorIndex = ref(0)
const localDataResolution = ref('default')
const timeSliderHover = ref(null)
const scanResults = ref([])
const scanLoading = ref(false)
const activeWindowIndex = ref(0)
const activeCauseId = ref('argon')
const isPlaying = ref(false)
const message = ref('')
const manualConfirmed = ref(false)
const caseDecision = ref('')
const caseDecisions = ref({})
const agentAnalysis = ref(null)
const agentLoading = ref(false)
const agentLoadingStage = ref('idle')
const agentError = ref('')
const llmStreamingText = ref('')
const llmTraceLogLines = ref([])
const llmTracePhase = ref('idle')
const showTrendOverlay = ref(false)
const faultTreeCollapsed = ref(true)
const chartEventPrompt = ref(null)
const chartEventPromptCollapsed = ref(true)
const chartEventPromptDragging = ref(false)
const chartEventFocusState = ref(null)
const lastRenderableChartRows = ref([])
const dataSourceLabel = ref('衢州杭氧1#42000数据.csv')
const globalMetricBounds = ref({})
const fixedMetricBounds = ref({})
const chartWidth = ref(0)
const mergedSuspectedBands = ref([])

let chart = null
let playTimer = null
let refreshTimer = null
let resizeObserver = null
let scanWorker = null
let workerRequestId = 0
let llmStreamTimer = null
let chartLabelLayout = null
let chartEventPromptDrag = null

const defaultDataUrl = '/data/nitrogen-demo-default.csv'
const selectedDemoFileBaseUrl = '/api/nitrogen-demo-selected/file'
const minStreamHorizonHours = 1 / 12
const maxStreamHorizonHours = 24 * 7
const tagNames = {
  AI705: '粗氩含氮量',
  AI701: '氩馏分纯度',
  AIAS704: '粗氩氧含量',
  FI702: '氩馏分流量',
  FIQC701: 'FIC701粗氩流量',
  LIC701: '粗氩冷凝器液位',
  FIQC102: '氧气取出量',
  FIC103: '产品氮气流量',
  FIC8: '液氮流量',
  FI105: '膨胀机增压端空气流量',
  FIC1: '膨胀空气进上塔流量',
  PdI2: '上塔阻力',
  PdI1: '下塔阻力',
  AIAS102: '氧气纯度',
  FIC101: '原料空气总量',
  V3: 'V3阀位',
  BALANCE: '物料平衡偏差'
}
const tagUnits = {
  AI705: '%',
  AI701: '%',
  AIAS704: '%',
  FI702: 'Nm3/h',
  FIQC701: 'Nm3/h',
  LIC701: '%',
  FIQC102: 'Nm3/h',
  FIC103: 'Nm3/h',
  FIC8: 'Nm3/h',
  FI105: 'Nm3/h',
  FIC1: 'Nm3/h',
  PdI2: 'kPa',
  PdI1: 'kPa',
  AIAS102: '%',
  FIC101: 'Nm3/h',
  V3: '%',
  BALANCE: '%'
}
const primaryTriggerTag = 'AI705'
const tagGroups = [
  { name: '粗氩塔', tags: ['FI702', 'FIQC701', 'AIAS704', 'LIC701'] },
  { name: '主塔', tags: ['AI701', 'FIQC102', 'FIC103', 'FIC8', 'V3', 'AIAS102', 'PdI2', 'PdI1'] },
  { name: '空气系统', tags: ['FIC101', 'FI105', 'FIC1'] },
  { name: '事件/校核', tags: ['BALANCE'] }
].filter((group) => group.tags.length)
const trendGroupDefinitions = [
  { key: 'argon-tower', label: '粗氩塔', tags: ['AI705', 'FI702', 'FIQC701', 'AIAS704', 'LIC701'] },
  { key: 'main-tower', label: '主塔', tags: ['AI701', 'FIQC102', 'FIC103', 'FIC8', 'V3', 'AIAS102', 'PdI2', 'PdI1'] },
  { key: 'air-system', label: '空气系统', tags: ['FIC101', 'FI105', 'FIC1'] },
  { key: 'event-check', label: '事件/校核', tags: ['BALANCE'] }
]
const tagColors = {
  AI705: '#2563eb',
  AI701: '#0891b2',
  AIAS704: '#db2777',
  FI702: '#d97706',
  FIQC701: '#7c3aed',
  LIC701: '#0d9488',
  FIQC102: '#16a34a',
  FIC103: '#65a30d',
  FIC8: '#14b8a6',
  FI105: '#ea580c',
  FIC1: '#ca8a04',
  PdI2: '#4f46e5',
  PdI1: '#0f766e',
  AIAS102: '#dc2626',
  FIC101: '#475569',
  V3: '#9333ea',
  BALANCE: '#0f766e'
}
const preferredAxisRanges = {
  AI705: { min: 95, max: 101, stepSize: 1, hiddenTickValues: [101], referenceLines: [{ value: 100, label: '100' }] },
  AI701: { min: 80, max: 100, stepSize: 5 },
  AIAS102: { min: 90, max: 100, stepSize: 2 },
  AIAS704: { min: 0, max: 5, stepSize: 1 },
  LIC701: { min: 0, max: 100, stepSize: 20 },
  V3: { min: 0, max: 100, stepSize: 20 },
  BALANCE: { min: -5, max: 5, stepSize: 1 }
}

const tagAliases = {
  AI705: ['AI705'],
  AI701: ['AI701'],
  AIAS704: ['AIAS704'],
  FI702: ['FI702'],
  FIQC701: ['FIQC701', 'FIC701'],
  LIC701: ['LIC701'],
  FIQC102: ['FIQC102', 'FIQC102_2'],
  FIC103: ['FIC103', 'FIC103_2'],
  FIC8: ['FIC8'],
  FI105: ['FI105'],
  FIC1: ['FIC1_1', 'FIC1'],
  PdI2: ['PdI2'],
  PdI1: ['PdI1'],
  AIAS102: ['AIAS102'],
  FIC101: ['FIC101', 'FIQ101'],
  V3: ['V3', 'FIC3.MV'],
  PRODUCT_N2: ['FIC103', 'FIC103_2'],
  LIQUID_N2: ['FIC8'],
  MEDIUM_N2: ['FI131'],
  EXPAND_AIR: ['FIC1_1', 'FI105']
}
const suspectedCaseActions = [
  { value: 'confirmed', label: '确认氮塞' },
  { value: 'excluded', label: '排除氮塞' },
  { value: 'observe', label: '继续观察' },
  { value: 'supplement', label: '补充数据' }
]
const normalCaseActions = [
  { value: 'observe', label: '继续观察' },
  { value: 'normal', label: '标记为正常波动' },
  { value: 'record', label: '补充现场记录' }
]
const traceStageDefinitions = [
  { id: 'top_event', title: '第一步：看图识别', detail: '正在识别 AI705 相对工作点的下凹、谷底和回升形态。', focusNode: 'T0' },
  { id: 'material_balance', title: '第二步：物料平衡复核', detail: '正在判断稳态/动态，并把空气、氧气、氮气、液氮、粗氩抽取量转成方向性原因证据。', focusNode: 'B' },
  { id: 'branch_detail', title: '第三步：故障树排序', detail: '正在把物料平衡证据送入粗氩塔、主塔、空气系统和事件分支排序。', focusNode: 'A' },
  { id: 'final_summary', title: '结论整理', detail: '正在整理结论和处理建议。', focusNode: 'T0' }
]

const activeResult = computed(() => scanResults.value[activeWindowIndex.value] || null)
const rows = computed(() => archiveRows.value)
const demoSummaryById = computed(() => Object.fromEntries(demoSummaryRows.value.map((row) => [row['事件编号'], row])))
const demoDetailById = computed(() => Object.fromEntries(demoDetailRows.value.map((row) => [row['事件编号'], row])))
const activeDemoCase = computed(() => selectedDemoCases.value.find((item) => item.event_id === activeDemoEventId.value) || null)
const activeDemoSummary = computed(() => demoSummaryById.value[activeDemoEventId.value] || null)
const activeDemoDetail = computed(() => demoDetailById.value[activeDemoEventId.value] || null)
const activeDemoFigureUrl = computed(() => {
  if (!activeDemoCase.value?.figure_file) return ''
  return `${selectedDemoFileBaseUrl}/${activeDemoCase.value.figure_file}`
})
const activeDemoMetrics = computed(() => {
  const summary = activeDemoSummary.value || {}
  return [
    { label: '持续时间', value: formatMetricValue(summary['持续min'], 'min') },
    { label: 'AI705下凹', value: formatMetricValue(summary['下凹幅度'], '%') },
    { label: '谷底值', value: formatMetricValue(summary['AI705最低'], '%') },
    { label: '初步归类', value: summary['AI705形态分级'] || '-' }
  ]
})
const chartRows = computed(() => buildChartRows(rows.value, chartWidth.value, selectedTags.value))
const abnormalCount = computed(() => scanResults.value.filter((item) => item.suspected).length)
const activeWindowLabel = computed(() => activeResult.value?.windowLabel || '-')
const selectedMetricText = computed(() => selectedTags.value.map((tag) => tagNames[tag] || tag).join(' / '))
const suspectedSummaryText = computed(() => suspectedEvents.value.length ? `氮塞区间：${suspectedEvents.value.length} 个` : '未识别到氮塞区间')
const currentTraceStageMeta = computed(() => traceStageDefinitions.find((item) => item.id === agentLoadingStage.value) || null)
const agentStageText = computed(() => {
  if (scanLoading.value) return '识别中'
  if (agentLoading.value) return currentTraceStageMeta.value?.title || '路径追踪中'
  if (agentAnalysis.value) return '等待人工确认'
  if (hasSuspectedEvents.value) return '已标注氮塞区间'
  if (scanResults.value.length) return '扫描完成'
  if (demoRowCount.value) return '待识别'
  return '待导入'
})
const agentStageClass = computed(() => {
  if (agentLoading.value) return 'running'
  if (agentAnalysis.value) return 'review'
  if (hasSuspectedEvents.value) return 'suspected'
  if (scanResults.value.length) return 'normal'
  return 'pending'
})
const analysisModeActive = computed(() => agentLoading.value || Boolean(agentAnalysis.value))
const llmTrace = computed(() => agentAnalysis.value?.llm_trace || {})
const reportDownloadUrl = computed(() => {
  const reportPath = String(agentAnalysis.value?.report_md || '').trim()
  return reportPath ? `/api/reports/download?path=${encodeURIComponent(reportPath)}` : ''
})
const fallbackSource = computed(() => String(agentAnalysis.value?.fallback_source || '').trim())
const decisionLabel = computed(() => String(agentAnalysis.value?.decision_label || '规则主判定').trim())
const explanationLabel = computed(() => {
  const label = String(agentAnalysis.value?.explanation_label || '').trim()
  if (label) return label
  return agentAnalysis.value?.analysis_mode === 'llm_enhanced' ? '智能补充说明' : '规则分析说明'
})
const explanationText = computed(() => {
  return String(agentAnalysis.value?.llm_sentence || agentAnalysis.value?.summary || agentAnalysis.value?.conclusion || '').trim()
})
const llmTraceErrorDetail = computed(() => {
  const attempts = Array.isArray(llmTrace.value?.attempts) ? llmTrace.value.attempts : []
  const latestAttempt = attempts[attempts.length - 1] || {}
  const errorCode = String(llmTrace.value?.error_code || latestAttempt.code || '').trim()
  const errorReason = String(llmTrace.value?.error_reason || latestAttempt.message || agentAnalysis.value?.analysis_fallback_reason || llmTrace.value?.message || '').trim()
  const parts = []
  if (errorCode) parts.push(`错误码：${errorCode}`)
  if (errorReason) parts.push(`原因：${errorReason}`)
  return parts.join('；')
})
const llmTraceLabel = computed(() => {
  if (agentLoading.value) return currentTraceStageMeta.value?.title || '正在分析'
  if (fallbackSource.value === 'frontend_local') return '本地规则分析已完成'
  if (fallbackSource.value === 'request_failure') return '规则结果已完成'
  if (llmTrace.value.status === 'succeeded') return `智能补充已生成${llmTrace.value.model ? `：${llmTrace.value.model}` : ''}`
  if (llmTrace.value.status === 'failed') return '智能补充失败，已保留规则结果'
  if (llmTrace.value.status === 'skipped') return '未调用智能补充，当前为规则分析'
  if (agentAnalysis.value?.analysis_mode === 'llm_enhanced') return '智能补充已生成'
  if (agentAnalysis.value) return decisionLabel.value
  return '等待原因分析'
})
const llmTraceDetail = computed(() => {
  if (agentLoading.value) return llmTracePhase.value || currentTraceStageMeta.value?.detail || '正在分析当前区间。'
  if (fallbackSource.value === 'frontend_local') return '已完成看图识别、物料平衡复核、故障树排序和结论整理；当前展示页面本地规则结果。'
  if (fallbackSource.value === 'request_failure') return '已完成规则分析链路；智能补充不可用时不会影响演示流程。'
  if (llmTrace.value.status === 'failed' && llmTraceErrorDetail.value) return llmTraceErrorDetail.value
  if (llmTrace.value.message) return llmTrace.value.message
  if (agentAnalysis.value?.analysis_fallback_reason) return agentAnalysis.value.analysis_fallback_reason
  if (agentAnalysis.value?.analysis_mode === 'llm_enhanced') return '规则负责最终判断，智能补充负责原因说明、分支排序和处置建议。'
  if (agentAnalysis.value) return '当前结果以规则主判定为准。'
  return '识别到氮塞区间后点击“分析原因”。'
})
const agentPanelTitle = computed(() => {
  if (agentLoading.value) return '原因分析中'
  if (agentAnalysis.value) return '分析结论'
  if (scanResults.value.length) return '氮塞识别结果'
  return '等待识别'
})
const agentBannerText = computed(() => {
  if (agentLoading.value) return currentTraceStageMeta.value?.detail || '正在分析当前区间。'
  if (fallbackSource.value === 'frontend_local') return '分析已完成：当前展示页面本地规则结果。'
  if (fallbackSource.value === 'request_failure') return '分析已完成：智能补充不可用，已保留规则结果。'
  if (llmTrace.value.status === 'failed') return '规则主判定已保留，请直接查看智能补充失败原因。'
  if (agentAnalysis.value) return '分析已完成，请结合现场记录进行人工确认。'
  if (hasSuspectedEvents.value) return '已完成氮塞识别，可选择氮塞区间后点击“分析原因”。'
  if (scanResults.value.length) return '识别完成，当前窗口未发现氮塞区间。'
  return '先点击“识别氮塞”，再根据识别结果分析原因。'
})
const summaryStatusText = computed(() => {
  if (!scanResults.value.length) return '等待扫描'
  return suspectedEvents.value.length ? `${suspectedSummaryText.value}，${resultStatusText.value}` : resultStatusText.value
})
const visibleTrendGroups = computed(() => {
  return trendGroupDefinitions
    .map((group) => ({
      ...group,
      tags: group.tags.filter((tag) => selectedTags.value.includes(tag))
    }))
    .filter((group) => group.tags.length)
})
const fixedChartYBounds = computed(() => {
  if (chartDisplayMode.value === 'normalized') return {}
  if (chartDisplayMode.value === 'grouped') {
    return visibleTrendGroups.value.reduce((bounds, group) => {
      bounds[`group-${group.key}`] = calcFixedYBoundsFromMetricBounds(fixedMetricBounds.value, group.tags)
      return bounds
    }, {})
  }
  return {
    y: calcFixedYBoundsFromMetricBounds(fixedMetricBounds.value, selectedTags.value)
  }
})
const fixedTagYBounds = computed(() => {
  return selectedTags.value.reduce((bounds, tag) => {
    bounds[tag] = calcFixedYBoundsFromMetricBounds(fixedMetricBounds.value, [tag])
    return bounds
  }, {})
})
const renderedPointText = computed(() => {
  if (!rows.value.length) return '0'
  return chartRows.value.length === rows.value.length ? `${rows.value.length}` : `${chartRows.value.length}/${rows.value.length}`
})
const streamProgressText = computed(() => {
  if (!demoRowCount.value) return '-'
  return `${formatTime(streamCursorIndex.value)}`
})
const streamSliderStepMs = computed(() => {
  const sourceRows = localArchiveRows.value.length > 1 ? localArchiveRows.value : archiveRows.value
  if (sourceRows.length > 1) {
    const delta = sourceRows[1].timeMs - sourceRows[0].timeMs
    if (Number.isFinite(delta) && delta > 0) return Math.max(1000, Math.round(delta))
  }
  return 60000
})
const visibleRangeText = computed(() => {
  if (!rows.value.length) return '-'
  return `${formatTime(rows.value[0].timeMs)} - ${formatTime(rows.value[rows.value.length - 1].timeMs)}`
})
const pageStatusText = computed(() => {
  if (!demoRowCount.value) return '请先导入数据，开始区间识别。'
  if (scanLoading.value) return '正在识别氮塞区间，请稍候。'
  if (!scanResults.value.length) return '数据已加载，等待识别分析区间。'
  if (!suspectedEvents.value.length) return '扫描完成，未识别到氮塞区间。'
  if (!agentAnalysis.value) return '已标注轻/中/重氮塞区间，可直接在列表中分析对应区间。'
  if (!caseDecision.value) return '已完成区间扫描，等待人工确认。'
  return {
    confirmed: '已完成人工确认，请结合处置流程继续跟进。',
    excluded: '已排除本区间异常，请继续关注后续趋势变化。',
    observe: '当前区间已标记为继续观察，请持续跟踪关键测点。',
    supplement: '当前区间需要补充数据，请补齐现场记录后复核。',
    normal: '当前区间已标记为正常波动，可继续保持观察。',
    record: '当前区间需要补充现场记录，请补齐信息后复核。'
  }[caseDecision.value] || '已完成区间扫描，等待人工确认。'
})
const horizonHintText = computed(() => {
  if (!archiveRows.value.length || !rows.value.length) return '-'
  const actualHours = (rows.value[rows.value.length - 1].timeMs - rows.value[0].timeMs) / 3600000
  return `当前向前看 ${formatHorizonHours(streamHorizonHours.value)}，实际覆盖 ${formatHorizonHours(actualHours, 1)}`
})
const streamHorizonLimitText = computed(() => `最大支持回看 ${formatHorizonHours(maxStreamHorizonHours)}`)
const resultStatusText = computed(() => {
  if (!activeResult.value) return '等待扫描'
  if (activeResult.value.suspected) {
    return '已识别 AI705 下凹形态，待分析原因'
  }
  return '当前未见明显氮塞特征'
})
const frontlineFocusText = computed(() => {
  const tags = activeResult.value?.triggerTags || []
  if (!tags.length) return '先看AI705，再联看AI701、FI702、FIQC701'
  return tags.slice(0, 4).map(tagLabel).join('、')
})
const activeCauses = computed(() => activeResult.value?.causes || buildNormalCauses())
const hasSuspectedEvents = computed(() => suspectedEvents.value.length > 0)
const canAnalyzeCause = computed(() => hasSuspectedEvents.value && Boolean(selectedSuspectedEvent.value || activeResult.value?.suspected) && !agentLoading.value)
const activeCaseActions = computed(() => hasSuspectedEvents.value ? suspectedCaseActions : normalCaseActions)
const agentEvidence = computed(() => {
  const byTag = new Map()
  const shape = activeResult.value?.ai705Primary
  if (shape?.basis) {
    byTag.set('AI705', {
      tag: 'AI705',
      value: `${shape.shapeText || '下凹形态'}；工作点 ${formatShapeNumber(shape.workpoint)}，最低 ${formatShapeNumber(shape.minValue)}，下凹 ${formatShapeNumber(shape.dipDepth)}，候选 ${Number.isFinite(shape.candidateCount) ? `${shape.candidateCount} 段` : '-'}`,
      basis: shape.basis,
      directionText: '图形主触发',
      riskLevel: activeResult.value?.level || 'low',
      riskLevelText: levelText(activeResult.value?.level)
    })
  }
  activeCauses.value.forEach((cause) => {
    ;(cause.evidence || []).forEach((item) => {
      if (!byTag.has(item.tag)) byTag.set(item.tag, item)
    })
  })
  return Array.from(byTag.values()).slice(0, 6)
})
const missingDataRequests = computed(() => {
  const requests = ['粗氩塔阻力', '上塔/下塔阻力', '分子筛切换记录', '操作记录']
  if (!selectedTags.value.includes('FIC101')) requests.push('总空气量 FIC101')
  if (!selectedTags.value.includes('FIQC102')) requests.push('氧气取出量 FIQC102')
  if (!selectedTags.value.includes('FIC103')) requests.push('氮气产量 FIC103')
  if (!selectedTags.value.includes('FIC8')) requests.push('液氮产量 FIC8')
  if (!selectedTags.value.includes('FI105')) requests.push('膨胀空气旁通量 FI105')
  if (!selectedTags.value.includes('AIAS102')) requests.push('产品氧纯度 AIAS102')
  if (!selectedTags.value.includes('BALANCE')) requests.push('物料平衡偏差 BALANCE')
  return requests
})
const verificationTags = computed(() => {
  const tags = new Set([...(activeResult.value?.triggerTags || []), 'AI705', 'AI701', 'FI702', 'FIQC701', 'FIC101', 'FIQC102', 'FIC103', 'FIC8', 'FI105', 'FIC1', 'V3', 'BALANCE'])
  return Array.from(tags).slice(0, 12)
})
const suspectedEvents = computed(() => {
  const events = []
  const allowedGapMs = slideStepMin.value * 60 * 1000
  scanResults.value.forEach((result, index) => {
    if (!result.suspected) return
    const shape = result.ai705Primary || {}
    const last = events[events.length - 1]
    if (last && result.startMs <= last.endMs + allowedGapMs) {
      last.endMs = Math.max(last.endMs, result.endMs)
      last.windowCount += 1
      result.triggerTags.forEach((tag) => last.triggerTagSet.add(tag))
      last.maxDipDepth = Math.max(last.maxDipDepth || 0, shape.dipDepth || 0)
      last.maxRecoveryRatio = Math.max(last.maxRecoveryRatio || 0, shape.recoveryRatio || 0)
      last.maxValleyCount = Math.max(last.maxValleyCount || 0, shape.valleyCount || 0)
      if (riskRank(result.level) >= riskRank(last.level) || (shape.dipDepth || 0) >= (last.shape?.dipDepth || 0)) {
        last.level = result.level
        last.index = index
        last.summary = result.summary
        last.shape = shape
      }
      return
    }
    events.push({
      id: `event-${result.id}`,
      index,
      startMs: result.startMs,
      endMs: result.endMs,
      level: result.level,
      summary: result.summary,
      triggerTagSet: new Set(result.triggerTags),
      windowCount: 1,
      suspected: true,
      shape,
      maxDipDepth: shape.dipDepth || 0,
      maxRecoveryRatio: shape.recoveryRatio || 0,
      maxValleyCount: shape.valleyCount || 0
    })
  })

  return events.map((event, eventIndex) => {
    const eventNo = `NP-${String(eventIndex + 1).padStart(3, '0')}`
    const eventLevel = classifyMergedEventLevel(event)
    const shape = event.shape || {}
    return {
      ...event,
      level: riskRank(eventLevel) > riskRank(event.level) ? eventLevel : event.level,
      eventNo,
      windowLabel: `${formatTime(event.startMs)} - ${formatTime(event.endMs)}`,
      durationText: formatDuration(event.startMs, event.endMs),
      triggerTags: Array.from(event.triggerTagSet),
      active: Boolean(activeResult.value && activeResult.value.startMs >= event.startMs && activeResult.value.endMs <= event.endMs),
      reviewText: reviewText(caseDecisions.value[eventNo]?.value || caseDecisions.value[eventNo]),
      summary: event.windowCount > 1 ? `合并 ${event.windowCount} 个扫描窗口：${event.summary}` : event.summary,
      shapeText: shape.shapeText || '-',
      workpointText: formatShapePercent(shape.workpoint),
      minText: formatShapePercent(shape.minValue),
      dipDepthText: formatShapePercent(shape.dipDepth),
      recoveryText: formatPercent(shape.recoveryRatio),
      valleyCountText: Number.isFinite(shape.valleyCount) ? `${shape.valleyCount} 个` : '-',
      candidateCountText: Number.isFinite(shape.candidateCount) ? `${shape.candidateCount} 段` : '-',
      deviceStandardText: formatDeviceStandard(shape.deviceStandard),
      analysisText: agentAnalysis.value ? '已完成原因分析' : '待分析'
    }
  })
})
const activeEvent = computed(() => suspectedEvents.value.find((event) => event.active) || null)
const selectedSuspectedEvent = computed(() => activeEvent.value || suspectedEvents.value[0] || null)
const isChartEventFocusActive = computed(() => {
  const focusedEventId = chartEventFocusState.value?.eventId
  const promptEventId = chartEventPrompt.value?.event?.id
  return Boolean(focusedEventId && promptEventId && focusedEventId === promptEventId)
})
const compactSuspectedEvents = computed(() => {
  if (analysisModeActive.value && activeEvent.value) return [activeEvent.value]
  const list = suspectedEvents.value.slice(0, 4)
  if (activeEvent.value && !list.some((item) => item.id === activeEvent.value.id)) {
    return [activeEvent.value, ...list.slice(0, 3)]
  }
  return list
})
const comparisonRows = computed(() => {
  if (!activeResult.value || !rows.value.length) return buildEmptyComparisonRows()
  const beforeStart = activeResult.value.startMs - 30 * 60 * 1000
  const beforeEnd = activeResult.value.startMs
  const duringStart = activeResult.value.startMs
  const duringEnd = activeResult.value.endMs
  const afterStart = activeResult.value.endMs
  const afterEnd = activeResult.value.endMs + 30 * 60 * 1000
  const beforeRows = pickRowsByTime(rows.value, beforeStart, beforeEnd)
  const duringRows = pickRowsByTime(rows.value, duringStart, duringEnd)
  const afterRows = pickRowsByTime(rows.value, afterStart, afterEnd)
  const focusTags = Array.from(new Set(['AI705', 'AI701', 'FI702', 'FIQC701', 'FIC101', 'FIQC102', 'FIC103', 'FIC8', 'FI105', 'FIC1', 'PdI2', 'PdI1', ...verificationTags.value])).slice(0, 12)

  return focusTags.map((tag) => {
    const before = calcSegmentStats(beforeRows, tag)
    const during = calcSegmentStats(duringRows, tag)
    const after = calcSegmentStats(afterRows, tag)
    return {
      tag,
      before: formatMean(before.mean),
      during: formatMean(during.mean),
      after: formatMean(after.mean),
      direction: describeDirection(before, during, after),
      support: describeSupport(tag, before, during)
    }
  })
})
const balanceVerification = computed(() => {
  const equation = activeResult.value?.balance?.formulaText || 'EGOX = GOX - 125/136 × LIN + 114/136 × (GAR - GARBase)；PAIR、GAN+LIN、TURBBY、FAR、CAR、LEV、AIR由外压缩回归模型输出。'
  const balance = activeResult.value?.balance
  const operatingMode = activeResult.value?.operatingMode
  if (activeResult.value && agentAnalysis.value?.material_balance_review) {
    return {
      level: balance?.staticApplicable === false ? 'pending' : (balance?.triggered ? 'warn' : 'normal'),
      equation,
      result: agentAnalysis.value.material_balance_review,
      conclusion: balance?.staticApplicable === false
        ? '当前处于变负荷过程，静态物料平衡不直接用于原因定位。'
        : balance?.triggered ? '需要排查负荷或取出量扰动' : '平衡复核未单独指向负荷扰动',
      note: '物料平衡用于把空气、氧气、氮气、液氮等变量转成偏低/正常/偏高语义，不单独定位氮塞原因。'
    }
  }
  if (!activeResult.value) {
    return {
      level: 'pending',
      equation,
      result: '等待扫描',
      conclusion: '尚未进入区间验证',
      note: '链路为：运行状态判断 → 稳态/动态分流 → 物料平衡基准计算 → 多原因并行排查。'
    }
  }
  if (!balance || !Number.isFinite(balance.mean)) {
    return {
      level: 'pending',
      equation,
      result: '关键流量数据不足',
      conclusion: '需要补充进塔空气量、产品取出量和氩馏分取出量',
      note: '缺少 FIC101、FIQC102、FIC103、FIC8 或相关取出量时，方程只能作为待补验证项。'
    }
  }
  if (operatingMode?.dynamic || balance.staticApplicable === false) {
    return {
      level: 'pending',
      equation,
      result: balance.summary,
      conclusion: balance.conclusion || '当前氮塞可能发生在变负荷过程中，原因可能与负荷变化速度、空气和产品抽取之间的时序不匹配有关。',
      note: '动态过程重点看空气、氧气、氮气的升降速度和时序匹配，不能直接套用静态物料平衡。'
    }
  }
  if (balance.triggered) {
    return {
      level: 'warn',
      equation,
      result: balance.summary,
      conclusion: '至少一个关键变量超出当前负荷合理范围，需要并行排查空气少进、氧气多抽、氮气少抽、液氮负荷和粗氩侧扰动。',
      note: '偏离程度越大，对应原因可能性越高；正常项不必展开，重点展示异常项。'
    }
  }
  return {
    level: 'normal',
    equation,
    result: balance.summary,
    conclusion: '关键变量未明显超出基准范围，当前氮塞判断主要依赖粗氩侧和事件因素证据。',
    note: '平衡稳定时，可降低全流程负荷扰动解释优先级，但仍需结合塔阻力、压力、分子筛切换和操作记录复核。'
  }
})
const operatingModeCard = computed(() => {
  const mode = activeResult.value?.operatingMode
  if (!mode) {
    return {
      level: 'pending',
      status: '待确认',
      detail: '尚未进入窗口诊断。'
    }
  }
  return {
    level: mode.dynamic ? 'partial' : 'normal',
    status: mode.label || '待确认',
    detail: mode.basis || '根据 FIC101 窗口变化、波动和前段均值判断运行状态。'
  }
})
const materialBalanceCard = computed(() => {
  const balance = activeResult.value?.balance
  if (!balance || !Number.isFinite(balance.mean)) {
    return {
      level: 'pending',
      status: '待补数据',
      detail: '缺少物料平衡必要测点，无法计算当前负荷基准。',
      note: '需要 FIC101、FIQC102、氮产品流量、氩馏分流量等关键流量。'
    }
  }
  if (balance.staticApplicable === false) {
    return {
      level: 'partial',
      status: '动态降级',
      detail: balance.summary,
      note: '当前先判断负荷变化速度，以及空气、氧气、氮气之间的调整节奏是否匹配。'
    }
  }
  const abnormalChecks = (balance.semanticChecks || [])
    .filter((item) => item.direction !== 'normal' && item.direction !== 'unknown')
    .slice(0, 3)
    .map((item) => `${tagLabel(item.tag)} ${item.directionText}，${item.riskLevelText}`)
    .join('；')
  return {
    level: balance.triggered ? 'triggered' : 'normal',
    status: balance.triggered ? '超出范围' : '范围内',
    detail: balance.summary,
    note: abnormalChecks || balance.conclusion || balance.baselineBasis || '按当前负荷基准、±1.25%合理范围、当前均值和前段均值复核。'
  }
})
const materialBalanceIOItems = computed(() => {
  const balance = activeResult.value?.balance
  if (!balance) return []
  const outputs = balance.outputs || {}
  const componentInputs = outputs.component_inputs || balance.componentInputs || {}
  const externalModel = outputs.external_model || balance.externalModel || {}
  const modelVariables = Array.isArray(externalModel.variables) ? externalModel.variables : []
  const keyVariables = modelVariables
    .filter((item) => ['EGOX', 'PAIR', 'GAN+LIN', 'TURBBY', 'FAR', 'CAR', 'LEV', 'AIR'].includes(item.key))
    .slice(0, 8)
    .map((item) => `${item.key} ${formatMetricValue(item.value)}`)
    .join('、')
  const abnormalChecks = outputs.abnormal_checks || []
  const componentText = Number.isFinite(componentInputs.O2_in)
    ? `O2_in ${formatMetricValue(componentInputs.O2_in)}、N2_in ${formatMetricValue(componentInputs.N2_in)}、Ar_in ${formatMetricValue(componentInputs.Ar_in)}`
    : '等待进塔空气量'
  return [
    { label: '位置', value: balance.stepPosition || '氮塞识别完成 → 物料平衡复核 → 故障树排序' },
    { label: '模型', value: externalModel.name || '外压缩物料平衡模型' },
    { label: '输入', value: 'GOX(FIQC102)、LIN(FIC8/V8)、GAR(FIC103)、TEMP、TURBINE(FIC1/FI105)、FI702、FIC701、LIC701。' },
    { label: '方程', value: balance.formulaText || balanceVerification.value.equation },
    { label: '中间量', value: keyVariables || componentText },
    {
      label: '输出',
      value: abnormalChecks.length
        ? abnormalChecks.slice(0, 4).map((item) => `${item.name || tagLabel(item.tag)}${item.directionText}`).join('、')
        : (balance.staticApplicable === false ? '动态过程提示，不输出静态闭合判据' : '关键变量在同负荷合理范围内')
    },
    {
      label: '系数',
      value: externalModel.coefficientNote || '回归系数后续由Curve Fitting建模结果接入。'
    },
    {
      label: '缺项',
      value: externalModel.missingForProduction?.join('；') || '正式模型缺项待确认。'
    }
  ]
})
const materialBalanceTrace = computed(() => {
  const balance = activeResult.value?.balance
  if (!balance) return null
  const externalModel = balance.outputs?.external_model || balance.externalModel || {}
  const variables = Array.isArray(externalModel.variables) ? externalModel.variables : []
  const byKey = new Map(variables.map((item) => [item.key, item]))
  const valueOf = (key) => byKey.get(key)?.value
  const format = (key) => formatMetricValue(valueOf(key))
  const modelStatus = externalModel.status || 'unknown'
  const statusLabel = modelStatus === 'demo_ready'
    ? '实测输入'
    : modelStatus === 'demo_estimated'
    ? '含临时估算'
    : modelStatus === 'missing_inputs'
    ? '缺核心输入'
    : '待确认'
  const statusClass = modelStatus === 'missing_inputs' ? 'warn' : modelStatus === 'demo_estimated' ? 'partial' : 'normal'
  const substitution = `EGOX = ${format('GOX')} - 125/136 × ${format('LIN')} + 114/136 × (${format('GAR')} - ${format('GARBase')}) = ${format('EGOX')}`
  const pairs = [
    ['PAIR', 'PAIR_actual'],
    ['GAN+LIN', 'GAN+LIN_actual'],
    ['TURBBY', 'TURBBY_actual'],
    ['FAR', 'FAR_actual'],
    ['CAR', 'CAR_actual'],
    ['LEV', 'LEV_actual'],
    ['AIR', 'AIR_actual']
  ]
  const comparisons = pairs.map(([modelKey, actualKey]) => {
    const model = valueOf(modelKey)
    const actual = valueOf(actualKey)
    const diff = Number.isFinite(model) && Number.isFinite(actual) ? actual - model : NaN
    const diffPct = Number.isFinite(diff) && Number.isFinite(model) && model !== 0 ? (diff / Math.abs(model)) * 100 : NaN
    const absPct = Math.abs(diffPct || 0)
    return {
      key: modelKey,
      model: formatMetricValue(model),
      actual: formatMetricValue(actual),
      diffText: Number.isFinite(diff) ? `差值 ${formatMetricValue(diff)}（${formatPercent(diffPct)}）` : '缺少实测对比',
      level: !Number.isFinite(diffPct) ? 'pending' : absPct > 5 ? 'triggered' : absPct > 1.25 ? 'partial' : 'normal'
    }
  }).filter((item) => item.model !== '-' || item.actual !== '-')
  return {
    statusLabel,
    statusClass,
    statusText: externalModel.recoveredInputs?.length
      ? `已完成计算，但使用了临时估算：${externalModel.recoveredInputs.join('、')}`
      : externalModel.missingCoreInputs?.length
      ? `缺少核心输入：${externalModel.missingCoreInputs.map((item) => item.key).join('、')}`
      : '已完成公式代入和模型/实测对比。',
    primaryFormula: {
      label: '公式代入',
      text: substitution
    },
    steps: [
      { key: 'input', index: '01', title: '读取输入', value: `GOX ${format('GOX')} / LIN ${format('LIN')} / GAR ${format('GAR')}`, note: '来自当前窗口均值或 Demo 临时估算' },
      { key: 'egox', index: '02', title: '计算 EGOX', value: format('EGOX'), note: '等效全液氧工况氧气产量' },
      { key: 'pair', index: '03', title: '回归 PAIR', value: format('PAIR'), note: '由 AIRCoef1-4 计算进塔分离空气' },
      { key: 'outputs', index: '04', title: '派生目标量', value: `FAR ${format('FAR')} / CAR ${format('CAR')} / AIR ${format('AIR')}`, note: '再与当前实测值做偏差判断' }
    ],
    comparisons
  }
})
const directionalRiskRows = computed(() => {
  const checks = activeResult.value?.directionalChecks || []
  const focusOrder = ['AI705', 'AI701', 'FI702', 'FIQC701', 'FIC101', 'FIQC102', 'FIC103', 'FIC8', 'FI105', 'FIC1', 'PdI2', 'PdI1', 'AIAS102', 'V3', 'BALANCE']
  const abnormalRows = checks
    .filter((item) => item.triggered || ['AI705', 'FIC101', 'FIQC102', 'FIC103', 'FIC8', 'BALANCE'].includes(item.tag))
    .sort((a, b) => focusOrder.indexOf(a.tag) - focusOrder.indexOf(b.tag))
    .slice(0, 8)
  const rows = abnormalRows.length ? abnormalRows : checks.filter((item) => focusOrder.includes(item.tag)).slice(0, 4)
  return rows.map((item) => ({
    tag: item.tag,
    name: tagLabel(item.tag),
    directionText: item.directionText || '待补数据',
    basis: item.basis || '缺少基准或当前窗口数据。',
    riskText: item.riskText || `偏离程度：${item.riskLevelText || '正常'}。未发现明确偏高/偏低风险。`,
    level: item.triggered ? (item.direction === 'high' ? 'triggered' : 'partial') : item.direction === 'unknown' ? 'pending' : 'normal'
  }))
})
const supportedCauseCards = computed(() => {
  const cards = activeCauses.value
    .filter((cause) => (cause.evidence || []).length || !/待确认/.test(cause.confidence || ''))
    .map((cause) => ({
      id: cause.id,
      title: `${cause.branch}：${cause.name}`,
      level: (cause.evidence || []).length ? 'partial' : 'pending',
      reason: cause.evidence?.length
        ? `已发现 ${cause.evidence.length} 项异常证据，${cause.advice}`
        : cause.advice,
      evidence: (cause.evidence || []).slice(0, 4).map((item) => ({
        tag: item.tag,
        label: `${item.tag} ${item.directionText || ''}`.trim()
      }))
    }))
  if (cards.length) return cards.slice(0, 4)
  return [{
    id: 'none',
    title: '未锁定明确原因分支',
    level: 'pending',
    reason: '当前窗口未发现足够的异常证据，建议继续观察并补充现场记录。',
    evidence: []
  }]
})
const analysisEngineCard = computed(() => {
  if (agentLoading.value) {
    if (agentLoadingStage.value === 'final_summary') {
      return {
        level: 'running',
        status: '已发起',
        detail: '当前这一步会真正请求大模型，并等待返回结构化 JSON 结果。',
        note: '步骤1-3 主要用于规则判断和页面推进，步骤4 才进入完整大模型分析。'
      }
    }
    return {
      level: 'pending',
      status: '未发起',
      detail: '当前这一步还没有真正调用大模型，先走规则判断或占位复核。',
      note: '只有步骤4“生成结论”会发起完整大模型调用。'
    }
  }
  if (llmTrace.value.status === 'succeeded') {
    return {
      level: 'triggered',
      status: '成功',
      detail: `本次分析已成功调用${llmTrace.value.model ? ` ${llmTrace.value.model}` : '大模型'}，并返回结构化 JSON。`,
      note: '规则负责最终判断，智能补充负责原因说明、分支排序和处置建议。'
    }
  }
  if (fallbackSource.value === 'frontend_local') {
    return {
      level: 'normal',
      status: '规则完成',
      detail: '页面已用本地规则完成完整分析流程。',
      note: '后端或智能补充不可用时，演示仍会展示识别、物料平衡、故障树和结论。'
    }
  }
  if (fallbackSource.value === 'request_failure') {
    return {
      level: 'normal',
      status: '规则完成',
      detail: '请求链路不可用时已切回规则分析结果。',
      note: '智能补充失败不影响四步演示流程。'
    }
  }
  if (llmTrace.value.status === 'failed') {
    return {
      level: 'partial',
      status: '失败',
      detail: '完整分析阶段尝试调用过智能补充，但本次未拿到有效结果，当前保留规则主判定。',
      note: llmTrace.value.message || '页面当前展示的是规则主判定，不是智能补充结论。'
    }
  }
  if (agentAnalysis.value) {
    return {
      level: 'pending',
      status: '未调用',
      detail: '当前结果没有走到有效的智能补充，页面主要展示规则分析内容。',
      note: '步骤1-3 本身不会调用大模型；若步骤4未成功，最终会保留规则结果。'
    }
  }
  return {
    level: 'pending',
    status: '未开始',
        detail: '点击“分析原因”后，前 3 步先走规则判断和占位复核，第 4 步再调用大模型。',
    note: '这样能先把故障树步骤跑起来，再尝试生成完整结构化结论。'
  }
})
const materialBalancePlaceholderCard = computed(() => {
  const formulaStatus = agentAnalysis.value?.material_balance_formula_status || activeResult.value?.balance?.formulaStatus || 'implemented'
  const mode = agentAnalysis.value?.material_balance_mode || activeResult.value?.balance?.mode || 'steady_review'
  const isRunning = agentLoading.value && agentLoadingStage.value === 'material_balance'
  return {
    level: isRunning ? 'running' : (balanceVerification.value.level === 'warn' ? 'partial' : 'normal'),
    status: isRunning ? '执行中' : (formulaStatus === 'implemented' ? '已接入' : '待补数据'),
    detail: formulaStatus === 'implemented'
      ? '当前步骤已接入工程化物料平衡复核：识别后先判断稳态/动态，再输出输入、方程、组分入口和方向性偏差。'
      : '关键流量不足时，物料平衡会降级为待补验证项。',
    basis: mode === 'dynamic_load'
      ? '变负荷过程已单独标记，静态平衡不直接定位原因'
      : '按当前负荷基准、当前值和历史/前段均值计算偏差',
    formula: formulaStatus === 'implemented' ? '已接入正式方程' : '正式方程待接入',
    note: balanceVerification.value.result || '当前仅作为辅助校核步骤，不单独决定是否为氮塞。'
  }
})
const agentConclusionText = computed(() => {
  if (agentAnalysis.value?.conclusion) return agentAnalysis.value.conclusion
  if (!activeResult.value) return '等待选择观察窗口'
  if (activeResult.value.suspected) {
    return agentAnalysis.value
      ? '已按本设备标准识别到氮塞区间，建议结合现场记录复核原因结论。'
      : '已识别到 AI705 下凹形态，下一步需要点击“分析原因”联看辅助证据。'
  }
  return '未识别到达到本设备轻度标准的氮塞区间，当前以正常波动为主。'
})
const agentSummaryText = computed(() => {
  if (!activeResult.value) return '等待选择观察窗口后再生成初步分析。'
  if (agentAnalysis.value?.top_event_judgement?.summary) {
    return agentAnalysis.value.top_event_judgement.summary
  }
  if (agentAnalysis.value?.summary && !looksLikeRawMetricSummary(agentAnalysis.value.summary)) {
    return agentAnalysis.value.summary
  }
  if (activeResult.value.suspected) {
    return agentAnalysis.value
      ? '当前窗口已完成原因分析，建议重点联看粗氩组分、流量与负荷变化。'
      : '当前窗口已完成 AI705 下凹形态识别，原因分析尚未开始。'
  }
  return '关键测点整体平稳，当前未见达到本设备标准的氮塞特征。'
})
const agentBasis = computed(() => agentAnalysis.value?.basis?.length ? agentAnalysis.value.basis : agentEvidence.value)
const agentMissingInformation = computed(() => agentAnalysis.value?.missing_information?.length ? agentAnalysis.value.missing_information : missingDataRequests.value)
const agentReviewTags = computed(() => agentAnalysis.value?.review_tags?.length ? agentAnalysis.value.review_tags : verificationTags.value)
const topEventJudgement = computed(() => {
  const local = buildLocalTopEventJudgement()
  const remote = agentAnalysis.value?.top_event_judgement
  if (!remote) return local
  return {
    ...local,
    ...remote,
    items: remote.items?.length ? remote.items : local.items
  }
})
const topEventRows = computed(() => topEventJudgement.value?.items || [])
const agentEvidenceNodes = computed(() => {
  const rows = agentAnalysis.value?.evidence_nodes?.length ? agentAnalysis.value.evidence_nodes : buildLocalEvidenceNodes()
  return rows.slice(0, 10).map((item) => ({
    evidence: item.evidence || item.tag || item.title || '证据',
    node: item.node || item.node_id || item.focus || '故障树节点',
    status: item.status || item.support_level || '待排查',
    explanation: item.explanation || item.reason || item.basis || '按节点判据复核。'
  }))
})
const agentFaultTreePath = computed(() => {
  const remote = agentAnalysis.value?.fault_tree_path
  const lines = Array.isArray(remote) && remote.length
    ? remote
    : (typeof remote === 'string' && remote.trim() ? remote.split('\n') : buildLocalFaultTreePath())
  return lines.filter(Boolean).join('\n')
})
const agentBranchRanking = computed(() => {
  const rows = agentAnalysis.value?.branch_ranking?.length ? agentAnalysis.value.branch_ranking : buildLocalBranchRanking()
  return rows.slice(0, 4).map((item, index) => ({
    rank: item.rank || index + 1,
    branch: item.branch || item.name || '故障树分支',
    status: item.status || item.support_level || '待排查',
    reason: item.reason || item.detail || '按当前证据状态排序。',
    next_step: item.next_step || item.nextStep || item.action || '补齐对应节点证据后复核。'
  }))
})
const agentLogicNodes = computed(() => agentBranchRanking.value.map((item) => {
  const match = String(item.branch || '').match(/^[A-D]/)
  const id = match?.[0] || `R${item.rank}`
  const children = buildLogicChildren(id).filter((child) => /已|部分|待判别|有波动|有提示/.test(child.status || ''))
  return {
    id,
    title: String(item.branch || '').replace(/^[A-D]\s*/, '') || '原因分支',
    status: item.status || '待排查',
    children
  }
}))
const currentTraceFocusNode = computed(() => {
  const focusNode = String(agentAnalysis.value?.trace_focus_node || currentTraceStageMeta.value?.focusNode || 'T0').toUpperCase()
  return ['T0', 'A', 'B', 'C', 'D'].includes(focusNode) ? focusNode : 'T0'
})
const currentTraceStageIndex = computed(() => {
  const activeStage = agentLoading.value ? agentLoadingStage.value : (agentAnalysis.value?.trace_stage || 'final_summary')
  const index = traceStageDefinitions.findIndex((item) => item.id === activeStage)
  return index >= 0 ? index : traceStageDefinitions.length - 1
})
const analysisLoadingPercent = computed(() => {
  if (!agentLoading.value) return agentAnalysis.value ? 100 : 0
  const stepCount = Math.max(traceStageDefinitions.length, 1)
  return Math.min(96, Math.max(8, Math.round(((currentTraceStageIndex.value + 0.55) / stepCount) * 100)))
})
const currentLoadingStageText = computed(() => {
  const index = Math.max(0, currentTraceStageIndex.value)
  const title = currentTraceStageMeta.value?.title || '原因分析'
  return `正在执行 ${index + 1}/${traceStageDefinitions.length}：${title}`
})
const shouldShowCompactEventSection = computed(() => scanResults.value.length > 0 && !analysisModeActive.value)
const analysisProcessSteps = computed(() => {
  const activeIndex = currentTraceStageIndex.value
  return traceStageDefinitions.map((stage, index) => {
    let state = 'pending'
    if (agentLoading.value) {
      if (index < activeIndex) state = 'completed'
      else if (index === activeIndex) state = 'running'
    } else if (agentAnalysis.value) {
      state = 'completed'
    }

    const stateMeta = getAnalysisStepStateMeta(stage.id, state)

    let detail = stage.detail
    if (state === 'running') {
      detail = llmTracePhase.value || currentTraceStageMeta.value?.detail || stage.detail
    } else if (state === 'completed' && stage.id === 'final_summary') {
      detail = agentSummaryText.value
    } else if (state === 'completed') {
      detail = buildAnalysisStepSummary(stage.id)
    }

    return {
      id: stage.id,
      index: index + 1,
      title: stage.title,
      detail,
      items: buildAnalysisStepProcessItems(stage.id, state),
      state,
      stateText: stateMeta.text,
      badgeClass: stateMeta.className
    }
  })
})
function getAnalysisStepStateMeta(stageId, state) {
  if (state === 'running') return { text: '进行中', className: 'running' }
  if (state === 'pending') return { text: '等待中', className: 'pending' }
  if (stageId === 'top_event') return { text: '已识别', className: 'normal' }
  if (stageId === 'material_balance') {
    const balance = activeResult.value?.balance
    const externalStatus = balance?.outputs?.external_model?.status || balance?.externalModel?.status
    if (externalStatus === 'missing_inputs') return { text: '待补输入', className: 'pending' }
    if (externalStatus === 'demo_estimated') return { text: '估算复核', className: 'partial' }
    if (balance?.staticApplicable === false) return { text: '动态降级', className: 'partial' }
    return { text: balance?.triggered ? '已复核' : '已复核', className: balance?.triggered ? 'partial' : 'normal' }
  }
  if (stageId === 'branch_detail') return { text: '已排序', className: 'normal' }
  if (stageId === 'final_summary') return { text: '已整理', className: 'normal' }
  return { text: '已完成', className: 'normal' }
}
function buildAnalysisStepSummary(stageId) {
  const result = activeResult.value
  const balance = result?.balance
  const shape = result?.ai705Primary || {}
  if (stageId === 'top_event') {
    return `AI705形成${shape.shapeText || '下凹回升'}，下凹 ${formatShapeNumber(shape.dipDepth)}，恢复 ${formatPercent(shape.recoveryRatio)}，判为${levelText(result?.level)}。`
  }
  if (stageId === 'material_balance') {
    const abnormal = balance?.outputs?.abnormal_checks || []
    const externalModel = balance?.outputs?.external_model || balance?.externalModel || {}
    const modelOutput = externalModel.primaryOutputText || ''
    const abnormalText = abnormal.length
      ? abnormal.slice(0, 3).map((item) => `${item.name || tagLabel(item.tag)}${item.directionText}`).join('、')
      : (balance?.staticApplicable === false ? '当前为动态过程，静态平衡降级' : '关键变量未明显越界')
    if (externalModel.status === 'missing_inputs') {
      const missing = (externalModel.missingCoreInputs || []).map((item) => item.key).join('/') || '核心输入'
      return `物料平衡流程已执行，但缺少${missing}，外压缩模型标记为待补输入；已保留方向证据：${abnormalText}。`
    }
    const estimatedNote = externalModel.status === 'demo_estimated' ? `；临时估算：${(externalModel.recoveredInputs || []).join('、')}` : ''
    return `已按外压缩模型复核：${modelOutput || 'EGOX、PAIR、GAN+LIN、TURBBY、FAR、CAR、LEV、AIR链式输出'}；方向证据：${abnormalText}${estimatedNote}。`
  }
  if (stageId === 'branch_detail') {
    const first = (buildLocalBranchRanking()[0] || {})
    return `已把识别结果和物料平衡证据送入故障树，当前优先分支：${first.branch || '待复核'}。`
  }
  return agentSummaryText.value
}
function buildAnalysisStepProcessItems(stageId, state) {
  if (state === 'pending') return []
  const result = activeResult.value
  const balance = result?.balance
  const shape = result?.ai705Primary || {}
  const rankRows = buildLocalBranchRanking()

  if (stageId === 'top_event') {
    return [
      { label: '输入', text: `AI705趋势窗口 ${activeWindowLabel.value}` },
      {
        label: '判断',
        text: `${shape.shapeText || '下凹形态'}；工作点 ${formatShapeNumber(shape.workpoint)}，谷底 ${formatShapeNumber(shape.minValue)}，下凹 ${formatShapeNumber(shape.dipDepth)}，恢复 ${formatPercent(shape.recoveryRatio)}。`
      },
      { label: '输出', text: `${levelText(result?.level)}；只负责确认是否形成轻/中/重氮塞，不在这一步判断原因。` }
    ]
  }

  if (stageId === 'material_balance') {
    const abnormal = balance?.outputs?.abnormal_checks || []
    const externalModel = balance?.outputs?.external_model || balance?.externalModel || {}
    const missingCore = externalModel.missingCoreInputs || []
    const recovered = externalModel.recoveredInputs || []
    const abnormalText = abnormal.length
      ? abnormal.slice(0, 4).map((item) => `${item.name || tagLabel(item.tag)}${item.directionText}`).join('、')
      : (balance?.staticApplicable === false ? '动态过程，静态平衡降级为提示' : '关键变量未超出同负荷合理范围')
    return [
      { label: '输入', text: '60分钟均值后的GOX、LIN、GAR、TEMP、TURBINE、FI702、FIC701、LIC701，并预留MS1201/MS1202分子筛状态修正。' },
      { label: '计算', text: balance?.formulaText || balanceVerification.value.equation },
      { label: '建模', text: (externalModel.steps || []).slice(0, 4).join(' → ') || 'Curve Fitting回归系数后续接入。' },
      { label: '输出', text: `${externalModel.primaryOutputText || balance?.summary || balanceVerification.value.result}；方向证据：${abnormalText}。` },
      { label: '缺项', text: missingCore.length ? missingCore.map((item) => item.label).join('、') : `Demo核心输入已满足${recovered.length ? `（${recovered.join('、')}）` : ''}；正式上线仍需回归系数、分子筛状态、V8-LIN估算和温度基准。` }
    ]
  }

  if (stageId === 'branch_detail') {
    const rankingText = rankRows
      .slice(0, 3)
      .map((item) => `${item.rank || '-'}.${item.branch || item.title || '分支'}：${item.status || item.support_level || '待复核'}${Number.isFinite(item.score) ? `(${item.score}分)` : ''}`)
      .join('；')
    return [
      { label: '输入', text: 'AI705主触发 + 物料平衡异常项 + 粗氩塔/主塔/空气系统联动测点。' },
      { label: '排序', text: rankingText || '等待故障树分支证据。' },
      { label: '输出', text: '把原因候选送入粗氩塔、主塔、空气系统、事件四类分支，不把物料平衡当作氮塞识别判据。' }
    ]
  }

  if (stageId === 'final_summary') {
    return [
      { label: '结论', text: agentConclusionText.value },
      { label: '依据', text: agentSummaryText.value },
      { label: '下一步', text: agentInspectionList.value.slice(0, 2).join('；') || '结合现场记录复核。' }
    ]
  }

  return []
}
const topEventHighlights = computed(() => topEventRows.value
  .filter((item) => !/未触发|排除/.test(item.status || ''))
  .slice(0, 4)
  .map((item) => ({
    label: item.item,
    status: item.status,
    text: item.description
  })))
const agentKeyMissingData = computed(() => {
  const rows = agentAnalysis.value?.key_missing_data?.length ? agentAnalysis.value.key_missing_data : buildLocalKeyMissingData()
  return rows.slice(0, 10).map((item) => ({
    data: item.data || item.name || item.tag || '缺失数据',
    node: item.node || item.node_id || '待映射节点',
    purpose: item.purpose || item.usage || item.reason || '用于补齐当前窗口判断所缺证据。'
  }))
})
const agentBasisNarratives = computed(() => {
  if (!activeResult.value) return []
  const items = [
    buildTagNarrative('AI705'),
    buildTagNarrative('AI701'),
    buildTagNarrative('FI702'),
    buildTagNarrative('FIQC701'),
    buildTagNarrative('FIC101'),
    buildBalanceNarrative()
  ].filter(Boolean)

  if (agentAnalysis.value?.basis?.length) {
    const textItems = agentAnalysis.value.basis
      .map((item) => formatBasisItem(item))
      .filter((item) => item && !looksLikeRawMetricSummary(item))
    if (textItems.length) {
      return Array.from(new Set([...textItems, ...items])).slice(0, 5)
    }
  }

  return Array.from(new Set(items)).slice(0, 5)
})
const agentFaultTreeSteps = computed(() => {
  const remoteSteps = agentAnalysis.value?.fault_tree_steps?.length
    ? agentAnalysis.value.fault_tree_steps
    : agentAnalysis.value?.fault_tree_guidance?.steps
  const source = remoteSteps?.length ? remoteSteps : buildLocalFaultTreeSteps()
  return source.slice(0, 4).map(normalizeFaultTreeStep)
})
const agentInspectionList = computed(() => {
  const dynamic = activeResult.value?.operatingMode?.dynamic
  const items = dynamic
    ? [
        '先按变负荷过程处理：判断空气量、氧气量、氮气量是否正在上升或下降。',
        '核对变负荷速度是否过快或过慢，并检查空气、氧气、氮气之间的调整节奏是否匹配。',
        '保留氮塞窗口前后趋势，重点排查负荷变化速度和产品抽取时序不协调。'
      ]
    : activeResult.value?.suspected
    ? [
        '进入稳态分块诊断：粗氩塔、主塔、空气系统和事件因素都要并行排查。',
        '粗氩塔重点看 FI702 是否偏高、FIC701 是否偏低，并补充粗氩塔阻力、液位和冷凝负荷。',
        '主塔重点看氧气多抽、氮气少抽、V3阀开过大，以及 AI701 长时间偏高或短时高高。',
        '空气系统重点看膨胀空气旁通量是否偏少，避免笼统写成膨胀空气异常。',
        '事件因素单独核对分子筛切换时间、切换是否平稳，以及氮塞是否发生在切换后较短时间内。'
      ]
    : [
        '继续观察 T0：若 AI705 后续达到本设备轻度标准，再进入氮塞复核。',
        '联看 FI702 是否偏高、FIC701 是否偏低，避免只按“流量异常”笼统判断。',
        '补充现场操作记录和分子筛切换记录，用于确认事件因素是否存在。'
      ]

  if (balanceVerification.value.level === 'warn') {
    items.push('物料平衡偏差已放大，建议同步排查进塔空气量与产品取出量扰动。')
  }
  if (balanceVerification.value.level === 'pending') {
    items.push('关键流量或操作记录仍不完整，建议补齐后再做复核。')
  }
  agentKeyMissingData.value.slice(0, 2).forEach((item) => {
    items.push(`补充 ${item.data}，用于确认 ${item.node} 节点：${item.purpose}`)
  })
  return Array.from(new Set(items)).slice(0, 6)
})
const expertConclusionCard = computed(() => {
  if (!agentAnalysis.value || !activeResult.value) return null
  const causeCards = supportedCauseCards.value.filter((card) => card.id !== 'none').slice(0, 2)
  const causeSummary = causeCards.length
    ? causeCards.map((card) => `${card.title}，${card.reason}`).join('；')
    : '当前未锁定单一主因，更像多因素共同扰动，仍需结合现场记录继续复核。'
  const actionSummary = agentInspectionList.value.slice(0, 3).join('；')
  const judgementSource = String(
    agentAnalysis.value?.final_conclusion
    || agentAnalysis.value?.conclusion
    || agentAnalysis.value?.llm_sentence
    || agentSummaryText.value
  ).trim()
  const judgement = judgementSource || '当前区间已完成原因分析，请结合下方证据和建议执行复核。'
  const headline = activeResult.value.suspected
    ? `本次区间判定为${levelText(activeResult.value.level)}，建议按氮塞异常处理。`
    : '本次区间未锁定明确氮塞，可先按波动事件继续观察。'
  return {
    headline,
    judgement,
    causeSummary,
    actionSummary: actionSummary || '建议先保留当前趋势窗口，并补齐现场操作记录后再复核。'
  }
})
const focusTreeCard = computed(() => {
  if (currentTraceFocusNode.value === 'T0') {
    return {
      id: 'T0',
      title: '氮塞顶事件',
      status: topEventJudgement.value.status || '待排查',
      reason: agentSummaryText.value,
      evidence: topEventHighlights.value
    }
  }
  return buildTreeNodeCard(currentTraceFocusNode.value)
})
const branchTreeCards = computed(() => agentLogicNodes.value
  .filter((node) => node.id !== focusTreeCard.value.id)
  .map((node) => buildTreeNodeCard(node.id))
  .filter((card) => card.evidence.length || !/暂不支持|排除/.test(card.status || ''))
  .slice(0, 4))
const pendingTreeNodes = computed(() => {
  const rows = []
  agentKeyMissingData.value.forEach((item) => {
    const nodeKeys = extractTreeNodeKeys(item.node)
    if (!nodeKeys.length) return
    rows.push({
      node: nodeKeys.join(' / '),
      label: item.data,
      text: item.purpose
    })
  })
  if (!rows.length) {
    return [{ node: 'T0', label: '当前路径', text: '暂未识别到新的待补节点，可继续结合现场记录复核。' }]
  }
  return rows.slice(0, 6)
})
const dataQualityRows = computed(() => {
  const selectedTagCount = selectedTags.value.length
  const availableTagCount = selectedTags.value.filter((tag) => rows.value.some((row) => Number.isFinite(row.metrics?.[tag]))).length
  return [
    {
      label: '当前显示范围',
      value: visibleRangeText.value,
      note: '用于核对当前趋势图覆盖的时间范围。'
    },
    {
      label: '当前显示点数',
      value: renderedPointText.value,
      note: '点数过少时建议扩大显示范围，点数过多时可缩小范围。'
    },
    {
      label: '重点测点覆盖',
      value: `${availableTagCount}/${selectedTagCount} 个测点可用`,
      note: availableTagCount === selectedTagCount ? '当前已选重点测点均有数据。' : '部分重点测点缺失，建议补齐后再复核。'
    },
    {
      label: '当前回看位置',
      value: streamProgressText.value,
      note: '用于对应现场记录或操作记录的时间点。'
    }
  ]
})
const caseHistoryRecords = computed(() => {
  return Object.entries(caseDecisions.value)
    .map(([id, record]) => {
      const item = typeof record === 'string'
        ? { value: record, label: id, note: '历史记录' }
        : record
      return {
        id,
        label: item.label || id,
        result: reviewText(item.value),
        note: item.note || '人工确认记录'
      }
    })
    .reverse()
})
const caseDecisionText = computed(() => {
  if (!caseDecision.value) return '尚未给出人工确认结果。'
  return {
    confirmed: '已人工确认：已选择区间符合氮塞特征。',
    excluded: '已人工排除：已选择区间不作为氮塞处理。',
    observe: '已标记继续观察：保持监视，等待后续区间变化。',
    supplement: '已标记补充数据：补齐现场记录后再次确认。',
    normal: '已标记为正常波动：已选择区间暂不作为异常处理。',
    record: '已标记补充现场记录：请补齐操作记录后再次确认。'
  }[caseDecision.value] || '尚未给出人工确认结果。'
})

const activeWindowPlugin = {
  id: 'active-window-band',
  beforeDatasetsDraw(targetChart) {
    const result = activeResult.value
    if (!result || !chartRows.value.length) return
    const visibleRows = chartRows.value
    mergedSuspectedBands.value
      .filter((item) => item.suspected && item.endMs >= visibleRows[0].timeMs && item.startMs <= visibleRows[visibleRows.length - 1].timeMs)
      .forEach((item) => {
        const bandStyle = getSuspectedBandStyle(resolveSuspectedBandLevel(item), item.active)
        drawWindowBand(targetChart, item, bandStyle.fill, bandStyle.stroke)
      })

    const shape = result.ai705Primary || {}
    if (Number.isFinite(shape.startMs) && Number.isFinite(shape.endMs)) {
      drawWindowBand(targetChart, { startMs: shape.startMs, endMs: shape.endMs }, 'rgba(14, 165, 233, 0.14)', 'rgba(14, 116, 144, 0.32)')
    }

    if (selectedTags.value.includes('AI705') && Number.isFinite(shape.workpoint)) {
      drawNormalBand(targetChart, shape)
    }
  },
  afterDraw(targetChart) {
    if (!chartRows.value.length || !selectedTags.value.includes('AI705')) return
    drawFixedReferenceLines(targetChart, 'AI705')
    const result = activeResult.value
    const shape = result?.ai705Primary || {}
    if (!result) return
    chartLabelLayout = createChartLabelLayout(targetChart)
    if (Number.isFinite(shape.workpoint)) {
      drawWorkpointLine(targetChart, shape, selectedSuspectedEvent.value)
    }
    if (Number.isFinite(shape.workpoint) && Number.isFinite(shape.valleyMs)) {
      drawShapeMarkers(targetChart, shape, selectedSuspectedEvent.value)
    }
    chartLabelLayout = null
  }
}

function drawFixedReferenceLines(chartInstance, tag) {
  const lines = preferredAxisRanges[tag]?.referenceLines || []
  if (!lines.length) return
  const area = chartInstance.chartArea
  const { ctx } = chartInstance
  ctx.save()
  lines.forEach((line) => {
    if (!Number.isFinite(line.value)) return
    const y = tag === 'AI705' ? ai705Y(chartInstance, line.value) : chartInstance.scales.y?.getPixelForValue(line.value)
    if (!Number.isFinite(y) || y < area.top || y > area.bottom) return
    ctx.beginPath()
    ctx.setLineDash([5, 4])
    ctx.strokeStyle = 'rgba(71, 85, 105, 0.48)'
    ctx.lineWidth = 1.3
    ctx.moveTo(area.left, y)
    ctx.lineTo(area.right, y)
    ctx.stroke()
  })
  ctx.restore()
}

function drawWindowBand(chartInstance, windowItem, fillStyle, strokeStyle) {
  const area = chartInstance.chartArea
  const startIndex = nearestVisibleRowIndex(windowItem.startMs)
  const endIndex = nearestVisibleRowIndex(windowItem.endMs)
  if (startIndex < 0 || endIndex < 0) return
  const left = chartInstance.scales.x.getPixelForValue(startIndex)
  const right = chartInstance.scales.x.getPixelForValue(Math.max(startIndex + 1, endIndex))
  const { ctx } = chartInstance
  ctx.save()
  ctx.fillStyle = fillStyle
  ctx.strokeStyle = strokeStyle
  ctx.lineWidth = 1
  ctx.fillRect(left, area.top, Math.max(2, right - left), area.bottom - area.top)
  ctx.strokeRect(left, area.top, Math.max(2, right - left), area.bottom - area.top)
  ctx.restore()
}

function resolveSuspectedBandLevel(windowItem) {
  if (windowItem?.level) return windowItem.level
  const match = suspectedEvents.value
    .filter((event) => event.endMs >= windowItem.startMs && event.startMs <= windowItem.endMs)
    .sort((a, b) => riskRank(b.level) - riskRank(a.level))[0]
  return match?.level || 'low'
}

function getSuspectedBandStyle(level, isActive = false) {
  const palette = {
    low: {
      fill: 'rgba(245, 158, 11, 0.12)',
      stroke: 'rgba(217, 119, 6, 0.34)',
    },
    medium: {
      fill: 'rgba(249, 115, 22, 0.13)',
      stroke: 'rgba(234, 88, 12, 0.36)',
    },
    high: {
      fill: 'rgba(220, 38, 38, 0.14)',
      stroke: 'rgba(185, 28, 28, 0.4)',
    },
  }
  const base = palette[level] || palette.low
  if (!isActive) return base
  return {
    fill: base.fill.replace(/0\.\d+\)/, level === 'high' ? '0.2)' : '0.18)'),
    stroke: base.stroke.replace(/0\.\d+\)/, level === 'high' ? '0.56)' : '0.48)'),
  }
}

async function handleChartStageClick(event) {
  if (!chart || !suspectedEvents.value.length || agentLoading.value) return
  const hit = findSuspectedEventAtPointer(event)
  if (!hit) {
    closeChartEventPrompt()
    return
  }
  await setActiveWindow(hit.event.index)
  const rect = chartStageRef.value?.getBoundingClientRect()
  const localX = rect ? event.clientX - rect.left : hit.x
  const localY = rect ? event.clientY - rect.top : hit.y
  chartEventPrompt.value = {
    event: hit.event,
    left: clamp(localX + 12, 8, Math.max(8, (rect?.width || 320) - 292)),
    top: clamp(localY + 12, 8, Math.max(8, (rect?.height || 220) - 172))
  }
  chartEventPromptCollapsed.value = true
  await nextTick()
  if (chartEventPrompt.value) {
    chartEventPrompt.value = {
      ...chartEventPrompt.value,
      ...clampChartEventPromptPosition(chartEventPrompt.value.left, chartEventPrompt.value.top)
    }
  }
}

function findSuspectedEventAtPointer(event) {
  const area = chart?.chartArea
  const stageRect = chartStageRef.value?.getBoundingClientRect()
  if (!area || !stageRect) return null
  const x = event.clientX - stageRect.left
  const y = event.clientY - stageRect.top
  if (x < area.left || x > area.right || y < area.top || y > area.bottom) return null
  const visibleRows = chartRows.value
  if (!visibleRows.length) return null
  const visibleStart = visibleRows[0].timeMs
  const visibleEnd = visibleRows[visibleRows.length - 1].timeMs
  const candidates = suspectedEvents.value
    .filter((item) => item.endMs >= visibleStart && item.startMs <= visibleEnd)
    .map((item) => {
      const startIndex = nearestVisibleRowIndex(item.startMs)
      const endIndex = nearestVisibleRowIndex(item.endMs)
      if (startIndex < 0 || endIndex < 0) return null
      const left = chart.scales.x.getPixelForValue(startIndex)
      const right = chart.scales.x.getPixelForValue(Math.max(startIndex + 1, endIndex))
      return {
        event: item,
        left: Math.min(left, right),
        right: Math.max(left, right)
      }
    })
    .filter(Boolean)
  const hit = candidates.find((item) => x >= item.left - 4 && x <= Math.max(item.left + 8, item.right + 4))
  return hit ? { ...hit, x, y } : null
}

function getChartEventPromptBounds() {
  const stageRect = chartStageRef.value?.getBoundingClientRect()
  const popoverRect = chartEventPopoverRef.value?.getBoundingClientRect()
  const width = popoverRect?.width || (chartEventPromptCollapsed.value ? 264 : 304)
  const height = popoverRect?.height || (chartEventPromptCollapsed.value ? 48 : 210)
  const stageWidth = stageRect?.width || 320
  const stageHeight = stageRect?.height || 220
  return {
    minLeft: 8,
    minTop: 8,
    maxLeft: Math.max(8, stageWidth - width - 8),
    maxTop: Math.max(8, stageHeight - height - 8)
  }
}

function clampChartEventPromptPosition(left, top) {
  const bounds = getChartEventPromptBounds()
  return {
    left: clamp(left, bounds.minLeft, bounds.maxLeft),
    top: clamp(top, bounds.minTop, bounds.maxTop)
  }
}

function startChartEventPromptDrag(event) {
  if (!chartEventPrompt.value || event.button !== 0) return
  const target = event.target
  if (target instanceof Element && target.closest('button, input, select, textarea, a')) return
  event.preventDefault()
  event.stopPropagation()
  chartEventPromptDrag = {
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startLeft: chartEventPrompt.value.left,
    startTop: chartEventPrompt.value.top
  }
  chartEventPromptDragging.value = true
  chartEventPopoverRef.value?.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', handleChartEventPromptDrag)
  window.addEventListener('pointerup', stopChartEventPromptDrag)
  window.addEventListener('pointercancel', stopChartEventPromptDrag)
  window.addEventListener('blur', stopChartEventPromptDrag)
}

function handleChartEventPromptDrag(event) {
  if (!chartEventPrompt.value || !chartEventPromptDrag) return
  const next = clampChartEventPromptPosition(
    chartEventPromptDrag.startLeft + event.clientX - chartEventPromptDrag.startClientX,
    chartEventPromptDrag.startTop + event.clientY - chartEventPromptDrag.startClientY
  )
  chartEventPrompt.value = {
    ...chartEventPrompt.value,
    ...next
  }
}

function stopChartEventPromptDrag(event) {
  if (chartEventPromptDrag?.pointerId && event?.pointerId === chartEventPromptDrag.pointerId) {
    chartEventPopoverRef.value?.releasePointerCapture?.(event.pointerId)
  }
  chartEventPromptDrag = null
  chartEventPromptDragging.value = false
  window.removeEventListener('pointermove', handleChartEventPromptDrag)
  window.removeEventListener('pointerup', stopChartEventPromptDrag)
  window.removeEventListener('pointercancel', stopChartEventPromptDrag)
  window.removeEventListener('blur', stopChartEventPromptDrag)
}

function closeChartEventPrompt() {
  restoreChartEventFocus()
  stopChartEventPromptDrag()
  chartEventPrompt.value = null
  chartEventPromptCollapsed.value = true
}

function toggleChartEventPromptCollapsed() {
  if (!chartEventPrompt.value) return
  chartEventPromptCollapsed.value = !chartEventPromptCollapsed.value
  nextTick(() => {
    if (!chartEventPrompt.value) return
    chartEventPrompt.value = {
      ...chartEventPrompt.value,
      ...clampChartEventPromptPosition(chartEventPrompt.value.left, chartEventPrompt.value.top)
    }
  })
}

function getCurrentStreamRange() {
  const endMs = streamCursorIndex.value || demoMaxTimeMs.value
  const durationMs = streamHorizonHours.value * 60 * 60 * 1000
  const startMs = Math.max(demoMinTimeMs.value, endMs - durationMs)
  return {
    startMs,
    endMs,
  }
}

function restoreChartEventFocus() {
  const snapshot = chartEventFocusState.value
  if (!snapshot) return false
  chartEventFocusState.value = null
  applyStreamRange(snapshot.startMs, snapshot.endMs, false, { preserveRecognition: true })
  return true
}

function toggleChartEventFocus() {
  const event = chartEventPrompt.value?.event
  if (!event || !demoRowCount.value) return
  if (chartEventFocusState.value?.eventId === event.id) {
    restoreChartEventFocus()
    return
  }
  const currentRange = getCurrentStreamRange()
  const durationMs = Math.max(60 * 1000, event.endMs - event.startMs)
  const paddingMs = clamp(durationMs * 0.6, 10 * 60 * 1000, 2 * 60 * 60 * 1000)
  chartEventFocusState.value = {
    eventId: event.id,
    startMs: currentRange.startMs,
    endMs: currentRange.endMs,
  }
  applyStreamRange(event.startMs - paddingMs, event.endMs + paddingMs, false, { preserveRecognition: true })
}

async function confirmChartEventAnalysis() {
  const event = chartEventPrompt.value?.event
  if (!event) return
  closeChartEventPrompt()
  await analyzeEvent(event)
}

function drawNormalBand(chartInstance, shape) {
  const band = shape.normalBand || {}
  if (!Number.isFinite(band.lower) || !Number.isFinite(band.upper)) return
  const area = chartInstance.chartArea
  const rawUpperY = ai705Y(chartInstance, band.upper)
  const rawLowerY = ai705Y(chartInstance, band.lower)
  if (!Number.isFinite(rawUpperY) || !Number.isFinite(rawLowerY)) return
  const upperY = clamp(rawUpperY, area.top, area.bottom)
  const lowerY = clamp(rawLowerY, area.top, area.bottom)
  const top = Math.min(upperY, lowerY)
  const height = Math.max(2, Math.abs(lowerY - upperY))
  const { ctx } = chartInstance
  ctx.save()
  ctx.fillStyle = 'rgba(14, 165, 233, 0.08)'
  ctx.fillRect(area.left, top, area.right - area.left, height)
  ctx.setLineDash([6, 4])
  ctx.strokeStyle = 'rgba(14, 116, 144, 0.74)'
  ctx.lineWidth = 1.2
  ;[upperY, lowerY].forEach((y) => {
    ctx.beginPath()
    ctx.moveTo(area.left, y)
    ctx.lineTo(area.right, y)
    ctx.stroke()
  })
  ctx.setLineDash([])
  ctx.restore()
}

function drawWorkpointLine(chartInstance, shape, eventWindow = null) {
  const area = chartInstance.chartArea
  const rawY = ai705Y(chartInstance, shape.workpoint)
  if (!Number.isFinite(rawY)) return
  const y = clamp(rawY, area.top, area.bottom)
  const { ctx } = chartInstance
  ctx.save()
  ctx.setLineDash([6, 5])
  ctx.strokeStyle = '#f97316'
  ctx.lineWidth = 1.8
  ctx.beginPath()
  ctx.moveTo(area.left, y)
  ctx.lineTo(area.right, y)
  ctx.stroke()
  ctx.setLineDash([])
  const eventStartX = Number.isFinite(eventWindow?.startMs) ? timeToChartX(chartInstance, eventWindow.startMs) : NaN
  const labelX = Number.isFinite(eventStartX) ? eventStartX + 8 : area.left + 8
  drawChartLabel(ctx, `基线 ${formatShapeNumber(shape.workpoint)}`, labelX, y - 17, '#ea580c', area, { anchorX: labelX, anchorY: y })
  ctx.restore()
}

function drawShapeMarkers(chartInstance, shape, eventWindow = null) {
  drawEventWindowLabel(chartInstance, shape, eventWindow)
  const startMs = Number.isFinite(eventWindow?.startMs) ? eventWindow.startMs : shape.startMs
  const endMs = Number.isFinite(eventWindow?.endMs) ? eventWindow.endMs : shape.endMs
  const markerItems = [
    { timeMs: startMs, label: '开始', color: '#991b1b', offsetY: 30 },
    { timeMs: shape.valleyMs, label: '谷底', color: '#2563eb', offsetY: 52 },
    { timeMs: endMs, label: '结束', color: '#991b1b', offsetY: 30 }
  ]
  markerItems.forEach((item) => drawVerticalMarker(chartInstance, item))
  drawValleyDots(chartInstance, shape)
  drawDipArrow(chartInstance, shape)
}

function drawEventWindowLabel(chartInstance, shape, eventWindow = null) {
  const startMs = Number.isFinite(eventWindow?.startMs) ? eventWindow.startMs : shape.startMs
  const endMs = Number.isFinite(eventWindow?.endMs) ? eventWindow.endMs : shape.endMs
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return
  const startX = timeToChartX(chartInstance, startMs)
  const endX = timeToChartX(chartInstance, endMs)
  if (!Number.isFinite(startX) || !Number.isFinite(endX)) return
  const area = chartInstance.chartArea
  const centerX = (startX + endX) / 2
  const label = eventWindow?.eventNo
    ? `${eventWindow.eventNo} ${levelText(eventWindow.level)}`
    : `${levelText(activeResult.value?.level)}`
  const { ctx } = chartInstance
  ctx.save()
  drawChartLabel(ctx, label, centerX - 56, area.top + 8, '#991b1b', area, { anchorX: centerX, anchorY: area.top + 8 })
  ctx.restore()
}

function drawVerticalMarker(chartInstance, item) {
  if (!Number.isFinite(item.timeMs)) return
  const x = timeToChartX(chartInstance, item.timeMs)
  if (!Number.isFinite(x)) return
  const area = chartInstance.chartArea
  const { ctx } = chartInstance
  ctx.save()
  ctx.strokeStyle = item.color
  ctx.lineWidth = 1.2
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  ctx.moveTo(x, area.top)
  ctx.lineTo(x, area.bottom)
  ctx.stroke()
  ctx.setLineDash([])
  const labelX = item.timeMs >= chartRows.value[chartRows.value.length - 1]?.timeMs ? x - 36 : x + 4
  drawChartLabel(ctx, item.label, labelX, area.top + (item.offsetY || 8), item.color, area, { anchorX: x, anchorY: area.top + (item.offsetY || 8) })
  ctx.restore()
}

function drawValleyDots(chartInstance, shape) {
  const valleys = Array.isArray(shape.valleys) ? shape.valleys.slice(0, 5) : []
  const { ctx } = chartInstance
  ctx.save()
  valleys.forEach((item, index) => {
    const x = timeToChartX(chartInstance, item.timeMs)
    const y = ai705Y(chartInstance, item.value)
    if (!Number.isFinite(x) || !Number.isFinite(y)) return
    ctx.fillStyle = '#991b1b'
    ctx.beginPath()
    ctx.arc(x, y, 3.5, 0, Math.PI * 2)
    ctx.fill()
    if (valleys.length > 1) {
      drawChartLabel(ctx, String(index + 1), x + 5, y - 18, '#991b1b', chartInstance.chartArea, { anchorX: x, anchorY: y })
    }
  })
  ctx.restore()
}

function drawDipArrow(chartInstance, shape) {
  if (!Number.isFinite(shape.valleyMs) || !Number.isFinite(shape.workpoint) || !Number.isFinite(shape.minValue)) return
  const area = chartInstance.chartArea
  const rawX = timeToChartX(chartInstance, shape.valleyMs)
  const rawWorkpointY = ai705Y(chartInstance, shape.workpoint)
  const rawValleyY = ai705Y(chartInstance, shape.minValue)
  if (!Number.isFinite(rawX) || !Number.isFinite(rawWorkpointY) || !Number.isFinite(rawValleyY)) return
  const x = clamp(rawX + 18, area.left + 18, area.right - 18)
  const workpointY = clamp(rawWorkpointY, area.top, area.bottom)
  const valleyY = clamp(rawValleyY, area.top, area.bottom)
  if (Math.abs(valleyY - workpointY) < 8) return
  const { ctx } = chartInstance
  ctx.save()
  ctx.strokeStyle = '#dc2626'
  ctx.fillStyle = '#dc2626'
  ctx.lineWidth = 1.3
  ctx.beginPath()
  ctx.moveTo(x, workpointY)
  ctx.lineTo(x, valleyY)
  ctx.stroke()
  drawArrowHead(ctx, x, valleyY, valleyY > workpointY ? 1 : -1)
  drawChartLabel(ctx, `下凹 ${formatShapeNumber(shape.dipDepth)}`, x + 5, (workpointY + valleyY) / 2 - 8, '#dc2626', area, { anchorX: x, anchorY: (workpointY + valleyY) / 2 })
  ctx.restore()
}

function drawArrowHead(ctx, x, y, direction) {
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x - 4, y - 7 * direction)
  ctx.lineTo(x + 4, y - 7 * direction)
  ctx.closePath()
  ctx.fill()
}

function createChartLabelLayout(chartInstance) {
  return {
    area: chartInstance.chartArea,
    boxes: []
  }
}

function normalizeLabelBounds(rect, bounds) {
  if (!bounds) return rect
  const minX = bounds.left + 2
  const maxX = Math.max(minX, bounds.right - rect.width - 2)
  const minY = bounds.top + 2
  const maxY = Math.max(minY, bounds.bottom - rect.height - 2)
  return {
    ...rect,
    x: clamp(rect.x, minX, maxX),
    y: clamp(rect.y, minY, maxY)
  }
}

function labelRectsOverlap(first, second, gap = 5) {
  return !(
    first.x + first.width + gap <= second.x ||
    second.x + second.width + gap <= first.x ||
    first.y + first.height + gap <= second.y ||
    second.y + second.height + gap <= first.y
  )
}

function buildLabelCandidates(x, y, width, height, bounds) {
  const stepY = height + 5
  const stepX = Math.min(width + 10, 96)
  const rawCandidates = [
    { x, y, cost: 0 },
    { x, y: y - stepY, cost: 10 },
    { x, y: y + stepY, cost: 12 },
    { x: x - stepX, y, cost: 14 },
    { x: x + stepX, y, cost: 14 },
    { x: x - stepX, y: y - stepY, cost: 22 },
    { x: x + stepX, y: y - stepY, cost: 22 },
    { x: x - stepX, y: y + stepY, cost: 24 },
    { x: x + stepX, y: y + stepY, cost: 24 },
    { x, y: y - stepY * 2, cost: 28 },
    { x, y: y + stepY * 2, cost: 30 },
    { x: x - stepX * 1.4, y: y - stepY * 2, cost: 36 },
    { x: x + stepX * 1.4, y: y - stepY * 2, cost: 36 },
    { x: x - stepX * 1.4, y: y + stepY * 2, cost: 38 },
    { x: x + stepX * 1.4, y: y + stepY * 2, cost: 38 }
  ]

  if (bounds) {
    const rows = []
    const topLimit = Math.min(bounds.bottom - height - 2, bounds.top + 132)
    for (let rowY = bounds.top + 6; rowY <= topLimit; rowY += stepY) rows.push(rowY)
    rows.forEach((rowY, rowIndex) => {
      rawCandidates.push({ x, y: rowY, cost: 44 + rowIndex * 4 })
      rawCandidates.push({ x: x - stepX, y: rowY, cost: 48 + rowIndex * 4 })
      rawCandidates.push({ x: x + stepX, y: rowY, cost: 48 + rowIndex * 4 })
    })
  }

  const seen = new Set()
  return rawCandidates
    .map((item) => normalizeLabelBounds({ ...item, width, height }, bounds))
    .filter((item) => {
      const key = `${Math.round(item.x)}:${Math.round(item.y)}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function placeChartLabel(preferredRect, bounds = null) {
  if (!chartLabelLayout) return normalizeLabelBounds(preferredRect, bounds)
  const candidates = buildLabelCandidates(preferredRect.x, preferredRect.y, preferredRect.width, preferredRect.height, bounds)
  if (bounds) {
    const gridStepY = preferredRect.height + 5
    const gridStepX = Math.max(42, Math.min(preferredRect.width * 0.7, 86))
    for (let rowY = bounds.top + 6; rowY <= bounds.bottom - preferredRect.height - 2; rowY += gridStepY) {
      for (let colX = bounds.left + 6; colX <= bounds.right - preferredRect.width - 2; colX += gridStepX) {
        candidates.push(normalizeLabelBounds({
          x: colX,
          y: rowY,
          width: preferredRect.width,
          height: preferredRect.height,
          cost: 90
        }, bounds))
      }
    }
  }
  const scored = candidates
    .map((item) => ({
      ...item,
      overlapCount: chartLabelLayout.boxes.filter((box) => labelRectsOverlap(item, box)).length,
      distance: Math.abs(item.x - preferredRect.x) + Math.abs(item.y - preferredRect.y)
    }))
    .sort((a, b) => (a.overlapCount - b.overlapCount) || (a.cost - b.cost) || (a.distance - b.distance))
  const placed = scored[0] || normalizeLabelBounds(preferredRect, bounds)
  chartLabelLayout.boxes.push(placed)
  return placed
}

function drawLabelLeader(ctx, anchorX, anchorY, rect, color) {
  if (!Number.isFinite(anchorX) || !Number.isFinite(anchorY)) return
  const centerX = rect.x + rect.width / 2
  const centerY = rect.y + rect.height / 2
  if (Math.abs(centerX - anchorX) + Math.abs(centerY - anchorY) < 24) return
  const edgeX = clamp(anchorX, rect.x, rect.x + rect.width)
  const edgeY = clamp(anchorY, rect.y, rect.y + rect.height)
  ctx.save()
  ctx.strokeStyle = color
  ctx.globalAlpha = 0.38
  ctx.lineWidth = 1
  ctx.setLineDash([2, 3])
  ctx.beginPath()
  ctx.moveTo(anchorX, anchorY)
  ctx.lineTo(edgeX, edgeY)
  ctx.stroke()
  ctx.restore()
}

function drawChartLabel(ctx, text, x, y, color, bounds = null, options = {}) {
  const paddingX = 5
  const paddingY = 3
  ctx.font = '700 11px sans-serif'
  const width = ctx.measureText(text).width + paddingX * 2
  const height = 18
  const placed = placeChartLabel({ x, y, width, height }, bounds)
  const safeX = placed.x
  const safeY = placed.y
  drawLabelLeader(ctx, options.anchorX, options.anchorY, placed, color)
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = 'rgba(255, 255, 255, 0.92)'
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.45)'
  ctx.lineWidth = 1
  ctx.beginPath()
  drawRoundedRectPath(ctx, safeX, safeY, width, height, 4)
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = color
  ctx.fillText(text, safeX + paddingX, safeY + height - paddingY - 3)
}

function drawRoundedRectPath(ctx, x, y, width, height, radius) {
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, width, height, radius)
    return
  }
  const safeRadius = Math.min(radius, width / 2, height / 2)
  ctx.moveTo(x + safeRadius, y)
  ctx.lineTo(x + width - safeRadius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + safeRadius)
  ctx.lineTo(x + width, y + height - safeRadius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height)
  ctx.lineTo(x + safeRadius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - safeRadius)
  ctx.lineTo(x, y + safeRadius)
  ctx.quadraticCurveTo(x, y, x + safeRadius, y)
  ctx.closePath()
}

function nearestVisibleRowIndex(timeMs) {
  const visibleRows = chartRows.value
  if (!visibleRows.length) return -1
  if (timeMs <= visibleRows[0].timeMs) return 0
  const lastIndex = visibleRows.length - 1
  if (timeMs >= visibleRows[lastIndex].timeMs) return lastIndex
  const index = lowerBoundTime(visibleRows, timeMs)
  return clamp(index, 0, lastIndex)
}

function timeToChartX(chartInstance, timeMs) {
  const index = nearestVisibleRowIndex(timeMs)
  if (index < 0) return NaN
  return chartInstance.scales.x.getPixelForValue(index)
}

function ai705Y(chartInstance, rawValue) {
  if (!Number.isFinite(rawValue)) return NaN
  const dataset = chartInstance.data.datasets.find((item) => item.tag === 'AI705')
  if (!dataset) return NaN
  const yScale = chartInstance.scales[dataset.yAxisID || 'y'] || chartInstance.scales.y
  if (!yScale) return NaN
  if (chartDisplayMode.value === 'normalized') {
    const fixedBounds = dataset.normalizationBounds || fixedTagYBounds.value?.[dataset.tag]
    const numericValues = (dataset.rawData || []).filter(Number.isFinite)
    if (!numericValues.length && (!Number.isFinite(fixedBounds?.min) || !Number.isFinite(fixedBounds?.max))) return NaN
    const minValue = Number.isFinite(fixedBounds?.min) ? fixedBounds.min : Math.min(...numericValues)
    const maxValue = Number.isFinite(fixedBounds?.max) ? fixedBounds.max : Math.max(...numericValues)
    const normalized = maxValue === minValue ? 0.5 : (rawValue - minValue) / (maxValue - minValue)
    return yScale.getPixelForValue(normalized)
  }
  return yScale.getPixelForValue(rawValue)
}

onMounted(() => {
  observeChartBox()
  initScanWorker()
  loadDemoData()
})

onBeforeUnmount(() => {
  stopPlayback()
  if (refreshTimer) window.clearTimeout(refreshTimer)
  stopLlmSentence()
  stopChartEventPromptDrag()
  resizeObserver?.disconnect()
  scanWorker?.terminate()
  chart?.destroy()
})

watch([selectedTags, activeResult, chartRows, chartDisplayMode, analysisModeActive, fixedChartYBounds, fixedTagYBounds], () => {
  nextTick(renderChart)
}, { deep: true })

watch(showTrendOverlay, () => {
  nextTick(renderChart)
})

async function loadDemoData() {
  stopPlayback()
  selectedDemoCases.value = []
  demoSummaryRows.value = []
  demoDetailRows.value = []
  activeDemoEventId.value = ''
  message.value = '正在整理历史数据，请稍候...'
  try {
    const metaResponse = await fetch('/api/nitrogen-demo/meta')
    const metaPayload = await metaResponse.json()
    if (!metaPayload.success) throw new Error(metaPayload.error || 'SQLite 元信息读取失败')
    const meta = metaPayload.data
    demoRowCount.value = meta.row_count || 0
    demoMinTimeMs.value = meta.min_time_ms || 0
    demoMaxTimeMs.value = meta.max_time_ms || 0
    globalMetricBounds.value = meta.metric_bounds || {}
    fixedMetricBounds.value = normalizeMetricBounds(meta.metric_bounds || {})
    usingSqliteApi.value = true
    streamCursorIndex.value = getInitialCursorIndex()
    dataSourceLabel.value = '历史数据库'
    await fetchDemoWindow()
    message.value = `历史数据已加载，当前显示范围已更新。`
  } catch (error) {
    usingSqliteApi.value = false
    globalMetricBounds.value = {}
    message.value = `${error.message}，正在切换到本地示例数据。`
    const response = await fetch(defaultDataUrl)
    if (!response.ok) throw new Error(`默认数据读取失败：${response.status}`)
    localArchiveRows.value = response.body
      ? await normalizeCsvReadable(response.body, Number(response.headers.get('content-length')) || 0)
      : normalizeCsvText(await response.text())
    fixedMetricBounds.value = calcMetricBoundsFromRows(localArchiveRows.value)
    demoRowCount.value = localArchiveRows.value.length
    demoMinTimeMs.value = localArchiveRows.value[0]?.timeMs || 0
    demoMaxTimeMs.value = localArchiveRows.value[localArchiveRows.value.length - 1]?.timeMs || 0
    streamCursorIndex.value = getInitialCursorIndex()
    refreshLocalWindow()
    dataSourceLabel.value = '本地示例数据'
  }
  resetDiagnosisFlow()
}

async function loadSelectedDemoPackage() {
  try {
    const response = await fetch('/api/nitrogen-demo-selected/manifest')
    if (!response.ok) throw new Error(`精选病例清单读取失败：${response.status}`)
    const payload = await response.json()
    if (!payload.success) throw new Error(payload.error || '精选病例清单读取失败')
    const data = payload.data || {}
    selectedDemoCases.value = data.demo_cases || []
    demoSummaryRows.value = data.summary || []
    demoDetailRows.value = data.detail || []
    activeDemoEventId.value = data.default_case || selectedDemoCases.value[0]?.event_id || ''
    if (!activeDemoEventId.value) throw new Error('精选病例为空')
    await loadSelectedDemoCase(activeDemoEventId.value)
    return true
  } catch (error) {
    selectedDemoCases.value = []
    demoSummaryRows.value = []
    demoDetailRows.value = []
    activeDemoEventId.value = ''
    message.value = `${error.message}，准备回退到历史数据。`
    return false
  }
}

async function selectDemoCase(eventId) {
  if (!eventId || eventId === activeDemoEventId.value) return
  await loadSelectedDemoCase(eventId)
}

async function loadSelectedDemoCase(eventId) {
  const caseItem = selectedDemoCases.value.find((item) => item.event_id === eventId)
  if (!caseItem) return
  stopPlayback()
  const { rows: parsedRows, resolutionLabel, sourcePath } = await loadSelectedDemoRows(caseItem, eventId)
  localArchiveRows.value = parsedRows
  archiveRows.value = parsedRows
  localDataResolution.value = resolutionLabel
  usingSqliteApi.value = false
  globalMetricBounds.value = {}
  fixedMetricBounds.value = calcMetricBoundsFromRows(parsedRows)
  activeDemoEventId.value = eventId
  demoRowCount.value = parsedRows.length
  demoMinTimeMs.value = parsedRows[0]?.timeMs || 0
  demoMaxTimeMs.value = parsedRows[parsedRows.length - 1]?.timeMs || 0
  streamCursorIndex.value = demoMaxTimeMs.value
  dataSourceLabel.value = `${eventId} 精选病例 ${resolutionLabel}`
  resetDiagnosisFlow()
  message.value = `${eventId} 已加载：${caseItem.case_type}，当前使用 ${sourcePath}。请点击“识别氮塞”。`
}

async function loadSelectedDemoRows(caseItem, eventId) {
  const candidates = [
    { path: caseItem.raw_5s_file, label: '5s' },
    { path: caseItem.resampled_1min_file, label: '1min' },
  ].filter((item) => item.path)
  let lastError = ''

  for (const candidate of candidates) {
    const response = await fetch(`${selectedDemoFileBaseUrl}/${candidate.path}`)
    if (!response.ok) {
      lastError = `${candidate.path} 读取失败：${response.status}`
      continue
    }
    const parsedRows = normalizeCsvText(await response.text())
    if (parsedRows.length) {
      return {
        rows: parsedRows,
        resolutionLabel: candidate.label,
        sourcePath: candidate.path,
      }
    }
    lastError = `${candidate.path} 无有效数据`
  }

  throw new Error(`${eventId} 事件窗口读取失败：${lastError || '未找到可用窗口文件'}`)
}

async function fetchDemoWindow() {
  if (!usingSqliteApi.value || !demoRowCount.value) return
  ensureCursorCanCoverHorizon()
  const endMs = streamCursorIndex.value
  const startMs = Math.max(demoMinTimeMs.value, endMs - streamHorizonHours.value * 60 * 60 * 1000)
  const params = new URLSearchParams({
    start_ms: String(startMs),
    end_ms: String(endMs),
    max_points: String(maxVisibleRows.value),
  })
  const response = await fetch(`/api/nitrogen-demo/data?${params.toString()}`)
  const payload = await response.json()
  if (!payload.success) throw new Error(payload.error || 'SQLite 数据查询失败')
  archiveRows.value = normalizeApiRows(payload.data.rows || [])
  primeFixedMetricBoundsFromRows(archiveRows.value)
}

function refreshLocalWindow() {
  if (usingSqliteApi.value || !localArchiveRows.value.length) return
  ensureCursorCanCoverHorizon()
  const endMs = streamCursorIndex.value
  const startMs = Math.max(demoMinTimeMs.value, endMs - streamHorizonHours.value * 60 * 60 * 1000)
  const startIndex = lowerBoundTime(localArchiveRows.value, startMs)
  const endIndex = lowerBoundTime(localArchiveRows.value, endMs)
  const visibleRows = localArchiveRows.value.slice(startIndex, Math.min(endIndex + 1, localArchiveRows.value.length))
  const relaxedLimit = localDataResolution.value === '5s'
    ? Math.max(maxVisibleRows.value * 4, 8000)
    : maxVisibleRows.value
  archiveRows.value = sampleRows(visibleRows, relaxedLimit)
}

async function handleFileSelect(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const parsedRows = file.name.toLowerCase().endsWith('.csv')
      ? await normalizeCsvReadable(file.stream(), file.size)
      : await parseExcel(file)
    localArchiveRows.value = Array.isArray(parsedRows) && parsedRows[0]?.metrics ? parsedRows : normalizeRows(parsedRows)
    localDataResolution.value = 'default'
    usingSqliteApi.value = false
    globalMetricBounds.value = {}
    fixedMetricBounds.value = calcMetricBoundsFromRows(localArchiveRows.value)
    demoRowCount.value = localArchiveRows.value.length
    demoMinTimeMs.value = localArchiveRows.value[0]?.timeMs || 0
    demoMaxTimeMs.value = localArchiveRows.value[localArchiveRows.value.length - 1]?.timeMs || 0
    streamCursorIndex.value = getInitialCursorIndex()
    refreshLocalWindow()
    dataSourceLabel.value = file.name
    resetDiagnosisFlow()
    message.value = `数据导入完成，当前显示最近 ${streamHorizonHours.value} 小时。请点击“识别氮塞”。`
  } catch (error) {
    message.value = `导入失败：${error.message}`
  } finally {
    event.target.value = ''
  }
}

async function parseExcel(file) {
  const XLSX = await loadXlsx()
  const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' })
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  return XLSX.utils.sheet_to_json(sheet, { defval: '' })
}

function loadXlsx() {
  if (window.XLSX) return Promise.resolve(window.XLSX)
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js'
    script.onload = () => resolve(window.XLSX)
    script.onerror = () => reject(new Error('Excel解析库加载失败，请先导入CSV。'))
    document.head.appendChild(script)
  })
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean)
  if (!lines.length) return []
  const headers = splitCsvLine(lines[0]).map((item) => item.trim())
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line)
    return headers.reduce((row, key, index) => {
      row[key] = values[index] ?? ''
      return row
    }, {})
  })
}

function normalizeCsvText(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean)
  if (!lines.length) return []
  const headers = splitCsvLine(lines[0]).map((item) => item.trim())
  const timeIndex = guessTimeIndex(headers)
  const columnIndexMap = buildColumnIndexMap(headers)
  const normalized = []

  for (let index = 1; index < lines.length; index += 1) {
    const values = splitCsvLine(lines[index])
    const timeMs = parseTime(values[timeIndex])
    if (!Number.isFinite(timeMs)) continue
    const metrics = Object.fromEntries(
      availableTags.map((tag) => [tag, readMetricFromValues(values, columnIndexMap[tag])])
    )
    metrics.BALANCE = calcMaterialBalanceFromValues(metrics, values, columnIndexMap)
    normalized.push({
      timeMs,
      time: formatTime(timeMs),
      metrics
    })
  }

  return normalized.sort((a, b) => a.timeMs - b.timeMs)
}

async function normalizeCsvReadable(readable, totalBytes = 0) {
  const reader = readable.getReader()
  const decoder = new TextDecoder('utf-8')
  const normalized = []
  let buffer = ''
  let headers = null
  let timeIndex = 0
  let columnIndexMap = null
  let loadedBytes = 0
  let lastProgress = 0

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    loadedBytes += value.byteLength
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''

    for (const line of lines) {
      processCsvLine(line)
    }

    if (totalBytes) {
      const progress = Math.floor((loadedBytes / totalBytes) * 100)
      if (progress >= lastProgress + 10) {
        lastProgress = progress
        message.value = `正在读取完整真实数据 ${progress}%...`
        await nextTick()
      }
    }
  }

  const tail = buffer + decoder.decode()
  if (tail.trim()) processCsvLine(tail)
  return normalized.sort((a, b) => a.timeMs - b.timeMs)

  function processCsvLine(line) {
    if (!line.trim()) return
    if (!headers) {
      headers = splitCsvLine(line).map((item) => item.trim())
      timeIndex = guessTimeIndex(headers)
      columnIndexMap = buildColumnIndexMap(headers)
      return
    }
    const values = splitCsvLine(line)
    const timeMs = parseTime(values[timeIndex])
    if (!Number.isFinite(timeMs)) return
    const metrics = Object.fromEntries(
      availableTags.map((tag) => [tag, readMetricFromValues(values, columnIndexMap[tag])])
    )
    metrics.BALANCE = calcMaterialBalanceFromValues(metrics, values, columnIndexMap)
    normalized.push({
      timeMs,
      time: formatTime(timeMs),
      metrics
    })
  }
}

function splitCsvLine(line) {
  const cells = []
  let current = ''
  let quoted = false
  for (const char of line) {
    if (char === '"') quoted = !quoted
    else if (char === ',' && !quoted) {
      cells.push(current)
      current = ''
    } else current += char
  }
  cells.push(current)
  return cells
}

function normalizeRows(rawRows) {
  const timeKey = guessTimeKey(Object.keys(rawRows[0] || {}))
  const keys = Object.keys(rawRows[0] || {})
  const columnMap = buildColumnMap(keys)
  return rawRows
    .map((row) => {
      const timeMs = parseTime(row[timeKey])
      const metrics = Object.fromEntries(availableTags.map((tag) => [tag, readMetric(row, columnMap[tag])]))
      metrics.BALANCE = calcMaterialBalance(metrics, row, columnMap)
      return {
        timeMs,
        time: formatTime(timeMs),
        metrics
      }
    })
    .filter((row) => Number.isFinite(row.timeMs))
    .sort((a, b) => a.timeMs - b.timeMs)
}

function normalizeApiRows(apiRows) {
  return apiRows.map((row) => ({
    ...row,
    time: formatTime(row.timeMs)
  }))
}

function buildColumnMap(keys) {
  return Object.fromEntries(
    Object.entries(tagAliases).map(([tag, aliases]) => [tag, findColumn(keys, aliases)])
  )
}

function buildColumnIndexMap(keys) {
  return Object.fromEntries(
    Object.entries(tagAliases).map(([tag, aliases]) => [tag, findColumnIndex(keys, aliases)])
  )
}

function findColumn(keys, aliases) {
  const normalizedAliases = aliases.map((item) => item.toLowerCase())
  return keys.find((key) => {
    const normalizedKey = key.toLowerCase()
    return normalizedAliases.some((alias) => (
      normalizedKey === alias ||
      normalizedKey.includes(`#${alias.toLowerCase()}`) ||
      normalizedKey.includes(`#${alias.toLowerCase()}.`) ||
      normalizedKey.includes(alias.toLowerCase())
    ))
  }) || ''
}

function findColumnIndex(keys, aliases) {
  const normalizedAliases = aliases.map((item) => item.toLowerCase())
  return keys.findIndex((key) => {
    const normalizedKey = key.toLowerCase()
    return normalizedAliases.some((alias) => (
      normalizedKey === alias ||
      normalizedKey.includes(`#${alias.toLowerCase()}`) ||
      normalizedKey.includes(`#${alias.toLowerCase()}.`) ||
      normalizedKey.includes(alias.toLowerCase())
    ))
  })
}

function readMetric(row, key) {
  return key ? toNumber(row[key]) : NaN
}

function readMetricFromValues(values, index) {
  return index >= 0 ? toNumber(values[index]) : NaN
}

function calcMaterialBalance(metrics, row, columnMap) {
  const airIn = metrics.FIC101
  const productO2 = metrics.FIQC102
  const productN2 = readMetric(row, columnMap.PRODUCT_N2)
  const liquidN2 = readMetric(row, columnMap.LIQUID_N2)
  const mediumN2 = readMetric(row, columnMap.MEDIUM_N2)
  const argonFlow = metrics.FI702
  const validOutputs = [productO2, productN2, liquidN2, mediumN2, argonFlow].filter(Number.isFinite)
  if (!Number.isFinite(airIn) || airIn === 0 || validOutputs.length < 2) return NaN
  const outputTotal = validOutputs.reduce((total, value) => total + value, 0)
  return ((airIn - outputTotal) / airIn) * 100
}

function calcMaterialBalanceFromValues(metrics, values, columnIndexMap) {
  const airIn = metrics.FIC101
  const productO2 = metrics.FIQC102
  const productN2 = readMetricFromValues(values, columnIndexMap.PRODUCT_N2)
  const liquidN2 = readMetricFromValues(values, columnIndexMap.LIQUID_N2)
  const mediumN2 = readMetricFromValues(values, columnIndexMap.MEDIUM_N2)
  const argonFlow = metrics.FI702
  const validOutputs = [productO2, productN2, liquidN2, mediumN2, argonFlow].filter(Number.isFinite)
  if (!Number.isFinite(airIn) || airIn === 0 || validOutputs.length < 2) return NaN
  const outputTotal = validOutputs.reduce((total, value) => total + value, 0)
  return ((airIn - outputTotal) / airIn) * 100
}

function createDemoRows() {
  const start = new Date('2026-04-27T08:00:00').getTime()
  const items = []
  for (let index = 0; index < 84; index += 1) {
    const timeMs = start + index * 5 * 60 * 1000
    const inEvent = index >= 36 && index <= 51
    const progress = Math.max(0, index - 36)
    const wave = Math.sin(index / 4)
    items.push({
      timeMs,
      time: formatTime(timeMs),
      metrics: {
        AI705: 89.5 + wave * 0.18 - (inEvent ? progress * 0.18 : 0),
        AI701: 97.8 + wave * 0.08 - (inEvent ? progress * 0.06 : 0),
        FI702: 125 + wave * 1.2 - (inEvent ? progress * 1.1 : 0),
        FIQC701: 118 + Math.cos(index / 5) * 1.4 - (inEvent ? progress * 0.9 : 0),
        FIQC102: 3400 + Math.sin(index / 6) * 25 + (inEvent ? progress * 8 : 0),
        AIAS102: 99.62 + Math.cos(index / 6) * 0.025 - (inEvent ? progress * 0.018 : 0),
        FIC101: 16800 + Math.sin(index / 5) * 60 + (inEvent ? progress * 14 : 0),
        V3: 42 + Math.sin(index / 8) * 1.5 + (inEvent ? progress * 0.45 : 0),
        BALANCE: 28 + Math.sin(index / 7) * 0.8 + (inEvent ? progress * 0.16 : 0)
      }
    })
  }
  return items
}

function initScanWorker() {
  scanWorker = new NitrogenScanWorker()
  scanWorker.onmessage = (event) => {
    const payload = event.data || {}
    if (!payload.success) {
      if (payload.requestId === workerRequestId) scanLoading.value = false
      message.value = `窗口扫描失败：${payload.error || '未知错误'}`
      return
    }
    if (payload.requestId !== workerRequestId) return
    scanLoading.value = false
    scanResults.value = payload.scanResults || []
    mergedSuspectedBands.value = (payload.suspectedBands || []).map((item) => ({
      ...item,
      suspected: true
    }))
    const firstAbnormal = scanResults.value.findIndex((item) => item.suspected)
    const strongestAbnormal = findStrongestSuspectedIndex(scanResults.value)
    const preferFirstAbnormal = Boolean(payload.options?.preferFirstAbnormal)
    const preferLatest = payload.options?.preferLatest !== false
    activeWindowIndex.value = preferFirstAbnormal
      ? strongestAbnormal >= 0 ? strongestAbnormal : firstAbnormal >= 0 ? firstAbnormal : 0
      : preferLatest
      ? Math.max(0, scanResults.value.length - 1)
      : firstAbnormal >= 0 ? firstAbnormal : 0
    activeCauseId.value = 'argon'
    manualConfirmed.value = false
    caseDecision.value = ''
    agentAnalysis.value = null
    agentError.value = ''
    llmStreamingText.value = ''
    llmTracePhase.value = 'idle'
    nextTick(renderChart)
  }
}

function runRollingScan(options = {}) {
  if (!options.keepPlaying) stopPlayback()
  if (options.markLoading) scanLoading.value = true
  if (!scanWorker) {
    initScanWorker()
  }
  workerRequestId += 1
  const requestId = workerRequestId
  scanWorker.postMessage({
    requestId,
    rows: cloneRowsForWorker(rows.value),
    options: {
      windowLengthMin: windowLengthMin.value,
      slideStepMin: slideStepMin.value,
      preferFirstAbnormal: Boolean(options.preferFirstAbnormal),
      preferLatest: options.preferLatest !== false,
      markLoading: Boolean(options.markLoading)
    }
  })
}

function findStrongestSuspectedIndex(results) {
  let bestIndex = -1
  let bestScore = -Infinity
  results.forEach((item, index) => {
    if (!item?.suspected) return
    const levelScore = riskRank(item.level) * 100
    const depthScore = Number.isFinite(item.ai705Primary?.dipDepth) ? item.ai705Primary.dipDepth : 0
    const confidenceScore = Number.isFinite(item.ai705Primary?.visualConfidence) ? item.ai705Primary.visualConfidence * 10 : 0
    const score = levelScore + depthScore + confidenceScore
    if (score > bestScore) {
      bestScore = score
      bestIndex = index
    }
  })
  return bestIndex
}

function cloneRowsForWorker(sourceRows) {
  return sourceRows.map((row) => ({
    timeMs: row.timeMs,
    time: row.time,
    metrics: { ...(row.metrics || {}) }
  }))
}

async function refreshStreamView(options = {}) {
  if (!demoRowCount.value) return
  streamCursorIndex.value = clamp(streamCursorIndex.value, demoMinTimeMs.value, demoMaxTimeMs.value)
  ensureCursorCanCoverHorizon()
  if (usingSqliteApi.value) {
    await fetchDemoWindow()
  } else {
    refreshLocalWindow()
  }
  if (options.scan === true) {
    runRollingScan({ keepPlaying: isPlaying.value, preferLatest: true })
  } else {
    nextTick(renderChart)
  }
}

function scheduleRefreshStreamView(options = {}) {
  if (!demoRowCount.value) return
  if (refreshTimer) window.clearTimeout(refreshTimer)
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    refreshStreamView(options)
  }, options.delayMs ?? 120)
}

function setStreamCursorTime(nextTimeMs, deferRefresh = false) {
  if (!demoRowCount.value) return
  clearRecognitionForViewportChange()
  streamCursorIndex.value = clamp(nextTimeMs, demoMinTimeMs.value, demoMaxTimeMs.value)
  if (deferRefresh) {
    scheduleRefreshStreamView()
    return
  }
  refreshStreamView()
}

function stepStream(delta) {
  if (!demoRowCount.value) return
  setStreamCursorTime(streamCursorIndex.value + delta * 60 * 1000)
}

function stepStreamMinutes(minutes) {
  if (!demoRowCount.value) return
  setStreamCursorTime(streamCursorIndex.value + minutes * 60 * 1000)
}

function handleStreamSliderInput(event) {
  const nextTimeMs = Number(event.target.value)
  if (!Number.isFinite(nextTimeMs)) return
  setStreamCursorTime(nextTimeMs, true)
  syncTimeSliderHover(nextTimeMs)
}

function handleStreamSliderCommit(event) {
  const nextTimeMs = Number(event.target.value)
  if (!Number.isFinite(nextTimeMs)) return
  setStreamCursorTime(nextTimeMs)
  syncTimeSliderHover(nextTimeMs)
}

function handleTimeSliderHover(event) {
  if (!demoRowCount.value) return
  const hoveredTimeMs = resolveTimeSliderEventTime(event)
  if (!Number.isFinite(hoveredTimeMs)) return
  syncTimeSliderHover(hoveredTimeMs)
}

function clearTimeSliderHover() {
  timeSliderHover.value = null
}

function handleTimeSliderTrackClick(event) {
  if (!demoRowCount.value) return
  const target = event.target
  if (target instanceof HTMLInputElement) return
  const hoveredTimeMs = resolveTimeSliderEventTime(event)
  if (!Number.isFinite(hoveredTimeMs)) return
  setStreamCursorTime(hoveredTimeMs)
  syncTimeSliderHover(hoveredTimeMs)
}

function resolveTimeSliderEventTime(event) {
  const track = timeSliderTrackRef.value
  if (!track || !demoRowCount.value) return Number.NaN
  const rect = track.getBoundingClientRect()
  if (!rect.width) return Number.NaN
  const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1)
  return demoMinTimeMs.value + (demoMaxTimeMs.value - demoMinTimeMs.value) * ratio
}

function syncTimeSliderHover(nextTimeMs) {
  if (!demoRowCount.value) {
    timeSliderHover.value = null
    return
  }
  const totalSpanMs = Math.max(1, demoMaxTimeMs.value - demoMinTimeMs.value)
  const safeTimeMs = clamp(nextTimeMs, demoMinTimeMs.value, demoMaxTimeMs.value)
  timeSliderHover.value = {
    timeMs: safeTimeMs,
    ratio: (safeTimeMs - demoMinTimeMs.value) / totalSpanMs,
    label: formatTime(safeTimeMs),
  }
}

function applyStreamRange(startMs, endMs, deferRefresh = false, refreshOptions = {}) {
  if (!demoRowCount.value) return
  if (refreshOptions.preserveRecognition !== true) {
    clearRecognitionForViewportChange()
  }
  const range = normalizeStreamRange(startMs, endMs)
  streamCursorIndex.value = range.endMs
  streamHorizonHours.value = (range.endMs - range.startMs) / 3600000
  if (deferRefresh) {
    scheduleRefreshStreamView(refreshOptions)
    return
  }
  refreshStreamView()
}

function setStreamHorizonHours(hours) {
  if (!demoRowCount.value || !Number.isFinite(hours)) return
  const nextHours = clamp(hours, minStreamHorizonHours, maxStreamHorizonHours)
  const endMs = streamCursorIndex.value || demoMaxTimeMs.value
  applyStreamRange(endMs - nextHours * 60 * 60 * 1000, endMs)
}

function isStreamHorizonOptionActive(hours) {
  return Math.abs(streamHorizonHours.value - hours) < 0.02
}

function normalizeStreamRange(startMs, endMs) {
  const minTimeMs = demoMinTimeMs.value
  const maxTimeMs = demoMaxTimeMs.value
  const minDurationMs = minStreamHorizonHours * 60 * 60 * 1000
  const maxDurationMs = maxStreamHorizonHours * 60 * 60 * 1000
  const totalDurationMs = Math.max(maxTimeMs - minTimeMs, minDurationMs)
  const desiredDurationMs = clamp(
    Math.max(endMs - startMs, minDurationMs),
    minDurationMs,
    Math.max(minDurationMs, Math.min(totalDurationMs, maxDurationMs)),
  )
  let nextStartMs = Number.isFinite(startMs) ? startMs : minTimeMs
  let nextEndMs = nextStartMs + desiredDurationMs

  if (nextStartMs < minTimeMs) {
    nextEndMs += minTimeMs - nextStartMs
    nextStartMs = minTimeMs
  }
  if (nextEndMs > maxTimeMs) {
    nextStartMs -= nextEndMs - maxTimeMs
    nextEndMs = maxTimeMs
  }

  nextStartMs = clamp(nextStartMs, minTimeMs, Math.max(minTimeMs, maxTimeMs - desiredDurationMs))
  nextEndMs = clamp(nextEndMs, Math.min(maxTimeMs, nextStartMs + minDurationMs), maxTimeMs)
  if (nextEndMs - nextStartMs < minDurationMs) {
    nextStartMs = Math.max(minTimeMs, nextEndMs - minDurationMs)
  }

  return {
    startMs: nextStartMs,
    endMs: nextEndMs,
  }
}

async function setActiveWindow(index) {
  closeChartEventPrompt()
  activeWindowIndex.value = index
  activeCauseId.value = 'argon'
  manualConfirmed.value = false
  agentAnalysis.value = null
  agentError.value = ''
  resetLlmTracePanel()
  await nextTick()
  const recordKey = activeEvent.value?.eventNo || activeResult.value?.id
  const record = recordKey ? caseDecisions.value[recordKey] : null
  caseDecision.value = typeof record === 'string' ? record : (record?.value || '')
  renderChart()
}

async function analyzeEvent(event) {
  if (!event || agentLoading.value) return
  await setActiveWindow(event.index)
  await generateAgentAnalysis()
}

function resetDiagnosisFlow() {
  closeChartEventPrompt()
  scanResults.value = []
  mergedSuspectedBands.value = []
  scanLoading.value = false
  activeWindowIndex.value = 0
  activeCauseId.value = 'argon'
  manualConfirmed.value = false
  caseDecision.value = ''
  agentAnalysis.value = null
  agentError.value = ''
  faultTreeCollapsed.value = true
  resetLlmTracePanel()
  nextTick(renderChart)
}

function clearRecognitionForViewportChange() {
  closeChartEventPrompt()
  if (
    !scanResults.value.length &&
    !mergedSuspectedBands.value.length &&
    !agentAnalysis.value &&
    !agentError.value &&
    !llmTraceLogLines.value.length &&
    !scanLoading.value
  ) {
    return
  }
  scanResults.value = []
  mergedSuspectedBands.value = []
  scanLoading.value = false
  activeWindowIndex.value = 0
  activeCauseId.value = 'argon'
  manualConfirmed.value = false
  caseDecision.value = ''
  agentAnalysis.value = null
  agentError.value = ''
  faultTreeCollapsed.value = true
  resetLlmTracePanel()
}

function identifyNitrogenPlug() {
  closeChartEventPrompt()
  agentAnalysis.value = null
  agentError.value = ''
  caseDecision.value = ''
  faultTreeCollapsed.value = true
  resetLlmTracePanel()
  runRollingScan({ preferFirstAbnormal: true, preferLatest: false, markLoading: true })
}

async function analyzeSelectedCause() {
  if (!canAnalyzeCause.value) return
  const event = selectedSuspectedEvent.value
  if (event && activeWindowIndex.value !== event.index) {
    await setActiveWindow(event.index)
  }
  await generateAgentAnalysis()
}

function toggleTag(tag) {
  if (selectedTags.value.includes(tag)) {
    selectedTags.value = selectedTags.value.filter((item) => item !== tag)
    return
  }
  selectedTags.value = [...selectedTags.value, tag]
}

function confirmCase(value) {
  caseDecision.value = value
  manualConfirmed.value = true
  const recordKey = activeEvent.value?.eventNo || activeResult.value?.id
  if (recordKey) {
    caseDecisions.value = {
      ...caseDecisions.value,
      [recordKey]: {
        value,
        label: activeEvent.value?.windowLabel || activeWindowLabel.value,
        note: `记录时间：${formatTime(Date.now())}`
      }
    }
  }
  const label = activeCaseActions.value.find((item) => item.value === value)?.label || '已复核'
  message.value = `${label}：已记录已选择区间的人工确认结果。`
}

function stopLlmSentence() {
  if (llmStreamTimer) window.clearInterval(llmStreamTimer)
  llmStreamTimer = null
}

function resetLlmTracePanel() {
  stopLlmSentence()
  llmStreamingText.value = ''
  llmTraceLogLines.value = []
  llmTracePhase.value = 'idle'
}

function formatTraceLogLine(title, content) {
  const safeTitle = String(title || '').trim()
  const safeContent = String(content || '').trim()
  if (safeTitle && safeContent) return `${safeTitle}：${safeContent}`
  return safeContent || safeTitle
}

function buildAnalysisFailureTrace(error, currentTrace = {}, configured = true) {
  const attempts = Array.isArray(currentTrace?.attempts) ? [...currentTrace.attempts] : []
  const nextCode = String(currentTrace?.error_code || error?.code || '').trim()
  const nextReason = String(currentTrace?.error_reason || error?.message || currentTrace?.message || '').trim()
  if (nextCode || nextReason) {
    const lastAttempt = attempts[attempts.length - 1] || {}
    if (lastAttempt.code !== nextCode || lastAttempt.message !== nextReason) {
      attempts.push({ code: nextCode, message: nextReason })
    }
  }
  return {
    ...currentTrace,
    status: 'failed',
    call_attempted: true,
    configured,
    error_code: nextCode,
    error_reason: nextReason,
    message: currentTrace?.message || nextReason,
    attempts,
  }
}

function streamLlmSentence(text, options = {}) {
  stopLlmSentence()
  const source = String(text || '')
  const speed = options.speed || 22
  const append = options.append !== false
  let entryIndex = llmTraceLogLines.value.length - 1
  if (append || entryIndex < 0) {
    llmTraceLogLines.value.push('')
    entryIndex = llmTraceLogLines.value.length - 1
  } else {
    llmTraceLogLines.value[entryIndex] = ''
  }
  llmStreamingText.value = ''
  let index = 0
  llmStreamTimer = window.setInterval(() => {
    index += 1
    llmStreamingText.value = source.slice(0, index)
    llmTraceLogLines.value[entryIndex] = llmStreamingText.value
    if (index >= source.length) {
      stopLlmSentence()
    }
  }, speed)
}

function buildAgentAnalysisRequest(detailLevel = 'full', analysisStage = '') {
  const shapeEvidence = activeResult.value?.ai705Primary || {}
  const balance = activeResult.value?.balance || {}
  const balanceOutputs = balance.outputs || {}
  return {
    event_id: activeEvent.value?.eventNo || activeResult.value.id,
    start_ms: shapeEvidence.startMs || activeEvent.value?.startMs || activeResult.value.startMs,
    end_ms: shapeEvidence.endMs || activeEvent.value?.endMs || activeResult.value.endMs,
    before_min: 30,
    after_min: 30,
    trigger_tags: activeResult.value.triggerTags,
    level: activeEvent.value?.level || activeResult.value.level,
    summary: activeResult.value.summary,
    shape_evidence: shapeEvidence,
    material_balance: {
      ...balanceVerification.value,
      formula_status: balance.formulaStatus,
      formula_name: balance.formulaName,
      formula_text: balance.formulaText,
      step_position: balance.stepPosition,
      static_applicable: balance.staticApplicable,
      external_model: balanceOutputs.external_model || balance.externalModel || {},
      semantic_checks: balance.semanticChecks || [],
      outputs: balanceOutputs
    },
    operating_mode: activeResult.value.operatingMode,
    load_baseline: activeResult.value.baseline,
    directional_checks: activeResult.value.directionalChecks,
    basis: agentEvidence.value,
    cause_branches: activeCauses.value.map((cause) => ({
      id: cause.id,
      branch: cause.branch,
      name: cause.name,
      confidence: cause.confidence,
      advice: cause.advice
    })),
    missing_information: missingDataRequests.value,
    review_tags: verificationTags.value,
    detail_level: detailLevel,
    analysis_stage: analysisStage
  }
}

async function requestAgentAnalysis({ detailLevel = 'full', analysisStage = '' } = {}) {
  const response = await fetch('/api/nitrogen-agent/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildAgentAnalysisRequest(detailLevel, analysisStage))
  })
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok || !payload?.success) {
    const error = new Error(payload?.error || `分析服务请求失败（HTTP ${response.status || 0}）`)
    error.code = payload?.code || `HTTP_${response.status || 0}`
    error.payload = payload
    throw error
  }
  return payload.data
}

function mergeAgentAnalysisPayload(nextPayload) {
  const current = agentAnalysis.value || buildLocalAgentAnalysis()
  agentAnalysis.value = {
    ...current,
    ...nextPayload,
    top_event_judgement: nextPayload?.top_event_judgement || current.top_event_judgement,
    basis: nextPayload?.basis?.length ? nextPayload.basis : current.basis,
    evidence_nodes: nextPayload?.evidence_nodes?.length ? nextPayload.evidence_nodes : current.evidence_nodes,
    fault_tree_path: nextPayload?.fault_tree_path?.length ? nextPayload.fault_tree_path : current.fault_tree_path,
    branch_ranking: nextPayload?.branch_ranking?.length ? nextPayload.branch_ranking : current.branch_ranking,
    key_missing_data: nextPayload?.key_missing_data?.length ? nextPayload.key_missing_data : current.key_missing_data,
    cause_branches: nextPayload?.cause_branches?.length ? nextPayload.cause_branches : current.cause_branches,
    fault_tree_guidance: nextPayload?.fault_tree_guidance || current.fault_tree_guidance,
    fault_tree_steps: nextPayload?.fault_tree_steps?.length ? nextPayload.fault_tree_steps : current.fault_tree_steps,
    review_tags: nextPayload?.review_tags?.length ? nextPayload.review_tags : current.review_tags,
    missing_information: nextPayload?.missing_information?.length ? nextPayload.missing_information : current.missing_information,
    operating_mode: nextPayload?.operating_mode || current.operating_mode,
    load_baseline: nextPayload?.load_baseline || current.load_baseline,
    directional_checks: nextPayload?.directional_checks?.length ? nextPayload.directional_checks : current.directional_checks,
    material_balance_mode: nextPayload?.material_balance_mode || current.material_balance_mode,
    material_balance_formula_status: nextPayload?.material_balance_formula_status || current.material_balance_formula_status,
    material_balance_formula_name: nextPayload?.material_balance_formula_name || current.material_balance_formula_name,
    material_balance_basis: nextPayload?.material_balance_basis || current.material_balance_basis,
    llm_trace: nextPayload?.llm_trace || current.llm_trace,
  }
}

function waitForAnalysisStage(ms = 650) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function generateAgentAnalysis() {
  if (!activeResult.value || agentLoading.value) return
  agentLoading.value = true
  agentLoadingStage.value = 'top_event'
  agentError.value = ''
  agentAnalysis.value = null
  faultTreeCollapsed.value = true
  resetLlmTracePanel()
  llmTracePhase.value = traceStageDefinitions[0].detail
  streamLlmSentence('已锁定当前区间，开始逐步分析。', { speed: 22, append: true })
  try {
    for (const stage of traceStageDefinitions) {
      agentLoadingStage.value = stage.id
      llmTracePhase.value = stage.detail
      await nextTick()
      await waitForAnalysisStage(stage.id === 'final_summary' ? 760 : 620)
      const data = await requestAgentAnalysis({
        detailLevel: stage.id === 'final_summary' ? 'full' : 'stage',
        analysisStage: stage.id
      })
      mergeAgentAnalysisPayload(data)
      const stageText = data?.llm_sentence || stage.detail
      streamLlmSentence(formatTraceLogLine(stage.title, stageText), { speed: 18, append: true })
    }
    const data = agentAnalysis.value
    const finalConclusion = data?.final_conclusion || data?.conclusion || '待人工确认'
    const finalExplanation = data?.llm_sentence || data?.summary || data?.conclusion || '分析完成，请结合现场记录确认。'
    if (data?.analysis_mode === 'rule_based') {
      message.value = data?.analysis_note || '已完成分析，请结合现场记录进行人工确认。'
    } else {
      message.value = data?.analysis_note || '已完成分析，请结合现场记录进行人工确认。'
    }
    streamLlmSentence(`${data?.decision_label || '规则主判定'}：${finalConclusion}`, { speed: 18, append: true })
    streamLlmSentence(`${data?.explanation_label || (data?.analysis_mode === 'llm_enhanced' ? '智能补充说明' : '规则分析说明')}：${finalExplanation}`, { speed: 18, append: true })
  } catch (error) {
    agentError.value = ''
    if (agentAnalysis.value) {
      agentAnalysis.value = {
        ...agentAnalysis.value,
        analysis_mode: agentAnalysis.value.analysis_mode || 'rule_based',
        analysis_note: agentAnalysis.value.analysis_note || '已完成规则分析，请结合现场记录进行人工确认。',
        analysis_fallback_reason: agentAnalysis.value.analysis_fallback_reason || String(error?.message || '智能补充暂不可用'),
        fallback_source: agentAnalysis.value.fallback_source || 'request_failure',
        trace_stage: 'final_summary',
        trace_title: '结论整理',
        trace_detail: '已使用当前可用规则结果整理结论。',
        trace_focus_node: agentAnalysis.value.trace_focus_node || currentTraceFocusNode.value || 'T0',
        llm_trace: buildAnalysisFailureTrace(error, agentAnalysis.value.llm_trace, true),
      }
      streamLlmSentence(
        formatTraceLogLine(
          '规则结果完成',
          '智能补充不可用，已使用当前规则结果完成演示链路。'
        ),
        { speed: 18, append: true }
      )
    } else {
      agentAnalysis.value = buildLocalAgentAnalysis()
      agentAnalysis.value = {
        ...agentAnalysis.value,
        analysis_note: '已完成规则分析，请结合现场记录进行人工确认。',
        analysis_fallback_reason: String(error?.message || '智能补充暂不可用。'),
        fallback_source: 'frontend_local',
        trace_stage: 'final_summary',
        trace_title: '结论整理',
        trace_detail: '已使用页面本地规则结果整理结论。',
        trace_focus_node: 'T0',
        llm_trace: buildAnalysisFailureTrace(error, agentAnalysis.value.llm_trace, false),
      }
      streamLlmSentence(
        formatTraceLogLine(
          '本地规则完成',
          '后端不可用时，页面已用本地规则完成四步分析。'
        ),
        { speed: 18, append: true }
      )
    }
    message.value = agentAnalysis.value?.analysis_note || '已完成规则分析，请结合现场记录进行人工确认。'
  } finally {
    agentLoading.value = false
    agentLoadingStage.value = 'idle'
  }
}

function toggleTrendOverlay(force) {
  showTrendOverlay.value = typeof force === 'boolean' ? force : !showTrendOverlay.value
}

function hasDiagnosisTag(tag) {
  if (activeResult.value?.triggerTags?.includes(tag)) return true
  if (!agentLoading.value && !agentAnalysis.value) return false
  return agentEvidence.value.some((item) => item.tag === tag)
}

function buildLogicChildren(branchId) {
  const fic101Status = hasDiagnosisTag('FIC101') ? '有波动' : '缺失'
  const items = {
    A: [
      { id: 'A1', title: 'FI702 氩馏分流量偏高', status: hasDiagnosisTag('FI702') ? '待判别' : '待排查' },
      { id: 'A2', title: 'FIC701 粗氩流量偏低', status: hasDiagnosisTag('FIQC701') ? '待判别' : '待排查' },
      { id: 'A3', title: '粗氩塔阻力 / 冷凝负荷', status: hasDiagnosisTag('LIC701') ? '有提示' : '缺失' }
    ],
    B: [
      { id: 'B1', title: '氧气多抽', status: hasDiagnosisTag('FIQC102') ? '待判别' : '缺失' },
      { id: 'B2', title: '氮气少抽', status: hasDiagnosisTag('FIC103') || hasDiagnosisTag('FIC8') ? '待判别' : '缺失' },
      { id: 'B3', title: 'V3 阀开过大', status: hasDiagnosisTag('V3') ? '待判别' : '缺失' },
      { id: 'B4', title: 'AI701 长时间偏高 / 短时间高高', status: hasDiagnosisTag('AI701') ? '已命中' : '待排查' }
    ],
    C: [
      { id: 'C1', title: '空气少进', status: fic101Status },
      { id: 'C2', title: '膨胀空气旁通量偏少', status: hasDiagnosisTag('FI105') || hasDiagnosisTag('FIC1') ? '有提示' : '缺失' }
    ],
    D: [
      { id: 'D1', title: '分子筛切换不平稳', status: '缺现场记录' },
      { id: 'D2', title: '变负荷过程', status: activeResult.value?.operatingMode?.dynamic ? '有提示' : '缺记录' }
    ]
  }
  return items[branchId] || []
}

function statusClass(status = '') {
  if (/检查中|分析中|处理中/.test(status)) return 'running'
  if (/强|高风险|已触发|已满足|优先|同步排查|成立|已命中|有提示/.test(status)) return 'triggered'
  if (/部分|弱|未完全|待判别|有波动/.test(status)) return 'partial'
  if (/缺失|待排查|待人工|缺现场|缺操作|缺记录|证据不足/.test(status)) return 'pending'
  if (/未触发|暂不支持|排除/.test(status)) return 'muted'
  return ''
}

function extractTreeNodeKeys(value = '') {
  const source = String(value || '').toUpperCase()
  const matches = [...source.matchAll(/(?:^|[^A-Z0-9])(T0|[A-D]\d|[A-D])(?=[^A-Z0-9]|$)/g)]
    .map((match) => match[1])
    .filter(Boolean)
  return Array.from(new Set(matches))
}

function toTreeBranchKey(value = '') {
  const keys = extractTreeNodeKeys(value)
  if (!keys.length) return ''
  if (keys[0] === 'T0') return 'T0'
  return keys[0].charAt(0)
}

function buildTreeNodeCard(nodeId = '') {
  const logicNode = agentLogicNodes.value.find((item) => item.id === nodeId)
  const ranking = agentBranchRanking.value.find((item) => toTreeBranchKey(item.branch) === nodeId)
  const evidence = agentEvidenceNodes.value
    .filter((item) => toTreeBranchKey(item.node) === nodeId)
    .slice(0, 3)
    .map((item) => ({
      label: item.evidence,
      status: item.status,
      text: item.explanation
    }))
  const childEvidence = (logicNode?.children || [])
    .filter((item) => /已|部分|待判别|有波动|缺失|证据不足/.test(item.status || ''))
    .slice(0, 2)
    .map((item) => ({
      label: item.id,
      status: item.status,
      text: `${item.title}`
    }))
  return {
    id: nodeId,
    title: logicNode?.title || (nodeId === 'T0' ? '氮塞顶事件' : '原因分支'),
    status: ranking?.status || logicNode?.status || '待排查',
    reason: ranking?.reason || ranking?.next_step || '结合当前节点证据继续复核。',
    evidence: evidence.length ? evidence : childEvidence
  }
}

function trailBadgeFor(nodeId = '') {
  const normalizedNodeId = String(nodeId || '').toUpperCase()
  const focusNode = currentTraceFocusNode.value
  const stageIndex = currentTraceStageIndex.value
  const status = normalizedNodeId === 'T0'
    ? String(topEventJudgement.value?.status || '')
    : String(buildTreeNodeCard(normalizedNodeId).status || '')

  if (normalizedNodeId === 'T0') {
    if (agentLoading.value && agentLoadingStage.value === 'top_event') {
      return { text: '当前', icon: '●', class: 'running', title: '当前正在检查顶事件' }
    }
    if (/未触发|排除|暂不支持/.test(status)) {
      return { text: '排除', icon: '✕', class: 'rejected', title: '当前顶事件未成立或已排除' }
    }
    if (agentAnalysis.value) {
      return { text: '已判定', icon: '✓', class: 'reviewed', title: '顶事件已完成阶段判断' }
    }
    return { text: '', icon: '', class: '', title: '' }
  }

  if (normalizedNodeId === focusNode) {
    if (agentLoading.value) {
      return { text: '当前', icon: '●', class: 'running', title: '当前正在检查该分支' }
    }
    if (stageIndex >= 2) {
      return { text: '已锁定', icon: '✓', class: 'reviewed', title: '当前已收敛到这条主路径' }
    }
    return { text: '', icon: '', class: '', title: '' }
  }

  if (/排除|未触发|暂不支持/.test(status)) {
    return { text: '排除', icon: '✕', class: 'rejected', title: '该路径已排除' }
  }

  if (/缺失|缺现场|缺操作|缺记录|证据不足|待人工/.test(status)) {
    return { text: '缺数据', icon: '?', class: 'missing', title: '该路径当前缺少数据或需人工确认' }
  }

  return { text: '', icon: '', class: '', title: '' }
}

function traceVisualClass(nodeId = '') {
  if (!agentLoading.value) return ''
  const activeStage = agentLoadingStage.value
  const normalizedNodeId = String(nodeId || '').toUpperCase()
  const focusNode = currentTraceFocusNode.value
  if (activeStage === 'top_event') {
    return normalizedNodeId === 'T0' ? 'running' : ''
  }
  if (activeStage === 'material_balance' || activeStage === 'branch_ranking') {
    if (normalizedNodeId === 'T0') return 'completed'
    if (normalizedNodeId === focusNode) return 'running'
    return ['A', 'B', 'C', 'D'].includes(normalizedNodeId) ? 'focus' : ''
  }
  if (activeStage === 'branch_detail') {
    if (normalizedNodeId === 'T0') return 'completed'
    if (normalizedNodeId === focusNode) return 'running'
    return ['A', 'B', 'C', 'D'].includes(normalizedNodeId) ? 'muted' : ''
  }
  if (activeStage === 'final_summary') {
    if (normalizedNodeId === 'T0' || normalizedNodeId === focusNode) return 'running'
    return ['A', 'B', 'C', 'D'].includes(normalizedNodeId) ? 'completed' : ''
  }
  return ''
}

function traceChildVisualClass(nodeId = '', childId = '') {
  if (!agentLoading.value) return ''
  const activeStage = agentLoadingStage.value
  const normalizedNodeId = String(nodeId || '').toUpperCase()
  const normalizedChildId = String(childId || '').toUpperCase()
  const focusNode = currentTraceFocusNode.value
  if (activeStage === 'branch_detail' && normalizedNodeId === focusNode) {
    return normalizedChildId.startsWith(focusNode) ? 'running' : 'focus'
  }
  if (activeStage === 'final_summary' && normalizedNodeId === focusNode) {
    return normalizedChildId.startsWith(focusNode) ? 'completed' : ''
  }
  return ''
}

function buildLocalTopEventJudgement() {
  const hasAi705 = hasDiagnosisTag('AI705')
  const hasAi701 = hasDiagnosisTag('AI701')
  const hasFiqc701 = hasDiagnosisTag('FIQC701')
  const hasFi702 = hasDiagnosisTag('FI702')
  const hasFic101 = hasDiagnosisTag('FIC101')
  const hasConfirmingArgonSystemData = false
  const auxCount = [hasAi701, hasFiqc701, hasFi702, hasFic101, hasConfirmingArgonSystemData].filter(Boolean).length
  const triggered = activeResult.value?.suspected || (hasAi705 && auxCount >= 2)
  const checkingTopEvent = agentLoading.value && agentLoadingStage.value === 'top_event' && !triggered
  return {
    node: 'T0',
    title: 'T0 氮塞顶事件',
    status: checkingTopEvent ? '检查中' : (triggered ? levelText(activeResult.value?.level) : '未触发'),
    logic: `触发逻辑：AI705 相对工作点下凹形态 ${hasAi705 ? '已满足' : '待排查'}；辅助联动信号满足 ${auxCount} / 5 项。`,
    summary: checkingTopEvent
      ? '正在看图识别，先确认 AI705 是否形成下凹、谷底和回升。'
      : triggered
      ? `当前可判为${levelText(activeResult.value?.level)}，原因仍需结合辅助测点和现场记录复核。`
      : '当前尚未达到本设备轻度氮塞标准，继续观察并保留趋势。',
    items: [
      { item: 'AI705 下凹形态', status: hasAi705 ? '已满足' : '待排查', description: '粗氩含氮量相对当前工作点出现下凹、谷底和回升，是本窗口主触发信号。' },
      { item: 'FI702 氩馏分流量偏高', status: hasFi702 ? '已满足' : '待排查', description: '粗氩塔分支：FI702偏高表示进入粗氩塔的氩馏分负荷偏高。' },
      { item: 'FIC701 粗氩流量偏低', status: hasFiqc701 ? '已满足' : '待排查', description: '粗氩塔分支：FIC701偏低表示粗氩抽出不足。' },
      { item: 'AI701 长时间偏高/短时间高高', status: hasAi701 ? '已满足' : '待排查', description: '主塔分支：AI701高值是主塔物料分配异常的重要表现。' },
      { item: 'FIC101 运行模式', status: hasFic101 ? '已满足' : '待排查', description: '先判断稳态或变负荷，动态过程不直接套用稳态物料平衡。' },
      { item: '粗氩塔阻力', status: '缺失', description: '需要补充后确认 A3 粗氩塔精馏能力是否下降。' },
      { item: '粗氩冷凝器液位 / 温差', status: '缺失', description: '需要补充后确认 A4 冷凝器换热是否恶化。' }
    ]
  }
}

function buildLocalEvidenceNodes() {
  return [
    { evidence: 'AI705 下凹形态', node: 'T0 氮塞', status: hasDiagnosisTag('AI705') ? '强触发' : '待排查', explanation: '粗氩含氮量相对当前工作点形成下凹、谷底和回升，是氮塞核心信号。' },
    { evidence: 'FI702 偏高', node: 'A1 粗氩塔氩馏分流量偏高', status: hasDiagnosisTag('FI702') ? '辅助成立' : '待排查', explanation: 'FI702偏高表示进入粗氩塔的氩馏分负荷偏高，可能增加氮塞风险。' },
    { evidence: 'FIC701 偏低', node: 'A2 粗氩塔粗氩流量偏低', status: hasDiagnosisTag('FIQC701') ? '辅助成立' : '待排查', explanation: '粗氩流量偏低表示抽出不足，可能造成系统内组分积累。' },
    { evidence: 'AI701 高值表现', node: 'B4 主塔 AI701 高值表现', status: hasDiagnosisTag('AI701') ? '辅助成立' : '待排查', explanation: 'AI701长时间偏高或短时间高高，是主塔物料分配异常的重要表现。' },
    { evidence: 'FIC101 负荷波动', node: 'C1 空气少进 / D2 变负荷过程', status: hasDiagnosisTag('FIC101') ? '待判别' : '待排查', explanation: '需先判断稳态还是动态；动态过程不能直接套用稳态物料平衡。' },
    { evidence: 'FIQC102 氧气多抽', node: 'B1', status: hasDiagnosisTag('FIQC102') ? '待判别' : '待排查', explanation: '氧气多抽可能改变主塔物料分配。' },
    { evidence: 'FIC103 氮气少抽', node: 'B2', status: hasDiagnosisTag('FIC103') ? '待判别' : '待排查', explanation: '氮气少抽可能改变全塔物料分配。' },
    { evidence: '膨胀空气偏少', node: 'C2', status: hasDiagnosisTag('FI105') || hasDiagnosisTag('FIC1') ? '待判别' : '待排查', explanation: '膨胀空气旁通量偏少可能影响冷量和塔内状态。' },
    { evidence: '粗氩塔阻力', node: 'A3', status: '缺失', explanation: '确认粗氩塔分支的重要证据。' },
    { evidence: '粗氩冷凝器液位 / 温差', node: 'A4', status: '缺失', explanation: '确认冷凝器换热异常的重要证据。' },
    { evidence: '分子筛切换记录', node: 'D1 事件', status: '缺现场记录', explanation: '判断氮塞是否发生在切换后较短时间内，以及切换过程是否平稳。' }
  ]
}

function buildLocalFaultTreePath() {
  const ai701 = hasDiagnosisTag('AI701') ? 'AI701 已提示偏高' : '缺 AI701 长时间偏高/短时间高高证据'
  const fiqc701 = hasDiagnosisTag('FIQC701') ? 'FIC701 已提示偏低' : 'FIC701 待排查'
  const fi702 = hasDiagnosisTag('FI702') ? 'FI702 已提示偏高' : 'FI702 证据不足'
  const fic101 = hasDiagnosisTag('FIC101') ? 'FIC101 有波动' : '缺 FIC101'
  const topEventStatus = agentLoading.value && agentLoadingStage.value === 'top_event' && !activeResult.value?.suspected ? '检查中' : (activeResult.value?.suspected ? '已触发' : '未触发')
  return [
    `T0 氮塞：${topEventStatus}`,
    '├─ A 粗氩塔：待排查',
    `│  ├─ A1 FI702 氩馏分流量偏高：${fi702}`,
    `│  ├─ A2 FIC701 粗氩流量偏低：${fiqc701}`,
    '│  └─ A3 粗氩塔阻力 / 冷凝负荷：缺现场测点',
    '├─ B 主塔：待排查',
    '│  ├─ B1 氧气多抽：缺 FIQC102',
    '│  ├─ B2 氮气少抽：缺 FIC103',
    '│  ├─ B3 V3 阀开过大：缺 V3 开度',
    `│  └─ B4 AI701 长时间偏高 / 短时间高高：${ai701}`,
    '├─ C 空气系统：待排查',
    `│  ├─ C1 空气少进：${fic101}`,
    '│  └─ C2 膨胀空气旁通量偏少：缺 FI105 / FIC1',
    '└─ D 事件：待人工确认',
    '   ├─ D1 分子筛切换不平稳：缺切换记录',
    `   └─ D2 变负荷过程：${fic101 === 'FIC101 有波动' ? '有变负荷提示' : '缺负荷变化记录'}`
  ]
}

function buildLocalBranchRanking() {
  const abnormalChecks = activeResult.value?.balance?.outputs?.abnormal_checks || []
  const materialByTag = new Map(abnormalChecks.map((item) => [item.tag, item]))
  const riskWeight = { low: 1, medium: 2, high: 3 }
  const evidenceScore = (tag) => {
    const material = materialByTag.get(tag)
    const materialScore = material ? (riskWeight[material.riskLevel] || 1) : 0
    return materialScore + (hasDiagnosisTag(tag) ? 1 : 0)
  }
  const evidenceLabels = (tags) => tags
    .filter((tag) => evidenceScore(tag) > 0)
    .map((tag) => {
      const material = materialByTag.get(tag)
      return material ? `${displayTagCode(tag)} ${material.directionText}` : displayTagCode(tag)
    })
  const makeBranch = (branch, tags, defaultStatus, defaultReason, nextStep, extraScore = 0) => {
    const labels = evidenceLabels(tags)
    const score = tags.reduce((total, tag) => total + evidenceScore(tag), extraScore)
    return {
      branch,
      score,
      status: score >= 4 ? '优先排查' : score > 0 ? '同步排查' : defaultStatus,
      evidence: labels,
      reason: labels.length ? `${branch}证据：${labels.join('、')}。` : defaultReason,
      next_step: nextStep
    }
  }
  const dynamicHit = activeResult.value?.operatingMode?.dynamic
  const externalMissing = activeResult.value?.balance?.outputs?.external_model?.missingForProduction?.length || 0
  const rows = [
    makeBranch('A 粗氩塔', ['FI702', 'FIQC701', 'LIC701', 'AIAS704'], '待排查', '稳态下先排查 FI702 氩馏分流量是否偏高、FIC701 粗氩流量是否偏低。', '补粗氩塔阻力、LIC702、冷凝器温差，确认粗氩塔负荷或抽出异常。'),
    makeBranch('B 主塔', ['AI701', 'FIQC102', 'FIC103', 'FIC8', 'AIAS102', 'PdI2', 'PdI1', 'V3'], '待排查', '需结合 FIQC102、FIC103、V3、AI701 和物料平衡复核。', '复核氧气多抽、氮气少抽、V3阀开度和AI701高值表现。'),
    makeBranch('C 空气系统', ['FIC101', 'FI105', 'FIC1', 'BALANCE'], '待排查', '重点看空气少进和膨胀空气旁通量偏少。', '补 FIC101、FI105、FIC1，并核对空气系统调节节奏。'),
    makeBranch('D 事件', [], '待人工确认', '分子筛切换是独立事件因素，需要现场记录支撑。', '补分子筛切换时间、切换是否平稳、切换后半小时内是否出现氮塞。', dynamicHit ? 2 : externalMissing ? 1 : 0)
  ]
  return rows
    .sort((a, b) => b.score - a.score)
    .map((item, index) => ({ ...item, rank: index + 1 }))
}

function buildLocalKeyMissingData() {
  return [
    { data: '粗氩塔阻力', node: 'A3', purpose: '判断粗氩塔精馏能力是否下降。' },
    { data: '粗氩冷凝器液空液位 LIC702', node: 'A4', purpose: '判断冷凝器换热是否恶化。' },
    { data: '粗氩冷凝器温差', node: 'A4', purpose: '判断冷凝负荷是否下降。' },
    { data: '产品氧气纯度 AIAS102', node: 'B2', purpose: '判断主塔富氩区是否可能下移。' },
    { data: '氧气取出量 FIQC102', node: 'B1', purpose: '判断是否存在氧气多抽。' },
    { data: '氮气产量 FIC103', node: 'B2', purpose: '判断是否存在氮气少抽。' },
    { data: '液氮产量 FIC8', node: 'B2', purpose: '确定目标液氮产量并参与物料平衡基准。' },
    { data: '上塔 / 下塔阻力', node: 'B3', purpose: '判断主塔精馏状态是否异常。' },
    { data: '膨胀空气旁通量 FI105 / FIC1', node: 'C2', purpose: '判断膨胀空气是否偏少，是否影响冷量和塔内状态。' },
    { data: 'V3 阀开度', node: 'D1', purpose: '判断液氮至上塔调节是否异常。' },
    { data: '分子筛切换记录', node: 'D2 / C4', purpose: '判断是否刚发生切换、切换是否平稳、氮塞是否发生在切换后短时间内。' },
    { data: '操作票 / 阀位记录', node: 'D2 / D3 / D4', purpose: '判断是否存在人为调整扰动。' }
  ]
}

function buildLocalAgentAnalysis() {
  const localFaultTreeSteps = buildLocalFaultTreeSteps()
  return {
    conclusion: resultStatusText.value,
    final_conclusion: resultStatusText.value,
    decision_source: 'rule_engine',
    decision_label: '规则主判定',
    summary: activeResult.value?.summary || buildNormalSummaryText(),
    explanation_source: 'local_rule',
    explanation_label: '本地规则说明',
    fallback_source: 'frontend_local',
    top_event_judgement: buildLocalTopEventJudgement(),
    basis: agentEvidence.value,
    evidence_nodes: buildLocalEvidenceNodes(),
    fault_tree_path: buildLocalFaultTreePath(),
    branch_ranking: buildLocalBranchRanking(),
    key_missing_data: buildLocalKeyMissingData(),
    cause_branches: activeCauses.value,
    material_balance_review: balanceVerification.value.conclusion,
    material_balance_mode: activeResult.value?.operatingMode?.mode || 'steady_review',
    material_balance_formula_status: activeResult.value?.balance?.formulaStatus || 'implemented',
    material_balance_formula_name: activeResult.value?.balance?.formulaName || 'external_compression_material_balance',
    material_balance_basis: activeResult.value?.balance?.formulaText || '外压缩物料平衡：EGOX、PAIR、GAN+LIN、TURBBY、FAR、CAR、LEV、AIR链式回归模型',
    material_balance_semantic_checks: activeResult.value?.balance?.semanticChecks || [],
    operating_mode: activeResult.value?.operatingMode || {},
    load_baseline: activeResult.value?.baseline || {},
    directional_checks: activeResult.value?.directionalChecks || [],
    action_advice: agentInspectionList.value,
    fault_tree_guidance: {
      tree_name: '氮塞故障树',
      source_path: 'data/故障树',
      steps: localFaultTreeSteps
    },
    fault_tree_steps: localFaultTreeSteps,
    review_tags: verificationTags.value,
    missing_information: missingDataRequests.value,
    analysis_mode: 'rule_based',
    llm_trace: {
      status: 'failed',
      call_attempted: false,
      configured: false,
      model: '',
      message: '本地兜底分析：未获得后端大模型响应。',
      error_code: 'LOCAL_FALLBACK',
      error_reason: '未获得后端大模型响应。',
      attempts: [{ code: 'LOCAL_FALLBACK', message: '未获得后端大模型响应。' }]
    },
    llm_sentence: activeResult.value?.summary || buildNormalSummaryText(),
    manual_review_required: true
  }
}

function buildLocalFaultTreeSteps() {
  if (activeResult.value?.suspected) {
    return [
      {
        title: '判断稳态还是动态',
        focus: '运行状态分流',
        checks: ['FIC101窗口变化', '空气/氧气/氮气升降速度', '产品抽取时序匹配'],
        reason: '变负荷过程不能直接套用静态物料平衡，需要先单独判断操作节奏。',
        action: '若为动态，优先输出负荷变化速度和时序不匹配风险。'
      },
      {
        title: '计算物料平衡基准范围',
        focus: '基准与语义判断',
        checks: ['目标负荷', '目标氧气', '目标液氮', '基准值 × ±1.25%'],
        reason: '把实际窗口均值转成偏低、正常、偏高和低/中/高风险语义。',
        action: '只展开异常项，正常项收起。'
      },
      {
        title: '多原因并行排查',
        focus: '粗氩 / 主塔 / 空气 / 事件因素',
        checks: ['FI702偏高与FIC701偏低', '空气少进/氧气多抽/氮气少抽/V3开大', '膨胀空气偏少', '分子筛切换'],
        reason: '氮塞原因可能叠加，故障树不是排他路径，不能查到一个原因就停止。',
        action: '输出每个异常原因的可能性、证据和后续检查方向。'
      }
    ]
  }
  return [
    {
      title: '保留观察窗口',
      focus: '正常波动排除',
      checks: ['AI705 后续是否连续偏离', 'FI702 与 FIQC701 是否同步下降'],
      reason: '当前未达到本设备轻度氮塞标准，先不进入处置流程。',
      action: '继续观察并记录，如后续触发再按故障树展开排查。'
    }
  ]
}

function normalizeFaultTreeStep(item) {
  if (typeof item === 'string') {
    return { title: item, detail: '按故障树步骤进行人工复核。' }
  }
  const checks = Array.isArray(item?.checks) ? item.checks.filter(Boolean).slice(0, 3).join('、') : ''
  const parts = [
    item?.focus ? `分支：${item.focus}` : '',
    checks ? `核对：${checks}` : '',
    item?.reason || '',
    item?.action ? `动作：${item.action}` : ''
  ].filter(Boolean)
  return {
    title: item?.title || item?.name || '故障树分支复核',
    detail: parts.join('；') || '按故障树步骤进行人工复核。'
  }
}

function togglePlayback() {
  if (isPlaying.value) {
    stopPlayback()
    return
  }
  isPlaying.value = true
  playTimer = window.setInterval(() => {
    if (streamCursorIndex.value >= demoMaxTimeMs.value) {
      stopPlayback()
      return
    }
    streamCursorIndex.value = clamp(streamCursorIndex.value + streamStepMin.value * 60 * 1000, demoMinTimeMs.value, demoMaxTimeMs.value)
    refreshStreamView()
  }, 900)
}

function stopPlayback() {
  isPlaying.value = false
  if (playTimer) window.clearInterval(playTimer)
  playTimer = null
}

function renderChart() {
  if (!chartCanvas.value) return
  const renderRows = chartRows.value.length ? chartRows.value : lastRenderableChartRows.value
  if (chartRows.value.length) {
    lastRenderableChartRows.value = chartRows.value
  }
  const labels = renderRows.map((row) => formatTime(row.timeMs))
  const datasets = buildChartDatasets(renderRows, selectedTags.value, tagNames, tagColors, {
    mode: chartDisplayMode.value,
    tagUnits,
    groupDefinitions: visibleTrendGroups.value,
    fixedTagBounds: fixedTagYBounds.value
  })
  chart = createOrUpdateLineChart({
    chart,
    canvas: chartCanvas.value,
    labels,
    datasets,
    plugins: [activeWindowPlugin],
    mode: chartDisplayMode.value,
    groupDefinitions: visibleTrendGroups.value,
    fixedYBounds: fixedChartYBounds.value
  })
}

function buildNormalSummaryText() {
  return 'AI705未形成相对工作点的明确下凹形态，关键变量未达到触发条件'
}

function looksLikeRawMetricSummary(text) {
  return /AI\d+\s*[+-]?\d|FI\w*\d+\s*[+-]?\d|平衡验证\s*[+-]?\d/i.test(String(text || ''))
}

function formatBasisItem(item) {
  if (!item) return ''
  if (typeof item === 'string') return item
  if (item.phenomenon) return item.phenomenon
  if (item.reason && item.title) return `${item.title}：${item.reason}`
  if (item.tag && item.basis) return `${tagLabel(item.tag)}：${item.basis}`
  if (item.title && item.value) return `${item.title}：${item.value}`
  return item.value || item.basis || item.reason || item.title || ''
}

function buildTagNarrative(tag) {
  const row = comparisonRows.value.find((item) => item.tag === tag)
  if (!row || row.during === '-') return ''
  const triggered = activeResult.value?.triggerTags?.includes(tag)
  const direction = row.direction

  if (tag === 'AI705') {
    if (triggered) return 'AI705 已形成相对工作点的下凹形态，是当前窗口的图形主触发信号。'
    if (direction === '基本稳定') return 'AI705 基本稳定，当前未见明确下凹形态。'
    if (direction.includes('下降')) return 'AI705 出现下降波动，但尚未形成足够强的持续触发证据。'
    if (direction.includes('升高')) return 'AI705 出现抬升，建议继续联看 AI701 与流量变化。'
  }

  if (tag === 'AI701') {
    if (triggered) return 'AI701 是重要表现信号，需结合空气、氧气、氮气和阀门共同判断。'
    if (direction === '基本稳定') return 'AI701 波动有限，当前未形成持续偏移。'
    return direction.includes('下降')
      ? 'AI701 出现波动，但当前更适合作为联动参考而非单独原因。'
      : 'AI701 有波动，仍需结合主塔负荷分配和粗氩流量共同判断。'
  }

  if (tag === 'FI702') {
    if (triggered) return 'FI702 偏高，表示进入粗氩塔的氩馏分负荷偏高，可能增加氮塞风险。'
    if (direction === '基本稳定') return 'FI702 基本稳定，当前未见氩馏分负荷偏高风险。'
    return direction.includes('升高')
      ? 'FI702 有升高迹象，建议继续观察是否持续偏高。'
      : 'FI702 有波动，但当前未形成明确偏高风险。'
  }

  if (tag === 'FIQC701') {
    if (triggered) return 'FIC701/粗氩流量偏低，提示粗氩抽出不足可能造成组分积累。'
    if (direction === '基本稳定') return 'FIC701 基本稳定，当前未见粗氩抽出不足风险。'
    return direction.includes('下降')
      ? 'FIC701 出现回落，建议继续联看 FI702 是否同时偏高。'
      : 'FIC701 有轻微波动，但未形成明确偏低风险。'
  }

  if (tag === 'FIC101') {
    if (direction === '基本稳定') return 'FIC101 当前未见明显突变，系统总负荷整体平稳。'
    return triggered || direction.includes('升高') || direction.includes('下降')
      ? 'FIC101 存在负荷波动，需先判断当前是稳态还是变负荷过程。'
      : 'FIC101 当前可作为负荷参考，建议与物料平衡一起复核。'
  }

  return ''
}

function buildBalanceNarrative() {
  if (balanceVerification.value.level === 'warn') {
    return '物料平衡已发现变量偏离合理范围，需同步排查空气少进、氧气多抽、氮气少抽和液氮负荷。'
  }
  if (balanceVerification.value.level === 'pending') {
    return '物料平衡侧证据暂不完整，建议补齐关键流量数据后再复核。'
  }
  return '物料平衡变量处于可接受范围，当前未单独指向系统负荷异常。'
}

function guessTimeKey(keys) {
  return keys.find((key) => /time|date|时间|日期|timestamp/i.test(key)) || keys[0]
}

function guessTimeIndex(keys) {
  const index = keys.findIndex((key) => /time|date|时间|日期|timestamp/i.test(key))
  return index >= 0 ? index : 0
}

function parseTime(value) {
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'number') {
    const excelEpoch = Date.UTC(1899, 11, 30)
    return value > 20000 && value < 80000 ? excelEpoch + value * 86400000 : value
  }
  const parsed = Date.parse(String(value).replace(/\//g, '-'))
  return Number.isFinite(parsed) ? parsed : NaN
}

function toNumber(value) {
  if (typeof value === 'number') return value
  const parsed = Number(String(value ?? '').replace('%', '').trim())
  return Number.isFinite(parsed) ? parsed : NaN
}

function nearestTimeIndex(timeMs) {
  return clamp(timeMs, demoMinTimeMs.value, demoMaxTimeMs.value)
}

function getInitialCursorIndex() {
  if (!demoRowCount.value) return 0
  return nearestTimeIndex(demoMinTimeMs.value + streamHorizonHours.value * 60 * 60 * 1000)
}

function ensureCursorCanCoverHorizon() {
  if (!demoRowCount.value) return
  const minCursorTime = demoMinTimeMs.value + streamHorizonHours.value * 60 * 60 * 1000
  if (minCursorTime > demoMaxTimeMs.value) {
    streamCursorIndex.value = demoMaxTimeMs.value
    return
  }
  if (streamCursorIndex.value < minCursorTime) {
    streamCursorIndex.value = minCursorTime
  }
}

function sampleRows(sourceRows, limit) {
  if (sourceRows.length <= limit) return sourceRows
  const sampled = []
  const step = (sourceRows.length - 1) / (limit - 1)
  for (let index = 0; index < limit; index += 1) {
    sampled.push(sourceRows[Math.round(index * step)])
  }
  return sampled
}

function observeChartBox() {
  const target = chartBoxRef.value
  if (!target) return
  chartWidth.value = target.clientWidth || 0
  if (typeof ResizeObserver === 'undefined') return
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver((entries) => {
    const nextWidth = entries[0]?.contentRect?.width || target.clientWidth || 0
    if (Math.abs(nextWidth - chartWidth.value) < 2) return
    chartWidth.value = nextWidth
  })
  resizeObserver.observe(target)
}

function tagLabel(tag) {
  return tagNames[tag] ? `${tagNames[tag]}(${displayTagCode(tag)})` : displayTagCode(tag)
}

function displayTagCode(tag) {
  return tag === 'FIQC701' ? 'FIC701' : tag
}

function levelText(level) {
  return {
    high: '重度氮塞',
    medium: '中度氮塞',
    low: '轻度氮塞',
    normal: '正常'
  }[level] || '待扫描'
}

function reviewText(value) {
  return {
    confirmed: '已确认氮塞',
    excluded: '已排除氮塞',
    observe: '继续观察',
    supplement: '补充数据',
    normal: '标记为正常波动',
    record: '补充现场记录'
  }[value] || '未复核'
}

function riskRank(level) {
  return {
    high: 3,
    medium: 2,
    low: 1,
    normal: 0
  }[level] || 0
}

function classifyMergedEventLevel(event) {
  const depth = event.maxDipDepth || event.shape?.dipDepth || 0
  const durationMin = Number.isFinite(event.startMs) && Number.isFinite(event.endMs)
    ? (event.endMs - event.startMs) / 60000
    : 0
  const standard = event.shape?.deviceStandard || {}
  const mildDrop = Number.isFinite(standard.mildDrop) ? standard.mildDrop : 0.3
  const moderateDrop = Number.isFinite(standard.moderateDrop) ? standard.moderateDrop : 0.8
  const severeDrop = Number.isFinite(standard.severeDrop) ? standard.severeDrop : 1.5
  const mildDuration = Number.isFinite(standard.mildDurationMin) ? standard.mildDurationMin : 10
  const moderateDuration = Number.isFinite(standard.moderateDurationMin) ? standard.moderateDurationMin : 30
  const severeDuration = Number.isFinite(standard.severeDurationMin) ? standard.severeDurationMin : 60
  if (depth >= severeDrop && durationMin >= severeDuration) return 'high'
  if (depth >= moderateDrop && durationMin >= moderateDuration) return 'medium'
  if (depth >= mildDrop && durationMin >= mildDuration) return 'low'
  return event.level || 'normal'
}

function formatDuration(startMs, endMs) {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return '-'
  const minutes = Math.round((endMs - startMs) / 60000)
  return `${minutes} min`
}

function formatHorizonHours(hours, fractionDigits = 0) {
  if (!Number.isFinite(hours) || hours <= 0) return '-'
  if (hours >= 24) {
    const days = hours / 24
    const precision = Number.isInteger(days) ? 0 : fractionDigits
    return `${days.toFixed(precision)} 天`
  }
  const precision = Number.isInteger(hours) ? 0 : fractionDigits
  return `${hours.toFixed(precision)} 小时`
}

function calcMetricBoundsFromRows(sourceRows, tags = availableTags) {
  const bounds = {}
  tags.forEach((tag) => {
    let minValue = Infinity
    let maxValue = -Infinity
    sourceRows.forEach((row) => {
      const value = row.metrics?.[tag]
      if (!Number.isFinite(value)) return
      minValue = Math.min(minValue, value)
      maxValue = Math.max(maxValue, value)
    })
    if (Number.isFinite(minValue) && Number.isFinite(maxValue)) {
      bounds[tag] = { min: minValue, max: maxValue }
    }
  })
  return bounds
}

function normalizeMetricBounds(metricBounds) {
  return Object.entries(metricBounds || {}).reduce((bounds, [tag, value]) => {
    if (Number.isFinite(value?.min) && Number.isFinite(value?.max)) {
      bounds[tag] = { min: value.min, max: value.max }
    }
    return bounds
  }, {})
}

function primeFixedMetricBoundsFromRows(sourceRows) {
  if (!sourceRows.length) return
  const current = fixedMetricBounds.value || {}
  const missingTags = availableTags.filter((tag) => !Number.isFinite(current[tag]?.min) || !Number.isFinite(current[tag]?.max))
  if (!missingTags.length) return
  fixedMetricBounds.value = {
    ...current,
    ...calcMetricBoundsFromRows(sourceRows, missingTags)
  }
}

function calcFixedYBoundsFromMetricBounds(metricBounds, tags) {
  const ranges = tags
    .map((tag) => metricBounds?.[tag])
    .filter((bounds) => Number.isFinite(bounds?.min) && Number.isFinite(bounds?.max))
  if (!ranges.length) return mergePreferredAxisRanges(tags)
  const minValue = Math.min(...ranges.map((bounds) => bounds.min))
  const maxValue = Math.max(...ranges.map((bounds) => bounds.max))
  return buildPreferredAxisBounds(minValue, maxValue, tags)
}

function buildPreferredAxisBounds(minValue, maxValue, tags) {
  const preferred = mergePreferredAxisRanges(tags)
  if (!preferred) return expandFixedYBounds(minValue, maxValue)
  const axisMin = Math.min(preferred.min, minValue)
  const axisMax = Math.max(preferred.max, maxValue)
  if (axisMin === preferred.min && axisMax === preferred.max) {
    return { ...preferred }
  }
  const span = preferred.max - preferred.min
  const padding = Math.max(span * 0.04, Math.abs(maxValue - minValue) * 0.08, 0.01)
  return {
    min: Math.min(preferred.min, minValue - padding),
    max: Math.max(preferred.max, maxValue + padding),
    stepSize: preferred.stepSize,
    hiddenTickValues: preferred.hiddenTickValues,
    referenceLines: preferred.referenceLines
  }
}

function mergePreferredAxisRanges(tags) {
  const ranges = tags.map((tag) => preferredAxisRanges[tag]).filter(Boolean)
  if (!ranges.length) return null
  const min = Math.min(...ranges.map((range) => range.min))
  const max = Math.max(...ranges.map((range) => range.max))
  const span = max - min
  const stepSize = ranges.length === 1 && Number.isFinite(ranges[0].stepSize) ? ranges[0].stepSize : span <= 10 ? 2 : span <= 25 ? 5 : 20
  const hiddenTickValues = ranges.flatMap((range) => range.hiddenTickValues || [])
  const referenceLines = ranges.flatMap((range) => range.referenceLines || [])
  return { min, max, stepSize, hiddenTickValues, referenceLines }
}

function expandFixedYBounds(minValue, maxValue) {
  const span = maxValue - minValue
  const padding = span > 0 ? span * 0.08 : Math.max(1, Math.abs(maxValue) * 0.08)
  return {
    min: minValue - padding,
    max: maxValue + padding
  }
}

function pickRowsByTime(sourceRows, startMs, endMs) {
  if (!sourceRows.length) return []
  return sourceRows.filter((row) => row.timeMs >= startMs && row.timeMs < endMs)
}

function calcSegmentStats(segmentRows, tag) {
  const values = segmentRows.map((row) => row.metrics[tag]).filter(Number.isFinite)
  if (!values.length) {
    return { valid: false, mean: NaN, min: NaN, max: NaN, swing: NaN }
  }
  const mean = values.reduce((total, value) => total + value, 0) / values.length
  return {
    valid: true,
    mean,
    min: Math.min(...values),
    max: Math.max(...values),
    swing: Math.max(...values) - Math.min(...values)
  }
}

function formatMean(value) {
  if (!Number.isFinite(value)) return '-'
  return Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2)
}

function formatShapeNumber(value) {
  if (!Number.isFinite(value)) return '-'
  return Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(2)
}

function formatShapePercent(value) {
  const text = formatShapeNumber(value)
  return text === '-' ? text : `${text}%`
}

function formatDeviceStandard(standard) {
  if (!standard) return '-'
  const mild = Number.isFinite(standard.mildDrop) ? standard.mildDrop.toFixed(2) : '-'
  const moderate = Number.isFinite(standard.moderateDrop) ? standard.moderateDrop.toFixed(2) : '-'
  const severe = Number.isFinite(standard.severeDrop) ? standard.severeDrop.toFixed(2) : '-'
  return `轻≥${mild} / 中≥${moderate} / 重≥${severe}`
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return '-'
  return `${Math.round(clamp(value, 0, 1) * 100)}%`
}

function formatMetricValue(value, unit = '') {
  const numberValue = toNumber(value)
  if (!Number.isFinite(numberValue)) return value || '-'
  const formatted = Math.abs(numberValue) >= 100 ? numberValue.toFixed(0) : numberValue.toFixed(2)
  return unit ? `${formatted}${unit}` : formatted
}

function describeDirection(before, during, after) {
  if (!during.valid) return '-'
  if (!before.valid) return after.valid ? '待补前段' : '待补数据'
  const delta = during.mean - before.mean
  const afterDelta = after.valid ? after.mean - during.mean : NaN
  const threshold = Math.max(Math.abs(before.mean) * 0.003, 0.08)
  if (Math.abs(delta) <= threshold && during.swing <= threshold * 3) return '基本稳定'
  if (delta > threshold) return after.valid && afterDelta < -threshold ? '升高后回落' : '升高'
  return after.valid && afterDelta > threshold ? '下降后恢复' : '下降'
}

function describeSupport(tag, before, during) {
  const triggered = activeResult.value?.triggerTags?.includes(tag)
  if (!during.valid) return '待补'
  if (triggered && tag === 'AI705') return '强'
  if (triggered) return '中'
  if (!before.valid) return '辅助'
  const delta = Math.abs(during.mean - before.mean)
  const threshold = Math.max(Math.abs(before.mean) * 0.005, 0.1)
  return delta > threshold ? '辅助' : '弱'
}

function buildEmptyComparisonRows() {
  return ['AI705', 'AI701', 'FI702', 'FIQC701'].map((tag) => ({
    tag,
    before: '-',
    during: '-',
    after: '-',
    direction: '-',
    support: '待扫描'
  }))
}
</script>

<style scoped>
.nitrogen-demo {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f6f8fb;
  color: #162033;
}

.demo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 18px;
  border-bottom: 1px solid #dde4ee;
  background: #ffffff;
}

.header-copy,
.header-toolbar {
  min-width: 0;
}

.header-copy {
  display: grid;
  gap: 4px;
}

.header-kicker {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.header-copy p {
  margin: 0;
  min-width: 0;
  flex: 1;
  color: #526072;
  font-size: 13px;
  line-height: 1.4;
}

.header-status-pill {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border: 1px solid #d8e0ea;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.header-status-pill.running {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}

.header-status-pill.review,
.header-status-pill.suspected {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #c2410c;
}

.header-status-pill.normal {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

h1 {
  margin: 0;
  white-space: nowrap;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: 0;
}

p {
  margin: 4px 0 0;
  color: #6b778c;
  font-size: 12px;
}

button,
.upload-btn {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 11px;
  border: 1px solid #c8d2df;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
  text-decoration: none;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

button:hover,
.upload-btn:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

button.primary {
  border-color: #1d4ed8;
  background: #1d4ed8;
  color: #ffffff;
}

.upload-btn input {
  display: none;
}

.primary-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.recognition-inline-note {
  max-width: 520px;
  margin-top: 7px;
  padding: 7px 9px;
  border: 1px solid #dbe4f0;
  border-radius: 6px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
}

.primary-flow-btn {
  border-color: #1d4ed8;
  background: #1d4ed8;
  color: #ffffff;
}

.primary-flow-btn:hover {
  border-color: #1e40af;
  background: #1e40af;
}

.primary-flow-btn.cause-btn {
  border-color: #0f766e;
  background: #0f766e;
}

.primary-flow-btn.cause-btn:hover {
  border-color: #115e59;
  background: #115e59;
}

.primary-flow-btn:disabled,
.primary-flow-btn.cause-btn:disabled {
  border-color: #c8d2df;
  background: #eef2f7;
  color: #64748b;
}

.recognition-note {
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(0, 1.6fr);
  gap: 10px;
  align-items: stretch;
  padding: 10px 12px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
}

.recognition-note strong {
  color: #0f172a;
  font-size: 13px;
}

.recognition-note p {
  margin: 4px 0 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.recognition-rule-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.recognition-rule-grid span {
  min-width: 0;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}

.recognition-rule-grid b {
  display: block;
  margin-bottom: 2px;
  color: #0f172a;
  font-size: 12px;
}

.demo-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  width: min(100%, 1720px);
  margin: 0 auto;
  padding: 8px 12px 12px;
  overflow: hidden;
}

.panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

.panel-title {
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
  font-weight: 800;
  font-size: 14px;
}

.panel-title-inline {
  min-height: 34px;
}

.source-pill {
  max-width: 420px;
  overflow: hidden;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  min-width: 0;
  overflow: hidden;
  color: #6b778c;
  font-size: 12px;
  font-weight: 500;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-bar {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  background: #ffffff;
  overflow: auto hidden;
  white-space: nowrap;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.summary-bar span {
  position: relative;
}

.summary-bar span:not(:last-child)::after {
  content: '｜';
  margin-left: 10px;
  color: #94a3b8;
}

.drawer-panel {
  border-style: dashed;
}

.drawer-grid {
  padding-top: 10px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 0 12px 10px;
}

.settings-grid label {
  display: grid;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.playback-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 8px;
}

.stream-row {
  display: grid;
  grid-template-columns: auto minmax(160px, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 2px 14px 10px;
  color: #6b778c;
  font-size: 12px;
  font-weight: 700;
}

.stream-row input {
  width: 100%;
}

.stream-row strong {
  color: #172033;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}

select {
  height: 30px;
  border: 1px solid #c8d2df;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
  font-size: 12px;
}

.summary-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 0 14px 12px;
  color: #6b778c;
  font-size: 12px;
}

.summary-strip strong {
  color: #172033;
}

.message {
  margin: 0;
  padding: 8px 12px;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #2563eb;
  font-size: 12px;
}

.workbench-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: 188px minmax(0, 1fr) 372px;
  gap: 8px;
  align-items: stretch;
}

.workbench-grid.analysis-expanded {
  grid-template-columns: 170px minmax(340px, 0.55fr) minmax(640px, 1.45fr);
}

.tag-groups {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.primary-trigger {
  padding: 8px 10px 6px;
  border-bottom: 1px solid #d7e0eb;
  background: linear-gradient(180deg, #f8fbff 0%, #f1f6fb 100%);
}

.primary-trigger-check {
  padding: 6px 8px;
  border: 1px solid #dde6f2;
  border-radius: 6px;
  background: #ffffff;
}

.primary-trigger-check strong {
  color: #1d4ed8;
}

.tag-group {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
}

.tag-group:last-child {
  border-bottom: 0;
}

.tag-group-head {
  display: flex;
  align-items: baseline;
  margin-bottom: 6px;
}

.tag-group-head strong {
  color: #162033;
  font-size: 13px;
}

.tag-check {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 7px;
  align-items: start;
  padding: 3px 0;
  color: #334155;
  cursor: pointer;
}

.tag-check span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.tag-check strong {
  font-size: 12px;
  line-height: 1.2;
}

.tag-check em {
  overflow: hidden;
  color: #6b778c;
  font-size: 11px;
  font-style: normal;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trend-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.mode-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.mode-select select {
  min-width: 132px;
}

.trend-panel {
  min-height: 0;
}

.trend-panel.trend-overlay {
  position: fixed;
  top: 76px;
  left: 206px;
  right: 24px;
  bottom: 24px;
  z-index: 70;
  border-color: #bfdbfe;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.18);
}

.trend-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding: 10px 14px 0;
  color: #6b778c;
  font-size: 12px;
  font-weight: 700;
}

.trend-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 18px;
  height: 8px;
  display: inline-block;
  border-radius: 999px;
}

.legend-dot.danger {
  background: rgba(220, 38, 38, 0.35);
}

.legend-dot.current {
  background: rgba(37, 99, 235, 0.35);
}

.legend-dot.neutral {
  background: #cbd5e1;
}

.legend-line {
  width: 22px;
  height: 0;
  display: inline-block;
  border-top: 2px solid #f97316;
}

.legend-line.marker {
  border-top-style: solid;
  border-top-color: #b91c1c;
}

.chart-box {
  flex: 1;
  min-height: 0;
  padding: 8px 12px 12px;
}

.trend-panel.trend-overlay .chart-box {
  padding-bottom: 16px;
}

.time-slider-bar {
  display: grid;
  grid-template-columns: auto minmax(120px, 170px) minmax(0, 1fr) minmax(120px, 170px) auto;
  align-items: center;
  gap: 10px;
  padding: 0 12px 8px;
}

.time-slider-track {
  position: relative;
  display: flex;
  align-items: center;
}

.time-slider-input {
  width: 100%;
  height: 22px;
  appearance: none;
  background: transparent;
  cursor: pointer;
}

.time-slider-input::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: #dbe4f0;
}

.time-slider-input::-webkit-slider-thumb {
  width: 4px;
  height: 20px;
  margin-top: -8px;
  appearance: none;
  border: 0;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
}

.time-slider-input::-moz-range-track {
  height: 4px;
  border-radius: 999px;
  background: #dbe4f0;
}

.time-slider-input::-moz-range-progress {
  height: 4px;
  border-radius: 999px;
  background: #dbe4f0;
}

.time-slider-input::-moz-range-thumb {
  width: 4px;
  height: 20px;
  border: 0;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
}

.time-slider-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.92);
  color: #f8fafc;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
}

.time-slider-edge {
  color: #64748b;
  font-size: 12px;
  text-align: center;
  white-space: nowrap;
}

.time-slider-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 12px 10px;
  color: #475569;
  font-size: 12px;
}

.time-scale-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 0 12px 12px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.time-scale-options span {
  margin-right: 2px;
  white-space: nowrap;
}

.time-scale-btn {
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid #dbe4f0;
  border-radius: 6px;
  background: #ffffff;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.time-scale-btn.active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.chart-stage {
  position: relative;
  width: 100%;
  height: 100%;
  cursor: default;
}

.chart-stage.clickable {
  cursor: pointer;
}

.chart-event-popover {
  position: absolute;
  z-index: 12;
  width: 304px;
  padding: 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.18);
  color: #334155;
  user-select: none;
}

.chart-event-popover.collapsed {
  width: 264px;
  padding: 10px 12px;
}

.chart-event-popover.dragging {
  cursor: grabbing;
  box-shadow: 0 20px 44px rgba(15, 23, 42, 0.24);
}

.chart-event-popover-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  cursor: grab;
  touch-action: none;
}

.chart-event-popover.dragging .chart-event-popover-header {
  cursor: grabbing;
}

.chart-event-popover-summary {
  min-width: 0;
  flex: 1;
}

.chart-event-popover strong,
.chart-event-popover span {
  display: block;
}

.chart-event-popover strong {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.3;
}

.chart-event-popover span {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.chart-event-popover-window {
  line-height: 1.45;
}

.chart-event-toggle {
  flex: 0 0 auto;
  min-width: 52px;
  padding: 0 10px;
}

.chart-event-popover-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 12px;
  margin-top: 10px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.chart-event-popover-grid .wide {
  grid-column: 1 / -1;
}

.chart-event-popover-note {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
}

.chart-event-popover-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.agent-panel {
  min-height: 0;
}

.agent-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.compact-action {
  min-height: 28px;
  padding: 0 12px;
  font-size: 12px;
  white-space: nowrap;
}

.ghost-btn {
  min-height: 28px;
  padding: 0 9px;
  color: #1d4ed8;
  font-size: 12px;
}

.ghost-btn.active {
  border-color: #1d4ed8;
  background: #eff6ff;
}

.trend-overlay-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(15, 23, 42, 0.16);
}

.ghost-btn:disabled {
  color: #94a3b8;
}

.agent-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.agent-banner {
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.llm-trace-log {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.llm-trace-log p {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
}

.agent-section h3 {
  margin: 0;
  color: #6b778c;
  font-size: 12px;
  font-weight: 800;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-toggle {
  flex-shrink: 0;
}

.logic-map-section {
  background: #fafcfd;
}

.trace-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.trace-meta-card {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dde5ed;
  border-radius: 10px;
  background: #fcfdff;
}

.trace-meta-card.ghost {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92) 0%, rgba(241, 245, 249, 0.9) 100%);
}

.trace-meta-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.trace-meta-card strong {
  color: #243041;
  font-size: 13px;
}

.trace-meta-card p,
.trace-meta-card em {
  margin: 0;
}

.trace-meta-card p {
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
}

.trace-meta-card em {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
  font-style: normal;
}

.trace-inline-fields {
  display: grid;
  gap: 6px;
}

.trace-inline-fields span {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border: 1px dashed #dbe2ea;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #475569;
  font-size: 12px;
}

.trace-inline-fields b {
  color: #1e293b;
  font-weight: 700;
}

.diagnosis-findings-section {
  background: #fcfdff;
}

.diagnosis-status-grid,
.cause-finding-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.diagnosis-status-card,
.cause-finding-card,
.variable-deviation-row {
  min-width: 0;
  padding: 10px;
  border: 1px solid #dde5ed;
  border-radius: 8px;
  background: #ffffff;
}

.diagnosis-status-card {
  display: grid;
  gap: 7px;
}

.material-balance-io-card {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.material-balance-io-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  min-width: 0;
}

.material-balance-io-row strong {
  color: #1e3a8a;
  font-size: 12px;
  line-height: 1.5;
}

.material-balance-io-row span {
  min-width: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.material-balance-trace-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
}

.trace-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.trace-card-head div {
  display: grid;
  gap: 3px;
}

.trace-card-head strong {
  color: #1e3a8a;
  font-size: 14px;
}

.trace-card-head span {
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}

.formula-substitution-card {
  display: grid;
  gap: 5px;
  padding: 10px;
  border: 1px dashed #93c5fd;
  border-radius: 10px;
  background: #ffffff;
}

.formula-substitution-card b {
  color: #1d4ed8;
  font-size: 12px;
}

.formula-substitution-card p {
  margin: 0;
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.balance-pipeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.balance-pipeline-step {
  display: grid;
  gap: 5px;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #ffffff;
}

.balance-pipeline-step small {
  width: fit-content;
  padding: 2px 6px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 700;
}

.balance-pipeline-step strong {
  color: #243041;
  font-size: 12px;
}

.balance-pipeline-step span {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}

.balance-pipeline-step em {
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
}

.model-comparison-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.model-comparison-item {
  display: grid;
  gap: 4px;
  padding: 9px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #ffffff;
}

.model-comparison-item.partial {
  border-color: #fde68a;
  background: #fffbeb;
}

.model-comparison-item.triggered {
  border-color: #fecaca;
  background: #fff1f2;
}

.model-comparison-item.pending {
  background: #f8fafc;
}

.model-comparison-item strong {
  color: #1e293b;
  font-size: 12px;
}

.model-comparison-item span,
.model-comparison-item em {
  color: #475569;
  font-size: 11px;
  line-height: 1.35;
}

@media (max-width: 1180px) {
  .balance-pipeline,
  .model-comparison-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .balance-pipeline,
  .model-comparison-grid {
    grid-template-columns: 1fr;
  }
}

.diagnosis-status-card strong,
.cause-finding-card strong,
.variable-deviation-row strong {
  color: #243041;
  font-size: 12px;
}

.diagnosis-status-card p,
.diagnosis-status-card em,
.cause-finding-card p,
.variable-deviation-row p,
.variable-deviation-row em {
  margin: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
  font-style: normal;
}

.diagnosis-status-card.triggered,
.cause-finding-card.triggered,
.variable-deviation-row.triggered {
  border-color: #fecaca;
  background: #fff7f7;
}

.diagnosis-status-card.partial,
.cause-finding-card.partial,
.variable-deviation-row.partial {
  border-color: #fed7aa;
  background: #fffaf3;
}

.diagnosis-status-card.normal,
.variable-deviation-row.normal {
  border-color: #bbf7d0;
  background: #f7fef9;
}

.diagnosis-status-card.pending,
.cause-finding-card.pending,
.variable-deviation-row.pending {
  border-color: #e2e8f0;
  background: #f8fafc;
}

.variable-deviation-list {
  display: grid;
  gap: 8px;
}

.variable-deviation-row {
  display: grid;
  gap: 5px;
}

.variable-deviation-row > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.variable-deviation-row span {
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.cause-finding-card {
  display: grid;
  gap: 8px;
}

.cause-evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cause-evidence-tags span {
  padding: 3px 7px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 11px;
  font-weight: 800;
}

.agent-logic-map {
  display: grid;
  gap: 10px;
}

.logic-root,
.logic-node {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 10px 11px;
  border: 1px solid #dde5ed;
  border-radius: 10px;
  background: #fcfdff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75);
}

.logic-root {
  position: relative;
  max-width: 260px;
  justify-self: center;
  text-align: center;
  overflow: visible;
}

.logic-root::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -11px;
  width: 1px;
  height: 10px;
  background: #cbd5e1;
}

.logic-branches {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding-top: 10px;
}

.logic-branches::before {
  content: '';
  position: absolute;
  left: 12.5%;
  right: 12.5%;
  top: 0;
  height: 1px;
  background: #cbd5e1;
}

.logic-node {
  position: relative;
  min-height: 148px;
  overflow: visible;
}

.logic-node::before {
  content: '';
  position: absolute;
  left: 50%;
  top: -10px;
  width: 1px;
  height: 10px;
  background: #cbd5e1;
}

.logic-root strong,
.logic-node strong {
  color: #243041;
  font-size: 13px;
  line-height: 1.2;
}

.logic-root span,
.logic-node span {
  min-width: 0;
  color: #4b5a6c;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
}

.logic-root em,
.logic-node em {
  color: #7b8797;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
}

.logic-children {
  display: grid;
  gap: 5px;
  margin-top: 4px;
}

.logic-children span {
  min-height: 22px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 6px;
  border: 1px solid #e5ebf1;
  border-radius: 6px;
  background: #ffffff;
  color: #58677a;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.25;
}

.logic-children span.triggered {
  border-color: #cddfcf;
  background: #f4faf5;
  color: #4a7150;
}

.logic-children span.partial {
  border-color: #d7dfeb;
  background: #f5f8fc;
  color: #5a7088;
}

.logic-children span.pending {
  border-color: #e5e7eb;
  background: #fafafa;
  color: #7a8592;
}

.logic-children span.muted {
  border-color: #eceff3;
  background: #f8fafb;
  color: #94a3b8;
}

.logic-children b {
  color: inherit;
  font-size: 11px;
}

.logic-root.triggered,
.logic-node.triggered {
  border-color: #d3e1d5;
  background: linear-gradient(180deg, #fbfdfb 0%, #f4faf5 100%);
}

.logic-root.partial,
.logic-node.partial {
  border-color: #dbe4ef;
  background: linear-gradient(180deg, #fdfefe 0%, #f5f8fc 100%);
}

.logic-root.pending,
.logic-node.pending {
  border-color: #e5e7eb;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
}

.logic-root.muted,
.logic-node.muted {
  border-color: #edf1f4;
  background: #fbfcfd;
}

.logic-root.focus,
.logic-node.focus {
  border-color: #d7dfeb;
  box-shadow: 0 0 0 1px rgba(203, 213, 225, 0.45);
}

.logic-root.completed,
.logic-node.completed {
  border-color: #d5e3d8;
  background: #f7fbf8;
}

.logic-root.running,
.logic-node.running,
.logic-children span.running,
.tree-focus-card.running,
.tree-branch-card.running {
  animation: tracePulse 0.82s ease-in-out infinite;
}

.logic-root.running,
.logic-node.running {
  border-color: #3b82f6;
  background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.62), 0 0 0 7px rgba(96, 165, 250, 0.34), 0 10px 20px rgba(59, 130, 246, 0.14);
}

.tree-focus-card.running,
.tree-branch-card.running {
  border-color: #3b82f6;
  background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.62), 0 0 0 7px rgba(96, 165, 250, 0.28), 0 12px 24px rgba(59, 130, 246, 0.12);
}

.logic-children span.running,
.status-chip.running {
  border-color: #60a5fa;
  background: #dbeafe;
  color: #1d4ed8;
  box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.24);
}

.logic-children span.focus {
  border-color: #dde5ed;
  background: #f7f9fb;
}

.logic-children span.completed {
  border-color: #d8e5da;
  background: #f6fbf7;
}

@keyframes tracePulse {
  0% {
    opacity: 0.86;
    transform: translateY(0) scale(1);
    filter: saturate(1);
  }
  50% {
    opacity: 1;
    transform: translateY(-1px) scale(1.02);
    filter: saturate(1.18);
  }
  100% {
    opacity: 0.88;
    transform: translateY(0) scale(1);
    filter: saturate(1.02);
  }
}

@keyframes analysisSpin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes progressGlow {
  0% {
    filter: brightness(0.96);
  }
  50% {
    filter: brightness(1.15);
  }
  100% {
    filter: brightness(0.98);
  }
}

@keyframes activeStepPulse {
  0% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1px);
  }
  100% {
    transform: translateY(0);
  }
}

@keyframes analysisStepBeat {
  0% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.32);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(37, 99, 235, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0);
  }
}

.agent-error {
  margin: 0;
  padding: 8px 14px;
  border-bottom: 1px solid #fed7aa;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  font-weight: 700;
}

.llm-presence {
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #dbeafe;
  background: #f8fbff;
}

.llm-presence div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
}

.llm-presence strong {
  color: #1d4ed8;
  font-size: 12px;
}

.llm-presence span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.llm-presence p {
  min-height: 20px;
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
  line-height: 1.55;
}

.analysis-progress-section {
  gap: 10px;
}

.analysis-progress-card {
  display: grid;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
}

.analysis-progress-head {
  display: grid;
  gap: 4px;
}

.analysis-progress-head strong {
  color: #0f172a;
  font-size: 13px;
}

.analysis-progress-head span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.analysis-loading-banner {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #93c5fd;
  border-radius: 8px;
  background: linear-gradient(90deg, #eff6ff 0%, #ffffff 100%);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.08);
}

.analysis-loading-spinner {
  width: 22px;
  height: 22px;
  border: 3px solid #bfdbfe;
  border-top-color: #2563eb;
  border-radius: 999px;
  animation: analysisSpin 0.72s linear infinite;
}

.analysis-loading-banner div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.analysis-loading-banner b {
  color: #1d4ed8;
  font-size: 13px;
  line-height: 1.35;
}

.analysis-loading-banner em {
  color: #64748b;
  font-size: 11px;
  font-style: normal;
  line-height: 1.45;
}

.analysis-loading-banner mark {
  padding: 3px 7px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 900;
}

.analysis-progress-track {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.analysis-progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #2563eb, #22c55e);
  transition: width 0.32s ease;
  animation: progressGlow 1.05s ease-in-out infinite;
}

.analysis-step-list {
  display: grid;
  gap: 8px;
}

.analysis-step-item {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.analysis-step-item.completed {
  border-color: #bfdbfe;
  background: #f8fbff;
}

.analysis-step-item.running {
  border-color: #93c5fd;
  background: #eff6ff;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08), 0 0 0 4px rgba(37, 99, 235, 0.12);
  animation: activeStepPulse 0.88s ease-in-out infinite;
}

.analysis-step-index {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 12px;
  font-weight: 800;
}

.analysis-step-item.completed .analysis-step-index {
  background: #bfdbfe;
  color: #1d4ed8;
}

.analysis-step-item.running .analysis-step-index {
  background: #2563eb;
  color: #ffffff;
  animation: analysisStepBeat 0.7s ease-in-out infinite;
}

.analysis-step-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.analysis-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.analysis-step-head strong {
  color: #172033;
  font-size: 12px;
}

.analysis-step-copy p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.analysis-step-detail-grid {
  display: grid;
  gap: 5px;
  margin-top: 4px;
}

.analysis-step-detail-row {
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid #dbeafe;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.78);
}

.analysis-step-detail-row b {
  color: #1d4ed8;
  font-size: 11px;
  line-height: 1.45;
}

.analysis-step-detail-row span {
  min-width: 0;
  color: #334155;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.analysis-log-list {
  display: grid;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
}

.analysis-log-list p {
  margin: 0;
  color: #475569;
  font-size: 11px;
  line-height: 1.45;
}

.analysis-report-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  background: #f0fdf4;
}

.analysis-report-card div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.analysis-report-card strong {
  color: #166534;
  font-size: 13px;
}

.analysis-report-card span {
  color: #64748b;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.expert-conclusion-section {
  gap: 10px;
}

.expert-conclusion-card {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
}

.expert-conclusion-card strong {
  color: #0f172a;
  font-size: 15px;
  line-height: 1.45;
}

.expert-conclusion-card p {
  margin: 0;
  color: #1e293b;
  font-size: 13px;
  line-height: 1.65;
  font-weight: 700;
}

.expert-conclusion-block {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.85);
}

.expert-conclusion-block b {
  color: #1d4ed8;
  font-size: 12px;
}

.expert-conclusion-block span {
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.compact-event-section {
  gap: 10px;
}

.compact-event-card {
  display: grid;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fbfcfe;
}

.compact-event-summary {
  display: grid;
  gap: 4px;
}

.compact-event-summary strong {
  color: #243041;
  font-size: 12px;
  font-weight: 800;
}

.compact-event-summary span {
  color: #6b778c;
  font-size: 11px;
  line-height: 1.45;
}

.compact-event-list {
  display: grid;
  gap: 6px;
}

.compact-event-item {
  min-width: 0;
  display: grid;
  justify-items: start;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  text-align: left;
}

.compact-event-item strong {
  color: #334155;
  font-size: 11px;
}

.compact-event-item span {
  color: #475569;
  font-size: 11px;
  line-height: 1.4;
}

.compact-event-item em {
  color: #7c6f55;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
}

.event-shape-grid {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 6px;
  margin-top: 6px;
}

.event-shape-grid small {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-shape-grid small:nth-last-child(2) {
  grid-column: 1 / -1;
}

.compact-event-item.active {
  border-color: #cdd9e7;
  background: #f6f9fc;
}

.agent-section {
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.evidence-list.compact {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  overflow: hidden;
}

.evidence-list {
  display: grid;
}

.evidence-row {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 5px 10px;
  padding: 9px 12px;
  border-bottom: 1px solid #e2e8f0;
}

.evidence-row:last-child {
  border-bottom: 0;
}

.evidence-row strong {
  grid-row: 1 / 3;
  color: #1d4ed8;
  line-height: 1.35;
}

.evidence-row span,
.evidence-row em {
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 12px;
  font-style: normal;
}

.evidence-row em {
  color: #64748b;
}

.advice-box {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fafcff;
}

.advice-box strong {
  line-height: 1.45;
}

.advice-box p {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}

.logic-text {
  color: #475569;
  font-weight: 800;
}

.advice-box.waiting {
  background: #f8fafc;
}

.tree-focus-card,
.tree-branch-card {
  position: relative;
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fbfcfe;
  overflow: visible;
}

.tree-focus-head,
.tree-branch-head {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.tree-focus-head > div,
.tree-branch-head {
  min-width: 0;
}

.tree-focus-head strong,
.tree-branch-head strong {
  color: #243041;
  font-size: 13px;
}

.tree-focus-head span,
.tree-branch-head span {
  color: #5b6777;
  font-size: 12px;
  font-weight: 700;
}

.tree-focus-card p,
.tree-branch-card p {
  margin: 0;
  color: #4b5a6c;
  font-size: 12px;
  line-height: 1.55;
}

.tree-bullet-list {
  display: grid;
  gap: 6px;
}

.tree-bullet-list-compact {
  gap: 8px;
}

.tree-bullet {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.tree-bullet span {
  min-width: 0;
  color: #4b5a6c;
  font-size: 12px;
  line-height: 1.5;
}

.tree-branch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.tree-inline-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.node-trail-badge {
  position: absolute;
  right: 8px;
  bottom: 8px;
  min-width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid #dbe2ea;
  background: #ffffff;
  color: #64748b;
  font-size: 11px;
  font-weight: 900;
  line-height: 1;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
}

.node-trail-badge.card-badge {
  right: 10px;
  bottom: 10px;
}

.node-trail-badge.running {
  border-color: #60a5fa;
  background: #dbeafe;
  color: #1d4ed8;
}

.node-trail-badge.reviewed {
  border-color: #cbd5e1;
  background: #f8fafc;
  color: #475569;
}

.node-trail-badge.candidate {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #2563eb;
}

.node-trail-badge.rejected {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #dc2626;
}

.node-trail-badge.missing {
  border-color: #fde68a;
  background: #fffbeb;
  color: #a16207;
}

.tree-inline-list span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #ffffff;
  color: #5a687a;
  font-size: 11px;
  font-weight: 700;
}

.analysis-step-list {
  display: grid;
  gap: 8px;
}

.analysis-step {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
}

.analysis-step > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
  font-weight: 900;
}

.analysis-step div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.analysis-step strong {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.35;
}

.analysis-step em {
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.analysis-step.completed > span {
  background: #dcfce7;
  color: #15803d;
}

.analysis-step.running > span {
  background: #dbeafe;
  color: #1d4ed8;
}

.analysis-step.blocked {
  background: #f8fafc;
}

.analysis-step.blocked strong,
.analysis-step.blocked em {
  color: #94a3b8;
}

.note-list {
  display: grid;
  gap: 6px;
}

.diagnosis-table {
  display: grid;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
}

.table-row {
  display: grid;
  gap: 8px;
  align-items: start;
  padding: 8px 10px;
  border-top: 1px solid #e2e8f0;
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
}

.table-row:first-child {
  border-top: 0;
}

.table-row span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.table-head {
  background: #f8fafc;
  color: #475569;
  font-weight: 900;
}

.top-event-table .table-row {
  grid-template-columns: minmax(96px, 1.1fr) minmax(76px, 0.7fr) minmax(0, 2fr);
}

.evidence-node-table .table-row {
  grid-template-columns: minmax(92px, 1fr) minmax(122px, 1.2fr) minmax(76px, 0.7fr) minmax(0, 1.7fr);
}

.branch-rank-table .table-row {
  grid-template-columns: 42px minmax(118px, 1.1fr) minmax(80px, 0.8fr) minmax(0, 1.7fr) minmax(0, 1.5fr);
}

.missing-data-table .table-row {
  grid-template-columns: minmax(130px, 1.2fr) minmax(80px, 0.7fr) minmax(0, 1.8fr);
}

.status-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 7px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 11px;
  font-weight: 900;
  white-space: nowrap;
}

.status-chip.triggered {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.status-chip.partial {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #c2410c;
}

.status-chip.normal {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.status-chip.pending {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.status-chip.muted {
  border-color: #e2e8f0;
  background: #f8fafc;
  color: #64748b;
}

.fault-path-box {
  overflow: auto;
  max-height: 360px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #0f172a;
}

.fault-path-box pre {
  margin: 0;
  color: #e5edf8;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre;
}

@media (max-width: 760px) {
  .tree-branch-grid {
    grid-template-columns: 1fr;
  }

  .top-event-table .table-row,
  .evidence-node-table .table-row,
  .branch-rank-table .table-row,
  .missing-data-table .table-row {
    grid-template-columns: 1fr;
  }

  .table-head {
    display: none;
  }
}

.note-row {
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fbfcfe;
  color: #334155;
  font-size: 12px;
  line-height: 1.5;
}

.note-row-numbered {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.note-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
}

.fault-step-row span:last-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.fault-step-row strong {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.35;
}

.fault-step-row em {
  color: #475569;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.verify-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.verify-tags span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.review-status {
  margin: 0;
  color: #334155;
  font-size: 13px;
  font-weight: 800;
}

.case-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid #e2e8f0;
  background: #ffffff;
}

.case-actions button {
  min-width: 0;
  padding: 0 8px;
  white-space: nowrap;
}

.case-actions button.active {
  border-color: #1d4ed8;
  background: #eff6ff;
  color: #1d4ed8;
}

.bottom-panel {
  min-height: 0;
}

.bottom-panel.compact {
  min-height: 46px;
}

.bottom-status-strip {
  min-height: 46px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 0 14px;
  background: #ffffff;
}

.bottom-status-strip strong {
  color: #0f172a;
  font-size: 13px;
  white-space: nowrap;
}

.bottom-status-strip span,
.bottom-status-strip em {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bottom-status-strip em {
  text-align: right;
}

.bottom-tabs {
  display: flex;
  gap: 8px;
}

.bottom-tabs button {
  min-height: 28px;
  padding: 0 10px;
  font-size: 12px;
}

.bottom-tabs button.active {
  border-color: #1d4ed8;
  background: #eff6ff;
  color: #1d4ed8;
}

.event-panel,
.comparison-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.section-caption {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #fafcff;
  font-size: 12px;
  font-weight: 800;
}

.event-table,
.compare-table {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.event-table-head,
.event-row {
  width: 100%;
  display: grid;
  grid-template-columns: 82px 220px 72px 72px minmax(140px, 1fr) 96px 84px;
  gap: 10px;
  align-items: center;
}

.event-table-head {
  min-height: 34px;
  padding: 0 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #6b778c;
  font-size: 12px;
  font-weight: 800;
}

.event-row {
  min-height: 42px;
  border: 0;
  border-bottom: 1px solid #e2e8f0;
  border-radius: 6px;
  text-align: left;
  background: #ffffff;
  padding: 0 12px;
}

.event-row.active {
  background: #f1f7ff;
}

.event-row.warn {
  border-left: 4px solid #dc2626;
}

.event-row span,
.event-row em,
.event-row small,
.event-row i,
.event-row u {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-row u {
  color: #1d4ed8;
  font-weight: 800;
}

.event-row u:hover {
  color: #1e40af;
  text-decoration: underline;
}

.event-row strong,
.event-row b {
  min-width: 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-row b {
  color: #c2410c;
}

.compare-table {
  min-width: 600px;
}

.compare-head,
.compare-row {
  display: grid;
  grid-template-columns: 88px repeat(5, minmax(82px, 1fr));
  gap: 8px;
  align-items: center;
  padding: 9px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.compare-head {
  background: #f8fafc;
  color: #6b778c;
  font-size: 12px;
  font-weight: 800;
}

.compare-row strong,
.compare-row b {
  color: #0f172a;
  font-size: 13px;
}

.compare-row span,
.compare-row em {
  color: #475569;
  font-size: 12px;
  font-style: normal;
}

.quality-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.quality-row {
  display: grid;
  grid-template-columns: 160px minmax(180px, 260px) minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
}

.quality-row strong {
  color: #0f172a;
  font-size: 13px;
}

.quality-row span,
.quality-row em {
  color: #475569;
  font-size: 12px;
  font-style: normal;
}

.empty {
  padding: 14px;
  color: #6b778c;
  font-size: 12px;
}

.empty-block {
  padding: 18px 14px;
}

.selected-case-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 8px;
}

.selected-case-card {
  display: grid;
  gap: 4px;
  min-width: 0;
  min-height: 86px;
  padding: 10px;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  background: #ffffff;
  color: #334155;
  text-align: left;
  cursor: pointer;
}

.selected-case-card.active {
  border-color: #2563eb;
  background: #eff6ff;
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.16);
}

.selected-case-card strong {
  color: #0f172a;
  font-size: 15px;
}

.selected-case-card span,
.selected-case-card em {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-case-card em {
  color: #475569;
}

.case-evidence-band {
  display: grid;
  grid-template-columns: minmax(220px, 34%) minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}

.case-evidence-band img {
  width: 100%;
  min-height: 118px;
  max-height: 180px;
  object-fit: contain;
  border: 1px solid #dbe4f0;
  border-radius: 6px;
  background: #ffffff;
}

.case-evidence-copy {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.case-evidence-copy strong {
  color: #0f172a;
  font-size: 14px;
}

.case-evidence-copy p {
  margin: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.case-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.case-metric-grid span {
  min-width: 0;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
}

.case-metric-grid b,
.case-metric-grid em {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-metric-grid b {
  color: #0f172a;
  font-size: 14px;
}

.case-metric-grid em {
  margin-top: 3px;
  color: #64748b;
  font-size: 11px;
  font-style: normal;
}

@media (max-width: 1380px) {
  .workbench-grid {
    grid-template-columns: 188px minmax(0, 1fr) 328px;
  }

  .workbench-grid.analysis-expanded {
    grid-template-columns: 160px minmax(320px, 0.5fr) minmax(560px, 1.5fr);
  }
}

@media (max-width: 1180px) {
  .workbench-grid {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .workbench-grid.analysis-expanded {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .agent-panel {
    grid-column: 1 / -1;
  }

  .settings-grid,
  .quality-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .demo-header {
    flex-direction: column;
    align-items: stretch;
    padding: 10px 12px;
  }

  .header-toolbar {
    width: 100%;
  }

  .header-title-row {
    flex-wrap: wrap;
  }

  .workbench-grid,
  .case-actions {
    grid-template-columns: 1fr;
  }

  .selected-case-strip,
  .case-evidence-band,
  .case-metric-grid,
  .recognition-note,
  .recognition-rule-grid {
    grid-template-columns: 1fr;
  }

  .workbench-grid.analysis-expanded {
    grid-template-columns: 1fr;
  }

  .logic-branches {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .demo-main {
    padding: 10px;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .primary-actions {
    width: 100%;
    justify-content: stretch;
  }

  .primary-actions button,
  .upload-btn,
  select {
    width: 100%;
  }

  .bottom-status-strip {
    grid-template-columns: 1fr;
    gap: 4px;
    padding: 8px 12px;
  }

  .bottom-status-strip em {
    text-align: left;
  }

  .panel-title {
    align-items: flex-start;
    flex-direction: column;
    padding: 9px 12px;
  }

  .event-row {
    grid-template-columns: 70px minmax(170px, 1fr);
  }

  .event-table-head {
    display: none;
  }

  .event-row em,
  .event-row b,
  .event-row small,
  .event-row i,
  .event-row u {
    display: none;
  }

  .summary-bar {
    padding: 8px 10px;
    white-space: normal;
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .summary-bar span:not(:last-child)::after {
    content: '';
    margin: 0;
  }
}
</style>
