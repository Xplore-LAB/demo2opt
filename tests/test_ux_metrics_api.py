from datetime import datetime

import pytest

from src.api.rest import server


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(server, "UX_METRICS_FILE", tmp_path / "ux_metrics.jsonl")
    server.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return server.app.test_client()


def test_collect_ux_metric_requires_fields(client):
    resp = client.post("/api/ux-metrics", json={})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False


def test_collect_and_summarize_ux_metrics(client):
    now = datetime.now().isoformat()
    session_id = "session-test-1"

    events = [
        {"event_name": "task_started", "session_id": session_id, "client_time": now},
        {"event_name": "key_action_card_rendered", "session_id": session_id, "client_time": now},
        {"event_name": "interaction_prompt_shown", "session_id": session_id, "interaction_id": "i-1", "risk_level": "high", "client_time": now},
        {"event_name": "interaction_answered", "session_id": session_id, "interaction_id": "i-1", "client_time": now},
        {"event_name": "task_finished", "session_id": session_id, "client_time": now},
    ]

    for payload in events:
        resp = client.post("/api/ux-metrics", json=payload)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    report = client.get("/api/ux-metrics/weekly?days=7")
    assert report.status_code == 200
    body = report.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["records"] >= 5
    assert data["event_counts"]["task_started"] >= 1
    assert data["event_counts"]["task_finished"] >= 1
    assert data["risk_level_counts"]["high"] >= 1
    assert data["completion_rate"] is not None
