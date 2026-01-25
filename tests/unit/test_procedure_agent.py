"""
Tests for Agents - Procedure Agent.

Tests the procedure extraction agent including:
- Prompt construction
- Step extraction
- Citation requirements
- JSON schema compliance
"""

from unittest.mock import Mock, MagicMock

import pytest

from agents.procedure_agent import run_procedure


class TestRunProcedureBasic:
    """Basic tests for run_procedure."""
    
    def test_returns_llm_result(self):
        """Test function returns LLM result."""
        mock_llm = Mock(return_value='{"steps": [], "sources": []}')
        
        result = run_procedure("How do I change oil?", [], mock_llm)
        
        mock_llm.assert_called_once()
        assert result == '{"steps": [], "sources": []}'
    
    def test_llm_called_with_prompt(self):
        """Test LLM is called with a prompt."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Test question", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert isinstance(call_args, str)
        assert len(call_args) > 0
    
    def test_question_in_prompt(self):
        """Test question is included in prompt."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("How do I replace the air filter?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "How do I replace the air filter?" in call_args


class TestContextDocs:
    """Tests for context document handling."""
    
    def test_context_docs_included(self):
        """Test context docs are included in prompt."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "text": "Step 1: Remove old filter"}
        ]
        
        run_procedure("How do I replace filter?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Step 1: Remove old filter" in call_args
        assert "manual.pdf" in call_args
    
    def test_multiple_context_docs(self):
        """Test multiple context docs are included."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "part1.pdf", "text": "Content 1"},
            {"source": "part2.pdf", "text": "Content 2"},
        ]
        
        run_procedure("Question?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Content 1" in call_args
        assert "Content 2" in call_args
    
    def test_empty_context_handled(self):
        """Test empty context is handled."""
        mock_llm = Mock(return_value='{}')
        
        result = run_procedure("Question?", [], mock_llm)
        
        # Should not crash
        assert result is not None
    
    def test_snippet_fallback(self):
        """Test snippet used when text missing."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "manual.pdf", "snippet": "Snippet content here"}
        ]
        
        run_procedure("Question?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Snippet content here" in call_args


class TestPromptInstructions:
    """Tests for prompt instructions."""
    
    def test_json_only_instruction(self):
        """Test prompt asks for JSON only."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "JSON" in call_args
    
    def test_no_prose_instruction(self):
        """Test prompt asks for no prose."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "no prose" in call_args.lower() or "no markdown" in call_args.lower()
    
    def test_schema_defined(self):
        """Test prompt defines schema."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "steps" in call_args
        assert "why" in call_args
        assert "verification" in call_args
        assert "risks" in call_args
        assert "sources" in call_args
    
    def test_citation_requirement(self):
        """Test prompt requires citations."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "citation" in call_args.lower() or "source" in call_args.lower()
    
    def test_pdf_only_instruction(self):
        """Test prompt emphasizes PDF-only content."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "Context" in call_args or "PDF" in call_args


class TestSchemaCompliance:
    """Tests for expected schema fields."""
    
    def test_schema_has_steps(self):
        """Test schema includes steps."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"steps"' in call_args
    
    def test_schema_has_why(self):
        """Test schema includes why."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"why"' in call_args
    
    def test_schema_has_verification(self):
        """Test schema includes verification."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"verification"' in call_args
    
    def test_schema_has_notes(self):
        """Test schema includes notes."""
        mock_llm = Mock(return_value='{}')
        
        run_procedure("Question?", [], mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert '"notes"' in call_args


class TestContextFormatting:
    """Tests for context document formatting."""
    
    def test_source_header_format(self):
        """Test source header is formatted correctly."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "test.pdf", "text": "Content"}
        ]
        
        run_procedure("Question?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "[Source: test.pdf]" in call_args
    
    def test_docs_separated(self):
        """Test documents are separated."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "doc1.pdf", "text": "First"},
            {"source": "doc2.pdf", "text": "Second"},
        ]
        
        run_procedure("Question?", context_docs, mock_llm)
        
        call_args = mock_llm.call_args[0][0]
        assert "---" in call_args  # Separator


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_missing_source_key(self):
        """Test handling of missing source key."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"text": "Content without source"}
        ]
        
        # Should not crash
        result = run_procedure("Question?", context_docs, mock_llm)
        
        assert result is not None
    
    def test_empty_text_doc(self):
        """Test handling of empty text."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": "empty.pdf", "text": ""}
        ]
        
        result = run_procedure("Question?", context_docs, mock_llm)
        
        assert result is not None
    
    def test_none_values_handled(self):
        """Test None values don't crash."""
        mock_llm = Mock(return_value='{}')
        context_docs = [
            {"source": None, "text": None}
        ]
        
        result = run_procedure("Question?", context_docs, mock_llm)
        
        assert result is not None
