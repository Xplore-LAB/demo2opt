from __future__ import annotations

import pytest

from src.services.knowledge_retrieval_service import KnowledgeRetrievalService


def test_service_uses_env_when_config_missing(monkeypatch):
    monkeypatch.setenv("DIFY_DATASETS_API_URL", "https://api.dify.ai/v1/datasets")
    monkeypatch.setenv("DIFY_API_KEY", "env-key")
    monkeypatch.delenv("DIFY_DATASET_ID", raising=False)

    service = KnowledgeRetrievalService()
    assert service.api_url == "https://api.dify.ai/v1/datasets"
    assert service.api_key == "env-key"


def test_service_parses_dataset_query_options_from_config():
    service = KnowledgeRetrievalService(
        {
            "api_url": "https://api.dify.ai/v1/datasets",
            "api_key": "dataset-key",
            "keyword": "main exchanger",
            "tag_ids": ["a", "b"],
            "page": "2",
            "limit": "200",
            "include_all": "true",
            "timeout_sec": "9",
        }
    )

    assert service.timeout_sec == 9
    assert service.dataset_query["keyword"] == "main exchanger"
    assert service.dataset_query["tag_ids"] == ["a", "b"]
    assert service.dataset_query["page"] == 2
    assert service.dataset_query["limit"] == 100
    assert service.dataset_query["include_all"] is True


def test_retrieve_measures_uses_review_draft_when_task_note_empty(monkeypatch):
    captured = {}

    class _PostResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"records": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _PostResponse()

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.post", fake_post)

    service = KnowledgeRetrievalService(
        {
            "api_url": "https://api.dify.ai/v1/datasets",
            "api_key": "dataset-key",
            "dataset_id": "kb-001",
            "top_k": 4,
        }
    )

    service.retrieve_measures(
        overall_judgement={},
        abnormal_details=[],
        task_note="",
        retrieval_stage="review",
        draft_suggestion="reduce reflux ratio",
    )

    assert captured["url"] == "https://api.dify.ai/v1/datasets/kb-001/retrieve"
    assert captured["headers"]["Authorization"] == "Bearer dataset-key"
    assert captured["json"]["query"] == "reduce reflux ratio"
    assert captured["json"]["retrieval_model"]["top_k"] == 4


def test_dataset_discovery_raises_on_http_error(monkeypatch):
    class _FakeResponse:
        status_code = 401
        text = "unauthorized"

        @staticmethod
        def json():
            return {}

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", lambda *args, **kwargs: _FakeResponse())

    service = KnowledgeRetrievalService(
        {
            "api_url": "https://api.dify.ai/v1/datasets",
            "api_key": "dataset-key",
            "dataset_id": "",
        }
    )

    with pytest.raises(RuntimeError, match="DIFY_DATASET_DISCOVERY_HTTP_ERROR"):
        service.retrieve_measures(overall_judgement={}, abnormal_details=[])


def test_dataset_discovery_raises_on_invalid_json(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            raise ValueError("invalid json")

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", lambda *args, **kwargs: _FakeResponse())

    service = KnowledgeRetrievalService(
        {
            "api_url": "https://api.dify.ai/v1/datasets",
            "api_key": "dataset-key",
            "dataset_id": "",
        }
    )

    with pytest.raises(RuntimeError, match="DIFY_DATASET_DISCOVERY_RESPONSE_INVALID"):
        service.retrieve_measures(overall_judgement={}, abnormal_details=[])
