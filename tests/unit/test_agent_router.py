"""
Unit tests for agents/agent_router.py
Tests intent classification, domain detection, and routing logic.
"""
import pytest
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestStripMarkdownCodeBlocks:
    """Tests for JSON extraction from LLM responses."""
    
    def test_plain_json_object(self):
        """Test extraction of plain JSON object."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '{"key": "value"}'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"key": "value"}'
    
    def test_json_with_markdown_wrapper(self):
        """Test extraction of JSON wrapped in markdown code blocks."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '```json\n{"key": "value"}\n```'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"key": "value"}'
    
    def test_json_with_preamble(self):
        """Test extraction of JSON with text before it."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = 'Here is the JSON:\n{"key": "value"}'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"key": "value"}'
    
    def test_json_with_postamble(self):
        """Test extraction of JSON with text after it."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '{"key": "value"}\nThat was the response.'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"key": "value"}'
    
    def test_nested_json(self):
        """Test extraction of nested JSON objects."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '{"outer": {"inner": "value"}}'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"outer": {"inner": "value"}}'
    
    def test_json_array(self):
        """Test extraction of JSON arrays."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '[{"item": 1}, {"item": 2}]'
        result = strip_markdown_code_blocks(input_text)
        assert result == '[{"item": 1}, {"item": 2}]'
    
    def test_json_with_escaped_quotes(self):
        """Test handling of escaped quotes in JSON."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = '{"message": "He said \\"hello\\""}'
        result = strip_markdown_code_blocks(input_text)
        assert result == '{"message": "He said \\"hello\\""}'
    
    def test_non_json_text(self):
        """Test handling of text without JSON."""
        from agents.agent_router import strip_markdown_code_blocks
        
        input_text = 'Just some regular text'
        result = strip_markdown_code_blocks(input_text)
        assert result == 'Just some regular text'
    
    def test_non_string_input(self):
        """Test handling of non-string input."""
        from agents.agent_router import strip_markdown_code_blocks
        
        result = strip_markdown_code_blocks(None)  # type: ignore[arg-type]
        assert result is None
        
        result = strip_markdown_code_blocks(123)  # type: ignore[arg-type]
        assert result == 123


class TestIntentClassification:
    """Tests for classify_intent function."""
    
    def test_out_of_scope_query(self):
        """Test that out-of-scope queries are properly classified."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("What is the capital of France?")
        
        assert result["intent"] == "out_of_scope"
        assert result["use_rag"] is False
        assert result["agent"] == "refusal"
    
    def test_out_of_scope_vehicle_type(self):
        """Test that non-automotive vehicles are rejected."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("How do I change the oil on my motorcycle?")
        
        assert result["intent"] == "out_of_scope_vehicle"
        assert result["agent"] == "refusal"
        assert "motorcycle" in result.get("detected_vehicle", "").lower()
    
    def test_automotive_context_overrides_out_of_scope(self):
        """Test that automotive context prevents out-of-scope classification."""
        from agents.agent_router import classify_intent
        
        # "Computer" normally out-of-scope but "engine computer" is automotive
        result = classify_intent("What does the engine computer do?")
        
        # Should NOT be out_of_scope due to "engine" context
        assert result["intent"] != "out_of_scope" or result.get("use_rag", True)
    
    def test_absurd_query_rejection(self):
        """Test that absurd queries are rejected."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("Can you teach my car to speak?")
        
        assert result["intent"] == "out_of_scope"
        assert result["agent"] == "refusal"
    
    def test_diagnostic_intent(self):
        """Test classification of diagnostic queries."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("What does error code P0300 mean?")
        
        # Accept various diagnostic-related intents
        assert result["intent"] in ["diagnostic", "vehicle_diagnostic", "definition", "other"]
        assert result["use_rag"] is True
    
    def test_maintenance_intent(self):
        """Test classification of maintenance queries."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("How do I change the oil filter?")
        
        assert result["use_rag"] is True
        assert result["intent"] in ["maintenance_procedure", "other"]
    
    def test_greeting_intent(self):
        """Test classification of greetings."""
        from agents.agent_router import classify_intent
        
        result = classify_intent("Hello, how are you?")
        
        # Greetings might be general_chat or out_of_scope
        assert result["intent"] in ["general_chat", "out_of_scope", "other"]


class TestUserQuestionExtraction:
    """Tests for _extract_user_question_from_prompt function."""
    
    def test_standard_prompt_extraction(self):
        """Test extraction from standard backend prompt format."""
        from agents.agent_router import _extract_user_question_from_prompt
        
        prompt = """Context from manuals:
Some context here...

Question:
How do I check the brake pads?

Answer format:
Please provide a detailed answer."""
        
        result = _extract_user_question_from_prompt(prompt)
        assert "brake pads" in result.lower()
        assert "Answer format" not in result
    
    def test_troubleshoot_prompt_extraction(self):
        """Test extraction from troubleshoot agent prompt format."""
        from agents.agent_router import _extract_user_question_from_prompt
        
        prompt = """Previous findings...

Problem / Update:
The engine is making a clicking noise.

Additional context..."""
        
        result = _extract_user_question_from_prompt(prompt)
        assert "clicking noise" in result.lower()
    
    def test_simple_question(self):
        """Test pass-through of simple questions."""
        from agents.agent_router import _extract_user_question_from_prompt
        
        prompt = "How do I check tire pressure?"
        
        result = _extract_user_question_from_prompt(prompt)
        assert result == prompt


class TestCitationAuditFlags:
    """Tests for citation audit configuration functions."""
    
    def test_citation_audit_enabled_default(self, monkeypatch):
        """Test that citation audit is enabled by default."""
        monkeypatch.delenv("NOVA_CITATION_AUDIT", raising=False)
        
        # Need to reload to pick up env change
        import importlib
        import agents.agent_router as ar
        importlib.reload(ar)
        
        assert ar.citation_audit_enabled() is True
    
    def test_citation_audit_disabled(self, monkeypatch):
        """Test that citation audit can be disabled."""
        monkeypatch.setenv("NOVA_CITATION_AUDIT", "0")
        
        import importlib
        import agents.agent_router as ar
        importlib.reload(ar)
        
        assert ar.citation_audit_enabled() is False
    
    def test_citation_strict_enabled_default(self, monkeypatch):
        """Test that strict citation is enabled by default."""
        monkeypatch.delenv("NOVA_CITATION_STRICT", raising=False)
        
        import importlib
        import agents.agent_router as ar
        importlib.reload(ar)
        
        assert ar.citation_strict_enabled() is True


class TestEnvFlag:
    """Tests for _env_flag helper function."""
    
    def test_env_flag_true(self, monkeypatch):
        """Test that _env_flag returns True when set to '1'."""
        monkeypatch.setenv("TEST_FLAG", "1")
        
        from agents.agent_router import _env_flag
        
        assert _env_flag("TEST_FLAG", "0") is True
    
    def test_env_flag_false(self, monkeypatch):
        """Test that _env_flag returns False when set to '0'."""
        monkeypatch.setenv("TEST_FLAG", "0")
        
        from agents.agent_router import _env_flag
        
        assert _env_flag("TEST_FLAG", "1") is False
    
    def test_env_flag_default(self, monkeypatch):
        """Test that _env_flag uses default when not set."""
        monkeypatch.delenv("NONEXISTENT_FLAG", raising=False)
        
        from agents.agent_router import _env_flag
        
        assert _env_flag("NONEXISTENT_FLAG", "1") is True
        assert _env_flag("NONEXISTENT_FLAG", "0") is False
