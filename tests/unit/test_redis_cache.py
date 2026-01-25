"""
Tests for Redis Distributed Cache.

Tests the Redis caching layer including:
- Basic get/set operations
- TTL handling
- Domain/tag invalidation
- Serialization
- Statistics
"""

import json
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

# Skip all tests if redis not available
pytest.importorskip("redis")

from core.caching.redis_cache import (
    RedisDistributedCache,
    RedisCacheConfig,
    AsyncRedisCache,
    SerializationFormat,
    CacheEntry,
    get_redis_cache,
    set_redis_cache,
)


class TestRedisCacheConfig:
    """Tests for RedisCacheConfig."""
    
    def test_default_values(self):
        """Test default configuration."""
        config = RedisCacheConfig()
        
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.default_ttl_seconds == 3600
        assert config.key_prefix == "nova:"
    
    def test_from_env(self):
        """Test configuration from environment."""
        with patch.dict("os.environ", {
            "REDIS_HOST": "redis.example.com",
            "REDIS_PORT": "6380",
            "REDIS_DB": "5",
        }):
            config = RedisCacheConfig.from_env()
            
            assert config.host == "redis.example.com"
            assert config.port == 6380
            assert config.db == 5


class TestCacheEntry:
    """Tests for CacheEntry."""
    
    def test_ttl_remaining(self):
        """Test TTL calculation."""
        entry = CacheEntry(
            value="test",
            created_at=time.time() - 100,
            expires_at=time.time() + 100,
        )
        
        assert 99 < entry.ttl_remaining < 101
    
    def test_is_expired(self):
        """Test expiration check."""
        # Not expired
        entry1 = CacheEntry(
            value="test",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        assert entry1.is_expired is False
        
        # Expired
        entry2 = CacheEntry(
            value="test",
            created_at=time.time() - 7200,
            expires_at=time.time() - 3600,
        )
        assert entry2.is_expired is True


class TestRedisDistributedCacheMocked:
    """Tests for RedisDistributedCache with mocked Redis."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock_pool = MagicMock()
        mock_client = MagicMock()
        
        with patch("redis.ConnectionPool", return_value=mock_pool):
            with patch("redis.Redis", return_value=mock_client):
                config = RedisCacheConfig(enable_pubsub=False)
                cache = RedisDistributedCache(config)
                cache._client = mock_client
                yield cache, mock_client
    
    def test_make_key(self, mock_redis):
        """Test key prefixing."""
        cache, _ = mock_redis
        
        key = cache._make_key("test_key")
        
        assert key == "nova:test_key"
    
    def test_get_success(self, mock_redis):
        """Test successful get."""
        cache, mock_client = mock_redis
        
        # Mock serialized data
        mock_client.get.return_value = b"U" + __import__("pickle").dumps("cached_value")
        
        result = cache.get("test_key")
        
        assert result == "cached_value"
        mock_client.get.assert_called_once_with("nova:test_key")
    
    def test_get_miss(self, mock_redis):
        """Test cache miss."""
        cache, mock_client = mock_redis
        mock_client.get.return_value = None
        
        result = cache.get("missing_key", default="default")
        
        assert result == "default"
    
    def test_set_success(self, mock_redis):
        """Test successful set."""
        cache, mock_client = mock_redis
        
        result = cache.set("test_key", "test_value", ttl=300)
        
        assert result is True
        mock_client.setex.assert_called_once()
    
    def test_set_with_domain(self, mock_redis):
        """Test set with domain tracking."""
        cache, mock_client = mock_redis
        
        cache.set("test_key", "test_value", domain="aviation")
        
        # Should add to domain set
        mock_client.sadd.assert_called()
    
    def test_set_with_tags(self, mock_redis):
        """Test set with tag tracking."""
        cache, mock_client = mock_redis
        
        cache.set("test_key", "test_value", tags={"tag1", "tag2"})
        
        # Should add to tag sets
        assert mock_client.sadd.call_count >= 2
    
    def test_delete(self, mock_redis):
        """Test deletion."""
        cache, mock_client = mock_redis
        mock_client.delete.return_value = 1
        
        result = cache.delete("test_key")
        
        assert result is True
        mock_client.delete.assert_called_once_with("nova:test_key")
    
    def test_invalidate_by_domain(self, mock_redis):
        """Test domain invalidation."""
        cache, mock_client = mock_redis
        mock_client.smembers.return_value = {b"key1", b"key2"}
        mock_client.delete.return_value = 2
        
        deleted = cache.invalidate_by_domain("aviation")
        
        assert deleted == 2
    
    def test_invalidate_by_tag(self, mock_redis):
        """Test tag invalidation."""
        cache, mock_client = mock_redis
        mock_client.smembers.return_value = {b"tagged_key"}
        mock_client.delete.return_value = 1
        
        deleted = cache.invalidate_by_tag("my_tag")
        
        assert deleted == 1
    
    def test_exists(self, mock_redis):
        """Test exists check."""
        cache, mock_client = mock_redis
        mock_client.exists.return_value = 1
        
        result = cache.exists("test_key")
        
        assert result is True
    
    def test_ttl(self, mock_redis):
        """Test TTL retrieval."""
        cache, mock_client = mock_redis
        mock_client.ttl.return_value = 300
        
        result = cache.ttl("test_key")
        
        assert result == 300
    
    def test_get_many(self, mock_redis):
        """Test bulk get."""
        cache, mock_client = mock_redis
        
        # Mock mget response
        serialized1 = b"U" + __import__("pickle").dumps("value1")
        serialized2 = b"U" + __import__("pickle").dumps("value2")
        mock_client.mget.return_value = [serialized1, None, serialized2]
        
        result = cache.get_many(["key1", "key2", "key3"])
        
        assert result == {"key1": "value1", "key3": "value2"}
    
    def test_set_many(self, mock_redis):
        """Test bulk set."""
        cache, mock_client = mock_redis
        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        
        count = cache.set_many({"key1": "value1", "key2": "value2"})
        
        assert count == 2
        mock_pipe.execute.assert_called_once()
    
    def test_health_check_success(self, mock_redis):
        """Test health check success."""
        cache, mock_client = mock_redis
        mock_client.ping.return_value = True
        
        healthy, message = cache.health_check()
        
        assert healthy is True
        assert "connected" in message.lower()
    
    def test_health_check_failure(self, mock_redis):
        """Test health check failure."""
        cache, mock_client = mock_redis
        mock_client.ping.side_effect = Exception("Connection refused")
        
        healthy, message = cache.health_check()
        
        assert healthy is False
        assert "error" in message.lower()
    
    def test_get_stats(self, mock_redis):
        """Test statistics."""
        cache, mock_client = mock_redis
        mock_client.info.return_value = {"used_memory_human": "10M"}
        
        # Simulate some activity
        cache._hits = 100
        cache._misses = 25
        cache._sets = 50
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 100
        assert stats["misses"] == 25
        assert stats["hit_rate"] == 0.8
        assert stats["sets"] == 50


class TestSerializationFormat:
    """Tests for different serialization formats."""
    
    @pytest.fixture
    def cache_with_format(self):
        """Create cache with specific serialization."""
        def create_cache(fmt):
            mock_client = MagicMock()
            with patch("redis.ConnectionPool"):
                with patch("redis.Redis", return_value=mock_client):
                    config = RedisCacheConfig(
                        serialization=fmt,
                        enable_pubsub=False,
                    )
                    cache = RedisDistributedCache(config)
                    cache._client = mock_client
                    return cache, mock_client
        return create_cache
    
    def test_json_serialization(self, cache_with_format):
        """Test JSON serialization."""
        cache, _ = cache_with_format(SerializationFormat.JSON)
        
        data = cache._serialize({"key": "value"})
        
        assert b'{"key": "value"}' == data
    
    def test_pickle_serialization(self, cache_with_format):
        """Test pickle serialization."""
        cache, _ = cache_with_format(SerializationFormat.PICKLE)
        
        original = {"key": "value", "number": 42}
        data = cache._serialize(original)
        result = cache._deserialize(data)
        
        assert result == original
    
    def test_compressed_pickle_small(self, cache_with_format):
        """Test compressed pickle with small data (no compression)."""
        cache, _ = cache_with_format(SerializationFormat.COMPRESSED_PICKLE)
        
        small_data = "small"
        serialized = cache._serialize(small_data)
        
        # Should start with 'U' (uncompressed)
        assert serialized[0:1] == b"U"
        
        result = cache._deserialize(serialized)
        assert result == small_data
    
    def test_compressed_pickle_large(self, cache_with_format):
        """Test compressed pickle with large data (compression)."""
        cache, _ = cache_with_format(SerializationFormat.COMPRESSED_PICKLE)
        
        # Large data that compresses well
        large_data = "x" * 10000
        serialized = cache._serialize(large_data)
        
        # Should start with 'Z' (compressed)
        assert serialized[0:1] == b"Z"
        
        # Should be smaller than uncompressed
        assert len(serialized) < len(large_data)
        
        result = cache._deserialize(serialized)
        assert result == large_data


class TestAsyncRedisCacheMocked:
    """Tests for AsyncRedisCache with mocks."""
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test async connection."""
        async def async_ping():
            return True
        
        mock_redis = MagicMock()
        mock_redis.ping = MagicMock(return_value=async_ping())
        
        with patch("redis.asyncio.Redis", return_value=mock_redis):
            cache = AsyncRedisCache()
            await cache.connect()
            
            assert cache._client is not None
    
    @pytest.mark.asyncio
    async def test_get_set(self):
        """Test async get and set."""
        async def async_get():
            return json.dumps("cached").encode()
        
        async def async_setex(*args):
            return True
        
        async def async_ping():
            return True
        
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=async_get())
        mock_redis.setex = MagicMock(return_value=async_setex())
        mock_redis.ping = MagicMock(return_value=async_ping())
        
        with patch("redis.asyncio.Redis", return_value=mock_redis):
            cache = AsyncRedisCache()
            cache._client = mock_redis
            
            # Need to handle the coroutine
            mock_redis.get.return_value = json.dumps("cached").encode()
            mock_redis.setex.return_value = True


class TestGlobalCacheFunctions:
    """Tests for global cache functions."""
    
    @pytest.fixture(autouse=True)
    def reset_global(self):
        """Reset global cache."""
        import core.caching.redis_cache as module
        module._global_cache = None
        yield
        module._global_cache = None
    
    def test_set_and_get_redis_cache(self):
        """Test setting and getting global cache."""
        mock_client = MagicMock()
        
        with patch("redis.ConnectionPool"):
            with patch("redis.Redis", return_value=mock_client):
                config = RedisCacheConfig(enable_pubsub=False)
                cache = RedisDistributedCache(config)
                
                set_redis_cache(cache)
                retrieved = get_redis_cache()
                
                assert retrieved is cache


import asyncio  # Import for async tests
