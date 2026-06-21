import json

from src.services.decision_service import DecisionService


def test_verify_and_suggest_with_ai_assistance(tmp_path):
    service = DecisionService(case_store_path=str(tmp_path / "decision_cases.jsonl"))
    reasoning_result = {
        "root_cause": "主换冷损偏高",
        "operation_suggestion": "调整回流液量",
        "safety_warning": "关注联锁波动",
        "coupling_analysis": "负荷与冷损耦合",
        "bottleneck_indicators": ["主换冷损"],
    }

    def ask_model(system_prompt: str, user_prompt: str, temperature: float) -> str:
        return json.dumps(
            {
                "actionable_steps": "先小步降低回流液量，再观察10分钟。",
                "simulation_result": "预计冷损下降 0.8%。",
                "verification_status": "Passed",
                "risk_assessment": "短时波动可控，需监控压差。",
                "rollback_strategy": "若压差恶化，恢复原回流设定。",
                "confidence_score": 0.86,
            },
            ensure_ascii=False,
        )

    result = service.verify_and_suggest(
        reasoning_result=reasoning_result,
        ask_model=ask_model,
        knowledge_context={"recommended_measures": [{"title": "优化回流"}]},
        overall_judgement={"summary": "存在冷损偏高"},
        task_note="关注冷损",
    )

    assert result["actionable_steps"].startswith("先小步")
    assert result["verification_status"] == "Passed"
    assert result["confidence_score"] == 0.86
