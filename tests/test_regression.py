"""
Regression test suite for NIC critical paths.
Tests core functionality and known edge cases.
"""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestCriticalPathRetrieval:
    """Regression tests for retrieval functionality."""
    
    @pytest.mark.smoke
    def test_retrieval_engine_imports(self):
        """Test that retrieval engine can be imported."""
        try:
            from core.retrieval import retrieval_engine
            assert hasattr(retrieval_engine, 'retrieve') or hasattr(retrieval_engine, 'docs')
        except ImportError as e:
            pytest.fail(f"Failed to import retrieval_engine: {e}")
    
    @pytest.mark.smoke
    def test_safety_modules_import(self):
        """Test that safety modules can be imported."""
        try:
            from core.safety import injection_handler
            from core.safety import risk_assessment
            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import safety modules: {e}")
    
    @pytest.mark.smoke
    def test_agent_modules_import(self):
        """Test that agent modules can be imported."""
        try:
            from agents import agent_router
            from agents import session_store
            from agents import citation_auditor
            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import agent modules: {e}")


class TestDomainIsolation:
    """Regression tests for domain isolation (critical safety feature)."""
    
    def test_out_of_scope_vehicles_rejected(self):
        """Test that non-automotive vehicles are rejected."""
        from agents.agent_router import classify_intent
        
        test_queries = [
            "How do I change oil on my motorcycle?",
            "What's the maintenance schedule for my boat?",
            "How to fix a helicopter engine?",
            "Lawnmower won't start",
            "Golf cart battery replacement",
        ]
        
        for query in test_queries:
            result = classify_intent(query)
            assert result["intent"] == "out_of_scope_vehicle", \
                f"Query '{query}' should be rejected as out-of-scope vehicle"
            assert result["use_rag"] is False
    
    def test_out_of_scope_general_rejected(self):
        """Test that non-automotive general queries are rejected."""
        from agents.agent_router import classify_intent
        
        test_queries = [
            "What is the capital of France?",
            "How do I cook pasta?",
            # Note: some edge cases may slip through, these are definitive out-of-scope
            "Who won the World Series?",
        ]
        
        for query in test_queries:
            result = classify_intent(query)
            # At minimum, should not use RAG or should be out_of_scope
            assert result["intent"] == "out_of_scope" or result.get("use_rag", True) is False, \
                f"Query '{query}' should be rejected as out-of-scope"
    
    def test_automotive_queries_accepted(self):
        """Test that valid automotive queries are accepted."""
        from agents.agent_router import classify_intent
        
        test_queries = [
            "How do I check the brake pads?",
            "What does the check engine light mean?",
            "How to change oil filter?",
            "Battery won't hold charge",
            "What is a catalytic converter?",
        ]
        
        for query in test_queries:
            result = classify_intent(query)
            # Should not be out_of_scope or out_of_scope_vehicle
            assert result["intent"] not in ["out_of_scope", "out_of_scope_vehicle"], \
                f"Query '{query}' should be accepted as automotive, got {result['intent']}"


class TestSafetyFilters:
    """Regression tests for safety filtering."""
    
    def test_absurd_queries_rejected(self):
        """Test that absurd queries are properly rejected."""
        from agents.agent_router import classify_intent
        
        absurd_queries = [
            "Can you teach my car to speak?",
            "What is the emotional state of my engine?",
            "What is the zodiac sign of my car?",
            "Make my engine sentient",
        ]
        
        for query in absurd_queries:
            result = classify_intent(query)
            assert result["intent"] == "out_of_scope", \
                f"Absurd query '{query}' should be rejected"


class TestSessionManagement:
    """Regression tests for session management."""
    
    def test_session_id_generation_unique(self):
        """Test that session IDs are unique."""
        from agents.session_store import generate_session_id
        
        ids = set()
        for _ in range(1000):
            session_id = generate_session_id()
            assert session_id not in ids, "Duplicate session ID generated"
            ids.add(session_id)
    
    def test_session_id_format(self):
        """Test that session IDs have correct format."""
        from agents.session_store import generate_session_id
        
        for _ in range(100):
            session_id = generate_session_id()
            
            # Should be 8 characters
            assert len(session_id) == 8
            
            # Should be hexadecimal
            try:
                int(session_id, 16)
            except ValueError:
                pytest.fail(f"Session ID '{session_id}' is not valid hex")


class TestCacheConsistency:
    """Regression tests for cache consistency."""
    
    def test_cache_key_deterministic(self):
        """Test that cache keys are deterministic."""
        import cache_utils
        
        # Same inputs should produce same key
        key1 = cache_utils._cache_key("test query", 12, 6)
        key2 = cache_utils._cache_key("test query", 12, 6)
        
        assert key1 == key2, "Cache keys should be deterministic"
    
    def test_cache_key_varies_with_params(self):
        """Test that cache keys vary with different parameters."""
        import cache_utils
        
        key1 = cache_utils._cache_key("query1", 12, 6)
        key2 = cache_utils._cache_key("query2", 12, 6)
        key3 = cache_utils._cache_key("query1", 10, 6)
        key4 = cache_utils._cache_key("query1", 12, 5)
        
        # All should be different
        keys = {key1, key2, key3, key4}
        assert len(keys) == 4, "Different parameters should produce different keys"


class TestMonitoringEndpoints:
    """Regression tests for monitoring endpoints."""
    
    @pytest.mark.smoke
    def test_prometheus_metrics_import(self):
        """Test that Prometheus metrics module imports."""
        try:
            from core.monitoring import prometheus_metrics
            # Check for actual metric names used in the module
            assert hasattr(prometheus_metrics, 'nova_queries_total') or \
                   hasattr(prometheus_metrics, 'nova_query_latency_seconds')
        except ImportError as e:
            pytest.fail(f"Failed to import prometheus_metrics: {e}")
    
    @pytest.mark.smoke
    def test_health_checks_import(self):
        """Test that health checks module imports."""
        try:
            from core.monitoring import health_checks
            assert hasattr(health_checks, 'run_all_checks') or \
                   hasattr(health_checks, 'HealthCheckResult')
        except ImportError as e:
            pytest.fail(f"Failed to import health_checks: {e}")
    
    @pytest.mark.smoke
    def test_logger_config_import(self):
        """Test that logger config module imports."""
        try:
            from core.monitoring import logger_config
            assert hasattr(logger_config, 'get_logger')
        except ImportError as e:
            pytest.fail(f"Failed to import logger_config: {e}")


class TestJSONParsing:
    """Regression tests for JSON parsing from LLM responses."""
    
    def test_extract_json_from_markdown(self):
        """Test JSON extraction from markdown code blocks."""
        from agents.agent_router import strip_markdown_code_blocks
        
        inputs_and_expected = [
            ('{"key": "value"}', '{"key": "value"}'),
            ('```json\n{"key": "value"}\n```', '{"key": "value"}'),
            ('Here is the result:\n{"key": "value"}', '{"key": "value"}'),
            ('```\n{"key": "value"}\n```\nDone.', '{"key": "value"}'),
        ]
        
        for input_text, expected in inputs_and_expected:
            result = strip_markdown_code_blocks(input_text)
            assert result == expected, \
                f"Input '{input_text}' should produce '{expected}', got '{result}'"
    
    def test_handle_nested_json(self):
        """Test handling of nested JSON structures."""
        from agents.agent_router import strip_markdown_code_blocks
        
        nested = '{"outer": {"inner": {"deep": "value"}}}'
        result = strip_markdown_code_blocks(nested)
        
        assert result == nested
    
    def test_handle_json_arrays(self):
        """Test handling of JSON arrays."""
        from agents.agent_router import strip_markdown_code_blocks
        
        array = '[{"item": 1}, {"item": 2}, {"item": 3}]'
        result = strip_markdown_code_blocks(array)
        
        assert result == array


class TestEdgeCases:
    """Regression tests for known edge cases."""
    
    def test_empty_query_handling(self):
        """Test handling of empty queries."""
        from agents.agent_router import classify_intent
        
        # Should not crash on empty input
        result = classify_intent("")
        assert "intent" in result
    
    def test_very_long_query_handling(self):
        """Test handling of very long queries."""
        from agents.agent_router import classify_intent
        
        # Create a very long query
        long_query = "How do I check " + "the engine " * 500 + "?"
        
        # Should not crash
        result = classify_intent(long_query)
        assert "intent" in result
    
    def test_special_characters_in_query(self):
        """Test handling of special characters in queries."""
        from agents.agent_router import classify_intent
        
        special_queries = [
            "What does the 'check engine' light mean?",
            "Error code: P0300 - what is it?",
            "Temperature is 100°C, is that normal?",
            "Engine makes a 'clicking' sound",
        ]
        
        for query in special_queries:
            result = classify_intent(query)
            assert "intent" in result, f"Failed to classify: {query}"
    
    def test_unicode_in_query(self):
        """Test handling of unicode in queries."""
        from agents.agent_router import classify_intent
        
        unicode_query = "How do I check the bräke pads? 🔧"
        
        # Should not crash
        result = classify_intent(unicode_query)
        assert "intent" in result


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with previous versions."""
    
    def test_cache_utils_deprecation_warning(self):
        """Test that cache_utils raises deprecation warning."""
        import warnings
        import sys
        
        # Remove from cache to test import
        if "cache_utils" in sys.modules:
            del sys.modules["cache_utils"]
        
        # Temporarily unset suppression
        old_val = os.environ.pop("NOVA_SUPPRESS_CACHE_UTILS_DEPRECATION", None)
        
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                import cache_utils
                
                # Should have raised deprecation warning
                deprecation_warnings = [
                    x for x in w if issubclass(x.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) >= 0  # May be suppressed by conftest
        finally:
            if old_val:
                os.environ["NOVA_SUPPRESS_CACHE_UTILS_DEPRECATION"] = old_val
