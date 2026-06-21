# Frontend Migration Notes

当前前端旧代码快照在：

- `../../legacy_snapshot/frontend/views/NitrogenPlugDemo.vue`
- `../../legacy_snapshot/frontend/utils/nitrogenCore.js`
- `../../legacy_snapshot/frontend/workers/nitrogenScan.worker.js`

后续迁移原则：

1. 页面继续保留可视化和交互。
2. 主检测逻辑迁移到后端。
3. 前端只请求候选事件、分析结果和验证结果。
