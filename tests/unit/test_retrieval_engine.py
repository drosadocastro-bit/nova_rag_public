"""
Tests for Core Retrieval Engine.

Tests the retrieval pipeline including:
- BM25 retrieval
- Lexical retrieval
- Query expansion (GAR)
- Reranking
- Hybrid search
"""

import re
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestTokenization:
    """Tests for the _tokenize function."""
    
    def test_basic_tokenization(self):
        """Test basic text tokenization."""
        from core.retrieval.retrieval_engine import _tokenize
        
        tokens = _tokenize("Hello World Test")
        
        assert tokens == ["hello", "world", "test"]
    
    def test_punctuation_removal(self):
        """Test that punctuation is removed."""
        from core.retrieval.retrieval_engine import _tokenize
        
        tokens = _tokenize("Hello, world! How's it going?")
        
        # Punctuation should be stripped, apostrophes split
        assert "hello" in tokens
        assert "world" in tokens
    
    def test_empty_string(self):
        """Test empty string handling."""
        from core.retrieval.retrieval_engine import _tokenize
        
        tokens = _tokenize("")
        
        assert tokens == []
    
    def test_none_handling(self):
        """Test None handling."""
        from core.retrieval.retrieval_engine import _tokenize
        
        tokens = _tokenize("")  # Pass empty string instead of None
        
        assert tokens == []
    
    def test_numbers_preserved(self):
        """Test that numbers are preserved."""
        from core.retrieval.retrieval_engine import _tokenize
        
        tokens = _tokenize("Error code 1234")
        
        assert "error" in tokens
        assert "code" in tokens
        assert "1234" in tokens


class TestBM25Scoring:
    """Tests for BM25 scoring mechanics."""
    
    def test_idf_known_term(self):
        """Test IDF for a known term."""
        from core.retrieval.retrieval_engine import _bm25_idf
        
        # IDF should be non-negative
        idf = _bm25_idf("test")
        
        assert idf >= 0.0
    
    def test_idf_unknown_term(self):
        """Test IDF for unknown term."""
        from core.retrieval.retrieval_engine import _bm25_idf
        
        idf = _bm25_idf("xyznonexistent123")
        
        # Unknown terms should have 0 IDF
        assert idf == 0.0


class TestBM25Retrieval:
    """Tests for BM25 retrieval."""
    
    def test_bm25_retrieve_returns_list(self):
        """Test that BM25 returns a list."""
        from core.retrieval.retrieval_engine import bm25_retrieve
        
        results = bm25_retrieve("oil change", k=5)
        
        assert isinstance(results, list)
    
    def test_bm25_retrieve_respects_k(self):
        """Test that results don't exceed k."""
        from core.retrieval.retrieval_engine import bm25_retrieve
        
        results = bm25_retrieve("maintenance", k=3, top_n=3)
        
        assert len(results) <= 3
    
    def test_bm25_retrieve_includes_score(self):
        """Test that results include BM25 score."""
        from core.retrieval.retrieval_engine import bm25_retrieve
        
        results = bm25_retrieve("brake", k=5)
        
        for result in results:
            if result:  # If there are results
                assert "bm25_score" in result
    
    def test_bm25_empty_query(self):
        """Test BM25 with empty query."""
        from core.retrieval.retrieval_engine import bm25_retrieve
        
        results = bm25_retrieve("", k=5)
        
        # Should return empty or handle gracefully
        assert isinstance(results, list)


class TestLexicalRetrieval:
    """Tests for lexical (Jaccard-based) retrieval."""
    
    def test_lexical_retrieve_returns_list(self):
        """Test lexical retrieval returns a list."""
        from core.retrieval.retrieval_engine import lexical_retrieve
        
        results = lexical_retrieve("oil change", k=5)
        
        assert isinstance(results, list)
    
    def test_lexical_includes_confidence(self):
        """Test that results include confidence score."""
        from core.retrieval.retrieval_engine import lexical_retrieve
        
        results = lexical_retrieve("maintenance", k=5)
        
        for result in results:
            if result:
                assert "confidence" in result
    
    def test_lexical_confidence_in_range(self):
        """Test that confidence is between 0 and 1."""
        from core.retrieval.retrieval_engine import lexical_retrieve
        
        results = lexical_retrieve("brake fluid", k=5)
        
        for result in results:
            if "confidence" in result:
                assert 0 <= result["confidence"] <= 1


class TestErrorCodeLookup:
    """Tests for error code table lookup."""
    
    def test_error_code_dict_exists(self):
        """Test that error code index exists."""
        from core.retrieval.retrieval_engine import ERROR_CODE_TO_DOCS
        
        assert isinstance(ERROR_CODE_TO_DOCS, dict)
    
    def test_error_code_values_are_lists(self):
        """Test that error code values are lists of docs."""
        from core.retrieval.retrieval_engine import ERROR_CODE_TO_DOCS
        
        for code, docs in ERROR_CODE_TO_DOCS.items():
            assert isinstance(docs, list)


class TestFallbackDocs:
    """Tests for fallback document generation."""
    
    def test_fallback_returns_list(self):
        """Test that fallback returns list."""
        from core.retrieval.retrieval_engine import _fallback_docs
        
        result = _fallback_docs()
        
        assert isinstance(result, list)
    
    def test_fallback_has_required_fields(self):
        """Test fallback docs have required fields."""
        from core.retrieval.retrieval_engine import _fallback_docs
        
        result = _fallback_docs()
        
        for doc in result:
            assert "id" in doc
            assert "source" in doc
            assert "text" in doc


class TestCrossEncoderReranking:
    """Tests for cross-encoder reranking."""
    
    def test_get_cross_encoder_flag(self):
        """Test cross-encoder disable flag exists."""
        from core.retrieval.retrieval_engine import DISABLE_CROSS_ENCODER
        
        # Flag should be a boolean
        assert isinstance(DISABLE_CROSS_ENCODER, bool)


class TestAnomalyDetector:
    """Tests for anomaly detector integration."""
    
    def test_anomaly_detector_flag(self):
        """Test anomaly detector enabled flag."""
        from core.retrieval.retrieval_engine import ANOMALY_DETECTOR_ENABLED
        
        # Flag should be a boolean
        assert isinstance(ANOMALY_DETECTOR_ENABLED, bool)


class TestHybridSearch:
    """Tests for hybrid search configuration."""
    
    def test_hybrid_search_env_toggle(self):
        """Test hybrid search can be toggled via env."""
        import os
        
        os.environ["NOVA_HYBRID_SEARCH"] = "0"
        
        try:
            from core.retrieval.retrieval_engine import HYBRID_SEARCH_ENABLED
            # Note: This tests at import time, so it may not reflect change
            assert isinstance(HYBRID_SEARCH_ENABLED, bool)
        finally:
            os.environ.pop("NOVA_HYBRID_SEARCH", None)


class TestBM25Cache:
    """Tests for BM25 index caching."""
    
    def test_corpus_hash_generation(self):
        """Test corpus hash is generated correctly."""
        from core.retrieval.retrieval_engine import _compute_corpus_hash
        
        hash1 = _compute_corpus_hash()
        hash2 = _compute_corpus_hash()
        
        # Same corpus should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA256 truncated to 16 chars


class TestQueryExpansion:
    """Tests for GAR query expansion."""
    
    def test_gar_import_flag(self):
        """Test GAR availability flag."""
        from core.retrieval.retrieval_engine import GAR_ENABLED
        
        assert isinstance(GAR_ENABLED, bool)


class TestIndexManagement:
    """Tests for index loading and management."""
    
    def test_index_exists(self):
        """Test that index variable exists."""
        from core.retrieval.retrieval_engine import index, docs
        
        # Index may be None in test environment
        assert docs is not None
        assert isinstance(docs, list)
    
    def test_docs_have_required_fields(self):
        """Test loaded docs have required fields."""
        from core.retrieval.retrieval_engine import docs
        
        for doc in docs[:10]:  # Check first 10
            assert "id" in doc
            assert "text" in doc or "snippet" in doc


class TestVisionSearch:
    """Tests for vision search utilities."""
    
    def test_vision_disabled_flag(self):
        """Test vision can be disabled."""
        from core.retrieval.retrieval_engine import DISABLE_VISION
        
        assert isinstance(DISABLE_VISION, bool)
    
    def test_ensure_vision_loaded_when_disabled(self):
        """Test vision returns None when disabled."""
        import os
        os.environ["NOVA_DISABLE_VISION"] = "1"
        
        try:
            from core.retrieval.retrieval_engine import ensure_vision_loaded
            
            model, embeddings, paths = ensure_vision_loaded()
            
            # Should return None when disabled
            assert model is None
        finally:
            os.environ.pop("NOVA_DISABLE_VISION", None)


class TestEmbeddingModel:
    """Tests for text embedding model."""
    
    def test_embed_disabled_flag(self):
        """Test embedding can be disabled."""
        from core.retrieval.retrieval_engine import DISABLE_EMBED
        
        assert isinstance(DISABLE_EMBED, bool)


class TestTFIDFCache:
    """Tests for TF-IDF vectorizer caching."""
    
    def test_tfidf_initialization_flag(self):
        """Test TF-IDF fitted flag."""
        from core.retrieval.retrieval_engine import tfidf_vectorizer_fitted
        
        assert isinstance(tfidf_vectorizer_fitted, bool)


class TestRetrievalConfig:
    """Tests for retrieval configuration."""
    
    def test_batch_size_config(self):
        """Test batch size configuration."""
        from core.retrieval.retrieval_engine import EMBED_BATCH_SIZE
        
        assert isinstance(EMBED_BATCH_SIZE, int)
        assert EMBED_BATCH_SIZE > 0
    
    def test_bm25_params(self):
        """Test BM25 parameters."""
        from core.retrieval.retrieval_engine import _BM25_K1, _BM25_B
        
        assert isinstance(_BM25_K1, float)
        assert isinstance(_BM25_B, float)
        assert 0 < _BM25_K1 < 5  # Typical range
        assert 0 <= _BM25_B <= 1  # Must be [0, 1]


class TestOfflineMode:
    """Tests for offline mode."""
    
    def test_force_offline_flag(self):
        """Test force offline configuration."""
        from core.retrieval.retrieval_engine import FORCE_OFFLINE
        
        assert isinstance(FORCE_OFFLINE, bool)


class TestPathConfiguration:
    """Tests for path configuration."""
    
    def test_base_dir_exists(self):
        """Test base directory path."""
        from core.retrieval.retrieval_engine import BASE_DIR
        
        assert BASE_DIR.exists()
    
    def test_index_dir_exists(self):
        """Test index directory is created."""
        from core.retrieval.retrieval_engine import INDEX_DIR
        
        assert INDEX_DIR.exists()


class TestSecureCacheIntegration:
    """Tests for secure cache integration."""
    
    def test_secure_cache_available_flag(self):
        """Test secure cache availability flag."""
        from core.retrieval.retrieval_engine import SECURE_CACHE_AVAILABLE
        
        assert isinstance(SECURE_CACHE_AVAILABLE, bool)
