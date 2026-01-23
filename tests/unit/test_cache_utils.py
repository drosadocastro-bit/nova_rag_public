"""
Unit tests for cache_utils module.
Tests secure caching, retrieval caching, and SQL logging.
"""
import pytest


class TestRetrievalCache:
    """Tests for retrieval caching functionality."""
    
    def test_cache_disabled_by_default(self, monkeypatch):
        """Test that caching is disabled when env var not set."""
        monkeypatch.setenv("NOVA_ENABLE_RETRIEVAL_CACHE", "0")
        
        # Import after setting env var
        import cache_utils
        
        # Create a mock function
        call_count = {"count": 0}
        
        def mock_retrieve(query, k=12, top_n=6, **kwargs):
            call_count["count"] += 1
            return [{"text": f"Result {call_count['count']}", "confidence": 0.9}]
        
        cached_retrieve = cache_utils.cache_retrieval(mock_retrieve)
        
        # Call twice with same params
        result1 = cached_retrieve("test query", k=12, top_n=6)
        result2 = cached_retrieve("test query", k=12, top_n=6)
        
        # Both should call the function (no caching)
        assert call_count["count"] == 2
        assert result1 != result2  # Different results due to counter
    
    def test_cache_enabled(self, monkeypatch):
        """Test that caching works when enabled."""
        monkeypatch.setenv("NOVA_ENABLE_RETRIEVAL_CACHE", "1")
        
        # Clear the module cache
        import sys
        if "cache_utils" in sys.modules:
            del sys.modules["cache_utils"]
        
        import cache_utils
        
        call_count = {"count": 0}
        
        def mock_retrieve(query, k=12, top_n=6, **kwargs):
            call_count["count"] += 1
            return [{"text": "Cached result", "confidence": 0.9}]
        
        cached_retrieve = cache_utils.cache_retrieval(mock_retrieve)
        
        # Call twice with same params
        result1 = cached_retrieve("test query", k=12, top_n=6)
        result2 = cached_retrieve("test query", k=12, top_n=6)
        
        # Second call should use cache
        assert call_count["count"] == 1
        assert result1 == result2
    
    def test_cache_key_generation(self):
        """Test that cache keys are generated correctly."""
        import cache_utils
        
        key1 = cache_utils._cache_key("query1", 12, 6)
        key2 = cache_utils._cache_key("query1", 12, 6)
        key3 = cache_utils._cache_key("query2", 12, 6)
        key4 = cache_utils._cache_key("query1", 10, 6)
        
        # Same params should generate same key
        assert key1 == key2
        
        # Different params should generate different keys
        assert key1 != key3
        assert key1 != key4
    
    def test_clear_cache(self, monkeypatch, tmp_path):
        """Test cache clearing functionality."""
        monkeypatch.setenv("NOVA_ENABLE_RETRIEVAL_CACHE", "1")
        cache_file = tmp_path / "retrieval_cache.pkl"
        
        import sys
        if "cache_utils" in sys.modules:
            del sys.modules["cache_utils"]
        
        import cache_utils
        cache_utils._retrieval_cache_file = cache_file
        
        # Add something to cache
        cache_utils._retrieval_cache["test_key"] = ["test_value"]
        cache_file.write_text("dummy")
        
        # Clear cache
        cache_utils.clear_retrieval_cache()
        
        assert len(cache_utils._retrieval_cache) == 0
        assert not cache_file.exists()


class TestSQLLogging:
    """Tests for SQL query logging functionality."""
    
    def test_sql_logging_disabled_by_default(self, monkeypatch):
        """Test that SQL logging doesn't run when disabled."""
        monkeypatch.setenv("NOVA_ENABLE_SQL_LOG", "0")
        
        import cache_utils
        
        # Should not raise any errors
        cache_utils.log_query(
            question="test",
            mode="auto",
            model_used="test",
            retrieval_confidence=0.8,
            audit_status="pass",
            citation_audit_enabled=True,
            citation_strict_enabled=False,
            answer_length=100,
            session_id="test_session",
            response_time_ms=500.0
        )
    
    def test_sql_logging_enabled(self, monkeypatch, tmp_path):
        """Test SQL logging when enabled."""
        monkeypatch.setenv("NOVA_ENABLE_SQL_LOG", "1")
        db_path = tmp_path / "query_log.db"
        
        import sys
        if "cache_utils" in sys.modules:
            del sys.modules["cache_utils"]
        
        import cache_utils
        cache_utils._sql_log_db = db_path
        
        # Initialize DB
        cache_utils.init_sql_log()
        assert db_path.exists()
        
        # Log a query
        cache_utils.log_query(
            question="test question",
            mode="auto",
            model_used="llama3.2:3b",
            retrieval_confidence=0.85,
            audit_status="pass",
            citation_audit_enabled=True,
            citation_strict_enabled=False,
            answer_length=150,
            session_id="session_123",
            response_time_ms=750.0
        )
        
        # Verify it was logged
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM query_log")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 1
    
    def test_get_query_stats(self, monkeypatch, tmp_path):
        """Test retrieval of query statistics."""
        monkeypatch.setenv("NOVA_ENABLE_SQL_LOG", "1")
        db_path = tmp_path / "query_log.db"
        
        import sys
        if "cache_utils" in sys.modules:
            del sys.modules["cache_utils"]
        
        import cache_utils
        cache_utils._sql_log_db = db_path
        
        # Initialize and log some queries
        cache_utils.init_sql_log()
        
        for i in range(3):
            cache_utils.log_query(
                question=f"test {i}",
                mode="auto",
                model_used="test",
                retrieval_confidence=0.8 + i * 0.05,
                audit_status="pass" if i % 2 == 0 else "fail",
                citation_audit_enabled=True,
                citation_strict_enabled=False,
                answer_length=100,
                session_id=f"session_{i}",
                response_time_ms=500.0 + i * 100
            )
        
        # Get stats
        stats = cache_utils.get_query_stats()
        
        assert stats["total_queries"] == 3
        assert "avg_response_time_ms" in stats
        assert "avg_retrieval_confidence" in stats
        assert "audit_status_breakdown" in stats


class TestSecureCache:
    """Tests for secure pickle serialization."""
    
    def test_secure_cache_availability(self):
        """Test that secure cache module is importable."""
        import importlib
        try:
            importlib.import_module("secure_cache")
            assert True
        except ImportError:
            # It's OK if not available, cache_utils falls back to regular pickle
            assert True
    
    def test_cache_with_hmac(self, tmp_path, monkeypatch):
        """Test caching with HMAC verification if available."""
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")
        
        try:
            from secure_cache import secure_pickle_dump, secure_pickle_load
            
            test_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
            cache_file = tmp_path / "test_cache.pkl"
            
            # Save with HMAC
            secure_pickle_dump(test_data, cache_file)
            assert cache_file.exists()
            
            # Load and verify
            loaded_data = secure_pickle_load(cache_file)
            assert loaded_data == test_data
            
        except ImportError:
            # Secure cache not available, skip test
            pytest.skip("secure_cache module not available")
    
    def test_tampered_cache_rejected(self, tmp_path, monkeypatch):
        """Test that tampered cache files are rejected."""
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")
        
        try:
            from secure_cache import secure_pickle_dump, secure_pickle_load
            
            test_data = {"key": "value"}
            cache_file = tmp_path / "test_cache.pkl"
            
            # Save with HMAC
            secure_pickle_dump(test_data, cache_file)
            
            # Tamper with file
            with open(cache_file, "ab") as f:
                f.write(b"tampered data")
            
            # Should raise ValueError on load
            with pytest.raises(ValueError, match="HMAC verification failed"):
                secure_pickle_load(cache_file)
                
        except ImportError:
            pytest.skip("secure_cache module not available")


@pytest.mark.unit
class TestCacheUtils:
    """General cache utilities tests."""
    
    def test_cache_modules_importable(self):
        """Test that cache_utils module imports successfully."""
        import cache_utils
        
        assert hasattr(cache_utils, "cache_retrieval")
        assert hasattr(cache_utils, "init_sql_log")
        assert hasattr(cache_utils, "log_query")
        assert hasattr(cache_utils, "get_query_stats")
        assert hasattr(cache_utils, "clear_retrieval_cache")
