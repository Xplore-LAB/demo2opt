from src.schemas.models import ReasoningResultModel


def test_reasoning_result_downgrades_absolute_root_cause_claims():
    result = ReasoningResultModel(
        root_cause="膨胀机B制冷量严重不足是核心根因，已锁定根因链起点。",
        operation_suggestion="先核查膨胀机B入口过滤器与导叶开度。",
        safety_warning="调整前确认联锁边界与回退条件。",
    )

    assert "核心根因" not in result.root_cause
    assert "已锁定根因链起点" not in result.root_cause
    assert "主导异常" in result.root_cause
    assert "疑似根因链起点" in result.root_cause
