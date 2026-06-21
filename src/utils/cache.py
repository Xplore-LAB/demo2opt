"""缓存机制实现"""
import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class CacheBackend(ABC):
    """缓存后端抽象接口"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
        """删除缓存"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空缓存"""
        pass


class MemoryCache(CacheBackend):
    """内存缓存实现"""
    
    def __init__(self, default_ttl: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        if entry["expires_at"] and time.time() > entry["expires_at"]:
            del self.cache[key]
            return None
        
        return entry["value"]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = None
        if ttl is not None or self.default_ttl:
            expires_at = time.time() + (ttl if ttl is not None else self.default_ttl)
        
        self.cache[key] = {
            "value": value,
            "expires_at": expires_at,
            "created_at": time.time()
        }
    
    def delete(self, key: str) -> None:
        self.cache.pop(key, None)
    
    def clear(self) -> None:
        self.cache.clear()


class ResponseCache:
    """响应缓存管理器"""
    
    def __init__(self, backend: Optional[CacheBackend] = None, enabled: bool = True):
        self.backend = backend or MemoryCache()
        self.enabled = enabled
    
    def make_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        content = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        hash_value = hashlib.md5(content.encode()).hexdigest()
        return f"{prefix}:{hash_value}"
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if not self.enabled:
            return None
        return self.backend.get(key)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存"""
        if not self.enabled:
            return
        self.backend.set(key, value, ttl)
    
    def delete(self, key: str) -> None:
        """删除缓存"""
        self.backend.delete(key)
    
    def clear(self) -> None:
        """清空缓存"""
        self.backend.clear()
