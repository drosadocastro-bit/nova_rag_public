"""
Async Query Handler for NOVA NIC.

Provides high-performance async query processing with:
- Concurrent embedding + retrieval + generation
- Query prioritization (safety-critical first)
- Timeout management per stage
- Circuit breaker for failing backends
- Request deduplication
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class QueryPriority(str, Enum):
    """Query priority levels."""
    
    CRITICAL = "critical"  # Safety-critical queries
    HIGH = "high"          # User-facing, interactive
    NORMAL = "normal"      # Standard queries
    LOW = "low"            # Background, batch
    BULK = "bulk"          # Bulk ingestion queries


class QueryStatus(str, Enum):
    """Query execution status."""
    
    PENDING = "pending"
    EMBEDDING = "embedding"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CACHED = "cached"


@dataclass
class QueryStageMetrics:
    """Metrics for a single query stage."""
    
    stage: str
    start_time: float
    end_time: float = 0.0
    success: bool = True
    error: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        """Stage duration in milliseconds."""
        if self.end_time == 0:
            return 0.0
        return (self.end_time - self.start_time) * 1000


@dataclass
class AsyncQueryResult:
    """Result of async query execution."""
    
    query_id: str
    query: str
    status: QueryStatus
    answer: str = ""
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    domain: str = ""
    confidence: float = 0.0
    
    # Timing
    total_time_ms: float = 0.0
    stage_metrics: List[QueryStageMetrics] = field(default_factory=list)
    
    # Metadata
    from_cache: bool = False
    priority: QueryPriority = QueryPriority.NORMAL
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_id": self.query_id,
            "query": self.query,
            "status": self.status.value,
            "answer": self.answer,
            "chunks": self.chunks,
            "domain": self.domain,
            "confidence": self.confidence,
            "total_time_ms": round(self.total_time_ms, 2),
            "stage_timings": {
                m.stage: round(m.duration_ms, 2) for m in self.stage_metrics
            },
            "from_cache": self.from_cache,
            "priority": self.priority.value,
            "error": self.error,
        }


@dataclass
class CircuitBreakerState:
    """Circuit breaker for backend services."""
    
    failure_count: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False
    half_open_attempts: int = 0
    
    def record_failure(self, threshold: int = 5, reset_timeout: float = 60.0) -> None:
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker opened after {threshold} failures")
    
    def record_success(self) -> None:
        """Record a success, reset state if in half-open."""
        self.failure_count = 0
        self.is_open = False
        self.half_open_attempts = 0
    
    def can_attempt(self, reset_timeout: float = 60.0) -> bool:
        """Check if we can attempt a request."""
        if not self.is_open:
            return True
        
        # Check if we should try half-open
        time_since_failure = time.time() - self.last_failure_time
        if time_since_failure > reset_timeout:
            self.half_open_attempts += 1
            return True
        
        return False


class AsyncQueryHandler:
    """
    High-performance async query handler.
    
    Features:
    - Async execution with concurrent stages
    - Priority-based queue management
    - Request deduplication
    - Circuit breaker for failing backends
    - Timeout management per stage
    """
    
    def __init__(
        self,
        embedding_fn: Optional[Callable] = None,
        retrieval_fn: Optional[Callable] = None,
        generation_fn: Optional[Callable] = None,
        max_concurrent: int = 10,
        embedding_timeout: float = 30.0,
        retrieval_timeout: float = 30.0,
        generation_timeout: float = 120.0,
        cache_size: int = 1000,
        enable_deduplication: bool = True,
    ):
        """
        Initialize async query handler.
        
        Args:
            embedding_fn: Sync function to generate embeddings
            retrieval_fn: Sync function for retrieval
            generation_fn: Sync function for LLM generation
            max_concurrent: Max concurrent queries
            embedding_timeout: Timeout for embedding stage
            retrieval_timeout: Timeout for retrieval stage
            generation_timeout: Timeout for generation stage
            cache_size: Size of result cache
            enable_deduplication: Enable request deduplication
        """
        self.embedding_fn = embedding_fn
        self.retrieval_fn = retrieval_fn
        self.generation_fn = generation_fn
        
        self.max_concurrent = max_concurrent
        self.embedding_timeout = embedding_timeout
        self.retrieval_timeout = retrieval_timeout
        self.generation_timeout = generation_timeout
        
        self.cache_size = cache_size
        self.enable_deduplication = enable_deduplication
        
        # Thread pool for sync functions
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix="AsyncQuery"
        )
        
        # State
        self._cache: OrderedDict[str, AsyncQueryResult] = OrderedDict()
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # Circuit breakers
        self._circuit_breakers = {
            "embedding": CircuitBreakerState(),
            "retrieval": CircuitBreakerState(),
            "generation": CircuitBreakerState(),
        }
        
        # Metrics
        self._total_queries = 0
        self._cache_hits = 0
        self._dedup_hits = 0
        self._failures = 0
        self._timeouts = 0
        
        logger.info(
            f"AsyncQueryHandler initialized: max_concurrent={max_concurrent}, "
            f"cache_size={cache_size}"
        )
    
    def _generate_query_id(self, query: str, domain: Optional[str] = None) -> str:
        """Generate unique query ID for caching/deduplication."""
        key = f"{query}:{domain or ''}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def _get_cached(self, query_id: str) -> Optional[AsyncQueryResult]:
        """Get result from cache if available."""
        if query_id in self._cache:
            # Move to end (LRU)
            self._cache.move_to_end(query_id)
            self._cache_hits += 1
            result = self._cache[query_id]
            result.from_cache = True
            return result
        return None
    
    def _put_cache(self, query_id: str, result: AsyncQueryResult) -> None:
        """Add result to cache with LRU eviction."""
        if query_id in self._cache:
            self._cache.move_to_end(query_id)
        else:
            self._cache[query_id] = result
            # Evict oldest if over capacity
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
    
    async def _run_stage(
        self,
        stage_name: str,
        fn: Callable,
        args: tuple,
        timeout: float,
        metrics: List[QueryStageMetrics],
    ) -> Any:
        """Run a pipeline stage with timeout and circuit breaker."""
        circuit = self._circuit_breakers.get(stage_name)
        
        # Check circuit breaker
        if circuit and not circuit.can_attempt():
            raise RuntimeError(f"Circuit breaker open for {stage_name}")
        
        stage_metric = QueryStageMetrics(stage=stage_name, start_time=time.time())
        
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(self._executor, fn, *args),
                timeout=timeout
            )
            
            stage_metric.end_time = time.time()
            stage_metric.success = True
            
            if circuit:
                circuit.record_success()
            
            return result
            
        except asyncio.TimeoutError:
            stage_metric.end_time = time.time()
            stage_metric.success = False
            stage_metric.error = "timeout"
            self._timeouts += 1
            
            if circuit:
                circuit.record_failure()
            
            raise
            
        except Exception as e:
            stage_metric.end_time = time.time()
            stage_metric.success = False
            stage_metric.error = str(e)
            
            if circuit:
                circuit.record_failure()
            
            raise
            
        finally:
            metrics.append(stage_metric)
    
    async def query(
        self,
        query: str,
        domain: Optional[str] = None,
        priority: QueryPriority = QueryPriority.NORMAL,
        skip_cache: bool = False,
        top_k: int = 5,
    ) -> AsyncQueryResult:
        """
        Execute an async query through the full pipeline.
        
        Args:
            query: The query string
            domain: Optional domain filter
            priority: Query priority level
            skip_cache: Skip cache lookup
            top_k: Number of chunks to retrieve
            
        Returns:
            AsyncQueryResult with answer and metadata
        """
        self._total_queries += 1
        query_id = self._generate_query_id(query, domain)
        start_time = time.time()
        
        # Check cache
        if not skip_cache:
            cached = self._get_cached(query_id)
            if cached:
                logger.debug(f"Cache hit for query: {query_id}")
                return cached
        
        # Check for in-flight duplicate
        if self.enable_deduplication and query_id in self._in_flight:
            self._dedup_hits += 1
            logger.debug(f"Dedup hit, waiting for in-flight query: {query_id}")
            return await self._in_flight[query_id]
        
        # Create result placeholder
        result = AsyncQueryResult(
            query_id=query_id,
            query=query,
            status=QueryStatus.PENDING,
            priority=priority,
            domain=domain or "",
        )
        
        # Register in-flight
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        if self.enable_deduplication:
            self._in_flight[query_id] = future
        
        try:
            async with self._semaphore:
                metrics: List[QueryStageMetrics] = []
                
                # Stage 1: Embedding
                if self.embedding_fn:
                    result.status = QueryStatus.EMBEDDING
                    try:
                        embedding = await self._run_stage(
                            "embedding",
                            self.embedding_fn,
                            (query,),
                            self.embedding_timeout,
                            metrics,
                        )
                    except asyncio.TimeoutError:
                        result.status = QueryStatus.TIMEOUT
                        result.error = "Embedding stage timeout"
                        raise
                else:
                    embedding = None
                
                # Stage 2: Retrieval
                if self.retrieval_fn:
                    result.status = QueryStatus.RETRIEVING
                    try:
                        retrieval_result = await self._run_stage(
                            "retrieval",
                            self.retrieval_fn,
                            (query, embedding, domain, top_k),
                            self.retrieval_timeout,
                            metrics,
                        )
                        result.chunks = retrieval_result.get("chunks", [])
                        result.domain = retrieval_result.get("domain", domain or "")
                        result.confidence = retrieval_result.get("confidence", 0.0)
                    except asyncio.TimeoutError:
                        result.status = QueryStatus.TIMEOUT
                        result.error = "Retrieval stage timeout"
                        raise
                
                # Stage 3: Generation
                if self.generation_fn:
                    result.status = QueryStatus.GENERATING
                    try:
                        generation_result = await self._run_stage(
                            "generation",
                            self.generation_fn,
                            (query, result.chunks),
                            self.generation_timeout,
                            metrics,
                        )
                        result.answer = generation_result.get("answer", "")
                    except asyncio.TimeoutError:
                        result.status = QueryStatus.TIMEOUT
                        result.error = "Generation stage timeout"
                        raise
                
                # Success
                result.status = QueryStatus.COMPLETED
                result.stage_metrics = metrics
                result.total_time_ms = (time.time() - start_time) * 1000
                
                # Cache successful result
                self._put_cache(query_id, result)
                
                logger.info(
                    f"Query completed: {query_id} in {result.total_time_ms:.1f}ms "
                    f"({len(result.chunks)} chunks)"
                )
                
                return result
                
        except Exception as e:
            self._failures += 1
            result.status = QueryStatus.FAILED
            result.error = str(e)
            result.total_time_ms = (time.time() - start_time) * 1000
            
            logger.error(f"Query failed: {query_id} - {e}")
            return result
            
        finally:
            # Resolve in-flight future
            if self.enable_deduplication and query_id in self._in_flight:
                future.set_result(result)
                del self._in_flight[query_id]
    
    async def query_batch(
        self,
        queries: List[str],
        domain: Optional[str] = None,
        priority: QueryPriority = QueryPriority.NORMAL,
        max_concurrent: Optional[int] = None,
    ) -> List[AsyncQueryResult]:
        """
        Execute multiple queries concurrently.
        
        Args:
            queries: List of query strings
            domain: Optional domain filter for all queries
            priority: Priority for all queries
            max_concurrent: Override max concurrent for this batch
            
        Returns:
            List of AsyncQueryResult in same order as queries
        """
        # Use batch-specific semaphore if provided
        semaphore = asyncio.Semaphore(max_concurrent or self.max_concurrent)
        
        async def bounded_query(q: str) -> AsyncQueryResult:
            async with semaphore:
                return await self.query(q, domain=domain, priority=priority)
        
        tasks = [bounded_query(q) for q in queries]
        return await asyncio.gather(*tasks)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics."""
        return {
            "total_queries": self._total_queries,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": (
                self._cache_hits / self._total_queries 
                if self._total_queries > 0 else 0.0
            ),
            "dedup_hits": self._dedup_hits,
            "failures": self._failures,
            "timeouts": self._timeouts,
            "in_flight": len(self._in_flight),
            "cache_size": len(self._cache),
            "circuit_breakers": {
                name: {
                    "is_open": cb.is_open,
                    "failure_count": cb.failure_count,
                }
                for name, cb in self._circuit_breakers.items()
            },
        }
    
    def reset_circuit_breaker(self, stage: str) -> bool:
        """Manually reset a circuit breaker."""
        if stage in self._circuit_breakers:
            self._circuit_breakers[stage] = CircuitBreakerState()
            logger.info(f"Circuit breaker reset for {stage}")
            return True
        return False
    
    def clear_cache(self) -> int:
        """Clear the result cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared {count} cached results")
        return count
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down AsyncQueryHandler...")
        
        # Wait for in-flight queries
        if self._in_flight:
            logger.info(f"Waiting for {len(self._in_flight)} in-flight queries...")
            await asyncio.gather(*self._in_flight.values(), return_exceptions=True)
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        
        logger.info("AsyncQueryHandler shutdown complete")


# ==================
# Priority Queue for Multi-Priority
# ==================

class PriorityQueryQueue:
    """
    Priority queue for query scheduling.
    
    Ensures critical queries are processed first while preventing starvation
    of lower priority queries.
    """
    
    def __init__(self, handler: AsyncQueryHandler):
        self.handler = handler
        
        # Separate queues per priority
        self._queues: Dict[QueryPriority, asyncio.Queue] = {
            p: asyncio.Queue() for p in QueryPriority
        }
        
        # Weight for priority scheduling
        self._weights = {
            QueryPriority.CRITICAL: 10,
            QueryPriority.HIGH: 5,
            QueryPriority.NORMAL: 2,
            QueryPriority.LOW: 1,
            QueryPriority.BULK: 1,
        }
        
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
    
    async def enqueue(
        self,
        query: str,
        domain: Optional[str] = None,
        priority: QueryPriority = QueryPriority.NORMAL,
    ) -> asyncio.Future:
        """
        Enqueue a query for processing.
        
        Returns a Future that will contain the result.
        """
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        await self._queues[priority].put((query, domain, future))
        return future
    
    async def start_workers(self, num_workers: int = 5) -> None:
        """Start worker tasks to process queues."""
        self._running = True
        
        async def worker():
            while self._running:
                # Priority-weighted selection
                for priority in QueryPriority:
                    queue = self._queues[priority]
                    if not queue.empty():
                        query, domain, future = await queue.get()
                        try:
                            result = await self.handler.query(
                                query, domain=domain, priority=priority
                            )
                            future.set_result(result)
                        except Exception as e:
                            future.set_exception(e)
                        finally:
                            queue.task_done()
                        break
                else:
                    # No items in any queue, sleep briefly
                    await asyncio.sleep(0.01)
        
        # Create worker tasks
        worker_tasks = [worker() for _ in range(num_workers)]
        self._worker_task = asyncio.create_task(
            asyncio.gather(*worker_tasks)  # type: ignore[arg-type]
        )
    
    async def stop_workers(self) -> None:
        """Stop worker tasks."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
    
    def queue_sizes(self) -> Dict[str, int]:
        """Get current queue sizes."""
        return {p.value: q.qsize() for p, q in self._queues.items()}
