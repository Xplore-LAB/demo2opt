"""全局错误处理器"""
import logging
import traceback
from typing import Any, Dict, Optional

from src.core.exceptions import (
    Demo2OptError,
    ConfigurationError,
    DataError,
    LLMError,
    RetrievalError,
    ValidationError,
)


class ErrorHandler:
    """全局错误处理器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def handle(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理错误并返回标准化错误信息"""
        context = context or {}
        
        if isinstance(error, Demo2OptError):
            return self._handle_known_error(error, context)
        
        return self._handle_unknown_error(error, context)
    
    def _handle_known_error(self, error: Demo2OptError, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理已知错误"""
        self.logger.error(
            f"[{error.code}] {error.message}",
            extra={"context": context, "details": error.details}
        )
        
        return {
            "error": True,
            "code": error.code,
            "message": error.message,
            "details": error.details,
            "context": context,
        }
    
    def _handle_unknown_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理未知错误"""
        self.logger.exception(
            f"Unexpected error: {str(error)}",
            extra={"context": context}
        )
        
        return {
            "error": True,
            "code": "INTERNAL_ERROR",
            "message": str(error),
            "details": {
                "type": type(error).__name__,
                "traceback": traceback.format_exc(),
            },
            "context": context,
        }
    
    def classify_error(self, error: Exception) -> str:
        """分类错误"""
        if isinstance(error, ConfigurationError):
            return "configuration"
        if isinstance(error, DataError):
            return "data"
        if isinstance(error, LLMError):
            return "llm"
        if isinstance(error, RetrievalError):
            return "retrieval"
        if isinstance(error, ValidationError):
            return "validation"
        if isinstance(error, Demo2OptError):
            return "known"
        return "unknown"
