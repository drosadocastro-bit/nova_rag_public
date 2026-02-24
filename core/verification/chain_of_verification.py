#!/usr/bin/env python3
"""
Chain of Verification (CoVe) for NIC
=====================================

Implements the CoVe prompting technique to reduce hallucinations in LLM outputs.

Process:
1. Generate initial response (done by main pipeline)
2. Generate verification questions from claims in the response
3. Answer each verification question independently (without original context)
4. Compare answers and flag contradictions
5. Produce verified response with confidence adjustments

References:
- Dhuliawala et al. (2023) "Chain-of-Verification Reduces Hallucination in LLMs"

Safety Philosophy:
- REFUSE > GUESS
- Evidence > Intuition
- Human safety is highest priority
"""

import json
import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Minimum confidence to accept a claim as verified
VERIFICATION_CONFIDENCE_THRESHOLD = 0.7

# Maximum verification questions per response
MAX_VERIFICATION_QUESTIONS = 5

# Keywords that indicate safety-critical claims (require stricter verification)
SAFETY_CRITICAL_KEYWORDS = [
    "voltage", "power", "frequency", "altitude", "warning", "caution", "danger",
    "maintenance", "procedure", "step", "must", "shall", "required", "critical",
    "safety", "hazard", "radiation", "interlock", "lockout", "tagout",
    "pressure", "temperature", "rpm", "tolerance", "calibration", "adjustment"
]


# =============================================================================
# PROMPTS
# =============================================================================

VERIFICATION_QUESTION_PROMPT = """You are a verification assistant for a safety-critical radar system documentation RAG.

Given the following answer to a technical question, extract the key factual claims and generate verification questions.
Focus on claims that can be verified against documentation - especially numerical values, procedures, and safety-related statements.

ORIGINAL QUESTION: {question}

ANSWER TO VERIFY:
{answer}

Generate 1-{max_questions} verification questions. Each question should:
1. Target a specific factual claim in the answer
2. Be answerable from the source documentation
3. Prioritize safety-critical claims (voltages, procedures, specifications)

Return ONLY valid JSON in this format:
{{
    "claims": [
        {{
            "claim_text": "The exact claim from the answer",
            "verification_question": "A question to verify this claim",
            "is_safety_critical": true/false,
            "source_required": "Type of source needed (e.g., 'TIB manual', 'specification table')"
        }}
    ]
}}

If no verifiable claims found, return: {{"claims": []}}
"""

VERIFICATION_ANSWER_PROMPT = """You are a fact-checking assistant for a safety-critical radar system documentation RAG.

Answer the following verification question using ONLY the provided context.
If the context does not contain enough information to answer, say "INSUFFICIENT_EVIDENCE".

CONTEXT:
{context}

VERIFICATION QUESTION: {question}

ORIGINAL CLAIM: {claim}

Respond with ONLY valid JSON:
{{
    "answer": "Your factual answer based on the context",
    "supports_claim": true/false/null,
    "confidence": 0.0-1.0,
    "evidence_quote": "Exact quote from context that supports your answer (or null)",
    "contradiction_found": true/false,
    "notes": "Any relevant notes or caveats"
}}

If you cannot verify from the context, use:
{{
    "answer": "INSUFFICIENT_EVIDENCE",
    "supports_claim": null,
    "confidence": 0.0,
    "evidence_quote": null,
    "contradiction_found": false,
    "notes": "Cannot verify - information not found in provided context"
}}
"""

FINAL_VERIFICATION_PROMPT = """You are the final reviewer for a safety-critical radar system documentation RAG.

Review the original answer and the verification results. Produce a verified response.

ORIGINAL QUESTION: {question}

ORIGINAL ANSWER:
{original_answer}

VERIFICATION RESULTS:
{verification_results}

Based on the verification:
1. Keep claims that were VERIFIED (supports_claim: true, confidence > 0.7)
2. REMOVE claims that were CONTRADICTED (contradiction_found: true)
3. ADD UNCERTAINTY MARKERS to claims with insufficient evidence
4. Flag any safety-critical claims that could not be verified

Return ONLY valid JSON:
{{
    "verified_answer": "The corrected/verified answer text",
    "verification_status": "verified" | "partial" | "unverified" | "contradicted",
    "verified_claims": ["List of claims that were verified"],
    "unverified_claims": ["List of claims that could not be verified"],
    "contradicted_claims": ["List of claims that were contradicted"],
    "confidence_adjustment": -0.3 to 0.0 (how much to reduce confidence),
    "safety_warnings": ["Any safety-related concerns from verification"],
    "sources_verified": ["Sources that were confirmed in verification"]
}}
"""


# =============================================================================
# CORE VERIFICATION FUNCTIONS
# =============================================================================

def extract_claims_for_verification(
    answer: str | dict,
    question: str,
    llm_call_fn: Callable[[str, str], str],
    model: str = "llama"
) -> list[dict]:
    """
    Extract factual claims from an answer that should be verified.
    
    Args:
        answer: The answer to extract claims from
        question: The original question
        llm_call_fn: Function to call LLM
        model: Which model to use
    
    Returns:
        List of claim dictionaries with verification questions
    """
    # Convert dict answers to string for analysis
    if isinstance(answer, dict):
        answer_str = json.dumps(answer, indent=2)
    else:
        answer_str = str(answer)
    
    # Build prompt
    prompt = VERIFICATION_QUESTION_PROMPT.format(
        question=question,
        answer=answer_str,
        max_questions=MAX_VERIFICATION_QUESTIONS
    )
    
    try:
        response = llm_call_fn(prompt, model)
        
        # Parse response
        claims_data = _parse_json_response(response)
        
        if not claims_data or "claims" not in claims_data:
            logger.warning("[CoVe] No claims extracted from response")
            return []
        
        claims = claims_data.get("claims", [])
        
        # Prioritize safety-critical claims
        safety_claims = [c for c in claims if c.get("is_safety_critical")]
        other_claims = [c for c in claims if not c.get("is_safety_critical")]
        
        # Return safety claims first, up to max
        prioritized = safety_claims + other_claims
        return prioritized[:MAX_VERIFICATION_QUESTIONS]
        
    except Exception as e:
        logger.error(f"[CoVe] Failed to extract claims: {e}")
        return []


def verify_claim(
    claim: dict,
    context_docs: list[dict],
    llm_call_fn: Callable[[str, str], str],
    model: str = "llama"
) -> dict:
    """
    Verify a single claim against the context documents.
    
    This is done INDEPENDENTLY from the original response generation
    to avoid confirmation bias.
    
    Args:
        claim: The claim dictionary with claim_text and verification_question
        context_docs: Retrieved documents to check against
        llm_call_fn: Function to call LLM
        model: Which model to use
    
    Returns:
        Verification result dictionary
    """
    # Build context string from documents
    context_str = _format_context_for_verification(context_docs)
    
    prompt = VERIFICATION_ANSWER_PROMPT.format(
        context=context_str,
        question=claim.get("verification_question", ""),
        claim=claim.get("claim_text", "")
    )
    
    try:
        response = llm_call_fn(prompt, model)
        result = _parse_json_response(response)
        
        if not result:
            return {
                "claim": claim,
                "answer": "VERIFICATION_FAILED",
                "supports_claim": None,
                "confidence": 0.0,
                "evidence_quote": None,
                "contradiction_found": False,
                "notes": "Failed to parse verification response"
            }
        
        result["claim"] = claim
        return result
        
    except Exception as e:
        logger.error(f"[CoVe] Verification failed for claim: {e}")
        return {
            "claim": claim,
            "answer": "VERIFICATION_ERROR",
            "supports_claim": None,
            "confidence": 0.0,
            "evidence_quote": None,
            "contradiction_found": False,
            "notes": f"Error during verification: {str(e)}"
        }


def run_chain_of_verification(
    answer: str | dict,
    question: str,
    context_docs: list[dict],
    llm_call_fn: Callable[[str, str], str],
    model: str = "llama",
    skip_if_low_risk: bool = True
) -> dict:
    """
    Execute the full Chain of Verification process.
    
    Args:
        answer: The initial answer to verify
        question: The original question
        context_docs: Retrieved documents
        llm_call_fn: Function to call LLM
        model: Which model to use
        skip_if_low_risk: Skip verification for simple/low-risk responses
    
    Returns:
        Verification result with adjusted answer and confidence
    """
    logger.info("[CoVe] Starting Chain of Verification")
    
    # Check if we should skip (low-risk, short answer)
    if skip_if_low_risk and _is_low_risk_response(answer, question):
        logger.info("[CoVe] Skipping verification (low-risk response)")
        return {
            "verified": True,
            "skipped": True,
            "reason": "low_risk_response",
            "original_answer": answer,
            "verified_answer": answer,
            "confidence_adjustment": 0.0,
            "verification_results": []
        }
    
    # Step 1: Extract claims to verify
    claims = extract_claims_for_verification(answer, question, llm_call_fn, model)
    
    if not claims:
        logger.info("[CoVe] No verifiable claims found")
        return {
            "verified": True,
            "skipped": True,
            "reason": "no_verifiable_claims",
            "original_answer": answer,
            "verified_answer": answer,
            "confidence_adjustment": 0.0,
            "verification_results": []
        }
    
    logger.info(f"[CoVe] Extracted {len(claims)} claims for verification")
    
    # Step 2: Verify each claim independently
    verification_results = []
    for i, claim in enumerate(claims):
        logger.debug(f"[CoVe] Verifying claim {i+1}/{len(claims)}: {claim.get('claim_text', '')[:50]}...")
        result = verify_claim(claim, context_docs, llm_call_fn, model)
        verification_results.append(result)
    
    # Step 3: Analyze results
    analysis = _analyze_verification_results(verification_results)
    
    logger.info(f"[CoVe] Verification complete: {analysis['verified_count']}/{len(claims)} verified, "
                f"{analysis['contradicted_count']} contradicted, {analysis['unverified_count']} unverified")
    
    # Step 4: Generate final verified response if needed
    if analysis["contradicted_count"] > 0 or analysis["unverified_count"] > len(claims) // 2:
        logger.info("[CoVe] Generating corrected response based on verification")
        verified_answer = _generate_verified_response(
            answer, question, verification_results, llm_call_fn, model
        )
    else:
        verified_answer = answer
    
    # Calculate confidence adjustment
    confidence_adjustment = _calculate_confidence_adjustment(analysis)
    
    return {
        "verified": analysis["contradicted_count"] == 0,
        "skipped": False,
        "reason": None,
        "original_answer": answer,
        "verified_answer": verified_answer,
        "confidence_adjustment": confidence_adjustment,
        "verification_results": verification_results,
        "analysis": analysis,
        "safety_warnings": analysis.get("safety_warnings", [])
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _parse_json_response(response: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    if not response:
        return None
    
    # Remove markdown code blocks
    response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'```\s*$', '', response, flags=re.MULTILINE)
    response = re.sub(r'^```\s*', '', response, flags=re.MULTILINE)
    response = response.strip()
    
    # Find JSON object
    json_match = re.search(r'\{[\s\S]*\}', response)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.debug("[CoVe] JSON regex match failed to parse, trying direct parse")
    
    # Try parsing directly
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        logger.debug("[CoVe] JSON parsing failed, returning None")
        return None


def _format_context_for_verification(context_docs: list[dict]) -> str:
    """Format context documents for verification prompt."""
    if not context_docs:
        return "No context available."
    
    parts = []
    for i, doc in enumerate(context_docs[:5]):  # Limit to top 5
        source = doc.get("source", doc.get("metadata", {}).get("source", "Unknown"))
        text = doc.get("text", doc.get("content", ""))
        if text:
            parts.append(f"[Source {i+1}: {source}]\n{text[:2000]}")  # Limit per doc
    
    return "\n\n".join(parts) if parts else "No context available."


def _is_low_risk_response(answer: str | dict, question: str) -> bool:
    """Check if response is low-risk and can skip verification."""
    # Convert answer to string for analysis
    answer_str = json.dumps(answer) if isinstance(answer, dict) else str(answer)
    
    # Check for safety-critical keywords FIRST (regardless of length)
    combined = f"{question} {answer_str}".lower()
    
    for keyword in SAFETY_CRITICAL_KEYWORDS:
        if keyword in combined:
            return False  # Safety-critical, must verify
    
    # Short answers without safety keywords are low risk
    if len(answer_str) < 100:
        return True
    
    return True  # No safety keywords, low risk


def _analyze_verification_results(results: list[dict]) -> dict:
    """Analyze verification results and produce summary."""
    verified_count = 0
    contradicted_count = 0
    unverified_count = 0
    safety_warnings = []
    
    for result in results:
        claim = result.get("claim", {})
        supports = result.get("supports_claim")
        contradiction = result.get("contradiction_found", False)
        is_safety = claim.get("is_safety_critical", False)
        
        if contradiction:
            contradicted_count += 1
            if is_safety:
                safety_warnings.append(
                    f"SAFETY-CRITICAL CONTRADICTION: {claim.get('claim_text', 'Unknown claim')}"
                )
        elif supports is True and result.get("confidence", 0) >= VERIFICATION_CONFIDENCE_THRESHOLD:
            verified_count += 1
        else:
            unverified_count += 1
            if is_safety:
                safety_warnings.append(
                    f"SAFETY-CRITICAL UNVERIFIED: {claim.get('claim_text', 'Unknown claim')}"
                )
    
    return {
        "verified_count": verified_count,
        "contradicted_count": contradicted_count,
        "unverified_count": unverified_count,
        "total_claims": len(results),
        "safety_warnings": safety_warnings,
        "verification_rate": verified_count / len(results) if results else 0.0
    }


def _calculate_confidence_adjustment(analysis: dict) -> float:
    """Calculate how much to adjust confidence based on verification."""
    # Base adjustment
    adjustment = 0.0
    
    # Penalize contradictions heavily
    if analysis["contradicted_count"] > 0:
        adjustment -= 0.2 * analysis["contradicted_count"]
    
    # Penalize unverified claims
    if analysis["unverified_count"] > 0:
        adjustment -= 0.05 * analysis["unverified_count"]
    
    # Safety warnings get extra penalty
    if analysis.get("safety_warnings"):
        adjustment -= 0.1 * len(analysis["safety_warnings"])
    
    # Cap adjustment at -0.5 (never reduce more than half)
    return max(adjustment, -0.5)


def _generate_verified_response(
    original_answer: str | dict,
    question: str,
    verification_results: list[dict],
    llm_call_fn: Callable[[str, str], str],
    model: str
) -> str | dict:
    """Generate a corrected response based on verification results."""
    # Format verification results for prompt
    results_str = json.dumps(verification_results, indent=2, default=str)
    
    answer_str = json.dumps(original_answer) if isinstance(original_answer, dict) else str(original_answer)
    
    prompt = FINAL_VERIFICATION_PROMPT.format(
        question=question,
        original_answer=answer_str,
        verification_results=results_str
    )
    
    try:
        response = llm_call_fn(prompt, model)
        result = _parse_json_response(response)
        
        if result and "verified_answer" in result:
            return result
        
        # If parsing failed, return original with warning
        logger.warning("[CoVe] Failed to generate verified response, returning original")
        return original_answer
        
    except Exception as e:
        logger.error(f"[CoVe] Error generating verified response: {e}")
        return original_answer


# =============================================================================
# INTEGRATION FUNCTIONS
# =============================================================================

def apply_cove_to_answer(
    answer: str | dict,
    question: str,
    context_docs: list[dict],
    llm_call_fn: Callable[[str, str], str],
    original_confidence: float,
    model: str = "llama",
    force_verification: bool = False
) -> tuple[str | dict, float, dict]:
    """
    Apply Chain of Verification to an answer and adjust confidence.
    
    This is the main integration point for the NIC pipeline.
    
    Args:
        answer: The answer to verify
        question: Original question
        context_docs: Retrieved documents
        llm_call_fn: LLM function
        original_confidence: Starting confidence score
        model: Which model to use
        force_verification: Force verification even for low-risk responses
    
    Returns:
        (verified_answer, adjusted_confidence, verification_metadata)
    """
    result = run_chain_of_verification(
        answer=answer,
        question=question,
        context_docs=context_docs,
        llm_call_fn=llm_call_fn,
        model=model,
        skip_if_low_risk=not force_verification
    )
    
    # Calculate adjusted confidence
    adjusted_confidence = max(0.0, original_confidence + result["confidence_adjustment"])
    
    # If contradictions found, further reduce confidence
    if not result["verified"] and result.get("analysis", {}).get("contradicted_count", 0) > 0:
        adjusted_confidence = min(adjusted_confidence, 0.3)  # Cap at 0.3 if contradictions
    
    # Build metadata
    metadata = {
        "cove_applied": not result.get("skipped", False),
        "cove_skipped_reason": result.get("reason"),
        "original_confidence": original_confidence,
        "adjusted_confidence": adjusted_confidence,
        "confidence_adjustment": result["confidence_adjustment"],
        "verified": result["verified"],
        "claims_checked": len(result.get("verification_results", [])),
        "analysis": result.get("analysis", {}),
        "safety_warnings": result.get("safety_warnings", [])
    }
    
    return result["verified_answer"], adjusted_confidence, metadata


# =============================================================================
# TESTING / STANDALONE
# =============================================================================

if __name__ == "__main__":
    # Simple test
    print("Chain of Verification module loaded successfully.")
    print(f"Verification threshold: {VERIFICATION_CONFIDENCE_THRESHOLD}")
    print(f"Max verification questions: {MAX_VERIFICATION_QUESTIONS}")
    print(f"Safety-critical keywords: {len(SAFETY_CRITICAL_KEYWORDS)}")
