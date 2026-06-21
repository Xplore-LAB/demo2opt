# Backend API Contract

本文档描述当前前后端对齐的后端输出字段，重点补充 `calculation_audit` 与新的数据接入口径。

## REST API

Base URL: `http://localhost:5000`

### `GET /api/health`

用途：健康检查。

### `GET /api/tasks`

用途：查询任务列表。

常见字段：
- `task_id`
- `status`
- `progress`
- `current_step`
- `total_steps`
- `current_step_index`
- `start_time`
- `end_time`
- `error_message`
- `metadata`

### `GET /api/tasks/{task_id}`

用途：查询单个任务详情。

### `GET /api/tasks/{task_id}/progress`

用途：查询任务进度摘要。

### `POST /api/tasks/cleanup`

用途：清理旧任务。

## WebSocket API

URL: `ws://localhost:8001`

### 客户端 `start`

```json
{
  "type": "start",
  "data_source": "sample",
  "sample_file": "data/demo.xlsx",
  "enable_cot": true,
  "auto_confirm": true
}
```

可选附加字段：
- `llm_config`
- `dify_config`
- `task_note`

### 客户端 `interaction_response`

```json
{
  "type": "interaction_response",
  "id": "1740900000000",
  "value": "yes"
}
```

## 服务端事件

### `log`

用途：日志流。

关键字段：
- `type`
- `message`
- `level`
- `timestamp`

### `phase_update`

用途：阶段状态更新。

关键字段：
- `type`
- `phase`
- `status`
- `step`
- `workflow_step_id`
- `workflow_step_title`
- `workflow_step_state`
- `progress_percent`
- `eta_sec`

### `interaction`

用途：中途要求用户确认。

关键字段：
- `type`
- `id`
- `title`
- `desc`
- `checkpoint_key`
- `phase`
- `risk_level`
- `impact_scope`
- `recommended_action`
- `blocking`

### `result`

用途：返回最终分析结果。

```json
{
  "type": "result",
  "data": {
    "report_pdf": "reports/analysis_report_20260316_100000.pdf",
    "report_md": "reports/analysis_report_20260316_100000.md",
    "abnormal_indicators": [],
    "reasoning": "根因摘要",
    "suggestion": "操作建议摘要",
    "warning": "安全提示",
    "decision": {},
    "reasoning_result": "完整推理文本",
    "semantic_data": [],
    "analysis_steps": [],
    "overall_judgement": {},
    "calculation_audit": {},
    "data_overview": {},
    "semantic_summary": {},
    "semantic_ai_review": {},
    "knowledge_retrieval": {},
    "optimization_context": {},
    "visualization_context": {},
    "traceability": {}
  },
  "timestamp": "2026-03-16T10:00:00.000000"
}
```

## `data_overview` 关键字段

- `file_name`
- `timepoint_count`
- `sensor_count`
- `effective_record_count`
- `time_range_start`
- `time_range_end`
- `latest_timestamp`
- `latest_record_count`
- `quality_gate_status`

当前示例样本的标准口径为：
- `timepoint_count = 335`
- `sensor_count = 11`
- `effective_record_count = 3685`
- 首个时间点已纳入 `2025-01-01 00:00:00`

## `calculation_audit` Contract

### `calculation_audit.data_intake`

关键字段：
- `layout_detected`
- `data_start_row`
- `design_ref_row`
- `dropped_rows`
- `first_included_timestamp`
- `last_included_timestamp`
- `record_count_before_gate`
- `record_count_after_gate`
- `timepoint_count_before_gate`
- `timepoint_count_after_gate`
- `sensor_count`
- `count_change_reason`

### `calculation_audit.indicators[]`

关键字段：
- `tag_id`
- `name`
- `objective`
- `state_label`
- `current_value`
- `target_reference`
- `history_baseline`
- `optimal_reference`
- `final_grade_basis`
- `final_grade_basis_label`
- `diff_ratio`
- `diff_percent`
- `history_diff_percent`
- `optimal_diff_percent`
- `history_percentile_rank`
- `trend`
- `duration_points`
- `severity_score`
- `severity_breakdown`
- `state_rule_trace`
- `comparison_method`
- `reference_label`

### `calculation_audit.subsystems[]`

关键字段：
- `name`
- `state`
- `abnormal_count`
- `total_count`
- `abnormal_ratio`
- `avg_severity`
- `members`
- `thresholds`
- `triggered_by`

### `calculation_audit.plant`

关键字段：
- `abnormal_count`
- `total_count`
- `abnormal_ratio`
- `max_severity`
- `avg_optimal_gap`
- `risk_level`
- `risk_level_label`
- `risk_branch`
- `plant_state`
- `plant_state_label`
- `plant_state_branch`
- `main_contradiction`
- `dominant_anomaly`

## Traceability Contract

`traceability.trace_files` 现在包含：
- `traceability`
- `summary`
- `calculation_audit`

其中 `traceability.trace_files.calculation_audit` 指向本轮运行生成的独立 JSON 审计文件。
