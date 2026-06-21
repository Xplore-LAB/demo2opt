import json
import os
from typing import Any, Dict, List, Optional

import requests


class KnowledgeRetrievalService:
    """Retrieve knowledge context from Dify datasets retrieve API."""

    def __init__(self, dify_config: Optional[Dict[str, Any]] = None):
        cfg = dify_config or {}
        raw_api_url = str(
            cfg.get("api_url")
            or os.getenv("DIFY_DATASETS_API_URL")
            or os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")
        ).strip()

        self.base_url = self._normalize_base_url(raw_api_url)
        self.api_url = f"{self.base_url}/datasets"
        self.api_key = str(cfg.get("api_key") or os.getenv("DIFY_API_KEY", "")).strip()

        # Legacy key kept for compatibility with existing callers.
        self.api_mode = str(
            cfg.get("api_mode") if "api_mode" in cfg else os.getenv("DIFY_RETRIEVAL_API_MODE", "datasets_retrieve")
        ).strip().lower() or "datasets_retrieve"

        self.dataset_id = str(
            cfg.get("dataset_id") if "dataset_id" in cfg else os.getenv("DIFY_DATASET_ID", "")
        ).strip()
        self.resolved_dataset_id = ""
        self.resolved_dataset_name = ""
        self.resolved_dataset_source = ""

        timeout_sec: Optional[int] = None
        timeout_value = cfg.get("timeout_sec") if dify_config else None
        try:
            timeout_sec = int(timeout_value) if timeout_value not in (None, "") else None
        except (TypeError, ValueError):
            timeout_sec = None
        self.timeout_sec = timeout_sec or 30

        raw_tag_ids = cfg.get("tag_ids") if "tag_ids" in cfg else os.getenv("DIFY_DATASETS_TAG_IDS", "")
        self.dataset_query = {
            "keyword": str(cfg.get("keyword") if "keyword" in cfg else os.getenv("DIFY_DATASETS_KEYWORD", "")).strip(),
            "tag_ids": self._normalize_tag_ids(raw_tag_ids),
            "page": self._parse_int(
                cfg.get("page") if "page" in cfg else os.getenv("DIFY_DATASETS_PAGE", 1),
                default=1,
                minimum=1,
            ),
            "limit": self._parse_int(
                cfg.get("limit") if "limit" in cfg else os.getenv("DIFY_DATASETS_LIMIT", 20),
                default=20,
                minimum=1,
                maximum=100,
            ),
            "include_all": self._parse_bool(
                cfg.get("include_all") if "include_all" in cfg else os.getenv("DIFY_DATASETS_INCLUDE_ALL", False)
            ),
        }
        self.retrieval_model = {
            "search_method": str(
                cfg.get("search_method")
                if "search_method" in cfg
                else os.getenv("DIFY_RETRIEVE_SEARCH_METHOD", "semantic_search")
            ).strip()
            or "semantic_search",
            "reranking_enable": self._parse_bool(
                cfg.get("reranking_enable")
                if "reranking_enable" in cfg
                else os.getenv("DIFY_RETRIEVE_RERANKING_ENABLE", False)
            ),
            "top_k": self._parse_int(
                cfg.get("top_k") if "top_k" in cfg else os.getenv("DIFY_RETRIEVE_TOP_K", 5),
                default=5,
                minimum=1,
                maximum=20,
            ),
            "score_threshold": self._parse_float(
                cfg.get("score_threshold")
                if "score_threshold" in cfg
                else os.getenv("DIFY_RETRIEVE_SCORE_THRESHOLD", 0.0),
                default=0.0,
                minimum=0.0,
                maximum=1.0,
            ),
        }

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _parse_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
        parsed = default
        try:
            if value not in (None, ""):
                parsed = int(value)
        except (TypeError, ValueError):
            parsed = default

        if minimum is not None:
            parsed = max(minimum, parsed)
        if maximum is not None:
            parsed = min(maximum, parsed)
        return parsed

    @staticmethod
    def _parse_float(value: Any, default: float, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
        parsed = default
        try:
            if value not in (None, ""):
                parsed = float(value)
        except (TypeError, ValueError):
            parsed = default

        if minimum is not None:
            parsed = max(minimum, parsed)
        if maximum is not None:
            parsed = min(maximum, parsed)
        return parsed

    @staticmethod
    def _normalize_tag_ids(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value or "").strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    @staticmethod
    def _clean_text(value: Any, max_len: int = 300) -> str:
        if value is None:
            return ""
        text = str(value)
        text = "".join(ch if ch >= " " or ch in "\n\t" else " " for ch in text)
        text = " ".join(text.split())
        if len(text) > max_len:
            return f"{text[:max_len]}..."
        return text

    @staticmethod
    def _normalize_base_url(url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return "https://api.dify.ai/v1"
        text = text.rstrip("/")
        if text.endswith("/datasets"):
            return text[: -len("/datasets")]
        return text

    def _build_dataset_discovery_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "page": self.dataset_query["page"],
            "limit": self.dataset_query["limit"],
        }
        keyword = self.dataset_query["keyword"]
        if keyword:
            params["keyword"] = keyword
        if self.dataset_query["tag_ids"]:
            params["tag_ids"] = self.dataset_query["tag_ids"]
        if self.dataset_query["include_all"]:
            params["include_all"] = True
        return params

    def _build_retrieve_query(self, task_note: str, retrieval_stage: str, draft_suggestion: str) -> str:
        query = self.dataset_query["keyword"]
        if not query and retrieval_stage == "review":
            query = self._clean_text(draft_suggestion, 200)
        if not query:
            query = self._clean_text(task_note, 200)
        if not query:
            query = "空分装置异常处置"
        return query

    def _build_retrieve_payload(self, query: str) -> Dict[str, Any]:
        score_threshold = float(self.retrieval_model["score_threshold"])
        return {
            "query": query,
            "retrieval_model": {
                "search_method": self.retrieval_model["search_method"],
                "reranking_enable": bool(self.retrieval_model["reranking_enable"]),
                "top_k": int(self.retrieval_model["top_k"]),
                "score_threshold_enabled": score_threshold > 0.0,
                "score_threshold": score_threshold,
            },
        }

    def _request_discovery(self, params: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.get(self.api_url, headers=headers, params=params, timeout=self.timeout_sec)
        except requests.RequestException as exc:
            raise RuntimeError(f"DIFY_DATASET_DISCOVERY_REQUEST_ERROR: {exc}") from exc

        if response.status_code != 200:
            detail = self._clean_text(response.text, 260)
            raise RuntimeError(f"DIFY_DATASET_DISCOVERY_HTTP_ERROR: HTTP {response.status_code} {detail}".strip())

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("DIFY_DATASET_DISCOVERY_RESPONSE_INVALID: response is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("DIFY_DATASET_DISCOVERY_RESPONSE_INVALID: response payload must be an object.")
        return payload

    def _request_retrieve(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        except requests.RequestException as exc:
            raise RuntimeError(f"DIFY_DATASET_RETRIEVE_REQUEST_ERROR: {exc}") from exc

        if response.status_code != 200:
            detail = self._clean_text(response.text, 260)
            raise RuntimeError(f"DIFY_DATASET_RETRIEVE_HTTP_ERROR: HTTP {response.status_code} {detail}".strip())

        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("DIFY_DATASET_RETRIEVE_RESPONSE_INVALID: response is not valid JSON.") from exc

        if not isinstance(result, dict):
            raise RuntimeError("DIFY_DATASET_RETRIEVE_RESPONSE_INVALID: response payload must be an object.")
        return result

    def _resolve_dataset_id(self) -> str:
        if self.resolved_dataset_id:
            return self.resolved_dataset_id

        if self.dataset_id:
            self.resolved_dataset_id = self.dataset_id
            self.resolved_dataset_name = ""
            self.resolved_dataset_source = "configured"
            return self.resolved_dataset_id

        payload = self._request_discovery(self._build_dataset_discovery_params())
        items = payload.get("data")
        if not isinstance(items, list):
            raise RuntimeError("DIFY_DATASET_DISCOVERY_RESPONSE_INVALID: `data` must be a list.")

        first_item = None
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_id = self._clean_text(item.get("id"), 80)
            if candidate_id:
                first_item = item
                break

        if not first_item:
            raise RuntimeError("DIFY_DATASET_DISCOVERY_EMPTY: no dataset available for retrieval.")

        self.resolved_dataset_id = self._clean_text(first_item.get("id"), 80)
        self.resolved_dataset_name = self._clean_text(first_item.get("name"), 120)
        self.resolved_dataset_source = "auto_discovered"
        self.dataset_id = self.resolved_dataset_id
        return self.resolved_dataset_id

    def _dataset_retrieve_url(self) -> str:
        dataset_id = self._resolve_dataset_id()
        if not dataset_id:
            raise RuntimeError("DIFY_DATASET_DISCOVERY_EMPTY: resolved dataset id is empty.")
        return f"{self.base_url}/datasets/{dataset_id}/retrieve"

    def _extract_retrieved_chunks(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_items = payload.get("records")
        if not isinstance(raw_items, list):
            raw_items = payload.get("data")
        if not isinstance(raw_items, list):
            raw_items = []

        chunks: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            segment = item.get("segment") if isinstance(item.get("segment"), dict) else {}
            document = segment.get("document") if isinstance(segment.get("document"), dict) else {}

            content = self._clean_text(
                segment.get("content")
                or item.get("content")
                or item.get("text")
                or "",
                1500,
            )
            title = self._clean_text(
                document.get("name")
                or item.get("document_name")
                or item.get("title")
                or f"chunk_{idx}",
                160,
            )
            chunks.append(
                {
                    "rank": idx,
                    "title": title or f"chunk_{idx}",
                    "score": item.get("score"),
                    "content": content,
                }
            )
        return chunks

    def _retrieve_via_dataset_chunks(
        self,
        task_note: str,
        retrieval_stage: str,
        draft_suggestion: str,
    ) -> Dict[str, Any]:
        retrieve_url = self._dataset_retrieve_url()
        effective_dataset_id = self._resolve_dataset_id()

        query = self._build_retrieve_query(task_note, retrieval_stage, draft_suggestion)
        payload = self._build_retrieve_payload(query)
        response_payload = self._request_retrieve(retrieve_url, payload)
        chunks = self._extract_retrieved_chunks(response_payload)

        knowledge_references: List[Any] = []
        for chunk in chunks:
            knowledge_references.append(
                {
                    "source": chunk.get("title") or "未命名片段",
                    "doc_id": effective_dataset_id,
                    "relevance_score": chunk.get("score"),
                    "content": chunk.get("content") or "",
                }
            )

        recommended_measures: List[Dict[str, Any]] = []
        for chunk in chunks[:3]:
            recommended_measures.append(
                {
                    "title": f"参考知识片段：{chunk.get('title')}",
                    "target_issue": f"知识库片段 rank={chunk.get('rank')}",
                    "steps": "优先按该片段中的操作约束执行，再由班组人工复核与现场确认。",
                    "expected_effect": "通过知识库命中片段提升决策可追溯性与一致性。",
                    "safety_note": "任何建议都必须经过联锁边界与现场审批核验后执行。",
                    "priority": "medium",
                }
            )

        risk_tips: List[str] = []
        if not chunks:
            risk_tips.append("外挂知识库检索未命中有效片段，请检查 dataset_id、query 或阈值配置。")

        retrieval_summary = (
            f"外挂知识库 API 召回完成：命中 {len(chunks)} 个片段"
            f"（dataset_id={effective_dataset_id}, top_k={self.retrieval_model['top_k']}）。"
        )
        return {
            "retrieval_stage": str(retrieval_stage or "primary"),
            "retrieval_summary": retrieval_summary,
            "recommended_measures": recommended_measures,
            "knowledge_references": knowledge_references,
            "risk_tips": risk_tips[:5],
            "datasets": [],
            "records": chunks,
            "resolved_dataset": {
                "id": effective_dataset_id,
                "name": self.resolved_dataset_name,
                "source": self.resolved_dataset_source or "configured",
            },
            "raw_response": json.dumps(response_payload, ensure_ascii=False),
        }

    def retrieve_measures(
        self,
        overall_judgement: Dict[str, Any],
        abnormal_details: List[Dict[str, Any]],
        task_note: str = "",
        retrieval_stage: str = "primary",
        draft_suggestion: str = "",
    ) -> Dict[str, Any]:
        note = self._clean_text(task_note, 200)
        if not note:
            note = self._clean_text((overall_judgement or {}).get("summary"), 200)
        if not note and abnormal_details:
            names = [
                self._clean_text(item.get("name"), 80)
                for item in abnormal_details
                if isinstance(item, dict) and item.get("name")
            ]
            note = self._clean_text("，".join(names[:3]), 200)

        return self._retrieve_via_dataset_chunks(note, retrieval_stage, draft_suggestion)
