import pytest
import requests

from src.services.knowledge_retrieval_service import KnowledgeRetrievalService


def test_base_api_url_auto_appends_datasets_suffix():
    service = KnowledgeRetrievalService({"api_url": "http://localhost/v1", "api_key": "k"})
    assert service.api_url == "http://localhost/v1/datasets"


def test_retrieve_measures_with_explicit_dataset_id_uses_only_retrieve_api(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "records": [
                    {
                        "score": 0.91,
                        "segment": {
                            "content": "先校验膨胀机B进出口温压，再确认导叶开度。",
                            "document": {"name": "空分操作规程-膨胀机章节"},
                        },
                    }
                ]
            }

    def fake_get(*args, **kwargs):
        raise AssertionError("explicit dataset_id should not trigger dataset discovery")

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", fake_get)
    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.post", fake_post)

    service = KnowledgeRetrievalService(
        {
            "api_url": "http://localhost/v1",
            "api_key": "dataset-key",
            "dataset_id": "kb-123",
            "top_k": 3,
        }
    )
    result = service.retrieve_measures(
        overall_judgement={},
        abnormal_details=[],
        task_note="膨胀机B制冷量偏低",
    )

    assert captured["url"] == "http://localhost/v1/datasets/kb-123/retrieve"
    assert captured["headers"]["Authorization"] == "Bearer dataset-key"
    assert captured["json"]["query"] == "膨胀机B制冷量偏低"
    assert captured["json"]["retrieval_model"]["top_k"] == 3
    assert "召回完成：命中 1 个片段" in result["retrieval_summary"]
    assert result["resolved_dataset"]["id"] == "kb-123"
    assert result["resolved_dataset"]["source"] == "configured"


def test_retrieve_measures_auto_discovers_dataset_once_and_caches(monkeypatch):
    get_count = {"value": 0}
    post_urls = []
    monkeypatch.delenv("DIFY_DATASET_ID", raising=False)

    class _GetResp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "data": [
                    {"id": "kb-auto-1", "name": "Auto KB"},
                    {"id": "kb-auto-2", "name": "Backup KB"},
                ],
                "has_more": False,
                "limit": 20,
                "total": 2,
                "page": 1,
            }

    class _PostResp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"records": []}

    def fake_get(url, headers=None, params=None, timeout=None):
        get_count["value"] += 1
        return _GetResp()

    def fake_post(url, headers=None, json=None, timeout=None):
        post_urls.append(url)
        return _PostResp()

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", fake_get)
    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.post", fake_post)

    service = KnowledgeRetrievalService(
        {
            "api_url": "http://localhost/v1",
            "api_key": "dataset-key",
        }
    )

    first = service.retrieve_measures(overall_judgement={}, abnormal_details=[], task_note="first")
    second = service.retrieve_measures(overall_judgement={}, abnormal_details=[], task_note="second")

    assert get_count["value"] == 1
    assert post_urls == [
        "http://localhost/v1/datasets/kb-auto-1/retrieve",
        "http://localhost/v1/datasets/kb-auto-1/retrieve",
    ]
    assert first["resolved_dataset"]["id"] == "kb-auto-1"
    assert first["resolved_dataset"]["source"] == "auto_discovered"
    assert second["resolved_dataset"]["id"] == "kb-auto-1"


def test_dataset_discovery_raises_when_empty(monkeypatch):
    class _Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"data": []}

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", lambda *args, **kwargs: _Resp())

    service = KnowledgeRetrievalService(
        {
            "api_url": "http://localhost/v1",
            "api_key": "dataset-key",
            "dataset_id": "",
        }
    )
    with pytest.raises(RuntimeError, match="DIFY_DATASET_DISCOVERY_EMPTY"):
        service.retrieve_measures(overall_judgement={}, abnormal_details=[], task_note="test")


def test_dataset_discovery_request_exception(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", fake_get)

    service = KnowledgeRetrievalService(
        {
            "api_url": "http://localhost/v1",
            "api_key": "dataset-key",
            "dataset_id": "",
        }
    )

    with pytest.raises(RuntimeError, match="DIFY_DATASET_DISCOVERY_REQUEST_ERROR"):
        service.retrieve_measures(overall_judgement={}, abnormal_details=[])
