<!-- 手机端布局 -->
<script setup lang="ts">
import Main from '@/layouts/components/Main/index.vue'
</script>

<template>
  <div class="mobile-layout">
    <!-- 移动端直接显示主内容，不显示侧边栏和头部 -->
    <div class="mobile-main">
      <Main />
    </div>
  </div>
</template>

<style scoped lang="scss">
.mobile-layout {
  width: 100%;
  height: 100vh;
  overflow: hidden;
  .mobile-main {
    width: 100%;
    height: 100%;
    padding: 0;
    overflow: auto;
  }
}
</style>
