# 氮塞模块拆分边界

## 旧模块来源

### 前端识别相关

- `legacy_snapshot/frontend/utils/nitrogenCore.js`
- `legacy_snapshot/frontend/workers/nitrogenScan.worker.js`
- `legacy_snapshot/frontend/views/NitrogenPlugDemo.vue`

### 后端分析相关

- `legacy_snapshot/backend/server.py`
- `legacy_snapshot/services/reasoning_engine_v2.py`
- `legacy_snapshot/services/decision_service.py`

## 新模块目标

### 1. detection_service

职责：
- 输入时序窗口或图像切片
- 输出候选氮塞事件
- 不负责原因分析

### 2. process_analysis_service

职责：
- 输入候选事件和多测点上下文
- 输出原因排序、证据链、补充测点建议
- 不负责动作验证

### 3. twin_validation_service

职责：
- 输入诊断结果和建议动作
- 输出稳态/动态验证结果
- 约束校核、风险等级、回退建议

## 当前迁移优先级

1. `nitrogenCore.js` 中的窗口扫描与事件识别
2. `server.py` 中的氮塞区间分析接口
3. `decision_service.py` 中的验证输出框架
