"""
Phase 2 Enhanced Retrieval Engine

Wraps standard retrieval_engine.retrieve() with:
1. Evidence tracking for debugging contamination
2. Domain-aware filtering via router
3. Per-domain caps for diversity enforcement

Usage:
    from core.retrieval.retrieval_engine_phase2 import retrieve_with_phase2
    
    results = retrieve_with_phase2(
        query="How do I check tire pressure?",
        k=12,
        top_n=6,
        enable_evidence_tracking=True,
        enable_domain_caps=True,
        enable_router_filtering=True
    )
"""
import os
from typing import Any, TYPE_CHECKING
from collections import defaultdict

# Import base retrieval engine
from core.retrieval.retrieval_engine import retrieve as base_retrieve

# Import Phase 2 modules
try:
    from core.retrieval.evidence_tracker import EvidenceTracker
    EVIDENCE_TRACKING_AVAILABLE = True
except ImportError:
    EVIDENCE_TRACKING_AVAILABLE = False
    if TYPE_CHECKING:
        from core.retrieval.evidence_tracker import EvidenceTracker  # type: ignore

try:
    from core.retrieval.domain_router import infer_domain_candidates, should_filter_with_domain
    DOMAIN_ROUTER_AVAILABLE = True
except ImportError:
    DOMAIN_ROUTER_AVAILABLE = False


# Environment flags
EVIDENCE_TRACKING_ENABLED = os.environ.get("NOVA_EVIDENCE_TRACKING", "0") == "1"
MAX_CHUNKS_PER_DOMAIN = int(os.environ.get("NOVA_MAX_CHUNKS_PER_DOMAIN", "0"))
ROUTER_FILTERING_ENABLED = os.environ.get("NOVA_ROUTER_FILTERING", "0") == "1"


def apply_domain_caps(chunks: list[dict], max_per_domain: int) -> list[dict]:
    """
    Enforce per-domain caps to prevent single domain from dominating results.
    
    Args:
        chunks: List of chunk dicts with 'domain' field
        max_per_domain: Maximum chunks allowed per domain
    
    Returns:
        Filtered list respecting caps
    """
    if max_per_domain <= 0:
        return chunks
    
    domain_counts = defaultdict(int)
    filtered = []
    
    for chunk in chunks:
        domain = chunk.get('domain', 'unknown')
        if domain_counts[domain] < max_per_domain:
            filtered.append(chunk)
            domain_counts[domain] += 1
    
    return filtered


def retrieve_with_phase2(
    query: str,
    k: int = 12,
    top_n: int = 6,
    lambda_diversity: float = 0.5,
    use_reranker: bool = True,
    use_sklearn_reranker: bool | None = None,
    use_gar: bool = True,
    enable_evidence_tracking: bool | None = None,
    enable_domain_caps: bool | None = None,
    enable_router_filtering: bool | None = None,
) -> list[dict]:
    """
    Enhanced retrieval with Phase 2 features.
    
    Args:
        query: Search query
        k: Initial retrieval count
        top_n: Final result count
        lambda_diversity: MMR diversity weight
        use_reranker: Enable cross-encoder reranking
        use_sklearn_reranker: Use sklearn reranker
        use_gar: Enable GAR expansion
        enable_evidence_tracking: Track evidence chain (default: from env NOVA_EVIDENCE_TRACKING)
        enable_domain_caps: Apply per-domain caps (default: from env NOVA_MAX_CHUNKS_PER_DOMAIN)
        enable_router_filtering: Use domain router filtering (default: from env NOVA_ROUTER_FILTERING)
    
    Returns:
        List of chunks with Phase 2 enhancements
    """
    # Determine feature flags
    if enable_evidence_tracking is None:
        enable_evidence_tracking = EVIDENCE_TRACKING_ENABLED
    if enable_domain_caps is None:
        enable_domain_caps = MAX_CHUNKS_PER_DOMAIN > 0
    if enable_router_filtering is None:
        enable_router_filtering = ROUTER_FILTERING_ENABLED
    
    # Check module availability
    if enable_evidence_tracking and not EVIDENCE_TRACKING_AVAILABLE:
        print("[Phase2] Evidence tracking requested but module not available")
        enable_evidence_tracking = False
    
    if enable_router_filtering and not DOMAIN_ROUTER_AVAILABLE:
        print("[Phase2] Router filtering requested but module not available")
        enable_router_filtering = False
    
    # Initialize evidence tracker if enabled
    tracker = None
    if enable_evidence_tracking and EVIDENCE_TRACKING_AVAILABLE:
        tracker = EvidenceTracker(query)
    
    # ===== PHASE 2.1: BASE RETRIEVAL (GAR + RERANKING) =====
    chunks = base_retrieve(
        query=query,
        k=k,
        top_n=top_n,
        lambda_diversity=lambda_diversity,
        use_reranker=use_reranker,
        use_sklearn_reranker=use_sklearn_reranker,
        use_gar=use_gar
    )
    
    # ===== PHASE 2.2: PER-DOMAIN CAPS =====
    if enable_domain_caps and MAX_CHUNKS_PER_DOMAIN > 0:
        pre_cap_count = len(chunks)
        chunks = apply_domain_caps(chunks, MAX_CHUNKS_PER_DOMAIN)
        if len(chunks) < pre_cap_count:
            print(f"[Phase2] Domain caps: {pre_cap_count} -> {len(chunks)} chunks (max {MAX_CHUNKS_PER_DOMAIN} per domain)")
    
    if tracker:
        print("\n" + "="*70)
        print("EVIDENCE CHAIN AVAILABLE")
        print("="*70)
        print(f"Query: {query}")
        print(f"Results: {len(chunks)} chunks")
        if chunks:
            domains = set(c.get('domain', 'unknown') for c in chunks)
            print(f"Domains: {domains}")
        print("="*70 + "\n")
    
    return chunks


def retrieve_with_evidence(
    query: str,
    k: int = 12,
    top_n: int = 6,
    **kwargs
) -> tuple[list[dict], str]:
    """
    Convenience wrapper that returns both chunks and evidence summary.
    
    Returns:
        (chunks, evidence_summary) tuple
    """
    chunks = base_retrieve(query=query, k=k, top_n=top_n, **kwargs)
    
    # Generate basic summary
    if chunks:
        domains = {}
        for chunk in chunks:
            domain = chunk.get('domain', 'unknown')
            domains[domain] = domains.get(domain, 0) + 1
        summary = f"{len(chunks)} results from domains: {domains}"
    else:
        summary = "No results found"
    
    return chunks, summary


# Backward compatibility alias
retrieve_phase2 = retrieve_with_phase2
