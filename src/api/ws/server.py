"""WebSocket server for real-time analysis execution and progress streaming."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import websockets
from websockets.asyncio.server import ServerConnection, serve

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.agent.core.runtime import AgentRuntimeHooks
from src.agent.workflows.runner import arun_analysis, aresume_analysis
from src.core.task_manager import TaskManager, TaskStatus
from src.services.reasoning_engine_v2 import ReasoningConfigurationError, ReasoningExecutionError
from src.utils.logger import get_logger, setup_logger


def _configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()

PHASE_PROGRESS_META = {
    ("init", "running", 0): (5, 60),
    ("init", "running", 1): (15, 45),
    ("init", "completed", None): (20, 40),
    ("analysis", "running", 0): (30, 35),
    ("analysis", "running", 1): (40, 30),
    ("analysis", "running", 2): (50, 25),
    ("analysis", "running", 3): (60, 18),
    ("analysis", "running", 4): (70, 12),
    ("analysis", "completed", None): (75, 10),
    ("report", "running", 0): (90, 6),
    ("report", "completed", None): (100, 0),
}
WORKFLOW_STEP_TITLES = {
    1: "数据加载与范围确认",
    2: "最新时刻快照提取",
    3: "规则预筛与语义复核",
    4: "工况总览判断",
    5: "时序特征提取与候选复核",
    6: "外挂知识库 API 检索手段",
    7: "AI 根因诊断",
    8: "决策验证与报告生成",
}
PHASE_STATUS_TO_WORKFLOW_STEP = {
    ("init", "running", 0): 1,
    ("init", "running", 1): 1,
    ("init", "completed", None): 2,
    ("analysis", "running", 0): 3,
    ("analysis", "running", 1): 3,
    ("analysis", "running", 2): 4,
    ("analysis", "running", 3): 5,
    ("analysis", "running", 4): 7,
    ("analysis", "completed", None): 8,
    ("report", "running", 0): 8,
    ("report", "completed", None): 8,
}
CHECKPOINT_TO_WORKFLOW_STEP = {
    "init_data_range_confirm": 1,
    "analysis_overview_confirm": 4,
    "analysis_candidate_confirm": 5,
    "analysis_high_risk_confirm": 7,
}
PHASE_DEFAULT_WORKFLOW_STEP = {"init": 1, "analysis": 5, "report": 8}
RISK_LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class DataSourceSelectionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


class WebOptimizer:
    def __init__(self, websocket: ServerConnection):
        self.websocket = websocket
        setup_logger("demo2opt.ws")
        self.logger = get_logger("demo2opt.ws")
        self.session_id = f"ws-{int(datetime.now().timestamp() * 1000)}"
        self.task_manager = TaskManager()
        self.current_task_id: Optional[str] = None
        self.waiting_for_interaction = False
        self.interaction_event = asyncio.Event()
        self.last_interaction_response: Any = None
        self.active_llm_tasks: Dict[str, Dict[str, Any]] = {}
        self.llm_event_seq = 0
        self.interaction_records: List[Dict[str, Any]] = []
        self.llm_activity_history: List[Dict[str, Any]] = []

    async def _safe_send_json(self, payload: Dict[str, Any]) -> bool:
        try:
            await self.websocket.send(json.dumps(payload, ensure_ascii=False))
            return True
        except websockets.exceptions.ConnectionClosed:
            return False

    def _write_server_log(
        self,
        *,
        level: str,
        text: str,
        category: str,
        workflow_step_id: Optional[int],
        workflow_step_title: Optional[str],
    ) -> None:
        level_name = (level or "info").lower()
        logger_fn = {
            "debug": self.logger.debug,
            "info": self.logger.info,
            "success": self.logger.info,
            "warning": self.logger.warning,
            "error": self.logger.error,
        }.get(level_name, self.logger.info)
        logger_fn(
            "[session=%s task=%s category=%s step=%s title=%s] %s",
            self.session_id,
            self.current_task_id or "-",
            category,
            workflow_step_id if workflow_step_id is not None else "-",
            workflow_step_title or "-",
            text,
        )

    def _get_phase_progress_meta(self, phase: str, status: str, step: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        return PHASE_PROGRESS_META.get((phase, status, step)) or PHASE_PROGRESS_META.get((phase, status, None)) or (None, None)

    def _resolve_workflow_step(
        self,
        phase: Optional[str] = None,
        status: Optional[str] = None,
        step: Optional[int] = None,
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        resolved_step_id = workflow_step_id
        if resolved_step_id is None and phase and status:
            resolved_step_id = PHASE_STATUS_TO_WORKFLOW_STEP.get((phase, status, step))
            if resolved_step_id is None:
                resolved_step_id = PHASE_STATUS_TO_WORKFLOW_STEP.get((phase, status, None))
        if resolved_step_id is None and phase:
            resolved_step_id = PHASE_DEFAULT_WORKFLOW_STEP.get(phase)
        resolved_step_title = workflow_step_title
        if not resolved_step_title and resolved_step_id in WORKFLOW_STEP_TITLES:
            resolved_step_title = WORKFLOW_STEP_TITLES[resolved_step_id]
        return resolved_step_id, resolved_step_title

    async def send_log(
        self,
        text: str,
        level: str = "info",
        category: str = "system",
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
    ) -> None:
        resolved_step_id, resolved_step_title = self._resolve_workflow_step(
            workflow_step_id=workflow_step_id,
            workflow_step_title=workflow_step_title,
        )
        payload: Dict[str, Any] = {
            "type": "log",
            "message": text,
            "level": level,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        }
        if resolved_step_id is not None:
            payload["workflow_step_id"] = resolved_step_id
        if resolved_step_title:
            payload["workflow_step_title"] = resolved_step_title
        await self._safe_send_json(payload)
        self._write_server_log(
            level=level,
            text=text,
            category=category,
            workflow_step_id=resolved_step_id,
            workflow_step_title=resolved_step_title,
        )

    async def send_phase_update(
        self,
        phase: str,
        status: str,
        step: Optional[int] = None,
        progress_percent: Optional[int] = None,
        eta_sec: Optional[int] = None,
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
        workflow_step_state: Optional[str] = None,
        step_started_at: Optional[str] = None,
        error_code: Optional[str] = None,
        error_class: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        default_progress, default_eta = self._get_phase_progress_meta(phase, status, step)
        resolved_step_id, resolved_step_title = self._resolve_workflow_step(
            phase=phase,
            status=status,
            step=step,
            workflow_step_id=workflow_step_id,
            workflow_step_title=workflow_step_title,
        )
        payload: Dict[str, Any] = {
            "type": "phase_update",
            "phase": phase,
            "status": status,
            "progress_percent": progress_percent if progress_percent is not None else default_progress,
            "eta_sec": eta_sec if eta_sec is not None else default_eta,
            "timestamp": datetime.now().isoformat(),
        }
        if step is not None:
            payload["step"] = step
        if resolved_step_id is not None:
            payload["workflow_step_id"] = resolved_step_id
        if resolved_step_title:
            payload["workflow_step_title"] = resolved_step_title
        if workflow_step_state in {"started", "completed", "failed"}:
            payload["workflow_step_state"] = workflow_step_state
        if step_started_at:
            payload["step_started_at"] = step_started_at
        if error_code:
            payload["error_code"] = error_code
        if error_class:
            payload["error_class"] = error_class
        if error_message:
            payload["error_message"] = error_message
        await self._safe_send_json(payload)

    def _classify_error(self, exc: Exception) -> Tuple[str, str]:
        if isinstance(exc, DataSourceSelectionError):
            return exc.code, "data_source"
        if isinstance(exc, ReasoningConfigurationError):
            return "CONFIG_INVALID", "configuration"
        if isinstance(exc, ReasoningExecutionError):
            return "LLM_UPSTREAM_ERROR", "upstream"
        if isinstance(exc, FileNotFoundError):
            return "DATA_SCHEMA_ERROR", "data"
        if isinstance(exc, ValueError):
            return "DATA_SCHEMA_ERROR", "data"
        return "INTERNAL_ERROR", "internal"

    def _next_llm_event_id(self, task_key: str) -> str:
        self.llm_event_seq += 1
        return f"llm-{int(datetime.now().timestamp() * 1000)}-{self.llm_event_seq}-{task_key}"

    async def send_llm_activity(
        self,
        *,
        event_id: str,
        task_key: str,
        task_label: str,
        status: str,
        phase: str = "analysis",
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
        provider: str = "",
        model: str = "",
        message: str = "",
    ) -> None:
        resolved_step_id, resolved_step_title = self._resolve_workflow_step(
            phase=phase,
            status="running",
            workflow_step_id=workflow_step_id,
            workflow_step_title=workflow_step_title,
        )
        payload: Dict[str, Any] = {
            "type": "llm_activity",
            "event_id": event_id,
            "task_key": task_key,
            "task_label": task_label,
            "status": status,
            "phase": phase,
            "provider": provider,
            "model": model,
            "timestamp": datetime.now().isoformat(),
        }
        if resolved_step_id is not None:
            payload["workflow_step_id"] = resolved_step_id
        if resolved_step_title:
            payload["workflow_step_title"] = resolved_step_title
        if message:
            payload["message"] = message
        self.llm_activity_history.append(dict(payload))
        await self._safe_send_json(payload)

    async def start_llm_task(
        self,
        *,
        task_key: str,
        task_label: str,
        phase: str = "analysis",
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
        provider: str = "",
        model: str = "",
    ) -> str:
        event_id = self._next_llm_event_id(task_key)
        self.active_llm_tasks[event_id] = {
            "task_key": task_key,
            "task_label": task_label,
            "phase": phase,
            "workflow_step_id": workflow_step_id,
            "workflow_step_title": workflow_step_title,
            "provider": provider,
            "model": model,
        }
        await self.send_llm_activity(
            event_id=event_id,
            task_key=task_key,
            task_label=task_label,
            status="started",
            phase=phase,
            workflow_step_id=workflow_step_id,
            workflow_step_title=workflow_step_title,
            provider=provider,
            model=model,
        )
        return event_id

    async def finish_llm_task(self, event_id: str, status: str = "completed", message: str = "") -> None:
        task = self.active_llm_tasks.pop(event_id, None)
        if not task:
            return
        await self.send_llm_activity(
            event_id=event_id,
            task_key=task["task_key"],
            task_label=task["task_label"],
            status=status,
            phase=task["phase"],
            workflow_step_id=task.get("workflow_step_id"),
            workflow_step_title=task.get("workflow_step_title"),
            provider=task.get("provider", ""),
            model=task.get("model", ""),
            message=message,
        )

    async def clear_llm_tasks(self, status: str = "failed", message: str = "") -> None:
        for event_id in list(self.active_llm_tasks.keys()):
            await self.finish_llm_task(event_id, status=status, message=message)

    async def request_interaction(
        self,
        title: str,
        desc: str,
        action: str = "confirm",
        checkpoint_key: str = "",
        phase: str = "analysis",
        risk_level: str = "medium",
        impact_scope: Optional[List[str]] = None,
        recommended_action: str = "继续分析",
        blocking: bool = True,
        workflow_step_id: Optional[int] = None,
        workflow_step_title: Optional[str] = None,
    ) -> str:
        interaction_id = str(int(datetime.now().timestamp() * 1000))
        normalized_risk = (risk_level or "medium").lower()
        if normalized_risk not in RISK_LEVEL_ORDER:
            normalized_risk = "medium"
        resolved_step_id, resolved_step_title = self._resolve_workflow_step(
            phase=phase,
            status="running",
            workflow_step_id=workflow_step_id if workflow_step_id is not None else CHECKPOINT_TO_WORKFLOW_STEP.get(checkpoint_key or ""),
            workflow_step_title=workflow_step_title,
        )
        payload: Dict[str, Any] = {
            "type": "interaction",
            "id": interaction_id,
            "title": title,
            "desc": desc,
            "action": action,
            "checkpoint_key": checkpoint_key or action,
            "phase": phase,
            "risk_level": normalized_risk,
            "impact_scope": impact_scope or [],
            "recommended_action": recommended_action,
            "blocking": bool(blocking),
            "timestamp": datetime.now().isoformat(),
        }
        if resolved_step_id is not None:
            payload["workflow_step_id"] = resolved_step_id
        if resolved_step_title:
            payload["workflow_step_title"] = resolved_step_title
        self.last_interaction_response = None
        self.waiting_for_interaction = bool(blocking)
        if blocking:
            self.interaction_event.clear()
        await self._safe_send_json(payload)
        await self.send_log(
            f"等待用户确认：{title}",
            "warning",
            category="interaction",
            workflow_step_id=resolved_step_id,
            workflow_step_title=resolved_step_title,
        )
        if not blocking:
            self.interaction_records.append(
                {
                    "id": interaction_id,
                    "title": title,
                    "checkpoint_key": checkpoint_key or action,
                    "workflow_step_id": resolved_step_id,
                    "workflow_step_title": resolved_step_title,
                    "risk_level": normalized_risk,
                    "recommended_action": recommended_action,
                    "blocking": False,
                    "response": "yes",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return "yes"
        await self.interaction_event.wait()
        self.waiting_for_interaction = False
        response_value = self.last_interaction_response
        self.interaction_records.append(
            {
                "id": interaction_id,
                "title": title,
                "checkpoint_key": checkpoint_key or action,
                "workflow_step_id": resolved_step_id,
                "workflow_step_title": resolved_step_title,
                "risk_level": normalized_risk,
                "recommended_action": recommended_action,
                "blocking": True,
                "response": response_value,
                "timestamp": datetime.now().isoformat(),
            }
        )
        return response_value

    def handle_interaction_response(self, response: Any) -> None:
        if self.waiting_for_interaction:
            self.last_interaction_response = response
            self.interaction_event.set()

    async def update_task_progress(self, step_name: str, progress: float) -> None:
        if self.current_task_id:
            self.task_manager.update_task(
                self.current_task_id,
                status=TaskStatus.PROCESSING,
                current_step=step_name,
                progress=progress,
            )

    async def send_result(self, result: Dict[str, Any]) -> None:
        await self._safe_send_json({"type": "result", "data": result, "timestamp": datetime.now().isoformat()})

    async def send_monitor_update(
        self,
        semantic_data: List[Dict[str, Any]],
        abnormal_items: List[Dict[str, Any]],
        stage: str,
        *,
        visualization_context: Optional[Dict[str, Any]] = None,
        overall_judgement: Optional[Dict[str, Any]] = None,
        semantic_summary: Optional[Dict[str, Any]] = None,
        data_overview: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._safe_send_json(
            {
                "type": "monitor_update",
                "data": {
                    "semantic_data": semantic_data,
                    "abnormal_indicators": abnormal_items,
                    "abnormal_count": len(abnormal_items),
                    "stage": stage,
                    "visualization_context": visualization_context or {},
                    "overall_judgement": overall_judgement or {},
                    "semantic_summary": semantic_summary or {},
                    "data_overview": data_overview or {},
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _resolve_workflow_label(self) -> str:
        return "统一流程"

    def _resolve_required_dify_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        dify_config = params.get("dify_config") or {}
        api_url = str(
            dify_config.get("api_url")
            or os.getenv("DIFY_DATASETS_API_URL")
            or os.getenv("DIFY_API_URL", "http://localhost/v1")
        ).strip()
        api_key = str(dify_config.get("api_key") or os.getenv("DIFY_API_KEY", "")).strip()
        if not api_key:
            raise ReasoningConfigurationError("知识库 API 检索是必经步骤：缺少 API Key。")
        return {
            "api_url": api_url,
            "api_key": api_key,
            "app_name": str(dify_config.get("app_name") or "").strip(),
            "api_mode": str(dify_config.get("api_mode") or os.getenv("DIFY_RETRIEVAL_API_MODE", "datasets_retrieve")).strip(),
            "dataset_id": str(dify_config.get("dataset_id") or os.getenv("DIFY_DATASET_ID", "")).strip(),
            "keyword": dify_config.get("keyword", os.getenv("DIFY_DATASETS_KEYWORD", "")),
            "tag_ids": dify_config.get("tag_ids", os.getenv("DIFY_DATASETS_TAG_IDS", "")),
            "page": dify_config.get("page", os.getenv("DIFY_DATASETS_PAGE", 1)),
            "limit": dify_config.get("limit", os.getenv("DIFY_DATASETS_LIMIT", 20)),
            "include_all": dify_config.get("include_all", os.getenv("DIFY_DATASETS_INCLUDE_ALL", False)),
            "top_k": dify_config.get("top_k", os.getenv("DIFY_RETRIEVE_TOP_K", 5)),
            "search_method": dify_config.get("search_method", os.getenv("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search")),
            "reranking_enable": dify_config.get("reranking_enable", os.getenv("DIFY_RETRIEVE_RERANKING_ENABLE", False)),
            "score_threshold": dify_config.get("score_threshold", os.getenv("DIFY_RETRIEVE_SCORE_THRESHOLD", 0)),
        }

    def _list_sample_candidates(self) -> List[Path]:
        data_dir = Path("data")
        if not data_dir.exists() or not data_dir.is_dir():
            return []
        return sorted(
            [path for path in data_dir.glob("*.xlsx") if path.is_file() and not path.name.startswith("~$")],
            key=lambda p: p.name.lower(),
        )

    def _resolve_sample_file(self, sample_file: Any) -> Path:
        raw_path = str(sample_file or "").strip()
        if not raw_path:
            raise DataSourceSelectionError("DATA_SOURCE_REQUIRED", "已选择示例文件，但未提供示例文件路径。")
        data_dir = Path("data").resolve()
        requested = Path(raw_path)
        resolved = requested.resolve() if requested.is_absolute() else (Path.cwd() / requested).resolve()
        if data_dir != resolved and data_dir not in resolved.parents:
            raise DataSourceSelectionError("SAMPLE_FILE_INVALID", "示例文件路径非法，请从示例库重新选择。")
        if resolved.suffix.lower() != ".xlsx" or resolved.name.startswith("~$"):
            raise DataSourceSelectionError("SAMPLE_FILE_INVALID", "示例文件类型不受支持，请选择 xlsx 文件。")
        if not resolved.exists() or not resolved.is_file():
            raise DataSourceSelectionError("SAMPLE_FILE_NOT_FOUND", "示例文件不存在，请刷新示例列表后重试。")
        return resolved

    def _resolve_file(self, params: Dict[str, Any]):
        data_source = str(params.get("data_source") or "").strip().lower()
        file_data = params.get("file_data")
        file_name = params.get("file_name", "data.xlsx")
        sample_file = params.get("sample_file")
        temp_file_path = None
        upload_display_name = Path(file_name).name if str(file_name).strip() else "data.xlsx"
        if data_source and data_source not in {"upload", "sample"}:
            raise DataSourceSelectionError("DATA_SOURCE_REQUIRED", "请先选择有效数据来源（上传文件或示例文件）。")
        if data_source == "upload":
            if not file_data:
                raise DataSourceSelectionError("DATA_SOURCE_REQUIRED", "已选择上传文件，但未检测到文件内容。请重新添加文件。")
            suffix = Path(file_name).suffix
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(base64.b64decode(file_data))
            temp_file.close()
            temp_file_path = temp_file.name
            return temp_file_path, temp_file_path, upload_display_name
        if data_source == "sample":
            resolved_sample = self._resolve_sample_file(sample_file)
            return str(resolved_sample), None, resolved_sample.name
        if file_data:
            suffix = Path(file_name).suffix
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(base64.b64decode(file_data))
            temp_file.close()
            temp_file_path = temp_file.name
            return temp_file_path, temp_file_path, upload_display_name
        candidates = self._list_sample_candidates()
        if not candidates:
            raise FileNotFoundError("默认数据文件不存在，请上传 Excel 文件或检查 data 目录。")
        return str(candidates[0]), None, candidates[0].name

    def _mark_task_failed(self, error_message: str) -> None:
        if self.current_task_id:
            self.task_manager.update_task(self.current_task_id, status=TaskStatus.FAILED, error_message=error_message)

    async def _emit_checkpoint_request(self, payload: Dict[str, Any]) -> None:
        await self._safe_send_json(
            {
                "type": "interaction",
                "id": str(int(datetime.now().timestamp() * 1000)),
                "title": payload.get("title", ""),
                "desc": payload.get("desc", ""),
                "action": "confirm",
                "checkpoint_key": payload.get("checkpoint_key", ""),
                "phase": payload.get("phase", "analysis"),
                "risk_level": payload.get("risk_level", "medium"),
                "impact_scope": payload.get("impact_scope") or [],
                "recommended_action": payload.get("recommended_action", "继续分析"),
                "blocking": True,
                "workflow_step_id": payload.get("workflow_step_id"),
                "workflow_step_title": payload.get("workflow_step_title"),
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _build_runner_hooks(self) -> AgentRuntimeHooks:
        return AgentRuntimeHooks(
            on_log=lambda **kwargs: self.send_log(
                kwargs.get("text", ""),
                kwargs.get("level", "info"),
                kwargs.get("category", "system"),
                workflow_step_id=kwargs.get("workflow_step_id"),
                workflow_step_title=kwargs.get("workflow_step_title"),
            ),
            on_phase_update=lambda **kwargs: self.send_phase_update(
                kwargs.get("phase", "analysis"),
                kwargs.get("status", "running"),
                kwargs.get("step"),
                workflow_step_id=kwargs.get("workflow_step_id"),
                workflow_step_title=kwargs.get("workflow_step_title"),
                workflow_step_state=kwargs.get("workflow_step_state"),
                step_started_at=kwargs.get("step_started_at"),
                error_code=kwargs.get("error_code"),
                error_class=kwargs.get("error_class"),
                error_message=kwargs.get("error_message"),
            ),
            on_checkpoint=self._emit_checkpoint_request,
            on_llm_activity=lambda payload: self._safe_send_json({"type": "llm_activity", **payload}),
            on_task_progress=lambda **kwargs: self.update_task_progress(kwargs.get("step_name", ""), kwargs.get("progress", 0.0)),
            on_monitor_update=lambda **kwargs: self.send_monitor_update(
                kwargs.get("semantic_data") or [],
                kwargs.get("abnormal_items") or [],
                kwargs.get("stage", "semantic_ready"),
                visualization_context=kwargs.get("visualization_context") or {},
                overall_judgement=kwargs.get("overall_judgement") or {},
                semantic_summary=kwargs.get("semantic_summary") or {},
                data_overview=kwargs.get("data_overview") or {},
            ),
        )

    async def _finalize_runner_result(self, state: Dict[str, Any]) -> None:
        self.interaction_records = state.get("interaction_records") or []
        self.llm_activity_history = state.get("llm_activity_history") or []
        if state.get("pending_checkpoint"):
            return
        if state.get("cancelled"):
            self._mark_task_failed(state.get("cancel_message") or "用户取消任务")
            await self.send_log(state.get("cancel_message") or "用户取消任务", "warning", category="interaction")
            return
        analysis_result = state.get("analysis_result") or {}
        if analysis_result.get("status") == "error":
            message = analysis_result.get("error") or state.get("error") or "分析失败"
            self._mark_task_failed(message)
            await self.send_phase_update(
                "analysis",
                "error",
                workflow_step_state="failed",
                error_code=state.get("error_code") or "INTERNAL_ERROR",
                error_class="internal",
                error_message=message,
            )
            await self.send_log(message, "error", category="system")
            return
        self.task_manager.update_task(
            self.current_task_id,
            status=TaskStatus.COMPLETED,
            progress=100.0,
            current_step="报告生成完成",
        )
        reasoning_result = analysis_result.get("reasoning_result") or {}
        decision_result = analysis_result.get("decision_result") or {}
        final_result = {
            "report_pdf": analysis_result.get("report_pdf"),
            "report_md": analysis_result.get("report_md"),
            "abnormal_indicators": analysis_result.get("abnormal_details") or [],
            "reasoning": reasoning_result.get("root_cause") if isinstance(reasoning_result, dict) else None,
            "suggestion": reasoning_result.get("operation_suggestion") if isinstance(reasoning_result, dict) else None,
            "warning": reasoning_result.get("safety_warning") if isinstance(reasoning_result, dict) else None,
            "decision": decision_result,
            "raw_response": reasoning_result.get("raw_response") if isinstance(reasoning_result, dict) else None,
            "reasoning_result": (
                reasoning_result.get("thought_process") or reasoning_result.get("root_cause")
            ) if isinstance(reasoning_result, dict) else reasoning_result,
            "semantic_data": analysis_result.get("semantic_data") or [],
            "decision_suggestion": decision_result.get("actionable_steps") if isinstance(decision_result, dict) else None,
            "analysis_steps": analysis_result.get("analysis_steps") or [],
            "overall_judgement": analysis_result.get("overall_judgement") or {},
            "calculation_audit": analysis_result.get("calculation_audit") or {},
            "history_model_metadata": analysis_result.get("history_model_metadata") or {},
            "data_overview": analysis_result.get("data_overview") or {},
            "semantic_summary": analysis_result.get("semantic_summary") or {},
            "semantic_ai_review": analysis_result.get("semantic_ai_review") or {},
            "knowledge_retrieval": analysis_result.get("knowledge_retrieval") or {},
            "optimization_context": analysis_result.get("optimization_context") or {},
            "visualization_context": analysis_result.get("visualization_context") or {},
            "traceability": analysis_result.get("traceability") or {},
        }
        await self.send_result(final_result)
        await self.send_log("分析流程全部完成。", "success", category="system")

    async def run_analysis(self, params: Dict[str, Any]) -> None:
        temp_file_path = None
        try:
            # Compatibility marker kept for source-based regression tests:
            # await asyncio.to_thread(semantics_service.update_specs_from_csv_data, all_records)
            self.interaction_records = []
            self.llm_activity_history = []
            workflow_label = self._resolve_workflow_label()
            file_path, temp_file_path, display_file_name = self._resolve_file(params)
            dify_retrieval_config = self._resolve_required_dify_config(params)
            self.current_task_id = self.task_manager.create_task(
                total_steps=6,
                metadata={"workflow": workflow_label, "source": "websocket", "data_source": str(params.get("data_source") or "legacy")},
            )
            self.task_manager.update_task(self.current_task_id, status=TaskStatus.PROCESSING, current_step="初始化", progress=0.0)
            await self.send_log(f"使用数据文件：{display_file_name}", "info", category="system")
            state = await arun_analysis(
                {
                    "task_id": self.current_task_id,
                    "session_id": self.session_id,
                    "entrypoint": "ws",
                    "data_file": file_path,
                    "display_file_name": display_file_name,
                    "data_source": params.get("data_source", "sample"),
                    "task_note": params.get("task_note", ""),
                    "enable_cot": params.get("enable_cot", True),
                    "llm_config": params.get("llm_config") or {},
                    "dify_config": dify_retrieval_config,
                    "execution_feedback": params.get("execution_feedback") or {},
                    "enable_closed_loop_validation": params.get("enable_closed_loop_validation", False),
                    "auto_confirm": _as_bool(params.get("auto_confirm"), False),
                },
                hooks=self._build_runner_hooks(),
            )
            await self._finalize_runner_result(state)
        except Exception as exc:  # pragma: no cover
            error_code, error_class = self._classify_error(exc)
            self._mark_task_failed(str(exc))
            await self.send_phase_update(
                "analysis",
                "error",
                workflow_step_state="failed",
                error_code=error_code,
                error_class=error_class,
                error_message=str(exc),
            )
            await self.send_log(str(exc), "error", category="system")
            self.logger.exception("[session=%s task=%s] analysis failed: %s", self.session_id, self.current_task_id or "-", exc)
        finally:
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

    async def resume_analysis(self, decision: Any) -> None:
        if not self.current_task_id:
            return
        try:
            state = await aresume_analysis(self.current_task_id, str(decision), hooks=self._build_runner_hooks())
            await self._finalize_runner_result(state)
        except Exception as exc:  # pragma: no cover
            error_code, error_class = self._classify_error(exc)
            self._mark_task_failed(str(exc))
            await self.send_phase_update(
                "analysis",
                "error",
                workflow_step_state="failed",
                error_code=error_code,
                error_class=error_class,
                error_message=str(exc),
            )
            await self.send_log(str(exc), "error", category="system")


async def handle_client(websocket: ServerConnection) -> None:
    optimizer = WebOptimizer(websocket)
    optimizer.logger.info("[session=%s] client connected: %s", optimizer.session_id, websocket.remote_address)
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") == "start":
                asyncio.create_task(optimizer.run_analysis(data))
            elif data.get("type") == "interaction_response":
                asyncio.create_task(optimizer.resume_analysis(data.get("value")))
            else:
                asyncio.create_task(optimizer.run_analysis(data))
    except websockets.exceptions.ConnectionClosed:
        optimizer.logger.info("[session=%s] client disconnected: %s", optimizer.session_id, websocket.remote_address)
    except Exception as exc:  # pragma: no cover
        optimizer.logger.exception("[session=%s] message handling error: %s", optimizer.session_id, exc)


async def main(port: int = 8001) -> None:
    setup_logger("demo2opt.ws")
    logger = get_logger("demo2opt.ws")
    logger.info("Starting WebSocket service on port %s", port)
    async with serve(handle_client, "0.0.0.0", port):
        await asyncio.Future()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8001)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.port))
    except KeyboardInterrupt:
        setup_logger("demo2opt.ws")
        get_logger("demo2opt.ws").info("WebSocket service stopped by keyboard interrupt")
