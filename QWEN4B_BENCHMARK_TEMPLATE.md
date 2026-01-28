# Qwen 4B Benchmark Template for Potato Hardware Testing

**Purpose:** Establish baseline performance for edge device deployment  
**Target Hardware:** Laptop/Edge device with 4GB VRAM  
**Comparison:** Qwen 4B vs. Llama2 8B vs. Current 14B Model

---

## 1. Execution Plan

### Phase 1: Setup (5-10 min)
- [ ] Download Qwen 4B model (~2.5GB)
- [ ] Configure Ollama with Qwen 4B
- [ ] Verify model loads successfully
- [ ] Check available system resources

### Phase 2: Baseline Measurements (15-20 min)
- [ ] Test with automotive domain (5 questions)
- [ ] Test with hvac domain (5 questions)
- [ ] Test with universal diagnostic pattern (5 questions)
- [ ] Record metrics for each

### Phase 3: Comparative Analysis (20-30 min)
- [ ] Compare Qwen 4B vs. 8B vs. 14B on same 15 questions
- [ ] Analyze speed/accuracy trade-off
- [ ] Document findings

---

## 2. Benchmark Metrics Template

```
Model: Qwen 4B
Hardware: [CPU/GPU specs here]
VRAM Available: [X GB]
Timestamp: [ISO 8601]

PERFORMANCE METRICS
==================
avg_latency_ms: [milliseconds from question to answer]
p50_latency_ms: [median latency]
p95_latency_ms: [95th percentile latency]
tokens_per_second: [throughput]

QUALITY METRICS
===============
accuracy_score: [0.0-1.0]
hallucination_count: [# of hallucinations in 15 questions]
citation_accuracy: [# with correct sources / total]
relevance_score: [0.0-1.0 avg]

DOMAIN PERFORMANCE
==================
automotive_accuracy: [0.0-1.0]
hvac_accuracy: [0.0-1.0]
aerospace_accuracy: [0.0-1.0]
medical_accuracy: [0.0-1.0]
nuclear_accuracy: [0.0-1.0]
universal_accuracy: [0.0-1.0]

RESOURCE USAGE
==============
peak_vram_mb: [max memory used]
avg_vram_mb: [average during inference]
cpu_usage_percent: [average CPU %]
disk_io_mb_per_sec: [if using disk swap]

VIABILITY ASSESSMENT
====================
potato_hardware_viable: [yes/no]
edge_deployment_ready: [yes/no]
battery_life_hours: [if on mobile]
reliability_score: [0.0-1.0]
```

---

## 3. Test Questions by Priority

### Tier 1: Critical Path (5 questions - 5 min)
**Automotive domain, foundational questions:**
```
1. "How do I check the alternator voltage?"
2. "What's the battery specification for this vehicle?"
3. "How do I diagnose a starter motor problem?"
4. "What's the tire pressure specification?"
5. "How do I check the engine oil level?"
```

**Expected:** All 5 should be answerable from automotive manuals

### Tier 2: Cross-Domain (5 questions - 5 min)
**HVAC + Medical + Electronics:**
```
1. "What's the refrigerant specification?" [HVAC]
2. "How do I check the device calibration?" [Medical]
3. "How do I check the power supply voltage?" [Electronics]
4. "How do I diagnose a thermostat problem?" [HVAC]
5. "What's the sensor accuracy specification?" [Medical]
```

**Expected:** Cross-domain generalization test

### Tier 3: Advanced Diagnostic (5 questions - 5 min)
**Universal patterns, edge cases:**
```
1. "How do I interpret system error codes?"
2. "What's the procedure for documenting maintenance activities?"
3. "How do I diagnose intermittent problems?"
4. "What's the escalation procedure for unresolved issues?"
5. "How do I verify system integrity after maintenance?"
```

**Expected:** Reasoning and procedural understanding

---

## 4. Scoring Framework

### Accuracy Scoring (0-1.0)
```
1.0 = Perfect answer with correct citations
0.8 = Correct answer with partial citations
0.6 = Mostly correct but missing details
0.4 = Partially correct but significant gaps
0.2 = Wrong answer but attempts RAG
0.0 = Hallucination or no attempt
```

### Citation Accuracy (0-1.0)
```
1.0 = All claims cited with document names
0.8 = Claims cited but page numbers missing
0.6 = Some claims cited
0.4 = Minimal citation
0.0 = No citations (all "unknown")
```

### Latency Categories
```
< 1s:   🟢 Excellent (suitable for real-time)
1-3s:   🟡 Good (acceptable for most use cases)
3-5s:   🟠 Acceptable (borderline for edge)
> 5s:   🔴 Poor (not suitable for potato hardware)
```

---

## 5. Comparison Matrix (Expected Results)

| Metric | Qwen 4B | Qwen 8B | Current 14B | Target |
|--------|---------|---------|------------|--------|
| **Latency (ms)** | 800-1200 | 600-900 | 400-600 | < 1200 |
| **Throughput (t/s)** | 15-25 | 25-35 | 35-50 | > 15 |
| **Accuracy** | 0.75-0.85 | 0.80-0.90 | 0.88-0.95 | > 0.75 |
| **VRAM (GB)** | 4 | 6 | 14 | 4 |
| **Model Size** | 4B | 8B | 14B | 4B |
| **Potato Ready** | ✅ YES | ⚠️ Maybe | ❌ NO | ✅ YES |

---

## 6. Data Collection Template

### For Each Question:
```json
{
  "question_id": "Q001",
  "question_text": "How do I check the alternator voltage?",
  "domain": "automotive",
  "model": "Qwen 4B",
  "timestamp": "2026-01-28T14:30:00Z",
  "latency_ms": 847,
  "tokens_generated": 124,
  "response_text": "[response here]",
  "sources_found": ["TM-10-3930-763-10 p12", "unknown"],
  "accuracy_score": 0.9,
  "citation_accuracy": 0.5,
  "hallucination_detected": false,
  "notes": "Good answer but citation missing for voltage range"
}
```

---

## 7. Success Criteria for Qwen 4B

### Minimum Viable
- ✅ Model loads on 4GB VRAM
- ✅ Average latency < 2 seconds
- ✅ Accuracy > 0.70 on automotive
- ✅ Zero crashes in 15-question test
- ✅ Citations present (even if some "unknown")

### Recommended
- ✅ Average latency < 1.5 seconds
- ✅ Accuracy > 0.75 across domains
- ✅ Citation accuracy > 0.60
- ✅ Hallucination rate < 5%
- ✅ VRAM peak < 3.5GB (headroom)

### Optimal
- ✅ Average latency < 1 second
- ✅ Accuracy > 0.80 across domains
- ✅ Citation accuracy > 0.80
- ✅ Hallucination rate < 2%
- ✅ Suitable for production edge deployment

---

## 8. Test Execution Script

```bash
#!/bin/bash
# Run comprehensive Qwen 4B benchmark

echo "=== Qwen 4B Benchmark Suite ==="
echo "Start Time: $(date)"

# Phase 1: Model verification
echo "Phase 1: Verifying Qwen 4B model..."
python -c "import ollama; print(ollama.list())"

# Phase 2: Tier 1 tests (automotive - critical path)
echo "Phase 2: Running Tier 1 tests (automotive)..."
python benchmark_runner.py --tier 1 --model qwen:4b --output tier1_results.json

# Phase 3: Tier 2 tests (cross-domain)
echo "Phase 3: Running Tier 2 tests (cross-domain)..."
python benchmark_runner.py --tier 2 --model qwen:4b --output tier2_results.json

# Phase 4: Tier 3 tests (advanced diagnostic)
echo "Phase 4: Running Tier 3 tests (advanced)..."
python benchmark_runner.py --tier 3 --model qwen:4b --output tier3_results.json

# Phase 5: Analysis
echo "Phase 5: Analyzing results..."
python analyze_benchmark.py tier1_results.json tier2_results.json tier3_results.json

echo "End Time: $(date)"
echo "Results saved to benchmark_report_$(date +%Y%m%d_%H%M%S).md"
```

---

## 9. Expected Output Report

```
QWEN 4B BENCHMARK REPORT
========================
Generated: 2026-01-28
Hardware: Potato (4GB VRAM)

TIER 1: AUTOMOTIVE (Critical Path)
Accuracy: 82% (4.1/5 questions correct)
Latency: 923ms average
Citations: 80% (4/5 with sources)

TIER 2: CROSS-DOMAIN (Generalization)
Accuracy: 78% (3.9/5 questions correct)
Latency: 1045ms average
Citations: 75% (3.75/5 with sources)

TIER 3: ADVANCED (Reasoning)
Accuracy: 72% (3.6/5 questions correct)
Latency: 1204ms average
Citations: 60% (3/5 with sources)

OVERALL SCORE
Weighted Accuracy: 77.3%
Weighted Latency: 1024ms
Viable for Potato Hardware: YES ✅
Recommended for Production: WITH CAUTION ⚠️

VIABILITY ASSESSMENT
✅ Meets minimum VRAM requirements (4GB)
✅ Acceptable latency for edge devices
⚠️ Accuracy trade-off acceptable for lightweight use cases
⚠️ Citation system needs improvement
✅ Suitable for offline/edge deployment
❌ Not recommended for high-accuracy critical systems

RECOMMENDATIONS
1. Use Qwen 4B for lightweight edge deployment
2. Use 8B model for balanced performance
3. Use 14B model for critical/high-accuracy tasks
4. Implement caching for common questions
5. Consider ensemble approach: 4B + retrieval-only fallback
```

---

## 10. Next Steps After Benchmark

- [ ] Compare with Qwen 8B results
- [ ] Generate performance scaling curve
- [ ] Document trade-offs for different hardware tiers
- [ ] Create deployment recommendations matrix
- [ ] Plan optimization strategies (quantization, pruning)

---

**Start Time:** [When Qwen 4B finishes downloading]  
**Estimated Duration:** 45-60 minutes total  
**Output Location:** `benchmark_results_qwen4b_[timestamp].json`

