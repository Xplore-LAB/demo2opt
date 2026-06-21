"""测试统一错误处理"""
import pytest
from src.core.exceptions import (
    Demo2OptError,
    ConfigurationError,
    DataError,
    LLMError,
    RetrievalError,
)
from src.core.error_handler import ErrorHandler


class TestExceptions:
    """测试异常类型"""
    
    def test_base_exception(self):
        error = Demo2OptError("测试错误", "TEST_ERROR", {"key": "value"})
        assert error.message == "测试错误"
        assert error.code == "TEST_ERROR"
        assert error.details == {"key": "value"}
    
    def test_configuration_error(self):
        error = ConfigurationError("配置错误")
        assert error.code == "CONFIG_ERROR"
    
    def test_data_error(self):
        error = DataError("数据错误")
        assert error.code == "DATA_ERROR"
    
    def test_llm_error(self):
        error = LLMError("LLM 错误")
        assert error.code == "LLM_ERROR"


class TestErrorHandler:
    """测试错误处理器"""
    
    def test_handle_known_error(self):
        handler = ErrorHandler()
        error = ConfigurationError("配置缺失", {"missing": "api_key"})
        result = handler.handle(error, {"module": "reasoning"})
        
        assert result["error"] is True
        assert result["code"] == "CONFIG_ERROR"
        assert result["message"] == "配置缺失"
        assert result["details"]["missing"] == "api_key"
    
    def test_handle_unknown_error(self):
        handler = ErrorHandler()
        error = ValueError("未知错误")
        result = handler.handle(error)
        
        assert result["error"] is True
        assert result["code"] == "INTERNAL_ERROR"
        assert "ValueError" in result["details"]["type"]
    
    def test_classify_error(self):
        handler = ErrorHandler()
        assert handler.classify_error(ConfigurationError("test")) == "configuration"
        assert handler.classify_error(DataError("test")) == "data"
        assert handler.classify_error(LLMError("test")) == "llm"
        assert handler.classify_error(ValueError("test")) == "unknown"
