import asyncio
import json
from pathlib import Path

from src.agent.workflows.runner import arun_analysis, aresume_analysis
from src.services.decision_service import DecisionService
from src.services.reasoning_engine_v2 import ReasoningEngineV2
from src.utils.llm_json import repair_llm_text


class _FakeLoader:
    def load_and_standardize(self):
        return {
            "records": [
                {"tag_id": "A", "name": "A", "value": 70.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
                {"tag_id": "B", "name": "B", "value": 70.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
            ],
            "quality_gate": {"status": "PASS"},
            "parsing_audit": {"layout_detected": "tall_table"},
        }


class _AbnormalLoader:
    def load_and_standardize(self):
        return {
            "records": [
                {"tag_id": "A", "name": "A", "value": 88.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
                {"tag_id": "B", "name": "B", "value": 65.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
            ],
            "quality_gate": {"status": "PASS"},
            "parsing_audit": {"layout_detected": "tall_table"},
        }


class _HealthySemantics:
    def __init__(self):
        self.core_indicator_input = None

    def update_specs_from_csv_data(self, payload):
        assert isinstance(payload, list)

    def process(self, records):
        return [
            {"tag_id": row["tag_id"], "name": row["name"], "current_value": row["value"], "state_desc": "正常", "diff": 0.0}
            for row in records
        ]

    def build_baseline_profile(self, _records):
        return {"tag_count": 2, "per_tag": {}}

    def build_abnormal_details(self, *_args, **_kwargs):
        return []

    def build_overall_operating_summary(self, *_args, **_kwargs):
        return {
            "summary": "工况平稳",
            "highlights": [],
            "plant_state": "stable",
            "calculation_audit": {
                "data_intake": {"layout_detected": "tall_table"},
                "indicators": [],
                "subsystems": [],
                "plant": {"abnormal_ratio": 0.0},
            },
        }

    def calculate_core_indicators(self, records):
        self.core_indicator_input = records
        return {"extraction_rate": {}, "stability": {}, "energy_consumption": {}}

    def extract_features(self, _records):
        return {}


class _AbnormalSemantics(_HealthySemantics):
    def process(self, records):
        return [
            {"tag_id": "A", "name": "A", "current_value": 88.0, "state_desc": "严重偏高", "diff": 18.0},
            {"tag_id": "B", "name": "B", "current_value": 65.0, "state_desc": "正常", "diff": -5.0},
        ]

    def build_abnormal_details(self, *_args, **_kwargs):
        return [
            {"tag_id": "A", "name": "A", "state_desc": "严重偏高", "diff": 18.0, "rule_reason": "高于设计值"}
        ]

    def build_overall_operating_summary(self, *_args, **_kwargs):
        return {
            "summary": "存在异常",
            "highlights": ["A 偏高"],
            "plant_state": "abnormal_unstable",
            "calculation_audit": {
                "data_intake": {"layout_detected": "tall_table"},
                "indicators": [{"tag_id": "A", "severity_score": 1.0}],
                "subsystems": [],
                "plant": {"abnormal_ratio": 0.5},
            },
        }

    def extract_features(self, _records):
        return {"A": {"trend": "up"}}


class _FakeReasoning:
    def analyze(self, *args, **kwargs):
        return json.dumps(
            {
                "thought_process": "mock",
                "root_cause": "mock root",
                "operation_suggestion": "mock op",
                "safety_warning": "mock safety",
                "bottleneck_indicators": [],
                "coupling_analysis": "",
                "indicator_diagnoses": [{"name": "A", "ai_reason": "mock reason"}],
            },
            ensure_ascii=False,
        )


class _FakeDecision:
    def verify_and_suggest(self, _reasoning, *_args, **_kwargs):
        return {
            "actionable_steps": "mock action",
            "simulation_result": "mock sim",
            "verification_status": "Passed",
            "reasoning_summary": "mock summary",
            "confidence_score": 0.9,
            "risk_assessment": "mock risk",
            "rollback_strategy": "mock rollback",
        }


def test_agent_runner_skips_reasoning_when_healthy():
    state = asyncio.run(
        arun_analysis(
            {
                "entrypoint": "cli",
                "auto_confirm": True,
                "service_overrides": {
                    "data_loader": _FakeLoader(),
                    "semantics_service": _HealthySemantics(),
                    "report_generator": None,
                },
            }
        )
    )
    result = state["analysis_result"]
    assert result["status"] == "healthy"
    assert result["abnormal_count"] == 0
    assert result["reasoning_result"] is None
    assert result["calculation_audit"]["data_intake"]["layout_detected"] == "tall_table"


def test_agent_runner_runs_abnormal_path_without_report_generator():
    semantics = _AbnormalSemantics()
    state = asyncio.run(
        arun_analysis(
            {
                "entrypoint": "cli",
                "auto_confirm": True,
                "service_overrides": {
                    "data_loader": _AbnormalLoader(),
                    "semantics_service": semantics,
                    "reasoning_engine": _FakeReasoning(),
                    "decision_service": _FakeDecision(),
                    "report_generator": None,
                },
            }
        )
    )
    result = state["analysis_result"]
    assert result["status"] == "abnormal"
    assert result["abnormal_count"] == 1
    assert result["decision_result"]["verification_status"] == "Passed"
    assert semantics.core_indicator_input
    assert all("current_value" in item for item in semantics.core_indicator_input)
    step_traces = result["traceability"]["step_traces"]
    assert len(step_traces) == 8
    assert all(int(item["duration_ms"]) >= 1 for item in step_traces)
    assert result["calculation_audit"]["plant"]["abnormal_ratio"] == 0.5
    assert result["traceability"]["trace_files"]["calculation_audit"]


def test_agent_runner_persists_pending_checkpoint_for_ws():
    task_id = "test-agent-pending"
    state = asyncio.run(
        arun_analysis(
            {
                "task_id": task_id,
                "entrypoint": "ws",
                "auto_confirm": False,
                "service_overrides": {
                    "data_loader": _FakeLoader(),
                    "semantics_service": _HealthySemantics(),
                    "report_generator": None,
                },
            }
        )
    )
    assert state["pending_checkpoint"]["checkpoint_key"] == "init_data_range_confirm"
    snapshot_path = Path("task_progress") / "graph_runs" / f"{task_id}.json"
    assert snapshot_path.exists()


def test_agent_runner_resume_restarts_from_checkpoint_node_not_previous_step():
    task_id = "test-agent-resume"
    state = asyncio.run(
        arun_analysis(
            {
                "task_id": task_id,
                "entrypoint": "ws",
                "auto_confirm": False,
                "service_overrides": {
                    "data_loader": _FakeLoader(),
                    "semantics_service": _HealthySemantics(),
                    "report_generator": None,
                },
            }
        )
    )

    assert state["resume_node"] == "confirm_data_range"

    resumed = asyncio.run(aresume_analysis(task_id, "yes"))

    assert resumed["pending_checkpoint"]["checkpoint_key"] == "analysis_overview_confirm"
    load_data_events = [item for item in resumed["execution_history"] if item["node"] == "load_data"]
    assert len(load_data_events) == 1


def test_repair_llm_text_fixes_mojibake_segments():
    broken = r"AI澶嶆牳锛毭x9c篓盲赂\x8d忙\x94鹿氓\x8f\x98猫搂\x84氓\x88\x99氓卤\x82"

    repaired = repair_llm_text(broken)

    assert isinstance(repaired, str)
    assert repaired
    assert "AI" in repaired


def test_reasoning_engine_analyze_accepts_dict_core_indicators():
    class _FakeClient:
        def analyze_with_knowledge(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "thought_process": "mock",
                    "root_cause": "mock root",
                    "operation_suggestion": "mock op",
                    "safety_warning": "mock safety",
                    "bottleneck_indicators": [],
                    "coupling_analysis": "",
                    "indicator_diagnoses": [],
                    "knowledge_references": [],
                },
                ensure_ascii=False,
            )

    engine = object.__new__(ReasoningEngineV2)
    engine.client = _FakeClient()

    payload = json.loads(
        engine.analyze(
            semantic_data=[{"name": "A"}],
            abnormal_items=[{"name": "A"}],
            core_indicators={
                "extraction_rate": {"tag-1": {"membership": 0.5}},
                "stability": {},
                "energy_consumption": {"tag-2": {"membership": 0.9}},
            },
        )
    )

    assert payload["root_cause"] == "mock root"


def test_decision_service_repairs_ai_review_text():
    service = DecisionService()

    result = service._apply_ai_decision_review(
        rule_output={
            "actionable_steps": "rule",
            "simulation_result": "rule",
            "verification_status": "Pending",
            "risk_assessment": "rule",
            "rollback_strategy": "rule",
            "confidence_score": 0.5,
        },
        reasoning_result={},
        ask_model=lambda *_args, **_kwargs: json.dumps(
            {
                "actionable_steps": "莽禄麓忙聦聛芒聙聹茅芦聵茅拢聨茅聶漏氓陇聞莽陆庐芒聙聺氓鹿露忙聦聣盲赂聣茅聵露忙庐碌忙聣搂猫隆聦",
                "simulation_result": "ok",
                "verification_status": "Passed",
                "risk_assessment": "ok",
                "rollback_strategy": "ok",
            },
            ensure_ascii=False,
        ),
        knowledge_context={},
        overall_judgement={},
        task_note="",
    )

    assert result["verification_status"] == "Passed"
    assert isinstance(result["actionable_steps"], str)
    assert result["actionable_steps"]
