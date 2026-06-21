# 工业空分装置智能优化系统 Backend Logic

## 当前主链路

1. 数据接入
   - 入口：`src/services/data_loader.py`
   - 负责读取 Excel、识别表格布局、标准化记录并执行质量门禁。
2. 语义分析
   - 入口：`src/services/data_semantics.py`
   - 负责单指标判级、异常明细、子系统状态、装置状态与风险等级聚合。
3. 根因推理
   - 入口：`src/services/reasoning_engine_v2.py`
   - 基于结构化异常结果和知识检索结果生成推理结论。
4. 决策建议
   - 入口：`src/services/decision_service.py`
   - 基于推理结果生成动作建议、验证状态、风险评估和回退策略。
5. 报告生成
   - 入口：`src/utils/report_generator.py`
   - 输出 Markdown/PDF 报告，并保留 traceability 文件。

## 数据接入口径

- `ExcelDataLoader` 现在会自动识别 `tall_table` 与 `wide_table`。
- 对当前仓库样本 `data/【原始数据】运行诊断.xlsx`：
  - `descriptor_row = 0`
  - `data_start_row = 1`
  - `design_ref_row = null`
  - 首个纳入时间点为 `2025-01-01 00:00:00`
  - 最后时间点为 `2025-12-01 00:00:00`
- 当前样本统计口径：
  - `timepoint_count = 335`
  - `sensor_count = 11`
  - `effective_record_count = 3685`
- 仅当检测到真实的“设计参考值行”时才会回填 `design_ref`；否则仍使用 `config/indicators.yaml` 的目标参考值作为最终判级依据。

## 规则与基线

- 单指标最终判级依赖三类参考：
  - 目标参考值：用于最终异常级别判定。
  - 历史运行基线：用于说明当前值相对历史常态的偏移。
  - 优态基线：用于说明优化空间。
- 单指标语义带宽统一来自 `config/semantic_rule_registry.yaml` 的 `indicator_state` 规则，而不是散落在代码中的隐式阈值。
- 每个异常项会输出 `rule_trace` / `state_rule_trace`，包含：
  - 目标方向
  - 参考值
  - 相对偏差
  - 命中的阈值区间
  - 最终状态标签

## 严重度计算

- 报告与审计统一展示真实公式：

```text
severity_score = level_score + diff_component + duration_component
```

- `base_score` 只保留为 fallback 配置，不再作为当前命中分支的展示口径。
- 严重度分解字段：
  - `level_score`
  - `diff_component`
  - `duration_component`
  - `duration_component_raw`
  - `duration_cap`
  - `duration_cap_applied`
  - `severity_score`
  - `base_score_fallback`
- 典型示例：
  - `level = 严重偏低`
  - `diff_percent = -80.6%`
  - `duration_points = 116`
  - 输出 `1.0 + 0.2821 + 0.2 = 1.4821`

## Calculation Audit

- `analysis_result.calculation_audit` 用于输出完整中间计算链。
- `traceability.trace_files.calculation_audit` 会落一份独立 JSON 文件。
- `calculation_audit` 结构：
  - `data_intake`
    - 布局识别、起始行、设计参考值行、排除行、首末时间点、门禁前后计数。
  - `indicators`
    - 当前值、目标参考值、历史中位、优态基线、最终判级依据、状态标签、历史百分位、持续点数、趋势、严重度分解。
  - `subsystems`
    - 成员指标、`abnormal_count`、`abnormal_ratio`、`avg_severity`、命中阈值、输出状态。
  - `plant`
    - `abnormal_ratio`、`max_severity`、`avg_optimal_gap`、风险等级分支、装置状态分支、主导异常和时间先后性说明。

## 报告与追溯

- Markdown/PDF 新增“中间计算审计”章节，包含：
  - 数据接入口径
  - 单指标审计表
  - 子系统与装置聚合输入
- trace 文件当前包括：
  - `traceability.json`
  - `summary.json`
  - `calculation_audit.json`
- WebSocket 最终结果会透传 `calculation_audit`，前端本次不新增专门面板。
