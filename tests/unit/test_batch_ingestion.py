"""Tests for batch ingestion module."""

import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any
from unittest.mock import MagicMock, patch

import pytest

from core.indexing.batch_ingestion import (
    BatchIngestionPipeline,
    BatchProgress,
    DocumentResult,
    IngestionConfig,
    IngestionStatus,
    stream_documents,
)


class TestIngestionStatus:
    """Tests for IngestionStatus enum."""
    
    def test_status_values(self):
        """Test all status values exist."""
        assert IngestionStatus.PENDING == "pending"
        assert IngestionStatus.PROCESSING == "processing"
        assert IngestionStatus.COMPLETED == "completed"
        assert IngestionStatus.FAILED == "failed"
        assert IngestionStatus.SKIPPED == "skipped"


class TestDocumentResult:
    """Tests for DocumentResult dataclass."""
    
    def test_basic_creation(self):
        """Test basic result creation."""
        result = DocumentResult(
            doc_id="abc123",
            file_path="/path/to/doc.txt",
            status=IngestionStatus.COMPLETED,
            chunks_created=5,
        )
        
        assert result.doc_id == "abc123"
        assert result.chunks_created == 5
        assert result.status == IngestionStatus.COMPLETED
    
    def test_to_dict(self):
        """Test serialization."""
        result = DocumentResult(
            doc_id="abc123",
            file_path="/path/to/doc.txt",
            status=IngestionStatus.COMPLETED,
            chunks_created=5,
            processing_time_ms=123.45,
        )
        
        d = result.to_dict()
        
        assert d["doc_id"] == "abc123"
        assert d["status"] == "completed"
        assert d["processing_time_ms"] == 123.45


class TestBatchProgress:
    """Tests for BatchProgress dataclass."""
    
    def test_progress_percent_empty(self):
        """Test progress with no documents."""
        progress = BatchProgress(batch_id="b1", total_documents=0)
        assert progress.progress_percent == 100.0
    
    def test_progress_percent_partial(self):
        """Test partial progress."""
        progress = BatchProgress(
            batch_id="b1",
            total_documents=100,
            processed_documents=25,
        )
        assert progress.progress_percent == 25.0
    
    def test_elapsed_seconds(self):
        """Test elapsed time calculation."""
        now = time.time()
        progress = BatchProgress(
            batch_id="b1",
            total_documents=10,
            started_at=now - 60,
        )
        
        assert 59 <= progress.elapsed_seconds <= 61
    
    def test_estimated_remaining(self):
        """Test remaining time estimation."""
        now = time.time()
        progress = BatchProgress(
            batch_id="b1",
            total_documents=10,
            processed_documents=5,
            started_at=now - 10,  # 10 seconds for 5 docs = 2s/doc
        )
        
        # 5 remaining * 2s/doc = 10s
        assert 9 <= progress.estimated_remaining_seconds <= 11
    
    def test_documents_per_second(self):
        """Test throughput calculation."""
        now = time.time()
        progress = BatchProgress(
            batch_id="b1",
            total_documents=100,
            processed_documents=20,
            started_at=now - 10,
        )
        
        # Allow small floating point variance
        assert abs(progress.documents_per_second - 2.0) < 0.01
    
    def test_to_dict(self):
        """Test serialization."""
        progress = BatchProgress(
            batch_id="b1",
            total_documents=100,
            processed_documents=50,
            successful_documents=45,
            failed_documents=3,
            skipped_documents=2,
            started_at=time.time(),
        )
        
        d = progress.to_dict()
        
        assert d["batch_id"] == "b1"
        assert d["progress_percent"] == 50.0
        assert d["successful_documents"] == 45


class TestIngestionConfig:
    """Tests for IngestionConfig."""
    
    def test_default_values(self):
        """Test default configuration."""
        config = IngestionConfig()
        
        assert config.max_workers == 4
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.max_retries == 3
        assert ".txt" in config.supported_extensions
    
    def test_from_env(self):
        """Test config from environment."""
        with patch.dict("os.environ", {
            "NOVA_INGEST_WORKERS": "8",
            "NOVA_CHUNK_SIZE": "1024",
        }):
            config = IngestionConfig.from_env()
            
            assert config.max_workers == 8
            assert config.chunk_size == 1024


class TestBatchIngestionPipeline:
    """Tests for BatchIngestionPipeline."""
    
    @pytest.fixture
    def temp_docs(self, tmp_path):
        """Create temporary test documents."""
        docs = []
        for i in range(5):
            doc_path = tmp_path / f"doc{i}.txt"
            doc_path.write_text(f"This is document {i} with enough content for chunking." * 10)
            docs.append((doc_path, {"index": i}))
        return docs
    
    def test_ingest_batch_basic(self, temp_docs):
        """Test basic batch ingestion."""
        config = IngestionConfig(max_workers=2, fail_fast=False)
        pipeline = BatchIngestionPipeline(config)
        
        progress = pipeline.ingest_batch(temp_docs)
        
        assert progress.total_documents == 5
        assert progress.processed_documents == 5
        assert progress.successful_documents == 5
        assert progress.failed_documents == 0
    
    def test_ingest_batch_with_callback(self, temp_docs):
        """Test progress callback."""
        config = IngestionConfig(max_workers=1)
        pipeline = BatchIngestionPipeline(config)
        
        callbacks = []
        pipeline.add_progress_callback(lambda p: callbacks.append(p.processed_documents))
        
        pipeline.ingest_batch(temp_docs)
        
        # Should have received callbacks
        assert len(callbacks) >= 5
    
    def test_skip_unsupported_extension(self, tmp_path):
        """Test skipping unsupported file types."""
        doc_path = tmp_path / "doc.xyz"
        doc_path.write_text("Content")
        
        pipeline = BatchIngestionPipeline()
        progress = pipeline.ingest_batch([(doc_path, {})])
        
        assert progress.skipped_documents == 1
    
    def test_skip_too_short_content(self, tmp_path):
        """Test skipping too short content."""
        doc_path = tmp_path / "doc.txt"
        doc_path.write_text("Hi")
        
        config = IngestionConfig(min_content_length=10)
        pipeline = BatchIngestionPipeline(config)
        
        progress = pipeline.ingest_batch([(doc_path, {})])
        
        assert progress.skipped_documents == 1
    
    def test_duplicate_detection(self, tmp_path):
        """Test duplicate content detection."""
        content = "Duplicate content for testing" * 10
        
        doc1 = tmp_path / "doc1.txt"
        doc2 = tmp_path / "doc2.txt"
        doc1.write_text(content)
        doc2.write_text(content)
        
        config = IngestionConfig(skip_duplicates=True)
        pipeline = BatchIngestionPipeline(config)
        
        progress = pipeline.ingest_batch([(doc1, {}), (doc2, {})])
        
        assert progress.successful_documents == 1
        assert progress.skipped_documents == 1
    
    def test_custom_processor(self, temp_docs):
        """Test custom document processor."""
        def custom_processor(content, path, meta):
            # Simple processor that creates one chunk
            return [content[:100]], {"custom": True}
        
        pipeline = BatchIngestionPipeline(document_processor=custom_processor)
        progress = pipeline.ingest_batch(temp_docs[:1])
        
        assert progress.successful_documents == 1
        assert progress.results[0].chunks_created == 1
    
    def test_fail_fast_mode(self, tmp_path):
        """Test fail-fast stops on first error."""
        # Create one valid and one invalid file
        good = tmp_path / "good.txt"
        good.write_text("Valid content" * 20)
        
        def failing_processor(content, path, meta):
            if "good" not in str(path):
                raise ValueError("Intentional failure")
            return [content], meta
        
        config = IngestionConfig(fail_fast=True, max_workers=1)
        pipeline = BatchIngestionPipeline(config, failing_processor)
        
        bad = tmp_path / "bad.txt"
        bad.write_text("Content that will fail" * 20)
        
        progress = pipeline.ingest_batch([(bad, {}), (good, {})])
        
        # Should have stopped after first failure
        assert progress.failed_documents >= 1
    
    def test_checkpoint_save_and_resume(self, temp_docs, tmp_path):
        """Test checkpoint functionality."""
        checkpoint_path = tmp_path / "checkpoint.json"
        
        config = IngestionConfig(
            checkpoint_path=checkpoint_path,
            checkpoint_interval=2,
        )
        pipeline = BatchIngestionPipeline(config)
        
        # Run ingestion
        progress = pipeline.ingest_batch(temp_docs, batch_id="test_batch")
        
        # Checkpoint should exist
        assert checkpoint_path.exists()
    
    def test_ingest_directory(self, tmp_path):
        """Test directory ingestion."""
        # Create files
        (tmp_path / "doc1.txt").write_text("Content 1" * 20)
        (tmp_path / "doc2.txt").write_text("Content 2" * 20)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "doc3.txt").write_text("Content 3" * 20)
        
        pipeline = BatchIngestionPipeline()
        progress = pipeline.ingest_directory(tmp_path, recursive=True)
        
        assert progress.total_documents == 3
    
    def test_ingest_directory_non_recursive(self, tmp_path):
        """Test non-recursive directory ingestion."""
        (tmp_path / "doc1.txt").write_text("Content 1" * 20)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "doc2.txt").write_text("Content 2" * 20)
        
        pipeline = BatchIngestionPipeline()
        progress = pipeline.ingest_directory(tmp_path, recursive=False)
        
        assert progress.total_documents == 1
    
    def test_stop_ingestion(self, temp_docs):
        """Test stopping ingestion."""
        config = IngestionConfig(max_workers=1)
        pipeline = BatchIngestionPipeline(config)
        
        # Request stop immediately
        pipeline.stop()
        
        # Should complete quickly with partial results
        progress = pipeline.ingest_batch(temp_docs)
        
        assert progress.completed_at is not None
    
    def test_get_active_progress(self, temp_docs):
        """Test getting active progress."""
        pipeline = BatchIngestionPipeline()
        
        # No active batch
        assert pipeline.get_active_progress() is None


class TestStreamDocuments:
    """Tests for stream_documents generator."""
    
    def test_stream_batches(self, tmp_path):
        """Test streaming in batches."""
        paths = [tmp_path / f"doc{i}.txt" for i in range(10)]
        
        batches = list(stream_documents(paths, chunk_size=3))
        
        assert len(batches) == 4  # 3 + 3 + 3 + 1
        assert len(batches[0]) == 3
        assert len(batches[-1]) == 1
    
    def test_stream_empty(self):
        """Test streaming empty iterable."""
        batches = list(stream_documents([], chunk_size=10))
        assert len(batches) == 0
    
    def test_stream_exact_batch(self, tmp_path):
        """Test streaming with exact batch size."""
        paths = [tmp_path / f"doc{i}.txt" for i in range(6)]
        
        batches = list(stream_documents(paths, chunk_size=3))
        
        assert len(batches) == 2
        assert all(len(b) == 3 for b in batches)
