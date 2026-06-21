import json

from scripts import run_interactive


class _FakeLoader:
    def __init__(self, _file_path):
        pass

    def load_and_standardize(self):
        return {
            "records": [
                {"tag_id": "A", "name": "A", "value": 75.0, "design_ref": 70.0, "timestamp": "2026-03-09T10:00:00"},
                {"tag_id": "B", "name": "B", "value": 65.0, "design_ref": 70.0, "timestamp": "2026-03-09T10:00:00"},
                {"tag_id": "A", "name": "A", "value": 90.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
                {"tag_id": "B", "name": "B", "value": 62.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
            ],
            "parsing_audit": {"layout_detected": "wide_table", "data_start_row": 1},
        }


class _FakeCoreIndicators:
    def dict(self):
        return {}


class _FakeSemantics:
    def __init__(self):
        self.core_indicator_input = None

    def update_specs_from_csv_data(self, _records):
        return None

    def process(self, records):
        result = []
        for row in records:
            state = "严重偏高" if float(row.get("value") or 0.0) > 80 else "正常"
            diff = float(row.get("value") or 0.0) - float(row.get("design_ref") or 70.0)
            result.append(
                {
                    "tag_id": row.get("tag_id"),
                    "name": row.get("name"),
                    "current_value": row.get("value"),
                    "state_desc": state,
                    "diff": diff,
                    "membership_degree": 0.6,
                    "assessment_reason": "mock",
                    "comparison_summary": "mock",
                    "reference_label": "design_ref",
                    "reference_value": row.get("design_ref"),
                }
            )
        return result

    def build_abnormal_details(self, _all_records, semantic_data):
        out = []
        for item in semantic_data:
            if item.get("state_desc") == "正常":
                continue
            out.append(
                {
                    "tag_id": item.get("tag_id"),
                    "name": item.get("name"),
                    "current_value": item.get("current_value"),
                    "diff": item.get("diff"),
                    "state_desc": item.get("state_desc"),
                    "rule_reason": "mock rule",
                    "ai_reason": "",
                    "level": item.get("state_desc"),
                    "window": {"start": "2026-03-09T11:00:00", "end": "2026-03-09T11:00:00", "duration_points": 1, "is_ongoing": True},
                    "trend": "stable",
                }
            )
        return out

    def build_overall_operating_summary(self, semantic_data, abnormal_details, **_kwargs):
        return {
            "summary": f"共 {len(semantic_data)} 项，异常 {len(abnormal_details)} 项。",
            "highlights": [],
            "calculation_audit": {
                "data_intake": {"layout_detected": "wide_table", "data_start_row": 1},
                "indicators": [{"tag_id": "A", "name": "A", "severity_score": 1.0}],
                "subsystems": [],
                "plant": {"abnormal_ratio": len(abnormal_details) / max(len(semantic_data), 1)},
            },
        }

    def calculate_core_indicators(self, records):
        self.core_indicator_input = records
        return _FakeCoreIndicators()


class _FakeReasoningEngine:
    def __init__(self, *args, **kwargs):
        pass

    def analyze(self, *args, **kwargs):
        return json.dumps(
            {
                "thought_process": "mock",
                "root_cause": "mock root cause",
                "operation_suggestion": "mock operation",
                "safety_warning": "mock safety",
                "bottleneck_indicators": [],
                "coupling_analysis": "",
                "missing_data_request": None,
                "indicator_diagnoses": [],
                "knowledge_references": [],
            },
            ensure_ascii=False,
        )

    def ask_assistant(self, user_prompt: str, system_prompt: str = "", temperature: float = 0.1):
        return "{\"actionable_steps\":\"mock action\"}"


class _FakeDecisionService:
    def verify_and_suggest(self, *_args, **_kwargs):
        return {
            "actionable_steps": "mock action",
            "simulation_result": "mock simulation",
            "verification_status": "Passed",
            "reasoning_summary": "mock summary",
            "confidence_score": 0.8,
            "risk_assessment": "mock risk",
            "rollback_strategy": "mock rollback",
        }


class _FakeKnowledgeRetrievalService:
    def __init__(self, *_args, **_kwargs):
        pass

    def retrieve_measures(self, *args, **kwargs):
        return {
            "retrieval_summary": "mock retrieval summary",
            "recommended_measures": [{"title": "mock"}],
            "knowledge_references": [],
            "risk_tips": [],
            "raw_response": "{}",
        }


class _FakeReportGenerator:
    def __init__(self):
        self.last_analysis_result = None

    def generate_both_formats(self, analysis_result, _base_filename=None):
        self.last_analysis_result = analysis_result
        return "reports/mock.pdf", "reports/mock.md"


def test_run_interactive_emits_traceability_and_latest_snapshot_abnormal_count(monkeypatch):
    monkeypatch.setattr(run_interactive, "ExcelDataLoader", _FakeLoader)
    monkeypatch.setattr(run_interactive, "DataSemanticsService", _FakeSemantics)
    monkeypatch.setattr(run_interactive, "ReasoningEngineV2", _FakeReasoningEngine)
    monkeypatch.setattr(run_interactive, "DecisionService", _FakeDecisionService)
    monkeypatch.setattr(run_interactive, "KnowledgeRetrievalService", _FakeKnowledgeRetrievalService)
    monkeypatch.setattr(run_interactive, "ReportGenerator", _FakeReportGenerator)

    result = run_interactive.simulate_user_operation(
        data_file="data/demo.xlsx",
        use_asu_pipeline=False,
        enable_cot=True,
    )

    assert result["abnormal_count"] == 1
    assert result["data_overview"]["latest_timestamp"] == "2026-03-09T11:00:00"
    assert len(result["analysis_steps"]) == 8
    assert len(result["traceability"]["step_traces"]) == 8
    assert result["visualization_context"]["top_indicator_cards"]
    assert result["calculation_audit"]["data_intake"]["layout_detected"] == "wide_table"


def test_run_interactive_builds_core_indicators_from_semantic_snapshot(monkeypatch):
    fake_semantics = _FakeSemantics()

    monkeypatch.setattr(run_interactive, "ExcelDataLoader", _FakeLoader)
    monkeypatch.setattr(run_interactive, "DataSemanticsService", lambda: fake_semantics)
    monkeypatch.setattr(run_interactive, "ReasoningEngineV2", _FakeReasoningEngine)
    monkeypatch.setattr(run_interactive, "DecisionService", _FakeDecisionService)
    monkeypatch.setattr(run_interactive, "KnowledgeRetrievalService", _FakeKnowledgeRetrievalService)
    monkeypatch.setattr(run_interactive, "ReportGenerator", _FakeReportGenerator)

    run_interactive.simulate_user_operation(
        data_file="data/demo.xlsx",
        use_asu_pipeline=False,
        enable_cot=True,
    )

    assert fake_semantics.core_indicator_input is not None
    assert fake_semantics.core_indicator_input
    assert all("current_value" in item for item in fake_semantics.core_indicator_input)
