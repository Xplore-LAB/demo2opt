import asyncio
import json

import pytest

import src.api.ws.server as ws_server
from src.api.ws.server import WebOptimizer


class DummyWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(json.loads(message))


def test_send_phase_update_includes_progress_fields():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    asyncio.run(optimizer.send_phase_update("analysis", "running", 3))

    assert ws.sent
    payload = ws.sent[-1]
    assert payload["type"] == "phase_update"
    assert payload["phase"] == "analysis"
    assert payload["status"] == "running"
    assert payload["step"] == 3
    assert "progress_percent" in payload
    assert "eta_sec" in payload
    assert payload["workflow_step_id"] == 5
    assert payload["workflow_step_title"] == "时序特征提取与候选复核"


def test_send_phase_update_includes_step_state_fields():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    asyncio.run(
        optimizer.send_phase_update(
            "analysis",
            "running",
            4,
            workflow_step_id=7,
            workflow_step_title="AI 根因诊断",
            workflow_step_state="started",
            step_started_at="2026-03-05T12:00:00",
        )
    )

    assert ws.sent
    payload = ws.sent[-1]
    assert payload["type"] == "phase_update"
    assert payload["workflow_step_id"] == 7
    assert payload["workflow_step_title"] == "AI 根因诊断"
    assert payload["workflow_step_state"] == "started"
    assert payload["step_started_at"] == "2026-03-05T12:00:00"


def test_send_phase_update_includes_error_fields():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    asyncio.run(
        optimizer.send_phase_update(
            "analysis",
            "error",
            workflow_step_id=6,
            workflow_step_state="failed",
            error_code="LLM_UPSTREAM_ERROR",
            error_class="upstream",
            error_message="timeout",
        )
    )

    payload = ws.sent[-1]
    assert payload["type"] == "phase_update"
    assert payload["status"] == "error"
    assert payload["error_code"] == "LLM_UPSTREAM_ERROR"
    assert payload["error_class"] == "upstream"
    assert payload["error_message"] == "timeout"


def test_request_interaction_extended_fields_non_blocking():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    result = asyncio.run(
        optimizer.request_interaction(
            title="高风险附加确认",
            desc="检测到高风险候选。",
            checkpoint_key="analysis_high_risk_confirm",
            phase="analysis",
            risk_level="critical",
            impact_scope=["主换热器", "负荷"],
            recommended_action="继续高风险复核",
            blocking=False,
        )
    )

    assert result == "yes"
    interaction_payload = ws.sent[0]
    assert interaction_payload["type"] == "interaction"
    assert interaction_payload["checkpoint_key"] == "analysis_high_risk_confirm"
    assert interaction_payload["phase"] == "analysis"
    assert interaction_payload["risk_level"] == "critical"
    assert interaction_payload["impact_scope"] == ["主换热器", "负荷"]
    assert interaction_payload["recommended_action"] == "继续高风险复核"
    assert interaction_payload["blocking"] is False
    assert interaction_payload["workflow_step_id"] == 7
    assert interaction_payload["workflow_step_title"] == "AI 根因诊断"


def test_llm_activity_lifecycle_with_same_event_id():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    event_id = asyncio.run(
        optimizer.start_llm_task(
            task_key="root_cause_diagnosis",
            task_label="根因诊断",
            phase="analysis",
            workflow_step_id=7,
            provider="direct",
            model="gpt-4o-mini",
        )
    )
    asyncio.run(optimizer.finish_llm_task(event_id, status="failed", message="timeout"))

    assert len(ws.sent) == 2
    started_payload = ws.sent[0]
    finished_payload = ws.sent[1]

    assert started_payload["type"] == "llm_activity"
    assert started_payload["status"] == "started"
    assert started_payload["task_key"] == "root_cause_diagnosis"
    assert started_payload["task_label"] == "根因诊断"
    assert started_payload["workflow_step_id"] == 7
    assert started_payload["workflow_step_title"] == "AI 根因诊断"
    assert started_payload["provider"] == "direct"
    assert started_payload["model"] == "gpt-4o-mini"

    assert finished_payload["type"] == "llm_activity"
    assert finished_payload["status"] == "failed"
    assert finished_payload["event_id"] == started_payload["event_id"] == event_id
    assert finished_payload["message"] == "timeout"


def test_send_monitor_update_includes_overview_payloads():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    asyncio.run(
        optimizer.send_monitor_update(
            [{"tag_id": "A", "name": "压缩机电耗"}],
            [{"tag_id": "A", "name": "压缩机电耗", "level": "偏高"}],
            "semantic_ready",
            visualization_context={"data_curve_overview": {"category_count": 2}},
            overall_judgement={"summary": "当前处于风险上升阶段"},
            semantic_summary={"plant_state": "risk_rising"},
            data_overview={"file_name": "demo.xlsx"},
        )
    )

    payload = ws.sent[-1]
    assert payload["type"] == "monitor_update"
    assert payload["data"]["stage"] == "semantic_ready"
    assert payload["data"]["visualization_context"]["data_curve_overview"]["category_count"] == 2
    assert payload["data"]["overall_judgement"]["summary"] == "当前处于风险上升阶段"
    assert payload["data"]["semantic_summary"]["plant_state"] == "risk_rising"
    assert payload["data"]["data_overview"]["file_name"] == "demo.xlsx"


def test_resolve_file_accepts_sample_source(tmp_path, monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sample_file = data_dir / "demo.xlsx"
    sample_file.write_bytes(b"sample")
    monkeypatch.chdir(tmp_path)

    file_path, temp_file, display_name = optimizer._resolve_file(
        {
            "data_source": "sample",
            "sample_file": "data/demo.xlsx",
        }
    )

    assert temp_file is None
    assert file_path == str(sample_file.resolve())
    assert display_name == "demo.xlsx"


def test_resolve_file_rejects_invalid_sample_path(tmp_path, monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(Exception) as exc_info:
        optimizer._resolve_file(
            {
                "data_source": "sample",
                "sample_file": "../outside.xlsx",
            }
        )

    error_code, error_class = optimizer._classify_error(exc_info.value)
    assert error_code == "SAMPLE_FILE_INVALID"
    assert error_class == "data_source"


def test_resolve_file_upload_source_requires_file_data():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)

    with pytest.raises(Exception) as exc_info:
        optimizer._resolve_file({"data_source": "upload"})

    error_code, error_class = optimizer._classify_error(exc_info.value)
    assert error_code == "DATA_SOURCE_REQUIRED"
    assert error_class == "data_source"


def test_resolve_file_legacy_fallback_still_works(tmp_path, monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "b.xlsx").write_bytes(b"b")
    (data_dir / "a.xlsx").write_bytes(b"a")
    monkeypatch.chdir(tmp_path)

    file_path, temp_file, display_name = optimizer._resolve_file({})

    assert temp_file is None
    assert file_path.endswith("a.xlsx")
    assert display_name == "a.xlsx"


def test_resolve_required_dify_config_requires_api_key(monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)

    with pytest.raises(Exception) as exc_info:
        optimizer._resolve_required_dify_config({})

    assert "缺少 API Key" in str(exc_info.value)


def test_resolve_required_dify_config_includes_dataset_and_retrieve_fields(monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    monkeypatch.setenv("DIFY_API_KEY", "env-k")
    monkeypatch.setenv("DIFY_DATASET_ID", "env-ds")
    monkeypatch.setenv("DIFY_RETRIEVE_TOP_K", "7")
    monkeypatch.setenv("DIFY_RETRIEVE_SEARCH_METHOD", "hybrid_search")
    monkeypatch.setenv("DIFY_RETRIEVE_RERANKING_ENABLE", "true")
    monkeypatch.setenv("DIFY_RETRIEVE_SCORE_THRESHOLD", "0.4")

    cfg = optimizer._resolve_required_dify_config(
        {
            "dify_config": {
                "api_url": "http://localhost/v1",
                "api_key": "cfg-k",
            }
        }
    )

    assert cfg["api_mode"] == "datasets_retrieve"
    assert cfg["dataset_id"] == "env-ds"
    assert cfg["top_k"] == "7"
    assert cfg["search_method"] == "hybrid_search"
    assert cfg["reranking_enable"] == "true"
    assert cfg["score_threshold"] == "0.4"


def test_run_analysis_forwards_auto_confirm(monkeypatch):
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    captured = {}

    monkeypatch.setattr(
        optimizer,
        "_resolve_file",
        lambda _params: ("D:/mock/demo.xlsx", None, "demo.xlsx"),
    )
    monkeypatch.setattr(
        optimizer,
        "_resolve_required_dify_config",
        lambda _params: {"api_url": "http://localhost/v1", "api_key": "demo-key"},
    )

    async def fake_arun_analysis(payload, hooks=None):
        captured.update(payload)
        return {"analysis_result": {}}

    async def fake_finalize(_state):
        return None

    monkeypatch.setattr(ws_server, "arun_analysis", fake_arun_analysis)
    monkeypatch.setattr(optimizer, "_finalize_runner_result", fake_finalize)

    asyncio.run(
        optimizer.run_analysis(
            {
                "type": "start",
                "data_source": "sample",
                "sample_file": "data/demo.xlsx",
                "auto_confirm": True,
            }
        )
    )

    assert captured["entrypoint"] == "ws"
    assert captured["auto_confirm"] is True


def test_finalize_runner_result_includes_calculation_audit():
    ws = DummyWebSocket()
    optimizer = WebOptimizer(ws)
    optimizer.current_task_id = optimizer.task_manager.create_task(total_steps=1)

    state = {
        "analysis_result": {
            "status": "abnormal",
            "report_pdf": "reports/demo.pdf",
            "report_md": "reports/demo.md",
            "abnormal_details": [{"name": "膨胀机B制冷量"}],
            "reasoning_result": {"root_cause": "冷量不足", "operation_suggestion": "先核查", "safety_warning": "守住联锁"},
            "decision_result": {"actionable_steps": "先核查", "verification_status": "Passed"},
            "semantic_data": [{"name": "膨胀机B制冷量"}],
            "analysis_steps": [],
            "overall_judgement": {"summary": "当前装置处于高风险状态"},
            "calculation_audit": {
                "data_intake": {"layout_detected": "wide_table"},
                "indicators": [{"name": "膨胀机B制冷量", "severity_score": 1.4821}],
                "subsystems": [],
                "plant": {"max_severity": 1.4821},
            },
            "history_model_metadata": {"profile_source": "runtime", "selected_regime": "low"},
            "data_overview": {"file_name": "demo.xlsx"},
            "semantic_summary": {"plant_state": "abnormal_unstable"},
            "semantic_ai_review": {},
            "knowledge_retrieval": {},
            "optimization_context": {},
            "visualization_context": {},
            "traceability": {},
        }
    }

    asyncio.run(optimizer._finalize_runner_result(state))

    result_payload = next(item for item in ws.sent if item["type"] == "result")
    assert result_payload["type"] == "result"
    assert result_payload["data"]["calculation_audit"]["plant"]["max_severity"] == 1.4821
    assert result_payload["data"]["history_model_metadata"]["selected_regime"] == "low"
