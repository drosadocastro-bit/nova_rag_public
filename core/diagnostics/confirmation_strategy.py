"""
Confirmation Strategy Engine

Determines the appropriate diagnostic confirmation strategy based on confidence score.
Uses deterministic thresholds to select between midpoint isolation, branching, or
multi-node verification approaches.

Strategy definitions:
- midpoint: High confidence (≥0.85) → Direct midpoint isolation
- branch: Medium confidence (0.60-0.85) → Branch both directions
- multi_node: Low confidence (<0.60) → Verify multiple nodes for corroboration

This module is part of NIC Phase 4 infrastructure - confidence-based adaptive strategies.
"""

import logging
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ConfirmationStrategy(str, Enum):
    """Available confirmation strategies."""
    MIDPOINT = "midpoint"
    BRANCH = "branch"
    MULTI_NODE = "multi_node"


# Thresholds for strategy selection
MIDPOINT_THRESHOLD = 0.85
BRANCH_THRESHOLD = 0.60


def determine_confirmation_strategy(confidence: float) -> str:
    """
    Determine the appropriate confirmation strategy based on confidence score.
    
    Strategy Rules:
    - confidence >= 0.85 → "midpoint" (direct isolation)
    - 0.60 <= confidence < 0.85 → "branch" (check both upstream/downstream)
    - confidence < 0.60 → "multi_node" (verify multiple points)
    
    Args:
        confidence: Diagnostic confidence score (0.0-1.0)
        
    Returns:
        Strategy name as string: "midpoint", "branch", or "multi_node"
        
    Examples:
        >>> determine_confirmation_strategy(0.92)
        'midpoint'
        >>> determine_confirmation_strategy(0.75)
        'branch'
        >>> determine_confirmation_strategy(0.45)
        'multi_node'
    """
    # Clamp to valid range
    confidence = max(0.0, min(1.0, confidence))

    if confidence >= MIDPOINT_THRESHOLD:
        strategy = ConfirmationStrategy.MIDPOINT
    elif confidence >= BRANCH_THRESHOLD:
        strategy = ConfirmationStrategy.BRANCH
    else:
        strategy = ConfirmationStrategy.MULTI_NODE

    logger.debug(
        f"Confidence {confidence:.3f} → Strategy: {strategy.value}"
    )

    return strategy.value


def get_strategy_description(strategy: str) -> str:
    """
    Get human-readable description of a confirmation strategy.
    
    Args:
        strategy: Strategy name
        
    Returns:
        Description string
    """
    descriptions = {
        ConfirmationStrategy.MIDPOINT: (
            "Direct midpoint isolation - high confidence allows single-point check"
        ),
        ConfirmationStrategy.BRANCH: (
            "Branching verification - check both upstream and downstream paths"
        ),
        ConfirmationStrategy.MULTI_NODE: (
            "Multi-node verification - corroborate across multiple test points"
        ),
    }
    # Convert string strategy to enum for dictionary lookup
    try:
        strategy_enum = ConfirmationStrategy(strategy)
        return descriptions.get(strategy_enum, "Unknown strategy")
    except ValueError:
        return "Unknown strategy"


def get_strategy_metadata(confidence: float) -> Dict[str, Any]:
    """
    Get full strategy metadata including strategy, confidence, and description.
    
    Args:
        confidence: Diagnostic confidence score
        
    Returns:
        Dict with strategy details
    """
    strategy = determine_confirmation_strategy(confidence)

    return {
        "strategy": strategy,
        "confidence": round(confidence, 3),
        "description": get_strategy_description(strategy),
        "thresholds": {
            "midpoint": MIDPOINT_THRESHOLD,
            "branch": BRANCH_THRESHOLD,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Strategy-Specific Parameters
# ──────────────────────────────────────────────────────────────────────────────


def get_max_steps_for_strategy(strategy: str, default_max_steps: int = 5) -> int:
    """
    Get recommended maximum steps for a given strategy.
    
    Args:
        strategy: Confirmation strategy name
        default_max_steps: Default if strategy not recognized
        
    Returns:
        Recommended max_steps for the strategy
    """
    strategy_steps = {
        ConfirmationStrategy.MIDPOINT: 3,      # Focused isolation
        ConfirmationStrategy.BRANCH: 5,        # Standard branching
        ConfirmationStrategy.MULTI_NODE: 7,    # More verification points
    }

    # Convert string strategy to enum for dictionary lookup
    try:
        strategy_enum = ConfirmationStrategy(strategy)
        return strategy_steps.get(strategy_enum, default_max_steps)
    except ValueError:
        return default_max_steps


def get_required_nodes_count(strategy: str) -> int:
    """
    Get minimum number of nodes that should be checked for a strategy.
    
    Args:
        strategy: Confirmation strategy name
        
    Returns:
        Minimum nodes to verify
    """
    required_nodes = {
        ConfirmationStrategy.MIDPOINT: 1,
        ConfirmationStrategy.BRANCH: 2,
        ConfirmationStrategy.MULTI_NODE: 3,
    }

    # Convert string strategy to enum for dictionary lookup
    try:
        strategy_enum = ConfirmationStrategy(strategy)
        return required_nodes.get(strategy_enum, 1)
    except ValueError:
        return 1
