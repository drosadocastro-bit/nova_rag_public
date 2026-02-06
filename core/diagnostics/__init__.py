"""Diagnostics subsystem for NIC."""

from core.diagnostics.diagnostic_confidence import (
    DiagnosticConfidenceAggregator,
    ConfidenceComponents,
    compute_diagnostic_confidence,
    get_aggregator,
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

__all__ = [
    # Confidence aggregation
    "DiagnosticConfidenceAggregator",
    "ConfidenceComponents",
    "compute_diagnostic_confidence",
    "get_aggregator",
    # Confirmation strategy
    "ConfirmationStrategy",
    "determine_confirmation_strategy",
    "get_strategy_description",
    "get_strategy_metadata",
    "get_max_steps_for_strategy",
    "get_required_nodes_count",
    # Debug output
    "is_debug_enabled",
    "format_debug_block",
    "log_debug_info",
    "get_debug_context",
    "format_confidence_breakdown",
]
