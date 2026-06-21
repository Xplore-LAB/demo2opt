"""
Interactive CLI entrypoint for running the optimizer without the web UI.
"""

import glob
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.services.data_loader import ASUDataLoader, ExcelDataLoader
from src.services.data_semantics import DataSemanticsService
from src.services.decision_service import DecisionService
from src.services.knowledge_retrieval_service import KnowledgeRetrievalService
from src.services.reasoning_engine_v2 import ReasoningEngineV2
from src.services.visualization_service import TimeComparisonVisualizationService
from src.utils.report_generator import ReportGenerator


def _verification_status_text(status: str) -> str:
    mapping = {"Passed": "通过", "Pending": "待确认", "Failed": "失败"}
    return mapping.get(str(status or "").strip(), str(status or "未知"))


def _trend_label(trend: str) -> str:
    mapping = {
        "increasing": "上升",
        "decreasing": "下降",
        "stable": "稳定",
        "unknown": "未知",
    }
    text = str(trend or "").strip().lower()
    return mapping.get(text, str(trend or "未知"))


def _analysis_step_summary(step_traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "step": item.get("step"),
            "title": item.get("title"),
            "summary": item.get("output_summary"),
        }
        for item in sorted(step_traces, key=lambda x: int(x.get("step") or 0))
    ]


def _ensure_full_steps(step_traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    defaults = {
        1: "数据加载与范围确认",
        2: "最新时刻快照提取",
        3: "规则预筛与语义复核",
        4: "工况总览判断",
        5: "时序特征提取与候选复核",
        6: "知识检索与候选措施整理",
        7: "AI 根因诊断",
        8: "决策验证与报告生成",
    }
    by_step = {int(item.get("step")): item for item in step_traces if str(item.get("step", "")).isdigit()}
    fixed: List[Dict[str, Any]] = []
    for step in range(1, 9):
        row = by_step.get(step) or {}
        fixed.append(
            {
                "step": step,
                "title": row.get("title") or defaults[step],
                "started_at": row.get("started_at") or "未记录（模板占位）",
                "ended_at": row.get("ended_at") or "未记录（模板占位）",
                "duration_ms": max(1, int(row.get("duration_ms") or 1)),
                "input_summary": row.get("input_summary") or "未记录（模板占位）",
                "processing_summary": row.get("processing_summary") or "未记录（模板占位）",
                "output_summary": row.get("output_summary") or "未记录（模板占位）",
                "manual_verification": row.get("manual_verification") or "未记录（模板占位）",
                "interaction_checkpoint": row.get("interaction_checkpoint") or "",
                "interaction_response": row.get("interaction_response") or "未触发",
                "llm_tasks": row.get("llm_tasks") if isinstance(row.get("llm_tasks"), list) else [],
            }
        )
    return fixed


def _build_retrieval_config() -> Dict[str, Any]:
    return {
        "api_url": os.getenv("DIFY_DATASETS_API_URL") or os.getenv("DIFY_API_URL", "http://localhost/v1"),
        "api_key": os.getenv("DIFY_API_KEY", ""),
        "api_mode": os.getenv("DIFY_RETRIEVAL_API_MODE", "datasets_retrieve"),
        "dataset_id": os.getenv("DIFY_DATASET_ID", ""),
        "keyword": os.getenv("DIFY_DATASETS_KEYWORD", ""),
        "tag_ids": os.getenv("DIFY_DATASETS_TAG_IDS", ""),
        "page": os.getenv("DIFY_DATASETS_PAGE", "1"),
        "limit": os.getenv("DIFY_DATASETS_LIMIT", "20"),
        "include_all": os.getenv("DIFY_DATASETS_INCLUDE_ALL", "false"),
        "top_k": os.getenv("DIFY_RETRIEVE_TOP_K", "5"),
        "search_method": os.getenv("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search"),
        "reranking_enable": os.getenv("DIFY_RETRIEVE_RERANKING_ENABLE", "false"),
        "score_threshold": os.getenv("DIFY_RETRIEVE_SCORE_THRESHOLD", "0"),
        "response_mode": os.getenv("DIFY_RESPONSE_MODE", "blocking"),
        "timeout_sec": os.getenv("LLM_TIMEOUT_SEC", ""),
    }


def _run_knowledge_retrieval(
    *,
    overall_judgement: Dict[str, Any],
    abnormal_details: List[Dict[str, Any]],
    task_note: str,
    retrieval_stage: str = "primary",
    draft_suggestion: str = "",
) -> Dict[str, Any]:
    dify_config = _build_retrieval_config()
    if not dify_config.get("api_key"):
        return {
            "retrieval_summary": "Dify 检索未执行：缺少 DIFY_API_KEY 配置。",
            "recommended_measures": [],
            "knowledge_references": [],
            "risk_tips": ["请先配置 Dify 检索凭证。"],
            "raw_response": "",
        }
    try:
        service = KnowledgeRetrievalService(dify_config)
        return service.retrieve_measures(
            overall_judgement=overall_judgement or {},
            abnormal_details=abnormal_details or [],
            task_note=task_note or "",
            retrieval_stage=retrieval_stage,
            draft_suggestion=draft_suggestion,
        )
    except Exception as exc:
        return {
            "retrieval_summary": f"Dify 检索失败，已降级继续：{exc}",
            "recommended_measures": [],
            "knowledge_references": [],
            "risk_tips": [f"检索失败：{exc}"],
            "raw_response": "",
        }


def _merge_knowledge_retrieval(primary: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    primary = primary or {}
    review = review or {}

    def _dedupe(items: List[Any]) -> List[Any]:
        seen = set()
        output: List[Any] = []
        for item in items or []:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    primary_summary = str(primary.get("retrieval_summary") or "").strip()
    review_summary = str(review.get("retrieval_summary") or "").strip()
    summary = " | ".join(
        text
        for text in [
            f"主检索：{primary_summary}" if primary_summary else "",
            f"校核检索：{review_summary}" if review_summary else "",
        ]
        if text
    ) or "知识检索未返回有效摘要。"

    return {
        "retrieval_stage": "dual",
        "retrieval_summary": summary,
        "recommended_measures": _dedupe((primary.get("recommended_measures") or []) + (review.get("recommended_measures") or [])),
        "knowledge_references": _dedupe((primary.get("knowledge_references") or []) + (review.get("knowledge_references") or [])),
        "risk_tips": _dedupe((primary.get("risk_tips") or []) + (review.get("risk_tips") or [])),
        "primary_retrieval": primary,
        "review_retrieval": review,
        "raw_response": "\n---primary---\n"
        + str(primary.get("raw_response") or "")
        + "\n---review---\n"
        + str(review.get("raw_response") or ""),
    }


def simulate_user_operation(
    data_file: str = None,
    use_asu_pipeline: bool = False,
    enable_cot: bool = True,
    execution_feedback: Optional[Dict[str, Any]] = None,
):
    print("\n" + "=" * 70)
    print("工业空分装置智能优化系统 - 交互式演示")
    print("=" * 70)
    print("流程: 统一流程（直连LLM推理 + Dify知识检索）")
    print(f"数据文件: {data_file}")

    data_loader = ASUDataLoader() if use_asu_pipeline else ExcelDataLoader(data_file)
    reasoning_engine = ReasoningEngineV2()
    semantics_service = DataSemanticsService()
    decision_service = DecisionService()
    report_generator = ReportGenerator()
    visualization_service = TimeComparisonVisualizationService()
    report_output_dir = Path(getattr(report_generator, "output_dir", "reports"))
    quality_gate: Dict[str, Any] = {
        "status": "SKIPPED",
        "summary": "ASU 管道入口未执行 Excel 质量门禁。",
    }
    parsing_audit: Dict[str, Any] = {}
    baseline_profile: Dict[str, Any] = {
        "method": "not_available",
        "tag_count": 0,
        "per_tag": {},
    }
    knowledge_retrieval_primary: Dict[str, Any] = {
        "retrieval_summary": "主检索未执行。",
        "recommended_measures": [],
        "knowledge_references": [],
        "risk_tips": [],
        "raw_response": "",
    }
    knowledge_retrieval_review: Dict[str, Any] = {
        "retrieval_summary": "校核检索未执行。",
        "recommended_measures": [],
        "knowledge_references": [],
        "risk_tips": [],
        "raw_response": "",
    }
    knowledge_retrieval: Dict[str, Any] = _merge_knowledge_retrieval(
        knowledge_retrieval_primary,
        knowledge_retrieval_review,
    )

    step_started_perf: Dict[int, float] = {}
    step_started_at: Dict[int, str] = {}
    step_traces: List[Dict[str, Any]] = []

    def start_step(step_id: int):
        step_started_perf[step_id] = time.perf_counter()
        step_started_at[step_id] = datetime.now().isoformat()

    def finish_step(
        step_id: int,
        title: str,
        input_summary: str,
        processing_summary: str,
        output_summary: str,
        manual_verification: str,
    ):
        elapsed_ms = max(1, int((time.perf_counter() - step_started_perf.get(step_id, time.perf_counter())) * 1000))
        step_traces.append(
            {
                "step": step_id,
                "title": title,
                "started_at": step_started_at.get(step_id, datetime.now().isoformat()),
                "ended_at": datetime.now().isoformat(),
                "duration_ms": elapsed_ms,
                "input_summary": input_summary,
                "processing_summary": processing_summary,
                "output_summary": output_summary,
                "manual_verification": manual_verification,
                "interaction_checkpoint": "",
                "interaction_response": "未触发",
                "llm_tasks": [],
            }
        )

    def ask_ai(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        return reasoning_engine.ask_assistant(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    if use_asu_pipeline:
        start_step(1)
        asu_data = data_loader.load_asu_data(data_file)
        finish_step(
            1,
            "数据加载与范围确认",
            f"输入文件: {data_file}",
            "加载 ASU 管道数据。",
            f"facts={len(asu_data.get('facts', []))}，derived={len(asu_data.get('derived', []))}",
            "确认 ASU 数据完整性。",
        )

        start_step(2)
        from src.schemas.models import ASUDerivedResultModel, model_to_dict, validate_reasoning_result

        derived_models = []
        for row in asu_data.get("derived", []).to_dict("records"):
            try:
                derived_models.append(ASUDerivedResultModel(**row))
            except Exception:
                continue
        latest_timestamp = "未记录"
        finish_step(
            2,
            "最新时刻快照提取",
            f"衍生指标记录={len(derived_models)}",
            "ASU 管道以衍生指标直接进入语义分析。",
            f"可用衍生指标={len(derived_models)}",
            "确认衍生指标是否满足本次分析需求。",
        )

        start_step(3)
        semantic_data = semantics_service.process_asu_derived_metrics(derived_models)
        abnormal_details = [x for x in semantic_data if x.get("state_desc") not in ["正常", "Unknown", "优秀", "良好"]]
        finish_step(
            3,
            "规则预筛与语义复核",
            f"衍生指标语义结果={len(semantic_data)}",
            "执行 ASU 衍生指标语义映射。",
            f"异常候选={len(abnormal_details)}",
            "抽检异常候选标签是否合理。",
        )

        start_step(4)
        overall_judgement = {
            "summary": f"ASU 管道共输出 {len(semantic_data)} 条语义结果，异常候选 {len(abnormal_details)} 条。",
            "highlights": [],
        }
        try:
            semantic_ai_review = semantics_service.apply_ai_assistance(
                semantic_data=semantic_data,
                abnormal_details=abnormal_details,
                overall_judgement=overall_judgement,
                ask_model=ask_ai,
                task_note="interactive入口自动语义复核",
            )
        except Exception as exc:
            semantic_ai_review = {"used": False, "reason": str(exc)}
        finish_step(
            4,
            "工况总览判断",
            "输入 ASU 语义结果。",
            "汇总 ASU 总览结论，并执行语义 AI 复核增强。",
            overall_judgement["summary"],
            "核验总览结论与现场状态一致。",
        )

        start_step(5)
        trend_counts = {}
        for detail in abnormal_details:
            trend = _trend_label(detail.get("trend", "unknown"))
            trend_counts[trend] = trend_counts.get(trend, 0) + 1
        finish_step(
            5,
            "时序特征提取与候选复核",
            f"异常候选={len(abnormal_details)}",
            "统计异常候选趋势分布（ASU分支无历史基线建模）。",
            f"趋势分布={trend_counts}",
            "核对持续偏离与短时波动。",
        )

        start_step(6)
        knowledge_retrieval_primary = _run_knowledge_retrieval(
            overall_judgement=overall_judgement,
            abnormal_details=abnormal_details,
            task_note="interactive入口自动检索",
            retrieval_stage="primary",
        )
        knowledge_retrieval = _merge_knowledge_retrieval(knowledge_retrieval_primary, knowledge_retrieval_review)
        finish_step(
            6,
            "知识检索与候选措施整理",
            "输入异常候选与工况总览。",
            "调用 Dify 主检索，产出候选处置手段并预留校核检索。",
            str(knowledge_retrieval.get("retrieval_summary") or "未返回检索摘要。"),
            "核验候选手段是否满足现场边界与联锁约束。",
        )

        core_indicators = None
        all_records: List[Dict[str, Any]] = []
        timepoint_count = "-"
        sensor_count = len({item.get("tag_id") for item in semantic_data if item.get("tag_id")})
        effective_record_count = len(semantic_data)
        min_t = "未记录"
        max_t = "未记录"
    else:
        start_step(1)
        result = data_loader.load_and_standardize()
        standardized_data = result["records"]
        quality_gate = result.get("quality_gate") or {}
        parsing_audit = result.get("parsing_audit") or {}
        quality_status = str(quality_gate.get("status") or "UNKNOWN")
        if quality_status == "FAIL":
            raise ValueError("数据质量门禁未通过：有效样本为 0，无法继续优化分析。")
        all_records = standardized_data
        timestamps = [record.get("timestamp") for record in standardized_data if record.get("timestamp")]
        timepoint_count = len(set(timestamps))
        sensor_count = len({record.get("tag_id") for record in standardized_data if record.get("tag_id")})
        effective_record_count = len(standardized_data)
        min_t = min(timestamps) if timestamps else "未记录"
        max_t = max(timestamps) if timestamps else "未记录"
        finish_step(
            1,
            "数据加载与范围确认",
            f"输入文件: {data_file}",
            "读取并标准化 Excel 数据，执行质量门禁过滤。",
            (
                f"时间点={timepoint_count}，指标数={sensor_count}，有效记录={effective_record_count}，"
                f"时间范围={min_t}~{max_t}，质量门禁={quality_status}"
            ),
            "确认数据范围、质量门禁结果与样本完整性。",
        )

        start_step(2)
        latest_timestamp = max(timestamps) if timestamps else ""
        latest_records = (
            [record for record in standardized_data if record.get("timestamp") == latest_timestamp]
            if latest_timestamp
            else standardized_data
        )
        finish_step(
            2,
            "最新时刻快照提取",
            f"全量记录={len(standardized_data)}",
            "提取最新时刻快照记录。",
            f"最新时刻={latest_timestamp or '未记录'}，快照记录={len(latest_records)}",
            "核验快照时刻是否符合分析窗口。",
        )

        start_step(3)
        semantics_service.update_specs_from_csv_data(standardized_data)
        semantic_data = semantics_service.process(latest_records)
        if hasattr(semantics_service, "build_baseline_profile"):
            baseline_profile = semantics_service.build_baseline_profile(standardized_data)
        try:
            abnormal_details = semantics_service.build_abnormal_details(
                standardized_data,
                semantic_data,
                baseline_profile=baseline_profile,
            )
        except TypeError:
            abnormal_details = semantics_service.build_abnormal_details(standardized_data, semantic_data)
        finish_step(
            3,
            "规则预筛与语义复核",
            f"快照记录={len(latest_records)}",
            "执行规则判定与语义映射，并关联历史/优态基线参考。",
            f"异常候选={len(abnormal_details)}",
            "抽检高偏差指标是否与规则说明及基线偏差一致。",
        )

        start_step(4)
        try:
            overall_judgement = semantics_service.build_overall_operating_summary(
                semantic_data,
                abnormal_details,
                baseline_profile=baseline_profile,
                history_data=standardized_data,
                parsing_audit=parsing_audit,
            )
        except TypeError:
            overall_judgement = semantics_service.build_overall_operating_summary(
                semantic_data,
                abnormal_details,
            )
        try:
            semantic_ai_review = semantics_service.apply_ai_assistance(
                semantic_data=semantic_data,
                abnormal_details=abnormal_details,
                overall_judgement=overall_judgement,
                ask_model=ask_ai,
                task_note="interactive入口自动语义复核",
            )
        except Exception as exc:
            semantic_ai_review = {"used": False, "reason": str(exc)}
        finish_step(
            4,
            "工况总览判断",
            "输入语义结果与异常详情。",
            "计算风险等级与总览结论，并执行语义 AI 复核增强。",
            str(overall_judgement.get("summary") or "未生成总览结论。"),
            "确认风险等级与现场观测一致。",
        )

        start_step(5)
        trend_counts = {}
        for detail in abnormal_details:
            trend = _trend_label(detail.get("trend", "unknown"))
            trend_counts[trend] = trend_counts.get(trend, 0) + 1
        finish_step(
            5,
            "时序特征提取与候选复核",
            f"异常候选={len(abnormal_details)}",
            "统计异常候选趋势分布并生成优化主线优先级。",
            f"趋势分布={trend_counts}，基线覆盖={baseline_profile.get('tag_count', 0)}",
            "确认持续偏离与短时波动是否区分清晰。",
        )

        start_step(6)
        knowledge_retrieval_primary = _run_knowledge_retrieval(
            overall_judgement=overall_judgement,
            abnormal_details=abnormal_details,
            task_note="interactive入口自动检索",
            retrieval_stage="primary",
        )
        knowledge_retrieval = _merge_knowledge_retrieval(knowledge_retrieval_primary, knowledge_retrieval_review)
        finish_step(
            6,
            "知识检索与候选措施整理",
            "输入异常候选与工况总览。",
            "调用 Dify 主检索，产出候选处置手段并预留校核检索。",
            str(knowledge_retrieval.get("retrieval_summary") or "未返回检索摘要。"),
            "核验候选手段是否满足现场边界与联锁约束。",
        )

        core_indicators = semantics_service.calculate_core_indicators(semantic_data)
        from src.schemas.models import model_to_dict, validate_reasoning_result

    abnormal_count = len(abnormal_details)
    print(f"发现异常指标: {abnormal_count}")
    plant_state = str(overall_judgement.get("plant_state") or "").strip().lower()
    should_run_reasoning = abnormal_count > 0 or plant_state in {"optimizable", "risk_rising", "abnormal_unstable"}

    if not should_run_reasoning:
        start_step(7)
        finish_step(
            7,
            "AI 根因诊断",
            "当前快照无异常候选且无可执行优化机会。",
            "跳过大模型推理。",
            "未发现异常，维持当前工况。",
            "继续常规巡检与监控。",
        )

        start_step(8)
        finish_step(
            8,
            "决策验证与报告生成",
            "无异常候选，跳过决策推演。",
            "整理健康态结论并准备生成报告。",
            "健康态报告待生成。",
            "执行前仍需按标准巡检流程复核。",
        )
        sorted_traces = _ensure_full_steps(step_traces)
        report_base = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        visualization_context = visualization_service.build_visualization_context(
            standardized_data=standardized_data if "standardized_data" in locals() else [],
            latest_timestamp=latest_timestamp if "latest_timestamp" in locals() else None,
            abnormal_details=[],
            baseline_profile=baseline_profile,
            asset_dir=report_output_dir / "assets" / report_base,
            asset_prefix=f"assets/{report_base}",
        )
        analysis_result = {
            "status": "healthy",
            "abnormal_count": 0,
            "historical_abnormal_count": 0,
            "semantic_data": semantic_data,
            "core_indicators": None,
            "quality_gate": quality_gate,
            "baseline_profile": baseline_profile,
            "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
            "calculation_audit": overall_judgement.get("calculation_audit") or {},
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_name": os.path.basename(data_file or ""),
            "data_overview": {
                "file_name": os.path.basename(data_file or ""),
                "timepoint_count": timepoint_count,
                "sensor_count": sensor_count,
                "effective_record_count": effective_record_count,
                "time_range_start": min_t,
                "time_range_end": max_t,
                "latest_timestamp": latest_timestamp if "latest_timestamp" in locals() and latest_timestamp else "未记录",
                "latest_record_count": len(latest_records) if "latest_records" in locals() else len(semantic_data),
            },
            "analysis_steps": _analysis_step_summary(sorted_traces),
            "overall_judgement": overall_judgement,
            "semantic_ai_review": semantic_ai_review,
            "knowledge_retrieval": knowledge_retrieval,
            "optimization_context": {
                "workflow_goal": "整体优化（含异常处理）",
                "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
                "baseline_tag_count": baseline_profile.get("tag_count", 0),
                "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
                "knowledge_retrieval_used": True,
                "plant_state": overall_judgement.get("plant_state", "unknown"),
            },
            "visualization_context": visualization_context,
            "traceability": {
                "task_id": f"interactive-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "session_id": "interactive_cli",
                "mode": "统一流程",
                "data_source": "样本数据",
                "llm_provider": "direct",
                "llm_model": os.getenv("LLM_MODEL_NAME", ""),
                "retrieval_provider": "dify",
                "retrieval_model": os.getenv("DIFY_API_URL", "未配置"),
                "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
                "baseline_tag_count": baseline_profile.get("tag_count", 0),
                "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
                "generated_at": datetime.now().isoformat(),
                "step_traces": sorted_traces,
            },
        }
        report_generator.generate_both_formats(analysis_result, report_base)
        return analysis_result

    start_step(7)
    reasoning_result = json.loads(
        reasoning_engine.analyze(
            semantic_data=semantic_data,
            core_indicators=core_indicators,
            enable_cot=enable_cot,
            task_note="interactive入口自动诊断",
            knowledge_context=knowledge_retrieval,
            overall_judgement=overall_judgement,
        )
    )
    reasoning_result = model_to_dict(validate_reasoning_result(reasoning_result))
    finish_step(
        7,
        "AI 根因诊断",
        f"异常候选={len(abnormal_details)}，语义结果={len(semantic_data)}",
        "执行大模型根因推理并生成结构化结果。",
        str(reasoning_result.get("root_cause") or "")[:280] or "已生成根因诊断。",
        "确认根因链路与现场信号一致。",
    )
    knowledge_retrieval_review = _run_knowledge_retrieval(
        overall_judgement=overall_judgement,
        abnormal_details=abnormal_details,
        task_note="interactive入口建议校核检索",
        retrieval_stage="review",
        draft_suggestion=str(reasoning_result.get("operation_suggestion") or ""),
    )
    knowledge_retrieval = _merge_knowledge_retrieval(knowledge_retrieval_primary, knowledge_retrieval_review)

    start_step(8)

    decision_result = decision_service.verify_and_suggest(
        reasoning_result=reasoning_result,
        ask_model=ask_ai,
        knowledge_context=knowledge_retrieval,
        overall_judgement=overall_judgement,
        task_note="interactive入口自动决策校核",
        execution_feedback=execution_feedback,
        enable_closed_loop_validation=str(
            os.getenv("ENABLE_CLOSED_LOOP_VALIDATION", "false")
        ).strip().lower() in {"1", "true", "yes", "y", "on"},
    )
    decision_status = decision_result.get("verification_status", "Unknown")
    finish_step(
        8,
        "决策验证与报告生成",
        f"决策验证状态={_verification_status_text(decision_status)}",
        "汇总推理与决策结果并准备生成报告。",
        "异常态报告待生成。",
        "执行前按规程核验步骤、风险与回退策略。",
    )

    sorted_traces = _ensure_full_steps(step_traces)
    report_base = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    visualization_context = visualization_service.build_visualization_context(
        standardized_data=standardized_data if "standardized_data" in locals() else [],
        latest_timestamp=latest_timestamp if "latest_timestamp" in locals() else None,
        abnormal_details=abnormal_details,
        baseline_profile=baseline_profile,
        asset_dir=report_output_dir / "assets" / report_base,
        asset_prefix=f"assets/{report_base}",
    )
    analysis_result = {
        "status": "abnormal",
        "abnormal_count": abnormal_count,
        "historical_abnormal_count": abnormal_count,
        "semantic_data": semantic_data,
        "core_indicators": core_indicators.dict() if core_indicators and hasattr(core_indicators, "dict") else core_indicators,
        "quality_gate": quality_gate,
        "baseline_profile": baseline_profile,
        "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
        "calculation_audit": overall_judgement.get("calculation_audit") or {},
        "reasoning_result": reasoning_result,
        "decision_result": decision_result,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_name": os.path.basename(data_file or ""),
        "data_overview": {
            "file_name": os.path.basename(data_file or ""),
            "timepoint_count": timepoint_count,
            "sensor_count": sensor_count,
            "effective_record_count": effective_record_count,
            "time_range_start": min_t,
            "time_range_end": max_t,
            "latest_timestamp": latest_timestamp if "latest_timestamp" in locals() and latest_timestamp else "未记录",
            "latest_record_count": len(latest_records) if "latest_records" in locals() else len(semantic_data),
        },
        "analysis_steps": _analysis_step_summary(sorted_traces),
        "overall_judgement": overall_judgement,
        "semantic_ai_review": semantic_ai_review,
        "knowledge_retrieval": knowledge_retrieval,
        "abnormal_details": abnormal_details,
        "optimization_context": {
            "workflow_goal": "整体优化（含异常处理）",
            "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
            "baseline_tag_count": baseline_profile.get("tag_count", 0),
            "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
            "knowledge_retrieval_used": True,
            "plant_state": overall_judgement.get("plant_state", "unknown"),
        },
        "visualization_context": visualization_context,
        "traceability": {
            "task_id": f"interactive-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "session_id": "interactive_cli",
            "mode": "统一流程",
            "data_source": "样本数据",
            "llm_provider": "direct",
            "llm_model": os.getenv("LLM_MODEL_NAME", ""),
            "retrieval_provider": "dify",
            "retrieval_model": os.getenv("DIFY_API_URL", "未配置"),
            "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
            "baseline_tag_count": baseline_profile.get("tag_count", 0),
            "history_model_metadata": overall_judgement.get("history_model_metadata") or baseline_profile.get("history_model_metadata") or {},
            "generated_at": datetime.now().isoformat(),
            "step_traces": sorted_traces,
        },
    }
    report_generator.generate_both_formats(analysis_result, report_base)
    return analysis_result


def list_available_files():
    files = []
    for pattern in ("data/*.xlsx", "data/*.xls"):
        files.extend(glob.glob(pattern))
    return sorted(f for f in files if not f.endswith("~"))


def choose(prompt: str, options):
    print(f"\n{prompt}")
    for idx, option in enumerate(options, start=1):
        print(f"{idx}. {option}")
    while True:
        raw = input("请选择: ").strip()
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(options):
                return index
        print("输入无效，请重试。")


def main():
    files = list_available_files()
    if not files:
        raise FileNotFoundError("data 目录下没有可用的 Excel 文件。")

    file_index = choose("选择数据文件", [os.path.basename(path) for path in files])
    use_asu = input("是否使用 ASU 时间序列管道? (y/N): ").strip().lower() == "y"
    enable_cot = input("是否启用 CoT 推理? (Y/n): ").strip().lower() != "n"
    feedback_path = input("执行反馈JSON路径（可留空）: ").strip()
    execution_feedback = None
    if feedback_path:
        with open(feedback_path, "r", encoding="utf-8") as f:
            execution_feedback = json.load(f)

    selected_file = files[file_index]
    result = simulate_user_operation(
        data_file=selected_file,
        use_asu_pipeline=use_asu,
        enable_cot=enable_cot,
        execution_feedback=execution_feedback,
    )
    print("\n分析完成。")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1000])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户取消。")
    except Exception as exc:
        print(f"\n发生错误: {exc}")
        raise
