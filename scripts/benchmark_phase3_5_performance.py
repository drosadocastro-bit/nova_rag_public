#!/usr/bin/env python3
"""
Phase 3.5 Performance Benchmarking Script

Measures latency overhead of Phase 3.5 features:
- Finetuned embeddings (Task 7)
- Anomaly detection (Task 8)
- Compliance reporting (Task 9)
- Neural Advisory Layer orchestration (Task 10)

Target: <15ms additional latency compared to baseline
"""

import os
import sys
import json
import time
import statistics
import requests
from typing import Dict, List, Tuple
from datetime import datetime

# Configuration
API_URL = os.environ.get("NIC_API_URL", "http://localhost:5000/api/ask")
API_TOKEN = os.environ.get("NOVA_API_TOKEN", "")
WARMUP_RUNS = 5
BENCH_RUNS = 25
RESULTS_FILE = "phase3_5_benchmark_results.json"

BASE_HEADERS = {"Content-Type": "application/json"}
if API_TOKEN:
    BASE_HEADERS["X-API-TOKEN"] = API_TOKEN

# Test queries - representative vehicle manual queries
TEST_QUERIES = [
    "What is the recommended tire pressure for a 2020 Honda Civic?",
    "How often should I change the engine oil?",
    "What type of coolant should I use?",
    "How do I jump start the vehicle?",
    "What is the proper brake fluid type?",
    "When should I rotate the tires?",
    "How do I check the transmission fluid level?",
    "What is the fuel tank capacity?",
    "How do I replace the air filter?",
    "What is the warranty coverage for the battery?",
]

print("=" * 80)
print("PHASE 3.5 PERFORMANCE BENCHMARKING")
print("=" * 80)
print()

# Check server is running
print("[1/3] Checking API availability...")
try:
    response = requests.get(API_URL.replace("/api/ask", "/api/status"), timeout=5)
    status = response.json()
    print(f"✓ API is running: {status.get('status', 'unknown')}")
except Exception as e:
    print(f"✗ API unavailable: {e}")
    print("  Please start the server first: python nova_flask_app.py")
    sys.exit(1)

print()

def run_benchmark(query: str, enabled_features: Dict[str, bool], iterations: int = BENCH_RUNS) -> Dict:
    """Run performance benchmark for a single query."""
    latencies = []
    errors = []
    
    # Feature flags to enable
    feature_flags = {
        "NOVA_USE_FINETUNED_EMBEDDINGS": enabled_features.get("finetuned_embeddings", False),
        "NOVA_USE_ANOMALY_DETECTION": enabled_features.get("anomaly_detection", False),
        "NOVA_AUTO_COMPLIANCE_REPORTS": enabled_features.get("compliance_reports", False),
    }
    
    for i in range(iterations):
        try:
            payload: Dict[str, object] = {
                "query": query,
                "session_id": f"bench_{int(time.time() * 1000)}_{i}",
            }
            
            # Add feature flags to request
            for flag, value in feature_flags.items():
                payload[flag] = value
            
            start = time.time()
            response = requests.post(API_URL, json=payload, headers=BASE_HEADERS, timeout=30)
            elapsed = (time.time() - start) * 1000  # Convert to milliseconds
            
            if response.status_code == 200:
                latencies.append(elapsed)
            else:
                errors.append(f"Status {response.status_code}")
        except Exception as e:
            errors.append(str(e))
    
    if not latencies:
        return {
            "error": f"All {iterations} iterations failed",
            "errors": errors[:5],  # Show first 5 errors
        }
    
    return {
        "iterations": len(latencies),
        "mean_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)],
        "p99_ms": sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[0],
        "errors": len(errors),
    }

print("[2/3] Running baseline benchmark (all Phase 3.5 features DISABLED)...")
print()

baseline_results = {}
for i, query in enumerate(TEST_QUERIES, 1):
    print(f"  Baseline {i}/10: ", end="", flush=True)
    
    # Warmup
    run_benchmark(query, {"finetuned_embeddings": False, "anomaly_detection": False, "compliance_reports": False}, WARMUP_RUNS)
    
    # Benchmark
    result = run_benchmark(query, {"finetuned_embeddings": False, "anomaly_detection": False, "compliance_reports": False}, BENCH_RUNS)
    baseline_results[query] = result
    
    if "error" in result:
        print(f"✗ FAILED: {result['error']}")
    else:
        print(f"✓ {result['mean_ms']:.2f}ms (median: {result['median_ms']:.2f}ms, p95: {result['p95_ms']:.2f}ms)")

print()
print("[3/3] Running Phase 3.5 benchmark (all Phase 3.5 features ENABLED)...")
print()

phase3_5_results = {}
for i, query in enumerate(TEST_QUERIES, 1):
    print(f"  Phase3.5 {i}/10: ", end="", flush=True)
    
    # Warmup
    run_benchmark(query, {"finetuned_embeddings": True, "anomaly_detection": True, "compliance_reports": True}, WARMUP_RUNS)
    
    # Benchmark
    result = run_benchmark(query, {"finetuned_embeddings": True, "anomaly_detection": True, "compliance_reports": True}, BENCH_RUNS)
    phase3_5_results[query] = result
    
    if "error" in result:
        print(f"✗ FAILED: {result['error']}")
    else:
        print(f"✓ {result['mean_ms']:.2f}ms (median: {result['median_ms']:.2f}ms, p95: {result['p95_ms']:.2f}ms)")

print()
print("=" * 80)
print("BENCHMARK SUMMARY")
print("=" * 80)
print()

# Calculate overall statistics
baseline_means = [r.get("mean_ms", 0) for r in baseline_results.values() if "error" not in r]
phase3_5_means = [r.get("mean_ms", 0) for r in phase3_5_results.values() if "error" not in r]
overhead_ms = 0.0
overhead_pct = 0.0

if baseline_means and phase3_5_means:
    baseline_avg = statistics.mean(baseline_means)
    phase3_5_avg = statistics.mean(phase3_5_means)
    overhead_ms = phase3_5_avg - baseline_avg
    overhead_pct = (overhead_ms / baseline_avg * 100) if baseline_avg > 0 else 0
    
    print(f"Baseline Average Latency:      {baseline_avg:.2f}ms")
    print(f"Phase 3.5 Average Latency:     {phase3_5_avg:.2f}ms")
    print(f"Absolute Overhead:             {overhead_ms:+.2f}ms")
    print(f"Relative Overhead:             {overhead_pct:+.1f}%")
    print()
    
    # Check against target
    target_overhead = 15.0
    if overhead_ms <= target_overhead:
        status = "✅ PASS"
    else:
        status = "❌ FAIL"
    
    print(f"Target Overhead:               <{target_overhead}ms")
    print(f"Status:                        {status}")
    print()
    
    # Detailed breakdown
    print("Detailed Results:")
    print("-" * 80)
    print(f"{'Query':<50} {'Baseline':<15} {'Phase3.5':<15} {'Overhead':<10}")
    print("-" * 80)
    
    for query in TEST_QUERIES:
        baseline = baseline_results.get(query, {})
        phase3_5 = phase3_5_results.get(query, {})
        
        baseline_mean = baseline.get("mean_ms", 0)
        phase3_5_mean = phase3_5.get("mean_ms", 0)
        overhead = phase3_5_mean - baseline_mean
        
        query_short = query[:47] + "..." if len(query) > 50 else query
        
        print(f"{query_short:<50} {baseline_mean:>6.2f}ms      {phase3_5_mean:>6.2f}ms      {overhead:>+5.2f}ms")
    
    print("-" * 80)

print()

# Save results to JSON
results_json = {
    "timestamp": datetime.now().isoformat(),
    "target_overhead_ms": 15.0,
    "warmup_runs": WARMUP_RUNS,
    "benchmark_runs": BENCH_RUNS,
    "baseline_results": baseline_results,
    "phase3_5_results": phase3_5_results,
    "summary": {
        "baseline_avg_ms": statistics.mean(baseline_means) if baseline_means else 0,
        "phase3_5_avg_ms": statistics.mean(phase3_5_means) if phase3_5_means else 0,
        "overhead_ms": overhead_ms if baseline_means and phase3_5_means else 0,
        "overhead_pct": overhead_pct if baseline_means and phase3_5_means else 0,
        "status": "PASS" if (baseline_means and phase3_5_means and overhead_ms <= 15.0) else "FAIL",
    }
}

with open(RESULTS_FILE, "w") as f:
    json.dump(results_json, f, indent=2)

print(f"Results saved to: {RESULTS_FILE}")
print()

# Final status
if results_json["summary"]["status"] == "PASS":
    print("✅ PHASE 3.5 PERFORMANCE BENCHMARK: PASSED")
    sys.exit(0)
else:
    print("❌ PHASE 3.5 PERFORMANCE BENCHMARK: FAILED")
    print(f"   Overhead: {results_json['summary']['overhead_ms']:.2f}ms (target: <15ms)")
    sys.exit(1)
