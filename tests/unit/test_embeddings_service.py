"""
Tests for Async Embeddings Service.

Tests the embedding service including:
- Batch embedding
- Caching behavior
- Retry logic
- Statistics tracking
"""

import asyncio
import time
from unittest.mock import Mock, patch

import numpy as np
import pytest

from core.async_pipeline.embeddings_service import (
    AsyncEmbeddingsService,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingStatus,
    get_embeddings_service,
    set_embeddings_service,
    embed,
    embed_many,
)


class TestEmbeddingRequest:
    """Tests for EmbeddingRequest."""
    
    def test_auto_generates_id(self):
        """Request auto-generates ID from text."""
        request = EmbeddingRequest(text="test text")
        
        assert len(request.request_id) == 12
    
    def test_explicit_id(self):
        """Explicit ID is preserved."""
        request = EmbeddingRequest(text="test", request_id="custom-id")
        
        assert request.request_id == "custom-id"
    
    def test_deterministic_id(self):
        """Same text produces same ID."""
        req1 = EmbeddingRequest(text="identical text")
        req2 = EmbeddingRequest(text="identical text")
        
        assert req1.request_id == req2.request_id


class TestEmbeddingResult:
    """Tests for EmbeddingResult."""
    
    def test_to_dict(self):
        """Test serialization."""
        result = EmbeddingResult(
            request_id="test-123",
            text="sample text",
            embedding=np.array([0.1, 0.2]),
            status=EmbeddingStatus.COMPLETED,
            latency_ms=10.5,
            model_name="test-model",
            dimension=2,
        )
        
        d = result.to_dict()
        
        assert d["request_id"] == "test-123"
        assert d["status"] == "completed"
        assert d["dimension"] == 2
        assert d["latency_ms"] == 10.5
    
    def test_to_dict_truncates_text(self):
        """Long text is truncated in dict."""
        long_text = "x" * 100
        result = EmbeddingResult(
            request_id="test",
            text=long_text,
            embedding=None,
            status=EmbeddingStatus.FAILED,
        )
        
        d = result.to_dict()
        
        assert len(d["text_preview"]) == 53  # 50 + "..."


class TestAsyncEmbeddingsService:
    """Tests for AsyncEmbeddingsService."""
    
    @pytest.fixture
    def mock_embed_fn(self):
        """Mock embedding function."""
        def embed_texts(texts):
            return np.random.rand(len(texts), 384)
        return embed_texts
    
    @pytest.fixture
    def service(self, mock_embed_fn):
        """Create service with mock."""
        return AsyncEmbeddingsService(
            embed_fn=mock_embed_fn,
            model_name="test-model",
            cache_size=100,
        )
    
    @pytest.mark.asyncio
    async def test_embed_single(self, service):
        """Test single text embedding."""
        result = await service.embed_single("test text")
        
        assert result.status == EmbeddingStatus.COMPLETED
        assert result.embedding is not None
        assert len(result.embedding) == 384
        assert result.model_name == "test-model"
    
    @pytest.mark.asyncio
    async def test_embed_batch(self, service):
        """Test batch embedding."""
        texts = ["text 1", "text 2", "text 3"]
        results = await service.embed_batch(texts)
        
        assert len(results) == 3
        assert all(r.status == EmbeddingStatus.COMPLETED for r in results)
        assert all(r.embedding is not None for r in results)
    
    @pytest.mark.asyncio
    async def test_empty_batch(self, service):
        """Test empty batch returns empty list."""
        results = await service.embed_batch([])
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_caching(self, service):
        """Test embedding caching."""
        # First embed
        result1 = await service.embed_single("cached text")
        assert result1.from_cache is False
        
        # Second should be from cache
        result2 = await service.embed_single("cached text")
        assert result2.from_cache is True
        
        # Embeddings should match
        np.testing.assert_array_equal(result1.embedding, result2.embedding)
    
    @pytest.mark.asyncio
    async def test_skip_cache(self, service):
        """Test skip_cache option."""
        await service.embed_single("skip test")
        
        result = await service.embed_single("skip test", skip_cache=True)
        
        assert result.from_cache is False
    
    @pytest.mark.asyncio
    async def test_batch_caching(self, service):
        """Test batch partially uses cache."""
        # Pre-cache one text
        await service.embed_single("cached")
        
        # Batch with cached and new
        results = await service.embed_batch(["cached", "new text"])
        
        assert results[0].from_cache is True
        assert results[1].from_cache is False
    
    @pytest.mark.asyncio
    async def test_cache_eviction(self):
        """Test LRU cache eviction."""
        def simple_embed(texts):
            return np.ones((len(texts), 10))
        
        service = AsyncEmbeddingsService(
            embed_fn=simple_embed,
            cache_size=3,
        )
        
        # Fill cache
        await service.embed_batch(["text1", "text2", "text3"])
        
        assert len(service._cache) == 3
        
        # Add one more
        await service.embed_single("text4")
        
        # Should still be 3 (LRU eviction)
        assert len(service._cache) == 3
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry logic on failure."""
        call_count = 0
        
        def failing_embed(texts):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return np.ones((len(texts), 10))
        
        service = AsyncEmbeddingsService(
            embed_fn=failing_embed,
            max_retries=3,
            retry_base_delay=0.01,
        )
        
        result = await service.embed_single("retry test")
        
        assert result.status == EmbeddingStatus.COMPLETED
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_failure_after_retries(self):
        """Test failure after all retries exhausted."""
        def always_fails(texts):
            raise ValueError("Always fails")
        
        service = AsyncEmbeddingsService(
            embed_fn=always_fails,
            max_retries=2,
            retry_base_delay=0.01,
        )
        
        result = await service.embed_single("fail test")
        
        assert result.status == EmbeddingStatus.FAILED
        assert result.embedding is None
    
    @pytest.mark.asyncio
    async def test_no_embed_fn(self):
        """Test service without embed function."""
        service = AsyncEmbeddingsService()
        
        result = await service.embed_single("no function")
        
        assert result.status == EmbeddingStatus.FAILED
        assert result.error is not None
        assert "No embedding function" in result.error
    
    @pytest.mark.asyncio
    async def test_streaming(self, service):
        """Test streaming embeddings."""
        texts = [f"text {i}" for i in range(10)]
        
        results = []
        async for result in service.embed_streaming(texts, batch_size=3):
            results.append(result)
        
        assert len(results) == 10
        assert all(r.status == EmbeddingStatus.COMPLETED for r in results)
    
    def test_warm_up(self, service):
        """Test model warm-up."""
        # Should not raise
        service.warm_up()
        
        assert service._embedding_dimension == 384
    
    def test_warm_up_no_fn(self):
        """Warm-up with no function is no-op."""
        service = AsyncEmbeddingsService()
        service.warm_up()  # Should not raise
    
    @pytest.mark.asyncio
    async def test_stats(self, service):
        """Test statistics tracking."""
        await service.embed_single("stats test 1")
        await service.embed_single("stats test 2")
        await service.embed_single("stats test 1")  # Cache hit
        
        stats = service.get_stats()
        
        assert stats["total_requests"] == 3
        assert stats["cache_hits"] == 1
        assert stats["cache_hit_rate"] > 0
        assert stats["total_batches"] == 2
        assert stats["model_name"] == "test-model"
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, service):
        """Test cache clearing."""
        await service.embed_single("clear test")
        assert len(service._cache) == 1
        
        count = service.clear_cache()
        
        assert count == 1
        assert len(service._cache) == 0
    
    @pytest.mark.asyncio
    async def test_shutdown(self, service):
        """Test graceful shutdown."""
        await service.embed_single("pre shutdown")
        await service.shutdown()
        
        # Executor should be shut down
        assert service._executor._shutdown


class TestGlobalFunctions:
    """Tests for global convenience functions."""
    
    @pytest.fixture(autouse=True)
    def reset_global(self):
        """Reset global service before each test."""
        import core.async_pipeline.embeddings_service as module
        module._global_service = None
        yield
        module._global_service = None
    
    def test_get_embeddings_service(self):
        """Test getting global service."""
        service1 = get_embeddings_service()
        service2 = get_embeddings_service()
        
        assert service1 is service2
    
    def test_set_embeddings_service(self):
        """Test setting global service."""
        def custom_fn(texts):
            return np.ones((len(texts), 10))
        
        custom = AsyncEmbeddingsService(embed_fn=custom_fn)
        set_embeddings_service(custom)
        
        service = get_embeddings_service()
        assert service is custom
    
    @pytest.mark.asyncio
    async def test_embed_convenience(self):
        """Test embed() convenience function."""
        def simple_fn(texts):
            return np.array([[0.1, 0.2]])
        
        service = AsyncEmbeddingsService(embed_fn=simple_fn)
        set_embeddings_service(service)
        
        embedding = await embed("test")
        
        assert embedding is not None
        np.testing.assert_array_almost_equal(embedding, [0.1, 0.2])
    
    @pytest.mark.asyncio
    async def test_embed_many_convenience(self):
        """Test embed_many() convenience function."""
        def simple_fn(texts):
            return np.ones((len(texts), 5))
        
        service = AsyncEmbeddingsService(embed_fn=simple_fn)
        set_embeddings_service(service)
        
        embeddings = await embed_many(["text1", "text2"])
        
        assert len(embeddings) == 2
        assert all(e is not None for e in embeddings)


class TestConcurrency:
    """Tests for concurrent embedding operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_batches(self):
        """Test multiple concurrent batch operations."""
        call_count = 0
        
        def counting_embed(texts):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)
            return np.ones((len(texts), 10))
        
        service = AsyncEmbeddingsService(
            embed_fn=counting_embed,
            max_concurrent_batches=4,
        )
        
        # Launch 4 concurrent batches
        start = time.time()
        results = await asyncio.gather(
            service.embed_batch([f"batch1_{i}" for i in range(5)]),
            service.embed_batch([f"batch2_{i}" for i in range(5)]),
            service.embed_batch([f"batch3_{i}" for i in range(5)]),
            service.embed_batch([f"batch4_{i}" for i in range(5)]),
        )
        elapsed = time.time() - start
        
        # All should complete
        assert all(len(r) == 5 for r in results)
        
        # Should be faster than sequential (4 * 0.1s)
        assert elapsed < 0.3
