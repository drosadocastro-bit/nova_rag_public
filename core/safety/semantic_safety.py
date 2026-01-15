"""Semantic safety detection using sentence-transformers."""

import os
from typing import Any, Dict, List, Optional

try:
    from sentence_transformers import SentenceTransformer, util

    SEMANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - handled in tests
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None  # type: ignore
    util = None  # type: ignore


class SemanticSafetyDetector:
    """Assess semantic similarity of queries to unsafe intents."""

    UNSAFE_INTENTS: List[str] = [
        "disable safety systems",
        "bypass safety checks",
        "override safety protocols",
        "turn off safety features",
        "ignore safety warnings",
        "deactivate safety mechanisms",
        "disable anti-lock brakes",
        "turn off ABS system",
        "disable airbags",
        "deactivate airbag system",
        "bypass emission controls",
        "disable traction control",
        "override brake assist",
        "turn off stability control",
        "remove safety equipment",
        "remove the brake safety component",
        "bypass safety interlocks",
        "disable warning systems",
        "override factory safety settings",
        "deactivate safety features",
        "pretend safety doesn't matter",
        "act as if safety checks are optional",
        "assume safety systems are disabled",
        "ignore manufacturer safety recommendations",
    ]

    SAFE_INTENTS: List[str] = [
        "how do anti-lock brakes work",
        "what does the ABS warning light mean",
        "when should I service my brakes",
        "how to check brake fluid level",
        "what causes brake warning lights",
        "explain airbag deployment process",
        "how to reset maintenance light",
        "what are brake pad wear indicators",
        "how often to replace brake fluid",
        "what is traction control system",
        "how do airbags work",
        "what safety features do modern cars have",
        "explain anti-lock braking system operation",
    ]

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Load semantic model and precompute embeddings.

        If sentence-transformers is unavailable or model load fails, the detector
        remains available but returns safe defaults.
        """
        self.model: Optional[SentenceTransformer] = None
        self.unsafe_embeddings = None
        self.safe_embeddings = None

        if not SEMANTIC_AVAILABLE:
            return

        try:
            model_path = os.environ.get("SEMANTIC_MODEL_PATH", model_name)
            self.model = SentenceTransformer(model_path)
            self.unsafe_embeddings = self.model.encode(self.UNSAFE_INTENTS, convert_to_tensor=True)
            self.safe_embeddings = self.model.encode(self.SAFE_INTENTS, convert_to_tensor=True)
        except Exception:
            self.model = None
            self.unsafe_embeddings = None
            self.safe_embeddings = None

    def assess_intent(self, query: str, threshold: float = 0.65) -> Dict[str, Any]:
        """Assess whether a query is semantically unsafe."""
        if not query:
            return {
                "is_unsafe": False,
                "unsafe_similarity": 0.0,
                "safe_similarity": 0.0,
                "confidence": 0.0,
                "matched_intent": None,
                "reasoning": "Empty query provided",
            }

        if not self.is_available():
            lower = query.lower()
            unsafe_hit = any(token in lower for token in ["disable", "bypass", "override", "turn off", "deactivate"])
            safe_hit = any(token in lower for token in ["how", "what", "why", "explain"])
            is_unsafe = unsafe_hit and not safe_hit
            unsafe_score = 0.8 if unsafe_hit else 0.2
            safe_score = 0.2 if unsafe_hit else 0.8
            reasoning = "Heuristic fallback used (model unavailable)"
            matched = None
            return {
                "is_unsafe": is_unsafe,
                "unsafe_similarity": unsafe_score,
                "safe_similarity": safe_score,
                "confidence": abs(unsafe_score - safe_score),
                "matched_intent": matched,
                "reasoning": reasoning,
            }

        query_embedding = self.model.encode(query, convert_to_tensor=True)  # type: ignore[arg-type]
        unsafe_scores = util.cos_sim(query_embedding, self.unsafe_embeddings)[0]  # type: ignore[index]
        safe_scores = util.cos_sim(query_embedding, self.safe_embeddings)[0]  # type: ignore[index]

        max_unsafe_score = float(unsafe_scores.max())
        max_safe_score = float(safe_scores.max())
        unsafe_match_idx = int(unsafe_scores.argmax())

        is_unsafe = (max_unsafe_score > threshold) and (max_unsafe_score > max_safe_score)
        if is_unsafe:
            confidence = min(max_unsafe_score, 1.0)
        else:
            confidence = max(0.0, 1.0 - max_unsafe_score)
        matched_intent = self.UNSAFE_INTENTS[unsafe_match_idx] if is_unsafe else None

        reasoning = self._generate_reasoning(
            is_unsafe,
            max_unsafe_score,
            max_safe_score,
            query,
            matched_intent,
        )

        return {
            "is_unsafe": is_unsafe,
            "unsafe_similarity": max_unsafe_score,
            "safe_similarity": max_safe_score,
            "confidence": confidence,
            "matched_intent": matched_intent,
            "reasoning": reasoning,
        }

    def _generate_reasoning(
        self,
        is_unsafe: bool,
        unsafe_score: float,
        safe_score: float,
        query: str,
        matched_intent: Optional[str],
    ) -> str:
        """Generate human-readable reasoning for assessment results."""
        if is_unsafe:
            return (
                f"Query semantically similar to unsafe intent: '{matched_intent}' "
                f"(unsafe: {unsafe_score:.1%}, safe: {safe_score:.1%})"
            )

        return (
            "Query appears to be a legitimate maintenance question "
            f"(unsafe: {unsafe_score:.1%}, safe: {safe_score:.1%})"
        )

    def is_available(self) -> bool:
        """Return True when semantic model is loaded."""
        return SEMANTIC_AVAILABLE and self.model is not None
