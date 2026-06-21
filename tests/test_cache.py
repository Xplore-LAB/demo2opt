"""测试缓存机制"""
import time
import pytest
from src.utils.cache import MemoryCache, ResponseCache


class TestMemoryCache:
    """测试内存缓存"""
    
    def test_set_and_get(self):
        cache = MemoryCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_get_nonexistent(self):
        cache = MemoryCache()
        assert cache.get("nonexistent") is None
    
    def test_ttl_expiration(self):
        cache = MemoryCache(default_ttl=1)
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None
    
    def test_delete(self):
        cache = MemoryCache()
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None
    
    def test_clear(self):
        cache = MemoryCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestResponseCache:
    """测试响应缓存管理器"""
    
    def test_make_key(self):
        cache = ResponseCache()
        key1 = cache.make_key("test", param1="value1", param2="value2")
        key2 = cache.make_key("test", param1="value1", param2="value2")
        key3 = cache.make_key("test", param1="value1", param2="value3")
        
        assert key1 == key2
        assert key1 != key3
    
    def test_disabled_cache(self):
        cache = ResponseCache(enabled=False)
        cache.set("key1", "value1")
        assert cache.get("key1") is None
    
    def test_enabled_cache(self):
        cache = ResponseCache(enabled=True)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
