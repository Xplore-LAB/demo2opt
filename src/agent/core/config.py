from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class AgentConfig:
    entrypoint: str = "cli"
    data_file: str = ""
    enable_async: bool = False
    enable_cot: bool = True
    use_asu_pipeline: bool = False
    auto_confirm: bool = True
    task_note: str = ""
    data_source: str = "sample"
    llm_config: Optional[Dict[str, Any]] = None
    dify_config: Optional[Dict[str, Any]] = None
    execution_feedback: Optional[Dict[str, Any]] = None
    enable_closed_loop_validation: bool = False

    def to_state_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["llm_config"] = dict(self.llm_config or {})
        payload["dify_config"] = dict(self.dify_config or {})
        payload["execution_feedback"] = dict(self.execution_feedback or {})
        return payload


def build_retrieval_config(override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    override = override or {}
    return {
        "api_url": str(
            override.get("api_url")
            or os.getenv("DIFY_DATASETS_API_URL")
            or os.getenv("DIFY_API_URL", "http://localhost/v1")
        ).strip(),
        "api_key": str(override.get("api_key") or os.getenv("DIFY_API_KEY", "")).strip(),
        "app_name": str(override.get("app_name") or "").strip(),
        "api_mode": str(override.get("api_mode") or os.getenv("DIFY_RETRIEVAL_API_MODE", "datasets_retrieve")).strip(),
        "dataset_id": str(override.get("dataset_id") or os.getenv("DIFY_DATASET_ID", "")).strip(),
        "keyword": override.get("keyword", os.getenv("DIFY_DATASETS_KEYWORD", "")),
        "tag_ids": override.get("tag_ids", os.getenv("DIFY_DATASETS_TAG_IDS", "")),
        "page": override.get("page", os.getenv("DIFY_DATASETS_PAGE", "1")),
        "limit": override.get("limit", os.getenv("DIFY_DATASETS_LIMIT", "20")),
        "include_all": override.get("include_all", os.getenv("DIFY_DATASETS_INCLUDE_ALL", "false")),
        "top_k": override.get("top_k", os.getenv("DIFY_RETRIEVE_TOP_K", "5")),
        "search_method": override.get("search_method", os.getenv("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search")),
        "reranking_enable": override.get(
            "reranking_enable",
            os.getenv("DIFY_RETRIEVE_RERANKING_ENABLE", "false"),
        ),
        "score_threshold": override.get("score_threshold", os.getenv("DIFY_RETRIEVE_SCORE_THRESHOLD", "0")),
        "response_mode": override.get("response_mode", os.getenv("DIFY_RESPONSE_MODE", "blocking")),
        "timeout_sec": override.get("timeout_sec", os.getenv("LLM_TIMEOUT_SEC", "")),
    }


def build_llm_config(override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    override = override or {}
    return {
        "base_url": str(override.get("base_url") or os.getenv("LLM_BASE_URL", "")).strip(),
        "api_key": str(override.get("api_key") or os.getenv("LLM_API_KEY", "")).strip(),
        "model": str(override.get("model") or os.getenv("LLM_MODEL_NAME", "")).strip(),
    }


def load_agent_config(inputs: Optional[Dict[str, Any]] = None) -> AgentConfig:
    inputs = inputs or {}
    return AgentConfig(
        entrypoint=str(inputs.get("entrypoint") or "cli"),
        data_file=str(inputs.get("data_file") or os.getenv("DATA_FILE", "data/【原始数据】运行诊断.xlsx")),
        enable_async=bool(inputs.get("enable_async", False)),
        enable_cot=bool(inputs.get("enable_cot", True)),
        use_asu_pipeline=bool(inputs.get("use_asu_pipeline", False)),
        auto_confirm=bool(inputs.get("auto_confirm", inputs.get("entrypoint") != "ws")),
        task_note=str(inputs.get("task_note") or ""),
        data_source=str(inputs.get("data_source") or "sample"),
        llm_config=build_llm_config(inputs.get("llm_config")),
        dify_config=build_retrieval_config(inputs.get("dify_config")),
        execution_feedback=inputs.get("execution_feedback") or {},
        enable_closed_loop_validation=bool(
            inputs.get("enable_closed_loop_validation", _bool_env("ENABLE_CLOSED_LOOP_VALIDATION", False))
        ),
    )

