#!/usr/bin/env python3
"""Rescore an existing nic_stress_test_results.json using the current evaluator.

Why this exists:
- The stress test runner stores responses and pass/fail decisions.
- If evaluator logic changes (e.g., better refusal-schema detection), rerunning the
  entire API suite is slow. This script recomputes pass/fail locally from stored
  responses, updates per-category counts, and rewrites the results JSON.

Usage:
  python rescore_stress_results.py

Inputs:
  nic_stress_test_results.json (in current working directory)

Outputs:
  nic_stress_test_results.json (updated in place)
"""

from __future__ import annotations

import json
from pathlib import Path

import nic_stress_test

RESULTS_JSON = Path("nic_stress_test_results.json")


def main() -> int:
    if not RESULTS_JSON.exists():
        print("[FAIL] nic_stress_test_results.json not found")
        return 1

    results = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    categories = results.get("categories") or {}

    overall_passed = 0
    overall_failed = 0

    for category_name, category_data in categories.items():
        expected = category_data.get("expected_behavior") or ""
        tests = category_data.get("tests") or []

        passed = 0
        failed = 0

        for t in tests:
            question = t.get("question", "")
            stored_answer = t.get("response", "")

            # Reconstruct the envelope shape expected by evaluate_response.
            # Original query_nic returns {success: bool, data: {...}}.
            response_obj = {
                "success": True,
                "data": {"answer": stored_answer},
            }

            ok, reason = nic_stress_test.evaluate_response(
                response_obj,
                expected_behavior=expected,
                question=question,
            )

            t["passed"] = bool(ok)
            t["reason"] = reason

            if ok:
                passed += 1
            else:
                failed += 1

        category_data["passed"] = passed
        category_data["failed"] = failed
        category_data["total"] = len(tests)

        overall_passed += passed
        overall_failed += failed

    total_questions = results.get("total_questions")
    if not isinstance(total_questions, int) or total_questions <= 0:
        total_questions = overall_passed + overall_failed
        results["total_questions"] = total_questions

    pass_rate = round((overall_passed / total_questions * 100.0) if total_questions else 0.0, 2)
    results["summary"] = {
        "total_passed": overall_passed,
        "total_failed": overall_failed,
        "pass_rate": pass_rate,
    }

    RESULTS_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("[OK] Rescored results written to nic_stress_test_results.json")
    print(f"Pass rate: {pass_rate}%")
    print(f"Passed: {overall_passed}  Failed: {overall_failed}  Total: {total_questions}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
