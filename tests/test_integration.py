"""集成测试 - 测试完整工作流程"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


class TestIntegration:
    """集成测试"""
    
    @patch('src.services.reasoning.llm_adapter.SimpleLLMClient')
    def test_reasoning_with_cache(self, mock_client):
        """测试带缓存的推理流程"""
        from src.services.reasoning import ReasoningEngineV2, SimpleLLMAdapter
        from src.utils.cache import ResponseCache
        
        # 模拟 LLM 响应
        mock_response = {
            "root_cause": "测试根因",
            "operation_suggestion": "测试建议",
            "safety_warning": "测试警告",
            "thought_process": "测试思考",
            "bottleneck_indicators": [],
            "coupling_analysis": "测试耦合",
            "indicator_diagnoses": []
        }
        
        mock_client_instance = Mock()
        mock_client_instance.analyze_with_knowledge.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # 创建带缓存的适配器
        cache = ResponseCache(enabled=True)
        adapter = SimpleLLMAdapter("http://test", "test-key", "test-model", cache=cache)
        adapter.client = mock_client_instance
        
        engine = ReasoningEngineV2(llm_adapter=adapter)
        
        # 第一次调用
        result1 = engine.analyze([{"tag_id": "T001", "state": "abnormal"}])
        assert mock_client_instance.analyze_with_knowledge.call_count == 1
        
        # 第二次调用相同输入（应该使用缓存）
        result2 = engine.analyze([{"tag_id": "T001", "state": "abnormal"}])
        assert mock_client_instance.analyze_with_knowledge.call_count == 1  # 没有增加
        
        # 结果应该相同
        assert result1 == result2
    
    def test_error_handling_flow(self):
        """测试错误处理流程"""
        from src.core.exceptions import ConfigurationError
        from src.core.error_handler import ErrorHandler
        
        handler = ErrorHandler()
        error = ConfigurationError("API Key 缺失", {"required": "LLM_API_KEY"})
        
        result = handler.handle(error, {"module": "reasoning", "step": "init"})
        
        assert result["error"] is True
        assert result["code"] == "CONFIG_ERROR"
        assert result["message"] == "API Key 缺失"
        assert result["context"]["module"] == "reasoning"
