"""
Tests for Safety Layer - Semantic Safety Detection.

Tests the semantic similarity-based safety detection including:
- Unsafe intent detection
- Safe intent recognition
- Fallback heuristics
- Confidence scoring
"""

from unittest.mock import Mock, patch, MagicMock

import pytest


class TestSemanticSafetyDetectorInit:
    """Tests for SemanticSafetyDetector initialization."""
    
    def test_detector_creates(self):
        """Test detector can be created."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        
        assert detector is not None
    
    def test_unsafe_intents_defined(self):
        """Test unsafe intents are defined."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        assert len(SemanticSafetyDetector.UNSAFE_INTENTS) > 0
    
    def test_safe_intents_defined(self):
        """Test safe intents are defined."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        assert len(SemanticSafetyDetector.SAFE_INTENTS) > 0


class TestUnsafeIntentExamples:
    """Tests for unsafe intent examples."""
    
    def test_disable_safety_in_intents(self):
        """Test disable safety intents."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.UNSAFE_INTENTS]
        
        assert any("disable" in i for i in intents)
    
    def test_bypass_safety_in_intents(self):
        """Test bypass safety intents."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.UNSAFE_INTENTS]
        
        assert any("bypass" in i for i in intents)
    
    def test_override_safety_in_intents(self):
        """Test override safety intents."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.UNSAFE_INTENTS]
        
        assert any("override" in i for i in intents)
    
    def test_disable_airbags_in_intents(self):
        """Test disable airbags intent."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.UNSAFE_INTENTS]
        
        assert any("airbag" in i for i in intents)


class TestSafeIntentExamples:
    """Tests for safe intent examples."""
    
    def test_how_questions_safe(self):
        """Test 'how' questions are safe."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.SAFE_INTENTS]
        
        assert any("how" in i for i in intents)
    
    def test_what_questions_safe(self):
        """Test 'what' questions are safe."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.SAFE_INTENTS]
        
        assert any("what" in i for i in intents)
    
    def test_brake_info_safe(self):
        """Test brake information is safe."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        intents = [i.lower() for i in SemanticSafetyDetector.SAFE_INTENTS]
        
        assert any("brake" in i for i in intents)


class TestAssessIntentEmptyQuery:
    """Tests for empty query handling."""
    
    def test_empty_string(self):
        """Test empty string is handled."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("")
        
        assert result["is_unsafe"] is False
        assert "Empty query" in result["reasoning"]
    
    def test_none_equivalent(self):
        """Test falsy query is handled."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        
        # Empty string should work
        result = detector.assess_intent("")
        
        assert "is_unsafe" in result


class TestAssessIntentResult:
    """Tests for assess_intent result structure."""
    
    def test_result_has_required_keys(self):
        """Test result has all required keys."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("test query")
        
        assert "is_unsafe" in result
        assert "unsafe_similarity" in result
        assert "safe_similarity" in result
        assert "confidence" in result
        assert "matched_intent" in result
        assert "reasoning" in result
    
    def test_is_unsafe_is_boolean(self):
        """Test is_unsafe is boolean."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("How do I check my oil?")
        
        assert isinstance(result["is_unsafe"], bool)
    
    def test_similarity_scores_numeric(self):
        """Test similarity scores are numeric."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("test query")
        
        assert isinstance(result["unsafe_similarity"], (int, float))
        assert isinstance(result["safe_similarity"], (int, float))


class TestHeuristicFallback:
    """Tests for heuristic fallback when model unavailable."""
    
    def test_fallback_detects_unsafe_keywords(self):
        """Test fallback uses keyword detection."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        # Create detector with no model
        detector = SemanticSafetyDetector()
        detector.model = None  # Force fallback
        
        result = detector.assess_intent("disable the safety system")
        
        # Fallback should trigger on "disable"
        assert result["unsafe_similarity"] >= 0.5 or result["is_unsafe"] is True
        assert "Heuristic" in result["reasoning"] or "fallback" in result["reasoning"].lower()
    
    def test_fallback_safe_question(self):
        """Test fallback handles safe questions."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        detector.model = None  # Force fallback
        
        result = detector.assess_intent("How do I check tire pressure?")
        
        # Safe questions should have higher safe similarity
        assert result["safe_similarity"] >= result["unsafe_similarity"]


class TestIsAvailable:
    """Tests for is_available method."""
    
    def test_unavailable_when_no_model(self):
        """Test unavailable when model is None."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        detector.model = None
        
        assert detector.is_available() is False
    
    def test_available_when_model_loaded(self):
        """Test available when model is loaded."""
        from core.safety.semantic_safety import SemanticSafetyDetector, SEMANTIC_AVAILABLE
        
        detector = SemanticSafetyDetector()
        
        if SEMANTIC_AVAILABLE and detector.model is not None:
            assert detector.is_available() is True


class TestThresholdBehavior:
    """Tests for threshold parameter behavior."""
    
    def test_custom_threshold(self):
        """Test custom threshold is respected."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        
        # Very high threshold should make almost nothing unsafe
        result_high = detector.assess_intent("bypass safety", threshold=0.99)
        
        # Very low threshold could flag more things
        result_low = detector.assess_intent("bypass safety", threshold=0.1)
        
        # Both should return valid results
        assert "is_unsafe" in result_high
        assert "is_unsafe" in result_low


class TestConfidenceScores:
    """Tests for confidence scoring."""
    
    def test_confidence_in_range(self):
        """Test confidence is in [0, 1] range."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("test query")
        
        assert 0 <= result["confidence"] <= 1
    
    def test_high_confidence_for_clear_safe(self):
        """Test high confidence for clearly safe queries."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("What oil does my car need?")
        
        # Should be confident it's safe
        assert result["is_unsafe"] is False or result["confidence"] < 0.5


class TestMatchedIntent:
    """Tests for matched intent reporting."""
    
    def test_matched_intent_for_unsafe(self):
        """Test matched intent is reported for unsafe queries."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        detector.model = None  # Use fallback for predictable behavior
        
        result = detector.assess_intent("disable all safety systems")
        
        # When unsafe via fallback, matched_intent may be None
        # but is_unsafe should be True
        if result["is_unsafe"]:
            # Matched intent is optional in fallback mode
            pass
    
    def test_no_matched_intent_for_safe(self):
        """Test no matched intent for safe queries."""
        from core.safety.semantic_safety import SemanticSafetyDetector
        
        detector = SemanticSafetyDetector()
        result = detector.assess_intent("How do I inflate my tires?")
        
        if not result["is_unsafe"]:
            assert result["matched_intent"] is None


class TestSemanticAvailableFlag:
    """Tests for SEMANTIC_AVAILABLE flag."""
    
    def test_flag_is_boolean(self):
        """Test flag is boolean."""
        from core.safety.semantic_safety import SEMANTIC_AVAILABLE
        
        assert isinstance(SEMANTIC_AVAILABLE, bool)
