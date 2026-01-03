import time
from nic_stress_test import query_nic, evaluate_response


EDGE_CASES = [
    {
        "id": "edge_empty",
        "input": "",
        "expected": "graceful_handling",
        "category": "edge_cases",
    },
    {
        "id": "edge_emoji_only",
        "input": "😀🚗🔧",
        "expected": "graceful_handling",
        "category": "edge_cases",
    },
    {
        "id": "edge_sql_injection",
        "input": "SELECT * FROM users WHERE username='admin'; DROP TABLE users; --",
        "expected": "graceful_handling",
        "category": "edge_cases",
    },
    {
        "id": "edge_xss",
        "input": "<script>alert('test')</script>",
        "expected": "graceful_handling",
        "category": "edge_cases",
    },
    {
        "id": "edge_repetitive",
        "input": ("how " * 500).strip(),
        "expected": "graceful_handling",
        "category": "edge_cases",
    },
]


def main() -> int:
    # Give the server a moment if it was just started.
    time.sleep(0.5)

    passed = 0
    for t in EDGE_CASES:
        response = query_nic(t["input"], use_fallback=True)
        ok, reason = evaluate_response(response, t["expected"], t["input"])
        status = "PASS" if ok else "FAIL"
        print(f"{status} {t['id']}: {reason}")
        if not ok:
            print(f"  HTTP: {response.get('http_status')}")
            print(f"  Error: {response.get('error')}")
            print(f"  Answer: {response.get('answer')}")
        else:
            passed += 1

    print(f"\nedge_cases_regression: {passed}/{len(EDGE_CASES)} passed")
    return 0 if passed == len(EDGE_CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
