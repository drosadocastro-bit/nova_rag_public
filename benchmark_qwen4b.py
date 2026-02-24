#!/usr/bin/env python3
"""
Qwen 4B Benchmark Runner for NIC
Quick performance test using multi-domain questions
"""

import json
import time
import requests
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5678"
MODEL_NAME = "qwen3:4b"
OUTPUT_FILE = f"benchmark_qwen4b_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

def load_test_questions():
    """Load multi-domain test questions"""
    with open('test_questions_multidomains.json', 'r') as f:
        return json.load(f)

def test_question(question: str, domain: str, question_id: str):
    """Test a single question and measure performance"""
    print(f"\n[{question_id}] Testing: {question[:60]}...")
    
    start_time = time.time()
    
    try:
        response = requests.post(
            f"{BASE_URL}/query",
            params={
                "q": question,
                "domain": domain,
                "mode": "Auto"
            },
            timeout=180  # 3 minutes for slow models
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            answer = data.get("answer", "")
            model_used = data.get("model_used", "unknown")
            
            # Extract sources from answer
            sources_found = []
            if "📚 Sources" in answer or "Sources:" in answer:
                # Simple extraction - look for document names
                import re
                source_matches = re.findall(r'(TM-[\d-]+|[\w_]+\.(?:pdf|txt|docx))', answer)
                sources_found = source_matches
            
            # Check for "unknown" in sources
            has_unknown = "unknown" in answer.lower() if answer else True
            
            result = {
                "question_id": question_id,
                "question": question,
                "domain": domain,
                "timestamp": datetime.now().isoformat(),
                "latency_ms": latency_ms,
                "model_used": model_used,
                "response_text": answer[:500] if answer else "",  # Truncate for readability
                "sources_found": sources_found,
                "has_citations": len(sources_found) > 0,
                "has_unknown_sources": has_unknown,
                "status": "success"
            }
            
            print(f"  [OK] Success - {latency_ms}ms - Citations: {len(sources_found)}")
            return result
            
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
            return {
                "question_id": question_id,
                "question": question,
                "domain": domain,
                "status": "http_error",
                "error": f"HTTP {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        print("  ⏱️ Timeout (>180s)")
        return {
            "question_id": question_id,
            "question": question,
            "domain": domain,
            "status": "timeout"
        }
    except Exception as e:
        print(f"  [ERROR] {e}")
        return {
            "question_id": question_id,
            "question": question,
            "domain": domain,
            "status": "error",
            "error": str(e)
        }

def run_tier1_benchmark():
    """Run Tier 1 benchmark (5 automotive questions)"""
    print("=" * 70)
    print("QWEN 4B BENCHMARK - TIER 1 (Critical Path)")
    print("=" * 70)
    print(f"Model: {MODEL_NAME}")
    print(f"Server: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Load questions
    data = load_test_questions()
    automotive_questions = data["automotive"]["questions"][:5]
    
    results = []
    for i, question in enumerate(automotive_questions, 1):
        result = test_question(question, "automotive", f"T1-Q{i:02d}")
        results.append(result)
        time.sleep(0.5)  # Brief pause between questions
    
    return results

def run_tier2_benchmark():
    """Run Tier 2 benchmark (5 cross-domain questions)"""
    print("\n" + "=" * 70)
    print("TIER 2 (Cross-Domain Generalization)")
    print("=" * 70)
    
    data = load_test_questions()
    
    # Pick 2 from HVAC, 2 from Medical, 1 from Electronics
    tier2_questions = [
        (data["hvac"]["questions"][0], "hvac"),
        (data["hvac"]["questions"][3], "hvac"),
        (data["medical"]["questions"][0], "medical"),
        (data["medical"]["questions"][1], "medical"),
        (data["electronics"]["questions"][0], "electronics"),
    ]
    
    results = []
    for i, (question, domain) in enumerate(tier2_questions, 1):
        result = test_question(question, domain, f"T2-Q{i:02d}")
        results.append(result)
        time.sleep(0.5)
    
    return results

def run_tier3_benchmark():
    """Run Tier 3 benchmark (5 universal/edge case questions)"""
    print("\n" + "=" * 70)
    print("TIER 3 (Advanced Diagnostic)")
    print("=" * 70)
    
    data = load_test_questions()
    tier3_questions = data["cross_domain_edge_cases"]["questions"][:5]
    
    results = []
    for i, question in enumerate(tier3_questions, 1):
        result = test_question(question, "universal", f"T3-Q{i:02d}")
        results.append(result)
        time.sleep(0.5)
    
    return results

def analyze_results(all_results):
    """Analyze benchmark results and generate report"""
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS ANALYSIS")
    print("=" * 70)
    
    successful = [r for r in all_results if r.get("status") == "success"]
    
    if not successful:
        print("[ERROR] No successful queries!")
        return
    
    # Latency stats
    latencies = [r["latency_ms"] for r in successful]
    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    
    # Citation stats
    with_citations = sum(1 for r in successful if r.get("has_citations", False))
    with_unknown = sum(1 for r in successful if r.get("has_unknown_sources", False))
    
    print("\n[METRICS] PERFORMANCE METRICS")
    print(f"  Total Questions: {len(all_results)}")
    print(f"  Successful: {len(successful)}")
    print(f"  Failed: {len(all_results) - len(successful)}")
    print("\n⏱️ LATENCY")
    print(f"  Average: {avg_latency:.0f}ms")
    print(f"  Min: {min_latency}ms")
    print(f"  Max: {max_latency}ms")
    print("\n📚 CITATIONS")
    print(f"  With Citations: {with_citations}/{len(successful)} ({with_citations/len(successful)*100:.0f}%)")
    print(f"  With 'unknown': {with_unknown}/{len(successful)} ({with_unknown/len(successful)*100:.0f}%)")
    
    # Viability assessment
    print("\n🎯 VIABILITY ASSESSMENT")
    viable = avg_latency < 1200 and len(successful) >= 12
    print(f"  Potato Hardware Viable: {'[YES]' if viable else '[NO]'}")
    
    if avg_latency < 1000:
        print("  Latency Grade: 🟢 Excellent (< 1s)")
    elif avg_latency < 1500:
        print("  Latency Grade: 🟡 Good (1-1.5s)")
    elif avg_latency < 2000:
        print("  Latency Grade: 🟠 Acceptable (1.5-2s)")
    else:
        print("  Latency Grade: 🔴 Poor (> 2s)")
    
    return {
        "total_questions": len(all_results),
        "successful": len(successful),
        "avg_latency_ms": avg_latency,
        "min_latency_ms": min_latency,
        "max_latency_ms": max_latency,
        "citation_rate": with_citations / len(successful) if successful else 0,
        "unknown_rate": with_unknown / len(successful) if successful else 0,
        "viable": viable
    }

def main():
    """Run complete benchmark suite"""
    print("\n[BENCHMARK] Starting Qwen 4B Benchmark Suite")
    print(f"Output will be saved to: {OUTPUT_FILE}\n")
    
    all_results = []
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"[ERROR] Server not responding properly at {BASE_URL}")
            print("   Make sure FastAPI server is running: .\\start_fastapi_qwen4b.ps1")
            return
    except:
        print(f"[ERROR] Cannot connect to {BASE_URL}")
        print("   Make sure FastAPI server is running: .\\start_fastapi_qwen4b.ps1")
        return
    
    # Run all tiers
    tier1_results = run_tier1_benchmark()
    all_results.extend(tier1_results)
    
    tier2_results = run_tier2_benchmark()
    all_results.extend(tier2_results)
    
    tier3_results = run_tier3_benchmark()
    all_results.extend(tier3_results)
    
    # Analyze
    summary = analyze_results(all_results)
    
    # Save results
    output = {
        "metadata": {
            "model": MODEL_NAME,
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(all_results),
            "server_url": BASE_URL
        },
        "summary": summary,
        "tier1_results": tier1_results,
        "tier2_results": tier2_results,
        "tier3_results": tier3_results
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to: {OUTPUT_FILE}")
    print("\n[COMPLETE] Benchmark complete!")

if __name__ == "__main__":
    main()
