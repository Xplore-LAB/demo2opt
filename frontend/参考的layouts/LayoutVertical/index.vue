<!-- 纵向布局作为基础布局 -->
<script setup lang="ts">
import { useSafeArea } from '@/hooks/useSafeArea'
import { useWindowWidthObserver } from '@/hooks/useWindowWidthObserver'
import Aside from '@/layouts/components/Aside/index.vue'
import Header from '@/layouts/components/Header/index.vue'
import Main from '@/layouts/components/Main/index.vue'
import { useDesignStore } from '@/stores'

const designStore = useDesignStore()

const isCollapse = computed(() => designStore.isCollapse)

/* 是否移入了安全区 */
useSafeArea({
  direction: 'left',
  size: 50,
  onChange(isInSafeArea) {
    // 设置悬停为 true
    designStore.isSafeAreaHover = isInSafeArea
  },
  enabled: isCollapse, // 折叠才开启监听
})

/** 监听窗口大小变化，折叠侧边栏 */
useWindowWidthObserver()
</script>

<template>
  <el-container class="layout-container">
    <el-header class="layout-header">
      <Header />
    </el-header>
    <el-container class="layout-container-main">
      <Aside />
      <el-main class="layout-main">
        <!-- 路由页面 -->
        <Main />
      </el-main>
    </el-container>
  </el-container>
</template>

<style lang="scss" scoped>
.layout-container {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  .layout-header {
    padding: 0;
  }
  .layout-main {
    width: 100%;
    height: 100%;
    padding: 0;
  }
  .layout-container-main {
    /* 设置左侧边栏的默认宽度 */
    margin-left: var(--sidebar-left-container-default-width, 0);

    /* 添加过渡动画效果,使边栏收缩更平滑 */
    transition: margin-left 0.3s ease;

    /* 确保主内容区域居中显示 */
    .layout-main {
      display: flex;
      align-items: flex-start;
      justify-content: center;

      /* 为内容添加最大宽度和居中 */
      > * {
        width: 100%;
        max-width: 1200px;
        margin: 0 auto;
      }
    }
  }
}

/** 去除菜单右侧边框 */
.el-menu {
  border-right: none;
}
.layout-scrollbar {
  width: 100%;
}
</style>
