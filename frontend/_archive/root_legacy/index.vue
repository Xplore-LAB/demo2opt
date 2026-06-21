<!-- 每个回话对应的聊天内容 -->
<script setup lang="ts">
import type { AnyObject } from 'typescript-api-pro'
import type { Sender } from 'vue-element-plus-x'
import type { BubbleProps } from 'vue-element-plus-x/types/Bubble'
import type { BubbleListInstance } from 'vue-element-plus-x/types/BubbleList'
import type { FilesCardProps } from 'vue-element-plus-x/types/FilesCard'
import type { ThinkingStatus } from 'vue-element-plus-x/types/Thinking'
import { ElMessage } from 'element-plus'

defineOptions({
  name: 'ChatWithId',
})

// 图表内容接口定义
interface ChartContent {
  title: string
  chartType: 'line' | 'bar' | 'pie' | 'scatter' | 'area'
  data: any // ECharts配置数据
  query?: string // SQL查询语句（可选）
  dataSource?: string // 数据源（可选）
  queryTime?: number // 查询耗时（可选）
}

// 表格数据接口定义
export interface TableData {
  title?: string // 表格标题
  columns: string[] // 列名数组
  rows: any[][] // 数据行数组
  totalRows?: number // 总行数（用于分页）
  query?: string // 查询语句（可选）
  dataSource?: string // 数据源（可选）
  queryTime?: number // 查询耗时（可选）
  originalQuery?: string // 用户原始查询问题
  recommendedChartType?: string // 推荐的图表类型
}

// 扩展BubbleProps类型以支持打字机效果、图表消息和表格消息
interface ExtendedBubbleProps extends BubbleProps {
  // typewriterTimer?: number | null; // 暂时禁用打字机效果
  responseTime?: number // 响应时间
  thinkCollapse?: boolean // 思考内容折叠状态
  reasoning_content?: string // 思考推理内容
  thinking_time?: number // 思考用时
  thinking_start?: number // 思考开始时间
  isThinking?: boolean
  // 图表相关属性
  messageType?: 'text' | 'chart' | 'table' | undefined // 消息类型，新增table类型
  chartContent?: ChartContent // 图表内容
  // 表格相关属性
  tableData?: TableData // 表格数据内容
  // 数据溯源相关属性
  provenanceMarkdown?: string // 数据溯源Markdown内容
  provenanceExtracted?: boolean // 是否已提取数据溯源
  // 原始查询相关属性
  originalQuery?: string // 用户原始查询
}

import type { OpenAIResponse } from '@/utils/request'
import { useHookFetch } from 'hook-fetch/vue'
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
// import ChartBubble from '@/components/ChartBubble/index.vue'
import TableBubble from '@/components/TableBubble/index.vue'
import { useMarkdown } from '@/composables/chat/useMarkdown'
// import ModelSelect from '@/components/ModelSelect/index.vue'
import { getUserAvatar } from '@/config/avatars'
import { useChatStore } from '@/stores/modules/chat'
import { useFilesStore } from '@/stores/modules/files'
import { useModelStore } from '@/stores/modules/model'
import { useUserStore } from '@/stores/modules/user'
import { initImageRenderer, processMessageImages } from '@/utils/imageRenderer'
import { addImageClickToEnlarge, processHtmlImages, processMarkdownImages } from '@/utils/imageUtils'
import { processMermaidCharts } from '@/utils/mermaidUtils'
// import { send } from '@/api'; // 暂时注释掉未使用的导入
import { aiRequest } from '@/utils/request'

// 移除未使用的marked导入

type MessageItem = ExtendedBubbleProps & {
  key: number
  role: 'ai' | 'user' | 'system'
  avatar: string
  thinkingStatus?: ThinkingStatus
}

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const modelStore = useModelStore()
const filesStore = useFilesStore()
const userStore = useUserStore()
const { renderMarkdown } = useMarkdown()
const renderMessageMarkdown = renderMarkdown

// 用户头像 - 使用统一的头像配置
const avatar = computed(() => getUserAvatar(userStore.userInfo))

const inputValue = ref('')
const senderRef = ref<InstanceType<typeof Sender> | null>(null)
const bubbleItems = ref<MessageItem[]>([])
const bubbleListRef = ref<BubbleListInstance | null>(null)

// 流式响应控制
const enableStreamResponse = ref(true) // 默认启用流式响应

// 添加控制思考区域显示的响应式变量
const showThinkingArea = ref(true) // 默认不显示思考区域

// 添加控制Markdown渲染的响应式变量
const enableMarkdownRender = ref(false) // 默认启用Markdown渲染

// 移除了Dify相关变量，现在只使用aipost

const { stream, loading: isLoading, cancel } = useHookFetch({
  request: aiRequest.post,
  onError: (err) => {
    console.error('=== OpenAI API useHookFetch错误拦截 ===')
    console.error('错误详情:', err)
    console.error('错误类型:', typeof err)
    console.error('错误消息:', err?.message)
    console.error('错误状态:', (err as any)?.status)
  },
})

// 移除了Dify API的useHookFetch实例，现在只使用aipost
// 流式响应完成标志
let streamCompleted = false

// 存储当前用户查询，用于表格数据的originalQuery字段
let currentUserQuery = ''

// 计时器相关变量
const responseTimer = ref<number>(0) // 当前响应时间（秒）
const timerInterval = ref<NodeJS.Timeout | null>(null) // 计时器间隔
const isTimerRunning = ref(false) // 计时器是否正在运行
const finalResponseTime = ref<number>(0) // 最终响应时间

watch(
  () => route.params?.id,
  async (_id_) => {
    if (_id_) {
      // 如果会话ID是'error'，显示错误信息
      if (_id_ === 'error') {
        console.error('会话创建失败，显示错误信息')
        // 显示用户友好的错误消息
        ElMessage.error({
          message: '会话创建失败，请稍后重试或联系管理员',
          duration: 5000,
        })
        // 添加一条系统消息说明错误
        if (bubbleItems.value.length === 0) {
          addMessage('抱歉，会话创建失败。可能是由于网络问题或服务器暂时不可用。请稍后重试或联系管理员。', false, false, 'text')
        }
        return
      }

      if (_id_ !== 'not_login') {
        // 判断的当前会话id是否有聊天记录，有缓存则直接赋值展示
        if (chatStore.chatMap[`${_id_}`] && chatStore.chatMap[`${_id_}`].length) {
          const cachedHistory = chatStore.chatMap[`${_id_}`] as MessageItem[]
          // 处理缓存中的图片路径
          bubbleItems.value = cachedHistory.map((item) => {
            if (item.role !== 'user' && item.content) {
              // 对AI消息进行图片路径处理
              let processedContent = item.content
              processedContent = processHtmlImages(processedContent)
              processedContent = processMarkdownImages(processedContent)
              return { ...item, content: processedContent }
            }
            return item
          })
          // 滚动到底部
          setTimeout(() => {
            if (bubbleListRef.value) {
              bubbleListRef.value.scrollToBottom()
            }
            else {
              console.warn('bubbleListRef.value is null or undefined when trying to scroll to bottom.')
            }
          }, 350)
          return
        }

        // 注释掉消息列表请求 - 用户已取消会话列表功能，不需要从后端恢复历史消息
        // await chatStore.requestChatList(`${_id_}`);
        // 新会话直接初始化为空数组，不从后端获取历史消息
        bubbleItems.value = []
        console.log('新会话初始化，会话ID:', _id_)

        // 为历史消息中的图片添加点击放大功能
        addImageClickHandlers()

        // 滚动到底部
        setTimeout(() => {
          bubbleListRef.value!.scrollToBottom()
        }, 350)
      }

      // 如果本地有发送内容 ，则直接发送
      const v = localStorage.getItem('chatContent')
      if (v) {
        // 立即显示用户消息，避免空白页面
        console.log('检测到localStorage中的消息，立即显示用户消息:', v)
        addMessage(v, true, false) // 立即添加用户消息到界面

        // 发送消息
        console.log('发送消息 v', v)
        // 恢复消息时不应该清空输入框，因为输入框中可能有用户正在编辑的内容
        setTimeout(() => {
          // 修改startSSE调用，传入skipUserMessage参数避免重复添加用户消息
          startSSEWithoutUserMessage(v) // 使用新函数，不重复添加用户消息
        }, 350)

        localStorage.removeItem('chatContent')
      }
    }
  },
  { immediate: true, deep: true },
)

// 打字机效果的延迟时间（毫秒）- 暂时禁用
// const TYPEWRITER_DELAY = 30;

// 工具：安全追加，避免重复内容（SSE重复片段、双通道调用）
function appendIfNew(target: any, key: 'content' | 'reasoning_content', text: string) {
  if (!text)
    return
  const t = String(text)
  if (!t.trim())
    return
  const current = String((target as any)[key] || '')
  if (current.endsWith(t)) {
    console.log(`🔁 [DEDUP] 跳过重复追加 ${key}:`, t)
    return
  }
  ;(target as any)[key] = current + t
}

// 优化的Markdown渲染函数，减少多余空行

// 简化的换行符处理函数 - 暂时注释掉，因为已经不再使用
/* function optimizeNewlines(content: string): string {
  if (!content) return ''

  // 添加调试信息
  console.log('🔄 [AI消息格式调试] 换行符处理前:', content)

  // 简单的换行符处理：只将换行符转换为<br>
  const result = content.replace(/\n/g, '<br>')

  // 添加调试信息
  console.log('✅ [AI消息格式调试] 换行符处理后:', result)

  return result
} */

// 提取"查询结果"中的耗电量数值与日期（仅用于chat模块AI消息的指标看板）
// 暂时注释掉未使用的函数
/* function extractPowerKPI(content?: string): {
  valueDisplay: string
  valueNumber: number
  unit: string
} | null {
  if (!content || typeof content !== 'string') return null;

  if (!/查询结果|耗电量/.test(content)) return null;

  const text = content.replace(/<[^>]+>/g, '');

  const valueReg = /([\-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(千瓦时|kWh)/i;
  const valueMatch = text.match(valueReg);

  if (!valueMatch) return null;

  const rawValue = valueMatch[1];
  const unit = valueMatch[2] || '千瓦时';
  const valueNumber = Number.parseFloat(rawValue.replace(/,/g, ''));

  if (Number.isNaN(valueNumber)) return null;

  const valueDisplay = `${rawValue} ${unit}`;

  return {
    valueDisplay,
    valueNumber,
    unit,
  };
} */

// 提取数据溯源信息的函数 - 暂时禁用
/*
function extractProvenanceSection(content: string): { mainContent: string; provenanceContent: string } {
  // 匹配数据溯源相关的标题和内容
  const provenanceRegex = /(?:^|\n)(?:📊\s*)?(?:数据溯源信息|数据来源|数据溯源|溯源信息)(?:[：:]?\s*)?([\s\S]*?)(?=\n\n|$)/gi

  let provenanceContent = ''
  let mainContent = content

  const matches = content.match(provenanceRegex)
  if (matches && matches.length > 0) {
    // 提取所有匹配的溯源内容
    provenanceContent = matches.join('\n\n')
    // 从主内容中移除溯源部分
    mainContent = content.replace(provenanceRegex, '').trim()
  }

  return {
    mainContent,
    provenanceContent: provenanceContent.trim()
  }
}
*/

// 直接处理content内容的函数（暂时取消打字机效果）
function processContentDirectly(content: string) {
  if (!content || !bubbleItems.value.length) {
    console.log('🔍 [DEBUG] processContentDirectly: 内容为空或消息列表为空，跳过处理')
    return
  }

  console.log('🔍 [DEBUG] processContentDirectly: 开始处理内容:', content)
  console.log('🔍 [DEBUG] processContentDirectly: 内容类型:', typeof content)
  console.log('🔍 [DEBUG] processContentDirectly: 内容长度:', content.length)

  // 使用统一的Unicode解码函数
  const processedContent = decodeUnicodeContent(content)
  console.log('🔍 [DEBUG] processContentDirectly: 解码后内容:', processedContent)

  // 🔧 增强：检测和处理JSON格式的表格数据
  try {
    // 检测内容是否为JSON格式
    const trimmedContent = processedContent.trim()
    console.log('🔍 [DEBUG] processContentDirectly: 检查JSON格式 - 开始字符:', trimmedContent.charAt(0))
    console.log('🔍 [DEBUG] processContentDirectly: 检查JSON格式 - 结束字符:', trimmedContent.charAt(trimmedContent.length - 1))
    console.log('🔍 [DEBUG] processContentDirectly: 是否包含table_data:', trimmedContent.includes('table_data'))

    if (trimmedContent.startsWith('{') && trimmedContent.endsWith('}')) {
      console.log('🔍 [DEBUG] processContentDirectly: 检测到JSON格式内容，尝试解析...')
      const jsonData = JSON.parse(trimmedContent)
      console.log('🔍 [DEBUG] processContentDirectly: JSON解析成功:', jsonData)

      // 检查是否包含table_data字段
      if (jsonData.table_data) {
        console.log('✅ [表格数据] processContentDirectly: 检测到table_data，调用handleTableData处理')
        console.log('✅ [表格数据] processContentDirectly: table_data内容:', jsonData.table_data)
        handleTableData(jsonData.table_data)
        return // 处理完表格数据后直接返回，不再进行文本处理
      }
      else {
        console.log('🔍 [DEBUG] processContentDirectly: JSON数据中未找到table_data字段')
        console.log('🔍 [DEBUG] processContentDirectly: JSON数据的键:', Object.keys(jsonData))
      }
    }
    else {
      console.log('🔍 [DEBUG] processContentDirectly: 内容不是JSON格式，继续文本处理')
    }
  }
  catch (jsonError) {
    // JSON解析失败，继续按文本内容处理
    console.log('🔍 [DEBUG] processContentDirectly: JSON解析失败，继续按文本处理:', jsonError)
  }

  // 获取最后一条消息
  const lastBubble = bubbleItems.value[bubbleItems.value.length - 1] as MessageItem

  // 防抖机制：避免流式过程中重复切分数据溯源 - 暂时禁用
  /*
  if (!lastBubble.provenanceExtracted && processedContent.includes('数据溯源')) {
    const { mainContent, provenanceContent } = extractProvenanceSection(processedContent)

    if (provenanceContent) {
      console.log('🔍 [DEBUG] processContentDirectly: 提取到数据溯源信息:', provenanceContent)
      lastBubble.provenanceMarkdown = provenanceContent
      lastBubble.provenanceExtracted = true

      // 使用提取后的主内容继续处理
      const updatedProcessedContent = decodeUnicodeContent(mainContent)
      console.log('🔍 [DEBUG] processContentDirectly: 更新后的主内容:', updatedProcessedContent)

      // 继续使用更新后的内容进行后续处理
      processContentWithProvenance(updatedProcessedContent, lastBubble)
      return
    }
  }
  */

  // 处理普通内容（无数据溯源或已提取过）
  processContentWithProvenance(processedContent, lastBubble)
}

// 处理已提取数据溯源后的内容
function processContentWithProvenance(processedContent: string, lastBubble: MessageItem) {
  // 改进思考处理逻辑，支持跨chunk的增量流，使用bubble级isThinking
  console.log('🔍 [DEBUG] processContentDirectly: 当前消息对象:', {
    role: lastBubble.role,
    reasoning_content_length: lastBubble.reasoning_content?.length || 0,
    isThinking: lastBubble.isThinking,
    thinkingStatus: lastBubble.thinkingStatus,
  })

  if (lastBubble.isThinking === undefined) {
    lastBubble.isThinking = false
  }
  if (!lastBubble.reasoning_content) {
    lastBubble.reasoning_content = ''
    console.log('🔍 [DEBUG] processContentDirectly: 初始化reasoning_content为空字符串')
  }
  if (lastBubble.thinkCollapse === undefined) {
    lastBubble.thinkCollapse = true // 默认收起：保持界面简洁；用户可点击展开；流式时仍可展开观察
  }

  let remainingContent = processedContent

  // 如果已经在思考中
  if (lastBubble.isThinking) {
    console.log('🔍 [DEBUG] processContentDirectly: 当前正在思考中，处理思考内容')
    const endIndex = remainingContent.indexOf('</think>')
    if (endIndex !== -1) {
      const thinkingPart = remainingContent.substring(0, endIndex)
      appendIfNew(lastBubble, 'reasoning_content', decodeUnicodeContent(thinkingPart))
      console.log('🔍 [DEBUG] processContentDirectly: 思考结束，reasoning_content更新为:', lastBubble.reasoning_content)
      lastBubble.thinkingStatus = 'end'
      lastBubble.loading = false
      lastBubble.thinkCollapse = true
      lastBubble.isThinking = false

      // 强制折叠思考过程
      nextTick(() => {
        forceCollapseThinking()
      })
      remainingContent = remainingContent.substring(endIndex + 8)
    }
    else {
      appendIfNew(lastBubble, 'reasoning_content', decodeUnicodeContent(remainingContent))
      console.log('🔍 [DEBUG] processContentDirectly: 继续思考中，reasoning_content更新为:', lastBubble.reasoning_content)
      lastBubble.thinkCollapse = false // 思考进行中应该保持展开状态
      remainingContent = ''
    }
  }
  else {
    const startIndex = remainingContent.indexOf('<think>')
    if (startIndex !== -1) {
      console.log('🚨 [THINK DETECTED] 识别到思考标签！当前状态:', {
        thinkCollapse: lastBubble.thinkCollapse,
        reasoning_content_length: lastBubble.reasoning_content ? lastBubble.reasoning_content.length : 0,
        isThinking: lastBubble.isThinking,
        loading: lastBubble.loading,
      })

      let normalPart = remainingContent.substring(0, startIndex)
      normalPart = decodeUnicodeContent(normalPart)
      normalPart = processHtmlImages(normalPart)
      normalPart = processMarkdownImages(normalPart)
      appendIfNew(lastBubble, 'content', normalPart)

      remainingContent = remainingContent.substring(startIndex + 7)

      const endIndex = remainingContent.indexOf('</think>')
      if (endIndex !== -1) {
        const thinkingPart = remainingContent.substring(0, endIndex)
        lastBubble.thinkingStatus = 'thinking'
        lastBubble.loading = true
        appendIfNew(lastBubble, 'reasoning_content', decodeUnicodeContent(thinkingPart))
        console.log('🔍 [DEBUG] processContentDirectly: 完整思考内容，reasoning_content更新为:', lastBubble.reasoning_content)
        lastBubble.thinkingStatus = 'end'
        lastBubble.loading = false
        lastBubble.thinkCollapse = true
        lastBubble.isThinking = false

        // 强制折叠思考过程
        nextTick(() => {
          forceCollapseThinking()
        })
        remainingContent = remainingContent.substring(endIndex + 8)
      }
      else {
        lastBubble.thinkingStatus = 'thinking'
        lastBubble.loading = true
        appendIfNew(lastBubble, 'reasoning_content', decodeUnicodeContent(remainingContent))
        console.log('🔍 [DEBUG] processContentDirectly: 思考开始，reasoning_content更新为:', lastBubble.reasoning_content)
        lastBubble.thinkCollapse = false // 思考开始时应该展开，不是折叠
        lastBubble.isThinking = true
        remainingContent = ''
      }
    }
    else {
      // 无<think>标签时，直接处理普通内容
      console.log('🔍 [DEBUG] processContentDirectly: 无思考标签，处理普通内容')
      let finalContent = decodeUnicodeContent(remainingContent)

      finalContent = processHtmlImages(finalContent)
      finalContent = processMarkdownImages(finalContent)
      // 修复SQL语句识别：在流式响应中也要调用formatSqlInMessage函数
      finalContent = formatSqlInMessage(finalContent)
      appendIfNew(lastBubble, 'content', finalContent)
      // 修复：该分支已消费 remainingContent，置空避免在后续“处理剩余普通内容”中再次追加
      remainingContent = ''
    }
  }

  // 处理剩余普通内容（不包括思考内容）
  if (remainingContent) {
    let finalContent = decodeUnicodeContent(remainingContent)
    finalContent = processHtmlImages(finalContent)
    finalContent = processMarkdownImages(finalContent)
    // 修复SQL语句识别：在处理剩余内容时也要调用formatSqlInMessage函数
    finalContent = formatSqlInMessage(finalContent)
    appendIfNew(lastBubble, 'content', finalContent)

    nextTick(() => {
      const container = document.querySelector('.bubble-list') as HTMLElement
      if (container) {
        processMermaidCharts(container)
      }
    })

    addImageClickHandlers()
  }

  if (!lastBubble.isThinking) {
    lastBubble.thinkingStatus = 'end'
    lastBubble.loading = false

    // 如果有思考内容且思考结束，强制折叠
    if (lastBubble.reasoning_content) {
      lastBubble.thinkCollapse = true
      nextTick(() => {
        forceCollapseThinking()
      })
    }
  }

  // 滚动到底部
  nextTick(() => {
    if (bubbleListRef.value) {
      bubbleListRef.value.scrollToBottom()
    }
  })
}

// 打字机效果函数 - 暂时禁用
/*
function addContentWithTypewriter(content: string) {
  if (!content || !bubbleItems.value.length) {
    return;
  }

  const lastBubble = bubbleItems.value[bubbleItems.value.length - 1];

  // 如果内容很短（少于3个字符），直接添加，但保持typing状态
  if (content.length <= 3) {
    lastBubble.content += content;
    // 不要在这里关闭typing状态，让它在响应完全结束时才关闭
    addImageClickHandlers();
    return;
  }

  // 将内容分割成字符数组（正确处理Unicode字符）
  const chars = Array.from(content);
  let currentIndex = 0;

  // 清除之前的定时器（如果存在）
  if (lastBubble.typewriterTimer) {
    clearInterval(lastBubble.typewriterTimer);
  }

  // 创建打字机定时器
  lastBubble.typewriterTimer = setInterval(() => {
    if (currentIndex < chars.length) {
      lastBubble.content += chars[currentIndex];
      currentIndex++;

      // 滚动到底部
      nextTick(() => {
        if (bubbleListRef.value) {
          bubbleListRef.value.scrollToBottom();
        }
      });
    }
    else {
      // 打字机效果完成，但保持typing状态直到整个响应结束
      if (lastBubble.typewriterTimer) {
        clearInterval(lastBubble.typewriterTimer);
      }
      lastBubble.typewriterTimer = null;
      // 不要在这里关闭typing状态，让它在整个响应流结束时才关闭

      // 为更新的消息中的图片添加点击放大功能
      addImageClickHandlers();
    }
  }, TYPEWRITER_DELAY);
}
*/

// 已弃用：生成思考内容的HTML结构，改用#content插槽在模板中渲染
// 保留注释记录历史方案，防止未使用声明导致构建失败
// function generateThinkingHtml(content: string, isCollapsed: boolean = true, bubbleKey?: string): string {
//   /* deprecated: use template-based rendering */
//   return ''
// }

// 已弃用：更新思考内容显示状态逻辑，改为依赖响应式状态与模板
// function updateThinkingDisplay(_bubble: any) {
//   /* deprecated: handled by Vue template */
// }

// 计时器控制函数
function startResponseTimer() {
  console.log('开始计时器')
  responseTimer.value = 0
  isTimerRunning.value = true

  // 清除之前的计时器
  if (timerInterval.value) {
    clearInterval(timerInterval.value as any)
  }

  // 每100毫秒更新一次计时器
  timerInterval.value = setInterval(() => {
    responseTimer.value += 0.1
  }, 100)
}

function stopResponseTimer() {
  console.log('停止计时器，最终时间:', `${responseTimer.value.toFixed(1)}s`)
  isTimerRunning.value = false
  finalResponseTime.value = responseTimer.value

  if (timerInterval.value) {
    clearInterval(timerInterval.value as any)
    timerInterval.value = null
  }
}

function resetResponseTimer() {
  console.log('重置计时器')
  responseTimer.value = 0
  finalResponseTime.value = 0
  isTimerRunning.value = false

  if (timerInterval.value) {
    clearInterval(timerInterval.value as any)
    timerInterval.value = null
  }
}

// 统一的Unicode解码函数
function decodeUnicodeContent(content: string): string {
  if (!content || typeof content !== 'string') {
    return content
  }

  let decodedContent = content

  try {
    // 首先尝试JSON解析（如果是JSON字符串格式）
    if (decodedContent.startsWith('"') && decodedContent.endsWith('"')) {
      try {
        decodedContent = JSON.parse(decodedContent)
      }
      catch (jsonError) {
        console.warn('JSON解析失败，继续使用原始字符串:', jsonError)
      }
    }

    // 处理各种Unicode编码格式
    // 1. 处理\uXXXX格式
    decodedContent = decodedContent.replace(/\\u([0-9a-fA-F]{4})/g, (_: string, code: string) => {
      return String.fromCharCode(Number.parseInt(code, 16))
    })

    // 2. 处理\u{XXXXX}格式
    decodedContent = decodedContent.replace(/\\u\{([0-9a-fA-F]+)\}/g, (_: string, code: string) => {
      return String.fromCodePoint(Number.parseInt(code, 16))
    })

    // 3. 处理%uXXXX格式
    decodedContent = decodedContent.replace(/%u([0-9a-fA-F]{4})/g, (_: string, code: string) => {
      return String.fromCharCode(Number.parseInt(code, 16))
    })

    // 4. 处理HTML实体编码
    decodedContent = decodedContent.replace(/&#(\d+);/g, (_: string, code: string) => {
      return String.fromCharCode(Number.parseInt(code, 10))
    })

    // 5. 处理十六进制HTML实体编码
    decodedContent = decodedContent.replace(/&#x([0-9a-fA-F]+);/g, (_: string, code: string) => {
      return String.fromCharCode(Number.parseInt(code, 16))
    })

    // 6. 尝试decodeURIComponent解码
    try {
      const decoded = decodeURIComponent(decodedContent)
      if (decoded !== decodedContent) {
        decodedContent = decoded
      }
    }
    catch {
      // 解码失败，继续使用原始字符串
    }
  }
  catch (error) {
    console.warn('Unicode解码失败:', error)
  }

  return decodedContent
}

// 移除未使用的renderMarkdown函数
// 封装数据处理逻辑
function handleDataChunk(chunk: AnyObject) {
  console.log('=== 处理OpenAI数据块 ===')
  console.log('原始数据:', chunk)
  console.log('数据类型:', typeof chunk)

  // 🔍 添加详细调试信息
  console.log('🔍 [调试] handleDataChunk被调用')
  console.log('🔍 [调试] chunk.result:', chunk.result)
  console.log('🔍 [调试] chunk.source:', chunk.source)
  console.log('🔍 [调试] chunk.table_data:', chunk.table_data)
  console.log('🔍 [调试] chunk.data?.table_data:', chunk.data?.table_data)
  console.log('🔍 [调试] 当前bubbleItems长度:', bubbleItems.value.length)

  // 处理blocking模式的完整响应
  if (chunk.answer && !chunk.event) {
    console.log('处理blocking模式响应')

    // 使用统一的Unicode解码函数
    let processedContent = decodeUnicodeContent(chunk.answer)
    processedContent = processHtmlImages(processedContent)
    processedContent = processMarkdownImages(processedContent)

    // 替换整个内容（blocking模式是完整响应）
    if (bubbleItems.value.length) {
      bubbleItems.value[bubbleItems.value.length - 1].content = processedContent
      console.log('blocking模式内容设置完成，长度:', processedContent.length)
      // blocking模式下内容设置完成后设置完成标志并结束typing状态
      streamCompleted = true
      finishResponse()
    }
    return
  }

  try {
    // 检查是否是SSE格式的原始数据
    let processedChunk = chunk

    // 如果chunk是字符串且包含SSE格式数据，需要解析
    if (typeof chunk === 'string') {
      console.log('检测到字符串格式的SSE数据，开始解析...')

      const rawText = chunk as string
      console.log('原始SSE数据长度:', rawText.length)
      console.log(`原始SSE数据预览: ${rawText.substring(0, 200)}...`)

      // 检查是否是连续的结构化数据（没有正确的SSE格式分隔）
      console.log('🔍 [DEBUG] 检查连续数据流条件:')
      console.log('🔍 [DEBUG] 包含 data: {"id":', rawText.includes('data: {"id":'))
      console.log('🔍 [DEBUG] 包含 "object": "chat.completion.chunk":', rawText.includes('"object": "chat.completion.chunk"'))

      if (rawText.includes('data: {"id":') && rawText.includes('"object": "chat.completion.chunk"')) {
        console.log('✅ 检测到连续的结构化数据流，开始解析...')

        // 使用正则表达式分割连续的data块
        const dataBlocks = rawText.split(/(?=data: \{)/g).filter((block: string) => block.trim())
        console.log('🔍 [DEBUG] 分割出的数据块数量:', dataBlocks.length)
        console.log('🔍 [DEBUG] 数据块详情:', dataBlocks)

        for (const block of dataBlocks) {
          const trimmedBlock = block.trim()
          if (!trimmedBlock)
            continue

          console.log('处理数据块:', `${trimmedBlock.substring(0, 100)}...`)

          // 处理data:开头的块
          if (trimmedBlock.startsWith('data:')) {
            const dataContent = trimmedBlock.substring(5).trim()
            console.log('🔍 [DEBUG] 提取的dataContent:', dataContent)

            // 检测结束标记
            if (dataContent === '[DONE]') {
              console.log('收到SSE结束标记，设置流式响应完成')
              streamCompleted = true
              finishResponse()
              continue
            }

            if (!dataContent) {
              console.log('空的data内容，跳过')
              continue
            }

            // 解析结构化数据并提取content
            try {
              const parsedData = JSON.parse(dataContent)
              console.log('✅ 成功解析数据块:', parsedData)

              // 🔧 优先检查是否包含表格数据
              if (parsedData.table_data) {
                console.log('🔍 [表格数据检测] 在连续数据流中发现table_data字段')
                console.log('🔍 [表格数据] table_data内容:', parsedData.table_data)
                handleTableData(parsedData.table_data)
                continue // 处理完表格数据后跳过content提取
              }

              // 从choices数组中提取content
              if (parsedData.choices && parsedData.choices[0] && parsedData.choices[0].delta && parsedData.choices[0].delta.content) {
                const deltaContent = parsedData.choices[0].delta.content
                console.log('✅ 提取到内容:', deltaContent)
                // 直接处理提取的content，避免递归调用
                processContentDirectly(deltaContent)
              }
              else {
                console.log('🔍 [DEBUG] 数据结构检查:')
                console.log('🔍 [DEBUG] parsedData.choices:', parsedData.choices)
                console.log('🔍 [DEBUG] parsedData.choices?.[0]:', parsedData.choices?.[0])
                console.log('🔍 [DEBUG] parsedData.choices?.[0]?.delta:', parsedData.choices?.[0]?.delta)
                console.log('🔍 [DEBUG] parsedData.choices?.[0]?.delta?.content:', parsedData.choices?.[0]?.delta?.content)
              }
            }
            catch (parseError) {
              console.warn('❌ 解析数据块失败:', parseError)
              console.warn(`原始数据块: ${dataContent.substring(0, 200)}...`)
            }
          }
        }

        return // 处理完连续数据后直接返回
      }

      // 处理标准的SSE格式（按行分割）
      const lines = rawText.split('\n').filter((line: string) => line.trim())
      console.log('分割后的行数:', lines.length)

      for (const line of lines) {
        const trimmedLine = line.trim()

        // 跳过空行和注释行
        if (!trimmedLine || trimmedLine.startsWith(':')) {
          continue
        }

        // 处理SSE事件数据
        if (trimmedLine.startsWith('data:')) {
          const dataContent = trimmedLine.substring(5).trim()
          console.log('提取的数据内容:', dataContent)

          // 检测结束标记
          if (dataContent === '[DONE]') {
            console.log('收到SSE结束标记，设置流式响应完成')
            streamCompleted = true
            finishResponse()
            continue
          }

          if (!dataContent) {
            console.log('空的data内容，跳过')
            continue
          }

          // 尝试解析JSON数据
          try {
            // 使用统一的Unicode解码函数
            const decodedContent = decodeUnicodeContent(dataContent)

            console.log('Unicode解码前:', dataContent)
            console.log('Unicode解码后:', decodedContent)

            const parsedData = JSON.parse(decodedContent)
            console.log('成功解析SSE数据:', parsedData)

            // 🔧 优先检查是否包含表格数据
            if (parsedData.table_data) {
              console.log('🔍 [表格数据检测] 在SSE数据流中发现table_data字段')
              console.log('🔍 [表格数据] table_data内容:', parsedData.table_data)
              handleTableData(parsedData.table_data)
              continue // 处理完表格数据后跳过content提取
            }

            // 🔧 检查是否包含图表数据
            if (parsedData.chart_data) {
              console.log('🔍 [图表数据检测] 在SSE数据流中发现chart_data字段')
              console.log('🔍 [图表数据] chart_data内容:', parsedData.chart_data)
              handleChartData(parsedData.chart_data)
              continue // 处理完图表数据后跳过content提取
            }

            // 🔧 检查是否包含指标看板数据
            if (parsedData.dashboard_data) {
              console.log('🔍 [指标看板数据检测] 在SSE数据流中发现dashboard_data字段')
              console.log('🔍 [指标看板数据] dashboard_data内容:', parsedData.dashboard_data)
              handleDashboardData(parsedData.dashboard_data)
              continue // 处理完指标看板数据后跳过content提取
            }

            // 🔧 检查是否包含溯源数据
            if (parsedData.provenance) {
              console.log('🔍 [溯源数据检测] 在SSE数据流中发现provenance字段')
              console.log('🔍 [溯源数据] provenance内容:', parsedData.provenance)
              handleProvenanceData(parsedData.provenance)
              continue // 处理完溯源数据后跳过content提取
            }

            // 从choices数组中提取content
            if (parsedData.choices && parsedData.choices[0] && parsedData.choices[0].delta && parsedData.choices[0].delta.content) {
              const deltaContent = parsedData.choices[0].delta.content
              console.log('提取到内容:', deltaContent)
              // 直接处理提取的content，避免递归调用
              processContentDirectly(deltaContent)
              continue // 处理完毕，继续下一行
            }
          }
          catch (jsonError) {
            console.warn('SSE数据JSON解析失败:', jsonError)
            console.warn('原始数据内容:', dataContent)
            // 如果JSON解析失败，尝试提取content字段
            try {
              // 尝试从原始数据中提取content内容
              const contentMatch = dataContent.match(/"content"\s*:\s*"([^"]*)"/)
              if (contentMatch && contentMatch[1]) {
                // 解码可能的转义字符
                const content = contentMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
                if (content.trim()) {
                  console.log('通过正则提取到内容:', content)
                  processContentDirectly(content)
                }
              }
              else {
                console.warn('无法从SSE数据中提取有效内容，跳过此数据块')
              }
            }
            catch (extractError) {
              console.warn('内容提取失败:', extractError)
            }
          }
        }
        else {
          // 处理不带data:前缀的行
          console.log('处理非data:行:', trimmedLine)

          try {
            const parsedData = JSON.parse(trimmedLine)
            console.log('成功解析非data:行:', parsedData)

            // 🔧 优先检查是否包含表格数据
            if (parsedData.table_data) {
              console.log('🔍 [表格数据检测] 在非data行中发现table_data字段')
              console.log('🔍 [表格数据] table_data内容:', parsedData.table_data)
              handleTableData(parsedData.table_data)
              continue // 处理完表格数据后跳过content提取
            }

            // 🔧 检查是否包含图表数据
            if (parsedData.chart_data) {
              console.log('🔍 [图表数据检测] 在非data行中发现chart_data字段')
              console.log('🔍 [图表数据] chart_data内容:', parsedData.chart_data)
              handleChartData(parsedData.chart_data)
              continue // 处理完图表数据后跳过content提取
            }

            // 🔧 检查是否包含指标看板数据
            if (parsedData.dashboard_data) {
              console.log('🔍 [指标看板数据检测] 在非data行中发现dashboard_data字段')
              console.log('🔍 [指标看板数据] dashboard_data内容:', parsedData.dashboard_data)
              handleDashboardData(parsedData.dashboard_data)
              continue // 处理完指标看板数据后跳过content提取
            }

            // 🔧 检查是否包含溯源数据
            if (parsedData.provenance) {
              console.log('🔍 [溯源数据检测] 在非data行中发现provenance字段')
              console.log('🔍 [溯源数据] provenance内容:', parsedData.provenance)
              handleProvenanceData(parsedData.provenance)
              continue // 处理完溯源数据后跳过content提取
            }

            // 从choices数组中提取content
            if (parsedData.choices && parsedData.choices[0] && parsedData.choices[0].delta && parsedData.choices[0].delta.content) {
              const deltaContent = parsedData.choices[0].delta.content
              console.log('提取到内容:', deltaContent)
              // 直接处理提取的content，避免递归调用
              processContentDirectly(deltaContent)
              continue // 处理完毕，继续下一行
            }
          }
          catch (jsonError) {
            console.warn('非data:行JSON解析失败:', jsonError)
            // 检查是否包含结构化数据，如果是则尝试提取content
            if (trimmedLine.includes('"content"') || trimmedLine.includes('"choices"')) {
              try {
                const contentMatch = trimmedLine.match(/"content"\s*:\s*"([^"]*)"/)
                if (contentMatch && contentMatch[1]) {
                  const content = contentMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\')
                  if (content.trim()) {
                    console.log('通过正则从非data行提取到内容:', content)
                    processContentDirectly(content)
                  }
                }
                else {
                  console.warn('无法从非data行中提取有效内容，跳过此数据块')
                }
              }
              catch (extractError) {
                console.warn('非data行内容提取失败:', extractError)
              }
            }
            else {
              // 如果不包含结构化数据标识，且内容不为空，作为普通文本处理
              if (trimmedLine.trim()) {
                console.log('将非结构化行作为普通文本处理:', trimmedLine)
                processContentDirectly(trimmedLine)
              }
            }
          }
        }
      }
      return
    }

    // 如果chunk.result存在，使用chunk.result（来自useHookFetch的包装）
    if (chunk.result) {
      processedChunk = chunk.result

      // 如果result也是字符串格式的SSE数据，需要递归处理
      if (typeof processedChunk === 'string') {
        console.log('检测到result字段包含字符串格式的SSE数据，递归处理...')
        handleDataChunk(processedChunk)
        return
      }
    }

    // 处理reasoning_content（思考链）- 修复：支持不含<think>标签的增量更新
    const reasoningChunk = processedChunk.choices?.[0].delta.reasoning_content
    if (reasoningChunk) {
      console.log('检测到reasoning_content:', reasoningChunk)
      const decodedReasoning = decodeUnicodeContent(reasoningChunk)
      if (decodedReasoning.includes('<think>') || decodedReasoning.includes('</think>')) {
        // 标准带标签的思考内容交给统一处理
        processContentDirectly(decodedReasoning)
      }
      else {
        // 无<think>标签的思考增量，直接追加到思考容器
        if (bubbleItems.value.length) {
          const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
          if (!lastBubble.reasoning_content) {
            lastBubble.reasoning_content = ''
            lastBubble.thinking_start = Date.now() // 记录开始时间
          }
          if (lastBubble.thinkCollapse === undefined)
            lastBubble.thinkCollapse = false // 思考开始时应该展开
          appendIfNew(lastBubble, 'reasoning_content', decodedReasoning)
          if (reasoningChunk.includes('</think>')) {
            if (lastBubble.thinking_start !== undefined) {
              lastBubble.thinking_time = Math.round((Date.now() - lastBubble.thinking_start) / 1000)
            }
          }
          lastBubble.thinkingStatus = 'thinking'
          lastBubble.loading = true
        }
      }
      return
    }

    // 检查是否包含表格数据
    const tableData = processedChunk.table_data || processedChunk.data?.table_data
    if (tableData) {
      console.log('检测到表格数据:', tableData)
      handleTableData(tableData)
      return
    }

    // 检查是否包含溯源数据
    const provenanceData = processedChunk.provenance || processedChunk.data?.provenance
    if (provenanceData) {
      console.log('检测到溯源数据:', provenanceData)
      handleProvenanceData(provenanceData)
      return
    }

    // 提取content内容
    const extractedContent = processedChunk.choices?.[0].delta.content || processedChunk.content || processedChunk.answer || processedChunk.data?.answer || ''

    if (extractedContent) {
      console.log('从结构化数据中提取到content:', extractedContent)
      processContentDirectly(extractedContent)
    }
    else {
      // 如果没有找到标准的content字段，尝试其他可能的内容字段
      const fallbackContent = processedChunk.message || processedChunk.text || processedChunk.response
      if (fallbackContent) {
        console.log('使用fallback内容:', fallbackContent)
        processContentDirectly(fallbackContent)
      }
      else {
        console.warn('无法从数据块中提取有效内容:', processedChunk)
      }
    }
  }
  catch (err) {
    // 这里如果使用了中断，会有报错，可以忽略不管
    console.error('解析数据时出错:', err)
  }
}

// 处理表格数据的函数
function handleTableData(tableData: any) {
  console.log('🔍 [表格数据] 开始处理表格数据:', tableData)
  console.log('🔍 [表格数据] 表格数据类型:', typeof tableData)
  console.log('🔍 [表格数据] 当前bubbleItems长度:', bubbleItems.value.length)

  try {
    // 处理图表类型映射 (ranking -> rank)
    let recommendedChartType = tableData.recommendedChartType || tableData.recommended_chart_type
    if (recommendedChartType === 'ranking') {
      recommendedChartType = 'rank'
    }

    // 确保表格数据格式正确，兼容py_nl2sql后端格式
    const formattedTableData: TableData = {
      title: tableData.title || '查询结果',
      columns: tableData.columns || [],
      rows: tableData.rows || [],
      totalRows: tableData.totalRows || tableData.total || tableData.rows?.length || 0,
      query: tableData.query || tableData.sql_query || '',
      dataSource: tableData.dataSource || tableData.data_source || '',
      queryTime: tableData.queryTime || tableData.query_time || Date.now(),
      originalQuery: currentUserQuery, // 设置用户原始查询
      recommendedChartType, // 支持后端推荐的图表类型
    }

    console.log('🔍 [表格数据] 设置originalQuery字段:', currentUserQuery)

    console.log('🔍 [表格数据] 格式化后的表格数据:', formattedTableData)
    console.log('🔍 [表格数据] 列数:', formattedTableData.columns.length)
    console.log('🔍 [表格数据] 行数:', formattedTableData.rows.length)

    // 验证表格数据的有效性
    if (!formattedTableData.columns.length) {
      console.warn('⚠️ [表格数据] 表格数据无效：缺少列定义')
      ElMessage.warning('表格数据格式错误：缺少列定义')
      return
    }

    if (!formattedTableData.rows.length) {
      console.warn('⚠️ [表格数据] 表格数据无效：没有数据行')
      // 即使没有数据行，也显示表格结构
      ElMessage.info('查询完成，但没有找到匹配的数据')
    }

    // 获取最后一个AI消息气泡
    if (bubbleItems.value.length > 0) {
      const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
      if (lastBubble.role === 'ai') {
        // 设置表格数据和消息类型
        lastBubble.tableData = formattedTableData
        lastBubble.messageType = 'table'
        lastBubble.loading = false
        lastBubble.typing = false
        // 确保originalQuery字段也被设置到消息对象中
        lastBubble.originalQuery = currentUserQuery

        console.log('✅ [表格数据] 表格数据已设置到最后一个AI消息气泡')
      }
      else {
        // 如果最后一个不是AI消息，创建新的AI消息气泡
        addMessage('', false, false, 'table', undefined, formattedTableData, currentUserQuery)
        console.log('✅ [表格数据] 创建新的AI消息气泡显示表格数据')
      }
    }
    else {
      // 如果没有消息气泡，创建新的AI消息气泡
      addMessage('', false, false, 'table', undefined, formattedTableData, currentUserQuery)
      console.log('✅ [表格数据] 创建第一个AI消息气泡显示表格数据')
    }

    // 停止响应计时器
    stopResponseTimer()

    // 滚动到底部
    nextTick(() => {
      bubbleListRef.value?.scrollToBottom()
    })

    // 自动生成表格数据的溯源信息
    if (formattedTableData.query) {
      console.log('🔍 [表格数据] 检测到SQL查询，自动生成溯源数据')
      const tableProvenanceData = {
        dataType: 'table',
        queryTime: formattedTableData.queryTime,
        sourceTable: formattedTableData.dataSource || '未知数据源',
        tableSqlQuery: formattedTableData.query,
      }

      // 延迟一下再添加溯源数据，确保表格数据先显示
      setTimeout(() => {
        handleProvenanceData(tableProvenanceData)
      }, 100)
    }

    // 显示成功消息
    ElMessage.success(`查询完成，共找到 ${formattedTableData.rows.length} 条数据`)
  }
  catch (error) {
    console.error('❌ [表格数据] 处理表格数据时出错:', error)
    ElMessage.error(`表格数据处理失败：${(error as Error).message}`)
  }
}

// 处理图表数据的函数
function handleChartData(chartData: any) {
  console.log('🔍 [图表数据] 开始处理图表数据:', chartData)
  console.log('🔍 [图表数据] 图表数据类型:', typeof chartData)
  console.log('🔍 [图表数据] 当前bubbleItems长度:', bubbleItems.value.length)

  try {
    // 确保图表数据格式正确
    const formattedChartData: ChartContent = {
      title: chartData.title || '图表',
      chartType: chartData.chartType || chartData.chart_type || 'line',
      data: chartData.data || chartData.chart_data || {},
      query: chartData.query || chartData.sql_query || '',
      dataSource: chartData.dataSource || chartData.data_source || '',
      queryTime: chartData.queryTime || chartData.query_time || Date.now(),
    }

    console.log('🔍 [图表数据] 格式化后的图表数据:', formattedChartData)

    // 验证图表数据的有效性
    if (!formattedChartData.data || Object.keys(formattedChartData.data).length === 0) {
      console.warn('⚠️ [图表数据] 图表数据无效：缺少图表配置数据')
      ElMessage.warning('图表数据格式错误：缺少图表配置数据')
      return
    }

    // 获取最后一个AI消息气泡
    if (bubbleItems.value.length > 0) {
      const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
      if (lastBubble.role === 'ai') {
        // 设置图表数据和消息类型
        lastBubble.chartContent = formattedChartData
        lastBubble.messageType = 'chart'
        lastBubble.loading = false
        lastBubble.typing = false

        console.log('✅ [图表数据] 图表数据已设置到最后一个AI消息气泡')
      }
      else {
        // 如果最后一个不是AI消息，创建新的AI消息气泡
        addMessage('', false, false, 'chart', formattedChartData)
        console.log('✅ [图表数据] 创建新的AI消息气泡显示图表数据')
      }
    }
    else {
      // 如果没有消息气泡，创建新的AI消息气泡
      addMessage('', false, false, 'chart', formattedChartData)
      console.log('✅ [图表数据] 创建第一个AI消息气泡显示图表数据')
    }

    // 自动生成图表数据的溯源信息
    if (formattedChartData.query) {
      console.log('🔍 [图表数据] 检测到SQL查询，自动生成溯源数据')
      const chartProvenanceData = {
        dataType: 'chart',
        queryTime: formattedChartData.queryTime,
        sourceTable: formattedChartData.dataSource || '未知数据源',
        chartSqlQuery: formattedChartData.query,
      }

      // 延迟一下再添加溯源数据，确保图表数据先显示
      setTimeout(() => {
        handleProvenanceData(chartProvenanceData)
      }, 100)
    }

    // 停止响应计时器
    stopResponseTimer()

    // 滚动到底部
    nextTick(() => {
      bubbleListRef.value?.scrollToBottom()
    })

    // 显示成功消息
    ElMessage.success('图表生成完成')
  }
  catch (error) {
    console.error('❌ [图表数据] 处理图表数据时出错:', error)
    ElMessage.error(`图表数据处理失败：${(error as Error).message}`)
  }
}

// 处理指标看板数据的函数
function handleDashboardData(dashboardData: any) {
  console.log('🔍 [指标看板数据] 开始处理指标看板数据:', dashboardData)
  console.log('🔍 [指标看板数据] 指标看板数据类型:', typeof dashboardData)
  console.log('🔍 [指标看板数据] 当前bubbleItems长度:', bubbleItems.value.length)

  try {
    // 指标看板数据可以作为特殊的表格数据处理
    const formattedDashboardData: TableData = {
      title: dashboardData.title || '指标看板',
      columns: dashboardData.columns || [],
      rows: dashboardData.rows || [],
      totalRows: dashboardData.totalRows || dashboardData.total || dashboardData.rows?.length || 0,
      query: dashboardData.query || dashboardData.sql_query || '',
      dataSource: dashboardData.dataSource || dashboardData.data_source || '',
      queryTime: dashboardData.queryTime || dashboardData.query_time || Date.now(),
    }

    console.log('🔍 [指标看板数据] 格式化后的指标看板数据:', formattedDashboardData)

    // 验证指标看板数据的有效性
    if (!formattedDashboardData.columns.length) {
      console.warn('⚠️ [指标看板数据] 指标看板数据无效：缺少列定义')
      ElMessage.warning('指标看板数据格式错误：缺少列定义')
      return
    }

    // 获取最后一个AI消息气泡
    if (bubbleItems.value.length > 0) {
      const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
      if (lastBubble.role === 'ai') {
        // 设置指标看板数据和消息类型
        lastBubble.tableData = formattedDashboardData
        lastBubble.messageType = 'table'
        lastBubble.loading = false
        lastBubble.typing = false

        console.log('✅ [指标看板数据] 指标看板数据已设置到最后一个AI消息气泡')
      }
      else {
        // 如果最后一个不是AI消息，创建新的AI消息气泡
        addMessage('', false, false, 'table', undefined, formattedDashboardData)
        console.log('✅ [指标看板数据] 创建新的AI消息气泡显示指标看板数据')
      }
    }
    else {
      // 如果没有消息气泡，创建新的AI消息气泡
      addMessage('', false, false, 'table', undefined, formattedDashboardData)
      console.log('✅ [指标看板数据] 创建第一个AI消息气泡显示指标看板数据')
    }

    // 自动生成指标看板数据的溯源信息
    if (formattedDashboardData.query) {
      console.log('🔍 [指标看板数据] 检测到SQL查询，自动生成溯源数据')
      const dashboardProvenanceData = {
        dataType: 'dashboard',
        queryTime: formattedDashboardData.queryTime,
        sourceTable: formattedDashboardData.dataSource || '未知数据源',
        dashboardSqlQuery: formattedDashboardData.query,
      }

      // 延迟一下再添加溯源数据，确保指标看板数据先显示
      setTimeout(() => {
        handleProvenanceData(dashboardProvenanceData)
      }, 100)
    }

    // 停止响应计时器
    stopResponseTimer()

    // 滚动到底部
    nextTick(() => {
      bubbleListRef.value?.scrollToBottom()
    })

    // 显示成功消息
    ElMessage.success(`指标看板生成完成，共 ${formattedDashboardData.rows.length} 个指标`)
  }
  catch (error) {
    console.error('❌ [指标看板数据] 处理指标看板数据时出错:', error)
    ElMessage.error(`指标看板数据处理失败：${(error as Error).message}`)
  }
}

// 处理溯源数据的函数
function handleProvenanceData(provenanceData: any) {
  console.log('🔍 [溯源数据] 开始处理溯源数据:', provenanceData)
  console.log('🔍 [溯源数据] 溯源数据类型:', typeof provenanceData)
  console.log('🔍 [溯源数据] 当前bubbleItems长度:', bubbleItems.value.length)

  try {
    // 验证溯源数据的有效性
    if (!provenanceData || typeof provenanceData !== 'object') {
      console.warn('⚠️ [溯源数据] 溯源数据无效:', provenanceData)
      return
    }

    // 格式化溯源数据为Markdown格式
    const provenanceMarkdown = formatProvenanceToMarkdown(provenanceData)
    console.log('🔍 [溯源数据] 格式化后的Markdown:', provenanceMarkdown)

    // 获取最后一个AI消息气泡
    if (bubbleItems.value.length > 0) {
      const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
      if (lastBubble.role === 'ai') {
        // 设置溯源数据到最后一个AI消息
        lastBubble.provenanceMarkdown = provenanceMarkdown
        lastBubble.provenanceExtracted = provenanceData

        console.log('✅ [溯源数据] 溯源数据已设置到最后一个AI消息气泡')
      }
      else {
        console.warn('⚠️ [溯源数据] 最后一个消息不是AI消息，无法设置溯源数据')
      }

      // 滚动到底部
      nextTick(() => {
        if (bubbleListRef.value) {
          bubbleListRef.value.scrollToBottom()
        }
      })
    }
    else {
      console.warn('⚠️ [溯源数据] 没有找到可用的消息气泡来显示溯源数据')
    }
  }
  catch (error) {
    console.error('❌ [溯源数据] 处理溯源数据时发生错误:', error)
    ElMessage.error('处理溯源数据时发生错误')
  }
}

// 将溯源数据格式化为纯文本的函数
function formatProvenanceToMarkdown(provenanceData: any): string {
  try {
    const {
      queryTimeISO,
      queryTime,
      sourceTable,
      sourceTables,
      sqlQuery,
      // 支持来自不同数据类型的SQL查询
      tableSqlQuery,
      chartSqlQuery,
      dashboardSqlQuery,
      dataType, // 数据类型：table, chart, dashboard
    } = provenanceData

    let content = '📊 数据溯源信息\n\n'

    // 数据类型信息
    if (dataType) {
      const typeMap: Record<string, string> = {
        table: '📋 表格数据',
        chart: '📈 图表数据',
        dashboard: '📊 指标看板',
      }
      content += `数据类型： ${typeMap[dataType] || dataType}\n\n`
    }

    // 查询时间信息 - 简化显示
    if (queryTimeISO || queryTime) {
      if (queryTime) {
        const date = new Date(queryTime)
        content += `查询时间： ${date.toLocaleString()}\n\n`
      }
      else if (queryTimeISO) {
        content += `查询时间： ${queryTimeISO}\n\n`
      }
    }

    // 数据源信息 - 简化显示
    if (sourceTable || (sourceTables && sourceTables.length > 0)) {
      if (sourceTable) {
        content += `数据来源： ${sourceTable}\n\n`
      }
      else if (sourceTables && sourceTables.length > 0) {
        content += `数据来源： ${sourceTables.join(', ')}\n\n`
      }
    }

    // SQL查询语句 - 支持多种来源的SQL查询
    const finalSqlQuery = sqlQuery || tableSqlQuery || chartSqlQuery || dashboardSqlQuery
    if (finalSqlQuery) {
      content += `SQL查询：\n${finalSqlQuery}\n\n`
    }

    return content
  }
  catch (error) {
    console.error('❌ [溯源数据] 格式化文本时发生错误:', error)
    return '📊 数据溯源信息\n\n数据格式化失败，请查看控制台获取详细信息。'
  }
}

// 封装错误处理逻辑
function handleError(err: any) {
  console.error('=== 处理错误 ===')
  console.error('错误对象:', err)
  console.error('错误消息:', err?.message || '未知错误')
  console.error('错误状态码:', err?.status || '无状态码')
  console.error('错误响应:', err?.response || '无响应数据')

  // 显示用户友好的错误消息
  ElMessage.error({
    message: `发送消息失败: ${err?.message || '网络连接错误'}`,
    duration: 5000,
  })
}

// 处理用户直接输入的消息发送
function handleUserSubmit(chatContent: string) {
  console.log('=== 用户提交消息 ===')
  console.log('消息内容:', chatContent)
  console.log('使用aipost发送到8000端口')
  startSSE(chatContent, true) // 用户直接输入时需要清空输入框
}

// 测试溯源数据功能
function testProvenanceData() {
  console.log('🧪 [测试] 开始测试溯源数据功能')

  // 模拟添加一个AI消息
  const testMessage = '这是一个测试消息，用于验证溯源数据显示功能。'
  addMessage(testMessage, false, false, 'text')

  // 模拟溯源数据
  const mockProvenanceData = {
    queryTimeISO: new Date().toISOString(),
    queryTime: Date.now(),
    sourceTable: 'test_table',
    sourceTables: ['test_table', 'related_table_1', 'related_table_2'],
    sqlQuery: 'SELECT * FROM test_table WHERE condition = \'test\' ORDER BY created_at DESC LIMIT 10;',
  }

  console.log('🧪 [测试] 模拟溯源数据:', mockProvenanceData)

  // 延迟一下再添加溯源数据，模拟真实场景
  setTimeout(() => {
    handleProvenanceData(mockProvenanceData)
    ElMessage.success('溯源数据测试完成！请查看聊天界面中的溯源信息板块。')
  }, 500)
}

// 确保会话ID存在的函数
function ensureSessionId(): string {
  const currentSessionId = route.params?.id

  // 如果当前会话ID是'error'，显示错误信息并返回一个临时ID
  if (currentSessionId === 'error') {
    console.error('会话创建失败，显示错误信息')
    // 显示用户友好的错误消息
    ElMessage.error({
      message: '会话创建失败，请稍后重试或联系管理员',
      duration: 5000,
    })
    // 添加一条系统消息说明错误
    if (bubbleItems.value.length === 0) {
      addMessage('抱歉，会话创建失败。可能是由于网络问题或服务器暂时不可用。请稍后重试或联系管理员。', false)
    }
    // 返回一个临时ID，但不进行API调用
    return 'error'
  }

  // 如果当前会话ID不存在或为'not_login'，生成新的会话ID
  if (!currentSessionId || currentSessionId === 'not_login') {
    // 生成包含日期时间的会话ID格式：session_YYYYMMDD_HHMMSS_随机字符
    const now = new Date()
    const dateStr = now.getFullYear().toString()
      + (now.getMonth() + 1).toString().padStart(2, '0')
      + now.getDate().toString().padStart(2, '0')
    const timeStr = now.getHours().toString().padStart(2, '0')
      + now.getMinutes().toString().padStart(2, '0')
      + now.getSeconds().toString().padStart(2, '0')
    const randomStr = Math.random().toString(36).substr(2, 6)
    const newSessionId = `session_${dateStr}_${timeStr}_${randomStr}`

    // 更新路由到新的会话ID
    router.replace({
      name: 'chatWithId',
      params: { id: newSessionId },
    })

    console.log('生成新会话ID:', newSessionId)
    return newSessionId
  }

  return String(currentSessionId)
}

async function startSSE(chatContent: string, shouldClearInput: boolean = false) {
  try {
    console.log('=== 开始SSE连接 ===')
    console.log('消息内容:', chatContent)
    console.log('是否清空输入:', shouldClearInput)

    // 保存当前用户查询，用于表格数据的originalQuery字段
    currentUserQuery = chatContent
    console.log('🔍 [用户查询] 保存当前用户查询:', currentUserQuery)

    // 重置思考状态和流式响应状态 - 修复流式响应显示问题
    streamCompleted = false

    // 检查用户登录状态
    console.log('=== 用户登录状态检查 ===')
    console.log('用户登录状态:', userStore.isLogin)
    console.log('用户Token:', userStore.token ? '存在' : '不存在')
    console.log('用户信息:', userStore.userInfo ? '存在' : '不存在')

    if (!userStore.isLogin) {
      console.error('用户未登录，无法发送消息')
      ElMessage.error('请先登录后再使用AI功能')
      userStore.openLoginDialog()
      return
    }

    // 添加用户输入的消息
    // console.log('chatContent', chatContent);
    // 只有在用户直接输入时才清空输入框
    if (shouldClearInput) {
      inputValue.value = ''
    }
    addMessage(chatContent, true, false)
    addMessage('', false, true, 'text') // 为AI消息启用typing状态
    console.log('当前bubbleItems数量:', bubbleItems.value.length)
    console.log('最后一条消息:', bubbleItems.value[bubbleItems.value.length - 1])

    // 重置并启动响应计时器
    resetResponseTimer()
    startResponseTimer()

    // 这里有必要调用一下 BubbleList 组件的滚动到底部 手动触发 自动滚动
    bubbleListRef.value?.scrollToBottom()

    // 确保会话ID存在
    const sessionId = ensureSessionId()

    // 如果会话ID是'error'，不发送API请求
    if (sessionId === 'error') {
      console.log('会话ID为error，不发送API请求')
      return
    }

    // 直接使用aipost发送到8000端口后端
    console.log('=== 使用aipost发送消息到8000端口 ===')

    const openaiParams = {
      messages: bubbleItems.value
        .filter((item: any) => item.role === 'user')
        .slice(-5) // 限制最近5条用户消息
        .map((item: any) => ({
          role: item.role,
          content: item.content,
        })),
      sessionId, // 使用确保存在的会话ID
      userId: userStore.userInfo?.user_id,
      model: modelStore.currentModelInfo.modelName ?? '',
      stream: enableStreamResponse.value, // 根据用户选择启用或禁用流式响应
    }

    console.log('OpenAI API请求参数:', JSON.stringify(openaiParams, null, 2))
    console.log('流式响应模式:', enableStreamResponse.value ? '启用' : '禁用')

    if (enableStreamResponse.value) {
      // 流式响应模式：逐字显示
      console.log('开始调用stream...')
      console.log('🔍 [网络请求] 流式请求URL:', '/chat/completions')
      console.log('🔍 [网络请求] 流式请求参数:', openaiParams)

      try {
        for await (const chunk of stream('/chat/completions', openaiParams)) {
          console.log('🔍 [网络响应] 收到OpenAI数据块:', chunk)
          handleDataChunk(chunk as AnyObject)
        }
        console.log('🔍 [网络响应] OpenAI流式响应完成')
        streamCompleted = true
        // 确保在流式响应结束后立即完成响应
        finishResponse()
      }
      catch (streamError) {
        console.error('🔍 [网络错误] 流式请求失败:', streamError)
        handleError(streamError)
      }
    }
    else {
      // 固定输出模式：等待完整响应
      console.log('开始调用固定响应模式...')
      try {
        const apiResponse = await aiRequest.post('/chat/completions', openaiParams)
        console.log('收到完整响应:', apiResponse)

        // 从ApiResponse中提取data字段，这才是真正的OpenAI响应
        const response: OpenAIResponse = (apiResponse as any).data
        console.log('提取的OpenAI响应数据:', response)

        // 处理完整响应
        if (response && response.choices && response.choices[0] && response.choices[0].message) {
          const fullContent = response.choices[0].message.content
          console.log('提取完整内容:', fullContent)

          // 直接设置完整内容，不使用打字机效果
          if (bubbleItems.value.length) {
            bubbleItems.value[bubbleItems.value.length - 1].content = fullContent
            bubbleItems.value[bubbleItems.value.length - 1].typing = false
            bubbleItems.value[bubbleItems.value.length - 1].loading = false

            // 处理图片路径
            let processedContent = fullContent
            processedContent = processHtmlImages(processedContent)
            processedContent = processMarkdownImages(processedContent)
            bubbleItems.value[bubbleItems.value.length - 1].content = processedContent

            // 格式化SQL语句
            const content = bubbleItems.value[bubbleItems.value.length - 1].content
            if (content) {
              bubbleItems.value[bubbleItems.value.length - 1].content = formatSqlInMessage(content)
            }

            // 处理溯源数据（非流式模式）
            if (response.provenance) {
              console.log('🔍 [溯源数据] 在非流式响应中发现provenance字段:', response.provenance)
              handleProvenanceData(response.provenance)
            }
          }
        }
        else {
          console.warn('响应格式不正确:', response)
          throw new Error('响应格式不正确')
        }
      }
      catch (error) {
        console.error('固定响应模式请求失败:', error)
        throw error
      }
      streamCompleted = true
    }
  }
  catch (err) {
    console.error('=== SSE连接发生错误 ===')
    console.error('错误详情:', err)
    console.error('错误类型:', typeof err)
    console.error('错误堆栈:', err instanceof Error ? err.stack : '无堆栈信息')
    handleError(err)
  }
  finally {
    console.log('=== SSE连接结束 ===')
    console.log('数据接收完毕')
    console.log('流式响应完成状态:', streamCompleted)
    // 只有在流式响应真正完成时才停止打字器和加载状态
    if (streamCompleted) {
      finishResponse() // 调用统一的完成响应函数
    }
  }
}

// 中断请求
async function cancelSSE() {
  cancel()
  streamCompleted = true // 设置流式响应完成标志
  // 结束最后一条消息打字状态
  finishResponse() // 错误时也要关闭typing状态
}

// 专用于从localStorage恢复消息的SSE函数 - 跳过添加用户消息步骤
async function startSSEWithoutUserMessage(chatContent: string) {
  try {
    console.log('=== 开始SSE连接（跳过用户消息添加）===')
    console.log('消息内容:', chatContent)

    // 重置思考状态和流式响应状态 - 修复流式响应显示问题
    streamCompleted = false

    // 检查用户登录状态
    console.log('=== 用户登录状态检查 ===')
    console.log('用户登录状态:', userStore.isLogin)
    console.log('用户Token:', userStore.token ? '存在' : '不存在')
    console.log('用户信息:', userStore.userInfo ? '存在' : '不存在')

    if (!userStore.isLogin) {
      console.error('用户未登录，无法发送消息')
      ElMessage.error('请先登录后再使用AI功能')
      userStore.openLoginDialog()
      return
    }

    // 跳过添加用户消息步骤，因为消息已经在调用前添加了
    // 只添加AI消息的typing状态
    addMessage('', false, true, 'text') // 为AI消息启用typing状态
    console.log('当前bubbleItems数量:', bubbleItems.value.length)
    console.log('最后一条消息:', bubbleItems.value[bubbleItems.value.length - 1])

    // 重置并启动响应计时器
    resetResponseTimer()
    startResponseTimer()

    // 这里有必要调用一下 BubbleList 组件的滚动到底部 手动触发 自动滚动
    bubbleListRef.value?.scrollToBottom()

    // 确保会话ID存在
    const sessionId = ensureSessionId()

    // 如果会话ID是'error'，不发送API请求
    if (sessionId === 'error') {
      console.log('会话ID为error，不发送API请求')
      return
    }

    // 直接使用aipost发送到8000端口后端
    console.log('=== 使用aipost发送消息到8000端口 ===')

    const openaiParams = {
      messages: bubbleItems.value
        .filter((item: any) => item.role === 'user')
        .slice(-5) // 限制最近5条用户消息
        .map((item: any) => ({
          role: item.role,
          content: item.content,
        })),
      sessionId, // 使用确保存在的会话ID
      userId: userStore.userInfo?.user_id,
      model: modelStore.currentModelInfo.modelName ?? '',
      stream: enableStreamResponse.value, // 根据用户选择启用或禁用流式响应
    }

    console.log('OpenAI API请求参数:', JSON.stringify(openaiParams, null, 2))
    console.log('流式响应模式:', enableStreamResponse.value ? '启用' : '禁用')

    if (enableStreamResponse.value) {
      // 流式响应模式：逐字显示
      console.log('开始调用stream...')
      for await (const chunk of stream('/chat/completions', openaiParams)) {
        console.log('收到OpenAI数据块:', chunk)
        handleDataChunk(chunk as AnyObject)
      }
      console.log('OpenAI流式响应完成')
      streamCompleted = true
      // 确保在流式响应结束后立即完成响应
      finishResponse()
    }
    else {
      // 固定输出模式：等待完整响应
      console.log('开始调用固定响应模式...')
      try {
        const apiResponse = await aiRequest.post('/chat/completions', openaiParams)
        console.log('收到完整响应:', apiResponse)

        // 从ApiResponse中提取data字段，这才是真正的OpenAI响应
        const response: OpenAIResponse = (apiResponse as any).data
        console.log('提取的OpenAI响应数据:', response)

        // 处理完整响应
        if (response && response.choices && response.choices[0] && response.choices[0].message) {
          const fullContent = response.choices[0].message.content
          console.log('提取完整内容:', fullContent)

          // 直接设置完整内容，不使用打字机效果
          if (bubbleItems.value.length) {
            bubbleItems.value[bubbleItems.value.length - 1].content = fullContent
            bubbleItems.value[bubbleItems.value.length - 1].typing = false
            bubbleItems.value[bubbleItems.value.length - 1].loading = false

            // 处理图片路径
            let processedContent = fullContent
            processedContent = processHtmlImages(processedContent)
            processedContent = processMarkdownImages(processedContent)
            bubbleItems.value[bubbleItems.value.length - 1].content = processedContent

            // 格式化SQL语句
            const content = bubbleItems.value[bubbleItems.value.length - 1].content
            if (content) {
              bubbleItems.value[bubbleItems.value.length - 1].content = formatSqlInMessage(content)
            }

            // 处理溯源数据（非流式模式）
            if (response.provenance) {
              console.log('🔍 [溯源数据] 在非流式响应中发现provenance字段:', response.provenance)
              handleProvenanceData(response.provenance)
            }
          }
        }
        else {
          console.warn('响应格式不正确:', response)
          throw new Error('响应格式不正确')
        }
      }
      catch (error) {
        console.error('固定响应模式请求失败:', error)
        throw error
      }
      streamCompleted = true
    }
  }
  catch (err) {
    console.error('=== SSE连接发生错误 ===')
    console.error('错误详情:', err)
    console.error('错误类型:', typeof err)
    console.error('错误堆栈:', err instanceof Error ? err.stack : '无堆栈信息')
    handleError(err)
  }
  finally {
    console.log('=== SSE连接结束 ===')
    console.log('数据接收完毕')
    console.log('流式响应完成状态:', streamCompleted)
    // 只有在流式响应真正完成时才停止打字器和加载状态
    if (streamCompleted) {
      finishResponse() // 调用统一的完成响应函数
    }
  }
}

// 简化的SQL格式化函数 - 暂时禁用复杂的SQL识别
function formatSqlInMessage(message: string): string {
  // 添加调试信息
  console.log('🔧 [AI消息格式调试] SQL格式化前:', message)

  // 暂时直接返回原消息，不进行复杂的SQL识别和格式化
  // 这样可以避免格式处理导致的问题
  console.log('⚠️ [AI消息格式调试] SQL格式化已简化，直接返回原消息')

  return message
}

// 完成响应 - 关闭typing状态
function finishResponse() {
  if (bubbleItems.value.length) {
    const lastMessage = bubbleItems.value[bubbleItems.value.length - 1]
    lastMessage.typing = false
    lastMessage.loading = false
    // 保存当前响应时间到消息对象
    lastMessage.responseTime = finalResponseTime.value
    console.log('响应完成，关闭typing状态，响应时间:', `${finalResponseTime.value}s`)
  }
  // 停止计时器
  stopResponseTimer()
}

function getLastLine(content: string): string {
  if (!content)
    return ''
  const lines = content.split('\n')
  return lines[lines.length - 1].trim()
}

function toggleThinkingContent(message: MessageItem) {
  message.thinkCollapse = !message.thinkCollapse
}

// 新增：强制折叠思考过程的方法
function forceCollapseThinking() {
  if (bubbleItems.value.length > 0) {
    const lastMessage = bubbleItems.value[bubbleItems.value.length - 1]
    if (lastMessage.reasoning_content && lastMessage.thinkingStatus === 'end') {
      lastMessage.thinkCollapse = true
      console.log('🧠 强制折叠思考过程')
      // 强制触发响应式更新
      bubbleItems.value = [...bubbleItems.value]
    }
  }
}

// 处理Markdown渲染开关切换 (在模板中使用)
// @ts-ignore
function handleMarkdownToggle(value: string | number | boolean) {
  const boolValue = Boolean(value)
  console.log('🔄 [Markdown开关] 切换状态:', boolValue ? '启用' : '禁用')

  // 更新所有现有AI消息的isMarkdown属性
  bubbleItems.value.forEach((item, index) => {
    if (item.role === 'ai') {
      const oldValue = item.isMarkdown
      item.isMarkdown = boolValue
      console.log(`🔄 [Markdown开关] 更新消息${index}: ${oldValue} -> ${boolValue}`)
    }
  })

  // 强制重新渲染
  nextTick(() => {
    console.log('🔄 [Markdown开关] 强制重新渲染完成')
  })
}

// 添加消息 - 维护聊天记录
function addMessage(message: string, isUser: boolean, enableTyping: boolean = false, messageType?: 'text' | 'chart' | 'table', chartContent?: any, tableData?: TableData, originalQuery?: string) {
  console.log('=== 添加消息 ===')
  console.log('消息内容:', message)
  console.log('是否用户消息:', isUser)
  console.log('是否启用打字状态:', enableTyping)

  // 🔍 添加详细调试信息
  console.log('🔍 [调试] addMessage被调用')
  console.log('🔍 [调试] messageType:', messageType)
  console.log('🔍 [调试] chartContent:', chartContent)
  console.log('🔍 [调试] tableData:', tableData)
  console.log('🔍 [调试] 添加前bubbleItems长度:', bubbleItems.value.length)

  // 定义系统消息标识
  const isSystemMessage = false // 当前版本不支持系统消息

  const i = bubbleItems.value.length

  // 处理消息内容中的图片路径
  let processedMessage = message || ''

  // 添加详细的消息处理调试信息
  console.log('📝 [AI消息格式调试] 开始处理消息内容')
  console.log('📝 [AI消息格式调试] 原始消息:', processedMessage)
  console.log('📝 [AI消息格式调试] 是否用户消息:', isUser)
  console.log('📝 [AI消息格式调试] 是否系统消息:', isSystemMessage)

  if (processedMessage && !isUser && !isSystemMessage) {
    console.log('🖼️ [AI消息格式调试] 开始处理图片路径')
    // 对AI回复的消息进行图片路径处理
    // 先尝试作为HTML处理，再作为Markdown处理
    const beforeImageProcessing = processedMessage
    processedMessage = processHtmlImages(processedMessage)
    processedMessage = processMarkdownImages(processedMessage)
    console.log('🖼️ [AI消息格式调试] 图片处理前:', beforeImageProcessing)
    console.log('🖼️ [AI消息格式调试] 图片处理后:', processedMessage)
  }

  // 处理SQL语句识别和代码块格式化
  if (processedMessage && !isUser && !isSystemMessage) {
    console.log('🔧 [AI消息格式调试] 开始SQL格式化处理')
    const beforeSqlProcessing = processedMessage
    processedMessage = formatSqlInMessage(processedMessage)
    console.log('🔧 [AI消息格式调试] SQL处理前:', beforeSqlProcessing)
    console.log('🔧 [AI消息格式调试] SQL处理后:', processedMessage)
  }

  console.log('✅ [AI消息格式调试] 最终处理结果:', processedMessage)

  const obj: MessageItem = {
    key: i,
    // 根据用户要求：AI消息不设置avatar属性，从源头避免头像显示
    avatar: isUser ? avatar.value : '',
    avatarSize: isUser ? '32px' : '0px',
    role: isUser ? 'user' : (isSystemMessage ? 'system' : 'ai'),
    placement: isUser ? 'end' : 'start',
    isMarkdown: !isUser && !isSystemMessage && enableMarkdownRender.value, // 根据开关控制AI消息的Markdown渲染
    loading: false, // 修复双重加载动画：AI消息不设置loading状态
    typing: enableTyping && !isUser && !isSystemMessage, // 只有AI消息且明确启用时才显示typing
    content: processedMessage,
    // 思考状态相关属性的完整初始化
    reasoning_content: '',
    thinkingStatus: isUser || isSystemMessage ? 'end' : 'start', // 用户和系统消息不需要思考状态
    thinkCollapse: true, // 默认折叠
    thinking_time: 0, // 思考用时
    // 确保响应式更新的完整性
    responseTime: 0,
    // 添加消息类型和相关数据
    messageType,
    chartContent,
    tableData,
    originalQuery, // 保存用户原始查询
  }

  console.log('🔍 [DEBUG] addMessage: 创建消息对象:', {
    role: obj.role,
    reasoning_content: obj.reasoning_content,
    thinkingStatus: obj.thinkingStatus,
    thinkCollapse: obj.thinkCollapse,
    isUser,
    isSystemMessage,
    loading: obj.loading,
    typing: obj.typing,
  })

  // 🎯 专门调试用户消息位置配置
  if (isUser) {
    console.log('👤 [用户消息位置调试]:', {
      role: obj.role,
      placement: obj.placement,
      avatar: obj.avatar,
      avatarSize: obj.avatarSize,
      content: obj.content ? `${obj.content.substring(0, 50)}...` : '',
      key: obj.key,
    })
  }

  // 添加思考框显示条件的调试日志
  if (obj.role === 'ai') {
    const shouldShowThinking = (obj.reasoning_content && obj.reasoning_content.length > 0) || obj.loading || obj.typing
    console.log('🤔 [DEBUG] 思考框显示条件:', {
      hasReasoningContent: !!(obj.reasoning_content && obj.reasoning_content.length > 0),
      isLoading: obj.loading,
      isTyping: obj.typing,
      shouldShow: shouldShowThinking,
    })
  }

  bubbleItems.value.push(obj)

  console.log('消息已添加，当前消息总数:', bubbleItems.value.length)
  console.log('最新消息:', obj)

  // 🖼️ 使用优化的图片渲染器处理图片，解决布局抖动问题
  processMessageImages()
}

// handleChange函数已移除，因为思考内容现在直接内嵌在对话框中

// 为消息中的图片添加点击放大功能
function addImageClickHandlers() {
  nextTick(() => {
    // 添加调试日志
    console.log('开始添加图片点击处理器')

    // 查找所有的消息容器，使用更广泛的选择器
    const bubbleContainers = document.querySelectorAll('.el-bubble, .bubble-content, .markdown-body, [class*="bubble"]')
    console.log('找到的容器数量:', bubbleContainers.length)

    bubbleContainers.forEach((container, index) => {
      console.log(`处理容器 ${index}:`, container.className)
      const images = container.querySelectorAll('img')
      console.log(`容器 ${index} 中的图片数量:`, images.length)
      addImageClickToEnlarge(container as HTMLElement)
    })

    // 直接查找所有图片作为备用方案
    const allImages = document.querySelectorAll('img')
    console.log('页面中所有图片数量:', allImages.length)
    allImages.forEach((img, index) => {
      console.log(`图片 ${index}:`, img.src, img.parentElement?.className)
      // 直接为每个图片添加点击事件
      if (!img.dataset.clickEnlargeAdded) {
        addImageClickToEnlarge(img.parentElement as HTMLElement || document.body)
      }
    })
  })
}

// 添加全局图片点击监听器作为备用方案
function setupGlobalImageClickListener() {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    if (target.tagName === 'IMG') {
      console.log('全局监听器: 检测到图片点击', (target as HTMLImageElement).src)
      // 检查是否在聊天消息中
      const chatContainer = target.closest('.el-bubble, .bubble-content, .markdown-body')
      if (chatContainer) {
        console.log('全局监听器: 图片在聊天消息中，显示预览')
        e.preventDefault()
        e.stopPropagation()
        // 动态导入并调用预览功能
        import('@/utils/imageUtils').then(({ ImagePreviewManager }) => {
          ImagePreviewManager.showImagePreview((target as HTMLImageElement).src)
        })
      }
    }
  })
}

function handleDeleteCard(_item: FilesCardProps, index: number) {
  filesStore.deleteFileByIndex(index)
}

// 移除了Dify连接测试功能，现在只使用aipost

// 页面可见性检测
let visibilityChangeHandler: (() => void) | null = null

// 测试思考框显示的函数
function testThinkingBox() {
  console.log('🧪 [TEST] 开始测试思考框显示功能')

  // 创建一个测试AI消息
  const testMessage: MessageItem = {
    key: 999,
    avatar: '', // AI消息不显示头像
    avatarSize: '0px',
    role: 'ai',
    placement: 'start',
    isMarkdown: true,
    loading: true,
    typing: true,
    content: '这是一个测试消息',
    reasoning_content: '这是测试的思考内容，用于验证思考框是否能正常显示。',
    thinkingStatus: 'start',
    thinkCollapse: true,
    responseTime: 0,
  }

  console.log('🧪 [TEST] 创建的测试消息:', testMessage)

  // 检查显示条件
  const shouldShow = testMessage.role === 'ai' && ((testMessage.reasoning_content && testMessage.reasoning_content.length > 0) || testMessage.loading || testMessage.typing)
  console.log('🧪 [TEST] 思考框应该显示:', shouldShow)
  console.log('🧪 [TEST] 显示条件详情:', {
    isAI: testMessage.role === 'ai',
    hasReasoningContent: !!(testMessage.reasoning_content && testMessage.reasoning_content.length > 0),
    isLoading: testMessage.loading,
    isTyping: testMessage.typing,
  })

  // 添加到消息列表
  bubbleItems.value.push(testMessage)
  console.log('🧪 [TEST] 测试消息已添加到列表，当前消息数:', bubbleItems.value.length)
}

// 测试图表消息功能
function testChartMessage() {
  console.log('🧪 [TEST] 开始测试图表消息功能')

  const chartMessage: MessageItem = {
    key: Date.now(),
    role: 'ai',
    avatar: '', // AI消息不显示头像
    content: '这是一个销售数据图表：',
    messageType: 'chart',
    chartContent: {
      title: '月度销售数据',
      chartType: 'line',
      data: {
        xAxis: {
          type: 'category',
          data: ['1月', '2月', '3月', '4月', '5月', '6月'],
        },
        yAxis: {
          type: 'value',
        },
        series: [{
          name: '销售额',
          data: [120, 200, 150, 80, 70, 110],
          type: 'line',
          smooth: true,
          itemStyle: {
            color: '#4f46e5',
          },
        }],
      },
    },
  }

  bubbleItems.value.push(chartMessage)
  console.log('🧪 [TEST] 图表消息已添加到列表，当前消息数:', bubbleItems.value.length)

  // 滚动到底部
  nextTick(() => {
    if (bubbleListRef.value) {
      bubbleListRef.value.scrollToBottom()
    }
  })
}

// 测试表格消息功能
function testTableMessage() {
  console.log('🧪 [TEST] 开始测试表格消息功能')

  const tableMessage: MessageItem = {
    key: Date.now(),
    role: 'ai',
    avatar: '', // AI消息不显示头像
    content: '这是一个查询结果表格：',
    messageType: 'table',
    tableData: {
      title: '员工信息查询结果',
      columns: ['姓名', '部门', '职位', '薪资', '入职日期'],
      rows: [
        ['张三', '技术部', '前端工程师', '15000', '2023-01-15'],
        ['李四', '产品部', '产品经理', '18000', '2022-08-20'],
        ['王五', '设计部', 'UI设计师', '12000', '2023-03-10'],
        ['赵六', '技术部', '后端工程师', '16000', '2022-12-05'],
        ['钱七', '运营部', '运营专员', '10000', '2023-05-22'],
      ],
      totalRows: 5,
      query: 'SELECT name, department, position, salary, hire_date FROM employees',
      dataSource: '员工管理系统',
      queryTime: Date.now(), // 使用时间戳（毫秒）
    },
  }

  bubbleItems.value.push(tableMessage)
  console.log('🧪 [TEST] 表格消息已添加到列表，当前消息数:', bubbleItems.value.length)

  // 滚动到底部
  nextTick(() => {
    if (bubbleListRef.value) {
      bubbleListRef.value.scrollToBottom()
    }
  })
}

// 组件挂载时设置全局图片点击监听器
onMounted(() => {
  // 🔍 添加页面加载调试信息
  console.log('🔍 [页面加载] ChatWithId组件成功挂载')
  console.log('🔍 [页面加载] 用户登录状态:', userStore.isLogin)
  console.log('🔍 [页面加载] bubbleItems初始长度:', bubbleItems.value.length)
  console.log('🔍 [页面加载] 当前时间:', new Date().toLocaleString())
  console.log('🔍 [页面加载] 当前路由参数:', route.params)

  // 🖼️ 初始化图片渲染器，解决图片加载导致的布局抖动问题
  initImageRenderer()

  setupGlobalImageClickListener()
  console.log('全局图片点击监听器已设置')

  // 将toggleThinkingContent函数绑定到全局window对象，以便HTML中的onclick事件能够调用
  ;(window as any).toggleThinkingContent = toggleThinkingContent

  // 绑定测试函数到全局对象，方便在控制台调用
  ;(window as any).testThinkingBox = testThinkingBox
  ;(window as any).testChartMessage = testChartMessage
  ;(window as any).testTableMessage = testTableMessage

  // 🔍 添加调试函数：检查bubbleItems中的表格数据
  ;(window as any).debugBubbleItems = () => {
    console.log('🔍 [DEBUG] 当前bubbleItems总数:', bubbleItems.value.length)
    bubbleItems.value.forEach((item, index) => {
      console.log(`🔍 [DEBUG] 消息 ${index}:`, {
        role: item.role,
        messageType: item.messageType,
        hasTableData: !!item.tableData,
        tableData: item.tableData,
        content: `${item.content?.substring(0, 50)}...`,
      })
    })

    // 检查表格类型的消息
    const tableMessages = bubbleItems.value.filter(item => item.messageType === 'table')
    console.log('🔍 [DEBUG] 表格类型消息数量:', tableMessages.length)
    tableMessages.forEach((item, index) => {
      console.log(`🔍 [DEBUG] 表格消息 ${index}:`, item)
    })

    return {
      totalMessages: bubbleItems.value.length,
      tableMessagesCount: tableMessages.length,
      bubbleItems: bubbleItems.value,
      tableMessages,
    }
  }

  // 🔍 添加调试函数：检查TableBubble组件渲染条件
  ;(window as any).debugTableRenderCondition = () => {
    bubbleItems.value.forEach((item, index) => {
      const isAI = item.role === 'ai'
      const isTable = item.messageType === 'table'
      const hasTableData = !!item.tableData
      const shouldRender = isAI && isTable && hasTableData

      console.log(`🔍 [DEBUG] 消息 ${index} 渲染条件:`, {
        isAI,
        isTable,
        hasTableData,
        shouldRender,
        messageType: item.messageType,
        role: item.role,
      })
    })
  }

  console.log('🧪 [TEST] 测试函数已绑定到 window.testThinkingBox、window.testChartMessage 和 window.testTableMessage，可在控制台调用')
  console.log('🔍 [DEBUG] 调试函数已绑定到 window.debugBubbleItems 和 window.debugTableRenderCondition，可在控制台调用')

  // 添加设置data-role属性的函数
  const setDataRoleAttributes = () => {
    nextTick(() => {
      const bubbleElements = document.querySelectorAll('.el-bubble')
      bubbleElements.forEach((element, index) => {
        const bubbleItem = bubbleItems.value[index]
        if (bubbleItem && bubbleItem.role) {
          element.setAttribute('data-role', bubbleItem.role)
          console.log(`🎯 [DATA-ROLE] 设置第${index}个气泡的data-role为: ${bubbleItem.role}`)
        }
      })
    })
  }

  // 初始设置data-role属性
  setDataRoleAttributes()

  // 监听bubbleItems变化，重新设置data-role属性
  watch(bubbleItems, () => {
    setDataRoleAttributes()
  }, { deep: true })

  // 添加页面可见性检测
  visibilityChangeHandler = () => {
    if (!document.hidden) {
      // 页面变为可见时，重新渲染最后一条消息
      nextTick(() => {
        if (bubbleItems.value.length > 0) {
          const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
          if (lastBubble && lastBubble.role !== 'user') {
            // 强制重新渲染
            lastBubble.content = formatSqlInMessage(lastBubble.content || '')
            addImageClickHandlers()
          }
        }
        // 滚动到底部
        if (bubbleListRef.value) {
          bubbleListRef.value.scrollToBottom()
        }
      })
    }
  }

  document.addEventListener('visibilitychange', visibilityChangeHandler)
})

// 组件卸载时清理事件监听器
onUnmounted(() => {
  if (visibilityChangeHandler) {
    document.removeEventListener('visibilitychange', visibilityChangeHandler)
    visibilityChangeHandler = null
  }

  // 清理全局函数绑定
  if ((window as any).toggleThinkingContent) {
    delete (window as any).toggleThinkingContent
  }
})

// keep-alive 激活时重新渲染
onActivated(() => {
  nextTick(() => {
    if (bubbleItems.value.length > 0) {
      const lastBubble = bubbleItems.value[bubbleItems.value.length - 1]
      if (lastBubble && lastBubble.role !== 'user') {
        // 强制重新渲染最后一条消息
        lastBubble.content = formatSqlInMessage(lastBubble.content || '')
        addImageClickHandlers()
      }
    }
    // 滚动到底部
    if (bubbleListRef.value) {
      bubbleListRef.value.scrollToBottom()
    }
  })
})

// keep-alive 失活时清理定时器
onDeactivated(() => {
  // 清理所有打字机定时器 - 暂时禁用
  /*
  bubbleItems.value.forEach((item) => {
    if (item.typewriterTimer) {
      clearInterval(item.typewriterTimer);
      item.typewriterTimer = null;
    }
  });
  */
})

watch(
  () => filesStore.filesList.length,
  (val) => {
    if (val > 0) {
      nextTick(() => {
        senderRef.value?.openHeader()
      })
    }
    else {
      nextTick(() => {
        senderRef.value?.closeHeader()
      })
    }
  },
)
</script>

<template>
  <div class="chat-with-id-container chat-message-width">
    <div class="chat-warp">
      <!-- Markdown渲染开关 -->
      <!-- <div class="markdown-switch-container">
        <el-switch
          v-model="enableMarkdownRender"
          class="markdown-switch"
          active-text="Markdown渲染"
          inactive-text="原始文本"
          @change="handleMarkdownToggle"
        />
      </div> -->

      <BubbleList ref="bubbleListRef" :list="bubbleItems" max-height="calc(100vh - 180px)" :btn-loading="false">
        <template #content="{ item }">
          <div v-if="item.role === 'ai'">
            <div class="markdown-body" v-html="renderMessageMarkdown(item.content || '')" />
          </div>
          <div v-else class="bubble-content-text" :class="{ 'is-user': item.role === 'user' }">
            {{ item.content }}
          </div>
        </template>
        <template #header="{ item }">
          <div
            v-if="showThinkingArea && item && item.role === 'ai' && ((item.reasoning_content && item.reasoning_content.length > 0) || item.typing)"
            class="thinking-container thinking-inside-content visible-thinking"
            :data-thinking-id="`thinking-${item.key}`"
          >
            <div class="thinking-header" :data-active-thinking="item.typing || item.thinkingStatus !== 'end'" @click="toggleThinkingContent(item)">
              <!-- <div class="thinking-icon">🤔</div> -->
              <div class="thinking-title">
                思考过程 <span v-if="item.thinking_time" class="thinking-time">({{ item.thinking_time }}s)</span>
              </div>
              <div class="thinking-toggle" :data-expanded="!item.thinkCollapse">
                {{ !item.thinkCollapse ? 'v' : '>' }}
              </div>
            </div>
            <div class="thinking-content" :data-expanded="!item.thinkCollapse">
              <div v-if="!item.thinkCollapse" class="thinking-text">
                {{ item.reasoning_content }}
              </div>
              <div v-else class="thinking-last-line">
                {{ (item.thinkingStatus === 'end') ? '思考完成' : getLastLine(item.reasoning_content) }}
              </div>
            </div>
            <!-- 移除thinking-summary，实现完全折叠，只需后续在header添加用时显示 -->
          </div>
        </template>

        <!-- 修复：移除content插槽，让BubbleList使用默认内容渲染，避免重复头像显示 -->
        <!-- 如果需要自定义内容，应该使用footer插槽而不是content插槽 -->
        <!-- 完全移除指标看板相关代码 -->
        <!-- 将加载动画移入气泡内部：当Bubble处于loading状态时显示 -->
        <template #loading="{ item }">
          <!-- 将加载动画移入气泡内部：当Bubble处于loading状态时显示 -->
          <div v-if="item && item.loading" class="typing-indicator">
            <div class="typing-text">
              正在查询中
            </div>
            <div class="typing-dots">
              <span class="dot" />
              <span class="dot" />
              <span class="dot" />
            </div>
            <div class="breathing-light" />
          </div>
        </template>

        <template #footer="{ item }">
          <!-- 表格组件：当消息类型为table时显示 -->
          <!-- 表格气泡组件：仅当消息角色为AI、消息类型为表格且存在表格数据时渲染 -->
          <TableBubble
            v-if="item && item.role === 'ai' && item.messageType === 'table' && item.tableData"
            :table-data="item.tableData"
            :provenance-markdown="item.provenanceMarkdown"
          />

          <!-- 数据溯源信息：非表格消息时在气泡下方显示 -->
          <!-- 仅当 AI 消息存在溯源内容且当前消息不是表格类型时才渲染，避免与 TableBubble 内部溯源重复 -->
          <!-- 🚫 暂时隐藏独立数据溯源面板 -->
          <div v-if="false" class="provenance-board">
            <!-- 溯源头部：小圆点 + 标题 -->
            <div class="provenance-header">
              <span class="provenance-dot" />
              <span class="provenance-title">数据溯源信息</span>
            </div>
            <!-- 溯源主体：将 Markdown 格式的溯源内容渲染成 HTML 后展示 -->
            <div class="provenance-body">
              <div class="provenance-content" v-html="renderMarkdown(item.provenanceMarkdown)" />
            </div>
          </div>
        </template>
      </BubbleList>

      <Sender
        ref="senderRef" v-model="inputValue" class="chat-defaul-sender" :auto-size="{
          maxRows: 6,
          minRows: 2,
        }" variant="updown" clearable allow-speech :loading="isLoading" @submit="handleUserSubmit" @cancel="cancelSSE"
      >
        <!-- 添加停止按钮插槽，保持与其他模块一致 -->
        <template #send-button>
          <div class="send-button-group">
            <!-- 测试溯源数据按钮 -->
            <el-button
              v-if="!isLoading"
              type="warning"
              size="small"
              @click="testProvenanceData"
            >
              测试溯源
            </el-button>

            <el-button
              v-if="!isLoading"
              type="primary"
              @click="() => handleUserSubmit(inputValue)"
            >
              发送
            </el-button>
            <el-button
              v-else
              type="info"
              @click="cancelSSE"
            >
              停止
            </el-button>
          </div>
        </template>
        <template #header>
          <div class="sender-header p-12px pt-6px pb-0px">
            <Attachments :items="filesStore.filesList" :hide-upload="true" @delete-card="handleDeleteCard">
              <template #prev-button="{ show, onScrollLeft }">
                <div
                  v-if="show && onScrollLeft"
                  class="prev-next-btn left-8px flex-center w-22px h-22px rounded-8px border-1px border-solid border-[rgba(0,0,0,0.08)] c-[rgba(0,0,0,.4)] hover:bg-#f3f4f6 bg-#fff font-size-10px"
                  @click="onScrollLeft"
                >
                  <el-icon>
                    <ArrowLeftBold />
                  </el-icon>
                </div>
              </template>

              <template #next-button="{ show, onScrollRight }">
                <div
                  v-if="show && onScrollRight"
                  class="prev-next-btn right-8px flex-center w-22px h-22px rounded-8px border-1px border-solid border-[rgba(0,0,0,0.08)] c-[rgba(0,0,0,.4)] hover:bg-#f3f4f6 bg-#fff font-size-10px"
                  @click="onScrollRight"
                >
                  <el-icon>
                    <ArrowRightBold />
                  </el-icon>
                </div>
              </template>
            </Attachments>
          </div>
        </template>
        <!-- <template #prefix>
          <div class="flex-1 flex items-center gap-8px flex-none w-fit overflow-hidden">
            <FilesSelect />
            <ModelSelect />
          </div>
        </template> -->
      </Sender>
    </div>
  </div>
</template>

<style lang="scss">
@import '@/styles/chat-bubble.scss';
</style>

<style scoped lang="scss">
/* 流光闪烁动画关键帧 */
@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}
.chat-with-id-container {
  /* 页面级字体变量，与知识问答页面保持一致 */
  --chat-message-font-size: var(--font-size-xs);
  --chat-bubble-font-size: var(--font-size-xs);
  --chat-markdown-font-size: var(--font-size-xs);

  // 定位相关
  position: relative;  // 影响子元素定位参考系
  box-sizing: border-box;  // 影响盒模型计算方式

  // 布局相关
  display: flex;  // 影响直接子元素排列方式
  flex-direction: column;  // 影响子元素垂直排列
  align-items: center;  // 影响子元素水平居中

  // 尺寸相关
  width: 80%;  // 影响容器宽度，与chatDefault保持一致
  height: 100%;  // 影响容器高度
  padding: 0 20px;  // 添加左右内边距，与chatDefault保持一致

  // 间距相关  // 影响容器水平居中
  .visible-thinking {
    position: relative;
    box-sizing: border-box;
    display: block !important;
    align-self: stretch;

    /* 固定宽度：占满可用行宽，避免随文字长短波动 */
    width: 100%;
    min-width: 100%;
    max-width: 100%;
    padding: 20px;
    margin: 20px 0;
    overflow: hidden;
    background: transparent;
    border: none;
    border-radius: 16px;
    box-shadow: none;
    isolation: isolate;
    transform: translateZ(0);

    /* 移除动态光效 - 注释掉动画相关属性 */

    /* &::before {
      position: absolute;
      top: 0;
      right: 0;
      left: 0;
      height: 4px;
      content: '';
      background: linear-gradient(
        90deg,
        transparent 0%,
        rgb(14 165 233 / 30%) 20%,
        rgb(6 182 212 / 80%) 40%,
        rgb(59 130 246 / 100%) 50%,
        rgb(6 182 212 / 80%) 60%,
        rgb(14 165 233 / 30%) 80%,
        transparent 100%
      );
      background-size: 300% 100%;
      border-radius: 2px;
      box-shadow:
        0 0 8px rgb(59 130 246 / 40%),
        0 0 16px rgb(59 130 246 / 20%);
      animation: shimmer 6s ease-in-out infinite;
    } */

    /* 移除整体发光效果 - 注释掉动画相关属性 */

    /* &::after {
      position: absolute;
      inset: -2px;
      z-index: -1;
      content: '';
      background: linear-gradient(
        135deg,
        rgb(59 130 246 / 10%) 0%,
        rgb(6 182 212 / 5%) 50%,
        rgb(14 165 233 / 10%) 100%
      );
      border-radius: 18px;
      opacity: 0;
      animation: glow-pulse 3s ease-in-out infinite;
    } */
  }
  .thinking-header {
    display: flex;
    align-items: center;

    /* 头部强制占满整行，避免随内容伸缩 */
    width: 100%;
    padding: 8px 12px;
    font-weight: 600;
    color: #0369a1;
    cursor: pointer;
    border-radius: 8px;
    transition: background-color 0.2s ease;
    &:hover {
      background: rgb(14 165 233 / 8%);
    }
    .thinking-icon {
      margin-right: 8px;
      font-size: var(--font-size-sm);

      /* 移除脉冲动画 */

      /* animation: pulse 2s infinite; */
    }
    .thinking-title {
      flex: 0 0 auto;
      font-size: var(--font-size-sm);
      font-weight: 600;
      color: #475569;
      background: none;
      -webkit-text-fill-color: initial;
      animation: none;
    }
    .thinking-toggle {
      flex-shrink: 0; /* 防止被压缩 */
      width: 20px; /* 固定宽度防止位置跳动 */
      font-size: var(--font-size-xs);
      color: #666666; /* 改为普通灰色 */
      text-align: center; /* 居中对齐 */

      /* 移除旋转动画，保持简洁 */
    }

    /* 思考进行中：为标题与箭头添加闪烁光效，仅在进行中激活 */
    &[data-active-thinking="true"] {
      .thinking-title {
        background: linear-gradient(
          90deg,
          #475569 0%,
          #475569 40%,
          #e2f1f8 50%,
          #475569 60%,
          #475569 100%
        );
        background-clip: text;
        background-size: 200% 100%;
        animation: shimmer 5s infinite linear;
        -webkit-text-fill-color: transparent;
      }
      .thinking-toggle {
        background: linear-gradient(
          90deg,
          #475569 0%,
          #475569 40%,
          #e2f1f8 50%,
          #475569 60%,
          #475569 100%
        );
        background-clip: text;
        background-size: 200% 100%;
        animation: shimmer 5s infinite linear;
        -webkit-text-fill-color: transparent;
      }
    }
  }
  .thinking-content {
    /* 内容区域同样占满整行 */
    width: 100%;
    margin-top: 12px;
    overflow: hidden;
    color: #0c4a6e;
    background: transparent;
    border-left: none;
    border-radius: 8px;
    transition: all 0.3s ease;
    &[data-expanded="true"] {
      max-height: 500px;
      padding: 12px;
      opacity: 1;
    }
    &[data-expanded="false"] {
      max-height: 1.6em;
      padding: 8px 12px;
      opacity: 1;
    }
    .thinking-text {
      font-size: var(--font-size-sm);
      line-height: 1.6;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .thinking-last-line {
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: var(--font-size-sm);
      line-height: 1.6;
      white-space: nowrap;
    }
    .thinking-placeholder {
      display: flex;
      align-items: center;
      font-style: italic;
      color: #64748b;
      opacity: 0.8;
      &::before {
        margin-right: 8px;
        content: '💭';

        /* 移除弹跳动画 */

        /* animation: bounce 1.5s infinite; */
      }
    }
  }

  /* 移除thinking-summary样式 */

  // 间距相关
  margin: 0 auto;  // 影响容器水平居中
  .chat-warp {
    // 布局相关
    display: flex;  // 影响子元素排列
    flex-direction: column;  // 影响子元素垂直排列
    gap: 6px;  // 进一步缩小子元素间距，减少列表与输入框之间空白
    justify-content: space-between;  // 修复：改为space-between，确保BubbleList占据剩余空间，Sender固定在底部

    // 尺寸相关
    width: 100%;  // 影响容器宽度
    height: calc(100vh - 60px);  // 修复：优化高度计算，适配不同缩放比例
    min-height: 100%;  // 修复：确保容器占满可用空间
    min-height: calc(100vh - 60px);  // 修复：添加最小高度，确保正确适配
    max-height: calc(100vh - 60px);  // 修复：添加最大高度，防止溢出
    padding-bottom: 4px;  // 进一步缩小底部内边距，充分利用可视区域

    // 让消息列表在父容器中尽可能占满空间
    :deep(.el-bubble-list) {
      display: flex;  // 修复：设置flex布局
      flex: 1 1 auto;  // 修复：让BubbleList占据剩余空间
      flex-direction: column;  // 修复：垂直排列内部消息
      min-height: 0;  // 修复：允许内容收缩
      max-height: 100%;  // 修复：防止溢出
      margin-bottom: 0;
      overflow-y: auto;
    }
    .thinking-chain-warp {
      margin-bottom: 8px;  // 减少下方元素间距
    }
  }
  .chat-defaul-sender {
    flex-shrink: 0;  // 防止输入框被压缩
    width: 100%;  // 影响发送框宽度
    margin-bottom: 6px;  // 进一步减少底部间距，充分利用空间
  }

  // 修复：为Sender组件添加额外的防压缩保护
  > .chat-defaul-sender {
    flex-shrink: 0;  // 防止输入框被压缩
  }

  // 流式响应切换开关样式
  .stream-toggle-container {
    display: flex;
    align-items: center;
    margin-left: 8px;
    .stream-toggle-wrapper {
      display: flex;
      gap: 6px;
      align-items: center;
      padding: 4px 8px;
      background: rgb(255 255 255 / 80%);
      border: 1px solid rgb(0 0 0 / 8%);
      border-radius: 8px;
      transition: all 0.3s ease;
      &:hover {
        background: rgb(255 255 255 / 95%);
        border-color: rgb(0 0 0 / 12%);
        box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
      }
      .stream-icon {
        font-size: 14px;
        color: #666666;
        transition: all 0.3s ease;
        &.active {
          color: #13ce66;
        }
        &:not(.active) {
          color: #8957e5;
        }
      }
      :deep(.el-switch) {
        .el-switch__label {
          font-size: 11px;
          font-weight: 500;
        }
        .el-switch__core {
          width: 36px;
          height: 18px;
          .el-switch__action {
            width: 14px;
            height: 14px;
          }
        }
      }
    }
  }
}

  // 流式响应动态效果样式 - 确保AI消息加载动画左对齐
  .typing-indicator {
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: flex-start; // 确保左对齐
    width: 100%;
    padding: 8px 0;
    margin-right: auto; // 确保左对齐
    margin-left: 0; // 确保没有左边距
    .typing-text {
      margin-right: 4px;
      font-size: 12px;
      color: #999999;
    }
    .typing-dots {
      display: flex;
      gap: 4px;
      .dot {
        width: 6px;
        height: 6px;
        background-color: #666666;
        border-radius: 50%;
        animation: typing-bounce 1.4s infinite ease-in-out;
        &:nth-child(1) {
          animation-delay: -0.32s;
        }
        &:nth-child(2) {
          animation-delay: -0.16s;
        }
        &:nth-child(3) {
          animation-delay: 0s;
        }
      }
    }
    .breathing-light {
      width: 8px;
      height: 8px;
      background-color: #00d084;
      border-radius: 50%;
      box-shadow: 0 0 6px rgb(0 208 132 / 60%);
      animation: breathing 2s infinite ease-in-out;
    }
  }

  // 计时器样式
  .response-timer {
    display: flex;
    align-items: center;
    margin-top: 8px;
    .timer-container {
      display: flex;
      gap: 4px;
      align-items: center;
      padding: 4px 8px;
      font-size: 12px;
      color: #64748b;
      background: rgb(248 250 252);
      border: 1px solid rgb(226 232 240);
      border-radius: 12px;
      .timer-icon {
        font-size: 12px;
        color: #94a3b8;
      }
      .timer-text {
        min-width: 24px;
        font-weight: 500;
        text-align: center;
      }
    }
  }

  // Thinking组件样式覆盖 - 添加平滑过渡动画
  :deep(.el-thinking) {
    // 🔧 修复：思考组件的高度稳定性
    min-height: 40px; // 设置最小高度，避免折叠时完全消失导致的高度跳动
    transition: all 0.3s ease; // 缩短过渡时间，提升响应性

    // 思考内容容器的过渡动画
    .el-thinking__content {
      min-height: 0; // 确保有基础高度
      overflow: hidden;
      transform-origin: top;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); // 缩短过渡时间
    }

    // 折叠状态的样式
    &.is-collapsed {
      min-height: 32px; // 折叠状态下保持最小高度
      .el-thinking__content {
        max-height: 0;
        padding: 0;
        margin: 0;
        opacity: 0;
        transform: scaleY(0);
      }
    }

    // 展开状态的样式
    &:not(.is-collapsed) {
      .el-thinking__content {
        max-height: 1000px;
        opacity: 1;
        transform: scaleY(1);
      }
    }

    // 思考模式的视觉标识
    .el-thinking__header {
      display: flex;
      gap: 6px;
      align-items: center;
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 500;
      color: #475569;
      background: transparent;
      border: 1px solid #e2e8f0;
      border-radius: 8px 8px 0 0;
      transition: all 0.3s ease;
    }
  }

  // 嵌入式思考内容样式
  :deep(.thinking-container) {
    box-sizing: border-box;
    width: 100%;

    // 🔧 修复：嵌入式思考容器的高度稳定性
    min-height: 36px; // 设置最小高度
    margin: 4px 0;
    overflow: hidden;
    background: transparent;
    border: none;
    border-radius: 0;
    transition: all 0.2s ease; // 添加平滑过渡
    &.thinking-inside-content {
      display: block;
      width: 100%;
      min-height: 32px; // 内嵌模式下的最小高度
      margin: 0;
    }
    .thinking-header {
      display: flex;
      gap: 4px;
      align-items: center;
      padding: 4px 8px;
      color: #666666;
      cursor: pointer;
      user-select: none;
      background: transparent;
      border-bottom: none;
    }
    .thinking-title {
      flex: 0 0 auto;
      font-size: 12px;
      color: #475569;
    }
    .thinking-time {
      font-size: 12px;
      color: #999999;
    }
    .thinking-toggle {
      flex: 0 0 20px; /* 固定宽度并不随布局变化 */
      flex-shrink: 0; /* 防止被压缩 */
      width: 20px; /* 与桌面端保持一致的固定宽度 */
      margin-left: 6px; /* 紧挨在标题右侧 */
      font-size: 12px;
      color: #666666; /* 统一使用灰色 */
      text-align: center;
    }
    .thinking-content {
      max-height: none;
      padding: 8px;
      overflow: visible;
      font-size: 12px;
      line-height: 1.5;
      color: #666666;
      background: transparent;
    }
    .thinking-text,
    .thinking-last-line {
      word-wrap: break-word;
      white-space: pre-wrap;
    }

    // 折叠按钮样式
    .el-thinking__toggle {
        padding: 4px 8px;
        margin-left: auto;
        color: white;
        cursor: pointer;
        background: rgb(255 255 255 / 20%);
        border: none;
        border-radius: 4px;
        transition: all 0.3s ease;
        &:hover {
          background: rgb(255 255 255 / 30%);
          transform: scale(1.05);
        }
      }

    // 思考内容区域样式
    .el-thinking__body {
      position: relative;
      padding: 12px;
      background: transparent;
      border: none;
      border-radius: 0 0 8px 8px;
    }

    // 思考文本样式
    .el-thinking__text {
      font-size: 12px;
      line-height: 1.5;
      color: #475569;
      word-break: break-word;
      white-space: pre-wrap;
    }

  }

  // 输入框大小设置 - 与其他三个模块保持一致
  .chat-defaul-sender {
    width: 100%; /* 统一设置为100%，与chatDefault页面保持一致 */
    padding: 0 16px;
    margin-top: -8px; /* 添加负上边距，使输入框更靠上 */
    margin-bottom: 80px; /* 增加底部边距，确保输入框与页面底部有足够间距 */
  }

  // 移除自定义输入框样式，使用全局elx.scss中的统一样式
  // 全局样式已在elx.scss中定义，无需在此重复定义

  // 移除嵌入式指标看板样式代码

// 移动端特定样式
@media (width <= 767px) {
  .chat-with-id-container {
    padding: 12px;
    margin: 0;
    .chat-defaul-sender {
      padding: 0 12px;
      margin-bottom: 36px; /* 移动端增加更多底部边距 */
    }

    // 移动端也使用全局elx.scss中的统一样式，无需自定义

    // 移动端流式响应切换开关样式
    .stream-toggle-container {
      .stream-toggle-wrapper {
        padding: 6px 10px;
        .stream-icon {
          font-size: 14px;
        }
        :deep(.el-switch) {
          .el-switch__core {
            width: 40px;
            height: 20px;
            .el-switch__action {
              width: 16px;
              height: 16px;
            }
          }
        }
      }
    }

    // 移动端指标看板样式已移除
  }
}

// 所有@keyframes定义放在最后，符合Sass新规范
@keyframes shimmer {
  0% {
    background-position: -300% 0;
    opacity: 0.8;
  }
  50% {
    opacity: 1;
  }
  100% {
    background-position: 300% 0;
    opacity: 0.8;
  }
}

@keyframes glow-pulse {
  0%, 100% {
    opacity: 0;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.02);
  }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

@keyframes bounce {
  0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-3px); }
  60% { transform: translateY(-2px); }
}

@keyframes typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-10px);
  }
}

@keyframes breathing {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.02);
  }
}

/* 移除独立的KPI看板样式，现在使用TableBubble内部的指标看板样式 */

/* 数据溯源样式（与指标看板保持视觉一致性） */
.provenance-board {
  box-sizing: border-box;
  width: 100%;
  padding: 12px 14px;
  margin-top: 8px;
  background: #fefbf3;
  border: 1px solid #f3e8d0;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 4%);
}
.provenance-header { box-sizing: border-box; display: flex; gap: 8px; align-items: center; width: 100%; margin-bottom: 8px; }
.provenance-body { box-sizing: border-box; width: 100%; }
.provenance-dot { width: 8px; height: 8px; background: #f59e0b; border-radius: 50%; box-shadow: 0 0 8px rgb(245 158 11 / 50%); }
.provenance-title { font-size: 13px; font-weight: 600; color: #111827; }
.provenance-content {
  font-size: 12px;
  line-height: 1.5;
  color: #374151;
}
.provenance-content h3 {
  margin: 8px 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}
.provenance-content p {
  margin: 4px 0;
}
.provenance-content ul, .provenance-content ol {
  padding-left: 16px;
  margin: 4px 0;
}
.provenance-content li {
  margin: 2px 0;
}

@media (width <= 767px) {
  .provenance-board {
    padding: 10px 12px;
  }
  .provenance-content {
    font-size: 11px;
  }
}

/* 发送按钮组样式 */
.send-button-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 测试按钮样式优化 */
.send-button-group .el-button--warning {
  padding: 6px 12px;
  font-size: 12px;
}

/* 移动端适配 */
@media (width <= 768px) {
  .send-button-group {
    gap: 6px;
  }
  .send-button-group .el-button--warning {
    padding: 5px 10px;
    font-size: 11px;
  }

  // 移动端聊天容器优化
  .chat-with-id-container {
    padding: 8px;  // 减少移动端内边距
    .chat-warp {
      gap: 4px;  // 进一步减少间距
      height: calc(100vh - 100px);  // 移动端调整高度计算
      padding-bottom: 2px;  // 减少底部内边距
      :deep(.el-bubble-list) {
        // 移动端列表优化
        padding: 0 4px;
      }
      .chat-defaul-sender {
        margin-bottom: 4px;  // 移动端减少底部间距
      }
    }
  }
}

/* 小屏幕设备适配 */
@media (width <= 480px) {
  .chat-with-id-container {
    padding: 4px;  // 小屏幕进一步减少内边距
    .chat-warp {
      gap: 2px;  // 最小间距
      height: calc(100vh - 120px);  // 小屏幕调整高度
      .chat-defaul-sender {
        margin-bottom: 2px;  // 小屏幕最小底部间距
      }
    }
  }
}
</style>
