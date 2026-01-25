"""
Tests for Tantivy BM25 Backend.

Tests the scalable full-text search including:
- Document indexing
- Search functionality
- Domain filtering
- Fallback behavior
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.indexing.tantivy_bm25 import (
    TantivyDocument,
    TantivySearchResult,
    TantivyBM25Fallback,
    create_bm25_index,
    TANTIVY_AVAILABLE,
)


class TestTantivyDocument:
    """Tests for TantivyDocument."""
    
    def test_basic_document(self):
        """Test basic document creation."""
        doc = TantivyDocument(
            doc_id="doc-001",
            content="This is test content",
            title="Test Document",
            domain="aviation",
        )
        
        assert doc.doc_id == "doc-001"
        assert doc.content == "This is test content"
        assert doc.domain == "aviation"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        doc = TantivyDocument(
            doc_id="doc-001",
            content="content",
            title="title",
            domain="domain",
            source="source.pdf",
            chunk_index=5,
            metadata={"key": "value"},
        )
        
        d = doc.to_dict()
        
        assert d["doc_id"] == "doc-001"
        assert d["content"] == "content"
        assert d["chunk_index"] == 5
        assert "metadata_json" in d
        assert json.loads(d["metadata_json"]) == {"key": "value"}


class TestTantivySearchResult:
    """Tests for TantivySearchResult."""
    
    def test_basic_result(self):
        """Test basic result creation."""
        result = TantivySearchResult(
            doc_id="doc-001",
            score=0.95,
            content="matched content",
        )
        
        assert result.doc_id == "doc-001"
        assert result.score == 0.95
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        result = TantivySearchResult(
            doc_id="doc-001",
            score=0.95432,
            content="content",
            title="title",
            domain="aviation",
            highlights=["matched <em>term</em>"],
        )
        
        d = result.to_dict()
        
        assert d["score"] == 0.9543  # Rounded
        assert d["highlights"] == ["matched <em>term</em>"]


class TestTantivyBM25Fallback:
    """Tests for fallback in-memory BM25."""
    
    @pytest.fixture
    def index(self, tmp_path):
        """Create fallback index."""
        return TantivyBM25Fallback(str(tmp_path / "fallback_index"))
    
    def test_index_document(self, index):
        """Test indexing a document."""
        doc = TantivyDocument(
            doc_id="doc-001",
            content="Safety procedures for aircraft",
            title="Safety Manual",
            domain="aviation",
        )
        
        result = index.index_document(doc)
        
        assert result is True
        assert index.doc_count() == 1
    
    def test_index_batch(self, index):
        """Test batch indexing."""
        docs = [
            TantivyDocument(
                doc_id=f"doc-{i}",
                content=f"Document {i} content",
                domain="test",
            )
            for i in range(10)
        ]
        
        success, failed = index.index_batch(docs)
        
        assert success == 10
        assert failed == 0
        assert index.doc_count() == 10
    
    def test_search_basic(self, index):
        """Test basic search."""
        docs = [
            TantivyDocument(
                doc_id="safety-1",
                content="Aircraft safety procedures",
                domain="aviation",
            ),
            TantivyDocument(
                doc_id="maint-1",
                content="Engine maintenance guide",
                domain="automotive",
            ),
        ]
        index.index_batch(docs)
        
        results = index.search("safety procedures")
        
        assert len(results) >= 1
        assert results[0].doc_id == "safety-1"
        assert results[0].score > 0
    
    def test_search_domain_filter(self, index):
        """Test search with domain filter."""
        docs = [
            TantivyDocument(
                doc_id="av-1",
                content="Safety first in aviation",
                domain="aviation",
            ),
            TantivyDocument(
                doc_id="auto-1",
                content="Safety first in automotive",
                domain="automotive",
            ),
        ]
        index.index_batch(docs)
        
        results = index.search("safety", domain="aviation")
        
        assert len(results) == 1
        assert results[0].domain == "aviation"
    
    def test_search_no_results(self, index):
        """Test search with no matches."""
        doc = TantivyDocument(
            doc_id="doc-1",
            content="Something completely different",
        )
        index.index_document(doc)
        
        results = index.search("nonexistent query")
        
        assert len(results) == 0
    
    def test_search_top_k(self, index):
        """Test top_k limit."""
        docs = [
            TantivyDocument(
                doc_id=f"doc-{i}",
                content=f"Common term document {i}",
            )
            for i in range(20)
        ]
        index.index_batch(docs)
        
        results = index.search("common term", top_k=5)
        
        assert len(results) == 5
    
    def test_delete_document(self, index):
        """Test document deletion."""
        doc = TantivyDocument(doc_id="to-delete", content="Delete me")
        index.index_document(doc)
        
        assert index.doc_count() == 1
        
        result = index.delete_document("to-delete")
        
        assert result is True
        assert index.doc_count() == 0
    
    def test_delete_nonexistent(self, index):
        """Test deleting nonexistent document."""
        result = index.delete_document("nonexistent")
        
        assert result is False
    
    def test_delete_by_domain(self, index):
        """Test deleting all documents in domain."""
        docs = [
            TantivyDocument(doc_id="av-1", content="Aviation 1", domain="aviation"),
            TantivyDocument(doc_id="av-2", content="Aviation 2", domain="aviation"),
            TantivyDocument(doc_id="auto-1", content="Auto 1", domain="automotive"),
        ]
        index.index_batch(docs)
        
        deleted = index.delete_by_domain("aviation")
        
        assert deleted == 2
        assert index.doc_count() == 1
    
    def test_persistence(self, tmp_path):
        """Test index persists to disk."""
        index_path = str(tmp_path / "persist_index")
        
        # Create and populate
        index1 = TantivyBM25Fallback(index_path)
        index1.index_document(TantivyDocument(
            doc_id="persist-1",
            content="Persistent content",
        ))
        index1.commit()
        
        # Reopen
        index2 = TantivyBM25Fallback(index_path)
        
        assert index2.doc_count() == 1
        
        results = index2.search("persistent")
        assert len(results) == 1
    
    def test_get_stats(self, index):
        """Test statistics reporting."""
        docs = [
            TantivyDocument(doc_id=f"doc-{i}", content=f"Content {i}", domain="test")
            for i in range(5)
        ]
        index.index_batch(docs)
        
        stats = index.get_stats()
        
        assert stats["doc_count"] == 5
        assert stats["is_fallback"] is True
        assert "test" in stats["domains"]
    
    def test_clear(self, index):
        """Test clearing all documents."""
        docs = [
            TantivyDocument(doc_id=f"doc-{i}", content=f"Content {i}")
            for i in range(10)
        ]
        index.index_batch(docs)
        
        assert index.doc_count() == 10
        
        index.clear()
        
        assert index.doc_count() == 0


class TestCreateBM25Index:
    """Tests for create_bm25_index factory function."""
    
    def test_creates_fallback_without_tantivy(self, tmp_path):
        """Creates fallback when tantivy not available."""
        with patch("core.indexing.tantivy_bm25.TANTIVY_AVAILABLE", False):
            index = create_bm25_index(str(tmp_path / "test_index"))
            
            assert isinstance(index, TantivyBM25Fallback)
    
    @pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="Tantivy not installed")
    def test_creates_tantivy_index(self, tmp_path):
        """Creates real Tantivy index when available."""
        from core.indexing.tantivy_bm25 import TantivyBM25Index
        
        index = create_bm25_index(str(tmp_path / "tantivy_index"))
        
        assert isinstance(index, TantivyBM25Index)


@pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="Tantivy not installed")
class TestTantivyBM25Index:
    """Tests for real Tantivy index (when available)."""
    
    @pytest.fixture
    def index(self, tmp_path):
        """Create Tantivy index."""
        from core.indexing.tantivy_bm25 import TantivyBM25Index
        
        idx = TantivyBM25Index(
            str(tmp_path / "tantivy_test"),
            heap_size_mb=64,
            auto_commit=False,
        )
        yield idx
        idx.close()
    
    def test_index_and_search(self, index):
        """Test indexing and searching."""
        doc = TantivyDocument(
            doc_id="doc-001",
            content="Aircraft maintenance procedures",
            title="Maintenance Manual",
            domain="aviation",
        )
        
        index.index_document(doc)
        index.commit()
        
        results = index.search("maintenance")
        
        assert len(results) >= 1
        assert results[0].doc_id == "doc-001"
    
    def test_batch_index(self, index):
        """Test batch indexing."""
        docs = [
            TantivyDocument(
                doc_id=f"batch-{i}",
                content=f"Batch document {i} with unique content",
            )
            for i in range(100)
        ]
        
        success, failed = index.index_batch(docs)
        
        assert success == 100
        assert failed == 0
        assert index.doc_count() == 100
    
    def test_domain_search(self, index):
        """Test domain-filtered search."""
        docs = [
            TantivyDocument(
                doc_id="av-1",
                content="Safety critical procedure",
                domain="aviation",
            ),
            TantivyDocument(
                doc_id="auto-1", 
                content="Safety critical procedure",
                domain="automotive",
            ),
        ]
        index.index_batch(docs)
        
        results = index.search("safety", domain="aviation")
        
        assert len(results) == 1
        assert results[0].domain == "aviation"
    
    def test_stats(self, index):
        """Test statistics."""
        docs = [
            TantivyDocument(doc_id=f"doc-{i}", content=f"Content {i}")
            for i in range(50)
        ]
        index.index_batch(docs)
        
        stats = index.get_stats()
        
        assert stats["doc_count"] == 50
        assert stats["total_indexed"] == 50
        assert "index_path" in stats


class TestSearchScoring:
    """Tests for search result scoring."""
    
    @pytest.fixture
    def index(self, tmp_path):
        """Create index with test documents."""
        idx = TantivyBM25Fallback(str(tmp_path / "score_test"))
        
        docs = [
            TantivyDocument(
                doc_id="exact",
                content="aircraft maintenance procedures",
            ),
            TantivyDocument(
                doc_id="partial",
                content="maintenance of vehicles",
            ),
            TantivyDocument(
                doc_id="none",
                content="something completely different",
            ),
        ]
        idx.index_batch(docs)
        return idx
    
    def test_scoring_order(self, index):
        """More relevant documents score higher."""
        results = index.search("aircraft maintenance")
        
        assert len(results) >= 1
        # "exact" should score highest (has both terms)
        assert results[0].doc_id == "exact"
    
    def test_partial_match(self, index):
        """Partial matches are returned."""
        results = index.search("maintenance")
        
        # Both "exact" and "partial" should match
        doc_ids = {r.doc_id for r in results}
        assert "exact" in doc_ids
        assert "partial" in doc_ids
