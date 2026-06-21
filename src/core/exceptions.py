"""统一异常类型定义"""


class Demo2OptError(Exception):
    """基础异常类"""
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ConfigurationError(Demo2OptError):
    """配置错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CONFIG_ERROR", details)


class DataError(Demo2OptError):
    """数据错误"""
    def __init__(self, message: str, code: str = "DATA_ERROR", details: dict = None):
        super().__init__(message, code, details)


class DataLoadError(DataError):
    """数据加载错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "DATA_LOAD_ERROR", details)


class DataQualityError(DataError):
    """数据质量错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "DATA_QUALITY_ERROR", details)


class LLMError(Demo2OptError):
    """LLM 相关错误"""
    def __init__(self, message: str, code: str = "LLM_ERROR", details: dict = None):
        super().__init__(message, code, details)


class LLMConnectionError(LLMError):
    """LLM 连接错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "LLM_CONNECTION_ERROR", details)


class LLMResponseError(LLMError):
    """LLM 响应错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "LLM_RESPONSE_ERROR", details)


class RetrievalError(Demo2OptError):
    """知识检索错误"""
    def __init__(self, message: str, code: str = "RETRIEVAL_ERROR", details: dict = None):
        super().__init__(message, code, details)


class RetrievalConnectionError(RetrievalError):
    """检索服务连接错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "RETRIEVAL_CONNECTION_ERROR", details)


class ValidationError(Demo2OptError):
    """验证错误"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "VALIDATION_ERROR", details)
