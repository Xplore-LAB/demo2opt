import json

import main as main_module


class _FakeLoader:
    def load_and_standardize(self):
        return {
            "records": [
                {"tag_id": "A", "name": "A", "value": 72.0, "design_ref": 70.0, "timestamp": "2026-03-09T10:00:00"},
                {"tag_id": "B", "name": "B", "value": 68.0, "design_ref": 70.0, "timestamp": "2026-03-09T10:00:00"},
                {"tag_id": "A", "name": "A", "value": 88.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
                {"tag_id": "B", "name": "B", "value": 65.0, "design_ref": 70.0, "timestamp": "2026-03-09T11:00:00"},
            ],
            "quality": {"status": "PASS"},
        }


class _FakeCore:
    extraction_rate = {}
    stability = {}
    energy_consumption = {}

    def dict(self):
        return {}


class _FakeSemantics:
    def __init__(self):
        self.received_specs_payload = None

    def update_specs_from_csv_data(self, payload):
        self.received_specs_payload = payload
        assert isinstance(payload, list)

    def process(self, records):
        out = []
        for row in records:
            state = "严重偏高" if float(row.get("value") or 0.0) > 80 else "正常"
            out.append(
                {
                    "tag_id": row.get("tag_id"),
                    "name": row.get("name"),
                    "current_value": row.get("value"),
                    "state_desc": state,
                    "diff": float(row.get("value") or 0.0) - float(row.get("design_ref") or 70.0),
                }
            )
        return out

    def calculate_core_indicators(self, _records):
        return _FakeCore()


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
                "indicator_diagnoses": [],
            },
            ensure_ascii=False,
        )


class _FakeDecision:
    def verify_and_suggest(self, _reasoning, **_kwargs):
        return {
            "actionable_steps": "mock action",
            "simulation_result": "mock sim",
            "verification_status": "Passed",
            "reasoning_summary": "mock summary",
            "confidence_score": 0.9,
            "risk_assessment": "mock risk",
            "rollback_strategy": "mock rollback",
        }


def test_main_run_analysis_accepts_loader_dict_records_contract():
    optimizer = main_module.AirSeparationOptimizer.__new__(main_module.AirSeparationOptimizer)
    optimizer.use_asu_pipeline = False
    optimizer.enable_async = False
    optimizer.enable_cot = True
    optimizer.data_loader = _FakeLoader()
    optimizer.semantics_service = _FakeSemantics()
    optimizer.reasoning_engine = _FakeReasoning()
    optimizer.decision_service = _FakeDecision()
    optimizer.report_generator = None
    optimizer._print_results = lambda *_args, **_kwargs: None
    optimizer._generate_reports = lambda *_args, **_kwargs: None

    result = optimizer.run_analysis()

    assert result["status"] == "abnormal"
    assert result["abnormal_count"] == 1
    assert len(result["semantic_data"]) == 2
