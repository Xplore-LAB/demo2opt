<!-- 主布局 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useScreenStore } from '@/hooks/useScreen'
import LayoutMobile from '@/layouts/LayoutMobile/index.vue'
import LayoutVertical from '@/layouts/LayoutVertical/index.vue'
import { useDesignStore } from '@/stores'

// 这里添加布局类型
const LayoutComponent = {
  vertical: LayoutVertical,
  mobile: LayoutMobile,
}

const designStore = useDesignStore()
const { isMobile } = useScreenStore()

/** 获取布局格式 */
const layout = computed(() => {
  // 如果是移动端，使用移动端布局
  if (isMobile.value) {
    return 'mobile'
  }
  return designStore.layout
})
</script>

<template>
  <div>
    <component :is="LayoutComponent[layout]" :key="layout" />
  </div>
</template>

<style scoped lang="scss"></style>
