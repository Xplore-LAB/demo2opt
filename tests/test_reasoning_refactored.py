"""测试重构后的推理引擎"""
import json
import pytest
from typing import Any, Dict, List

from src.services.reasoning.engine import ReasoningEngineV2, ReasoningConfigurationError
from src.services.reasoning.llm_adapter import LLMAdapter
from src.services.reasoning.response_parser import ResponseParser
from src.services.reasoning.i18n import I18n


class MockLLMAdapter(LLMAdapter):
    """Mock LLM 适配器用于测试"""
    
    def __init__(self, mock_response: Any = None):
        self.mock_response = mock_response or {
            "root_cause": "测试根因",
            "operation_suggestion": "测试建议",
            "safety_warning": "测试警告",
            "thought_process": "测试思考过程",
            "bottleneck_indicators": ["指标1", "指标2"],
            "coupling_analysis": "测试耦合分析",
            "indicator_diagnoses": []
        }
        self.call_count = 0
        self.last_call_args = None
    
    def chat(self, query: str, system_prompt: str = "", temperature: float = 0.1, **kwargs) -> Dict[str, Any]:
        self.call_count += 1
        self.last_call_args = {"query": query, "system_prompt": system_prompt, "temperature": temperature}
        return {"ok": True, "answer": "测试回答"}
    
    def analyze_with_knowledge(self, abnormal_items: List[Dict], enable_cot: bool = True, **kwargs) -> Any:
        self.call_count += 1
        self.last_call_args = {"abnormal_items": abnormal_items, "enable_cot": enable_cot, **kwargs}
        return self.mock_response


class TestResponseParser:
    """测试响应解析器"""
    
    def test_parse_dict_response(self):
        parser = ResponseParser()
        result = parser.parse({"key": "value"})
        assert result == {"key": "value"}
    
    def test_parse_json_string(self):
        parser = ResponseParser()
        result = parser.parse('{"key": "value"}')
        assert result == {"key": "value"}
    
    def test_parse_markdown_json(self):
        parser = ResponseParser()
        result = parser.parse('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_markdown_json_with_unescaped_quotes_inside_string(self):
        parser = ResponseParser()
        raw = '```json\n{"root_cause":"知识库仅返回\\"正常\\"和"反转"等碎片化关键词","operation_suggestion":"先核查设备","safety_warning":"人工复核","thought_process":"test","bottleneck_indicators":[],"coupling_analysis":"test","indicator_diagnoses":[]}\n```'
        result = parser.parse(raw)
        assert result["root_cause"] == '知识库仅返回"正常"和"反转"等碎片化关键词'

    def test_parse_invalid_response(self):
        parser = ResponseParser()
        with pytest.raises(ValueError, match="LLM_NON_JSON_RESPONSE"):
            parser.parse("这不是 JSON")


class TestI18n:
    """测试国际化"""
    
    def test_localize_common_phrase(self):
        text = "Energy and extraction indicators may be coupled."
        result = I18n.localize(text)
        assert result == "能耗指标与提取率指标可能存在耦合关系。"
    
    def test_localize_unknown_phrase(self):
        text = "Unknown phrase"
        result = I18n.localize(text)
        assert result == "Unknown phrase"


class TestReasoningEngineV2:
    """测试推理引擎"""
    
    def test_init_with_adapter(self):
        """测试使用适配器初始化"""
        mock_adapter = MockLLMAdapter()
        engine = ReasoningEngineV2(llm_adapter=mock_adapter)
        assert engine.adapter == mock_adapter
    
    def test_init_reject_dify(self):
        """测试拒绝 Dify 模式"""
        with pytest.raises(ReasoningConfigurationError, match="Dify 仅用于知识检索"):
            ReasoningEngineV2(use_dify=True)
    
    def test_ask_assistant(self):
        """测试询问助手"""
        mock_adapter = MockLLMAdapter()
        engine = ReasoningEngineV2(llm_adapter=mock_adapter)
        
        result = engine.ask_assistant("测试问题", "测试系统提示")
        
        assert result == "测试回答"
        assert mock_adapter.call_count == 1
        assert mock_adapter.last_call_args["query"] == "测试问题"
    
    def test_analyze_with_mock_adapter(self):
        """测试使用 Mock 适配器分析"""
        mock_adapter = MockLLMAdapter()
        engine = ReasoningEngineV2(llm_adapter=mock_adapter)
        
        semantic_data = [{"tag_id": "test", "state": "abnormal"}]
        result_json = engine.analyze(semantic_data)
        result = json.loads(result_json)
        
        assert "root_cause" in result
        assert result["root_cause"] == "测试根因"
        assert mock_adapter.call_count == 1
    
    def test_analyze_empty_data(self):
        """测试空数据分析"""
        mock_adapter = MockLLMAdapter()
        engine = ReasoningEngineV2(llm_adapter=mock_adapter)
        
        result_json = engine.analyze([], abnormal_items=[])
        result = json.loads(result_json)
        
        assert result["root_cause"] == "未检测到可分析的异常数据。"
        assert mock_adapter.call_count == 0  # 不应调用 LLM
