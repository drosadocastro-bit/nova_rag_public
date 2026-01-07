# NIC Public - RAGAS Evaluation Results

## Overview

RAGAS (Retrieval Augmented Generation Assessment) provides LLM-based evaluation of RAG pipeline quality. This document summarizes NIC's RAGAS evaluation results.

---

## Evaluation Configuration

| Parameter | Value |
|-----------|-------|
| Evaluator Model | qwen2.5-coder-14b (via Ollama) |
| Evaluation Mode | LLM-only (no embeddings) |
| Context Window | 16384 tokens |
| Output Format | JSON (strict) |
| Temperature | 0.0 (deterministic) |

---

## Metrics Evaluated

### Faithfulness
**Definition:** Measures whether the generated answer is grounded in the retrieved context.

**Calculation:** 
- Extract claims from the answer
- Verify each claim against context
- Score = (supported claims) / (total claims)

**Target:** > 50%

---

### Answer Relevancy
**Definition:** Measures whether the answer addresses the question.

**Note:** Requires embeddings; currently disabled in LLM-only mode.

---

## Latest Results

### Run: January 6, 2026

| Metric | Score | Samples |
|--------|-------|---------|
| Faithfulness | 30.00% | 5 |
| Answer Relevancy | N/A | - |

### Per-Sample Breakdown

| Question | Faithfulness |
|----------|-------------|
| Engine cranks but won't start | 100% ✅ |
| Torque spec for lug nuts | 0% |
| Temperature gauge reading high | 50% |
| Test alternator charging | 0% |
| Diagnostic code P0420 | 0% |

---

## Historical Results

| Date | Samples | Faithfulness | Notes |
|------|---------|--------------|-------|
| 2026-01-06 | 5 | 30.00% | ChatOllama + JSON mode |
| 2026-01-06 | 3 | 26.19% | First successful run |
| 2026-01-05 | 10 | 16.67% | JSON parsing issues |

---

## Analysis

### High Performers
- **Engine cranks but won't start** (100%): Well-structured response with clear citations from retrieved context.

### Low Performers
- Queries where NIC used **retrieval-only fallback** score 0% because the evaluator can't trace JSON-formatted snippets back to context.
- Queries where the **LLM timed out** also score poorly.

### Root Causes
1. **Response format mismatch**: RAGAS expects natural language; NIC sometimes returns structured JSON
2. **Context overflow**: Native engine hitting 30k token limit
3. **Fallback responses**: Snippet-only responses don't follow expected format

---

## Improvements Made

1. ✅ Switched to `ChatOllama` for native Ollama parameter support
2. ✅ Enabled `format="json"` to eliminate code fence issues
3. ✅ Increased `num_ctx=16384` for full RAGAS prompts
4. ✅ Increased `num_predict=2048` for complete JSON outputs
5. ✅ Set `temperature=0.0` for deterministic evaluation

---

## Running RAGAS Evaluation

```bash
# Ensure Flask server is running
python nova_flask_app.py &

# Run evaluation (N samples)
python nic_ragas_eval.py 10

# Results saved to ragas_results/
```

---

## Result Files

| File | Description |
|------|-------------|
| `ragas_results/ragas_report_*.json` | Full evaluation report |
| `ragas_results/ragas_scores_*.csv` | Per-sample scores |

---

## Future Work

1. **Enable embedding-based metrics** once embeddings are integrated with RAGAS
2. **Improve response formatting** to match RAGAS expectations
3. **Fix context overflow** in native LLM engine
4. **Add more test samples** to QA dataset
5. **Automate periodic evaluation** via CI/CD

---

## Related Documents

- [EVALUATION_SUMMARY.md](EVALUATION_SUMMARY.md) - Overall evaluation overview
- [ADVERSARIAL_TESTS.md](ADVERSARIAL_TESTS.md) - Security testing
- [../safety/HALLUCINATION_DEFENSE.md](../safety/HALLUCINATION_DEFENSE.md) - Hallucination prevention
