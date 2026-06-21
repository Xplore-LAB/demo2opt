"""LLM 适配器抽象接口"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.utils.cache import ResponseCache


class LLMAdapter(ABC):
    """LLM 适配器抽象基类"""

    @abstractmethod
    def chat(
        self,
        query: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """基础对话接口
        
        Returns:
            {"ok": bool, "answer": str, "error": Optional[Dict]}
        """
        pass

    @abstractmethod
    def analyze_with_knowledge(
        self,
        abnormal_items: List[Dict],
        enable_cot: bool = True,
        **kwargs
    ) -> Any:
        """知识增强分析接口"""
        pass


class SimpleLLMAdapter(LLMAdapter):
    """简单 LLM 适配器实现（支持缓存）"""

    def __init__(self, api_url: str, api_key: str, model_name: str, cache: Optional[ResponseCache] = None):
        from src.prompts.templates import SimpleLLMClient
        self.client = SimpleLLMClient(api_url=api_url, api_key=api_key, model_name=model_name)
        self.cache = cache or ResponseCache(enabled=False)

    def chat(
        self,
        query: str,
        system_prompt: str = "",
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        cache_key = self.cache.make_key("chat", query=query, system_prompt=system_prompt, temperature=temperature)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        result = self.client.chat(query=query, system_prompt=system_prompt, temperature=temperature)
        self.cache.set(cache_key, result)
        return result

    def analyze_with_knowledge(
        self,
        abnormal_items: List[Dict],
        enable_cot: bool = True,
        **kwargs
    ) -> Any:
        import json
        cache_key = self.cache.make_key(
            "analyze",
            abnormal_items=json.dumps(abnormal_items, sort_keys=True, ensure_ascii=False),
            enable_cot=enable_cot,
            kwargs=json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        result = self.client.analyze_with_knowledge(abnormal_items, enable_cot=enable_cot, **kwargs)
        self.cache.set(cache_key, result)
        return result
