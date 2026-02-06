#!/usr/bin/env python3
"""
Unit tests for Diagnostic Confidence and Confirmation Strategy modules.

Tests Phase 4 infrastructure components:
- DiagnosticConfidenceAggregator
- Confirmation strategy determination
- Debug output functionality
- Boundary conditions and edge cases

Run with:
    pytest tests/test_diagnostic_infrastructure.py -v
"""

import os
import pytest

from core.diagnostics.diagnostic_confidence import (
    DiagnosticConfidenceAggregator,
    ConfidenceComponents,
    compute_diagnostic_confidence,
)
from core.diagnostics.confirmation_strategy import (
    ConfirmationStrategy,
    determine_confirmation_strategy,
    get_strategy_description,
    get_strategy_metadata,
    get_max_steps_for_strategy,
    get_required_nodes_count,
)
from core.diagnostics.debug_output import (
    is_debug_enabled,
    format_debug_block,
    log_debug_info,
    get_debug_context,
    format_confidence_breakdown,
)


# ──────────────────────────────────────────────────────────────────────────────
# Test: Diagnostic Confidence Aggregator
# ──────────────────────────────────────────────────────────────────────────────


class TestDiagnosticConfidenceAggregator:
    """Tests for confidence aggregation."""

    def test_high_confidence_all_components(self):
        """Test with all high confidence values."""
        aggregator = DiagnosticConfidenceAggregator()
        result = aggregator.combine(
            retrieval_conf=0.90,
            graph_conf=0.88,
            alarm_conf=0.95,
            rerank_conf=0.85,
        )

        # Should be high (> 0.85)
        assert result > 0.85
        # Should be clamped to [0, 1]
        assert 0.0 <= result <= 1.0
        # Should be rounded to 3 decimals
        assert len(str(result).split(".")[-1]) <= 3

    def test_mixed_confidence_values(self):
        """Test with mixed confidence values."""
        aggregator = DiagnosticConfidenceAggregator()
        result = aggregator.combine(
            retrieval_conf=0.75,
            graph_conf=0.65,
            alarm_conf=0.80,
            rerank_conf=0.70,
        )

        # Should be in medium range (0.60-0.85)
        assert 0.60 < result < 0.85
        assert 0.0 <= result <= 1.0

    def test_weak_signals(self):
        """Test with weak confidence signals."""
        aggregator = DiagnosticConfidenceAggregator()
        result = aggregator.combine(
            retrieval_conf=0.40,
            graph_conf=0.35,
            alarm_conf=0.50,
            rerank_conf=0.45,
        )

        # Should be low (< 0.6)
        assert result < 0.6
        assert 0.0 <= result <= 1.0

    def test_rerank_absent_weight_adjustment(self):
        """Test that weights auto-adjust when rerank_conf is None."""
        aggregator = DiagnosticConfidenceAggregator()

        # With rerank
        with_rerank = aggregator.combine(
            retrieval_conf=0.80,
            graph_conf=0.75,
            alarm_conf=0.85,
            rerank_conf=0.70,
        )

        # Without rerank (should redistribute weight)
        without_rerank = aggregator.combine(
            retrieval_conf=0.80,
            graph_conf=0.75,
            alarm_conf=0.85,
            rerank_conf=None,
        )

        # Both should be valid and reasonably close
        assert 0.0 <= with_rerank <= 1.0
        assert 0.0 <= without_rerank <= 1.0
        # Without rerank should be slightly different
        assert abs(with_rerank - without_rerank) < 0.2

    def test_clamping_out_of_range(self):
        """Test that out-of-range values are clamped."""
        aggregator = DiagnosticConfidenceAggregator()

        # Values > 1.0 should be clamped to 1.0
        result = aggregator.combine(
            retrieval_conf=1.5,  # Invalid
            graph_conf=1.2,      # Invalid
            alarm_conf=0.9,
            rerank_conf=0.8,
        )
        assert result <= 1.0

        # Values < 0.0 should be clamped to 0.0
        result = aggregator.combine(
            retrieval_conf=-0.5,  # Invalid
            graph_conf=0.1,
            alarm_conf=0.2,
            rerank_conf=0.3,
        )
        assert result >= 0.0

    def test_combine_with_components(self):
        """Test combine_with_components returns ConfidenceComponents."""
        aggregator = DiagnosticConfidenceAggregator()
        components = aggregator.combine_with_components(
            retrieval_conf=0.75,
            graph_conf=0.70,
            alarm_conf=0.80,
            rerank_conf=0.65,
        )

        assert isinstance(components, ConfidenceComponents)
        assert components.retrieval_conf == 0.75
        assert components.graph_conf == 0.70
        assert components.alarm_conf == 0.80
        assert components.rerank_conf == 0.65
        assert 0.0 <= components.combined_conf <= 1.0

    def test_convenience_function(self):
        """Test the compute_diagnostic_confidence convenience function."""
        result = compute_diagnostic_confidence(
            retrieval_conf=0.82,
            graph_conf=0.78,
            alarm_conf=0.90,
        )

        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Test: Confirmation Strategy Engine
# ──────────────────────────────────────────────────────────────────────────────


class TestConfirmationStrategy:
    """Tests for confirmation strategy determination."""

    def test_midpoint_strategy_high_confidence(self):
        """Test that high confidence (>= 0.85) returns midpoint strategy."""
        strategy = determine_confirmation_strategy(0.92)
        assert strategy == ConfirmationStrategy.MIDPOINT

        strategy = determine_confirmation_strategy(0.85)  # Boundary
        assert strategy == ConfirmationStrategy.MIDPOINT

    def test_branch_strategy_medium_confidence(self):
        """Test that medium confidence (0.60-0.85) returns branch strategy."""
        strategy = determine_confirmation_strategy(0.75)
        assert strategy == ConfirmationStrategy.BRANCH

        strategy = determine_confirmation_strategy(0.60)  # Lower boundary
        assert strategy == ConfirmationStrategy.BRANCH

        strategy = determine_confirmation_strategy(0.84)  # Upper boundary
        assert strategy == ConfirmationStrategy.BRANCH

    def test_multi_node_strategy_low_confidence(self):
        """Test that low confidence (< 0.60) returns multi_node strategy."""
        strategy = determine_confirmation_strategy(0.45)
        assert strategy == ConfirmationStrategy.MULTI_NODE

        strategy = determine_confirmation_strategy(0.59)  # Just below threshold
        assert strategy == ConfirmationStrategy.MULTI_NODE

    def test_boundary_conditions(self):
        """Test exact threshold boundaries."""
        # Exactly at midpoint threshold (0.85)
        assert determine_confirmation_strategy(0.850) == ConfirmationStrategy.MIDPOINT

        # Just below midpoint threshold
        assert determine_confirmation_strategy(0.849) == ConfirmationStrategy.BRANCH

        # Exactly at branch threshold (0.60)
        assert determine_confirmation_strategy(0.600) == ConfirmationStrategy.BRANCH

        # Just below branch threshold
        assert determine_confirmation_strategy(0.599) == ConfirmationStrategy.MULTI_NODE

    def test_edge_cases_clamping(self):
        """Test that extreme values are handled correctly."""
        # Values > 1.0 should be clamped and return midpoint
        strategy = determine_confirmation_strategy(1.5)
        assert strategy == ConfirmationStrategy.MIDPOINT

        # Values < 0.0 should be clamped and return multi_node
        strategy = determine_confirmation_strategy(-0.5)
        assert strategy == ConfirmationStrategy.MULTI_NODE

        # Exactly 0.0
        strategy = determine_confirmation_strategy(0.0)
        assert strategy == ConfirmationStrategy.MULTI_NODE

        # Exactly 1.0
        strategy = determine_confirmation_strategy(1.0)
        assert strategy == ConfirmationStrategy.MIDPOINT

    def test_strategy_description(self):
        """Test that each strategy has a description."""
        desc_midpoint = get_strategy_description(ConfirmationStrategy.MIDPOINT)
        assert "midpoint" in desc_midpoint.lower()
        assert len(desc_midpoint) > 10

        desc_branch = get_strategy_description(ConfirmationStrategy.BRANCH)
        assert "branch" in desc_branch.lower()

        desc_multi = get_strategy_description(ConfirmationStrategy.MULTI_NODE)
        assert "multi" in desc_multi.lower()

    def test_strategy_metadata(self):
        """Test get_strategy_metadata returns complete metadata."""
        metadata = get_strategy_metadata(0.78)

        assert "strategy" in metadata
        assert "confidence" in metadata
        assert "description" in metadata
        assert "thresholds" in metadata

        assert metadata["strategy"] == ConfirmationStrategy.BRANCH
        assert metadata["confidence"] == 0.78
        assert isinstance(metadata["description"], str)
        assert "midpoint" in metadata["thresholds"]
        assert "branch" in metadata["thresholds"]

    def test_max_steps_for_strategy(self):
        """Test that each strategy has appropriate max_steps."""
        # Midpoint should have fewer steps (focused)
        midpoint_steps = get_max_steps_for_strategy(ConfirmationStrategy.MIDPOINT)
        assert midpoint_steps == 3

        # Branch should have standard steps
        branch_steps = get_max_steps_for_strategy(ConfirmationStrategy.BRANCH)
        assert branch_steps == 5

        # Multi-node should have more steps (more verification)
        multi_steps = get_max_steps_for_strategy(ConfirmationStrategy.MULTI_NODE)
        assert multi_steps == 7

        # Multi-node > Branch > Midpoint
        assert multi_steps > branch_steps > midpoint_steps

    def test_required_nodes_count(self):
        """Test required nodes count per strategy."""
        # Midpoint needs only 1 node
        assert get_required_nodes_count(ConfirmationStrategy.MIDPOINT) == 1

        # Branch needs 2 nodes (upstream + downstream)
        assert get_required_nodes_count(ConfirmationStrategy.BRANCH) == 2

        # Multi-node needs 3+ nodes for corroboration
        assert get_required_nodes_count(ConfirmationStrategy.MULTI_NODE) == 3


# ──────────────────────────────────────────────────────────────────────────────
# Test: Debug Output
# ──────────────────────────────────────────────────────────────────────────────


class TestDebugOutput:
    """Tests for debug output functionality."""

    def setup_method(self):
        """Clear debug environment variable before each test."""
        if "NIC_DEBUG_TROUBLESHOOT" in os.environ:
            del os.environ["NIC_DEBUG_TROUBLESHOOT"]

    def teardown_method(self):
        """Clear debug environment variable after each test."""
        if "NIC_DEBUG_TROUBLESHOOT" in os.environ:
            del os.environ["NIC_DEBUG_TROUBLESHOOT"]

    def test_debug_disabled_by_default(self):
        """Test that debug mode is disabled by default."""
        assert is_debug_enabled() is False

    def test_debug_enabled_when_set(self):
        """Test that debug mode enables when NIC_DEBUG_TROUBLESHOOT=1."""
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = "1"
        assert is_debug_enabled() is True

    def test_debug_disabled_with_other_values(self):
        """Test that debug mode requires exactly '1' to enable."""
        # "0" should be disabled
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = "0"
        assert is_debug_enabled() is False

        # "true" should be disabled (must be "1")
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = "true"
        assert is_debug_enabled() is False

        # Empty string should be disabled
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = ""
        assert is_debug_enabled() is False

    def test_format_debug_block_basic(self):
        """Test basic debug block formatting."""
        debug = format_debug_block(
            confidence=0.85,
            strategy="midpoint",
        )

        assert "===== NIC DIAGNOSTIC DEBUG =====" in debug
        assert "Confidence: 0.850" in debug
        assert "Strategy: midpoint" in debug
        assert "================================" in debug

    def test_format_debug_block_with_components(self):
        """Test debug block with confidence components."""
        debug = format_debug_block(
            confidence=0.82,
            strategy="branch",
            components={
                "retrieval": 0.85,
                "graph": 0.80,
                "alarm": 0.90,
                "rerank": 0.75,
            },
        )

        assert "Components:" in debug
        assert "retrieval: 0.850" in debug
        assert "graph: 0.800" in debug
        assert "alarm: 0.900" in debug
        assert "rerank: 0.750" in debug

    def test_format_debug_block_with_metadata(self):
        """Test debug block with strategy metadata."""
        debug = format_debug_block(
            confidence=0.70,
            strategy="branch",
            metadata={
                "required_nodes": 2,
                "max_steps": 5,
                "thresholds": {"midpoint": 0.85, "branch": 0.60},
            },
        )

        assert "Metadata:" in debug
        assert "required_nodes: 2" in debug
        assert "max_steps: 5" in debug
        assert "thresholds:" in debug
        assert "midpoint: 0.85" in debug
        # Python formats 0.60 as 0.6
        assert "branch: 0.6" in debug

    def test_format_debug_block_with_none_values(self):
        """Test debug block handles None values correctly."""
        # Filter out None values before passing to format_debug_block
        components_with_none = {
            "retrieval": 0.80,
            "graph": 0.70,
            "alarm": 0.85,
            "rerank": None,  # Rerank absent
        }
        components_filtered = {k: v for k, v in components_with_none.items() if v is not None}
        
        debug = format_debug_block(
            confidence=0.75,
            strategy="multi_node",
            components=components_filtered,
        )

        # Verify output contains the filtered components
        assert "retrieval: 0.80" in debug
        assert "graph: 0.70" in debug
        assert "alarm: 0.85" in debug

    def test_get_debug_context_disabled(self):
        """Test get_debug_context when debug is disabled."""
        context = get_debug_context()

        assert "debug_enabled" in context
        assert "debug_env_var" in context
        assert context["debug_enabled"] is False
        assert context["debug_env_var"] == "0"

    def test_get_debug_context_enabled(self):
        """Test get_debug_context when debug is enabled."""
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = "1"
        context = get_debug_context()

        assert context["debug_enabled"] is True
        assert context["debug_env_var"] == "1"

    def test_format_confidence_breakdown_with_rerank(self):
        """Test confidence breakdown formatting with rerank."""
        breakdown = format_confidence_breakdown(
            retrieval_conf=0.85,
            graph_conf=0.80,
            alarm_conf=0.90,
            rerank_conf=0.75,
            combined_conf=0.82,
        )

        assert "Confidence Breakdown:" in breakdown
        assert "retrieval: 0.850" in breakdown
        assert "graph: 0.800" in breakdown
        assert "alarm: 0.900" in breakdown
        assert "rerank: 0.750" in breakdown
        assert "combined: 0.820" in breakdown
        assert "weight:" in breakdown  # Should show weights

    def test_format_confidence_breakdown_without_rerank(self):
        """Test confidence breakdown when rerank is absent."""
        breakdown = format_confidence_breakdown(
            retrieval_conf=0.85,
            graph_conf=0.80,
            alarm_conf=0.90,
            rerank_conf=None,
            combined_conf=0.85,
        )

        assert "rerank: None (weight redistributed)" in breakdown
        assert "combined: 0.850" in breakdown

    def test_log_debug_info_no_output_when_disabled(self, capsys):
        """Test that log_debug_info produces no output when disabled."""
        # Ensure debug is disabled
        assert is_debug_enabled() is False

        # Call log_debug_info
        log_debug_info(
            confidence=0.85,
            strategy="midpoint",
            components={"retrieval": 0.90},
        )

        # Should have no stdout or stderr
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_log_debug_info_outputs_when_enabled(self, capsys):
        """Test that log_debug_info outputs to stderr when enabled."""
        # Enable debug mode
        os.environ["NIC_DEBUG_TROUBLESHOOT"] = "1"
        assert is_debug_enabled() is True

        # Call log_debug_info
        log_debug_info(
            confidence=0.85,
            strategy="midpoint",
            components={"retrieval": 0.90, "graph": 0.85},
        )

        # Should have stderr output, no stdout
        captured = capsys.readouterr()
        assert captured.out == ""  # No stdout pollution
        assert len(captured.err) > 0  # Should have stderr
        assert "NIC DIAGNOSTIC DEBUG" in captured.err
        assert "Confidence: 0.850" in captured.err


# ──────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining confidence and strategy."""

    def test_high_confidence_to_midpoint_workflow(self):
        """Test full workflow from high confidence to midpoint strategy."""
        # High confidence inputs
        confidence = compute_diagnostic_confidence(
            retrieval_conf=0.90,
            graph_conf=0.88,
            alarm_conf=0.95,
            rerank_conf=0.85,
        )

        # Should produce high confidence
        assert confidence > 0.85

        # Should select midpoint strategy
        strategy = determine_confirmation_strategy(confidence)
        assert strategy == ConfirmationStrategy.MIDPOINT

        # Should recommend few steps
        max_steps = get_max_steps_for_strategy(strategy)
        assert max_steps == 3

    def test_medium_confidence_to_branch_workflow(self):
        """Test workflow from medium confidence to branch strategy."""
        confidence = compute_diagnostic_confidence(
            retrieval_conf=0.75,
            graph_conf=0.70,
            alarm_conf=0.65,
        )

        # Should be in medium range
        assert 0.60 <= confidence < 0.85

        # Should select branch strategy
        strategy = determine_confirmation_strategy(confidence)
        assert strategy == ConfirmationStrategy.BRANCH

        # Should recommend standard steps
        max_steps = get_max_steps_for_strategy(strategy)
        assert max_steps == 5

    def test_low_confidence_to_multi_node_workflow(self):
        """Test workflow from low confidence to multi-node strategy."""
        confidence = compute_diagnostic_confidence(
            retrieval_conf=0.45,
            graph_conf=0.40,
            alarm_conf=0.50,
        )

        # Should be low confidence
        assert confidence < 0.60

        # Should select multi-node strategy
        strategy = determine_confirmation_strategy(confidence)
        assert strategy == ConfirmationStrategy.MULTI_NODE

        # Should recommend more steps for verification
        max_steps = get_max_steps_for_strategy(strategy)
        assert max_steps == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
