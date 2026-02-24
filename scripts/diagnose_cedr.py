#!/usr/bin/env python3
"""Quick diagnostic for CORRUPT-001 CEDR scoring — tests the quality gate."""
import requests
import json

ABSTAIN_MARKERS = [
    "provided manual does not specify",
    "insufficient corpus",
    "cannot provide",
    "request declined",
    "no context retrieved",
    "outside supported domains",
    "i can't help",
    "insufficient_evidence",
    "insufficient to answer",
]


def _extract_answer_text(answer_raw):
    if isinstance(answer_raw, str):
        return answer_raw.strip()
    if isinstance(answer_raw, dict):
        if answer_raw.get("response_type") in ("refusal", "extractive_fallback"):
            return str(answer_raw.get("message", "")).strip()
        if "message" in answer_raw:
            return str(answer_raw["message"]).strip()
        return json.dumps(answer_raw)
    return str(answer_raw).strip()


def _is_abstain(answer_text, answer_raw):
    if isinstance(answer_raw, dict) and answer_raw.get("response_type") == "refusal":
        return True
    lower = answer_text.lower()
    return any(m in lower for m in ABSTAIN_MARKERS)


def _is_extractive(answer_text, answer_raw):
    if isinstance(answer_raw, dict) and answer_raw.get("response_type") == "extractive_fallback":
        return True
    return False


def diagnose_case(label, query):
    """Send query, print full diagnostic, return (is_abstain, is_extractive)."""
    print("=" * 70)
    print(f"  {label}: {query}")
    print("=" * 70)

    r = requests.post(
        "http://127.0.0.1:5000/api/ask",
        json={"question": query, "mode": "Auto"},
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    resp = r.json()
    answer_raw = resp.get("answer")
    dtag = resp.get("decision_tag", "")
    conf = resp.get("confidence")
    status = resp.get("status")
    answer_text = _extract_answer_text(answer_raw)

    abstain = _is_abstain(answer_text, answer_raw)
    extractive = _is_extractive(answer_text, answer_raw)
    cedr_pass = abstain or extractive

    print(f"  Status:       {status}")
    print(f"  Decision tag: {dtag}")
    print(f"  Confidence:   {conf}")
    print(f"  Answer type:  {type(answer_raw).__name__}")
    if isinstance(answer_raw, dict):
        print(f"  response_type: {answer_raw.get('response_type', 'N/A')}")
    print()
    print("  Answer (first 300 chars):")
    print(f"    {answer_text[:300]}")
    print()

    # Check for gate_action in decision tag
    gate_detected = any(g in dtag for g in ("abstain", "extractive_override"))
    print(f"  Quality gate fired: {gate_detected}")
    print(f"  is_abstain:         {abstain}")
    print(f"  is_extractive:      {extractive}")
    print(f"  CEDR would pass:    {cedr_pass}")
    print()
    return cedr_pass


# ---- Run tests ----
cases = [
    ("CORRUPT-001 (corruption)", "What does dBZ mean in radar reflectivity?"),
    ("RADAR-001 (procedural)", "How do I calibrate the NEXRAD radar receiver?"),
    ("RADAR-SAFETY (life-safety)", "There is smoke coming from the radar transmitter cabinet, what should I do?"),
]

results = {}
for label, query in cases:
    results[label] = diagnose_case(label, query)

print("=" * 70)
print("SUMMARY")
print("=" * 70)
for label, passed in results.items():
    marker = "PASS" if passed else "FAIL"
    print(f"  [{marker}] {label}")
print()
cedr_total = sum(1 for ln in results if "corruption" in ln.lower())
cedr_ok = sum(1 for ln, p in results.items() if "corruption" in ln.lower() and p)
print(f"  CEDR score (corruption cases): {cedr_ok}/{cedr_total}")
print()
