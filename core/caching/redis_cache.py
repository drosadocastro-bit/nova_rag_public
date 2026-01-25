"""
Redis Distributed Cache for NOVA NIC.

Distributed caching layer for horizontal scaling with:
- TTL-based expiration
- Domain-based invalidation
- Pub/sub for multi-instance sync
- Connection pooling
- Serialization/compression
"""

import asyncio
import hashlib
import json
import logging
import os
import pickle
import threading
import time
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Try to import redis
try:
    import redis  # type: ignore
    from redis import asyncio as aioredis  # type: ignore
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning(
        "redis-py not installed. Install with: pip install redis\n"
        "Using in-memory fallback."
    )


class SerializationFormat(str, Enum):
    """Cache value serialization formats."""
    
    JSON = "json"
    PICKLE = "pickle"
    COMPRESSED_PICKLE = "compressed_pickle"


@dataclass
class RedisCacheConfig:
    """Configuration for Redis cache."""
    
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    
    # Connection pool
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    
    # Cache behavior
    default_ttl_seconds: int = 3600
    key_prefix: str = "nova:"
    serialization: SerializationFormat = SerializationFormat.COMPRESSED_PICKLE
    
    # Compression
    compression_threshold_bytes: int = 1024
    compression_level: int = 6
    
    # Pub/sub for invalidation
    enable_pubsub: bool = True
    invalidation_channel: str = "nova:invalidations"
    
    @classmethod
    def from_env(cls) -> "RedisCacheConfig":
        """Create config from environment variables."""
        return cls(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            db=int(os.environ.get("REDIS_DB", "0")),
            password=os.environ.get("REDIS_PASSWORD"),
            default_ttl_seconds=int(
                os.environ.get("REDIS_DEFAULT_TTL", "3600")
            ),
            key_prefix=os.environ.get("REDIS_KEY_PREFIX", "nova:"),
        )


@dataclass
class CacheEntry:
    """Cached entry with metadata."""
    
    value: Any
    created_at: float
    expires_at: float
    domain: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    
    @property
    def ttl_remaining(self) -> float:
        """Remaining TTL in seconds."""
        return max(0, self.expires_at - time.time())
    
    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return time.time() > self.expires_at


class RedisDistributedCache:
    """
    Redis-based distributed cache for horizontal scaling.
    
    Features:
    - Automatic serialization/compression
    - TTL-based expiration
    - Domain-based invalidation
    - Pub/sub for multi-instance sync
    - Connection pooling
    """
    
    def __init__(self, config: Optional[RedisCacheConfig] = None):
        """
        Initialize Redis cache.
        
        Args:
            config: Cache configuration
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis-py is required. Install with: pip install redis"
            )
        
        self.config = config or RedisCacheConfig.from_env()
        
        # Connection pool
        self._pool = redis.ConnectionPool(  # type: ignore
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            max_connections=self.config.max_connections,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            decode_responses=False,  # We handle serialization
        )
        
        self._client = redis.Redis(connection_pool=self._pool)  # type: ignore
        
        # Pub/sub for invalidations
        self._pubsub: Optional[redis.client.PubSub] = None  # type: ignore
        self._pubsub_thread: Optional[threading.Thread] = None
        self._invalidation_handlers: List[Callable[[str, str], None]] = []
        
        if self.config.enable_pubsub:
            self._start_pubsub()
        
        # Metrics
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._invalidations = 0
        
        logger.info(
            f"RedisDistributedCache initialized: {self.config.host}:{self.config.port}, "
            f"db={self.config.db}, prefix={self.config.key_prefix}"
        )
    
    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.config.key_prefix}{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value for storage."""
        if self.config.serialization == SerializationFormat.JSON:
            return json.dumps(value).encode("utf-8")
        
        elif self.config.serialization == SerializationFormat.PICKLE:
            return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        
        else:  # COMPRESSED_PICKLE
            data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            if len(data) > self.config.compression_threshold_bytes:
                compressed = zlib.compress(data, self.config.compression_level)
                # Prefix with 'Z' to indicate compression
                return b"Z" + compressed
            return b"U" + data  # 'U' for uncompressed
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from storage."""
        if self.config.serialization == SerializationFormat.JSON:
            return json.loads(data.decode("utf-8"))
        
        elif self.config.serialization == SerializationFormat.PICKLE:
            return pickle.loads(data)
        
        else:  # COMPRESSED_PICKLE
            if data[0:1] == b"Z":
                data = zlib.decompress(data[1:])
                return pickle.loads(data)
            return pickle.loads(data[1:])  # Skip 'U' prefix
    
    def _start_pubsub(self) -> None:
        """Start pub/sub listener for invalidations."""
        self._pubsub = self._client.pubsub()
        if self._pubsub is None:
            logger.warning("Pub/sub not available")
            return
        self._pubsub.subscribe(self.config.invalidation_channel)
        
        def listen():
            if self._pubsub is None:
                return
            for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        key = data.get("key", "")
                        reason = data.get("reason", "")
                        
                        for handler in self._invalidation_handlers:
                            try:
                                handler(key, reason)
                            except Exception as e:
                                logger.error(f"Invalidation handler error: {e}")
                    except Exception as e:
                        logger.error(f"Pub/sub message error: {e}")
        
        self._pubsub_thread = threading.Thread(
            target=listen,
            daemon=True,
            name="RedisInvalidationListener"
        )
        self._pubsub_thread.start()
    
    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            default: Default if not found
            
        Returns:
            Cached value or default
        """
        full_key = self._make_key(key)
        
        try:
            data = self._client.get(full_key)
            
            if data is None:
                self._misses += 1
                return default
            
            self._hits += 1
            return self._deserialize(data)
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self._misses += 1
            return default
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        domain: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = default)
            domain: Domain for invalidation
            tags: Tags for invalidation
            
        Returns:
            True if successful
        """
        full_key = self._make_key(key)
        ttl = ttl or self.config.default_ttl_seconds
        
        try:
            # Serialize
            data = self._serialize(value)
            
            # Set with TTL
            self._client.setex(full_key, ttl, data)
            self._sets += 1
            
            # Track domain membership
            if domain:
                domain_key = f"{self.config.key_prefix}domain:{domain}"
                self._client.sadd(domain_key, key)
                self._client.expire(domain_key, ttl * 2)  # Longer TTL for set
            
            # Track tags
            if tags:
                for tag in tags:
                    tag_key = f"{self.config.key_prefix}tag:{tag}"
                    self._client.sadd(tag_key, key)
                    self._client.expire(tag_key, ttl * 2)
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        full_key = self._make_key(key)
        
        try:
            return self._client.delete(full_key) > 0
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def invalidate_by_domain(self, domain: str) -> int:
        """
        Invalidate all keys in a domain.
        
        Args:
            domain: Domain to invalidate
            
        Returns:
            Number of keys invalidated
        """
        domain_key = f"{self.config.key_prefix}domain:{domain}"
        
        try:
            # Get all keys in domain
            keys = self._client.smembers(domain_key)
            
            if not keys:
                return 0
            
            # Delete all keys
            full_keys = [self._make_key(k.decode()) for k in keys]
            deleted = self._client.delete(*full_keys)
            
            # Delete domain set
            self._client.delete(domain_key)
            
            self._invalidations += deleted
            
            # Publish invalidation
            if self.config.enable_pubsub:
                self._publish_invalidation(domain, "domain_invalidation")
            
            logger.info(f"Invalidated {deleted} keys in domain: {domain}")
            return deleted
            
        except Exception as e:
            logger.error(f"Domain invalidation error: {e}")
            return 0
    
    def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all keys with a tag.
        
        Args:
            tag: Tag to invalidate
            
        Returns:
            Number of keys invalidated
        """
        tag_key = f"{self.config.key_prefix}tag:{tag}"
        
        try:
            keys = self._client.smembers(tag_key)
            
            if not keys:
                return 0
            
            full_keys = [self._make_key(k.decode()) for k in keys]
            deleted = self._client.delete(*full_keys)
            
            self._client.delete(tag_key)
            self._invalidations += deleted
            
            return deleted
            
        except Exception as e:
            logger.error(f"Tag invalidation error: {e}")
            return 0
    
    def _publish_invalidation(self, key: str, reason: str) -> None:
        """Publish invalidation event."""
        try:
            message = json.dumps({"key": key, "reason": reason})
            self._client.publish(self.config.invalidation_channel, message)
        except Exception as e:
            logger.error(f"Publish invalidation error: {e}")
    
    def on_invalidation(
        self,
        handler: Callable[[str, str], None]
    ) -> None:
        """
        Register invalidation handler.
        
        Handler receives (key, reason) for each invalidation.
        """
        self._invalidation_handlers.append(handler)
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        full_key = self._make_key(key)
        try:
            return self._client.exists(full_key) > 0
        except Exception:
            return False
    
    def ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        full_key = self._make_key(key)
        try:
            return self._client.ttl(full_key)
        except Exception:
            return -2
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once."""
        full_keys = [self._make_key(k) for k in keys]
        
        try:
            values = self._client.mget(full_keys)
            result = {}
            
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value)
                    self._hits += 1
                else:
                    self._misses += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Mget error: {e}")
            return {}
    
    def set_many(
        self,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> int:
        """Set multiple keys at once."""
        ttl = ttl or self.config.default_ttl_seconds
        success = 0
        
        try:
            pipe = self._client.pipeline()
            
            for key, value in items.items():
                full_key = self._make_key(key)
                data = self._serialize(value)
                pipe.setex(full_key, ttl, data)
            
            pipe.execute()
            success = len(items)
            self._sets += success
            
        except Exception as e:
            logger.error(f"Mset error: {e}")
        
        return success
    
    def clear_prefix(self, prefix: str) -> int:
        """Clear all keys with prefix."""
        pattern = f"{self.config.key_prefix}{prefix}*"
        
        try:
            cursor = 0
            deleted = 0
            
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += self._client.delete(*keys)
                if cursor == 0:
                    break
            
            return deleted
            
        except Exception as e:
            logger.error(f"Clear prefix error: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            info = self._client.info("memory")
            memory_used = info.get("used_memory_human", "unknown")
        except Exception:
            memory_used = "unknown"
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                self._hits / (self._hits + self._misses)
                if (self._hits + self._misses) > 0 else 0.0
            ),
            "sets": self._sets,
            "invalidations": self._invalidations,
            "memory_used": memory_used,
            "host": self.config.host,
            "port": self.config.port,
            "db": self.config.db,
        }
    
    def health_check(self) -> Tuple[bool, str]:
        """Check Redis connection health."""
        try:
            self._client.ping()
            return True, "Redis connected"
        except Exception as e:
            return False, f"Redis error: {e}"
    
    def close(self) -> None:
        """Close connections."""
        if self._pubsub:
            self._pubsub.close()
        self._pool.disconnect()
        logger.info("RedisDistributedCache closed")


class AsyncRedisCache:
    """
    Async Redis cache for use in async contexts.
    """
    
    def __init__(self, config: Optional[RedisCacheConfig] = None):
        """Initialize async Redis cache."""
        if not REDIS_AVAILABLE:
            raise ImportError("redis-py required: pip install redis")
        
        self.config = config or RedisCacheConfig.from_env()
        self._client: Optional[aioredis.Redis] = None  # type: ignore
    
    async def connect(self) -> None:
        """Connect to Redis."""
        self._client = aioredis.Redis(  # type: ignore
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
        )
        if self._client is None:
            raise RuntimeError("Failed to create Redis client")
        await self._client.ping()
        logger.info(f"AsyncRedisCache connected to {self.config.host}:{self.config.port}")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache."""
        if not self._client:
            await self.connect()
        
        if self._client is None:
            return default
        
        full_key = f"{self.config.key_prefix}{key}"
        data = await self._client.get(full_key)
        
        if data is None:
            return default
        
        # Simple JSON deserialization for async
        return json.loads(data)
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache."""
        if not self._client:
            await self.connect()
        
        if self._client is None:
            return False
        
        full_key = f"{self.config.key_prefix}{key}"
        ttl = ttl or self.config.default_ttl_seconds
        
        data = json.dumps(value)
        await self._client.setex(full_key, ttl, data)
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete from cache."""
        if not self._client:
            await self.connect()
        
        if self._client is None:
            return False
        
        full_key = f"{self.config.key_prefix}{key}"
        return await self._client.delete(full_key) > 0
    
    async def close(self) -> None:
        """Close connection."""
        if self._client:
            await self._client.close()


# ==================
# Global Instance
# ==================

_global_cache: Optional[RedisDistributedCache] = None


def get_redis_cache() -> RedisDistributedCache:
    """Get or create global Redis cache."""
    global _global_cache
    
    if _global_cache is None:
        _global_cache = RedisDistributedCache()
    
    return _global_cache


def set_redis_cache(cache: RedisDistributedCache) -> None:
    """Set global Redis cache."""
    global _global_cache
    _global_cache = cache
