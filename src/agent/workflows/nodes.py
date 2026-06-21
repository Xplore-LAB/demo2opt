from __future__ import annotations

import asyncio
import inspect
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.agent.core.runtime import AgentRuntimeHooks
from src.agent.core.state import OptimizationState
from src.services.data_loader import ASUDataLoader, ExcelDataLoader
from src.services.data_semantics import DataSemanticsService
from src.services.decision_service import DecisionService
from src.services.knowledge_retrieval_service import KnowledgeRetrievalService
from src.services.reasoning_engine_v2 import ReasoningEngineV2
from src.services.visualization_service import TimeComparisonVisualizationService
from src.schemas.models import model_to_dict, validate_decision_result, validate_reasoning_result
from src.utils.business_logic import is_abnormal_state
from src.utils.report_generator import ReportGenerator

STEP_TITLES = {
    1: "数据加载与范围确认",
    2: "最新时刻快照提取",
    3: "规则预筛与语义复核",
    4: "工况总览判断",
    5: "时序特征提取与候选复核",
    6: "外挂知识库 API 检索手段",
    7: "AI 根因诊断",
    8: "决策验证与报告生成",
}

NODE_META: Dict[str, Dict[str, Any]] = {
    "load_data": {"phase": "init", "step": 0, "workflow_step_id": 1, "workflow_step_title": STEP_TITLES[1]},
    "confirm_data_range": {"phase": "init", "step": 1, "workflow_step_id": 1, "workflow_step_title": STEP_TITLES[1]},
    "select_snapshot": {"phase": "init", "workflow_step_id": 2, "workflow_step_title": STEP_TITLES[2]},
    "semantic_analysis": {"phase": "analysis", "step": 0, "workflow_step_id": 3, "workflow_step_title": STEP_TITLES[3]},
    "confirm_overview": {"phase": "analysis", "step": 2, "workflow_step_id": 4, "workflow_step_title": STEP_TITLES[4]},
    "extract_features": {"phase": "analysis", "step": 3, "workflow_step_id": 5, "workflow_step_title": STEP_TITLES[5]},
    "confirm_candidates": {"phase": "analysis", "step": 3, "workflow_step_id": 5, "workflow_step_title": STEP_TITLES[5]},
    "primary_retrieval": {"phase": "analysis", "step": 3, "workflow_step_id": 6, "workflow_step_title": STEP_TITLES[6]},
    "confirm_high_risk": {"phase": "analysis", "step": 4, "workflow_step_id": 7, "workflow_step_title": STEP_TITLES[7]},
    "reasoning": {"phase": "analysis", "step": 4, "workflow_step_id": 7, "workflow_step_title": STEP_TITLES[7]},
    "review_retrieval": {"phase": "analysis", "step": 4, "workflow_step_id": 7, "workflow_step_title": STEP_TITLES[7]},
    "decision": {"phase": "analysis", "workflow_step_id": 8, "workflow_step_title": STEP_TITLES[8]},
    "generate_report": {"phase": "report", "step": 0, "workflow_step_id": 8, "workflow_step_title": STEP_TITLES[8]},
    "finalize_success": {"phase": "report", "workflow_step_id": 8, "workflow_step_title": STEP_TITLES[8]},
}

HEALTHY_PLANT_STATES = {"optimizable", "risk_rising", "abnormal_unstable"}
HIGH_RISK_KEYWORDS = ("严重", "危险", "联锁", "超压", "失稳", "泄漏", "critical", "trip")
RISK_LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _now() -> str:
    return datetime.now().isoformat()


def _service(state: OptimizationState, key: str, default_factory: Callable[[], Any]) -> Any:
    overrides = state.get("service_overrides") or {}
    if key in overrides:
        return overrides[key]
    return default_factory()


def _to_dict(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _append_record(state: OptimizationState, key: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    current = list(state.get(key) or [])
    current.append(item)
    return current


def _normalize_indicator_name(value: Any) -> str:
    return "".join(str(value or "").split()).lower()


def _build_data_overview(state: OptimizationState) -> Dict[str, Any]:
    return {
        "file_name": state.get("display_file_name") or Path(state.get("data_file") or "").name,
        "timepoint_count": state.get("timepoint_count", 0),
        "sensor_count": state.get("sensor_count", 0),
        "effective_record_count": state.get("effective_record_count", 0),
        "time_range_start": str(state.get("min_timestamp") or ""),
        "time_range_end": str(state.get("max_timestamp") or ""),
        "latest_timestamp": str(state.get("latest_timestamp") or ""),
        "latest_record_count": len(state.get("latest_records") or []),
        "task_note": state.get("task_note") or "",
        "quality_gate_status": (state.get("quality_gate") or {}).get("status", "UNKNOWN"),
    }


def _build_semantic_summary(
    state: OptimizationState,
    semantic_data: List[Dict[str, Any]],
    abnormal_details: List[Dict[str, Any]],
    overall_judgement: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state_counts = dict(Counter(item.get("state_desc", "Unknown") for item in semantic_data))
    feature_values = state.get("features") or {}
    feature_entries = feature_values.get("per_tag") if isinstance(feature_values, dict) and isinstance(feature_values.get("per_tag"), dict) else feature_values
    trend_counts = dict(Counter(item.get("trend", "unknown") for item in feature_entries.values())) if isinstance(feature_entries, dict) else {}
    overall = overall_judgement or state.get("overall_judgement") or {}
    return {
        "state_counts": state_counts,
        "trend_counts": trend_counts,
        "top_abnormal_names": [item.get("name") for item in abnormal_details[:5]],
        "plant_state": overall.get("plant_state"),
        "plant_state_label": overall.get("plant_state_label"),
        "optimization_priority": overall.get("optimization_priority") or [],
    }


def _has_llm_config(state: OptimizationState) -> bool:
    config = state.get("llm_config") or {}
    return bool(config.get("api_key") and config.get("base_url") and config.get("model"))


def _merge_ai_indicator_reasons(abnormal_details: List[Dict[str, Any]], reasoning_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    diagnoses = reasoning_result.get("indicator_diagnoses") or []
    if not diagnoses:
        return abnormal_details
    reason_map = {}
    for item in diagnoses:
        key = _normalize_indicator_name(item.get("name"))
        if key:
            reason_map[key] = item
    merged = []
    for detail in abnormal_details:
        enriched = dict(detail)
        diagnosis = reason_map.get(_normalize_indicator_name(detail.get("name")))
        if diagnosis:
            enriched["ai_reason"] = diagnosis.get("ai_reason", "")
            enriched["ai_confidence"] = diagnosis.get("confidence")
        merged.append(enriched)
    return merged


def _merge_knowledge_retrieval(primary: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    primary = primary or {}
    review = review or {}

    def _dedupe(items: List[Any]) -> List[Any]:
        seen = set()
        result = []
        for item in items or []:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    primary_summary = str(primary.get("retrieval_summary") or "").strip()
    review_summary = str(review.get("retrieval_summary") or "").strip()
    summary_parts = []
    if primary_summary:
        summary_parts.append(f"主检索：{primary_summary}")
    if review_summary:
        summary_parts.append(f"校核检索：{review_summary}")
    return {
        "retrieval_stage": "dual",
        "retrieval_summary": " | ".join(summary_parts) or "知识检索未返回有效摘要。",
        "recommended_measures": _dedupe((primary.get("recommended_measures") or []) + (review.get("recommended_measures") or [])),
        "knowledge_references": _dedupe((primary.get("knowledge_references") or []) + (review.get("knowledge_references") or [])),
        "risk_tips": _dedupe((primary.get("risk_tips") or []) + (review.get("risk_tips") or [])),
        "primary_retrieval": primary,
        "review_retrieval": review,
        "raw_response": "\n---primary---\n" + str(primary.get("raw_response") or "") + "\n---review---\n" + str(review.get("raw_response") or ""),
    }


def _infer_risk_level(item: Dict[str, Any]) -> str:
    text = " ".join(
        [
            str(item.get("level", "")),
            str(item.get("state_desc", "")),
            str(item.get("status", "")),
            str(item.get("rule_reason", "")),
            str(item.get("ai_reason", "")),
        ]
    ).lower()
    if "critical" in text or "严重" in text:
        return "critical"
    if "high" in text or "高" in text or "危险" in text:
        return "high"
    if "warning" in text or "medium" in text or "偏" in text:
        return "medium"
    return "low"


def _detect_high_risk_candidates(abnormal_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    high_risk_items = []
    for item in abnormal_details:
        risk_level = _infer_risk_level(item)
        text = f"{item.get('rule_reason', '')} {item.get('ai_reason', '')} {item.get('name', '')}".lower()
        has_template_hit = any(keyword.lower() in text for keyword in HIGH_RISK_KEYWORDS)
        if risk_level in {"high", "critical"} or has_template_hit:
            high_risk_items.append({**item, "risk_level": risk_level})
    if not high_risk_items:
        return {"triggered": False, "risk_level": "low", "items": [], "impact_scope": []}
    risk_level = sorted([item["risk_level"] for item in high_risk_items], key=lambda level: RISK_LEVEL_ORDER.get(level, 1))[-1]
    impact_scope = [item.get("name") or item.get("tag_id") for item in high_risk_items[:5] if item.get("name") or item.get("tag_id")]
    return {"triggered": True, "risk_level": risk_level, "items": high_risk_items, "impact_scope": impact_scope}


def _checkpoint_payload(
    *,
    checkpoint_key: str,
    title: str,
    desc: str,
    phase: str,
    workflow_step_id: int,
    workflow_step_title: str,
    recommended_action: str,
    risk_level: str = "medium",
    impact_scope: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "checkpoint_key": checkpoint_key,
        "title": title,
        "desc": desc,
        "phase": phase,
        "risk_level": risk_level,
        "impact_scope": impact_scope or [],
        "recommended_action": recommended_action,
        "blocking": True,
        "workflow_step_id": workflow_step_id,
        "workflow_step_title": workflow_step_title,
    }


async def _handle_checkpoint(
    state: OptimizationState,
    hooks: AgentRuntimeHooks,
    *,
    checkpoint_key: str,
    title: str,
    desc: str,
    phase: str,
    workflow_step_id: int,
    workflow_step_title: str,
    recommended_action: str,
    approved_next: str,
    rejection_message: str,
    risk_level: str = "medium",
    impact_scope: Optional[List[str]] = None,
) -> Dict[str, Any]:
    decisions = dict(state.get("human_decisions") or {})
    if state.get("auto_confirm"):
        decision = "yes"
    else:
        decision = decisions.get(checkpoint_key)
        if decision is None:
            payload = _checkpoint_payload(
                checkpoint_key=checkpoint_key,
                title=title,
                desc=desc,
                phase=phase,
                workflow_step_id=workflow_step_id,
                workflow_step_title=workflow_step_title,
                recommended_action=recommended_action,
                risk_level=risk_level,
                impact_scope=impact_scope,
            )
            await hooks.checkpoint(payload)
            return {"pending_checkpoint": payload, "resume_node": state.get("current_node"), "next_node": "END"}
    record = {
        "id": str(int(datetime.now().timestamp() * 1000)),
        "title": title,
        "checkpoint_key": checkpoint_key,
        "workflow_step_id": workflow_step_id,
        "workflow_step_title": workflow_step_title,
        "risk_level": risk_level,
        "recommended_action": recommended_action,
        "blocking": True,
        "response": decision,
        "timestamp": _now(),
    }
    if str(decision).lower() == "yes":
        return {
            "pending_checkpoint": None,
            "resume_node": "",
            "interaction_records": _append_record(state, "interaction_records", record),
            "next_node": approved_next,
        }
    return {
        "pending_checkpoint": None,
        "resume_node": "",
        "cancelled": True,
        "cancel_message": rejection_message,
        "interaction_records": _append_record(state, "interaction_records", record),
        "next_node": "END",
    }


async def _emit_llm(
    state: OptimizationState,
    hooks: AgentRuntimeHooks,
    *,
    task_key: str,
    task_label: str,
    status: str,
    workflow_step_id: int,
) -> List[Dict[str, Any]]:
    event = {
        "event_id": f"llm-{int(datetime.now().timestamp() * 1000)}-{task_key}-{status}",
        "task_key": task_key,
        "task_label": task_label,
        "status": status,
        "phase": "analysis",
        "provider": "dify" if "retrieval" in task_key else "direct",
        "model": (
            (state.get("dify_config") or {}).get("app_name")
            or (state.get("dify_config") or {}).get("api_url")
            or (state.get("llm_config") or {}).get("model")
            or ""
        ),
        "workflow_step_id": workflow_step_id,
        "workflow_step_title": STEP_TITLES.get(workflow_step_id, ""),
        "timestamp": _now(),
    }
    await hooks.llm_activity(event)
    return _append_record(state, "llm_activity_history", event)


def _build_analysis_steps(state: OptimizationState) -> List[Dict[str, Any]]:
    summary = state.get("overall_judgement") or {}
    abnormal_details = state.get("abnormal_details") or []
    features = state.get("features") or {}
    baseline = state.get("baseline_profile") or {}
    quality_gate = state.get("quality_gate") or {}
    knowledge = state.get("knowledge_retrieval") or {}
    decision = state.get("decision_result") or {}
    feature_entries = features.get("per_tag") if isinstance(features, dict) and isinstance(features.get("per_tag"), dict) else features
    trend_counts = dict(Counter(item.get("trend", "unknown") for item in feature_entries.values())) if isinstance(feature_entries, dict) else {}
    top_abnormal_items = sorted(abnormal_details, key=lambda item: abs(float(item.get("diff") or 0.0)), reverse=True)[:5]
    return [
        {"step": 1, "title": STEP_TITLES[1], "summary": f"载入文件 {state.get('display_file_name') or state.get('data_file')}，质量门禁 {quality_gate.get('status', 'UNKNOWN')}。"},
        {"step": 2, "title": STEP_TITLES[2], "summary": f"选取最新时刻 {state.get('latest_timestamp') or '未记录'} 的 {len(state.get('latest_records') or state.get('semantic_data') or [])} 条快照记录。"},
        {"step": 3, "title": STEP_TITLES[3], "summary": f"识别到 {len(abnormal_details)} 个异常候选。"},
        {"step": 4, "title": STEP_TITLES[4], "summary": summary.get("summary", "未生成工况总览判断。")},
        {"step": 5, "title": STEP_TITLES[5], "summary": f"趋势分布为 {trend_counts}，基线覆盖 {baseline.get('tag_count', 0)} 个指标。"},
        {"step": 6, "title": STEP_TITLES[6], "summary": knowledge.get("retrieval_summary", "未返回检索摘要。")},
        {"step": 7, "title": STEP_TITLES[7], "summary": f"优先关注指标：{[item.get('name') for item in top_abnormal_items]}。"},
        {"step": 8, "title": STEP_TITLES[8], "summary": f"验证状态为 {decision.get('verification_status', 'Unknown')}。"},
    ]


def _build_step_traces(state: OptimizationState) -> List[Dict[str, Any]]:
    history = list(state.get("execution_history") or [])
    grouped: Dict[int, Dict[str, Any]] = {}
    for item in history:
        meta = item.get("meta") or {}
        step_id = meta.get("workflow_step_id")
        if not step_id:
            continue
        step_id = int(step_id)
        started_at = item.get("started_at")
        ended_at = item.get("ended_at")
        row = grouped.setdefault(
            step_id,
            {
                "step": step_id,
                "title": meta.get("workflow_step_title") or STEP_TITLES.get(step_id, item.get("node")),
                "started_at": started_at,
                "ended_at": ended_at,
                "processing_summary": item.get("summary") or "",
                "interaction_checkpoint": item.get("pending_checkpoint", {}).get("checkpoint_key", ""),
                "interaction_response": item.get("interaction_response", "未触发"),
                "llm_tasks": [],
            },
        )
        if started_at and (not row.get("started_at") or str(started_at) < str(row.get("started_at"))):
            row["started_at"] = started_at
        if ended_at and (not row.get("ended_at") or str(ended_at) > str(row.get("ended_at"))):
            row["ended_at"] = ended_at
        if item.get("summary"):
            row["processing_summary"] = item.get("summary")
        checkpoint_key = item.get("pending_checkpoint", {}).get("checkpoint_key", "")
        if checkpoint_key:
            row["interaction_checkpoint"] = checkpoint_key
        interaction_response = item.get("interaction_response", "未触发")
        if interaction_response != "未触发":
            row["interaction_response"] = interaction_response

    traces: List[Dict[str, Any]] = []
    for step_id in sorted(grouped):
        row = grouped[step_id]
        started_at = row.get("started_at")
        ended_at = row.get("ended_at")
        duration_ms = 1
        if started_at and ended_at:
            try:
                duration_ms = max(
                    1,
                    int((datetime.fromisoformat(str(ended_at)) - datetime.fromisoformat(str(started_at))).total_seconds() * 1000),
                )
            except Exception:
                duration_ms = 1
        row["duration_ms"] = duration_ms
        traces.append(row)
    return traces


def _write_trace_files(task_id: str, traceability: Dict[str, Any], calculation_audit: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    reports_dir = Path(__file__).resolve().parents[3] / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"run_trace_{task_id}_{stamp}"
    raw_path = reports_dir / f"{base}_raw.json"
    summary_path = reports_dir / f"{base}_summary.json"
    timeline_md_path = reports_dir / f"{base}_timeline.md"
    timeline_csv_path = reports_dir / f"{base}_timeline.csv"
    calculation_audit_path = reports_dir / f"{base}_calculation_audit.json"
    raw_path.write_text(json.dumps(traceability, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "task_id": traceability.get("task_id"),
                "generated_at": traceability.get("generated_at"),
                "data_source": traceability.get("data_source"),
                "quality_gate_status": traceability.get("quality_gate_status"),
                "step_count": len(traceability.get("step_traces") or []),
                "interaction_count": len(traceability.get("interactions") or []),
                "calculation_audit_file": str(calculation_audit_path) if calculation_audit else "",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_lines = ["# Run Trace Timeline", ""]
    csv_lines = ["step,title,started_at,ended_at,duration_ms"]
    for step in traceability.get("step_traces") or []:
        md_lines.append(f"- Step {step.get('step')}: {step.get('title')} | {step.get('started_at')} -> {step.get('ended_at')}")
        csv_lines.append(
            f"{step.get('step')},{step.get('title')},{step.get('started_at')},{step.get('ended_at')},{step.get('duration_ms')}"
        )
    timeline_md_path.write_text("\n".join(md_lines), encoding="utf-8")
    timeline_csv_path.write_text("\n".join(csv_lines), encoding="utf-8")
    if calculation_audit:
        calculation_audit_path.write_text(json.dumps(calculation_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "raw": str(raw_path),
        "summary": str(summary_path),
        "timeline_md": str(timeline_md_path),
        "timeline_csv": str(timeline_csv_path),
        "calculation_audit": str(calculation_audit_path) if calculation_audit else "",
    }


def build_nodes(hooks: AgentRuntimeHooks, store: Any) -> Dict[str, Callable[[OptimizationState], Awaitable[Dict[str, Any]]]]:
    async def bootstrap_run(state: OptimizationState) -> Dict[str, Any]:
        await hooks.log(
            f"开始分析流程，流程标签：{state.get('entrypoint', 'agent')}",
            level="info",
            category="system",
        )
        return {"status": "running", "pending_checkpoint": None, "next_node": state.get("resume_node") or "load_data"}

    async def load_data(state: OptimizationState) -> Dict[str, Any]:
        if state.get("use_asu_pipeline"):
            loader = _service(state, "data_loader", lambda: ASUDataLoader())
            data = await asyncio.to_thread(loader.load_asu_data, state.get("data_file"))
            facts = data["facts"].to_dict("records")
            meta = data["meta"].to_dict("records")
            derived = data["derived"].to_dict("records")
            timestamps = [str(item.get("time")) for item in facts if item.get("time")]
            return {
                "asu_facts": facts,
                "asu_meta": meta,
                "asu_derived": derived,
                "timestamps": timestamps,
                "timepoint_count": len(set(timestamps)),
                "sensor_count": len({item.get('tag_code') for item in facts if item.get('tag_code')}),
                "effective_record_count": len(facts),
                "quality_gate": {"status": "SKIPPED", "summary": "ASU 管道未执行 Excel 质量门禁。"},
                "quality_report": data.get("quality") or {},
                "min_timestamp": min(timestamps) if timestamps else None,
                "max_timestamp": max(timestamps) if timestamps else None,
                "next_node": "confirm_data_range",
            }
        loader = _service(state, "data_loader", lambda: ExcelDataLoader(state.get("data_file") or ""))
        load_result = await asyncio.to_thread(loader.load_and_standardize)
        records = load_result["records"]
        quality_gate = load_result.get("quality_gate") or load_result.get("gate") or load_result.get("quality") or {}
        parsing_audit = load_result.get("parsing_audit") or {}
        quality_status = str(quality_gate.get("status") or "UNKNOWN").upper()
        if quality_status == "FAIL":
            raise ValueError("数据质量门禁未通过：有效样本为 0。")
        if not records:
            raise ValueError("数据文件解析后没有有效记录。")
        timestamps = [str(record.get("timestamp")) for record in records if record.get("timestamp")]
        return {
            "raw_records": load_result.get("raw_records") or [],
            "standardized_data": records,
            "timestamps": timestamps,
            "timepoint_count": len(set(timestamps)),
            "sensor_count": len({record.get("tag_id") for record in records if record.get("tag_id")}),
            "effective_record_count": len(records),
            "quality_gate": quality_gate,
            "quality_report": load_result.get("quality") or {},
            "parsing_audit": parsing_audit,
            "min_timestamp": min(timestamps) if timestamps else None,
            "max_timestamp": max(timestamps) if timestamps else None,
            "next_node": "confirm_data_range",
        }

    async def confirm_data_range(state: OptimizationState) -> Dict[str, Any]:
        desc = f"时间范围 {state.get('min_timestamp') or '未识别'} 至 {state.get('max_timestamp') or '未识别'}，共 {state.get('timepoint_count', 0)} 个时间点。是否继续分析？"
        return await _handle_checkpoint(
            state,
            hooks,
            checkpoint_key="init_data_range_confirm",
            title="数据范围确认",
            desc=desc,
            phase="init",
            workflow_step_id=1,
            workflow_step_title=STEP_TITLES[1],
            recommended_action="确认范围并继续",
            approved_next="select_snapshot",
            rejection_message="用户取消了分析任务。",
        )

    async def select_snapshot(state: OptimizationState) -> Dict[str, Any]:
        if state.get("use_asu_pipeline"):
            latest_records = list(state.get("asu_derived") or [])
            latest_timestamp = str(latest_records[-1].get("time")) if latest_records else None
            await hooks.task_progress("数据加载完成", 20.0)
            return {"latest_records": latest_records, "latest_timestamp": latest_timestamp, "next_node": "semantic_analysis"}
        records = list(state.get("standardized_data") or [])
        latest_timestamp = max([record.get("timestamp") for record in records if record.get("timestamp")], default=None)
        latest_records = [record for record in records if record.get("timestamp") == latest_timestamp] if latest_timestamp else records
        await hooks.task_progress("数据加载完成", 20.0)
        return {"latest_records": latest_records, "latest_timestamp": latest_timestamp, "next_node": "semantic_analysis"}

    async def semantic_analysis(state: OptimizationState) -> Dict[str, Any]:
        semantics = _service(state, "semantics_service", lambda: DataSemanticsService())
        if state.get("use_asu_pipeline"):
            semantic_data = await asyncio.to_thread(semantics.process_asu_derived_metrics, state.get("latest_records") or [])
            abnormal_details = [item for item in semantic_data if item.get("state_desc") not in ["正常", "Unknown", "优秀", "良好"]]
            baseline_profile = {"method": "not_available", "tag_count": 0, "per_tag": {}, "history_model_metadata": {}}
            overall_judgement = {
                "summary": f"ASU语义结果 {len(semantic_data)} 条，异常候选 {len(abnormal_details)} 条。",
                "highlights": [],
            }
            core_indicators = None
            semantic_ai_review = {"used": False}
            llm_history = state.get("llm_activity_history") or []
        else:
            all_records = state.get("standardized_data") or []
            latest_records = state.get("latest_records") or []
            await asyncio.to_thread(semantics.update_specs_from_csv_data, all_records)
            semantic_data = await asyncio.to_thread(semantics.process, latest_records)
            if hasattr(semantics, "build_baseline_profile"):
                baseline_profile = await asyncio.to_thread(semantics.build_baseline_profile, all_records)
            else:
                baseline_profile = {"method": "not_available", "tag_count": 0, "per_tag": {}, "history_model_metadata": {}}
            if hasattr(semantics, "build_abnormal_details"):
                try:
                    abnormal_details = await asyncio.to_thread(
                        semantics.build_abnormal_details,
                        all_records,
                        semantic_data,
                        baseline_profile,
                    )
                except TypeError:
                    abnormal_details = await asyncio.to_thread(semantics.build_abnormal_details, all_records, semantic_data)
            else:
                abnormal_details = [item for item in semantic_data if is_abnormal_state(item.get("state_desc", ""))]
            if hasattr(semantics, "build_overall_operating_summary"):
                overall_judgement = await asyncio.to_thread(
                    semantics.build_overall_operating_summary,
                    semantic_data,
                    abnormal_details,
                    baseline_profile,
                    all_records,
                    state.get("parsing_audit") or {},
                )
            else:
                overall_judgement = {
                    "summary": f"快照语义结果 {len(semantic_data)} 条，异常候选 {len(abnormal_details)} 条。",
                    "highlights": [],
                }
            if hasattr(semantics, "calculate_core_indicators"):
                core_indicators = await asyncio.to_thread(semantics.calculate_core_indicators, semantic_data)
            else:
                core_indicators = None
            semantic_ai_review = {"used": False}
            llm_history = state.get("llm_activity_history") or []
            if _has_llm_config(state) and hasattr(semantics, "apply_ai_assistance"):
                engine = _service(state, "reasoning_engine", lambda: ReasoningEngineV2(llm_config=state.get("llm_config") or {}))
                if hasattr(engine, "ask_assistant"):
                    llm_history = await _emit_llm(
                        state,
                        hooks,
                        task_key="semantic_ai_review",
                        task_label="语义AI复核",
                        status="started",
                        workflow_step_id=3,
                    )
                    def ask_ai(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
                        return engine.ask_assistant(user_prompt=user_prompt, system_prompt=system_prompt, temperature=temperature)
                    try:
                        semantic_ai_review = await asyncio.to_thread(
                            semantics.apply_ai_assistance,
                            semantic_data,
                            abnormal_details,
                            overall_judgement,
                            ask_ai,
                            state.get("task_note", ""),
                        )
                    except Exception as exc:
                        semantic_ai_review = {"used": False, "error": str(exc)}
                    llm_history = llm_history + await _emit_llm(
                        {**state, "llm_activity_history": llm_history},
                        hooks,
                        task_key="semantic_ai_review",
                        task_label="语义AI复核",
                        status="completed" if semantic_ai_review.get("used") else "failed",
                        workflow_step_id=3,
                    )
        abnormal_count = len(abnormal_details)
        plant_state = str((overall_judgement or {}).get("plant_state") or "").strip().lower()
        should_run_reasoning = abnormal_count > 0 or plant_state in HEALTHY_PLANT_STATES
        data_overview = _build_data_overview(state)
        semantic_summary = _build_semantic_summary(
            state,
            semantic_data,
            abnormal_details,
            overall_judgement=overall_judgement,
        )
        visualization_service = _service(state, "visualization_service", lambda: TimeComparisonVisualizationService())
        visualization_context: Dict[str, Any] = {}
        if visualization_service is not None and hasattr(visualization_service, "build_visualization_context"):
            visualization_context = await asyncio.to_thread(
                visualization_service.build_visualization_context,
                standardized_data=state.get("standardized_data") or [],
                latest_timestamp=state.get("latest_timestamp"),
                abnormal_details=abnormal_details,
                baseline_profile=baseline_profile or {},
                asset_dir=None,
                asset_prefix="",
            )
        await hooks.monitor_update(
            semantic_data,
            abnormal_details,
            "semantic_ready",
            visualization_context=visualization_context,
            overall_judgement=overall_judgement,
            semantic_summary=semantic_summary,
            data_overview=data_overview,
        )
        return {
            "semantic_data": semantic_data,
            "baseline_profile": baseline_profile,
            "history_model_metadata": (overall_judgement or {}).get("history_model_metadata") or (baseline_profile or {}).get("history_model_metadata") or {},
            "abnormal_details": abnormal_details,
            "overall_judgement": overall_judgement,
            "calculation_audit": (overall_judgement or {}).get("calculation_audit") or {},
            "data_overview": data_overview,
            "semantic_summary": semantic_summary,
            "visualization_context": visualization_context,
            "core_indicators": _to_dict(core_indicators),
            "semantic_ai_review": semantic_ai_review,
            "should_run_reasoning": should_run_reasoning,
            "llm_activity_history": llm_history,
            "next_node": "confirm_overview",
        }

    async def confirm_overview(state: OptimizationState) -> Dict[str, Any]:
        overall = state.get("overall_judgement") or {}
        highlights = overall.get("highlights") or []
        desc_lines = [f"总体判断：{overall.get('summary') or '暂无总体判断。'}"]
        if highlights:
            desc_lines.append("关键要点：")
            desc_lines.extend(f"- {item}" for item in highlights[:3])
        desc_lines.append("")
        desc_lines.append("是否继续进入异常候选复核？")
        return await _handle_checkpoint(
            state,
            hooks,
            checkpoint_key="analysis_overview_confirm",
            title="工况总览确认",
            desc="\n".join(desc_lines),
            phase="analysis",
            workflow_step_id=4,
            workflow_step_title=STEP_TITLES[4],
            recommended_action="继续异常复核",
            approved_next="extract_features",
            rejection_message="用户在工况总览确认阶段停止任务。",
        )

    async def extract_features(state: OptimizationState) -> Dict[str, Any]:
        semantics = _service(state, "semantics_service", lambda: DataSemanticsService())
        if state.get("use_asu_pipeline"):
            features = {}
        elif hasattr(semantics, "extract_features"):
            features = await asyncio.to_thread(semantics.extract_features, state.get("standardized_data") or [])
        else:
            features = {}
        await hooks.task_progress("规则预筛与特征复核完成", 35.0)
        return {"features": features, "next_node": "confirm_candidates"}

    async def confirm_candidates(state: OptimizationState) -> Dict[str, Any]:
        abnormal_details = state.get("abnormal_details") or []
        if abnormal_details:
            abnormal_names = ", ".join(item.get("name", "") for item in abnormal_details[:3] if item.get("name"))
            if len(abnormal_details) > 3:
                abnormal_names += " 等"
            desc = f"规则预筛发现候选异常：{abnormal_names}。是否继续由 AI 进行诊断与复核？"
        else:
            desc = "规则预筛未发现明显异常，是否继续由 AI 做整体诊断校验？"
        approved_next = "primary_retrieval" if state.get("should_run_reasoning") else "generate_report"
        return await _handle_checkpoint(
            state,
            hooks,
            checkpoint_key="analysis_candidate_confirm",
            title="异常候选确认",
            desc=desc,
            phase="analysis",
            workflow_step_id=5,
            workflow_step_title=STEP_TITLES[5],
            recommended_action="继续 AI 诊断",
            approved_next=approved_next,
            rejection_message="用户中止了分析任务。",
            impact_scope=[item.get("name") or item.get("tag_id") for item in abnormal_details[:4] if item.get("name") or item.get("tag_id")],
        )

    async def primary_retrieval(state: OptimizationState) -> Dict[str, Any]:
        dify_config = dict(state.get("dify_config") or {})
        if not dify_config.get("api_key"):
            primary = {
                "retrieval_summary": "知识库 API 检索未执行：缺少 DIFY_API_KEY 配置。",
                "recommended_measures": [],
                "knowledge_references": [],
                "risk_tips": ["请先配置知识库 API 凭证。"],
                "raw_response": "",
            }
            return {"primary_retrieval": primary, "knowledge_retrieval": dict(primary), "next_node": "confirm_high_risk"}
        retrieval_history = await _emit_llm(
            state,
            hooks,
            task_key="dify_retrieval",
            task_label="知识检索",
            status="started",
            workflow_step_id=6,
        )
        service = KnowledgeRetrievalService(dify_config)
        try:
            primary = await asyncio.to_thread(
                service.retrieve_measures,
                state.get("overall_judgement") or {},
                state.get("abnormal_details") or [],
                state.get("task_note") or "",
                "primary",
                "",
            )
            retrieval_history = retrieval_history + await _emit_llm(
                {**state, "llm_activity_history": retrieval_history},
                hooks,
                task_key="dify_retrieval",
                task_label="知识检索",
                status="completed",
                workflow_step_id=6,
            )
        except Exception as exc:
            primary = {
                "retrieval_summary": f"知识库 API 检索失败，已降级继续后续诊断。原因：{exc}",
                "recommended_measures": [],
                "knowledge_references": [],
                "risk_tips": [f"知识库 API 检索失败：{exc}"],
                "raw_response": "",
                "retrieval_status": "failed",
                "error": str(exc),
            }
            retrieval_history = retrieval_history + await _emit_llm(
                {**state, "llm_activity_history": retrieval_history},
                hooks,
                task_key="dify_retrieval",
                task_label="知识检索",
                status="failed",
                workflow_step_id=6,
            )
        return {
            "primary_retrieval": primary,
            "knowledge_retrieval": dict(primary),
            "llm_activity_history": retrieval_history,
            "next_node": "confirm_high_risk",
        }

    async def confirm_high_risk(state: OptimizationState) -> Dict[str, Any]:
        high_risk = _detect_high_risk_candidates(state.get("abnormal_details") or [])
        if not high_risk.get("triggered"):
            return {"next_node": "reasoning"}
        desc = (
            f"检测到 {high_risk['risk_level']} 风险候选，影响范围："
            f"{', '.join(high_risk['impact_scope']) or '未识别'}。是否继续 AI 深度诊断？"
        )
        return await _handle_checkpoint(
            state,
            hooks,
            checkpoint_key="analysis_high_risk_confirm",
            title="高风险附加确认",
            desc=desc,
            phase="analysis",
            workflow_step_id=7,
            workflow_step_title=STEP_TITLES[7],
            recommended_action="继续高风险复核",
            approved_next="reasoning",
            rejection_message="用户在高风险追加确认阶段停止任务。",
            risk_level=high_risk["risk_level"],
            impact_scope=high_risk["impact_scope"],
        )

    async def reasoning(state: OptimizationState) -> Dict[str, Any]:
        engine = _service(state, "reasoning_engine", lambda: ReasoningEngineV2(llm_config=state.get("llm_config") or {}))
        llm_history = await _emit_llm(
            state,
            hooks,
            task_key="root_cause_diagnosis",
            task_label="根因诊断",
            status="started",
            workflow_step_id=7,
        )
        reasoning_json = await asyncio.to_thread(
            engine.analyze,
            semantic_data=state.get("semantic_data") or [],
            core_indicators=state.get("core_indicators"),
            enable_cot=state.get("enable_cot", True),
            features=state.get("features") or {},
            task_note=state.get("task_note") or "",
            abnormal_items=state.get("abnormal_details") or [],
            knowledge_context=state.get("knowledge_retrieval") or {},
            overall_judgement=state.get("overall_judgement") or {},
        )
        reasoning_payload = json.loads(reasoning_json) if isinstance(reasoning_json, str) else dict(reasoning_json or {})
        validated = validate_reasoning_result(reasoning_payload)
        reasoning_result = model_to_dict(validated)
        abnormal_details = _merge_ai_indicator_reasons(state.get("abnormal_details") or [], reasoning_result)
        llm_history = llm_history + await _emit_llm(
            {**state, "llm_activity_history": llm_history},
            hooks,
            task_key="root_cause_diagnosis",
            task_label="根因诊断",
            status="completed",
            workflow_step_id=7,
        )
        return {
            "reasoning_result": reasoning_result,
            "abnormal_details": abnormal_details,
            "llm_activity_history": llm_history,
            "next_node": "review_retrieval",
        }

    async def review_retrieval(state: OptimizationState) -> Dict[str, Any]:
        dify_config = dict(state.get("dify_config") or {})
        review_history = list(state.get("llm_activity_history") or [])
        if not dify_config.get("api_key"):
            review = {
                "retrieval_summary": "知识库 API 校核检索未执行：缺少 DIFY_API_KEY 配置。",
                "recommended_measures": [],
                "knowledge_references": [],
                "risk_tips": ["请先配置知识库 API 凭证。"],
                "raw_response": "",
            }
        else:
            review_history = review_history + await _emit_llm(
                state,
                hooks,
                task_key="dify_retrieval_review",
                task_label="知识校核检索",
                status="started",
                workflow_step_id=7,
            )
            service = KnowledgeRetrievalService(dify_config)
            try:
                review = await asyncio.to_thread(
                    service.retrieve_measures,
                    state.get("overall_judgement") or {},
                    state.get("abnormal_details") or [],
                    state.get("task_note") or "",
                    "review",
                    str((state.get("reasoning_result") or {}).get("operation_suggestion") or ""),
                )
                review_history = review_history + await _emit_llm(
                    {**state, "llm_activity_history": review_history},
                    hooks,
                    task_key="dify_retrieval_review",
                    task_label="知识校核检索",
                    status="completed",
                    workflow_step_id=7,
                )
            except Exception as exc:
                review = {
                    "retrieval_summary": f"知识库 API 校核检索失败：{exc}",
                    "recommended_measures": [],
                    "knowledge_references": [],
                    "risk_tips": [f"知识库 API 校核检索失败：{exc}"],
                    "raw_response": "",
                    "retrieval_status": "failed",
                    "error": str(exc),
                }
                review_history = review_history + await _emit_llm(
                    {**state, "llm_activity_history": review_history},
                    hooks,
                    task_key="dify_retrieval_review",
                    task_label="知识校核检索",
                    status="failed",
                    workflow_step_id=7,
                )
        return {
            "review_retrieval": review,
            "knowledge_retrieval": _merge_knowledge_retrieval(state.get("primary_retrieval") or {}, review),
            "llm_activity_history": review_history,
            "next_node": "decision",
        }

    async def decision(state: OptimizationState) -> Dict[str, Any]:
        service = _service(state, "decision_service", lambda: DecisionService())
        ask_model = None
        if _has_llm_config(state):
            engine = _service(state, "reasoning_engine", lambda: ReasoningEngineV2(llm_config=state.get("llm_config") or {}))
            if hasattr(engine, "ask_assistant"):
                ask_model = lambda system_prompt, user_prompt, temperature=0.1: engine.ask_assistant(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )
        verify_signature = inspect.signature(service.verify_and_suggest)
        if "reasoning_result" in verify_signature.parameters:
            decision_payload = await asyncio.to_thread(
                service.verify_and_suggest,
                reasoning_result=state.get("reasoning_result") or {},
                ask_model=ask_model,
                knowledge_context=state.get("knowledge_retrieval") or {},
                overall_judgement=state.get("overall_judgement") or {},
                task_note=state.get("task_note") or "",
                execution_feedback=state.get("execution_feedback") or {},
                enable_closed_loop_validation=bool(state.get("enable_closed_loop_validation")),
            )
        else:
            decision_payload = await asyncio.to_thread(
                service.verify_and_suggest,
                state.get("reasoning_result") or {},
                ask_model=ask_model,
                knowledge_context=state.get("knowledge_retrieval") or {},
                overall_judgement=state.get("overall_judgement") or {},
                task_note=state.get("task_note") or "",
                execution_feedback=state.get("execution_feedback") or {},
                enable_closed_loop_validation=bool(state.get("enable_closed_loop_validation")),
            )
        validated = validate_decision_result(decision_payload)
        decision_result = model_to_dict(validated)
        await hooks.monitor_update(
            state.get("semantic_data") or [],
            state.get("abnormal_details") or [],
            "decision_ready",
            visualization_context=state.get("visualization_context") or {},
            overall_judgement=state.get("overall_judgement") or {},
            semantic_summary=state.get("semantic_summary") or {},
            data_overview=state.get("data_overview") or {},
        )
        await hooks.task_progress("AI 推理完成", 70.0)
        return {"decision_result": decision_result, "next_node": "generate_report"}

    async def generate_report(state: OptimizationState) -> Dict[str, Any]:
        abnormal_details = state.get("abnormal_details") or []
        semantic_data = state.get("semantic_data") or []
        state_counts = dict(Counter(item.get("state_desc", "Unknown") for item in semantic_data))
        feature_values = state.get("features") or {}
        trend_counts = dict(Counter(item.get("trend", "unknown") for item in feature_values.values())) if isinstance(feature_values, dict) else {}
        data_overview = {
            "file_name": state.get("display_file_name") or Path(state.get("data_file") or "").name,
            "timepoint_count": state.get("timepoint_count", 0),
            "sensor_count": state.get("sensor_count", 0),
            "effective_record_count": state.get("effective_record_count", 0),
            "time_range_start": str(state.get("min_timestamp") or ""),
            "time_range_end": str(state.get("max_timestamp") or ""),
            "latest_timestamp": str(state.get("latest_timestamp") or ""),
            "latest_record_count": len(state.get("latest_records") or []),
            "task_note": state.get("task_note") or "",
            "quality_gate_status": (state.get("quality_gate") or {}).get("status", "UNKNOWN"),
        }
        semantic_summary = {
            "state_counts": state_counts,
            "trend_counts": trend_counts,
            "top_abnormal_names": [item.get("name") for item in abnormal_details[:5]],
            "plant_state": (state.get("overall_judgement") or {}).get("plant_state"),
            "plant_state_label": (state.get("overall_judgement") or {}).get("plant_state_label"),
            "optimization_priority": (state.get("overall_judgement") or {}).get("optimization_priority") or [],
        }
        traceability = {
            "task_id": state.get("task_id"),
            "session_id": state.get("session_id"),
            "mode": state.get("entrypoint"),
            "data_source": state.get("data_source", "sample"),
            "llm_provider": "direct",
            "llm_model": (state.get("llm_config") or {}).get("model", ""),
            "retrieval_provider": "external_knowledge_api",
            "retrieval_model": (state.get("dify_config") or {}).get("app_name") or (state.get("dify_config") or {}).get("api_url") or "dify",
            "quality_gate_status": (state.get("quality_gate") or {}).get("status", "UNKNOWN"),
            "baseline_tag_count": (state.get("baseline_profile") or {}).get("tag_count", 0),
            "history_model_metadata": state.get("history_model_metadata") or (state.get("baseline_profile") or {}).get("history_model_metadata") or {},
            "generated_at": _now(),
            "interactions": state.get("interaction_records") or [],
            "step_traces": _build_step_traces(state),
        }
        traceability["trace_files"] = _write_trace_files(
            state.get("task_id") or "unknown",
            traceability,
            calculation_audit=state.get("calculation_audit") or (state.get("overall_judgement") or {}).get("calculation_audit") or {},
        )
        report_generator = _service(state, "report_generator", lambda: ReportGenerator())
        report_base_filename = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        visualization_service = _service(state, "visualization_service", lambda: TimeComparisonVisualizationService())
        visualization_context: Dict[str, Any] = {}
        if visualization_service is not None and hasattr(visualization_service, "build_visualization_context"):
            report_output_dir = Path(getattr(report_generator, "output_dir", "reports"))
            asset_dir = report_output_dir / "assets" / report_base_filename
            visualization_context = await asyncio.to_thread(
                visualization_service.build_visualization_context,
                standardized_data=state.get("standardized_data") or [],
                latest_timestamp=state.get("latest_timestamp"),
                abnormal_details=abnormal_details,
                baseline_profile=state.get("baseline_profile") or {},
                asset_dir=asset_dir,
                asset_prefix=f"assets/{report_base_filename}",
            )

        analysis_result = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "abnormal" if abnormal_details else "healthy",
            "abnormal_count": len(abnormal_details),
            "semantic_data": semantic_data,
            "core_indicators": state.get("core_indicators"),
            "quality_gate": state.get("quality_gate") or {},
            "baseline_profile": state.get("baseline_profile") or {},
            "history_model_metadata": state.get("history_model_metadata") or (state.get("baseline_profile") or {}).get("history_model_metadata") or {},
            "abnormal_details": abnormal_details,
            "overall_judgement": state.get("overall_judgement") or {},
            "calculation_audit": state.get("calculation_audit") or (state.get("overall_judgement") or {}).get("calculation_audit") or {},
            "knowledge_retrieval": state.get("knowledge_retrieval") or {},
            "reasoning_result": state.get("reasoning_result"),
            "decision_result": state.get("decision_result"),
            "optimization_context": {
                "workflow_goal": "整体优化（含异常处理）",
                "quality_gate_status": (state.get("quality_gate") or {}).get("status", "UNKNOWN"),
                "baseline_tag_count": (state.get("baseline_profile") or {}).get("tag_count", 0),
                "plant_state": (state.get("overall_judgement") or {}).get("plant_state", "unknown"),
                "history_model_metadata": state.get("history_model_metadata") or (state.get("baseline_profile") or {}).get("history_model_metadata") or {},
                "knowledge_retrieval_used": bool(state.get("knowledge_retrieval")),
            },
            "visualization_context": visualization_context,
            "data_overview": data_overview,
            "analysis_steps": _build_analysis_steps(state),
            "semantic_summary": semantic_summary,
            "semantic_ai_review": state.get("semantic_ai_review") or {"used": False},
            "traceability": traceability,
        }
        pdf_path = None
        md_path = None
        if report_generator is not None and hasattr(report_generator, "generate_both_formats"):
            pdf_path, md_path = await asyncio.to_thread(report_generator.generate_both_formats, analysis_result, report_base_filename)
        analysis_result["report_pdf"] = str(pdf_path) if pdf_path else None
        analysis_result["report_md"] = str(md_path) if md_path else None
        return {
            "analysis_steps": analysis_result["analysis_steps"],
            "data_overview": data_overview,
            "semantic_summary": semantic_summary,
            "traceability": traceability,
            "calculation_audit": analysis_result["calculation_audit"],
            "history_model_metadata": analysis_result["history_model_metadata"],
            "report_pdf": str(pdf_path) if pdf_path else None,
            "report_md": str(md_path) if md_path else None,
            "visualization_context": visualization_context,
            "analysis_result": analysis_result,
            "next_node": "finalize_success",
        }

    async def finalize_success(state: OptimizationState) -> Dict[str, Any]:
        return {"status": "completed", "pending_checkpoint": None, "next_node": "END"}

    async def finalize_error(state: OptimizationState) -> Dict[str, Any]:
        return {
            "analysis_result": {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "error",
                "error": state.get("error") or "Unknown error",
                "abnormal_count": 0,
                "semantic_data": state.get("semantic_data") or [],
                "reasoning_result": state.get("reasoning_result"),
                "decision_result": state.get("decision_result"),
                "quality_gate": state.get("quality_gate") or {},
                "baseline_profile": state.get("baseline_profile") or {},
                "overall_judgement": state.get("overall_judgement") or {},
            },
            "status": "error",
            "next_node": "END",
        }

    node_impls = {
        "bootstrap_run": bootstrap_run,
        "load_data": load_data,
        "confirm_data_range": confirm_data_range,
        "select_snapshot": select_snapshot,
        "semantic_analysis": semantic_analysis,
        "confirm_overview": confirm_overview,
        "extract_features": extract_features,
        "confirm_candidates": confirm_candidates,
        "primary_retrieval": primary_retrieval,
        "confirm_high_risk": confirm_high_risk,
        "reasoning": reasoning,
        "review_retrieval": review_retrieval,
        "decision": decision,
        "generate_report": generate_report,
        "finalize_success": finalize_success,
        "finalize_error": finalize_error,
    }

    def safe_node(name: str, func: Callable[[OptimizationState], Awaitable[Dict[str, Any]]]) -> Callable[[OptimizationState], Awaitable[Dict[str, Any]]]:
        async def wrapped(state: OptimizationState) -> Dict[str, Any]:
            meta = NODE_META.get(name, {})
            started_at = _now()
            working_state = dict(state)
            working_state["current_node"] = name
            if meta.get("phase"):
                await hooks.phase_update(
                    phase=meta["phase"],
                    status="running",
                    step=meta.get("step"),
                    workflow_step_id=meta.get("workflow_step_id"),
                    workflow_step_title=meta.get("workflow_step_title"),
                    workflow_step_state="started",
                    step_started_at=started_at,
                )
            try:
                updates = await func(working_state)
            except Exception as exc:
                updates = {
                    "error": str(exc),
                    "error_code": exc.__class__.__name__,
                    "next_node": "finalize_error",
                }
            ended_at = _now()
            event = {
                "node": name,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": max(1, int((datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds() * 1000)),
                "summary": updates.get("error") or f"{name} completed",
                "meta": meta,
                "pending_checkpoint": updates.get("pending_checkpoint") or {},
                "interaction_response": (
                    (updates.get("interaction_records") or [{}])[-1].get("response", "未触发")
                    if updates.get("interaction_records")
                    else "未触发"
                ),
            }
            merged = dict(working_state)
            merged.update(updates)
            merged["current_node"] = name
            merged["execution_history"] = _append_record(state, "execution_history", event)
            if meta.get("phase") and not updates.get("pending_checkpoint") and not updates.get("error") and not updates.get("cancelled"):
                await hooks.phase_update(
                    phase=meta["phase"],
                    status="completed" if name in {"finalize_success", "generate_report"} and meta["phase"] == "report" else "running",
                    step=meta.get("step"),
                    workflow_step_id=meta.get("workflow_step_id"),
                    workflow_step_title=meta.get("workflow_step_title"),
                    workflow_step_state="completed",
                    step_started_at=started_at,
                )
            if merged.get("task_id"):
                path = store.save_snapshot(merged["task_id"], merged)
                await hooks.state_saved(merged["task_id"], path, merged.get("pending_checkpoint"))
            return merged
        return wrapped

    return {name: safe_node(name, func) for name, func in node_impls.items()}
