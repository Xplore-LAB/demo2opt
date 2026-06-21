# Layouts 布局模块文档

## 概述
`src/layouts` 目录存放应用的全局布局组件，负责整体页面的结构（如侧边栏、顶部导航、内容区域）。

## 目录结构
```
src/layouts/
├── LayoutMobile/     # 移动端布局
├── LayoutVertical/   # 桌面端垂直布局（侧边栏模式）
├── components/       # 布局专用组件
│   ├── Aside/        # 侧边栏
│   ├── Header/       # 顶部导航栏
│   ├── Logo/         # Logo 组件
│   ├── Main/         # 主内容区域 wrapper
│   └── DesignConfig/ # 主题配置抽屉
└── index.vue         # 布局入口，负责响应式切换
```

## 维护说明
1. **响应式**: `index.vue` 根据 `useScreen` 等钩子决定显示 `LayoutMobile` 还是 `LayoutVertical`。
2. **插槽**: 布局组件通常包含 `<router-view>` 来渲染具体页面。
3. **文档更新**: 修改布局结构后，**必须**同步更新本文档。
