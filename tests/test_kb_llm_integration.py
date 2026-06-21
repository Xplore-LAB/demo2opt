import json
import os

import pytest

from src.services.knowledge_retrieval_service import KnowledgeRetrievalService
from src.services.reasoning_engine_v2 import ReasoningEngineV2


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "ok"

    def json(self):
        return self._payload


def test_external_knowledge_api_request_contract(monkeypatch):
    captured = {"get": None, "post": None}
    monkeypatch.delenv("DIFY_DATASET_ID", raising=False)

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["get"] = {
            "url": url,
            "headers": headers or {},
            "params": params or {},
            "timeout": timeout,
        }
        return _DummyResponse(
            200,
            {
                "data": [
                    {
                        "id": "kb-1",
                        "name": "空分知识库",
                        "provider": "dify",
                        "document_count": 12,
                        "word_count": 10240,
                        "embedding_available": True,
                    }
                ],
                "has_more": False,
                "limit": 20,
                "total": 1,
                "page": 1,
            },
        )

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["post"] = {
            "url": url,
            "headers": headers or {},
            "json": json or {},
            "timeout": timeout,
        }
        return _DummyResponse(
            200,
            {
                "records": [
                    {
                        "score": 0.88,
                        "segment": {
                            "content": "优先检查主换热器温差与液位控制。",
                            "document": {"name": "空分装置检修SOP"},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.get", fake_get)
    monkeypatch.setattr("src.services.knowledge_retrieval_service.requests.post", fake_post)

    service = KnowledgeRetrievalService(
        {
            "api_url": "http://localhost/v1",
            "api_key": "dataset-key",
            "page": 1,
            "limit": 20,
            "include_all": False,
        }
    )
    result = service.retrieve_measures(
        overall_judgement={"summary": "高风险异常"},
        abnormal_details=[{"name": "主换冷损"}],
        task_note="主换冷损偏高",
        retrieval_stage="primary",
    )

    assert captured["get"]["url"] == "http://localhost/v1/datasets"
    assert captured["get"]["headers"]["Authorization"] == "Bearer dataset-key"
    assert captured["get"]["params"]["page"] == 1
    assert captured["get"]["params"]["limit"] == 20
    assert captured["get"]["timeout"] == 30

    assert captured["post"]["url"] == "http://localhost/v1/datasets/kb-1/retrieve"
    assert captured["post"]["headers"]["Authorization"] == "Bearer dataset-key"
    assert captured["post"]["json"]["query"] == "主换冷损偏高"
    assert captured["post"]["json"]["retrieval_model"]["top_k"] == 5
    assert captured["post"]["timeout"] == 30

    assert result["retrieval_stage"] == "primary"
    assert "外挂知识库 API 召回完成" in result["retrieval_summary"]
    assert len(result["records"]) == 1
    assert len(result["recommended_measures"]) == 1
    assert len(result["knowledge_references"]) == 1


@pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_KB_LIVE_TEST", "0") != "1",
    reason="Set RUN_EXTERNAL_KB_LIVE_TEST=1 to run live external knowledge API smoke test.",
)
def test_external_knowledge_api_live_smoke():
    api_url = os.getenv("DIFY_DATASETS_API_URL") or os.getenv("DIFY_API_URL")
    api_key = os.getenv("DIFY_API_KEY")
    if not api_url or not api_key:
        pytest.skip("Missing DIFY_DATASETS_API_URL/DIFY_API_URL or DIFY_API_KEY.")

    service = KnowledgeRetrievalService(
        {
            "api_url": api_url,
            "api_key": api_key,
            "dataset_id": os.getenv("DIFY_DATASET_ID", ""),
            "page": 1,
            "limit": 5,
        }
    )
    result = service.retrieve_measures(
        overall_judgement={"summary": "空分工况异常"},
        abnormal_details=[],
        task_note="空分工况",
        retrieval_stage="primary",
    )

    assert result["retrieval_stage"] == "primary"
    assert "外挂知识库 API 召回完成" in result["retrieval_summary"]
    assert isinstance(result["records"], list)
    assert isinstance(result["recommended_measures"], list)
    assert isinstance(result["knowledge_references"], list)
    assert isinstance(result["risk_tips"], list)


@pytest.mark.skipif(
    os.getenv("RUN_LLM_KB_LIVE_TEST", "0") != "1",
    reason="Set RUN_LLM_KB_LIVE_TEST=1 to run live LLM + external knowledge API integration test.",
)
def test_live_llm_with_external_knowledge_api():
    required_env = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME", "DIFY_API_KEY")
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")

    retrieval_service = KnowledgeRetrievalService(
        {
            "api_url": os.getenv("DIFY_DATASETS_API_URL") or os.getenv("DIFY_API_URL", "http://localhost/v1"),
            "api_key": os.getenv("DIFY_API_KEY"),
            "dataset_id": os.getenv("DIFY_DATASET_ID", ""),
            "page": 1,
            "limit": 5,
        }
    )
    knowledge_context = retrieval_service.retrieve_measures(
        overall_judgement={"summary": "冷量系统异常，需定位根因。"},
        abnormal_details=[],
        task_note="膨胀机B制冷量偏低",
        retrieval_stage="primary",
    )

    engine = ReasoningEngineV2()
    semantic_data = [
        {
            "tag_id": "demo-1",
            "name": "1#膨胀机B制冷量",
            "current_value": 69.9,
            "diff": -290.1,
            "state_desc": "严重偏低",
            "assessment_reason": "相对参考值偏低且持续时间长",
            "comparison_summary": "相对参考值偏差约-80%",
            "reference_label": "reference",
            "reference_value": 360.0,
            "membership_degree": 0.15,
            "semantic_state": "abnormal",
        }
    ]
    abnormal_items = [
        {
            "name": "1#膨胀机B制冷量",
            "current_value": 69.9,
            "diff": -290.1,
            "diff_percent": -80.6,
            "state_desc": "严重偏低",
        }
    ]
    overall_judgement = {
        "summary": "当前装置处于异常失稳态，主矛盾集中在冷量系统。",
        "plant_state": "abnormal_unstable",
        "plant_state_label": "异常失稳态",
    }

    raw = engine.analyze(
        semantic_data=semantic_data,
        abnormal_items=abnormal_items,
        enable_cot=True,
        knowledge_context=knowledge_context,
        overall_judgement=overall_judgement,
        task_note="联调测试：外部知识库+大模型",
    )

    payload = json.loads(raw)
    assert isinstance(payload, dict)
    assert isinstance(payload.get("root_cause"), str) and payload["root_cause"].strip()
    assert isinstance(payload.get("operation_suggestion"), str) and payload["operation_suggestion"].strip()
    assert isinstance(payload.get("safety_warning"), str) and payload["safety_warning"].strip()
    assert isinstance(payload.get("indicator_diagnoses"), list)
