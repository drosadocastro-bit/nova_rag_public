"""
Diagnostic Confidence Aggregator

Combines multiple confidence signals from retrieval, graph matching, alarm correlation,
and optional reranking to produce a single deterministic confidence score for diagnostic plans.

Non-negotiable rules:
- No LLM usage
- Deterministic math only
- Output clamped to [0.0, 1.0]
- Rounded to 3 decimals
- Logged when debug mode enabled

This module is part of NIC Phase 4 infrastructure - confidence-based adaptive strategies.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Environment flag for debug logging
DEBUG_TROUBLESHOOT = os.environ.get("NIC_DEBUG_TROUBLESHOOT", "0") == "1"


@dataclass
class ConfidenceComponents:
    """Individual confidence components for transparency."""
    retrieval_conf: float
    graph_conf: float
    alarm_conf: float
    rerank_conf: Optional[float] = None
    combined_conf: float = 0.0


class DiagnosticConfidenceAggregator:
    """
    Aggregates multiple confidence signals into a single diagnostic confidence score.
    
    Strategy:
    - Retrieval confidence: How well do retrieved chunks match the query?
    - Graph confidence: How well does the graph match the symptom/alarm?
    - Alarm confidence: Did we get an explicit alarm_map match?
    - Rerank confidence (optional): Did a reranker boost relevance?
    
    Weights are tuned for safety-critical diagnostic accuracy.
    """

    def __init__(
        self,
        retrieval_weight: float = 0.35,
        graph_weight: float = 0.30,
        alarm_weight: float = 0.25,
        rerank_weight: float = 0.10,
    ):
        """
        Initialize confidence aggregator with component weights.
        
        Args:
            retrieval_weight: Weight for retrieval confidence (default 0.35)
            graph_weight: Weight for graph matching confidence (default 0.30)
            alarm_weight: Weight for alarm map confidence (default 0.25)
            rerank_weight: Weight for reranker confidence (default 0.10)
            
        Note: Weights should sum to ~1.0 when all components present.
              If rerank_conf is None, weights auto-adjust.
        """
        self.retrieval_weight = retrieval_weight
        self.graph_weight = graph_weight
        self.alarm_weight = alarm_weight
        self.rerank_weight = rerank_weight

    def combine(
        self,
        retrieval_conf: float,
        graph_conf: float,
        alarm_conf: float,
        rerank_conf: Optional[float] = None,
    ) -> float:
        """
        Combine confidence signals into a single diagnostic confidence score.
        
        Args:
            retrieval_conf: Confidence from retrieval (0.0-1.0)
            graph_conf: Confidence from graph matching (0.0-1.0)
            alarm_conf: Confidence from alarm_map match (0.0-1.0)
            rerank_conf: Optional confidence from reranking (0.0-1.0)
            
        Returns:
            Combined confidence score (0.0-1.0), rounded to 3 decimals
        """
        # Validate inputs
        retrieval_conf = self._clamp(retrieval_conf)
        graph_conf = self._clamp(graph_conf)
        alarm_conf = self._clamp(alarm_conf)

        # Compute weights (adjust if rerank absent)
        if rerank_conf is None:
            # Redistribute rerank weight proportionally
            total_base_weight = (
                self.retrieval_weight + self.graph_weight + self.alarm_weight
            )
            norm_retrieval_weight = self.retrieval_weight / total_base_weight
            norm_graph_weight = self.graph_weight / total_base_weight
            norm_alarm_weight = self.alarm_weight / total_base_weight
            rerank_contribution = 0.0
        else:
            rerank_conf = self._clamp(rerank_conf)
            norm_retrieval_weight = self.retrieval_weight
            norm_graph_weight = self.graph_weight
            norm_alarm_weight = self.alarm_weight
            rerank_contribution = self.rerank_weight * rerank_conf

        # Weighted combination
        combined = (
            norm_retrieval_weight * retrieval_conf
            + norm_graph_weight * graph_conf
            + norm_alarm_weight * alarm_conf
            + rerank_contribution
        )

        # Clamp and round
        combined = self._clamp(combined)
        combined = round(combined, 3)

        # Debug logging
        if DEBUG_TROUBLESHOOT:
            self._log_debug(
                retrieval_conf,
                graph_conf,
                alarm_conf,
                rerank_conf,
                combined,
            )

        return combined

    def combine_with_components(
        self,
        retrieval_conf: float,
        graph_conf: float,
        alarm_conf: float,
        rerank_conf: Optional[float] = None,
    ) -> ConfidenceComponents:
        """
        Combine confidence and return both result and components.
        
        Returns:
            ConfidenceComponents with all individual scores and combined result
        """
        combined = self.combine(retrieval_conf, graph_conf, alarm_conf, rerank_conf)

        return ConfidenceComponents(
            retrieval_conf=round(retrieval_conf, 3),
            graph_conf=round(graph_conf, 3),
            alarm_conf=round(alarm_conf, 3),
            rerank_conf=round(rerank_conf, 3) if rerank_conf is not None else None,
            combined_conf=combined,
        )

    def _clamp(self, value: float) -> float:
        """Clamp value to [0.0, 1.0]."""
        return max(0.0, min(1.0, value))

    def _log_debug(
        self,
        retrieval_conf: float,
        graph_conf: float,
        alarm_conf: float,
        rerank_conf: Optional[float],
        combined: float,
    ):
        """Log confidence components when debug mode enabled."""
        logger.debug("[DIAGNOSTIC CONFIDENCE BREAKDOWN]")
        logger.debug(f"  Retrieval Confidence: {retrieval_conf:.3f}")
        logger.debug(f"  Graph Confidence:     {graph_conf:.3f}")
        logger.debug(f"  Alarm Confidence:     {alarm_conf:.3f}")
        if rerank_conf is not None:
            logger.debug(f"  Rerank Confidence:    {rerank_conf:.3f}")
        else:
            logger.debug("  Rerank Confidence:    (not used)")
        logger.debug(f"  → Combined:           {combined:.3f}")


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────────────────────────────────────

_default_aggregator: Optional[DiagnosticConfidenceAggregator] = None


def get_aggregator() -> DiagnosticConfidenceAggregator:
    """Get or create the default confidence aggregator."""
    global _default_aggregator
    if _default_aggregator is None:
        _default_aggregator = DiagnosticConfidenceAggregator()
    return _default_aggregator


def compute_diagnostic_confidence(
    retrieval_conf: float,
    graph_conf: float,
    alarm_conf: float,
    rerank_conf: Optional[float] = None,
) -> float:
    """
    Convenience function to compute diagnostic confidence.
    
    Example:
        confidence = compute_diagnostic_confidence(
            retrieval_conf=0.82,
            graph_conf=0.78,
            alarm_conf=0.95,
        )
    """
    aggregator = get_aggregator()
    return aggregator.combine(retrieval_conf, graph_conf, alarm_conf, rerank_conf)
