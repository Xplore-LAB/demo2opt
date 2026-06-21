# Nitrogen Refactor Workspace

这个文件夹用于把当前仓库里的“氮塞模块”单独抽出来，先保留一份稳定快照，再在独立骨架上逐步改造。

## 目录说明

```text
nitrogen_refactor_workspace/
  legacy_snapshot/    # 从当前主项目直接复制出的稳定快照
  refactor_target/    # 后续真正改造的独立骨架
  docs/               # 模块边界、改造说明、迁移计划
```

## 已复制的旧模块

- `legacy_snapshot/backend/server.py`
- `legacy_snapshot/services/reasoning_engine_v2.py`
- `legacy_snapshot/services/decision_service.py`
- `legacy_snapshot/frontend/views/NitrogenPlugDemo.vue`
- `legacy_snapshot/frontend/utils/nitrogenCore.js`
- `legacy_snapshot/frontend/workers/nitrogenScan.worker.js`

## 当前改造策略

1. 先保留旧代码快照，确保现有逻辑可对照、可回退。
2. 在 `refactor_target/` 下重新定义三模块边界：
   - 氮塞检测
   - 过程分析
   - 数字孪生验证
3. 先搭接口和对象，再逐步把旧逻辑搬进新架构。

## 下一步建议

1. 先把旧前端检测逻辑迁到 `refactor_target/backend/services/detection_service.py`
2. 再把当前后端区间分析重组到 `process_analysis_service.py`
3. 最后把物料平衡和仿真验证整理到 `twin_validation_service.py`
