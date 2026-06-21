import json

from src.services.data_semantics import DataSemanticsService


def test_apply_ai_assistance_updates_review_fields():
    service = DataSemanticsService()
    semantic_data = [
        {
            "tag_id": "T1",
            "name": "主换冷损",
            "state_desc": "偏高",
            "current_value": 100.0,
            "diff": 20.0,
            "assessment_reason": "规则判定偏高",
            "comparison_summary": "设计基准 80.0",
        }
    ]
    abnormal_details = [
        {
            "tag_id": "T1",
            "name": "主换冷损",
            "level": "偏高",
            "rule_reason": "高于动态基准",
            "trend": "increasing",
            "window": {"duration_points": 3},
            "ai_reason": "",
        }
    ]
    overall_judgement = {"summary": "存在偏高风险", "highlights": []}

    def ask_model(system_prompt: str, user_prompt: str, temperature: float) -> str:
        return json.dumps(
            {
                "summary_refinement": "主换冷损偏高与换热端温差恶化相关。",
                "highlights_refinement": ["建议优先复核主换端温差。"],
                "state_reviews": [
                    {
                        "tag_id": "T1",
                        "name": "主换冷损",
                        "suggested_state": "偏高",
                        "reason": "与工艺负荷偏移一致。",
                        "confidence": "high",
                    }
                ],
                "risk_focus": ["主换换热恶化风险"],
            },
            ensure_ascii=False,
        )

    result = service.apply_ai_assistance(
        semantic_data=semantic_data,
        abnormal_details=abnormal_details,
        overall_judgement=overall_judgement,
        ask_model=ask_model,
        task_note="关注主换冷损",
    )

    assert result["used"] is True
    assert result["reviews_applied"] == 1
    assert "AI复核" in overall_judgement["summary"]
    assert semantic_data[0]["ai_state_desc"] == "偏高"
    assert abnormal_details[0]["ai_reason"] == "与工艺负荷偏移一致。"
