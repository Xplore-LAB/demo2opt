<!-- Aside 侧边栏 -->
<script setup lang="ts">
import { ElMessage } from 'element-plus'
// import type { ConversationItem } from 'vue-element-plus-x/types/Conversations'; // 暂时注释未使用的类型导入
// import type { ChatSessionVo } from '@/api/session/types'; // 暂时注释未使用的类型导入
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get_session } from '@/api'
import logo from '@/assets/images/logo.png'
import SkeletonLoader from '@/components/SkeletonLoader/index.vue'
// import SvgIcon from '@/components/SvgIcon/index.vue'; // 暂时注释未使用的导入
import Collapse from '@/layouts/components/Header/components/Collapse.vue'
import { useDesignStore, useUserStore } from '@/stores'
import { useSessionStore } from '@/stores/modules/session'

const route = useRoute()
const router = useRouter()
const designStore = useDesignStore()
const sessionStore = useSessionStore()

// 开发环境标识（暂时注释未使用的变量）
// const isDev = import.meta.env.DEV;

const sessionId = computed(() => route.params?.id)
const conversationsList = computed(() => sessionStore.sessionList)
// const loadMoreLoading = computed(() => sessionStore.isLoadingMore); // 暂时注释未使用的变量
const active = ref<string | undefined>()

// 加载与就绪状态
const isLoading = ref(true)
const componentReady = ref(false)
const isInitialized = ref(false)

function ensureCSSVariablesLoaded() {
  const root = document.documentElement
  const width = getComputedStyle(root).getPropertyValue('--sidebar-default-width').trim()
  return width && width !== '' && width !== '0px'
}

onMounted(async () => {
  if (!ensureCSSVariablesLoaded()) {
    await nextTick()
  }
  componentReady.value = true
  // 获取会话列表
  await sessionStore.requestSessionList()
  // 高亮最新会话
  if (conversationsList.value.length > 0 && sessionId.value && typeof sessionId.value === 'string' && sessionId.value !== 'not_login') {
    try {
      const currentSessionRes = await get_session(sessionId.value)
      // 通过 ID 查询详情，设置当前会话 (因为有分页)
      sessionStore.setCurrentSession(currentSessionRes.data)
    }
    catch (error) {
      console.error('获取会话详情失败:', error)
    }
  }
  isLoading.value = false
  isInitialized.value = true
})

watch(
  () => sessionStore.currentSession,
  (newValue) => {
    active.value = newValue ? `${newValue.id}` : undefined
  },
)

// 创建会话
function handleCreatChat() {
  // 创建会话, 跳转到默认聊天
  sessionStore.createSessionBtn()
}

// 菜单展开状态
// 存储当前展开的菜单项的路由名称数组,用于控制子菜单的展开/收起状态
const expandedMenus = ref<string[]>(['knowledgeQA', 'mathTraining', 'modelService']) // 初始展开所有菜单

// 当前选中的菜单项
const currentRoute = computed(() => {
  return route.name
})

async function handleMenuClick(routeName: string) {
  // 避免重复导航到同一路由
  if (route.name === routeName) {
    return
  }

  // 特殊处理登录路由
  if (routeName === 'login') {
    const userStore = useUserStore()
    userStore.openLoginDialog()
    return
  }

  // 处理子菜单展开/收起
  if (routeName === 'mathTraining' || routeName === 'modelService' || routeName === 'knowledgeQA') {
    if (expandedMenus.value.includes(routeName)) {
      expandedMenus.value = expandedMenus.value.filter(menu => menu !== routeName)
    }
    else {
      expandedMenus.value.push(routeName)
    }
    // 对于带有子菜单的菜单项，点击时只处理展开/收起，不进行路由跳转
    return
  }

  try {
    await router.push({ name: routeName })
  }
  catch (error) {
    console.error('路由跳转失败:', error)
    console.error('路由名称:', routeName)
    ElMessage.error(`页面跳转失败: ${error}`)
  }
}

// 子菜单项点击处理
function handleSubmenuClick(routeName: string, event: Event) {
  event.stopPropagation() // 阻止事件冒泡
  router.push({ name: routeName })
}

// 切换会话 - 暂时注释未使用的函数
// function handleChange(item: ConversationItem<ChatSessionVo>) {
//   sessionStore.setCurrentSession(item);
//   router.replace({
//     name: 'chatWithId',
//     params: {
//       id: item.id,
//     },
//   });
// }

// 处理组件触发的加载更多事件 - 暂时注释未使用的函数
// async function handleLoadMore() {
//   if (!sessionStore.hasMore)
//     return; // 无更多数据时不加载
//   await sessionStore.loadMoreSessions();
// }

// 右键菜单 - 暂时注释未使用的函数
// function handleMenuCommand(command: string, item: ConversationItem<ChatSessionVo>) {
//   switch (command) {
//     case 'delete':
//       ElMessageBox.confirm('删除后，聊天记录将不可恢复。', '确定删除对话？', {
//         confirmButtonText: '确定',
//         cancelButtonText: '取消',
//         type: 'warning',
//         confirmButtonClass: 'el-button--danger',
//         cancelButtonClass: 'el-button--info',
//         roundButton: true,
//         autofocus: false,
//       })
//         .then(() => {
//           // 删除会话
//           sessionStore.deleteSessions([item.id!]);
//           nextTick(() => {
//             if (item.id === active.value) {
//               // 如果删除当前会话 返回到默认页
//               sessionStore.createSessionBtn();
//             }
//           });
//         })
//         .catch(() => {
//           // 取消删除
//         });
//       break;
//     case 'rename':
//       ElMessageBox.prompt('', '编辑对话名称', {
//         confirmButtonText: '确定',
//         cancelButtonText: '取消',
//         inputErrorMessage: '请输入对话名称',
//         confirmButtonClass: 'el-button--primary',
//         cancelButtonClass: 'el-button--info',
//         roundButton: true,
//         inputValue: item.sessionTitle, // 设置默认值
//         autofocus: false,
//         inputValidator: (value) => {
//           if (!value) {
//             return false;
//           }
//           return true;
//         },
//       }).then(({ value }) => {
//         sessionStore
//           .updateSession({
//             id: item.id!,
//             sessionTitle: value,
//             sessionContent: item.sessionContent,
//           })
//           .then(() => {
//             ElMessage({
//               type: 'success',
//               message: '修改成功',
//             });
//             nextTick(() => {
//               // 如果是当前会话，则更新当前选中会话信息
//               if (sessionStore.currentSession?.id === item.id) {
//                 sessionStore.setCurrentSession({
//                   ...item,
//                   sessionTitle: value,
//                 });
//               }
//             });
//           });
//       });
//       break;
//     default:
//       break;
//   }
// }
</script>

<template>
  <div
    class="aside-container"
    :class="{
      'aside-container-suspended': designStore.isSafeAreaHover,
      'aside-container-collapse': designStore.isCollapse,
      // 折叠且未激活悬停时添加 no-delay 类
      'no-delay': designStore.isCollapse && !designStore.hasActivatedHover,
      'loading': isLoading,
      'component-ready': componentReady,
    }"
  >
    <!-- 骨架屏 -->
    <SkeletonLoader
      v-if="isLoading"
      :is-sidebar="true"
      :menu-count="4"
      class="sidebar-skeleton-wrapper"
    />

    <!-- 实际内容 -->
    <div
      v-show="!isLoading"
      class="aside-wrapper"
      :class="{ 'fade-in': isInitialized }"
    >
      <!-- 顶部Logo区域 -->
      <div v-if="!designStore.isCollapse" class="aside-header">
        <div class="flex items-center gap-8px hover:cursor-pointer" @click="handleCreatChat">
          <el-image :src="logo" alt="logo" fit="cover" class="logo-img" />
          <span class="logo-text max-w-150px text-overflow">喜氧氧</span>
        </div>
        <Collapse class="ml-auto" />
      </div>

      <div class="aside-body">
        <!-- 导航菜单 -->
        <div class="nav-menu">
          <!-- 新对话 -->
          <div class="menu-item" :class="{ active: currentRoute === 'chat' || currentRoute === 'chatWithId' }">
            <div class="menu-main" @click="handleCreatChat">
              <el-icon class="menu-icon">
                <ChatDotRound />
              </el-icon>
              <span class="menu-text">智能问数Agent</span>
            </div>
          </div>

          <!-- 知识问答 - 父级菜单 -->
          <div class="menu-item" :class="{ active: currentRoute === 'knowledgeQA' || currentRoute === 'difyChatModule' || currentRoute === 'difyChatWithId' || currentRoute === 'industryKnowledge' || currentRoute === 'industryKnowledgeChatWithId' || currentRoute === 'financeQA' || currentRoute === 'financeQAChatWithId' }">
            <div class="menu-main" @click="handleMenuClick('knowledgeQA')">
              <el-icon class="menu-icon">
                <ChatDotSquare />
              </el-icon>
              <span class="menu-text">知识问答Agent</span>
              <el-icon class="expand-icon" :class="{ expanded: expandedMenus.includes('knowledgeQA') }">
                <ArrowDown />
              </el-icon>
            </div>
            <div class="menu-submenu" :class="{ expanded: expandedMenus.includes('knowledgeQA') }">
              <div class="submenu-item" :class="{ active: currentRoute === 'difyChatModule' || currentRoute === 'difyChatWithId' }" @click="handleSubmenuClick('difyChatModule', $event)">
                安全知识问答
              </div>
              <div class="submenu-item" :class="{ active: currentRoute === 'industryKnowledge' || currentRoute === 'industryKnowledgeChatWithId' }" @click="handleSubmenuClick('industryKnowledge', $event)">
                空分知识问答
              </div>
              <div class="submenu-item" :class="{ active: currentRoute === 'financeQA' || currentRoute === 'financeQAChatWithId' }" @click="handleSubmenuClick('financeQA', $event)">
                行业情报问答
              </div>
            </div>
          </div>

          <!-- 空分运行诊断Agent - 独立顶级菜单 -->
          <div class="menu-item" :class="{ active: currentRoute === 'airSeparationDiagnosis' || currentRoute === 'airSeparationDiagnosisWithId' }">
            <div class="menu-main" @click="handleMenuClick('airSeparationDiagnosis')">
              <el-icon class="menu-icon">
                <Tools />
              </el-icon>
              <span class="menu-text">空分运行诊断Agent</span>
            </div>
          </div>

          <!-- 自定义AI助手2 -->
          <!-- <div class="menu-item" :class="{ active: currentRoute === 'customAI2' || currentRoute === 'customAI2WithId' }">
            <div class="menu-main" @click="handleMenuClick('customAI2')">
              <el-icon class="menu-icon">
                <MagicStick />
              </el-icon>
              <span class="menu-text">自定义AI助手2</span>
            </div>
          </div> -->

          <!-- 自定义AI助手1 -->
          <!-- <div class="menu-item" :class="{ active: currentRoute === 'customAI1' || currentRoute === 'customAI1WithId' }">
            <div class="menu-main" @click="handleMenuClick('customAI1')">
              <el-icon class="menu-icon">
                <Cpu />
              </el-icon>
              <span class="menu-text">通用大模型助手</span>
            </div>
          </div> -->

          <!-- OAuth2测试页面 - 开发调试用 (暂时隐藏，因为对应路由不存在) -->
          <!-- <div v-if="isDev" class="menu-item" :class="{ active: currentRoute === 'oauth2-test' }">
            <div class="menu-main" @click="handleMenuClick('oauth2-test')">
              <el-icon class="menu-icon">
                <Key />
              </el-icon>
              <span class="menu-text">OAuth2测试</span>
            </div>
          </div> -->

          <!-- 校友福利 - 暂时隐藏 -->
          <div v-if="false" class="menu-item" :class="{ active: currentRoute === 'alumniBenefits' }">
            <div class="menu-main" @click="handleMenuClick('alumniBenefits')">
              <el-icon class="menu-icon">
                <Present />
              </el-icon>
              <span class="menu-text">待开发模块2</span>
            </div>
          </div>

          <!-- 开发者中心 - 暂时隐藏 -->
          <div v-if="false" class="menu-item" :class="{ active: currentRoute === 'developerCenter' }">
            <div class="menu-main" @click="handleMenuClick('developerCenter')">
              <el-icon class="menu-icon">
                <Monitor />
              </el-icon>
              <span class="menu-text">待开发模块3</span>
            </div>
          </div>

          <!-- 数学实训 - 暂时隐藏 -->
          <div v-if="false" class="menu-item" :class="{ active: currentRoute === 'mathTraining' || currentRoute === 'moPlatform' || currentRoute === 'smartClassroom' }">
            <div class="menu-main" @click="handleMenuClick('mathTraining')">
              <el-icon class="menu-icon">
                <EditPen />
              </el-icon>
              <span class="menu-text">待开发模块4</span>
              <el-icon class="expand-icon" :class="{ expanded: expandedMenus.includes('mathTraining') }">
                <ArrowDown />
              </el-icon>
            </div>
            <div class="menu-submenu" :class="{ expanded: expandedMenus.includes('mathTraining') }">
              <div class="submenu-item" :class="{ active: currentRoute === 'moPlatform' }" @click="handleSubmenuClick('moPlatform', $event)">
                子菜单1
              </div>
              <div class="submenu-item" :class="{ active: currentRoute === 'smartClassroom' }" @click="handleSubmenuClick('smartClassroom', $event)">
                子菜单2
              </div>
            </div>
          </div>

          <!-- 模型服务 - 暂时隐藏 -->
          <div v-if="false" class="menu-item" :class="{ active: currentRoute === 'modelService' || currentRoute === 'modelSquare' || currentRoute === 'modelTuning' || currentRoute === 'callManagement' }">
            <div class="menu-main" @click="handleMenuClick('modelService')">
              <el-icon class="menu-icon">
                <Setting />
              </el-icon>
              <span class="menu-text">待开发模块5</span>
              <el-icon class="expand-icon" :class="{ expanded: expandedMenus.includes('modelService') }">
                <ArrowDown />
              </el-icon>
            </div>
            <div class="menu-submenu" :class="{ expanded: expandedMenus.includes('modelService') }">
              <div class="submenu-item" :class="{ active: currentRoute === 'modelSquare' }" @click="handleSubmenuClick('modelSquare', $event)">
                子菜单1
              </div>
              <div class="submenu-item" :class="{ active: currentRoute === 'modelTuning' }" @click="handleSubmenuClick('modelTuning', $event)">
                子菜单2
              </div>
              <div class="submenu-item" :class="{ active: currentRoute === 'callManagement' }" @click="handleSubmenuClick('callManagement', $event)">
                子菜单3
              </div>
            </div>
          </div>
        </div>

        <!-- 底部登录区域 - 已隐藏 -->
        <!-- <div class="login-section">
          <div class="login-btn" @click="handleMenuClick('login')">
            <el-icon class="login-icon">
              <User />
            </el-icon>
            <span class="login-text">登录</span>
          </div>
        </div> -->

        <!-- 底部版权标识 -->
        <div class="copyright-section">
          <div class="copyright-text">
            © 气体运行部DIOC团队
            <br>
            © 浙大-杭氧智能空分联合研发中心
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
/**
 * 侧边栏组件样式总结：
 *
 * 布局结构：
 * - 采用绝对定位的侧边栏布局，支持折叠和悬停展开
 * - 使用 Flexbox 垂直布局，包含头部Logo区域、导航菜单和底部版权信息
 *
 * 颜色方案：
 * - 背景色：使用CSS变量 --sidebar-background-color
 * - 文字颜色：主要使用 #333333，次要信息使用 #666666 和 #999999
 * - 激活状态：使用 #409eff 蓝色作为主题色
 * - 悬停效果：使用 #f0f0f0 浅灰色背景
 *
 * 字体设置：
 * - Logo文字：16px，粗体700
 * - 菜单文字：14px，常规字重
 * - 图标：18px（主菜单），12px（展开图标）
 * - 版权信息：12px，行高1.4
 *
 * 动画效果：
 * - 所有交互元素使用 0.3s 过渡动画
 * - 折叠状态使用透明度和位移动画，支持延迟控制
 * - 子菜单展开使用 max-height 过渡
 *
 * 响应式特性：
 * - 支持折叠模式，折叠时显示为悬浮卡片
 * - 悬停时自动展开，支持无延迟模式
 * - 使用CSS变量控制侧边栏宽度
 */

/* 骨架屏和加载状态样式 */
.sidebar-skeleton-wrapper {
  width: 100%;
  height: 100%;
  padding: 16px;
  background-color: var(--sidebar-background-color);
}

/* 淡入动画 */
.fade-in {
  animation: fadeInUp 0.6s ease-out forwards;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 加载状态下的容器样式 */
.aside-container.loading {
  /* 防止加载时的布局跳动 */
  .aside-wrapper {
    pointer-events: none;
    opacity: 0;
  }
}

/* 组件就绪状态 */
.aside-container.component-ready {
  .aside-wrapper {
    pointer-events: auto;
    opacity: 1;
    transition: opacity var(--sidebar-transition-duration) var(--sidebar-transition-timing);
  }
}

// 侧边栏容器 - 主要布局容器
.aside-container {
  position: absolute;           // 绝对定位，固定在页面左侧
  top: 0;                      // 顶部对齐
  left: 0;                     // 左侧对齐
  z-index: 11;                 // 层级设置，确保在其他内容之上
  width: var(--sidebar-default-width);  // 使用CSS变量控制宽度，便于全局调整
  height: 100%;                // 占满整个视口高度

  /* 防止内容溢出导致的布局跳动 */
  overflow: hidden;

  /* 确保字体加载完成前的布局稳定性 */
  font-family: var(--font-family-base);
  pointer-events: auto;        // 启用鼠标事件
  background-color: var(--sidebar-background-color);  // 使用CSS变量设置背景色
  border-right: 0.5px solid var(--s-color-border-tertiary, rgb(0 0 0 / 8%));  // 右侧边框，使用变量或回退色

  /* 使用统一的过渡动画变量 */
  transition: all var(--sidebar-transition-duration) var(--sidebar-transition-timing);

  // 侧边栏内容包装器 - 垂直布局容器
  .aside-wrapper {
    display: flex;               // 弹性布局
    flex-direction: column;      // 垂直方向排列
    height: 100%;                // 占满父容器高度

    /* 防止内容溢出 */
    overflow: hidden;

    // 侧边栏头部样式 - Logo和折叠按钮区域
    .aside-header {
      display: flex;               // 水平布局

      /* 防止头部区域收缩 */
      flex-shrink: 0;
      align-items: center;         // 垂直居中对齐
      height: 36px;                // 固定高度
      margin: 10px 12px 0;         // 外边距：上10px，左右12px，下0

      // Logo图片容器样式
      .logo-img {
        box-sizing: border-box;      // 边框盒模型

        /* 防止图片加载导致的布局跳动 */
        flex-shrink: 0;
        width: 36px;                 // 固定宽度
        height: 36px;                // 固定高度，与容器高度一致
        padding: 4px;                // 内边距，为图片留出空间
        overflow: hidden;            // 隐藏溢出内容
        background-color: #ffffff;   // 白色背景
        border-radius: 50%;          // 圆形边框

        // Logo图片本身的样式
        img {
          display: flex;             // 弹性布局
          align-items: center;       // 垂直居中
          justify-content: center;   // 水平居中
          width: 100%;               // 占满容器宽度
          height: 100%;              // 占满容器高度

          /* 图片加载优化 */
          object-fit: contain;
        }
      }

      // Logo文字样式
      .logo-text {
        font-size: var(--font-size-base);  // 使用CSS变量控制字体大小
        font-weight: var(--font-weight-bold);  // 使用CSS变量控制字重
        line-height: 1;
        color: var(--text-color-primary);  // 使用语义化颜色变量

        /* 防止字体加载导致的布局跳动 */
        font-display: swap;
        transform: skewX(-2deg);    // 轻微倾斜效果，增加设计感
      }
    }

    // 侧边栏主体内容区域 - 包含导航菜单和底部信息
    .aside-body {
      display: flex;               // 弹性布局
      flex: 1;                     // 占据剩余空间，实现头部固定、主体自适应
      flex-direction: column;      // 垂直方向排列
      padding: 16px 0;             // 上下内边距16px，左右无内边距
      overflow: hidden auto;

      /* 防止内容溢出 */

      // 导航菜单容器样式
      .nav-menu {
        padding: 0 10px;            // 左右内边距10px
        margin-top: 10px;           // 顶部外边距10px

        // 单个菜单项容器 - 支持主菜单和子菜单
        .menu-item {
          position: relative;          // 相对定位，为激活状态的伪元素提供定位基准
          display: flex;               // 弹性布局
          flex-direction: column;      // 垂直布局，主菜单在上，子菜单在下
          align-items: stretch;        // 拉伸子元素，确保宽度一致
          margin-bottom: 4px;          // 菜单项之间的间距
          color: var(--text-color-primary);  // 使用语义化颜色变量
          border-radius: 4px;          // 圆角边框

          /* 使用统一的过渡动画变量 */
          transition: all var(--sidebar-transition-duration) var(--sidebar-transition-timing);

          // 菜单项主体部分 - 可点击的主要区域
          .menu-main {
            display: flex;             // 水平布局
            align-items: center;       // 垂直居中对齐
            height: 40px;              // 固定高度，保证点击区域一致
            padding: 0 12px 0 9px;     // 内边距：上下0，右12px，左9px

            /* 防止内容溢出 */
            overflow: hidden;
            cursor: pointer;           // 鼠标指针样式
            border-radius: 4px;        // 圆角边框

            /* 使用统一的过渡动画变量 */
            transition: all var(--sidebar-transition-duration) var(--sidebar-transition-timing);
          }

          // 菜单项悬停状态 - 鼠标悬停时的视觉反馈
          &:hover .menu-main {
             background-color: #dbeafe;  // 浅灰色背景，提供悬停反馈
           }

           // 菜单项激活状态 - 当前选中的菜单项样式
           &.active .menu-main {
             padding-left: 9px;          // 保持与默认状态一致的左内边距
             color: var(--text-color-primary);  // 保持文字颜色不变
             background-color: #dbeafe;   // 激活背景色

             // 激活状态下的图标样式
             .menu-icon {
               color: #409eff;            // 图标变为主题蓝色
             }
           }

          // 菜单图标样式
          .menu-icon {
            /* 防止图标收缩 */
            flex-shrink: 0;
            margin-right: 8px;          // 右侧外边距，与文字保持间距
            font-size: 18px;            // 图标大小
            color: var(--text-color-secondary);  // 使用语义化颜色变量
          }

          // 菜单文字样式
          .menu-text {
            flex: 1;                     // 占据剩余空间，实现文字区域自适应

            /* 防止文字溢出 */
            overflow: hidden;
            text-overflow: ellipsis;
            font-size: var(--font-size-sm);  // 使用CSS变量控制字体大小
            white-space: nowrap;
          }

          // 展开/收起图标样式 - 用于有子菜单的菜单项
          .expand-icon {
            /* 防止图标收缩 */
            flex-shrink: 0;
            font-size: 12px;            // 较小的图标尺寸

            /* 使用统一的过渡动画变量 */
            transition: transform var(--sidebar-transition-duration) var(--sidebar-transition-timing);

            // 展开状态 - 图标旋转180度
            &.expanded {
              transform: rotate(180deg); // 箭头向上指向，表示可收起
            }
          }
        }

        // 子菜单容器样式 - 可展开收起的二级菜单
        .menu-submenu {
          position: static;            // 静态定位，确保在文档流中占据空间
          width: 100%;                 // 占据整行宽度
          max-height: 0;               // 初始状态高度为0，实现收起效果
          overflow: hidden;            // 隐藏超出部分，配合max-height实现动画

          /* 使用统一的过渡动画变量 */
          transition: max-height var(--sidebar-transition-duration) var(--sidebar-transition-timing);

          // 展开状态 - 显示子菜单项
          &.expanded {
            max-height: 500px;         // 足够大的最大高度，确保所有子菜单项都能显示
            padding-bottom: 4px;       // 展开时添加底部内边距，增加视觉层次
          }

          // 单个子菜单项样式
          .submenu-item {
            position: relative;          // 相对定位，为激活指示条提供定位基准
            display: flex;               // 弹性布局
            align-items: center;         // 垂直居中对齐
            height: 36px;                // 固定高度，比主菜单项稍小
            padding: 0 10px 0 36px;      // 内边距：左侧36px形成缩进效果
            margin-bottom: 2px;          // 子菜单项之间的间距

            /* 防止内容溢出 */
            overflow: hidden;
            text-overflow: ellipsis;
            font-size: var(--font-size-sm);  // 使用CSS变量控制字体大小
            color: var(--text-color-primary);  // 使用语义化颜色变量
            white-space: nowrap;
            cursor: pointer;             // 鼠标指针样式
            border-radius: 4px;          // 圆角边框

            /* 使用统一的过渡动画变量 */
            transition: all var(--sidebar-transition-duration) var(--sidebar-transition-timing);

            // 子菜单项悬停状态
            &:hover {
              background-color: #f0f0f0;  // 悬停背景色
            }

            // 子菜单项激活状态
            &.active {
              padding-left: 36px;         // 保持与默认状态一致的左内边距
              color: var(--text-color-primary);  // 保持文字颜色
              background-color: #f0f0f0;   // 激活背景色
            }
          }
        }
      }

      // 菜单项间距统一调整 - 确保所有菜单项之间有一致的间距
      .menu-item {
        margin-bottom: 8px;          // 统一设置菜单项之间的间距为8px
      }

      // 底部登录区域样式 - 已隐藏，保留样式定义以备后用
      .login-section {
        padding: 0 12px 20px;       // 内边距：上0，左右12px，下20px
        margin-top: auto;            // 自动上边距，推到底部

        // 登录按钮样式
        .login-btn {
          display: flex;             // 弹性布局
          align-items: center;       // 垂直居中对齐
          padding: 12px 16px;        // 内边距：上下12px，左右16px
          margin: 8px;               // 外边距8px
          color: rgb(0 0 0 / 65%);   // 文字颜色，65%透明度
          cursor: pointer;           // 鼠标指针样式
          border-radius: 8px;        // 圆角边框

          /* 使用统一的过渡动画变量 */
          transition: all var(--sidebar-transition-duration) var(--sidebar-transition-timing);

          // 登录按钮悬停状态
          &:hover {
            color: var(--text-color-primary);  // 悬停时文字颜色加深
            background-color: #f5f5f5; // 悬停背景色
          }

          // 登录图标样式
          .login-icon {
            /* 防止图标收缩 */
            flex-shrink: 0;
            margin-right: 8px;       // 右侧外边距
            font-size: 16px;         // 图标大小
          }

          // 登录文字样式
          .login-text {
            font-size: var(--font-size-sm);  // 使用CSS变量控制字体大小
            font-weight: var(--font-weight-medium);  // 使用CSS变量控制字重
          }
        }
      }

      // 底部版权标识
      .copyright-section {
        padding: 0 12px 16px;
        margin-top: auto;
        .copyright-text {
          font-size: var(--font-size-xs);  // 使用CSS变量控制字体大小
          line-height: 1.4;
          color: var(--text-color-tertiary);  // 使用语义化颜色变量
          text-align: center;

          /* 防止文字溢出 */
          word-break: break-word;
        }
      }
    }
  }
}

// 折叠样式
.aside-container-collapse {
  position: absolute;
  top: 54px;
  z-index: 22;
  height: auto;
  max-height: calc(100% - 110px);
  padding-bottom: 12px;
  overflow: hidden;

  /* 禁用悬停事件 */
  pointer-events: none;
  border: 1px solid var(--s-color-border-tertiary, rgb(0 0 0 / 8%));
  border-radius: 15px;
  box-shadow:
    0 10px 20px 0 rgb(0 0 0 / 10%),
    0 0 1px 0 rgb(0 0 0 / 15%);
  opacity: 0;

  // 向左偏移一个宽度
  transform: translateX(-100%);
  transition: opacity 0.3s ease 0.3s, transform 0.3s ease 0.3s;

  /* 新增：未激活悬停时覆盖延迟 */
  &.no-delay {
    transition-delay: 0s, 0s;
  }
}

// 悬停样式
.aside-container-collapse:hover,
.aside-container-collapse.aside-container-suspended {
  height: auto;
  max-height: calc(100% - 110px);
  padding-bottom: 12px;
  overflow: hidden;
  pointer-events: auto;
  border: 1px solid var(--s-color-border-tertiary, rgb(0 0 0 / 8%));
  border-radius: 15px;
  box-shadow:
    0 10px 20px 0 rgb(0 0 0 / 10%),
    0 0 1px 0 rgb(0 0 0 / 15%);

  // 直接在这里写悬停时的样式（与 aside-container-suspended 一致）
  opacity: 1;

  // 过渡动画沿用原有设置
  transform: translateX(15px);
  transition: opacity 0.3s ease 0s, transform 0.3s ease 0s;

  // 会话列表高度-悬停样式
  .conversations-wrap {
    height: calc(100vh - 155px) !important;
  }
}

// 样式穿透
:deep(.conversations-list) {
  // 会话列表背景色
  .conversations-list {
    background-color: transparent !important;
  }

  // 群组标题样式 和 侧边栏菜单背景色一致
  .conversation-group-title {
    padding-left: 12px !important;
    background-color: var(--sidebar-background-color) !important;
  }
}
</style>
