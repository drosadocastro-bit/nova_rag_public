# NIC Adversarial Test Report

**Generated:** 2026-01-02 08:47:24

**Total Tests:** 90
**Pass Rate:** 98.9%

## Confusion Matrix

- **True Positives (TP):** 20 - Correctly answered valid questions
- **True Negatives (TN):** 69 - Correctly refused invalid/unsafe questions
- **False Positives (FP):** 1 - Incorrectly refused valid questions
- **False Negatives (FN):** 0 - **CRITICAL** - Incorrectly answered invalid/unsafe questions

## Category Results

### prompt_injection_attacks
**Description:** Attempts to override system instructions and bypass safety guards

**Results:** 15/15 (100.0%)

**Confusion Matrix:** TP=0, TN=15, FP=0, FN=0

### context_poisoning
**Description:** Questions with false premises designed to manipulate retrieval or citations

**Results:** 10/10 (100.0%)

**Confusion Matrix:** TP=0, TN=10, FP=0, FN=0

### citation_evasion
**Description:** Attempts to get answers without proper citation or confidence checks

**Results:** 10/10 (100.0%)

**Confusion Matrix:** TP=0, TN=10, FP=0, FN=0

### confidence_manipulation
**Description:** Questions designed to elicit high-confidence answers on non-existent or wrong information

**Results:** 10/10 (100.0%)

**Confusion Matrix:** TP=0, TN=10, FP=0, FN=0

### semantic_manipulation
**Description:** Questions using semantic tricks, double negatives, or confirmation bias

**Results:** 10/10 (100.0%)

**Confusion Matrix:** TP=0, TN=10, FP=0, FN=0

### extreme_inputs
**Description:** Malformed, oversized, or unusual inputs designed to crash or confuse the system

**Results:** 15/15 (100.0%)

**Confusion Matrix:** TP=11, TN=4, FP=0, FN=0

### multi_turn_context_building
**Description:** Attempts to build false context across multiple queries (NOTE: single-turn test, checking if NIC resists)

**Results:** 10/10 (100.0%)

**Confusion Matrix:** TP=0, TN=10, FP=0, FN=0

### valid_but_tricky
**Description:** Legitimate questions that might be edge cases or require careful handling

**Results:** 9/10 (90.0%)

**Confusion Matrix:** TP=9, TN=0, FP=1, FN=0

