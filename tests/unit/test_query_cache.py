"""Tests for enhanced query cache module."""

import os
import tempfile
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from core.caching.query_cache import (
    CacheEntry,
    CacheStats,
    QueryCache,
    WarmingQuery,
    cached_query,
    get_query_cache,
    reset_query_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""
    
    def test_cache_entry_creation(self):
        """Test basic entry creation."""
        now = time.time()
        entry = CacheEntry(
            key="test_key",
            value={"result": "data"},
            created_at=now,
            expires_at=now + 3600,
            domain="medical",
        )
        
        assert entry.key == "test_key"
        assert entry.value == {"result": "data"}
        assert entry.domain == "medical"
        assert entry.hit_count == 0
    
    def test_is_expired_false(self):
        """Test entry not expired."""
        now = time.time()
        entry = CacheEntry(
            key="k",
            value="v",
            created_at=now,
            expires_at=now + 3600,
        )
        assert not entry.is_expired()
    
    def test_is_expired_true(self):
        """Test entry expired."""
        now = time.time()
        entry = CacheEntry(
            key="k",
            value="v",
            created_at=now - 7200,
            expires_at=now - 3600,
        )
        assert entry.is_expired()
    
    def test_touch_updates_stats(self):
        """Test touch updates hit count and access time."""
        now = time.time()
        entry = CacheEntry(
            key="k",
            value="v",
            created_at=now,
            expires_at=now + 3600,
            last_accessed=now - 100,
        )
        
        entry.touch()
        
        assert entry.hit_count == 1
        assert entry.last_accessed > now - 100


class TestCacheStats:
    """Tests for CacheStats."""
    
    def test_hit_rate_with_hits(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=80, misses=20)
        assert stats.hit_rate == 0.8
    
    def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0
    
    def test_to_dict(self):
        """Test stats serialization."""
        stats = CacheStats(hits=10, misses=5, evictions=2)
        d = stats.to_dict()
        
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["evictions"] == 2
        assert "hit_rate" in d


class TestQueryCache:
    """Tests for QueryCache."""
    
    def test_set_and_get(self):
        """Test basic set and get."""
        cache = QueryCache(max_entries=100, auto_cleanup_interval=0)
        
        cache.set("test query", ["result1", "result2"])
        result = cache.get("test query")
        
        assert result == ["result1", "result2"]
        cache.stop()
    
    def test_get_miss(self):
        """Test cache miss."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        result = cache.get("nonexistent")
        
        assert result is None
        assert cache.get_stats().misses == 1
        cache.stop()
    
    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = QueryCache(default_ttl_seconds=1, auto_cleanup_interval=0)
        
        cache.set("query", "result")
        assert cache.get("query") == "result"
        
        time.sleep(1.1)
        assert cache.get("query") is None
        cache.stop()
    
    def test_domain_based_invalidation(self):
        """Test invalidation by domain."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        cache.set("query1", "result1", domain="medical")
        cache.set("query2", "result2", domain="medical")
        cache.set("query3", "result3", domain="aerospace")
        
        invalidated = cache.invalidate_by_domain("medical")
        
        assert invalidated == 2
        assert cache.get("query1", domain="medical") is None
        assert cache.get("query2", domain="medical") is None
        assert cache.get("query3", domain="aerospace") == "result3"
        cache.stop()
    
    def test_invalidate_all(self):
        """Test clearing entire cache."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        cache.set("q3", "r3")
        
        count = cache.invalidate_all()
        
        assert count == 3
        assert len(cache) == 0
        cache.stop()
    
    def test_lru_eviction(self):
        """Test LRU eviction when max entries reached."""
        cache = QueryCache(max_entries=3, auto_cleanup_interval=0)
        
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        cache.set("q3", "r3")
        
        # Access q1 to make it recently used
        cache.get("q1")
        
        # Add q4, should evict q2 (least recently used)
        cache.set("q4", "r4")
        
        assert cache.get("q1") is not None  # Still there
        assert cache.get("q2") is None  # Evicted
        cache.stop()
    
    def test_size_based_eviction(self):
        """Test eviction based on size limit."""
        cache = QueryCache(
            max_entries=1000,
            max_size_bytes=1024,  # 1KB
            auto_cleanup_interval=0
        )
        
        # Add large entry
        large_data = "x" * 500
        cache.set("q1", large_data)
        cache.set("q2", large_data)
        cache.set("q3", large_data)
        
        # Should have evicted some due to size
        stats = cache.get_stats()
        assert stats.evictions > 0
        cache.stop()
    
    def test_cache_key_with_kwargs(self):
        """Test cache key generation with kwargs."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        # Different kwargs should result in different keys
        cache.set("query", "result1", k=10)
        cache.set("query", "result2", k=20)
        
        assert cache.get("query", k=10) == "result1"
        assert cache.get("query", k=20) == "result2"
        cache.stop()
    
    def test_get_stats(self):
        """Test statistics tracking."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        cache.set("q1", "r1")
        cache.get("q1")  # Hit
        cache.get("q1")  # Hit
        cache.get("q2")  # Miss
        
        stats = cache.get_stats()
        
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.total_entries == 1
        cache.stop()
    
    def test_get_entries_by_domain(self):
        """Test getting entry count by domain."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        cache.set("q1", "r1", domain="medical")
        cache.set("q2", "r2", domain="medical")
        cache.set("q3", "r3", domain="aerospace")
        
        by_domain = cache.get_entries_by_domain()
        
        assert by_domain["medical"] == 2
        assert by_domain["aerospace"] == 1
        cache.stop()
    
    def test_get_hot_entries(self):
        """Test getting most accessed entries."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        cache.set("cold", "data")
        cache.set("hot", "data")
        
        # Access hot entry multiple times
        for _ in range(10):
            cache.get("hot")
        
        hot = cache.get_hot_entries(limit=5)
        
        assert len(hot) <= 5
        assert hot[0]["hit_count"] >= 10
        cache.stop()
    
    def test_invalidate_expired(self):
        """Test cleanup of expired entries."""
        cache = QueryCache(default_ttl_seconds=1, auto_cleanup_interval=0)
        
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        
        time.sleep(1.1)
        
        expired = cache.invalidate_expired()
        
        assert expired == 2
        assert len(cache) == 0
        cache.stop()


class TestCacheWarming:
    """Tests for cache warming functionality."""
    
    def test_configure_warming(self):
        """Test warming configuration."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        def executor(query, domain):
            return f"result for {query}"
        
        queries = [
            WarmingQuery(query="common query", priority=1),
            WarmingQuery(query="rare query", priority=0),
        ]
        
        cache.configure_warming(executor, queries)
        
        warmed = cache.warm_cache()
        
        assert warmed == 2
        assert cache.get("common query") is not None
        cache.stop()
    
    def test_add_warming_query(self):
        """Test adding warming queries."""
        cache = QueryCache(auto_cleanup_interval=0)
        cache.configure_warming(lambda q, d: f"result for {q}")
        
        cache.add_warming_query("new query", priority=5)
        
        warmed = cache.warm_cache()
        assert warmed == 1
        cache.stop()
    
    def test_warming_respects_interval(self):
        """Test warming respects refresh interval."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        call_count = 0
        def executor(query, domain):
            nonlocal call_count
            call_count += 1
            return "result"
        
        cache.configure_warming(executor, [
            WarmingQuery(query="q", refresh_interval_seconds=3600)
        ])
        
        cache.warm_cache()
        cache.warm_cache()  # Should skip (not due)
        
        assert call_count == 1
        cache.stop()


class TestCachePersistence:
    """Tests for cache persistence."""
    
    def test_save_and_load(self):
        """Test saving and loading cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.pkl"
            
            # Create and populate cache
            cache1 = QueryCache(
                persistence_path=cache_path,
                auto_cleanup_interval=0
            )
            cache1.set("q1", "r1", domain="test")
            cache1.set("q2", "r2")
            cache1.save_to_disk()
            cache1.stop()
            
            # Load in new cache
            cache2 = QueryCache(
                persistence_path=cache_path,
                auto_cleanup_interval=0
            )
            
            # Domain must match for cache hits
            assert cache2.get("q1", domain="test") == "r1"
            assert cache2.get("q2") == "r2"
            cache2.stop()


class TestCachedQueryDecorator:
    """Tests for cached_query decorator."""
    
    def test_decorator_caches_result(self):
        """Test decorator caches function result."""
        cache = QueryCache(auto_cleanup_interval=0)
        
        call_count = 0
        
        @cached_query(cache)
        def search(query: str, domain: Optional[str] = None):
            nonlocal call_count
            call_count += 1
            return f"result for {query}"
        
        # First call - should execute
        result1 = search("test query")
        assert result1 == "result for test query"
        assert call_count == 1
        
        # Second call - should use cache
        result2 = search("test query")
        assert result2 == "result for test query"
        assert call_count == 1  # No additional call
        
        cache.stop()


class TestGlobalCache:
    """Tests for global cache instance."""
    
    def test_get_query_cache(self):
        """Test getting global cache."""
        reset_query_cache()
        
        cache1 = get_query_cache()
        cache2 = get_query_cache()
        
        assert cache1 is cache2
        
        reset_query_cache()
    
    def test_reset_query_cache(self):
        """Test resetting global cache clears state."""
        reset_query_cache()  # Clean start
        
        # Get cache and add data
        cache1 = get_query_cache()
        cache1.set("test_key", "test_value")
        assert cache1.get("test_key") == "test_value"
        
        # Reset and verify data is gone
        reset_query_cache()
        cache2 = get_query_cache()
        
        # Data should not persist after reset
        assert cache2.get("test_key") is None
        
        reset_query_cache()
