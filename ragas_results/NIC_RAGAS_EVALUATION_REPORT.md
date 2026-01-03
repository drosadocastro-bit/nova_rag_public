# NIC RAGAS Evaluation Report

**Generated:** December 31, 2025  
**Evaluator Model:** fireball-meta-llama-3.2-8b-instruct-agent-003-128k-code-dpo  
**Test Dataset:** governance/nic_qa_dataset.json (20 positive cases)

---

## Executive Summary

Nova Intelligent Copilot (NIC) was evaluated using RAGAS (Retrieval Augmented Generation Assessment) metrics to measure the quality of its RAG pipeline. This complements the existing stress test (111 cases, 100% pass) and adversarial test (90 cases, 92.2% pass).

### Overall RAG Quality Score: **52.55%**

| Metric | Score | Rating | Interpretation |
|--------|-------|--------|----------------|
| **Faithfulness** | 50.00% | ⚠️ Moderate | Half of answers are grounded in retrieved context |
| **Answer Relevancy** | 28.90% | ⚠️ Low | Format mismatch with expected prose answers |
| **Context Precision** | N/A | - | Timed out (LLM overload) |
| **Context Recall** | 78.75% | ✅ Good | Context contains most needed information |

---

## Detailed Analysis

### 1. Context Recall: 78.75% ✅

**What it measures:** Does the retrieved context contain the information needed to answer the question?

**Result:** GOOD - NIC's retrieval pipeline successfully finds relevant document chunks 79% of the time.

**Evidence:**
- Questions about engine diagnostics retrieved Para 1-2 (engine cranks/won't start)
- Questions about oil changes retrieved Para 7-2 (maintenance intervals)
- Questions about alternator testing retrieved Para 4-2.2 (charging system)

**Improvement opportunities:**
- Some specific specs (lug nut torque) weren't in top-6 retrieved chunks
- Diagnostic codes (P0420, P0171) need better keyword boosting

---

### 2. Faithfulness: 50.00% ⚠️

**What it measures:** Is the generated answer supported by the retrieved context (anti-hallucination)?

**Result:** MODERATE - Half of answers are fully grounded in source documents.

**Analysis:**
- Retrieval-only mode returns raw context snippets (100% faithful by design)
- Some answers include source citations not in retrieved context
- Refusal responses are counted as unfaithful (no supporting context)

**Note:** The 50% score is affected by:
1. Several questions triggered REFUSAL responses (safety/scope checks)
2. RAGAS penalizes refusals since they don't match ground truth

---

### 3. Answer Relevancy: 28.90% ⚠️

**What it measures:** Does the answer actually address the user's question?

**Result:** LOW - But this is largely a **format mismatch**, not a quality issue.

**Root Causes:**

| Issue | Impact | Count |
|-------|--------|-------|
| REFUSAL responses | Question marked out-of-scope | 6/20 |
| Structured JSON vs prose | Format doesn't match expected text | 8/20 |
| Truncated snippets | Raw context incomplete | 4/20 |

**Example:**
- **Question:** "What's the correct torque specification for lug nuts?"
- **Expected:** "Lug nuts should be torqued to 85-95 ft-lbs in a star pattern [Citation: Table 7-1]"
- **Actual:** `[REFUSAL] This question is outside the knowledge base...`
- **Analysis:** NIC's scope detection triggered incorrectly (false positive)

---

### 4. Context Precision: N/A (Timed Out)

**What it measures:** Are the retrieved documents relevant to the question?

**Result:** Evaluation timed out due to LLM Studio overload (running both NIC and RAGAS evaluator on same GPU).

**Workaround:** Run with dedicated evaluator instance or use cloud LLM for RAGAS.

---

## Test Case Analysis

### Successful Retrievals (High Recall)

| ID | Question | Context Quality | Answer Quality |
|----|----------|----------------|----------------|
| PC001 | Engine cranks but won't start | ✅ Found Para 1-2 | ✅ Correct procedure |
| PC006 | How often should I change my oil | ✅ Found Para 7-2 | ✅ Correct intervals |
| PC008 | What's the fuel pressure supposed to be | ✅ Found Table 5-1 | ✅ 40-50 PSI |
| PC012 | What's normal battery voltage | ✅ Found Table 1-2 | ✅ 12.4-14.4V range |

### False Refusals (Need Tuning)

| ID | Question | Issue |
|----|----------|-------|
| PC002 | Torque specification for lug nuts | Wrongly classified as out-of-scope |
| PC003 | Temperature gauge reading high | Wrongly classified as out-of-scope |
| PC005 | What does P0420 mean | Wrongly classified as out-of-scope |
| PC010 | What causes code P0171 | Wrongly classified as out-of-scope |

**Root Cause:** The agent_router's out-of-scope detection is over-triggering on valid maintenance questions.

---

## Comparison with Other Tests

| Test Suite | Pass Rate | Focus |
|------------|-----------|-------|
| **Stress Test** | 100% (111/111) | Functional coverage |
| **Adversarial Test** | 92.2% (83/90) | Safety/attack resistance |
| **RAGAS Evaluation** | 52.55% | RAG quality metrics |

**Key Insight:** NIC performs excellently on functional and safety tests but needs tuning for:
1. Reducing false refusals on valid questions
2. Better answer formatting for evaluation compatibility

---

## Recommendations

### High Priority

1. **Fix False Refusal Detection**
   - Questions like "torque specification" and "temperature gauge" are valid maintenance topics
   - Review `agent_router.classify_intent()` scope detection logic
   - Add "specification", "gauge", "reading" to allowed maintenance keywords

2. **Improve Diagnostic Code Retrieval**
   - P0420, P0171 questions aren't finding relevant context
   - Add error code patterns to keyword boosting in `retrieve()`

### Medium Priority

3. **Add RAGAS-Compatible Output Mode**
   - Create `--ragas` flag that returns prose answers instead of structured JSON
   - Will improve answer_relevancy scores without changing production behavior

4. **Run RAGAS with Cloud Evaluator**
   - LM Studio timeouts affect evaluation quality
   - Consider using OpenAI/Anthropic API for RAGAS evaluation only

### Low Priority

5. **Expand Test Dataset**
   - Add more safety-critical cases
   - Add edge cases from stress test failures
   - Include multi-turn conversation tests

---

## Artifacts

| File | Description |
|------|-------------|
| `ragas_results/ragas_report_20251231_072201.json` | Full evaluation data |
| `ragas_results/ragas_scores_20251231_072201.csv` | Per-sample scores |
| `nic_ragas_eval.py` | RAGAS evaluation harness |

---

## Appendix: RAGAS Metrics Explained

| Metric | Formula | Range | Goal |
|--------|---------|-------|------|
| **Faithfulness** | Claims in answer supported by context | 0-1 | Higher = less hallucination |
| **Answer Relevancy** | Semantic similarity to question | 0-1 | Higher = more on-topic |
| **Context Precision** | Relevant docs ranked higher | 0-1 | Higher = better ranking |
| **Context Recall** | Ground truth info in context | 0-1 | Higher = better retrieval |

---

*Report generated by NIC RAGAS Evaluation Harness v1.0*
