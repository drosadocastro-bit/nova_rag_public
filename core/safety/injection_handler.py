"""
Hybrid injection and multi-query handling: judge by intent, not syntax.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .risk_assessment import RiskAssessment
from core.monitoring.logger_config import get_logger, log_safety_event

logger = get_logger("core.safety.injection_handler")


def handle_injection_and_multi_query(question: str) -> Dict[str, Any]:
    """Process injection syntax and multi-query detection/decisions.

    Returns a dict with:
        - cleaned_question: str
        - multi_assessment: dict
        - dangerous_injection: bool
        - had_injection: bool
        - multi_query_warning: str | None
        - refusal: str | None
        - decision_tag: str | None
    """

    q_raw = question.strip()
    q_original = q_raw
    multi_query_warning: str | None = None

    # Step 1: Detect injection syntax (form only - don't decide safety yet)
    injection_meta = RiskAssessment.detect_injection_syntax(q_raw)
    if injection_meta.get("has_injection"):
        log_safety_event(
            logger,
            "injection_detection",
            check_name="injection_syntax",
            passed=False,
            details={
                "markers": injection_meta.get("injection_markers", [])[:2],
                "original_preview": q_original[:80],
                "core_extracted": injection_meta["core_question"][:80],
            },
        )

    # Step 2: Extract core question(s) - strip wrapper BEFORE any decisions
    q_clean = injection_meta.get("core_question", q_raw).strip() if injection_meta.get("has_injection") else q_raw

    # Step 3: Assess risk on CLEAN segments (multi-query detection + per-segment risk)
    multi_assessment = RiskAssessment.assess_multi_query(q_clean)
    heuristic_triggers = [
        sub.get("assessment", {}).get("heuristic_trigger")
        for sub in multi_assessment.get("sub_assessments", [])
        if sub.get("assessment", {}).get("heuristic_trigger") is not None
    ]

    def _log_refusal(decision_tag: str, refusal_msg: str | None = None) -> None:
        logger.info(
            "safety_refusal",
            extra={
                "decision_tag": decision_tag,
                "heuristic_triggers": heuristic_triggers,
                "message_preview": (refusal_msg or "")[:200],
            },
        )

    # Early refusal for unsafe injection wrappers even if core question is safe
    q_orig_lower = q_original.lower()
    dangerous_injection = False
    if injection_meta.get("has_injection"):
        for _pat in [
            r"\bdisable\s+(abs|airbag|safety|check)\b",
            r"\boverride\s+(all\s+)?(safety|guidance|protocol|protocols)\b",
            r"\bignore\s+(all\s+)?safety\b",
            r"\bbypass\s+(safety|checks|protocols)\b",
        ]:
            if re.search(_pat, q_orig_lower):
                dangerous_injection = True
                break

    # Decision rules (conservative - any dangerous segment blocks entire request)
    if multi_assessment.get("is_multi_query"):
        if dangerous_injection and multi_assessment.get("has_safe_parts"):
            override_msg = multi_assessment.get("override_response") or (
                "I cannot process this because it contains unsafe instructions alongside a safe question. "
                "Please ask only the safe, manufacturer-recommended question."
            )
            _log_refusal("multi_query_mixed_intent_blocked | unsafe_injection_wrapper", override_msg)
            return {
                "refusal": override_msg,
                "decision_tag": "multi_query_mixed_intent_blocked | unsafe_injection_wrapper",
                "cleaned_question": q_clean,
                "multi_assessment": multi_assessment,
                "dangerous_injection": dangerous_injection,
                "had_injection": bool(injection_meta.get("has_injection")),
                "multi_query_warning": multi_query_warning,
                "heuristic_triggers": heuristic_triggers,
            }

        print(f"[MULTI-QUERY] Detected {len(multi_assessment['sub_assessments'])} segments")
        print(f"[MULTI-QUERY] Safe: {len(multi_assessment['safe_queries'])}, Dangerous: {len(multi_assessment['dangerous_queries'])}")

        # Rule 1: All segments dangerous → refuse entire request
        if multi_assessment["all_dangerous"]:
            print("[SAFETY] All segments dangerous - refusing entirely")
            refusal_msg = (
                "I cannot help with any of those requests. "
                f"{multi_assessment['sub_assessments'][0]['assessment']['reasoning']}"
            )
            _log_refusal("multi_query_all_dangerous", refusal_msg)
            return {
                "refusal": refusal_msg,
                "decision_tag": "multi_query_all_dangerous",
                "cleaned_question": q_clean,
                "multi_assessment": multi_assessment,
                "dangerous_injection": dangerous_injection,
                "had_injection": bool(injection_meta.get("has_injection")),
                "multi_query_warning": multi_query_warning,
                "heuristic_triggers": heuristic_triggers,
            }

        # Rule 2: Mixed safe + dangerous → refuse
        if multi_assessment["has_dangerous_parts"] and multi_assessment["has_safe_parts"]:
            print("[SAFETY] Mixed intent detected - refusing entire request (contains dangerous segment)")
            override_msg = multi_assessment.get("override_response") or (
                "I cannot process this request because it contains both safe and unsafe queries. "
                "Please separate them into individual requests."
            )
            _log_refusal("multi_query_mixed_intent_blocked", override_msg)
            return {
                "refusal": override_msg,
                "decision_tag": "multi_query_mixed_intent_blocked",
                "cleaned_question": q_clean,
                "multi_assessment": multi_assessment,
                "dangerous_injection": dangerous_injection,
                "had_injection": bool(injection_meta.get("has_injection")),
                "multi_query_warning": multi_query_warning,
                "heuristic_triggers": heuristic_triggers,
            }

        # Rule 3: All segments safe → answer using first safe segment
        if multi_assessment["has_safe_parts"] and not multi_assessment["has_dangerous_parts"]:
            q_raw = multi_assessment["safe_queries"][0] if multi_assessment["safe_queries"] else q_clean
            multi_query_warning = None
    else:
        # Single segment - use normal risk assessment
        risk_assessment = multi_assessment["sub_assessments"][0]["assessment"]
        print(f"[RISK] {risk_assessment['risk_level'].value} - {risk_assessment['reasoning']}")

        if risk_assessment.get("is_emergency") or risk_assessment.get("override_response"):
            override_msg = risk_assessment.get("override_response")
            risk_header = RiskAssessment.format_risk_header(risk_assessment)
            if override_msg:
                override_msg = risk_header + "\n\n" + override_msg
            if risk_assessment.get("is_emergency"):
                decision_tag = "risk_override | EMERGENCY"
            elif risk_assessment.get("is_fake_part"):
                decision_tag = "risk_override | fake_part"
            else:
                decision_tag = f"risk_override | {risk_assessment['risk_level'].value}"

            print(f"[SAFETY] Override activated: {decision_tag}")
            _log_refusal(decision_tag, override_msg)
            return {
                "refusal": override_msg,
                "decision_tag": decision_tag,
                "cleaned_question": q_clean,
                "multi_assessment": multi_assessment,
                "dangerous_injection": dangerous_injection,
                "had_injection": bool(injection_meta.get("has_injection")),
                "multi_query_warning": multi_query_warning,
                "heuristic_trigger": risk_assessment.get("heuristic_trigger"),
                "heuristic_triggers": heuristic_triggers,
            }

        # Unsafe injection wrapper detected even if core seems safe
        if dangerous_injection:
            _log_refusal("unsafe_injection_wrapper | blocked")
            return {
                "refusal": (
                    "I cannot help with that request because it attempts to bypass or disable safety guidance. "
                    "Please ask a normal maintenance or diagnostic question."
                ),
                "decision_tag": "unsafe_injection_wrapper | blocked",
                "cleaned_question": q_clean,
                "multi_assessment": multi_assessment,
                "dangerous_injection": dangerous_injection,
                "had_injection": bool(injection_meta.get("has_injection")),
                "multi_query_warning": multi_query_warning,
                "heuristic_triggers": heuristic_triggers,
            }

        q_raw = q_clean

    # After all extraction/stripping, recompute lowercase for downstream checks
    q_lower = q_raw.lower()

    if injection_meta.get("has_injection"):
        print("[INJECTION-DECISION] Original had injection syntax, assessed CONTENT only")
        print(f"[INJECTION-DECISION] Final question for processing: {q_raw[:80]}")

    return {
        "refusal": None,
        "decision_tag": None,
        "cleaned_question": q_raw,
        "multi_assessment": multi_assessment,
        "dangerous_injection": dangerous_injection,
        "had_injection": bool(injection_meta.get("has_injection")),
        "multi_query_warning": multi_query_warning,
        "q_lower": q_lower,
        "heuristic_triggers": heuristic_triggers,
    }