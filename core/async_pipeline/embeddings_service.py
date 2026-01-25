"""
Async Embeddings Service for NOVA NIC.

High-performance async embedding generation with:
- Batched processing
- Connection pooling
- Retry with backoff
- Model warm-up
- Caching layer
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingStatus(str, Enum):
    """Status of embedding request."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CACHED = "cached"
    FAILED = "failed"


@dataclass
class EmbeddingRequest:
    """Request for embedding generation."""
    
    text: str
    request_id: str = ""
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.request_id:
            self.request_id = hashlib.sha256(self.text.encode()).hexdigest()[:12]


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    
    request_id: str
    text: str
    embedding: Optional[np.ndarray]
    status: EmbeddingStatus
    latency_ms: float = 0.0
    from_cache: bool = False
    error: Optional[str] = None
    model_name: str = ""
    dimension: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding embedding array)."""
        return {
            "request_id": self.request_id,
            "text_preview": self.text[:50] + "..." if len(self.text) > 50 else self.text,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "from_cache": self.from_cache,
            "error": self.error,
            "model_name": self.model_name,
            "dimension": self.dimension,
        }


class AsyncEmbeddingsService:
    """
    Async embeddings service with batching and caching.
    
    Features:
    - Automatic batching for throughput
    - LRU cache for repeated texts
    - Connection pooling
    - Retry with exponential backoff
    - Model warm-up on startup
    """
    
    def __init__(
        self,
        embed_fn: Optional[Callable[[List[str]], np.ndarray]] = None,
        model_name: str = "all-MiniLM-L6-v2",
        max_batch_size: int = 32,
        batch_timeout_ms: float = 50.0,
        max_concurrent_batches: int = 4,
        cache_size: int = 10000,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
    ):
        """
        Initialize async embeddings service.
        
        Args:
            embed_fn: Sync function that takes list of texts, returns embeddings
            model_name: Name of embedding model (for logging)
            max_batch_size: Maximum texts per batch
            batch_timeout_ms: Max wait time to fill batch
            max_concurrent_batches: Max parallel batch operations
            cache_size: Number of embeddings to cache
            max_retries: Maximum retry attempts
            retry_base_delay: Base delay for exponential backoff
        """
        self.embed_fn = embed_fn
        self.model_name = model_name
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self.max_concurrent_batches = max_concurrent_batches
        self.cache_size = cache_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        
        # Thread pool for sync embedding calls
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent_batches,
            thread_name_prefix="Embed"
        )
        
        # LRU cache: text_hash -> (embedding, timestamp)
        self._cache: OrderedDict[str, Tuple[np.ndarray, float]] = OrderedDict()
        
        # Batching state
        self._pending_requests: asyncio.Queue = asyncio.Queue()
        self._batcher_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Semaphore for concurrent batches
        self._batch_semaphore = asyncio.Semaphore(max_concurrent_batches)
        
        # Metrics
        self._total_requests = 0
        self._cache_hits = 0
        self._total_batches = 0
        self._total_texts_embedded = 0
        self._total_errors = 0
        self._embedding_dimension = 0
        
        logger.info(
            f"AsyncEmbeddingsService initialized: model={model_name}, "
            f"batch_size={max_batch_size}, cache_size={cache_size}"
        )
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash for caching."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    def _get_cached(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache."""
        text_hash = self._get_text_hash(text)
        if text_hash in self._cache:
            # Move to end (LRU)
            self._cache.move_to_end(text_hash)
            embedding, _ = self._cache[text_hash]
            self._cache_hits += 1
            return embedding
        return None
    
    def _put_cache(self, text: str, embedding: np.ndarray) -> None:
        """Put embedding in cache."""
        text_hash = self._get_text_hash(text)
        self._cache[text_hash] = (embedding, time.time())
        
        # Evict if over capacity
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
    
    async def embed_single(
        self,
        text: str,
        skip_cache: bool = False,
    ) -> EmbeddingResult:
        """
        Embed a single text.
        
        Args:
            text: Text to embed
            skip_cache: Skip cache lookup
            
        Returns:
            EmbeddingResult with embedding
        """
        results = await self.embed_batch([text], skip_cache=skip_cache)
        return results[0]
    
    async def embed_batch(
        self,
        texts: List[str],
        skip_cache: bool = False,
    ) -> List[EmbeddingResult]:
        """
        Embed a batch of texts.
        
        Args:
            texts: List of texts to embed
            skip_cache: Skip cache lookup
            
        Returns:
            List of EmbeddingResult in same order
        """
        if not texts:
            return []
        
        if not self.embed_fn:
            return [
                EmbeddingResult(
                    request_id=self._get_text_hash(t)[:12],
                    text=t,
                    embedding=None,
                    status=EmbeddingStatus.FAILED,
                    error="No embedding function configured",
                )
                for t in texts
            ]
        
        self._total_requests += len(texts)
        start_time = time.time()
        
        # Check cache for each text
        results: List[Optional[EmbeddingResult]] = [None] * len(texts)
        texts_to_embed: List[Tuple[int, str]] = []  # (original_index, text)
        
        for i, text in enumerate(texts):
            if not skip_cache:
                cached = self._get_cached(text)
                if cached is not None:
                    results[i] = EmbeddingResult(
                        request_id=self._get_text_hash(text)[:12],
                        text=text,
                        embedding=cached,
                        status=EmbeddingStatus.CACHED,
                        from_cache=True,
                        model_name=self.model_name,
                        dimension=len(cached),
                    )
                    continue
            
            texts_to_embed.append((i, text))
        
        # Embed remaining texts
        if texts_to_embed:
            embeddings = await self._embed_with_retry(
                [t for _, t in texts_to_embed]
            )
            
            for (orig_idx, text), embedding in zip(texts_to_embed, embeddings):
                if embedding is not None:
                    # Cache the result
                    self._put_cache(text, embedding)
                    
                    if self._embedding_dimension == 0:
                        self._embedding_dimension = len(embedding)
                    
                    results[orig_idx] = EmbeddingResult(
                        request_id=self._get_text_hash(text)[:12],
                        text=text,
                        embedding=embedding,
                        status=EmbeddingStatus.COMPLETED,
                        model_name=self.model_name,
                        dimension=len(embedding),
                    )
                else:
                    results[orig_idx] = EmbeddingResult(
                        request_id=self._get_text_hash(text)[:12],
                        text=text,
                        embedding=None,
                        status=EmbeddingStatus.FAILED,
                        error="Embedding generation failed",
                    )
        
        # Set latency on all results
        latency_ms = (time.time() - start_time) * 1000
        for r in results:
            if r:
                r.latency_ms = latency_ms / len(texts)  # Per-text latency
        
        return [r for r in results if r is not None]
    
    async def _embed_with_retry(
        self,
        texts: List[str],
    ) -> List[Optional[np.ndarray]]:
        """Embed with retry logic."""
        attempt = 0
        last_error = None
        
        while attempt < self.max_retries:
            try:
                async with self._batch_semaphore:
                    loop = asyncio.get_event_loop()
                    if self.embed_fn is None:
                        raise ValueError("Embedding function not configured")
                    embeddings = await loop.run_in_executor(
                        self._executor,
                        self.embed_fn,
                        texts,
                    )
                    
                    self._total_batches += 1
                    self._total_texts_embedded += len(texts)
                    
                    # Convert to list of arrays
                    if isinstance(embeddings, np.ndarray):
                        return [embeddings[i] for i in range(len(texts))]
                    return list(embeddings)
                    
            except Exception as e:
                attempt += 1
                last_error = str(e)
                self._total_errors += 1
                
                if attempt < self.max_retries:
                    delay = self.retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding attempt {attempt} failed, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
        
        logger.error(f"Embedding failed after {self.max_retries} attempts: {last_error}")
        return [None] * len(texts)
    
    async def embed_streaming(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
    ):
        """
        Stream embeddings for large text lists.
        
        Yields EmbeddingResult as each batch completes.
        """
        batch_size = batch_size or self.max_batch_size
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            results = await self.embed_batch(batch)
            for result in results:
                yield result
    
    def warm_up(self, sample_texts: Optional[List[str]] = None) -> None:
        """
        Warm up the embedding model.
        
        Call this at startup to ensure model is loaded.
        """
        if not self.embed_fn:
            return
        
        sample = sample_texts or [
            "This is a warm-up query for the embedding model.",
            "Safety-critical procedures require careful attention.",
            "Vehicle maintenance includes regular inspections.",
        ]
        
        try:
            logger.info(f"Warming up embedding model: {self.model_name}")
            start = time.time()
            
            # Sync call for warm-up
            embeddings = self.embed_fn(sample)
            
            if isinstance(embeddings, np.ndarray):
                self._embedding_dimension = embeddings.shape[1]
            
            elapsed = time.time() - start
            logger.info(
                f"Model warmed up in {elapsed:.2f}s, "
                f"dimension={self._embedding_dimension}"
            )
        except Exception as e:
            logger.error(f"Model warm-up failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "model_name": self.model_name,
            "embedding_dimension": self._embedding_dimension,
            "total_requests": self._total_requests,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": (
                self._cache_hits / self._total_requests
                if self._total_requests > 0 else 0.0
            ),
            "cache_size": len(self._cache),
            "total_batches": self._total_batches,
            "total_texts_embedded": self._total_texts_embedded,
            "total_errors": self._total_errors,
            "avg_batch_size": (
                self._total_texts_embedded / self._total_batches
                if self._total_batches > 0 else 0.0
            ),
        }
    
    def clear_cache(self) -> int:
        """Clear embedding cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cached embeddings")
        return count
    
    async def shutdown(self) -> None:
        """Shutdown the service."""
        self._running = False
        
        if self._batcher_task:
            self._batcher_task.cancel()
            try:
                await self._batcher_task
            except asyncio.CancelledError:
                pass
        
        self._executor.shutdown(wait=True)
        logger.info("AsyncEmbeddingsService shutdown complete")


# ==================
# Convenience Functions
# ==================

_global_service: Optional[AsyncEmbeddingsService] = None


def get_embeddings_service() -> AsyncEmbeddingsService:
    """Get or create global embeddings service."""
    global _global_service
    
    if _global_service is None:
        _global_service = AsyncEmbeddingsService()
    
    return _global_service


def set_embeddings_service(service: AsyncEmbeddingsService) -> None:
    """Set global embeddings service."""
    global _global_service
    _global_service = service


async def embed(text: str) -> Optional[np.ndarray]:
    """Convenience function to embed a single text."""
    service = get_embeddings_service()
    result = await service.embed_single(text)
    return result.embedding if result.status == EmbeddingStatus.COMPLETED else None


async def embed_many(texts: List[str]) -> List[Optional[np.ndarray]]:
    """Convenience function to embed multiple texts."""
    service = get_embeddings_service()
    results = await service.embed_batch(texts)
    return [
        r.embedding if r.status in (EmbeddingStatus.COMPLETED, EmbeddingStatus.CACHED) else None
        for r in results
    ]
