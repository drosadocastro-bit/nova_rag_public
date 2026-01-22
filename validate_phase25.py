#!/usr/bin/env python3
"""
Phase 2.5 Validation Script

Tests all Phase 2.5 features:
1. Data gap fixes (civilian vehicle, HVAC expansion)
2. Keyword refinement effectiveness
3. Evidence tracking integration
4. Domain caps enforcement
5. Router filtering functionality

Usage:
    python validate_phase25.py
    python validate_phase25.py --enable-all  # Enable all Phase 2 features
"""
import os
import sys
import argparse
from pathlib import Path
from operator import itemgetter

# Set environment for Phase 2.5 features
os.environ['NOVA_EVIDENCE_TRACKING'] = '1'
os.environ['NOVA_MAX_CHUNKS_PER_DOMAIN'] = '3'
os.environ['NOVA_ROUTER_FILTERING'] = '1'
os.environ['NOVA_ROUTER_MONITORING'] = '1'

# Import Phase 2.5 retrieval engine
try:
    from core.retrieval.retrieval_engine_phase2 import retrieve_with_phase2, retrieve_with_evidence
except ImportError:
    print("[ERROR] Phase 2.5 retrieval engine not found")
    sys.exit(1)


def test_data_gap_fixes():
    """Test that data gap fixes work (civilian vehicle, HVAC)."""
    print("\n" + "="*70)
    print("TEST 1: Data Gap Fixes")
    print("="*70)
    
    test_cases = [
        ("How do I check my tire pressure?", "vehicle", "civilian vehicle query should return results"),
        ("What is the recommended oil change interval?", "vehicle", "civilian vehicle maintenance query"),
        ("How do I clean the AC filter?", "hvac", "HVAC maintenance query (expanded corpus)"),
        ("Air conditioner is not cooling properly", "hvac", "HVAC troubleshooting (expanded corpus)"),
    ]
    
    for query, expected_domain, description in test_cases:
        print(f"\nQuery: {query}")
        print(f"Expected domain: {expected_domain}")
        print(f"Test: {description}")
        
        try:
            results = retrieve_with_phase2(
                query=query,
                k=12,
                top_n=6,
                enable_evidence_tracking=False,  # Suppress evidence output for cleaner logs
                enable_domain_caps=True,
                enable_router_filtering=True
            )
            
            if not results:
                print(f"  [FAIL] No results returned (data gap still exists)")
                continue
            
            # Check if expected domain is present
            domains = [r.get('domain', 'unknown') for r in results]
            if expected_domain in domains:
                print(f"  [PASS] Results found in expected domain '{expected_domain}'")
                print(f"  Domains: {set(domains)}")
                print(f"  Top result: {results[0].get('text', '')[:100]}...")
            else:
                print(f"  [WARN] Expected domain '{expected_domain}' not in results")
                print(f"  Domains: {set(domains)}")
        
        except Exception as e:
            print(f"  [ERROR] {e}")


def test_keyword_refinement():
    """Test that refined keywords improve domain routing."""
    print("\n" + "="*70)
    print("TEST 2: Keyword Refinement Effectiveness")
    print("="*70)
    
    test_cases = [
        ("multiscan weather radar operation", "radar", ["multiscan", "weather"]),
        ("air conditioner cooling filter", "hvac", ["air", "conditioner", "cooling", "filter"]),
        ("hydraulic pallet forklift", "forklift", ["hydraulic", "pallet"]),
        ("sedan battery transmission", "vehicle", ["sedan", "battery", "transmission"]),
        ("tactical convoy military vehicle", "vehicle_military", ["tactical", "convoy"]),
    ]
    
    # Import router for direct testing
    try:
        from core.retrieval.domain_router import infer_domain_candidates, DEFAULT_KEYWORDS
    except ImportError:
        print("[SKIP] Domain router not available")
        return
    
    for query, expected_domain, new_keywords in test_cases:
        print(f"\nQuery: {query}")
        print(f"New keywords tested: {new_keywords}")
        
        scores = infer_domain_candidates(
            query=query,
            index_dir=Path("vector_db"),
            keyword_map=DEFAULT_KEYWORDS
        )
        
        if not scores:
            print(f"  [FAIL] No domain scores returned")
            continue
        
        # infer_domain_candidates returns (candidates, scores_dict)
        if isinstance(scores, tuple):
            candidates, scores_dict = scores
            top_domain = max(scores_dict.items(), key=itemgetter(1))[0] if scores_dict else None
            scores = scores_dict
        else:
            top_domain = max(scores.items(), key=itemgetter(1))[0]
        
        if top_domain == expected_domain:
            print(f"  [PASS] Top domain '{top_domain}' matches expected '{expected_domain}'")
            print(f"  Scores: {scores}")
        else:
            print(f"  [WARN] Top domain '{top_domain}' != expected '{expected_domain}'")
            print(f"  Scores: {scores}")


def test_evidence_tracking():
    """Test evidence tracking integration."""
    print("\n" + "="*70)
    print("TEST 3: Evidence Tracking Integration")
    print("="*70)
    
    query = "How do I change my oil?"
    print(f"\nQuery: {query}")
    
    try:
        chunks, evidence = retrieve_with_evidence(
            query=query,
            k=12,
            top_n=6
        )
        
        if evidence and "ROUTER" in evidence:
            print("[PASS] Evidence tracking captured router decision")
        else:
            print("[WARN] Evidence tracking incomplete")
        
        if evidence and "GAR" in evidence:
            print("[PASS] Evidence tracking captured GAR expansion")
        else:
            print("[WARN] GAR evidence not captured")
        
        if evidence and "FINAL" in evidence:
            print("[PASS] Evidence tracking captured final selection")
        else:
            print("[WARN] Final selection evidence not captured")
        
        print("\nEvidence Summary:")
        print(evidence)
    
    except Exception as e:
        print(f"[ERROR] Evidence tracking failed: {e}")


def test_domain_caps():
    """Test per-domain caps enforcement."""
    print("\n" + "="*70)
    print("TEST 4: Per-Domain Caps Enforcement")
    print("="*70)
    
    # Use a query that might return many forklift results
    query = "engine maintenance hydraulic oil"
    print(f"\nQuery: {query}")
    print("Testing with NOVA_MAX_CHUNKS_PER_DOMAIN=3")
    
    try:
        results = retrieve_with_phase2(
            query=query,
            k=12,
            top_n=6,
            enable_evidence_tracking=False,
            enable_domain_caps=True
        )
        
        # Count chunks per domain
        from collections import Counter
        domain_counts = Counter(r.get('domain', 'unknown') for r in results)
        
        print(f"\nDomain distribution:")
        for domain, count in domain_counts.items():
            print(f"  {domain}: {count} chunks")
        
        # Check if any domain exceeds cap
        max_per_domain = 3
        violations = [d for d, c in domain_counts.items() if c > max_per_domain]
        
        if violations:
            print(f"[FAIL] Domains exceeding cap ({max_per_domain}): {violations}")
        else:
            print(f"[PASS] All domains respect cap of {max_per_domain} chunks")
    
    except Exception as e:
        print(f"[ERROR] Domain caps test failed: {e}")


def test_router_filtering():
    """Test router filtering functionality."""
    print("\n" + "="*70)
    print("TEST 5: Router Filtering Functionality")
    print("="*70)
    
    test_cases = [
        ("radar weather detection", "radar", True, "High confidence - should NOT filter"),
        ("operating procedures", None, True, "Ambiguous - might filter"),
    ]
    
    try:
        from core.retrieval.domain_router import should_filter_with_domain
    except ImportError:
        print("[SKIP] Domain router not available")
        return
    
    for query, expected_domain, should_work, description in test_cases:
        print(f"\nQuery: {query}")
        print(f"Test: {description}")
        
        should_filter, message = should_filter_with_domain(query)
        
        if should_filter:
            print(f"  [INFO] Router filtering triggered: {message}")
        else:
            print(f"  [INFO] Router passed query through")


def main():
    parser = argparse.ArgumentParser(description="Validate Phase 2.5 implementation")
    parser.add_argument('--enable-all', action='store_true', help='Enable all Phase 2 features')
    args = parser.parse_args()
    
    if args.enable_all:
        print("[CONFIG] All Phase 2.5 features enabled")
    else:
        print("[CONFIG] Default Phase 2.5 configuration")
    
    print("\n" + "="*70)
    print("PHASE 2.5 VALIDATION SUITE")
    print("="*70)
    print(f"NOVA_EVIDENCE_TRACKING: {os.environ.get('NOVA_EVIDENCE_TRACKING')}")
    print(f"NOVA_MAX_CHUNKS_PER_DOMAIN: {os.environ.get('NOVA_MAX_CHUNKS_PER_DOMAIN')}")
    print(f"NOVA_ROUTER_FILTERING: {os.environ.get('NOVA_ROUTER_FILTERING')}")
    
    # Run all tests
    test_data_gap_fixes()
    test_keyword_refinement()
    test_evidence_tracking()
    test_domain_caps()
    test_router_filtering()
    
    print("\n" + "="*70)
    print("VALIDATION COMPLETE")
    print("="*70)
    print("\nReview results above for any failures or warnings.")
    print("Next step: Run full cross-contamination test with Phase 2.5 features enabled")


if __name__ == '__main__':
    main()
