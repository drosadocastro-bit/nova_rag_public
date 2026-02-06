"""
NIC Verification Module
=======================

Provides hallucination prevention through verification techniques.

Components:
- chain_of_verification: CoVe implementation for claim verification
"""

from .chain_of_verification import (
    run_chain_of_verification,
    apply_cove_to_answer,
    extract_claims_for_verification,
    verify_claim,
    VERIFICATION_CONFIDENCE_THRESHOLD,
    MAX_VERIFICATION_QUESTIONS,
    SAFETY_CRITICAL_KEYWORDS,
)

__all__ = [
    "run_chain_of_verification",
    "apply_cove_to_answer",
    "extract_claims_for_verification",
    "verify_claim",
    "VERIFICATION_CONFIDENCE_THRESHOLD",
    "MAX_VERIFICATION_QUESTIONS",
    "SAFETY_CRITICAL_KEYWORDS",
]
