#!/usr/bin/env python3
"""
Adaptive Threshold Recommender for Domain Router

Analyzes router monitoring logs to recommend optimal DOMAIN_FILTER_THRESHOLD
based on contamination vs filter activation tradeoff.

Usage:
    python scripts/recommend_threshold.py --log nova_router_monitoring.log
    python scripts/recommend_threshold.py --analyze-range 0.3 0.5 --step 0.05
"""
import json
import sys
import argparse
from collections import defaultdict
from pathlib import Path


def load_router_logs(log_path: str) -> list[dict]:
    """Load JSON router monitoring logs."""
    logs = []
    if not Path(log_path).exists():
        print(f"[ERROR] Log file not found: {log_path}")
        return []
    
    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
    
    return logs


def analyze_threshold_performance(logs: list[dict], threshold: float) -> dict:
    """
    Simulate performance at given threshold.
    
    Returns:
        dict with metrics:
            - total_queries: int
            - filtered_queries: int (would be filtered at this threshold)
            - filter_rate: float
            - avg_confidence: float (when filtering would trigger)
            - contamination_prevented: int (estimated cross-domain contaminations avoided)
    """
    filtered = 0
    total = 0
    confidences = []
    contamination_prevented = 0
    
    for entry in logs:
        if entry.get('event') != 'domain_inference':
            continue
        
        total += 1
        scores = entry.get('scores', {})
        if not scores:
            continue
        
        # Get top domain and confidence
        top_domain = max(scores, key=scores.get)
        confidence = scores[top_domain]
        
        # Would this query be filtered at this threshold?
        if confidence >= threshold:
            filtered += 1
            confidences.append(confidence)
            
            # Estimate contamination prevention:
            # If second-best domain score is high, filtering prevents contamination
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2:
                second_best = sorted_scores[1]
                # If second-best is close to top (ambiguous query), filtering helps
                if second_best > 0.3 * confidence:
                    contamination_prevented += 1
    
    return {
        'total_queries': total,
        'filtered_queries': filtered,
        'filter_rate': filtered / total if total > 0 else 0.0,
        'avg_confidence': sum(confidences) / len(confidences) if confidences else 0.0,
        'contamination_prevented': contamination_prevented,
    }


def recommend_threshold(log_path: str, min_thresh: float = 0.25, max_thresh: float = 0.55, step: float = 0.05):
    """
    Analyze logs and recommend optimal threshold.
    
    Strategy:
        - Too low: Filters too many queries (over-aggressive)
        - Too high: Misses contamination opportunities (under-protective)
        - Optimal: Balance between filter rate and contamination prevention
    """
    logs = load_router_logs(log_path)
    if not logs:
        print("[ERROR] No valid logs found")
        return
    
    print(f"\n{'='*70}")
    print(f"ADAPTIVE THRESHOLD ANALYSIS")
    print(f"{'='*70}")
    print(f"Log file: {log_path}")
    print(f"Total log entries: {len(logs)}")
    print(f"Threshold range: {min_thresh:.2f} - {max_thresh:.2f} (step {step:.2f})\n")
    
    # Analyze performance across threshold range
    results = []
    thresholds = []
    current = min_thresh
    while current <= max_thresh:
        thresholds.append(current)
        perf = analyze_threshold_performance(logs, current)
        results.append(perf)
        current += step
    
    # Print table
    print(f"{'Threshold':<12} {'Filter Rate':<14} {'Avg Confidence':<18} {'Contamination':<20}")
    print(f"{'':12} {'':14} {'(when filtering)':<18} {'Prevented':<20}")
    print(f"{'-'*70}")
    
    best_idx = 0
    best_score = 0.0
    
    for i, (thresh, perf) in enumerate(zip(thresholds, results)):
        filter_rate = perf['filter_rate']
        avg_conf = perf['avg_confidence']
        contam_prev = perf['contamination_prevented']
        
        # Scoring heuristic:
        # - Prefer moderate filter rates (20-40%)
        # - Maximize contamination prevention
        # - Penalize extreme filter rates (too aggressive or too passive)
        ideal_filter_rate = 0.30
        filter_score = 1.0 - abs(filter_rate - ideal_filter_rate)
        contam_score = contam_prev / perf['total_queries'] if perf['total_queries'] > 0 else 0.0
        
        # Combined score: 40% filter balance + 60% contamination prevention
        score = 0.4 * filter_score + 0.6 * contam_score
        
        if score > best_score:
            best_score = score
            best_idx = i
        
        marker = " <- RECOMMENDED" if i == best_idx else ""
        print(f"{thresh:<12.2f} {filter_rate:<14.1%} {avg_conf:<18.3f} {contam_prev:<20}{marker}")
    
    print(f"{'-'*70}")
    recommended = thresholds[best_idx]
    print(f"\n[RECOMMENDATION] Set DOMAIN_FILTER_THRESHOLD = {recommended:.2f}")
    print(f"  Filter Rate: {results[best_idx]['filter_rate']:.1%}")
    print(f"  Contamination Prevented: {results[best_idx]['contamination_prevented']} queries")
    print(f"  Avg Confidence (when filtering): {results[best_idx]['avg_confidence']:.3f}")
    
    # Additional guidance
    print(f"\n[CONFIGURATION GUIDANCE]")
    print(f"  Add to your environment or config:")
    print(f"    export DOMAIN_FILTER_THRESHOLD={recommended:.2f}")
    print(f"  Or in Python:")
    print(f"    os.environ['DOMAIN_FILTER_THRESHOLD'] = '{recommended:.2f}'")
    
    # Edge case warnings
    if results[best_idx]['filter_rate'] < 0.15:
        print(f"\n[WARNING] Low filter rate - router may not be protecting against contamination enough")
    elif results[best_idx]['filter_rate'] > 0.45:
        print(f"\n[WARNING] High filter rate - may be over-filtering valid queries")
    
    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Recommend optimal domain filter threshold based on monitoring logs"
    )
    parser.add_argument(
        '--log',
        default='nova_router_monitoring.log',
        help='Path to router monitoring log file (default: nova_router_monitoring.log)'
    )
    parser.add_argument(
        '--min-threshold',
        type=float,
        default=0.25,
        help='Minimum threshold to analyze (default: 0.25)'
    )
    parser.add_argument(
        '--max-threshold',
        type=float,
        default=0.55,
        help='Maximum threshold to analyze (default: 0.55)'
    )
    parser.add_argument(
        '--step',
        type=float,
        default=0.05,
        help='Step size for threshold sweep (default: 0.05)'
    )
    
    args = parser.parse_args()
    
    recommend_threshold(
        log_path=args.log,
        min_thresh=args.min_threshold,
        max_thresh=args.max_threshold,
        step=args.step
    )


if __name__ == '__main__':
    main()
