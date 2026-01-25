"""
Nova NIC Caching Module.

Provides versioned cache management, enhanced query caching,
and distributed Redis caching for high-performance retrieval operations.
"""

from .cache_manager import VersionedCacheManager
from .index_version import IndexVersion
from .query_cache import (
    QueryCache,
    CacheEntry,
    CacheStats,
    WarmingQuery,
    cached_query,
    get_query_cache,
    reset_query_cache,
)

# Redis distributed cache (optional)
try:
    from .redis_cache import (
        RedisDistributedCache,
        RedisCacheConfig,
        AsyncRedisCache,
        SerializationFormat,
        get_redis_cache,
        set_redis_cache,
    )
    REDIS_CACHE_AVAILABLE = True
except ImportError:
    REDIS_CACHE_AVAILABLE = False

__all__ = [
    # Cache manager
    "VersionedCacheManager",
    "IndexVersion",
    # Query cache
    "QueryCache",
    "CacheEntry",
    "CacheStats",
    "WarmingQuery",
    "cached_query",
    "get_query_cache",
    "reset_query_cache",
    # Redis cache
    "REDIS_CACHE_AVAILABLE",
]

if REDIS_CACHE_AVAILABLE:
    __all__.extend([
        "RedisDistributedCache",
        "RedisCacheConfig",
        "AsyncRedisCache",
        "SerializationFormat",
        "get_redis_cache",
        "set_redis_cache",
    ])
