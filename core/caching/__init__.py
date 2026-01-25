"""
Nova NIC Caching Module.

Provides versioned cache management and enhanced query caching
for high-performance retrieval operations.
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
]
