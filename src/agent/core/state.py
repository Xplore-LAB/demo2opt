from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class OptimizationState(TypedDict, total=False):
    task_id: str
    session_id: str
    entrypoint: str
    created_at: str
    data_file: str
    file_name: str
    display_file_name: str
    data_source: str
    task_note: str
    enable_async: bool
    enable_cot: bool
    use_asu_pipeline: bool
    auto_confirm: bool
    llm_config: Dict[str, Any]
    dify_config: Dict[str, Any]
    execution_feedback: Dict[str, Any]
    service_overrides: Dict[str, Any]
    status: str
    cancelled: bool
    cancel_message: str
    error: str
    error_code: str
    current_node: str
    next_node: str
    resume_node: str
    pending_checkpoint: Dict[str, Any]
    human_decisions: Dict[str, Any]
    interaction_records: List[Dict[str, Any]]
    llm_activity_history: List[Dict[str, Any]]
    execution_history: List[Dict[str, Any]]
    raw_records: List[Dict[str, Any]]
    standardized_data: List[Dict[str, Any]]
    latest_records: List[Dict[str, Any]]
    asu_facts: List[Dict[str, Any]]
    asu_meta: List[Dict[str, Any]]
    asu_derived: List[Dict[str, Any]]
    quality_gate: Dict[str, Any]
    quality_report: Dict[str, Any]
    timestamps: List[str]
    timepoint_count: int
    sensor_count: int
    effective_record_count: int
    min_timestamp: Optional[str]
    max_timestamp: Optional[str]
    latest_timestamp: Optional[str]
    baseline_profile: Dict[str, Any]
    history_model_metadata: Dict[str, Any]
    semantic_data: List[Dict[str, Any]]
    abnormal_details: List[Dict[str, Any]]
    overall_judgement: Dict[str, Any]
    core_indicators: Any
    features: Dict[str, Any]
    semantic_ai_review: Dict[str, Any]
    should_run_reasoning: bool
    primary_retrieval: Dict[str, Any]
    review_retrieval: Dict[str, Any]
    knowledge_retrieval: Dict[str, Any]
    reasoning_result: Dict[str, Any]
    decision_result: Dict[str, Any]
    analysis_steps: List[Dict[str, Any]]
    data_overview: Dict[str, Any]
    semantic_summary: Dict[str, Any]
    optimization_context: Dict[str, Any]
    visualization_context: Dict[str, Any]
    traceability: Dict[str, Any]
    report_pdf: Optional[str]
    report_md: Optional[str]
    analysis_result: Dict[str, Any]
