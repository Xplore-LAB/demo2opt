<template>
  <section
    class="step-group"
    :class="{ active: group.isCurrent, collapsed: !group.isExpanded }"
    :data-testid="`step-group-${group.key}`"
  >
    <button class="step-group-head" type="button" @click="$emit('toggle-group', group)">
      <div class="step-group-title">
        <strong>{{ group.title }}</strong>
        <span class="step-group-meta">
          <span class="step-state-pill" :class="`state-${group.state}`">{{ group.stateText }}</span>
          <span>{{ group.runtimeText }}</span>
          <span>{{ group.eventCount }} 条事件</span>
        </span>
      </div>
      <span class="step-group-toggle">{{ group.isExpanded ? '收起' : '展开' }}</span>
    </button>

    <div v-if="group.isExpanded" class="step-group-body">
      <div v-if="group.typewriterText" class="step-heartbeat" :data-testid="`step-heartbeat-${group.key}`">
        <span class="thinking-spinner active"></span>
        <span>{{ group.typewriterText }}</span>
      </div>

      <article v-for="(item, idx) in group.items" :key="`${group.key}-${item.id || item.type}-${idx}`" class="message" :class="item.role">
        <div class="avatar">{{ item.role === 'user' ? '用户' : 'AI' }}</div>
        <div class="message-main">
          <div class="bubble" :class="[item.level || 'info', item.type]">
            <div v-if="item.title" class="bubble-title">{{ item.title }}</div>

            <template v-if="item.type === 'interaction'">
              <div class="interaction-meta">
                <span class="risk-pill" :class="`risk-${item.riskLevel || 'low'}`">风险 {{ riskLevelText(item.riskLevel || 'low') }}</span>
                <span v-if="item.blocking" class="blocking-tag">需确认</span>
              </div>
              <div class="markdown" v-html="renderMarkdown(item.desc)"></div>
              <div v-if="item.impactScope?.length" class="bubble-meta">影响范围：{{ item.impactScope.join(' / ') }}</div>
              <div v-if="!item.answered" class="bubble-meta">请在下方行动卡做出决策。</div>
              <div v-else class="bubble-meta">已回复：{{ item.answerText }}</div>
            </template>

            <template v-else-if="item.type === 'thinking'">
              <div class="thinking-head">
                <span class="thinking-spinner" :class="{ active: item.pending }"></span>
                <strong>{{ item.pending ? 'AI 正在思考' : 'AI 过程记录' }}</strong>
              </div>
              <div class="bubble-meta">{{ item.summary || '阶段过程摘要' }}</div>
              <div class="thinking-list">
                <div v-if="!item.isExpanded && item.entries.length > thinkingPreviewLimit" class="thinking-overflow">
                  还有 {{ item.entries.length - thinkingPreviewLimit }} 条过程消息已合并
                </div>
                <div v-for="(entry, entryIdx) in getThinkingPreview(item)" :key="`${idx}-${entryIdx}`" class="thinking-line">
                  <div class="markdown" v-html="renderMarkdown(entry.text)"></div>
                </div>
              </div>
              <div v-if="item.entries.length" class="thinking-actions">
                <button
                  v-if="item.entries.length > thinkingPreviewLimit"
                  class="inline-link-btn"
                  type="button"
                  @click="$emit('toggle-thinking', item)"
                >
                  {{ item.isExpanded ? '收起过程详情' : '展开全部过程' }}
                </button>
                <button
                  class="inline-link-btn secondary"
                  type="button"
                  @click="$emit('open-thinking-detail', item, group)"
                >
                  查看详情
                </button>
              </div>
            </template>

            <template v-else>
              <div class="markdown" v-html="renderMarkdown(item.text)"></div>
            </template>
          </div>
          <div class="bubble-time">{{ item.time }}</div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({
  group: { type: Object, required: true },
  thinkingPreviewLimit: { type: Number, required: true },
  riskLevelText: { type: Function, required: true },
  renderMarkdown: { type: Function, required: true },
  getThinkingPreview: { type: Function, required: true },
})

defineEmits(['toggle-group', 'toggle-thinking', 'open-thinking-detail'])
</script>

<style scoped>
.step-group{margin:10px 0 14px;border:1px solid var(--ui-border);border-radius:8px;background:rgba(255,255,255,.76);overflow:hidden}
.step-group.active{border-color:#93c5fd;box-shadow:0 0 0 1px rgba(147,197,253,.28)}
.step-group-head{width:100%;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 12px;border:none;background:linear-gradient(180deg,rgba(239,246,255,.56),rgba(248,250,252,.92));cursor:pointer;text-align:left}
.step-group-title{display:grid;gap:4px}
.step-group-title strong{font-size:13px;line-height:1.3}
.step-group-meta{display:flex;flex-wrap:wrap;gap:8px;color:var(--ui-muted);font-size:12px}
.step-group-toggle{color:var(--ui-primary);font-size:12px;font-weight:700}
.step-group-body{padding:10px 12px 4px}
.step-heartbeat{display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:10px;border:1px dashed rgba(37,99,235,.25);border-radius:7px;background:rgba(239,246,255,.74);color:#1d4ed8;font-size:12px}
.step-state-pill{display:inline-flex;align-items:center;min-height:20px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:700}
.step-state-pill.state-running{background:#eff6ff;color:#1d4ed8}
.step-state-pill.state-completed{background:#ecfdf3;color:#15803d}
.step-state-pill.state-failed{background:#fef2f2;color:#b91c1c}
.step-state-pill.state-pending{background:#f3f4f6;color:#6b7280}
.message{display:flex;align-items:flex-start;gap:12px;margin-bottom:12px}
.message.user{flex-direction:row-reverse}
.message-main{display:flex;align-items:flex-end;gap:10px;max-width:min(92%,760px)}
.message.user .message-main{flex-direction:row-reverse}
.avatar{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-surface-tint);color:var(--ui-primary);font-size:12px;font-weight:700}
.message.user .avatar{background:#f0fdf4;color:var(--ui-success)}
.bubble{width:fit-content;max-width:min(100%,660px);padding:10px 12px 9px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-surface);line-height:1.58}
.message.ai .bubble{font-size:13px}
.message.user .bubble{background:var(--ui-surface-tint);border-color:#bfdbfe}
.bubble.info,.bubble.intro{background:var(--ui-surface-soft)}
.bubble.success{background:#f0fdf4;border-color:#bbf7d0}
.bubble.error{background:#fef2f2;border-color:#fecaca}
.bubble.interaction{background:var(--ui-surface-tint);border-color:#bfdbfe}
.bubble.thinking{background:linear-gradient(180deg,#f8fbff,#eef6ff);border-color:#c7dcff}
.bubble-title{margin-bottom:6px;font-weight:700}
.interaction-meta{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.bubble-time{flex:0 0 auto;padding-bottom:2px;font-size:11px;line-height:1;color:var(--ui-muted);white-space:nowrap}
.thinking-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.thinking-spinner{width:12px;height:12px;border:2px solid rgba(37,99,235,.22);border-top-color:var(--ui-primary);border-radius:999px}
.thinking-spinner.active{animation:stream-spin .8s linear infinite}
.thinking-list{display:grid;gap:8px}
.thinking-overflow{font-size:11px;color:var(--ui-muted)}
.thinking-line{padding:6px 8px;border:1px dashed rgba(37,99,235,.18);border-radius:6px;background:rgba(255,255,255,.58)}
.thinking-actions{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:8px}
.inline-link-btn{margin-top:8px;border:none;background:none;color:var(--ui-primary);cursor:pointer;font-size:12px;padding:0}
.thinking-actions .inline-link-btn{margin-top:0}
.inline-link-btn.secondary{color:#475569}
.risk-pill{display:inline-flex;align-items:center;min-height:20px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:700}
.risk-pill.risk-low{background:#ecfdf3;color:#15803d}
.risk-pill.risk-medium{background:#fffbeb;color:#b45309}
.risk-pill.risk-high{background:#fff7ed;color:#c2410c}
.risk-pill.risk-critical{background:#fef2f2;color:#b91c1c}
.blocking-tag{display:inline-flex;align-items:center;min-height:20px;padding:0 8px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-size:11px;font-weight:700}
@keyframes stream-spin{to{transform:rotate(360deg)}}
</style>
