"""
Unit tests for incremental BM25 index.

Tests cover:
- Document addition
- Corpus persistence
- Search functionality
- Domain filtering
- Document removal
"""

import pytest
import importlib.util
from core.indexing.incremental_bm25 import (
    IncrementalBM25,
    BM25Document,
)

BM25_AVAILABLE = importlib.util.find_spec("rank_bm25") is not None


pytestmark = pytest.mark.skipif(not BM25_AVAILABLE, reason="rank-bm25 not installed")


class TestBM25Document:
    """Test BM25Document dataclass."""
    
    def test_document_creation(self):
        """Test creating BM25 document."""
        doc = BM25Document(
            chunk_id=0,
            tokens=["test", "document", "tokens"],
            domain="vehicle",
            metadata={"file": "test.pdf"}
        )
        
        assert doc.chunk_id == 0
        assert len(doc.tokens) == 3
        assert doc.domain == "vehicle"
        assert doc.metadata["file"] == "test.pdf"


class TestIncrementalBM25:
    """Test IncrementalBM25 class."""
    
    def test_initialization_new(self, tmp_path):
        """Test initializing new BM25 index."""
        corpus_path = tmp_path / "corpus.pkl"
        
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        assert bm25.total_documents == 0
        assert bm25.bm25 is None
    
    def test_add_documents_basic(self, tmp_path):
        """Test adding documents."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [
            BM25Document(
                chunk_id=i,
                tokens=["token" + str(i), "test"],
                domain="vehicle",
                metadata={}
            )
            for i in range(5)
        ]
        
        success, error = bm25.add_documents(docs)
        
        assert success
        assert error is None
        assert bm25.total_documents == 5
        assert bm25.bm25 is not None
    
    def test_add_documents_incremental(self, tmp_path):
        """Test adding documents in multiple batches."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        # First batch
        docs1 = [
            BM25Document(chunk_id=i, tokens=["batch1", "token"], domain="vehicle", metadata={})
            for i in range(5)
        ]
        bm25.add_documents(docs1)
        
        # Second batch
        docs2 = [
            BM25Document(chunk_id=i+5, tokens=["batch2", "token"], domain="forklift", metadata={})
            for i in range(3)
        ]
        success, error = bm25.add_documents(docs2)
        
        assert success
        assert bm25.total_documents == 8
    
    def test_add_documents_duplicate_chunk_ids(self, tmp_path):
        """Test error handling for duplicate chunk IDs."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        # Add first batch
        docs1 = [BM25Document(chunk_id=0, tokens=["test"], domain="vehicle", metadata={})]
        bm25.add_documents(docs1)
        
        # Try to add duplicate
        docs2 = [BM25Document(chunk_id=0, tokens=["duplicate"], domain="vehicle", metadata={})]
        success, error = bm25.add_documents(docs2)
        
        assert not success
        assert error is not None
        assert "duplicate" in error.lower()
    
    def test_search_basic(self, tmp_path):
        """Test basic search."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [
            BM25Document(chunk_id=0, tokens=["brake", "system", "maintenance"], domain="vehicle", metadata={}),
            BM25Document(chunk_id=1, tokens=["engine", "oil", "change"], domain="vehicle", metadata={}),
            BM25Document(chunk_id=2, tokens=["tire", "pressure", "check"], domain="vehicle", metadata={}),
        ]
        bm25.add_documents(docs)
        
        # Search for brake-related content
        results = bm25.search(["brake", "system"], k=2)
        
        assert len(results) > 0
        assert results[0][0] == 0  # Should return chunk_id 0
    
    def test_search_with_domain_filter(self, tmp_path):
        """Test search with domain filtering."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [
            BM25Document(chunk_id=0, tokens=["hydraulic", "system"], domain="vehicle", metadata={}),
            BM25Document(chunk_id=1, tokens=["hydraulic", "lift"], domain="forklift", metadata={}),
            BM25Document(chunk_id=2, tokens=["hydraulic", "pump"], domain="vehicle", metadata={}),
        ]
        bm25.add_documents(docs)
        
        # Search only forklift domain
        results = bm25.search(["hydraulic"], k=5, domain_filter="forklift")
        
        # Should only return forklift documents
        chunk_ids = [r[0] for r in results]
        assert 1 in chunk_ids
        assert 0 not in chunk_ids
        assert 2 not in chunk_ids
    
    def test_remove_documents(self, tmp_path):
        """Test document removal."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        # Add documents
        docs = [
            BM25Document(chunk_id=i, tokens=["doc" + str(i)], domain="vehicle", metadata={})
            for i in range(5)
        ]
        bm25.add_documents(docs)
        
        # Remove some documents
        success, error = bm25.remove_documents([1, 3])
        
        assert success
        assert bm25.total_documents == 3
        
        # Verify removed documents not in index
        assert bm25.get_document(1) is None
        assert bm25.get_document(3) is None
        assert bm25.get_document(0) is not None
    
    def test_save_and_load(self, tmp_path):
        """Test corpus persistence."""
        corpus_path = tmp_path / "corpus.pkl"
        
        # Create and populate index
        bm25_1 = IncrementalBM25(corpus_path=corpus_path)
        docs = [
            BM25Document(chunk_id=i, tokens=["test", str(i)], domain="vehicle", metadata={})
            for i in range(10)
        ]
        bm25_1.add_documents(docs)
        
        # Load in new instance
        bm25_2 = IncrementalBM25(corpus_path=corpus_path)
        
        assert bm25_2.total_documents == 10
        assert bm25_2.bm25 is not None
    
    def test_get_document(self, tmp_path):
        """Test retrieving document by chunk ID."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [
            BM25Document(chunk_id=5, tokens=["test"], domain="vehicle", metadata={"key": "value"}),
        ]
        bm25.add_documents(docs)
        
        doc = bm25.get_document(5)
        
        assert doc is not None
        assert doc.chunk_id == 5
        assert doc.metadata["key"] == "value"
    
    def test_get_document_nonexistent(self, tmp_path):
        """Test retrieving non-existent document."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        doc = bm25.get_document(999)
        
        assert doc is None
    
    def test_get_stats(self, tmp_path):
        """Test getting index statistics."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [
            BM25Document(chunk_id=0, tokens=["test"], domain="vehicle", metadata={}),
            BM25Document(chunk_id=1, tokens=["test"], domain="vehicle", metadata={}),
            BM25Document(chunk_id=2, tokens=["test"], domain="forklift", metadata={}),
        ]
        bm25.add_documents(docs)
        
        stats = bm25.get_stats()
        
        assert stats["total_documents"] == 3
        assert stats["index_built"] is True
        assert "vehicle" in stats["domain_distribution"]
        assert "forklift" in stats["domain_distribution"]
        assert stats["domain_distribution"]["vehicle"] == 2
        assert stats["domain_distribution"]["forklift"] == 1
    
    def test_clear(self, tmp_path):
        """Test clearing index."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        docs = [BM25Document(chunk_id=i, tokens=["test"], domain="vehicle", metadata={}) for i in range(5)]
        bm25.add_documents(docs)
        
        bm25.clear()
        
        assert bm25.total_documents == 0
        assert bm25.bm25 is None
    
    def test_empty_search(self, tmp_path):
        """Test searching empty index."""
        corpus_path = tmp_path / "corpus.pkl"
        bm25 = IncrementalBM25(corpus_path=corpus_path)
        
        results = bm25.search(["test"], k=5)
        
        assert len(results) == 0
