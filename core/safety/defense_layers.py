"""
Defense layer registry for NIC safety model.

This module provides a single source of truth for the 8-layer defense
architecture referenced in governance documentation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefenseLayer:
    id: int
    name: str
    description: str


def get_defense_layers() -> list[DefenseLayer]:
    """Return the ordered list of NIC safety defense layers."""
    return [
        DefenseLayer(1, "Policy Guard", "Keyword and policy guardrails for unsafe or out-of-scope queries."),
        DefenseLayer(2, "RAG Retrieval", "Retrieve evidence from approved manuals and indexes."),
        DefenseLayer(3, "Citation Tracing", "Maintain source attribution for claims and steps."),
        DefenseLayer(4, "Confidence Threshold", "Block low-confidence retrieval outputs before generation."),
        DefenseLayer(5, "Abstractive Generation", "LLM synthesis constrained to retrieved context."),
        DefenseLayer(6, "Extractive Fallback", "Deterministic snippet responses when confidence is low."),
        DefenseLayer(7, "Citation Auditing", "Post-generation verification against retrieved evidence."),
        DefenseLayer(8, "Self-Refinement", "Iterative refinement when confidence is below thresholds."),
    ]


__all__ = ["DefenseLayer", "get_defense_layers"]
