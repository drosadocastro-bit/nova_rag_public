"""
Debug Output Module for NIC Diagnostics

Provides debug logging functionality for troubleshooting diagnostic confidence
and confirmation strategy decisions. Output is controlled via NIC_DEBUG_TROUBLESHOOT
environment variable and goes to stderr to avoid stdout pollution.

Non-negotiable rules:
- No LLM usage
- Deterministic formatting only
- Output to stderr only (not stdout)
- Only outputs when NIC_DEBUG_TROUBLESHOOT=1
- Round confidence values to 3 decimals
- Handle None values gracefully
"""

import os
import sys
from typing import Dict, Optional, Any


def is_debug_enabled() -> bool:
    """
    Check if debug mode is enabled via environment variable.
    
    Returns:
        bool: True if NIC_DEBUG_TROUBLESHOOT is exactly "1", False otherwise
    """
    return os.environ.get("NIC_DEBUG_TROUBLESHOOT", "0") == "1"


def get_debug_context() -> Dict[str, Any]:
    """
    Get current debug context information.
    
    Returns:
        dict: Contains debug_enabled (bool) and debug_env_var (str)
    """
    env_var = os.environ.get("NIC_DEBUG_TROUBLESHOOT", "0")
    return {
        "debug_enabled": env_var == "1",
        "debug_env_var": env_var,
    }


def _format_metadata_value(value: Any, indent: int = 2) -> str:
    """
    Format a metadata value with proper indentation for nested structures.
    
    Args:
        value: The value to format (can be dict, list, or primitive)
        indent: Number of spaces for indentation
    
    Returns:
        str: Formatted value string
    """
    if isinstance(value, dict):
        # Format nested dictionaries with indentation
        lines = []
        for k, v in value.items():
            if isinstance(v, dict):
                lines.append(f"{' ' * indent}{k}:")
                for nested_k, nested_v in v.items():
                    lines.append(f"{' ' * (indent + 2)}{nested_k}: {nested_v}")
            else:
                lines.append(f"{' ' * indent}{k}: {v}")
        return "\n".join(lines)
    else:
        return str(value)


def format_debug_block(
    confidence: float,
    strategy: str,
    components: Optional[Dict[str, float]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Format a debug output block with confidence, strategy, and optional details.
    
    Args:
        confidence: Combined confidence score (0.0-1.0)
        strategy: Confirmation strategy name
        components: Optional dict of confidence components (retrieval, graph, alarm, rerank)
        metadata: Optional dict of strategy metadata
    
    Returns:
        str: Formatted debug block with clear delimiters
    """
    lines = []
    lines.append("===== NIC DIAGNOSTIC DEBUG =====")
    lines.append(f"Confidence: {confidence:.3f}")
    lines.append(f"Strategy: {strategy}")
    
    # Add components section if provided
    if components:
        lines.append("")
        lines.append("Components:")
        for key, value in components.items():
            lines.append(f"  {key}: {value:.3f}")
    
    # Add metadata section if provided
    if metadata:
        lines.append("")
        lines.append("Metadata:")
        for key, value in metadata.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for nested_key, nested_value in value.items():
                    lines.append(f"    {nested_key}: {nested_value}")
            else:
                lines.append(f"  {key}: {value}")
    
    lines.append("================================")
    return "\n".join(lines)


def log_debug_info(
    confidence: float,
    strategy: str,
    components: Optional[Dict[str, float]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log debug information to stderr when debug mode is enabled.
    
    Args:
        confidence: Combined confidence score (0.0-1.0)
        strategy: Confirmation strategy name
        components: Optional dict of confidence components
        metadata: Optional dict of strategy metadata
    
    Returns:
        None: Output goes to stderr, no return value
    """
    if not is_debug_enabled():
        return
    
    debug_block = format_debug_block(confidence, strategy, components, metadata)
    print(debug_block, file=sys.stderr)


def format_confidence_breakdown(
    retrieval_conf: float,
    graph_conf: float,
    alarm_conf: float,
    rerank_conf: Optional[float],
    combined_conf: float,
) -> str:
    """
    Format a detailed confidence breakdown with all components and weights.
    
    Args:
        retrieval_conf: Retrieval confidence score
        graph_conf: Graph matching confidence score
        alarm_conf: Alarm correlation confidence score
        rerank_conf: Optional reranking confidence score (None if absent)
        combined_conf: Final combined confidence score
    
    Returns:
        str: Formatted breakdown showing all components with weights
    """
    lines = []
    lines.append("Confidence Breakdown:")
    lines.append(f"  retrieval: {retrieval_conf:.3f} (weight: 0.3)")
    lines.append(f"  graph: {graph_conf:.3f} (weight: 0.3)")
    lines.append(f"  alarm: {alarm_conf:.3f} (weight: 0.3)")
    
    if rerank_conf is not None:
        lines.append(f"  rerank: {rerank_conf:.3f} (weight: 0.1)")
    else:
        lines.append("  rerank: None (weight redistributed)")
    
    lines.append(f"  combined: {combined_conf:.3f}")
    
    return "\n".join(lines)
