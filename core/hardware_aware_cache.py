"""
Hardware-Aware Cache Strategy - Phase 4.2.

Implements tiered caching with memory-aware eviction
and compression for potato hardware optimization.

Features:
- LRU cache with memory limits
- Compression for large results
- Adaptive TTL based on hardware
- Metrics and monitoring
"""

import os
import logging
import json
import time
import zlib
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for hardware tier caching."""
    
    max_items: int
    max_memory_mb: int
    ttl_seconds: int
    compress_threshold_kb: int = 10
    enable_compression: bool = False
    enable_eviction: bool = True
    
    @classmethod
    def for_tier(cls, tier: str) -> "CacheConfig":
        """Get cache config for hardware tier."""
        configs = {
            "ultra_lite": cls(
                max_items=50,
                max_memory_mb=25,
                ttl_seconds=300,
                compress_threshold_kb=5,
                enable_compression=True,
                enable_eviction=True,
            ),
            "lite": cls(
                max_items=200,
                max_memory_mb=100,
                ttl_seconds=600,
                compress_threshold_kb=10,
                enable_compression=True,
                enable_eviction=True,
            ),
            "standard": cls(
                max_items=500,
                max_memory_mb=300,
                ttl_seconds=1800,
                compress_threshold_kb=50,
                enable_compression=False,
                enable_eviction=True,
            ),
            "full": cls(
                max_items=2000,
                max_memory_mb=1000,
                ttl_seconds=3600,
                compress_threshold_kb=100,
                enable_compression=False,
                enable_eviction=False,  # Evict only on OOM
            ),
        }
        return configs.get(tier, configs["standard"])


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    
    key: str
    value: Any
    compressed: bool = False
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    size_bytes: int = 0
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if entry is expired."""
        return time.time() - self.created_at > ttl_seconds
    
    def update_access(self) -> None:
        """Update access metadata."""
        self.accessed_at = time.time()
        self.access_count += 1


class HardwareAwareCache:
    """
    LRU cache with memory limits and compression.
    
    Automatically adapts to available hardware resources.
    """
    
    def __init__(self, config: CacheConfig):
        """
        Initialize cache.
        
        Args:
            config: Cache configuration
        """
        self.config = config
        self.cache: Dict[str, CacheEntry] = {}
        self.current_memory_bytes = 0
        self.compression_ratio = 1.0
        
        logger.info(
            f"HardwareAwareCache initialized: "
            f"max_items={config.max_items}, "
            f"max_memory={config.max_memory_mb}MB, "
            f"compression={config.enable_compression}"
        )
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        
        # Check expiration
        if entry.is_expired(self.config.ttl_seconds):
            self._evict_key(key)
            return None
        
        # Update access metadata
        entry.update_access()
        
        # Decompress if needed
        value = entry.value
        if entry.compressed:
            try:
                value = json.loads(zlib.decompress(value).decode("utf-8"))
            except Exception as e:
                logger.warning(f"Decompression failed for key {key}: {e}")
                self._evict_key(key)
                return None
        
        return value
    
    def put(self, key: str, value: Any) -> bool:
        """
        Put value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (should be JSON-serializable)
            
        Returns:
            True if cached, False if rejected
        """
        # Serialize and optionally compress
        try:
            serialized = json.dumps(value)
            compressed = False
            
            if self.config.enable_compression:
                serialized_bytes = serialized.encode("utf-8")
                if len(serialized_bytes) > self.config.compress_threshold_kb * 1024:
                    compressed_data = zlib.compress(serialized_bytes, level=6)
                    ratio = len(compressed_data) / len(serialized_bytes)
                    if ratio < 0.8:  # Only compress if saves >20%
                        serialized = compressed_data
                        compressed = True
                        self.compression_ratio = ratio
            
        except Exception as e:
            logger.warning(f"Serialization failed for key {key}: {e}")
            return False
        
        # Estimate size
        size_bytes = len(serialized.encode("utf-8") if isinstance(serialized, str) else serialized)
        
        # Check if item exceeds max size
        if size_bytes > self.config.max_memory_mb * 1024 * 1024 / 2:
            logger.warning(f"Item too large for cache: {size_bytes} bytes")
            return False
        
        # Remove old entry if exists
        if key in self.cache:
            old_entry = self.cache[key]
            self.current_memory_bytes -= old_entry.size_bytes
        
        # Evict if needed
        while (
            self.config.enable_eviction
            and (
                len(self.cache) >= self.config.max_items
                or self.current_memory_bytes + size_bytes > self.config.max_memory_mb * 1024 * 1024
            )
            and self.cache
        ):
            self._evict_lru()
        
        # Add entry
        entry = CacheEntry(
            key=key,
            value=serialized,
            compressed=compressed,
            size_bytes=size_bytes,
        )
        
        self.cache[key] = entry
        self.current_memory_bytes += size_bytes
        
        return True
    
    def clear(self) -> None:
        """Clear entire cache."""
        self.cache.clear()
        self.current_memory_bytes = 0
        logger.info("Cache cleared")
    
    def _evict_lru(self) -> None:
        """Evict least-recently-used entry."""
        if not self.cache:
            return
        
        lru_key = min(
            self.cache.keys(),
            key=lambda k: (self.cache[k].accessed_at, self.cache[k].access_count)
        )
        self._evict_key(lru_key)
    
    def _evict_key(self, key: str) -> None:
        """Evict specific key."""
        if key in self.cache:
            entry = self.cache[key]
            self.current_memory_bytes -= entry.size_bytes
            del self.cache[key]
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_size_bytes = self.current_memory_bytes
        total_size_mb = total_size_bytes / 1024 / 1024
        
        # Count expired entries
        expired_count = sum(
            1 for entry in self.cache.values()
            if entry.is_expired(self.config.ttl_seconds)
        )
        
        # Count compressed entries
        compressed_count = sum(
            1 for entry in self.cache.values()
            if entry.compressed
        )
        
        return {
            "items": len(self.cache),
            "memory_mb": round(total_size_mb, 2),
            "memory_limit_mb": self.config.max_memory_mb,
            "utilization_percent": round(
                total_size_mb / self.config.max_memory_mb * 100, 1
            ),
            "expired_entries": expired_count,
            "compressed_entries": compressed_count,
            "compression_ratio": round(self.compression_ratio, 3),
            "avg_entry_size_kb": round(
                total_size_bytes / max(1, len(self.cache)) / 1024, 2
            ),
        }


class TieredCache:
    """
    Tiered cache system with L1 (hot) and L2 (warm) tiers.
    
    L1: Small, fast cache for recent results
    L2: Larger, slower cache with compression
    """
    
    def __init__(self, tier: str):
        """
        Initialize tiered cache.
        
        Args:
            tier: Hardware tier (ultra_lite, lite, standard, full)
        """
        config = CacheConfig.for_tier(tier)
        
        # L1: Hot cache (50% of config)
        l1_config = CacheConfig(
            max_items=max(10, config.max_items // 2),
            max_memory_mb=config.max_memory_mb // 2,
            ttl_seconds=config.ttl_seconds // 2,
            enable_compression=False,
            enable_eviction=True,
        )
        
        # L2: Warm cache (100% of config)
        l2_config = config
        
        self.l1 = HardwareAwareCache(l1_config)
        self.l2 = HardwareAwareCache(l2_config)
        
        self.hits_l1 = 0
        self.hits_l2 = 0
        self.misses = 0
        
        logger.info(f"TieredCache initialized for {tier} hardware")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from tiered cache."""
        # Try L1 first
        value = self.l1.get(key)
        if value is not None:
            self.hits_l1 += 1
            # Promote to L1 if in L2
            if key in self.l2.cache:
                self.l1.put(key, value)
            return value
        
        # Try L2
        value = self.l2.get(key)
        if value is not None:
            self.hits_l2 += 1
            # Promote to L1
            self.l1.put(key, value)
            return value
        
        self.misses += 1
        return None
    
    def put(self, key: str, value: Any) -> bool:
        """Put value in tiered cache."""
        # Always try L1 first
        if self.l1.put(key, value):
            # Also keep in L2
            self.l2.put(key, value)
            return True
        
        # If L1 full, try L2
        return self.l2.put(key, value)
    
    def clear(self) -> None:
        """Clear all tiers."""
        self.l1.clear()
        self.l2.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = self.hits_l1 + self.hits_l2
        total_requests = total_hits + self.misses
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "l1": self.l1.stats(),
            "l2": self.l2.stats(),
            "hits_l1": self.hits_l1,
            "hits_l2": self.hits_l2,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 1),
            "total_requests": total_requests,
        }


def create_hardware_cache(auto_detect: bool = True) -> TieredCache:
    """
    Create hardware-aware cache.
    
    Args:
        auto_detect: Auto-detect hardware tier
        
    Returns:
        Configured TieredCache instance
    """
    if auto_detect:
        from core.lazy_loading import get_model_registry
        registry = get_model_registry()
        tier = registry.tier.value
    else:
        tier = os.environ.get("NOVA_HARDWARE_TIER", "standard")
    
    logger.info(f"Creating hardware-aware cache for {tier}")
    return TieredCache(tier)
