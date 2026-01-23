"""
Unit tests for incremental FAISS index.

Tests cover:
- Index creation and loading
- Adding embeddings
- Backup and rollback
- Search functionality
- Atomic updates
"""

import numpy as np
import pytest
import importlib.util
from core.indexing.incremental_faiss import (
    IncrementalFAISSIndex,
    atomic_index_update,
)

FAISS_AVAILABLE = importlib.util.find_spec("faiss") is not None


pytestmark = pytest.mark.skipif(not FAISS_AVAILABLE, reason="faiss not installed")


class TestIncrementalFAISSIndex:
    """Test incremental FAISS index."""
    
    def test_create_new_index(self, tmp_path):
        """Test creating new index."""
        index_path = tmp_path / "test.index"
        
        index = IncrementalFAISSIndex(
            dimension=384,
            index_path=index_path
        )
        
        assert index.total_vectors == 0
        assert index.dimension == 384
        assert index.index is not None
    
    def test_add_chunks_basic(self, tmp_path):
        """Test adding chunks to index."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Create test embeddings
        embeddings = np.random.rand(5, 384).astype('float32')
        chunk_ids = [0, 1, 2, 3, 4]
        
        success, error = index.add_chunks(embeddings, chunk_ids, backup=False)
        
        assert success
        assert error is None
        assert index.total_vectors == 5
    
    def test_add_chunks_incremental(self, tmp_path):
        """Test adding chunks incrementally."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Add first batch
        embeddings1 = np.random.rand(5, 384).astype('float32')
        index.add_chunks(embeddings1, [0, 1, 2, 3, 4], backup=False)
        
        # Add second batch
        embeddings2 = np.random.rand(3, 384).astype('float32')
        success, error = index.add_chunks(embeddings2, [5, 6, 7], backup=False)
        
        assert success
        assert index.total_vectors == 8
    
    def test_add_chunks_dimension_mismatch(self, tmp_path):
        """Test error handling for dimension mismatch."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Wrong dimension
        embeddings = np.random.rand(5, 512).astype('float32')
        chunk_ids = [0, 1, 2, 3, 4]
        
        success, error = index.add_chunks(embeddings, chunk_ids, backup=False)
        
        assert not success
        assert error is not None
        assert "dimension" in error.lower()
    
    def test_add_chunks_count_mismatch(self, tmp_path):
        """Test error handling for embedding/chunk_id count mismatch."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        embeddings = np.random.rand(5, 384).astype('float32')
        chunk_ids = [0, 1, 2]  # Only 3 IDs for 5 embeddings
        
        success, error = index.add_chunks(embeddings, chunk_ids, backup=False)
        
        assert not success
        assert error is not None
        assert "count" in error.lower()
    
    def test_save_and_load(self, tmp_path):
        """Test saving and loading index."""
        index_path = tmp_path / "test.index"
        
        # Create and populate index
        index1 = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        embeddings = np.random.rand(10, 384).astype('float32')
        index1.add_chunks(embeddings, list(range(10)), backup=False)
        index1.save()
        
        # Load in new instance
        index2 = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        assert index2.total_vectors == 10
    
    def test_search_basic(self, tmp_path):
        """Test searching index."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Add embeddings
        embeddings = np.random.rand(10, 384).astype('float32')
        index.add_chunks(embeddings, list(range(10)), backup=False)
        
        # Search
        query = np.random.rand(384).astype('float32')
        distances, indices = index.search(query, k=5)
        
        assert distances.shape == (1, 5)
        assert indices.shape == (1, 5)
    
    def test_search_with_2d_query(self, tmp_path):
        """Test searching with 2D query array."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        embeddings = np.random.rand(10, 384).astype('float32')
        index.add_chunks(embeddings, list(range(10)), backup=False)
        
        # 2D query
        query = np.random.rand(1, 384).astype('float32')
        distances, indices = index.search(query, k=5)
        
        assert distances.shape == (1, 5)
        assert indices.shape == (1, 5)
    
    def test_backup_creation(self, tmp_path):
        """Test backup creation."""
        index_path = tmp_path / "test.index"
        backup_dir = tmp_path / "backups"
        
        index = IncrementalFAISSIndex(
            dimension=384,
            index_path=index_path,
            backup_dir=backup_dir
        )
        
        # Add data and create backup
        embeddings = np.random.rand(5, 384).astype('float32')
        index.add_chunks(embeddings, [0, 1, 2, 3, 4], backup=True)
        
        # Check backup exists
        backups = list(backup_dir.glob("*.index"))
        assert len(backups) > 0
    
    def test_backup_cleanup(self, tmp_path):
        """Test old backup cleanup."""
        index_path = tmp_path / "test.index"
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        index = IncrementalFAISSIndex(
            dimension=384,
            index_path=index_path,
            backup_dir=backup_dir
        )
        
        # Create multiple backups
        embeddings = np.random.rand(5, 384).astype('float32')
        for i in range(7):
            index.add_chunks(embeddings, [i*5 + j for j in range(5)], backup=True)
        
        # Should keep only last 5 backups
        backups = list(backup_dir.glob("*.index"))
        assert len(backups) <= 5
    
    def test_get_stats(self, tmp_path):
        """Test getting index statistics."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        embeddings = np.random.rand(10, 384).astype('float32')
        index.add_chunks(embeddings, list(range(10)), backup=False)
        
        stats = index.get_stats()
        
        assert stats["dimension"] == 384
        assert stats["total_vectors"] == 10
        assert stats["index_type"] == "IndexFlatL2"
        assert "index_path" in stats


class TestAtomicIndexUpdate:
    """Test atomic index update context manager."""
    
    def test_atomic_update_success(self, tmp_path):
        """Test successful atomic update."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Initial state
        embeddings1 = np.random.rand(5, 384).astype('float32')
        index.add_chunks(embeddings1, [0, 1, 2, 3, 4], backup=False)
        
        # Atomic update
        with atomic_index_update(index):
            embeddings2 = np.random.rand(3, 384).astype('float32')
            index.add_chunks(embeddings2, [5, 6, 7], backup=False)
        
        assert index.total_vectors == 8
    
    def test_atomic_update_rollback(self, tmp_path):
        """Test rollback on failure."""
        index_path = tmp_path / "test.index"
        index = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        
        # Initial state
        embeddings1 = np.random.rand(5, 384).astype('float32')
        index.add_chunks(embeddings1, [0, 1, 2, 3, 4], backup=False)
        initial_count = index.total_vectors
        
        # Atomic update that fails
        try:
            with atomic_index_update(index):
                # Valid addition
                embeddings2 = np.random.rand(3, 384).astype('float32')
                index.add_chunks(embeddings2, [5, 6, 7], backup=False)
                
                # Force an error
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Should rollback to initial state
        assert index.total_vectors == initial_count


class TestIndexPersistence:
    """Test index persistence across sessions."""
    
    def test_persistence_across_sessions(self, tmp_path):
        """Test that index persists across sessions."""
        index_path = tmp_path / "test.index"
        
        # Session 1: Create and populate
        index1 = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        embeddings1 = np.random.rand(10, 384).astype('float32')
        index1.add_chunks(embeddings1, list(range(10)), backup=False)
        del index1
        
        # Session 2: Load and add more
        index2 = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        assert index2.total_vectors == 10
        
        embeddings2 = np.random.rand(5, 384).astype('float32')
        index2.add_chunks(embeddings2, list(range(10, 15)), backup=False)
        del index2
        
        # Session 3: Verify total
        index3 = IncrementalFAISSIndex(dimension=384, index_path=index_path)
        assert index3.total_vectors == 15
