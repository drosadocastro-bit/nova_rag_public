"""
Phase 2 demonstration: Evidence tracking and per-domain caps.

Shows how to use the evidence tracker and per-domain diversity caps
to improve retrieval quality and debugging.
"""

import os
import sys
from pathlib import Path
from collections import Counter
from typing import List, Dict

sys.path.insert(0, '.')

# Import Phase 2 components
from core.retrieval.evidence_tracker import EvidenceTracker
from core.retrieval.domain_router import infer_domain_candidates, should_filter_with_domain

# Configuration
INDEX_DIR = Path("vector_db")
DOMAIN_FILTER_THRESHOLD = 0.35
MAX_CHUNKS_PER_DOMAIN = 5  # Enforce diversity


def apply_domain_caps(results: List[dict], max_per_domain: int) -> tuple[List[dict], List[str]]:
    """
    Enforce maximum chunks per domain for diversity.
    
    Args:
        results: List of result chunks with 'domain' field
        max_per_domain: Maximum chunks allowed from any single domain
    
    Returns:
        (capped_results, capped_domains)
    """
    if max_per_domain <= 0:
        return results, []
    
    domain_counts = Counter()
    capped_results = []
    capped_domains = set()
    
    for result in results:
        domain = result.get("domain", "unknown")
        if domain_counts[domain] < max_per_domain:
            capped_results.append(result)
            domain_counts[domain] += 1
        else:
            capped_domains.add(domain)
    
    return capped_results, list(capped_domains)


def demonstrate_evidence_tracking(query: str):
    """Show evidence tracking for a query."""
    print(f"\n{'='*80}")
    print(f"EVIDENCE TRACKING DEMO")
    print(f"{'='*80}")
    print(f"Query: {query}\n")
    
    # Create tracker
    tracker = EvidenceTracker(query, enabled=True)
    
    with tracker:
        # Simulate domain router stage
        domain_candidates, domain_priors = infer_domain_candidates(query, INDEX_DIR)
        filtered_domains = should_filter_with_domain(domain_candidates, DOMAIN_FILTER_THRESHOLD)
        
        tracker.record_router(
            domain_candidates=domain_candidates,
            domain_priors=domain_priors,
            filter_applied=bool(filtered_domains),
            filtered_domains=filtered_domains,
            threshold_used=DOMAIN_FILTER_THRESHOLD,
            zero_shot_available=True,
            method="zero-shot+keywords",
        )
        
        # Simulate GAR expansion (mock data)
        tracker.record_gar(
            initial_candidates=12,
            expanded_candidates=18,
            domains_in_candidates={"radar": 10, "forklift": 8},
        )
        
        # Simulate reranking (mock data)
        tracker.record_reranking(
            candidates_before=18,
            candidates_after=12,
            top_scores=[0.89, 0.85, 0.82, 0.78, 0.75],
            domain_prior_boost_applied=True,
            domains_in_top_10={"radar": 8, "forklift": 2},
        )
        
        # Simulate final selection (mock data)
        tracker.record_final_selection(
            total_results=6,
            domain_distribution={"radar": 5, "forklift": 1},
            domain_cap_applied=False,
            capped_domains=[],
            scores=[0.89, 0.85, 0.82, 0.78, 0.75, 0.72],
        )
    
    # Get and display evidence chain
    chain = tracker.get_chain()
    if chain:
        print(chain.summary())
        print(f"\n{'='*80}")
        print("Evidence chain captured successfully!")
        print(f"Execution time: {chain.execution_time_ms:.2f}ms")


def demonstrate_domain_caps():
    """Show per-domain result capping."""
    print(f"\n{'='*80}")
    print(f"PER-DOMAIN CAPS DEMO")
    print(f"{'='*80}\n")
    
    # Mock results heavily biased toward forklift
    mock_results = [
        {"text": "Forklift capacity...", "domain": "forklift", "confidence": 0.92},
        {"text": "Forklift safety...", "domain": "forklift", "confidence": 0.89},
        {"text": "Radar calibration...", "domain": "radar", "confidence": 0.87},
        {"text": "Forklift maintenance...", "domain": "forklift", "confidence": 0.85},
        {"text": "Forklift operation...", "domain": "forklift", "confidence": 0.83},
        {"text": "HVAC specs...", "domain": "hvac", "confidence": 0.82},
        {"text": "Forklift inspection...", "domain": "forklift", "confidence": 0.80},
        {"text": "Forklift training...", "domain": "forklift", "confidence": 0.78},
    ]
    
    print(f"Original Results ({len(mock_results)} chunks):")
    domain_dist = Counter(r["domain"] for r in mock_results)
    for domain, count in domain_dist.most_common():
        pct = (count / len(mock_results)) * 100
        print(f"  {domain:20s}: {count:2d} chunks ({pct:5.1f}%)")
    
    print(f"\nApplying cap: MAX_CHUNKS_PER_DOMAIN={MAX_CHUNKS_PER_DOMAIN}\n")
    
    # Apply caps
    capped_results, capped_domains = apply_domain_caps(mock_results, MAX_CHUNKS_PER_DOMAIN)
    
    print(f"Capped Results ({len(capped_results)} chunks):")
    capped_dist = Counter(r["domain"] for r in capped_results)
    for domain, count in capped_dist.most_common():
        pct = (count / len(capped_results)) * 100
        marker = "[CAPPED]" if domain in capped_domains else ""
        print(f"  {domain:20s}: {count:2d} chunks ({pct:5.1f}%) {marker}")
    
    if capped_domains:
        print(f"\nCapped domains: {', '.join(capped_domains)}")
        print(f"Dropped: {len(mock_results) - len(capped_results)} chunks")
    
    print(f"\n{'='*80}")
    print("Diversity enforcement successful!")
    print(f"Forklift dominance reduced from {domain_dist['forklift']/len(mock_results)*100:.1f}% "
          f"to {capped_dist['forklift']/len(capped_results)*100:.1f}%")


def demonstrate_router_monitoring():
    """Show router performance monitoring."""
    print(f"\n{'='*80}")
    print(f"ROUTER MONITORING DEMO")
    print(f"{'='*80}\n")
    
    print("Router monitoring is controlled by NOVA_ROUTER_MONITORING environment variable.")
    print(f"Current status: {'ENABLED' if os.environ.get('NOVA_ROUTER_MONITORING') == '1' else 'DISABLED'}")
    
    if os.environ.get('NOVA_ROUTER_MONITORING') != '1':
        print("\nTo enable monitoring:")
        print("  export NOVA_ROUTER_MONITORING=1")
        print("\nMonitoring logs will be written to: nova_router_monitoring.log")
        print("\nExample log entry:")
        print("""
        {
          "timestamp": "2026-01-22T10:30:15.123456",
          "query": "How do I calibrate weather radar?",
          "method": "zero-shot+keywords",
          "keyword_scores": {"radar": 1.0, "forklift": 0.0},
          "zero_shot_scores": {"radar": 0.95, "vehicle": 0.12},
          "combined_scores": {"radar": 1.0, "vehicle": 0.12},
          "top_candidates": [["radar", 1.0], ["vehicle", 0.12]],
          "priors": {"radar": 1.0, "vehicle": 0.12}
        }
        """)
    else:
        print("\nMonitoring is ENABLED. Running test queries...\n")
        
        test_queries = [
            "How do I calibrate weather radar?",
            "What is the forklift capacity?",
            "Engine maintenance procedures",
        ]
        
        for query in test_queries:
            print(f"Testing: {query}")
            domain_candidates, _ = infer_domain_candidates(query, INDEX_DIR)
            filtered = should_filter_with_domain(domain_candidates, DOMAIN_FILTER_THRESHOLD)
            print(f"  → Candidates: {domain_candidates}")
            print(f"  → Filter: {filtered}\n")
        
        print("Check nova_router_monitoring.log for detailed metrics.")
    
    print(f"{'='*80}")


def main():
    """Run all Phase 2 demonstrations."""
    print("\n" + "="*80)
    print("PHASE 2: Evidence Tracking & Per-Domain Caps")
    print("="*80)
    
    # Demo 1: Evidence tracking
    demonstrate_evidence_tracking("How do I calibrate weather radar?")
    
    # Demo 2: Domain caps
    demonstrate_domain_caps()
    
    # Demo 3: Router monitoring
    demonstrate_router_monitoring()
    
    print(f"\n{'='*80}")
    print("All Phase 2 demonstrations complete!")
    print(f"{'='*80}\n")
    
    print("Summary:")
    print("  ✅ Evidence tracking captures full pipeline trace")
    print("  ✅ Per-domain caps enforce diversity (prevents forklift dominance)")
    print("  ✅ Router monitoring provides performance metrics")
    print("\nNext steps:")
    print("  1. Enable evidence tracking: export NOVA_EVIDENCE_TRACKING=1")
    print("  2. Set domain caps: export NOVA_MAX_CHUNKS_PER_DOMAIN=5")
    print("  3. Enable monitoring: export NOVA_ROUTER_MONITORING=1")
    print("  4. Run cross-contamination tests to validate")


if __name__ == "__main__":
    main()
