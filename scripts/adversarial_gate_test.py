"""
Adversarial Quality Gate Test
=============================
Injects synthetic answers DIRECTLY into the grounding check to determine
whether the gate is purely lexical or has meaningful discriminating power.

Bypasses the LLM entirely — we control the answer text and context docs,
then observe whether the gate lets it through, forces extractive, or abstains.

Threat tiers:
  T1 - Zero overlap       (baseline: should always fail)
  T2 - Low paraphrase     (wrong answer, some shared words)
  T3 - High-overlap wrong (your exact test: plausible, mostly right tokens, factually wrong)
  T4 - Copy-paste correct (should pass — establishes the "accept" boundary)
  T5 - Subtle corruption  (one key fact changed, rest verbatim from source)
  T6 - Hallucinated extra (correct base + fabricated additional claims)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.handlers.query_handler import (
    _tokenize_for_grounding,
    _statement_is_grounded,
    _compute_grounding_ratio,
    _post_generation_quality_gate,
    _build_extractive_response,
)

# ---------------------------------------------------------------------------
# Simulated retrieved context (real chunk from the radar corpus)
# ---------------------------------------------------------------------------
CONTEXT_DOCS = [
    {
        "text": (
            "NWS EHB 6-513  5-57 5.5.3.5  Reflectivity Calibration Factor, dBZ0. "
            "The reflectivity calibration factor dBZ0 is used to calculate reflectivity, dBZ. "
            "dBZ0 is the equivalent radar reflectivity at the reference range where the "
            "return signal power is equal to the noise power (SNR = 0 dB). "
            "The reflectivity algorithm defines dBZ0 as the minimum detectable signal "
            "at a reference range of 1 km. The horizontal receiver and vertical receiver "
            "have individual dBZ0 values."
        ),
        "source": "6-513.pdf",
        "page": 511,
    },
    {
        "text": (
            "Reflectivity is a measure of the fraction of radiation reflected by a "
            "given target. Radar reflectivity factor Z is proportional to the sum of "
            "the sixth power of the diameters of the hydrometeors in a unit volume. "
            "dBZ is the logarithmic representation: dBZ = 10 * log10(Z). "
            "Higher dBZ values indicate more intense precipitation."
        ),
        "source": "6-521rev14fnl.pdf",
        "page": 98,
    },
]


# ---------------------------------------------------------------------------
# Adversarial test cases
# ---------------------------------------------------------------------------
CASES = [
    # --- T1: Zero overlap (baseline — must fail) ---
    {
        "id": "T1-ZERO",
        "tier": "T1",
        "answer": "The quick brown fox jumps over the lazy dog. This has nothing to do with radar.",
        "expected_gate": "extractive_override",
        "description": "Completely unrelated answer — zero token overlap with radar docs",
    },

    # --- T2: Low paraphrase (wrong, some shared words) ---
    {
        "id": "T2-PARAPHRASE",
        "tier": "T2",
        "answer": (
            "dBZ is decibels Zulu used for aviation weather reporting. "
            "It measures cloud thickness in nautical miles."
        ),
        "expected_gate": "extractive_override",
        "description": "Shares 'dBZ' token but introduces fabricated meaning ('Zulu', 'nautical miles')",
    },

    # --- T3: HIGH-OVERLAP WRONG (your exact test case) ---
    {
        "id": "T3-OVERLAP-WRONG",
        "tier": "T3",
        "answer": (
            "dBZ is decibels Zulu used for aviation reflectivity. "
            "The reflectivity calibration factor dBZ0 is used to calculate reflectivity. "
            "dBZ0 is the equivalent radar reflectivity at the reference range. "
            "Higher dBZ values indicate more intense cloud coverage."
        ),
        "expected_gate": "pass",  # This is the INTERESTING case — will it pass?
        "description": "3/4 statements are copied from source; 1st and 4th are subtly wrong",
    },

    # --- T4: Copy-paste correct (should pass — it IS the evidence) ---
    {
        "id": "T4-VERBATIM",
        "tier": "T4",
        "answer": (
            "The reflectivity calibration factor dBZ0 is used to calculate reflectivity, dBZ. "
            "dBZ0 is the equivalent radar reflectivity at the reference range where the "
            "return signal power is equal to the noise power (SNR = 0 dB). "
            "dBZ is the logarithmic representation: dBZ = 10 * log10(Z). "
            "Higher dBZ values indicate more intense precipitation."
        ),
        "expected_gate": "pass",
        "description": "Verbatim copy from source docs — should pass (this IS grounded)",
    },

    # --- T5: Subtle corruption (one key fact changed, rest verbatim) ---
    {
        "id": "T5-SUBTLE",
        "tier": "T5",
        "answer": (
            "The reflectivity calibration factor dBZ0 is used to calculate reflectivity, dBZ. "
            "dBZ0 is the equivalent radar reflectivity at the reference range where the "
            "return signal power is equal to the noise power (SNR = 0 dB). "
            "The reflectivity algorithm defines dBZ0 as the minimum detectable signal "
            "at a reference range of 10 km."  # WRONG: source says 1 km
        ),
        "expected_gate": "pass",  # Gate can't catch this — only 1 token differs
        "description": "Verbatim EXCEPT '1 km' → '10 km'. Semantic corruption, lexical near-match.",
    },

    # --- T6: Hallucinated extras (correct base + fabricated claims) ---
    {
        "id": "T6-HALLUC-EXTRA",
        "tier": "T6",
        "answer": (
            "dBZ is the logarithmic representation: dBZ = 10 * log10(Z). "
            "Higher dBZ values indicate more intense precipitation. "
            "The FAA requires recalibration every 90 days per Advisory Circular 150/5220-16E. "
            "Failure to maintain dBZ calibration voids the station's operational certificate."
        ),
        "expected_gate": "extractive_override",
        "description": "First 2 statements grounded; last 2 are fabricated regulatory claims",
    },
]


def run_test(case: dict, confidence: float = 0.90) -> dict:
    """Run a single adversarial case through the quality gate."""
    answer = case["answer"]
    
    # Compute raw grounding ratio
    grounding = _compute_grounding_ratio(answer, CONTEXT_DOCS)
    
    # Per-statement breakdown
    statements = [
        s.strip()
        for s in __import__("re").split(r"[;\n.]+", answer)
        if s.strip() and len(s.strip()) > 10
    ]
    context_texts = [
        (d.get("text") or d.get("snippet") or "").strip()
        for d in CONTEXT_DOCS
    ]
    stmt_details = []
    for stmt in statements:
        tokens = _tokenize_for_grounding(stmt)
        best_overlap = 0.0
        for ctx in context_texts:
            ctx_tokens = _tokenize_for_grounding(ctx)
            if tokens:
                overlap = len(tokens & ctx_tokens) / len(tokens)
                best_overlap = max(best_overlap, overlap)
        grounded = _statement_is_grounded(stmt, context_texts)
        stmt_details.append({
            "text": stmt[:80],
            "tokens": len(tokens),
            "best_overlap": best_overlap,
            "grounded": grounded,
        })
    
    # Run through the full quality gate
    gate_result = _post_generation_quality_gate(
        answer_text=answer,
        context_docs=CONTEXT_DOCS,
        avg_confidence=confidence,
        intent_meta={"intent": "other"},
    )
    
    if gate_result is None:
        gate_action = "pass"
    else:
        gate_action = gate_result.get("gate_action", "unknown")
    
    return {
        "case_id": case["id"],
        "tier": case["tier"],
        "grounding_ratio": grounding,
        "gate_action": gate_action,
        "expected_gate": case["expected_gate"],
        "match": gate_action == case["expected_gate"],
        "statement_details": stmt_details,
    }


def main():
    print("=" * 78)
    print("ADVERSARIAL QUALITY GATE TEST")
    print("=" * 78)
    print(f"Grounding threshold: 40% (default), 70% (procedural/safety)")
    print(f"Overlap minimum per statement: 40%")
    print(f"Confidence injected: 90%")
    print()

    results = []
    for case in CASES:
        result = run_test(case)
        results.append(result)
        
        match_str = "✓ EXPECTED" if result["match"] else "✗ UNEXPECTED"
        print(f"--- {case['id']} ({case['tier']}) ---")
        print(f"  Description: {case['description']}")
        print(f"  Grounding:   {result['grounding_ratio']:.2%}")
        print(f"  Gate action: {result['gate_action']}")
        print(f"  Expected:    {result['expected_gate']}")
        print(f"  Result:      {match_str}")
        print(f"  Statements:")
        for sd in result["statement_details"]:
            g = "GROUNDED" if sd["grounded"] else "UNGROUNDED"
            print(f"    [{g:10s}] overlap={sd['best_overlap']:.2%} tokens={sd['tokens']} → \"{sd['text']}\"")
        print()

    # Summary
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    passed = sum(1 for r in results if r["match"])
    total = len(results)
    print(f"Expected behavior: {passed}/{total}")
    print()
    
    # The critical finding
    print("GATE CHARACTERIZATION:")
    t3 = next(r for r in results if r["case_id"] == "T3-OVERLAP-WRONG")
    t5 = next(r for r in results if r["case_id"] == "T5-SUBTLE")
    t6 = next(r for r in results if r["case_id"] == "T6-HALLUC-EXTRA")
    
    if t3["gate_action"] == "pass":
        print("  [VULNERABLE] T3: High-overlap wrong answer PASSED the gate.")
        print("  → Gate is purely lexical. Token recycling defeats it.")
    else:
        print("  [DEFENDED]   T3: High-overlap wrong answer was CAUGHT.")
        print(f"  → Grounding={t3['grounding_ratio']:.2%} < 40% threshold.")
    
    if t5["gate_action"] == "pass":
        print("  [VULNERABLE] T5: Subtle 1-token corruption PASSED the gate.")
        print("  → Gate cannot detect single-fact semantic corruption.")
    else:
        print("  [DEFENDED]   T5: Subtle corruption was CAUGHT.")
    
    if t6["gate_action"] == "pass":
        print("  [VULNERABLE] T6: Hallucinated extras PASSED the gate.")
        print("  → Gate allows fabricated claims when mixed with grounded ones.")
    else:
        print("  [DEFENDED]   T6: Hallucinated extras were CAUGHT.")
        print(f"  → Grounding={t6['grounding_ratio']:.2%} — fabricated statements dragged ratio below threshold.")


if __name__ == "__main__":
    main()
