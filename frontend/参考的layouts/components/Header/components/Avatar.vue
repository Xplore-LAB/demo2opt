<!-- 头像 -->
<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
// 移除对 extractLoginInfoDisplay 的依赖，直接使用 userInfo 字段
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Popover from '@/components/Popover/index.vue'
import SvgIcon from '@/components/SvgIcon/index.vue'
import { type ManageEntry, resolveManageEntries } from '@/config/adminModules'
import { getUserAvatar } from '@/config/avatars'
import { useUserStore } from '@/stores'
import { useSessionStore } from '@/stores/modules/session'

const userStore = useUserStore()
const sessionStore = useSessionStore()
const router = useRouter()

// 加载状态检测
const isLoadingTooLong = ref(false)
const loadingStartTime = ref<number | null>(null)

// 监听token和userInfo的变化，智能管理加载状态
watch(
  () => [userStore.token, userStore.userInfo],
  ([newToken, newUserInfo]) => {
    // 如果有token但没有用户信息，开始计时
    if (newToken && !newUserInfo) {
      if (!loadingStartTime.value) {
        loadingStartTime.value = Date.now()
        isLoadingTooLong.value = false

        // 3秒后如果还在加载，标记为加载时间过长
        setTimeout(() => {
          if (loadingStartTime.value && userStore.token && !userStore.userInfo) {
            isLoadingTooLong.value = true
            console.warn('⚠️ 用户信息加载时间过长，可能存在问题')
          }
        }, 3000)
      }
    }
    else {
      // 如果没有token或已有用户信息，重置加载状态
      loadingStartTime.value = null
      isLoadingTooLong.value = false
    }
  },
  { immediate: true },
)
// 用户头像 - 使用统一的头像配置
const src = computed(() => getUserAvatar(userStore.userInfo))

// 头像与组件加载占位
const avatarLoaded = ref(false)

function preloadImage(url?: string | null) {
  return new Promise<void>((resolve) => {
    if (!url) {
      resolve()
      return
    }
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => resolve()
    img.onerror = () => resolve()
    img.src = url
  })
}

watch(src, async (url) => {
  avatarLoaded.value = false
  await preloadImage(typeof url === 'string' ? url : undefined)
  avatarLoaded.value = true
})

onMounted(async () => {
  await nextTick()
  await preloadImage(typeof src.value === 'string' ? src.value : undefined)
  avatarLoaded.value = true
})

// 获取用户显示名称
const userName = computed(() => {
  // 如果有完整的用户信息，直接返回用户名
  if (userStore.userInfo) {
    return userStore.userInfo.real_name || userStore.userInfo.user_name || userStore.userInfo.username || '未知用户'
  }

  // 如果有token但没有用户信息
  if (userStore.token) {
    // 如果加载时间过长，显示错误提示
    if (isLoadingTooLong.value) {
      return '加载失败，请刷新'
    }
    // 正常加载状态
    return '用户信息加载中...'
  }

  return '未登录'
})

// 获取用户详细信息 - 直接使用 userInfo 字段
const userDetails = computed(() => {
  const user = userStore.userInfo
  // 只要用户已登录且有基本用户标识就显示详情
  if (!user || (!user.user_name && !user.role_name && !user.user_id)) {
    return null
  }

  // 直接返回用户信息字段
  return {
    name: user.real_name || user.user_name || user.user_id || '未设置', // 优先显示真实姓名，其次用户名
    loginId: user.user_name || user.username || (user as any).loginId || '未设置', // 登录ID应显示登录名，兼容多字段
    employeeId: user.employee_id || '未设置',
    phone: user.phone_number || '未设置',
    role: user.role_name || '未设置',
    companyId: user.company_id || '未设置',
    companyName: user.company_name || '未设置',
    regionId: user.region_id || '未设置',
    regionName: user.region_name || '未设置',
  }
})

// 管理权限由 resolveManageEntries 统一判断，无需单独 isAdmin 变量

// 计算可见的管理入口（可配置，支持本地/后端扩展）
const extraEntries = computed<ManageEntry[]>(() => {
  try {
    const raw = localStorage.getItem('admin_entries')
    if (!raw)
      return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed))
      return parsed as ManageEntry[]
    return []
  }
  catch {
    return []
  }
})
const manageEntries = computed(() => {
  return resolveManageEntries(userStore.userInfo, extraEntries.value)
})

// 弹出面板样式与引用
const popoverStyle = ref({
  width: '320px',
  padding: '4px',
  height: 'fit-content',
  maxHeight: '600px',
  overflowY: 'auto' as const,
})
const popoverRef = ref()

// 弹出面板内容 - 根据登录状态动态显示（显式类型确保icon可选）
interface PopItem { key: string, title: string, icon?: string }
const popoverList = computed<PopItem[]>(() => {
  if (!userStore.isLogin) {
    return [
      { key: 'login', title: '登录', icon: 'login-box-line' },
      { key: 'clearCache', title: '清理缓存数据', icon: 'delete-bin-line' },
    ]
  }

  const baseItems: PopItem[] = [
    { key: 'logout', title: '退出登录', icon: 'logout-box-r-line' },
  ]

  // 如果拥有管理入口，插入到菜单顶部
  const entries = manageEntries.value
  entries.forEach(e => baseItems.unshift({ key: e.key, title: e.title, icon: e.icon }))

  return baseItems
})

// 点击处理 - 扩展处理管理入口路由
function handleClick(item: any) {
  switch (item.key) {
    case 'login':
      popoverRef.value?.hide?.()
      userStore.openLoginDialog()
      break
    // 动态管理入口
    case 'userManagement':
      popoverRef.value?.hide?.()
      router.push('/user-management')
      break
    default:
      // 如果是其它管理入口，尝试从配置解析路由
      const entry = manageEntries.value.find(e => e.key === item.key)
      if (entry && entry.route) {
        popoverRef.value?.hide?.()
        router.push(entry.route)
        break
      }
      // 原有处理
      if (item.key === 'logout') {
        popoverRef.value?.hide?.()
        ElMessageBox.confirm('退出登录不会丢失任何数据，你仍可以登录此账号。', '确认退出登录？', {
          confirmButtonText: '确认退出',
          cancelButtonText: '取消',
          type: 'warning',
          confirmButtonClass: 'el-button--danger',
          cancelButtonClass: 'el-button--info',
          roundButton: true,
          autofocus: false,
        })
          .then(async () => {
            await userStore.logout()
            await sessionStore.requestSessionList()
            await sessionStore.createSessionBtn()
            ElMessage({ type: 'success', message: '退出成功' })
          })
        break
      }
      if (item.key === 'clearCache') {
        popoverRef.value?.hide?.()
        ElMessageBox.confirm(
          '此操作将清理所有缓存的用户数据，包括登录状态、用户信息等。清理后需要重新登录。',
          '确认清理缓存数据？',
          {
            confirmButtonText: '确认清理',
            cancelButtonText: '取消',
            type: 'warning',
            confirmButtonClass: 'el-button--danger',
            cancelButtonClass: 'el-button--info',
            roundButton: true,
            autofocus: false,
          },
        ).then(() => {
          userStore.clearAllUserData()
          sessionStore.requestSessionList()
          sessionStore.createSessionBtn()
          setTimeout(() => window.location.reload(), 500)
          ElMessage({ type: 'success', message: '缓存数据已清理，页面即将刷新' })
        })
        break
      }
  }
}

/* 弹出面板 结束 */

// 帮助链接
const helpLink = ref('https://www.kdocs.cn/l/cgAVTIomKRhD') // 外部链接，待用户填写

function goToHelpLink() {
  window.open(helpLink.value, '_blank')
}
</script>

<template>
  <div class="avatar-container flex items-center flex-nowrap">
    <!-- 问号图标 -->
    <div class="help-icon-container mr-8px cursor-pointer hover:bg-[rgba(0,0,0,.04)] rounded-6px p-4px flex-shrink-0" @click="goToHelpLink">
      <SvgIcon name="question-line" size="20" class="text-[#333]" />
    </div>

    <Popover
      ref="popoverRef"
      placement="bottom-end"
      trigger="clickTarget"
      :trigger-style="{ cursor: 'pointer' }"
      popover-class="popover-content"
      :popover-style="popoverStyle"
    >
      <!-- 触发元素插槽 -->
      <template #trigger>
        <div class="user-info-container flex items-center flex-nowrap gap-8px cursor-pointer hover:bg-[rgba(0,0,0,.04)] rounded-6px p-4px">
          <template v-if="(userStore.token && !userStore.userInfo && !isLoadingTooLong) || !avatarLoaded">
            <div class="avatar-skeleton" aria-hidden="true">
              <div class="skeleton-circle" />
              <div class="skeleton-text" />
            </div>
          </template>
          <template v-else>
            <el-avatar :src="src" :size="28" fit="fit" shape="circle" />
            <span class="user-name font-size-14px text-[#333] max-w-100px text-overflow">{{ userName }}</span>
          </template>
        </div>
      </template>

      <div class="popover-content-box shadow-lg">
        <!-- 用户详细信息区域 -->
        <div v-if="userDetails" class="user-details-section p-12px border-b border-gray-200 mb-8px">
          <div class="user-details-title font-size-16px font-bold text-[#333] mb-8px">
            用户信息
          </div>
          <div class="user-details-list space-y-4px">
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">姓名:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.name }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">登录ID:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.loginId }}</span>
            </div>
            <!-- <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">工号:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.employeeId }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">电话:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.phone }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">角色:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.role }}</span>
            </div>

            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">公司ID:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.companyId }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">公司名称:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.companyName }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">区域ID:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.regionId }}</span>
            </div>
            <div class="user-detail-item flex justify-between items-center">
              <span class="detail-label font-size-12px text-gray-500 min-w-60px">区域名称:</span>
              <span class="detail-value font-size-13px text-[#333] text-right flex-1 ml-8px text-overflow">{{ userDetails.regionName }}</span>
            </div> -->
          </div>
        </div>

        <!-- 退出登录按钮区域 -->
        <div v-for="item in popoverList" :key="item.key" class="popover-content-box-items h-full">
          <div
            class="popover-content-box-item flex items-center h-full gap-8px p-8px pl-10px pr-12px rounded-lg hover:cursor-pointer hover:bg-[rgba(0,0,0,.04)]"
            @click="handleClick(item)"
          >
            <SvgIcon :name="item.icon!" size="16" class-name="flex-none" />
            <div class="popover-content-box-item-text font-size-14px text-overflow max-h-120px">
              {{ item.title }}
            </div>
          </div>
        </div>
      </div>
    </Popover>
  </div>
</template>

<style scoped lang="scss">
.popover-content {
  width: 320px;
  max-height: 600px;
  overflow-y: auto;
}
.popover-content-box {
  padding: 8px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 8%);
}
.avatar-skeleton {
  display: flex;
  gap: 8px;
  align-items: center;
}
.skeleton-circle {
  width: 28px;
  height: 28px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  border-radius: 50%;
  animation: shimmer 1.5s infinite;
}
.skeleton-text {
  width: 80px;
  height: 14px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  border-radius: 6px;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.user-details-section {
  .user-detail-item {
    min-height: 24px;
    .detail-label {
      font-weight: 500;
      color: #6b7280;
    }
    .detail-value {
      max-width: 200px;
      color: #374151;
      word-break: break-all;
    }
  }
}
</style>
