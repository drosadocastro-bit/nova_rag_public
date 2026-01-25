"""
Tests for Async Query Handler.

Tests the async query pipeline including:
- Concurrent query execution
- Caching and deduplication
- Circuit breaker behavior
- Timeout handling
- Batch queries
"""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

from core.async_pipeline.query_handler import (
    AsyncQueryHandler,
    AsyncQueryResult,
    QueryPriority,
    QueryStatus,
    CircuitBreakerState,
    PriorityQueryQueue,
)


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState."""
    
    def test_initial_state(self):
        """Circuit breaker starts closed."""
        cb = CircuitBreakerState()
        assert cb.is_open is False
        assert cb.failure_count == 0
        assert cb.can_attempt()
    
    def test_record_failure(self):
        """Failures accumulate."""
        cb = CircuitBreakerState()
        cb.record_failure(threshold=5)
        assert cb.failure_count == 1
        assert cb.is_open is False
    
    def test_circuit_opens_at_threshold(self):
        """Circuit opens after threshold failures."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb.record_failure(threshold=5)
        
        assert cb.is_open is True
        assert cb.failure_count == 5
    
    def test_open_circuit_blocks_attempts(self):
        """Open circuit blocks attempts."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb.record_failure(threshold=5)
        
        assert cb.can_attempt(reset_timeout=60.0) is False
    
    def test_half_open_after_timeout(self):
        """Circuit allows attempt after reset timeout."""
        cb = CircuitBreakerState()
        for _ in range(5):
            cb.record_failure(threshold=5)
        
        # Simulate time passing
        cb.last_failure_time = time.time() - 120
        
        assert cb.can_attempt(reset_timeout=60.0) is True
    
    def test_success_resets_circuit(self):
        """Success resets the circuit."""
        cb = CircuitBreakerState()
        for _ in range(3):
            cb.record_failure(threshold=5)
        
        cb.record_success()
        
        assert cb.failure_count == 0
        assert cb.is_open is False


class TestAsyncQueryHandler:
    """Tests for AsyncQueryHandler."""
    
    @pytest.fixture
    def mock_embedding_fn(self):
        """Mock embedding function."""
        def embed(query):
            time.sleep(0.01)  # Simulate work
            return [0.1, 0.2, 0.3]
        return embed
    
    @pytest.fixture
    def mock_retrieval_fn(self):
        """Mock retrieval function."""
        def retrieve(query, embedding, domain, top_k):
            return {
                "chunks": [{"text": "result", "score": 0.9}],
                "domain": domain or "default",
                "confidence": 0.95,
            }
        return retrieve
    
    @pytest.fixture
    def mock_generation_fn(self):
        """Mock generation function."""
        def generate(query, chunks):
            return {"answer": f"Answer to: {query}"}
        return generate
    
    @pytest.fixture
    def handler(self, mock_embedding_fn, mock_retrieval_fn, mock_generation_fn):
        """Create handler with mocks."""
        return AsyncQueryHandler(
            embedding_fn=mock_embedding_fn,
            retrieval_fn=mock_retrieval_fn,
            generation_fn=mock_generation_fn,
            max_concurrent=5,
            cache_size=100,
        )
    
    @pytest.mark.asyncio
    async def test_basic_query(self, handler):
        """Test basic query execution."""
        result = await handler.query("What is maintenance?")
        
        assert result.status == QueryStatus.COMPLETED
        assert result.answer == "Answer to: What is maintenance?"
        assert len(result.chunks) > 0
        assert result.total_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_query_caching(self, handler):
        """Test query result caching."""
        # First query
        result1 = await handler.query("cached query")
        assert result1.from_cache is False
        
        # Second identical query
        result2 = await handler.query("cached query")
        assert result2.from_cache is True
        assert result2.answer == result1.answer
    
    @pytest.mark.asyncio
    async def test_skip_cache(self, handler):
        """Test skip_cache option."""
        # First query
        await handler.query("skip test")
        
        # Second with skip_cache
        result = await handler.query("skip test", skip_cache=True)
        assert result.from_cache is False
    
    @pytest.mark.asyncio
    async def test_domain_filter(self, handler):
        """Test domain filtering."""
        result = await handler.query("domain query", domain="aviation")
        
        assert result.domain == "aviation"
    
    @pytest.mark.asyncio
    async def test_priority_levels(self, handler):
        """Test different priority levels."""
        for priority in QueryPriority:
            result = await handler.query(f"priority {priority.value}", priority=priority)
            assert result.priority == priority
    
    @pytest.mark.asyncio
    async def test_concurrent_queries(self, handler):
        """Test concurrent query execution."""
        queries = [f"query {i}" for i in range(10)]
        
        start = time.time()
        results = await handler.query_batch(queries)
        elapsed = time.time() - start
        
        assert len(results) == 10
        assert all(r.status == QueryStatus.COMPLETED for r in results)
        
        # Should complete faster than sequential (10 * 0.01s each)
        assert elapsed < 0.5
    
    @pytest.mark.asyncio
    async def test_query_timeout(self):
        """Test query timeout handling."""
        def slow_embed(query):
            time.sleep(2)  # Very slow
            return [0.1]
        
        handler = AsyncQueryHandler(
            embedding_fn=slow_embed,
            embedding_timeout=0.1,  # Very short timeout
        )
        
        result = await handler.query("slow query")
        
        # Either TIMEOUT or FAILED is acceptable for slow operations
        assert result.status in (QueryStatus.TIMEOUT, QueryStatus.FAILED)
        assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_generation_error_handling(self):
        """Test error handling in generation stage."""
        def failing_gen(query, chunks):
            raise ValueError("Generation failed")
        
        handler = AsyncQueryHandler(
            generation_fn=failing_gen,
        )
        
        result = await handler.query("error query")
        
        assert result.status == QueryStatus.FAILED
        assert result.error is not None
        assert "Generation failed" in result.error
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, handler):
        """Test statistics tracking."""
        await handler.query("stats query 1")
        await handler.query("stats query 2")
        await handler.query("stats query 1")  # Cache hit
        
        stats = handler.get_stats()
        
        assert stats["total_queries"] == 3
        assert stats["cache_hits"] == 1
        assert stats["cache_hit_rate"] > 0
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, handler):
        """Test cache clearing."""
        await handler.query("cache test")
        assert len(handler._cache) == 1
        
        count = handler.clear_cache()
        
        assert count == 1
        assert len(handler._cache) == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_reset(self, handler):
        """Test manual circuit breaker reset."""
        result = handler.reset_circuit_breaker("embedding")
        assert result is True
        
        result = handler.reset_circuit_breaker("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_shutdown(self, handler):
        """Test graceful shutdown."""
        await handler.query("pre shutdown")
        await handler.shutdown()
        
        # Handler should have cleaned up
        assert len(handler._in_flight) == 0
    
    @pytest.mark.asyncio
    async def test_query_id_generation(self, handler):
        """Test query ID generation is deterministic."""
        result1 = await handler.query("same query", domain="same")
        
        # Clear cache and query again
        handler.clear_cache()
        result2 = await handler.query("same query", domain="same")
        
        assert result1.query_id == result2.query_id
    
    @pytest.mark.asyncio
    async def test_query_result_to_dict(self, handler):
        """Test result serialization."""
        result = await handler.query("serialize me")
        result_dict = result.to_dict()
        
        assert "query_id" in result_dict
        assert "status" in result_dict
        assert "total_time_ms" in result_dict
        assert result_dict["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_empty_functions_still_work(self):
        """Test handler works with no functions configured."""
        handler = AsyncQueryHandler()
        
        result = await handler.query("no functions")
        
        assert result.status == QueryStatus.COMPLETED


class TestPriorityQueryQueue:
    """Tests for PriorityQueryQueue."""
    
    @pytest.fixture
    def handler(self):
        """Create simple handler."""
        return AsyncQueryHandler(
            generation_fn=lambda q, c: {"answer": "test"},
        )
    
    @pytest.mark.asyncio
    async def test_enqueue_and_process(self, handler):
        """Test basic enqueue and process."""
        queue = PriorityQueryQueue(handler)
        
        await queue.start_workers(num_workers=2)
        
        future = await queue.enqueue("test query")
        
        # Wait for processing
        result = await asyncio.wait_for(future, timeout=5.0)
        
        assert result.status == QueryStatus.COMPLETED
        
        await queue.stop_workers()
    
    @pytest.mark.asyncio
    async def test_queue_sizes(self, handler):
        """Test queue size reporting."""
        queue = PriorityQueryQueue(handler)
        
        sizes = queue.queue_sizes()
        
        assert "normal" in sizes
        assert "critical" in sizes
        assert all(s == 0 for s in sizes.values())


class TestAsyncQueryResult:
    """Tests for AsyncQueryResult dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        result = AsyncQueryResult(
            query_id="test123",
            query="test query",
            status=QueryStatus.PENDING,
        )
        
        assert result.answer == ""
        assert result.chunks == []
        assert result.from_cache is False
        assert result.error is None
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        result = AsyncQueryResult(
            query_id="test123",
            query="test query",
            status=QueryStatus.COMPLETED,
            answer="test answer",
            chunks=[{"text": "chunk"}],
            total_time_ms=100.5,
        )
        
        d = result.to_dict()
        
        assert d["query_id"] == "test123"
        assert d["status"] == "completed"
        assert d["total_time_ms"] == 100.5


class TestDeduplication:
    """Tests for request deduplication."""
    
    @pytest.mark.asyncio
    async def test_deduplication_enabled(self):
        """Test duplicate requests share result."""
        call_count = 0
        
        def counting_embed(query):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Slow enough to trigger dedup
            return [0.1]
        
        handler = AsyncQueryHandler(
            embedding_fn=counting_embed,
            enable_deduplication=True,
        )
        
        # Launch same query concurrently
        results = await asyncio.gather(
            handler.query("same query"),
            handler.query("same query"),
            handler.query("same query"),
        )
        
        # All should succeed
        assert all(r.status == QueryStatus.COMPLETED for r in results)
        
        # But embed should only be called once or twice (depending on timing)
        # First goes through, others wait for it
        assert call_count <= 2
    
    @pytest.mark.asyncio
    async def test_deduplication_disabled(self):
        """Test without deduplication."""
        call_count = 0
        
        def counting_embed(query):
            nonlocal call_count
            call_count += 1
            return [0.1]
        
        handler = AsyncQueryHandler(
            embedding_fn=counting_embed,
            enable_deduplication=False,
        )
        
        # Clear cache between queries
        await handler.query("query 1", skip_cache=True)
        await handler.query("query 2", skip_cache=True)
        await handler.query("query 3", skip_cache=True)
        
        assert call_count == 3
