import json

from src.services.decision_service import DecisionService


def test_decision_service_closed_loop_feedback_status_and_case_writeback(tmp_path):
    case_path = tmp_path / "decision_cases.jsonl"
    service = DecisionService(case_store_path=str(case_path))
    reasoning_result = {
        "root_cause": "压差偏高",
        "operation_suggestion": "降低负荷",
        "safety_warning": "关注联锁",
    }
    feedback = {
        "window_start": "2026-03-10T10:00:00",
        "window_end": "2026-03-10T10:15:00",
        "before": {"dp": 120.0, "energy": 98.0},
        "after": {"dp": 112.0, "energy": 95.0},
        "direction": {"dp": "decrease", "energy": "decrease"},
    }

    result = service.verify_and_suggest(
        reasoning_result=reasoning_result,
        execution_feedback=feedback,
        enable_closed_loop_validation=True,
    )

    assert result["closed_loop_validation"]["status"] == "passed"
    assert result["closed_loop_validation"]["improvement_ratio"] == 1.0

    lines = case_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["closed_loop_status"] == "passed"
    assert "改善" in payload["closed_loop_summary"]


def test_decision_service_closed_loop_feedback_pending_when_missing(tmp_path):
    service = DecisionService(case_store_path=str(tmp_path / "decision_cases.jsonl"))
    result = service.evaluate_closed_loop_feedback(None)
    assert result["status"] == "pending"
