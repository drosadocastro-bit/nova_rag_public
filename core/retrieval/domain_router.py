"""Domain-aware routing helpers for multi-domain retrieval.

Provides lightweight domain inference that combines a zero-shot classifier
with keyword heuristics. Intended to select a small set of likely domains
and optional domain priors for downstream reranking.
"""

from __future__ import annotations

import json
import os
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

# Configure monitoring logger
ENABLE_ROUTER_MONITORING = os.environ.get("NOVA_ROUTER_MONITORING", "0") == "1"
router_logger = logging.getLogger("nova.domain_router")
if ENABLE_ROUTER_MONITORING:
    handler = logging.FileHandler("nova_router_monitoring.log")
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    router_logger.addHandler(handler)
    router_logger.setLevel(logging.INFO)

# Default keywords per domain. Updated based on clustering analysis (Phase 2.5).
# Intentionally minimal so the router can operate without loading full pipeline.
DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "vehicle": ["vehicle", "car", "engine", "brake", "oil", "tire", "maintenance", "battery", "transmission", "sedan"],
    "vehicle_military": ["tm9-802", "amphibian", "ford", "gmc", "6x6", "military", "tactical", "convoy"],
    "forklift": ["forklift", "lift", "mast", "load", "capacity", "counterweight", "hydraulic", "pallet"],
    "hvac": ["hvac", "refrigerant", "thermostat", "compressor", "evaporator", "freon", "air", "conditioner", "cooling", "filter", "coil"],
    "radar": ["radar", "wxr", "antenna", "detection", "range", "calibration", "multiscan", "weather"],
}


def _load_domain_metadata(index_dir: Path) -> Dict:
    meta_path = index_dir / "domain_metadata.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _zero_shot_pipeline():
    """Lazily load a zero-shot classifier. Falls back to None on failure."""
    model_name = os.environ.get("NOVA_DOMAIN_ZS_MODEL", "facebook/bart-large-mnli")
    try:
        from transformers import pipeline

        return pipeline("zero-shot-classification", model=model_name, device=-1)
    except Exception as e:  # pragma: no cover - runtime guard
        print(f"[NovaRAG] Domain router: zero-shot model load failed ({e}); using keywords only")
        return None


def keyword_scores(query: str, keywords: Dict[str, List[str]]) -> Dict[str, float]:
    q_lower = query.lower()
    scores: Dict[str, float] = {}
    for domain, kws in keywords.items():
        hits = sum(1 for kw in kws if kw in q_lower)
        if hits:
            scores[domain] = float(hits)
    # Normalize
    if scores:
        max_hit = max(scores.values()) or 1.0
        for d in scores:
            scores[d] = scores[d] / max_hit
    return scores


def infer_domain_candidates(
    query: str,
    index_dir: Path,
    keyword_map: Dict[str, List[str]] | None = None,
    top_n: int = 2,
    min_zs_score: float = 0.25,
) -> Tuple[List[Tuple[str, float]], Dict[str, float]]:
    """Return ordered domain candidates and domain prior scores.

    Returns (candidates, priors) where candidates is a list of (domain, score)
    sorted descending. Priors is a dict of domain->score for easy lookup.
    """

    metadata = _load_domain_metadata(index_dir)
    available_domains: Iterable[str] = metadata.get("domains") or DEFAULT_KEYWORDS.keys()

    kw_map = keyword_map if keyword_map is not None else DEFAULT_KEYWORDS
    kw_scores = keyword_scores(query, kw_map)

    zs_scores: Dict[str, float] = {}
    classifier = _zero_shot_pipeline()
    zero_shot_used = False
    if classifier is not None:
        try:
            labels = list(available_domains)
            zs_result = classifier(query, candidate_labels=labels, multi_label=True)
            if isinstance(zs_result, dict) and "labels" in zs_result and "scores" in zs_result:
                for label, score in zip(zs_result["labels"], zs_result["scores"]):
                    if score >= min_zs_score:
                        zs_scores[label] = float(score)
                zero_shot_used = True
        except Exception as e:  # pragma: no cover - runtime guard
            print(f"[NovaRAG] Domain router: zero-shot classification failed ({e}); using keywords only")

    # Combine scores (simple max fusion)
    combined: Dict[str, float] = {}
    for d in set(list(available_domains) + list(kw_scores.keys()) + list(zs_scores.keys())):
        combined[d] = max(kw_scores.get(d, 0.0), zs_scores.get(d, 0.0))

    # Sort and trim
    ordered = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    ordered = ordered[:top_n]

    # Build priors dict
    priors = {d: s for d, s in ordered if s > 0}
    
    # Log monitoring data
    if ENABLE_ROUTER_MONITORING:
        router_logger.info(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "query": query[:100],  # Truncate long queries
            "method": "zero-shot+keywords" if zero_shot_used else "keywords-only",
            "keyword_scores": kw_scores,
            "zero_shot_scores": zs_scores,
            "combined_scores": dict(ordered),
            "top_candidates": ordered,
            "priors": priors,
        }))
    
    return ordered, priors


def should_filter_with_domain(candidates: List[Tuple[str, float]], threshold: float = 0.35) -> List[str]:
    """Decide which domains to filter on based on top scores."""
    if not candidates:
        filter_decision = []
    else:
        top_domain, top_score = candidates[0]
        filter_decision = [top_domain] if top_score >= threshold else []
    
    # Log filter activation
    if ENABLE_ROUTER_MONITORING:
        router_logger.info(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "event": "filter_decision",
            "candidates": candidates,
            "threshold": threshold,
            "filter_applied": bool(filter_decision),
            "filtered_domains": filter_decision,
            "top_score": candidates[0][1] if candidates else 0.0,
        }))
    
    return filter_decision
