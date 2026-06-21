import pytest

from src.services.reasoning_engine_v2 import ReasoningEngineV2, ReasoningExecutionError


class _FakeClient:
    def analyze_with_knowledge(self, *args, **kwargs):
        return "this is not json"


class _QuoteBrokenJsonClient:
    def analyze_with_knowledge(self, *args, **kwargs):
        return (
            '```json\n'
            '{"root_cause":"知识库召回片段质量极低（仅"效率过低""反转"等碎片化关键词）",'
            '"operation_suggestion":"先核查膨胀机B入口条件",'
            '"safety_warning":"执行前人工复核",'
            '"thought_process":"test",'
            '"bottleneck_indicators":["膨胀机B制冷量"],'
            '"coupling_analysis":"冷量系统受限",'
            '"indicator_diagnoses":[]}\n'
            '```'
        )


def test_reasoning_engine_raises_on_non_json_response(monkeypatch):
    monkeypatch.setattr(ReasoningEngineV2, "_build_direct_client", lambda self, _cfg: _FakeClient())

    engine = ReasoningEngineV2(
        llm_config={"api_key": "test", "base_url": "http://localhost", "model": "mock"},
    )

    with pytest.raises(ReasoningExecutionError, match="LLM_NON_JSON_RESPONSE"):
        engine.analyze(
            semantic_data=[{"tag_id": "x", "name": "x", "state_desc": "偏高", "current_value": 1.0}],
            enable_cot=True,
        )


def test_reasoning_engine_accepts_json_like_response_with_unescaped_quotes(monkeypatch):
    monkeypatch.setattr(ReasoningEngineV2, "_build_direct_client", lambda self, _cfg: _QuoteBrokenJsonClient())

    engine = ReasoningEngineV2(
        llm_config={"api_key": "test", "base_url": "http://localhost", "model": "mock"},
    )

    result = engine.analyze(
        semantic_data=[{"tag_id": "x", "name": "x", "state_desc": "偏高", "current_value": 1.0}],
        abnormal_items=[{"name": "x", "state_desc": "偏高", "current_value": 1.0}],
        enable_cot=True,
    )

    assert '"root_cause": "知识库召回片段质量极低（仅\\"效率过低\\"\\"反转\\"等碎片化关键词）"' in result
