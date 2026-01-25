"""
Tests for Agents - Troubleshoot Agent.

Tests the troubleshooting agent including:
- Prompt construction
- Cause analysis
- Diagram integration
- JSON schema compliance
"""

from unittest.mock import Mock, MagicMock

import pytest

from agents.troubleshoot_agent import run_troubleshoot


class TestRunTroubleshootBasic:
    """Basic tests for run_troubleshoot."""
    
    def test_returns_llm_result(self):
        """Test function returns LLM result."""
        mock_llm = Mock(return_value='{"likely_causes": [], "next_steps": []}')
        
        result = run_troubleshoot("Engine won't start", [], mock_llm)
        
        mock_llm.assert_called_once()
        assert result == '{"likely_causes": [], "next_steps": []}'
    
    def test_llm_called_with_prompt(self):
        """Test LLM is called with a prompt."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Test problem", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert isinstance(call_args, str)
        assert len(call_args) > 0
    
    def test_problem_in_prompt(self):
        """Test problem is included in prompt."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("ABS light is on", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "ABS light is on" in call_args


class TestContextDocs:
    """Tests for context document handling."""
    
    def test_context_docs_included(self):
        """Test context docs are included in prompt."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "troubleshooting.pdf", "page": 42, "text": "Check sensor first"}
        ]
        
        run_troubleshoot("Sensor error", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Check sensor first" in call_args
        assert "troubleshooting.pdf" in call_args
    
    def test_page_number_included(self):
        """Test page numbers are included."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "page": 55, "text": "Content"}
        ]
        
        run_troubleshoot("Problem?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "55" in call_args or "pg." in call_args
    
    def test_empty_context_handled(self):
        """Test empty context is handled."""
        mock_llm = Mock(return_value='{}')
        
        result = run_troubleshoot("Problem?", [], mock_llm)
        
        assert result is not None
    
    def test_snippet_fallback(self):
        """Test snippet used when text missing."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "snippet": "Snippet content"}
        ]
        
        run_troubleshoot("Problem?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Snippet content" in call_args


class TestDiagramIntegration:
    """Tests for diagram reference integration."""
    
    def test_diagrams_included(self):
        """Test diagrams are included in prompt."""
        mock_llm = Mock(return_value='{}')
        diagrams = [
            {"pdf_name": "wiring.pdf", "page": 10, "caption_guess": "ABS Wiring Diagram"}
        ]
        
        run_troubleshoot("Problem?", [], mock_llm, diagrams=diagrams)
        
        call_args = mock_llm.call_args[0][0]
        assert "wiring.pdf" in call_args or "DIAGRAM" in call_args.upper()
    
    def test_diagram_caption_included(self):
        """Test diagram captions are included."""
        mock_llm = Mock(return_value='{}')
        diagrams = [
            {"pdf_name": "manual.pdf", "page": 5, "caption_guess": "Brake System Overview"}
        ]
        
        run_troubleshoot("Problem?", [], mock_llm, diagrams=diagrams)
        
        call_args = mock_llm.call_args[0][0]
        assert "Brake System" in call_args or "Overview" in call_args
    
    def test_no_diagrams_no_crash(self):
        """Test no diagrams doesn't crash."""
        mock_llm = Mock(return_value='{}')
        
        result = run_troubleshoot("Problem?", [], mock_llm, diagrams=[])
        
        assert result is not None
    
    def test_empty_diagrams_list(self):
        """Test empty diagrams list is handled."""
        mock_llm = Mock(return_value='{}')
        
        result = run_troubleshoot("Problem?", [], mock_llm, diagrams=[])
        
        assert result is not None


class TestPromptInstructions:
    """Tests for prompt instructions."""
    
    def test_json_only_instruction(self):
        """Test prompt asks for JSON only."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "JSON" in call_args
    
    def test_no_prose_instruction(self):
        """Test prompt asks for no prose."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "no prose" in call_args.lower() or "no markdown" in call_args.lower()
    
    def test_schema_defined(self):
        """Test prompt defines schema."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "likely_causes" in call_args
        assert "next_steps" in call_args
        assert "confidence" in call_args


class TestSchemaCompliance:
    """Tests for expected schema fields."""
    
    def test_schema_has_likely_causes(self):
        """Test schema includes likely_causes."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"likely_causes"' in call_args
    
    def test_schema_has_rationale(self):
        """Test schema includes rationale."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"rationale"' in call_args
    
    def test_schema_has_next_steps(self):
        """Test schema includes next_steps."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"next_steps"' in call_args
    
    def test_schema_has_verification(self):
        """Test schema includes verification."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"verification"' in call_args
    
    def test_schema_has_fallback(self):
        """Test schema includes fallback."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"fallback"' in call_args
    
    def test_schema_has_confidence(self):
        """Test schema includes confidence."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"confidence"' in call_args
    
    def test_schema_has_reference_diagrams(self):
        """Test schema includes reference_diagrams."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"reference_diagrams"' in call_args


class TestContextFormatting:
    """Tests for context document formatting."""
    
    def test_source_header_format(self):
        """Test source header is formatted correctly."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "test.pdf", "page": 10, "text": "Content"}
        ]
        
        run_troubleshoot("Problem?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "test.pdf" in call_args
        assert "[Source:" in call_args or "Source" in call_args
    
    def test_docs_separated(self):
        """Test documents are separated."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "doc1.pdf", "text": "First"},
            {"source": "doc2.pdf", "text": "Second"},
        ]
        
        run_troubleshoot("Problem?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "---" in call_args  # Separator


class TestGroundingInstructions:
    """Tests for grounding in context instructions."""
    
    def test_context_grounding_required(self):
        """Test prompt requires grounding in context."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "context" in call_args.lower()
    
    def test_exact_terminology_required(self):
        """Test prompt asks for exact terminology."""
        mock_llm = Mock(return_value='{}')
        
        run_troubleshoot("Problem?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "terminology" in call_args.lower() or "exact" in call_args.lower()


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_missing_source_key(self):
        """Test handling of missing source key."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"text": "Content without source"}
        ]
        
        result = run_troubleshoot("Problem?", context_docs, mock_llm)
        
        assert result is not None
    
    def test_missing_page_key(self):
        """Test handling of missing page key."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "text": "Content"}
        ]
        
        result = run_troubleshoot("Problem?", context_docs, mock_llm)
        
        assert result is not None
    
    def test_none_page(self):
        """Test handling of None page."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "page": None, "text": "Content"}
        ]
        
        result = run_troubleshoot("Problem?", context_docs, mock_llm)
        
        assert result is not None
    
    def test_empty_text_doc(self):
        """Test handling of empty text."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "empty.pdf", "text": ""}
        ]
        
        result = run_troubleshoot("Problem?", context_docs, mock_llm)
        
        assert result is not None
