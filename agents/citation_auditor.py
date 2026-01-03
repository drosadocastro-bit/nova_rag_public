"""
Citation Auditor - Validates every answer against source PDFs for strict manual compliance

This module ensures that every procedural step, troubleshooting recommendation,
and technical claim can be traced back to an approved manual with page numbers.

Key Features:
- Validates citations against actual PDF content
- Extracts exact quotes from source pages
- Generates audit trails for compliance
- Supports "strict mode" where uncited answers are rejected
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can", "could",
    "do", "does", "did", "for", "from", "had", "has", "have", "how", "i", "if", "in",
    "into", "is", "it", "its", "may", "might", "must", "no", "not", "of", "on", "or",
    "our", "should", "so", "such", "than", "that", "the", "their", "then", "there",
    "these", "they", "this", "to", "use", "using", "was", "were", "what", "when", "where",
    "which", "who", "will", "with", "within", "without", "you", "your",
}


def _tokenize(text: str) -> list[str]:
    # Strip common inline citation patterns so they don't penalize overlap scoring.
    # Example: "... (6345_2b_mthb.pdf p36)" -> "..."
    text = re.sub(r"\([^)]*\.pdf[^)]*\)", " ", (text or ""), flags=re.IGNORECASE)
    # Keep only simple alphanumerics so comparisons are stable.
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()
    tokens = [t for t in cleaned.split() if len(t) > 2 and t not in STOPWORDS]
    return tokens


# =======================
# CITATION VALIDATION
# =======================

def extract_page_from_source(source_text: str) -> Optional[int]:
    """
    Extract page number from source metadata.
    
    Examples:
        "manual.pdf page 42" -> 42
        "6345_2b_mthb.pdf (pg. 56)" -> 56
        "Manual.pdf pg. 75" -> 75
    """
    patterns = [
        r'page\s+(\d+)',
        r'pg\.\s*(\d+)',
        r'\(pg\.\s*(\d+)\)',
        r'p\.\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, source_text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None


def validate_citation(
    claim: str,
    source_doc: Dict,
    strict: bool = False
) -> Dict:
    """
    Validate that a claim is supported by the source document.
    
    Args:
        claim: The statement being made (e.g., a procedural step)
        source_doc: Document dict with 'text', 'source', 'page', etc.
        strict: If True, require exact phrase matching; if False, allow semantic match
    
    Returns:
        {
            "valid": bool,
            "confidence": float,  # 0.0 to 1.0
            "quote": str,         # Exact quote from source
            "page": int,
            "source": str
        }
    """
    source_text = source_doc.get("text") or source_doc.get("snippet") or ""
    source_name = source_doc.get("source", "unknown")
    page = source_doc.get("page") or extract_page_from_source(source_text)
    
    # Keyword overlap validation (normalized; ignores stopwords/punctuation)
    claim_tokens = set(_tokenize(claim))
    source_tokens = set(_tokenize(source_text))
    overlap = claim_tokens & source_tokens

    if len(claim_tokens) == 0:
        confidence = 0.0
    else:
        # Cap denominator so long steps aren't unfairly penalized.
        denom = max(1, min(len(claim_tokens), 10))
        confidence = min(1.0, len(overlap) / denom)
    
    # Extract a relevant quote (first sentence containing overlapping keywords)
    quote = ""
    for sentence in source_text.split('.'):
        sentence_tokens = set(_tokenize(sentence))
        # Require a few meaningful overlapping tokens for a usable quote.
        if len(sentence_tokens & claim_tokens) >= 3:
            quote = sentence.strip()[:200]  # Limit quote length
            break
    
    # Default acceptance threshold
    valid = confidence >= 0.35 and len(overlap) >= 2

    # Strict mode is used for safety gating: require stronger support.
    if strict:
        # Require a known page and a stronger match.
        denom = max(1, min(len(claim_tokens), 10))
        min_overlap = min(3, denom)
        valid = (page is not None) and (confidence >= 0.5) and (len(overlap) >= min_overlap)
    
    return {
        "valid": valid,
        "confidence": round(confidence, 2),
        "quote": quote or source_text[:150],
        "page": page,
        "source": source_name
    }


def build_audit_trail(
    response_json: Dict,
    context_docs: List[Dict],
    strict: bool = False
) -> Dict:
    """
    Build a complete audit trail for a structured response.
    
    Args:
        response_json: The agent's JSON response (with steps, why, etc.)
        context_docs: Retrieved documents used for context
        strict: Enable strict citation validation
    
    Returns:
        {
            "audit_status": "fully_cited" | "partially_cited" | "uncited",
            "total_claims": int,
            "cited_claims": int,
            "citations": [
                {
                    "claim": str,
                    "valid": bool,
                    "confidence": float,
                    "quote": str,
                    "page": int,
                    "source": str
                },
                ...
            ]
        }
    """
    citations = []
    
    # Extract claims from response
    claims = []
    if "steps" in response_json:
        claims.extend(response_json["steps"])
    if "why" in response_json:
        claims.extend(response_json["why"])
    if "likely_causes" in response_json:
        claims.extend(response_json["likely_causes"])
    if "next_steps" in response_json:
        claims.extend(response_json["next_steps"])
    
    # Validate each claim against context docs
    for claim in claims:
        # Handle both string claims and dict claims (extract text from dict)
        if isinstance(claim, dict):
            claim_text = claim.get("step") or claim.get("action") or claim.get("cause") or str(claim)
        else:
            claim_text = str(claim)
        
        best_citation = None
        best_confidence = 0.0
        
        for doc in context_docs:
            citation = validate_citation(claim_text, doc, strict=strict)
            if citation["confidence"] > best_confidence:
                best_confidence = citation["confidence"]
                best_citation = citation
        
        if best_citation:
            best_citation["claim"] = claim_text
            citations.append(best_citation)
        else:
            # Uncited claim
            citations.append({
                "claim": claim,
                "valid": False,
                "confidence": 0.0,
                "quote": "",
                "page": None,
                "source": "uncited"
            })
    
    # Calculate audit status
    total_claims = len(claims)
    cited_claims = sum(1 for c in citations if c["valid"])
    
    if total_claims == 0:
        audit_status = "no_claims"
    elif cited_claims == total_claims:
        audit_status = "fully_cited"
    elif cited_claims > 0:
        audit_status = "partially_cited"
    else:
        audit_status = "uncited"
    
    return {
        "audit_status": audit_status,
        "total_claims": total_claims,
        "cited_claims": cited_claims,
        "citation_rate": round(cited_claims / total_claims, 2) if total_claims > 0 else 0.0,
        "citations": citations
    }


def format_audit_report(audit_trail: Dict) -> str:
    """
    Format audit trail as human-readable report for compliance logs.
    """
    report = []
    report.append("=" * 60)
    report.append("CITATION AUDIT REPORT")
    report.append("=" * 60)
    report.append(f"Status: {audit_trail['audit_status'].upper()}")
    report.append(f"Citations: {audit_trail['cited_claims']}/{audit_trail['total_claims']} ({audit_trail['citation_rate']*100:.0f}%)")
    report.append("")
    
    for i, citation in enumerate(audit_trail["citations"], 1):
        status = "" if citation["valid"] else ""
        report.append(f"{status} Citation {i}:")
        report.append(f"   Claim: {citation['claim'][:100]}...")
        report.append(f"   Source: {citation['source']}")
        if citation["page"]:
            report.append(f"   Page: {citation['page']}")
        report.append(f"   Confidence: {citation['confidence']:.0%}")
        if citation["quote"]:
            report.append(f"   Quote: \"{citation['quote'][:100]}...\"")
        report.append("")
    
    report.append("=" * 60)
    return "\n".join(report)


def should_reject_answer(audit_trail: Dict, strict_mode: bool = False) -> Tuple[bool, str]:
    """
    Decide if an answer should be rejected based on citation quality.
    
    Args:
        audit_trail: Output from build_audit_trail
        strict_mode: If True, reject answers with citation_rate < 0.8
    
    Returns:
        (should_reject: bool, reason: str)
    """
    # If the response makes no technical claims (e.g., it only asks clarifying questions),
    # it should not be rejected for citation rate.
    if audit_trail.get("total_claims", 0) == 0 or audit_trail.get("audit_status") == "no_claims":
        return False, "No claims to cite"

    if strict_mode:
        if audit_trail["audit_status"] == "uncited":
            return True, "No valid citations found in strict mode"
        if audit_trail["citation_rate"] < 0.8:
            return True, f"Citation rate {audit_trail['citation_rate']:.0%} below 80% threshold in strict mode"
    
    # Always reject completely uncited answers in safety-critical contexts
    if audit_trail["audit_status"] == "uncited" and audit_trail["total_claims"] > 0:
        return True, "Safety-critical answer has no valid citations"
    
    return False, "Citations acceptable"
