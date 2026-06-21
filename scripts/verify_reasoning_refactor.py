"""验证重构后的推理引擎"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.services.reasoning.response_parser import ResponseParser
from src.services.reasoning.i18n import I18n
from src.services.reasoning.llm_adapter import LLMAdapter
from src.services.reasoning.engine import ReasoningEngineV2
from typing import Any, Dict, List


class MockLLMAdapter(LLMAdapter):
    """Mock LLM 适配器"""
    
    def chat(self, query: str, system_prompt: str = "", temperature: float = 0.1, **kwargs) -> Dict[str, Any]:
        return {"ok": True, "answer": "测试回答"}
    
    def analyze_with_knowledge(self, abnormal_items: List[Dict], enable_cot: bool = True, **kwargs) -> Any:
        return {
            "root_cause": "测试根因",
            "operation_suggestion": "测试建议",
            "safety_warning": "测试警告",
            "thought_process": "测试思考过程",
            "bottleneck_indicators": ["指标1"],
            "coupling_analysis": "测试耦合",
            "indicator_diagnoses": []
        }


def test_response_parser():
    print("测试 ResponseParser...")
    parser = ResponseParser()
    
    # 测试 JSON 字符串
    result = parser.parse('{"key": "value"}')
    assert result == {"key": "value"}, "JSON 解析失败"
    
    # 测试 Markdown JSON
    result = parser.parse('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}, "Markdown JSON 解析失败"
    
    print("✓ ResponseParser 测试通过")


def test_i18n():
    print("测试 I18n...")
    text = "Energy and extraction indicators may be coupled."
    result = I18n.localize(text)
    assert "能耗指标" in result, "国际化失败"
    print("✓ I18n 测试通过")


def test_reasoning_engine():
    print("测试 ReasoningEngineV2...")
    
    # 使用 Mock 适配器
    mock_adapter = MockLLMAdapter()
    engine = ReasoningEngineV2(llm_adapter=mock_adapter)
    
    # 测试 ask_assistant
    result = engine.ask_assistant("测试问题")
    assert result == "测试回答", "ask_assistant 失败"
    
    # 测试 analyze
    import json
    semantic_data = [{"tag_id": "test", "state": "abnormal"}]
    result_json = engine.analyze(semantic_data)
    result = json.loads(result_json)
    assert "root_cause" in result, "analyze 失败"
    assert result["root_cause"] == "测试根因", "根因不匹配"
    
    print("✓ ReasoningEngineV2 测试通过")


if __name__ == "__main__":
    try:
        test_response_parser()
        test_i18n()
        test_reasoning_engine()
        print("\n✅ 所有测试通过！推理引擎重构成功。")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
