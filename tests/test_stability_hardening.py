import inspect
import json
from types import SimpleNamespace

import requests

from src.api.ws import server as ws_server
from src.prompts.templates import DifyAPIClient, SimpleLLMClient
from src.services import data_semantics
from src.utils.business_logic import ABNORMAL_STATES, is_abnormal_state


def test_server_uses_to_thread_for_specs_update():
    source = inspect.getsource(ws_server.WebOptimizer.run_analysis)
    assert "await asyncio.to_thread(semantics_service.update_specs_from_csv_data, all_records)" in source


def test_simple_llm_client_retries_then_succeeds(monkeypatch):
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.Timeout("timeout")
        return DummyResponse()

    monkeypatch.setattr("src.prompts.templates.requests.post", fake_post)
    monkeypatch.setattr("src.prompts.templates.time.sleep", lambda *_: None)

    client = SimpleLLMClient(
        api_url="https://example.com/v1/chat/completions",
        api_key="test",
        model_name="gpt-4o-mini",
        timeout_sec=1,
        max_retries=3,
        retry_backoff_sec=0.01,
    )

    result = client.chat("hello")
    assert result["ok"] is True
    assert result["answer"] == "ok"
    assert calls["count"] == 3


def test_simple_llm_client_falls_back_to_non_stream_when_stream_transport_fails(monkeypatch):
    class StreamResponse:
        headers = {"content-type": "text/event-stream"}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_lines(decode_unicode=True):
            return iter([])

    class NonStreamResponse:
        headers = {"content-type": "application/json"}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    calls = {"stream": 0, "non_stream": 0}

    def fake_post(*args, **kwargs):
        if kwargs.get("stream"):
            calls["stream"] += 1
            raise requests.exceptions.SSLError("EOF occurred in violation of protocol")
        calls["non_stream"] += 1
        return NonStreamResponse()

    monkeypatch.setattr("src.prompts.templates.requests.post", fake_post)

    client = SimpleLLMClient(
        api_url="https://example.com/v1/chat/completions",
        api_key="test",
        model_name="mimo-v2.5-pro",
        timeout_sec=1,
        max_retries=0,
    )

    result = client.chat("hello")

    assert result["ok"] is True
    assert result["answer"] == "ok"
    assert calls["stream"] == 1
    assert calls["non_stream"] == 1


def test_dify_client_returns_structured_error(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network down")

    monkeypatch.setattr("src.prompts.templates.requests.post", fake_post)
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello")

    assert result["ok"] is False
    assert result["error"]["code"] == "DIFY_REQUEST_ERROR"


def test_dify_client_http_error_contains_status_and_detail(monkeypatch):
    class DummyResponse:
        status_code = 400
        text = '{"message":"query too long"}'

        @staticmethod
        def json():
            return {"message": "query too long"}

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("400 Client Error", response=self)

    monkeypatch.setattr("src.prompts.templates.requests.post", lambda *args, **kwargs: DummyResponse())
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello")

    assert result["ok"] is False
    assert result["error"]["code"] == "DIFY_REQUEST_ERROR"
    assert result["error"]["status_code"] == 400
    assert "query too long" in result["error"]["message"]


def test_dify_client_non_json_response_returns_structured_error(monkeypatch):
    class DummyResponse:
        status_code = 200
        text = "<html>ok</html>"

        @staticmethod
        def json():
            raise ValueError("not json")

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.prompts.templates.requests.post", lambda *args, **kwargs: DummyResponse())
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello")

    assert result["ok"] is False
    assert result["error"]["code"] == "DIFY_RESPONSE_INVALID"
    assert result["error"]["status_code"] == 200


def test_dify_client_streaming_chat_accumulates_answer(monkeypatch):
    class DummyResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_lines(decode_unicode=True):
            return iter(
                [
                    'data: {"event":"workflow_started"}',
                    'data: {"event":"message","answer":"hello "}',
                    'data: {"event":"message","answer":"world"}',
                    'data: {"event":"message_end"}',
                ]
            )

    monkeypatch.setattr("src.prompts.templates.requests.post", lambda *args, **kwargs: DummyResponse())
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello", response_mode="streaming")

    assert result["ok"] is True
    assert result["answer"] == "hello world"


def test_dify_client_streaming_chat_incomplete_returns_structured_error(monkeypatch):
    class DummyResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_lines(decode_unicode=True):
            return iter(
                [
                    'data: {"event":"workflow_started"}',
                    "event: ping",
                ]
            )

    monkeypatch.setattr("src.prompts.templates.requests.post", lambda *args, **kwargs: DummyResponse())
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello", response_mode="streaming")

    assert result["ok"] is False
    assert result["error"]["code"] == "DIFY_STREAM_INCOMPLETE"


def test_dify_client_streaming_workflow_failed_returns_structured_error(monkeypatch):
    class DummyResponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def iter_lines(decode_unicode=True):
            return iter(
                [
                    'data: {"event":"workflow_started"}',
                    'data: {"event":"workflow_finished","data":{"status":"failed","error":"model dns failed","outputs":{}}}',
                ]
            )

    monkeypatch.setattr("src.prompts.templates.requests.post", lambda *args, **kwargs: DummyResponse())
    client = DifyAPIClient(api_url="http://localhost/v1/chat-messages", api_key="test", timeout_sec=1)
    result = client.chat("hello", response_mode="streaming")

    assert result["ok"] is False
    assert result["error"]["code"] == "DIFY_WORKFLOW_FAILED"
    assert "model dns failed" in result["error"]["message"]


def test_data_semantics_loads_external_yaml_like_config(monkeypatch, tmp_path):
    config_payload = {
        "indicator_profiles": {
            "TAG_1": {
                "objective": "minimize",
                "category": "娴嬭瘯鎸囨爣",
                "industry_benchmark": 10.0,
                "summary_good": "good",
                "summary_bad": "bad",
            }
        },
        "membership": {"state_weights": {"Unknown": 0.11}},
        "severity": {"diff_weight": 0.5, "duration_weight": 0.01},
        "expander": {"idle_threshold": 12.5},
    }
    config_path = tmp_path / "indicators.yaml"
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False), encoding="utf-8")

    yaml_stub = SimpleNamespace(
        safe_load=lambda stream: json.loads(stream.read() if hasattr(stream, "read") else stream)
    )
    monkeypatch.setattr(data_semantics, "yaml", yaml_stub)
    monkeypatch.setenv("SEMANTICS_CONFIG_PATH", str(config_path))

    service = data_semantics.DataSemanticsService()
    assert "TAG_1" in service.indicator_profiles
    assert service.membership_weights["Unknown"] == 0.11
    assert service.severity_config["diff_weight"] == 0.5
    assert service.expander_idle_threshold == 12.5


def test_is_abnormal_state_shared_logic():
    assert is_abnormal_state(next(iter(ABNORMAL_STATES))) is True
    assert is_abnormal_state("healthy") is False
    assert is_abnormal_state("") is False
