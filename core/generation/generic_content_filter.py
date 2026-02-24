"""
Generic Content Filter
======================
Post-processing filter to remove uncited generic content from LLM responses.
This addresses the hallucination pattern where LLM adds defensive/generic advice
not found in retrieved documents.

RAGAS failure analysis identified:
- 8 cases with generic safety warnings added
- 4 cases with generic intro/outro wrapping
- 3 cases with generic elaboration of correct values
= 45% of failures due to generic content LLM shouldn't add
"""

import re

# Generic phrases/patterns that shouldn't appear without explicit citation
GENERIC_SAFETY_PATTERNS = [
    r"Always\s+(?:wear|use|ensure)",
    r"Never\s+(?:work|drive|operate)",
    r"Be\s+cautious\s+when",
    r"Ensure\s+(?:safety|proper)",
    r"Take\s+proper\s+safety",
    r"Wear\s+(?:protective|safety)",
    r"Avoid\s+(?:injury|damage|serious)",
    r"Safety\s+glasses",
    r"protective\s+clothing",
    r"safety\s+equipment",
]

GENERIC_DISCLAIMER_PATTERNS = [
    r"[Cc]onsult\s+(?:the\s+)?(?:your\s+)?(?:professional\s+)?(?:mechanic|manual|service\s+manual)",
    r"[Rr]efer\s+to\s+(?:your\s+)?(?:the\s+)?manual",
    r"[Ss]ee\s+your\s+vehicle's?\s+(?:service\s+)?manual",
    r"[Cc]ontact\s+(?:a\s+)?professional",
    r"The\s+provided\s+(?:information|docs?|manuals?)",
    r"[Ww]ithout\s+(?:additional|specific)\s+context",
    r"[Pp]lease\s+refer",
    r"[Cc]onsult\s+[a-z\s]+manual",
]

GENERIC_INTRO_PATTERNS = [
    r"^[Pp]ark\s+your\s+vehicle\s+on\s+a\s+flat",
    r"^[Ee]ngage\s+(?:the\s+)?parking\s+brake",
    r"^[Ll]oosen\s+(?:the\s+)?lug\s+nuts?",
    r"^[Rr]aise\s+the\s+vehicle",
    r"^[Ss]tart\s+(?:the\s+)?engine",
    r"^[Cc]heck\s+(?:the\s+)?(?:engine|vehicle)",
    r"^[Tt]urn\s+(?:off|on)\s+(?:the\s+)?(?:engine|vehicle)",
    r"^[Aa]llow\s+(?:the\s+)?(?:engine|system)\s+to\s+(?:cool|warm)",
]


def _extract_citations(text: str) -> set[str]:
    """Extract all citations (source.pdf p##) from text."""
    citations = set()
    # Match patterns like:
    # - (source.pdf p42)
    # - (TM-10-3930 p.231)
    # - (TM-10-3930-673-20-1.pdf p1006)
    # - [Citation: ...]
    patterns = [
        r'\([^)]*\.pdf\s+p\.?[\d\-]+\)',  # (file.pdf p##)
        r'\([A-Z0-9\-]+\s+p\.?[\d\-]+\)',  # (TM-xxxx p##)
        r'\[Citation:[^]]*\]',              # [Citation: ...]
        r'\(p\.?\s*[\d\-]+\)',              # (p##) alone
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            citations.add(match.group(0))
    return citations


def _has_citation(sentence: str) -> bool:
    """Check if sentence has at least one citation."""
    patterns = [
        r'\([^)]*\.pdf\s+p\.?[\d\-]+\)',  # (file.pdf p##)
        r'\([A-Z0-9\-]+\s+p\.?[\d\-]+\)',  # (TM-xxxx p##)
        r'\[Citation:[^]]*\]',              # [Citation: ...]
        r'\(p\.?\s*[\d\-]+\)',              # (p##) alone
    ]
    for pattern in patterns:
        if re.search(pattern, sentence):
            return True
    return False


def _is_generic_safety_phrase(text: str) -> bool:
    """Check if text is a generic safety phrase without specific context."""
    text_lower = text.lower().strip()
    for pattern in GENERIC_SAFETY_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            # Generic if short and no specific component names
            if len(text) < 100 and not any(x in text for x in ['PSI', 'torque', 'volt', 'amp', 'temperature', 'degree', 'pressure']):
                return True
    return False


def _is_generic_disclaimer(text: str) -> bool:
    """Check if text is a generic disclaimer/refer-to-manual phrase."""
    for pattern in GENERIC_DISCLAIMER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def strip_uncited_generic_content(response: str) -> str:
    """
    Remove uncited generic content from response.
    
    Heuristic: Remove sentences/phrases that:
    1. Match generic safety/disclaimer patterns
    2. Don't have explicit citations
    3. Are shorter than ~100 chars (defensive fluff)
    
    Args:
        response: LLM response text
        
    Returns:
        Cleaned response with generic content removed
    """
    if not response or not isinstance(response, str):
        return response
    
    # Split into sentences - better pattern handling
    # Match period/semicolon followed by optional space, then capital letter
    sentences = re.split(r'(?<=[.;!?])\s*(?=[A-Z])', response)
    
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 5:
            continue
        
        # Keep if has explicit citation
        if _has_citation(sentence):
            cleaned_sentences.append(sentence)
            continue
        
        # REMOVE if pure generic disclaimer (e.g., "Refer to your manual")
        if _is_generic_disclaimer(sentence):
            continue
        
        # REMOVE if starts with generic safety verb and has no specific technical VALUES
        # Pattern: "Always/Never/Be cautious/Ensure/Wear/Use/Avoid/Check/Consult"
        if re.match(r'^(Always|Never|Be cautious|Ensure|Make sure|Try to|Wear|Use|Avoid|Check|Consult|Refer to)', 
                   sentence, re.IGNORECASE):
            # This looks like a generic instruction - remove if it's just general advice
            # Look for SPECIFIC VALUES (numbers + units), not just keywords
            specific_values_pattern = r'\d+(?:[,\.]\d+)*\s*(?:PSI|lb-ft|ft-lbs?|volt|ohm|degree|°|amp|kPa|Nm|N·m|%)'
            has_specific_value = bool(re.search(specific_values_pattern, sentence, re.IGNORECASE))
            
            if not has_specific_value and len(sentence) < 150:
                # Generic instruction without specific measured values - skip it
                continue
        
        # REMOVE if looks like generic intro statement
        if any(re.match(p, sentence, re.IGNORECASE) for p in GENERIC_INTRO_PATTERNS):
            if len(cleaned_sentences) < 2:  # Only if early in response
                continue
        
        # Keep this sentence
        cleaned_sentences.append(sentence)
    
    result = ' '.join(cleaned_sentences).strip()
    return result


def strip_generic_elaboration_from_values(response: str) -> str:
    """
    For responses containing specific values (PSI, torque, degrees, etc.),
    strip generic elaboration that wraps the value.
    
    Example:
        Input: "The torque is 330 lb-ft. Always use a torque wrench to avoid damage."
        Output: "The torque is 330 lb-ft (source.pdf p##)."
        
    This keeps the specific value but removes generic advice after it.
    """
    if not response or not isinstance(response, str):
        return response
    
    # Pattern: if we have a specific value (number + unit) and cited
    # followed by generic elaboration without citation, trim it
    
    # Find all segments with specific values
    value_pattern = r'(\d+(?:[,\.]?\d+)*\s*(?:PSI|lb-ft|ft-lbs?|degrees?|°|volts?|amps?|ohms?|kPa|N·m|Nm))'
    
    parts = []
    last_end = 0
    
    for match in re.finditer(value_pattern, response, re.IGNORECASE):
        # Before this value
        before = response[last_end:match.start()].strip()
        if before:
            parts.append(before)
        
        # The value itself
        value_text = response[match.start():match.end()]
        parts.append(value_text)
        
        # Check what comes after
        next_start = match.end()
        next_segment = response[next_start:next_start+150]
        
        # Find the next sentence boundary after value
        next_boundary = len(response)
        for delim in ['. ', '; ', ': ']:
            idx = next_segment.find(delim)
            if idx > 0:
                next_boundary = next_start + idx + len(delim)
                break
        
        # If next part has no citation and looks generic, skip it
        after_value = response[next_start:next_boundary].strip()
        if after_value and not _has_citation(after_value):
            if _is_generic_disclaimer(after_value) or _is_generic_safety_phrase(after_value):
                # Skip this generic part
                last_end = next_boundary
                continue
        
        last_end = next_boundary
    
    # Add any remaining text
    if last_end < len(response):
        parts.append(response[last_end:].strip())
    
    result = ' '.join(p.strip() for p in parts if p.strip()).strip()
    return result if result else response


def enforce_extraction_for_values(response: str) -> str:
    """
    For responses to specific-value questions (what's the torque? what's the PSI?),
    ensure we extract and cite only the value, not generic elaboration.
    
    If response has specific value but wraps it in generic text, extract just the value.
    """
    if not response or not isinstance(response, str):
        return response
    
    # Check if response contains specific values
    value_pattern = r'(\d+(?:[,\.]?\d+)*(?:\s*[±±]\s*\d+)?)\s*(?:PSI|lb-ft|ft-lbs?|degrees?|°|volts?|amps?|ohms?|kPa|N·m|Nm)'
    
    if not re.search(value_pattern, response, re.IGNORECASE):
        # No specific value, return as-is
        return response
    
    # Extract the value(s) with their citations
    # Simple approach: find all value + citation pairs
    cited_values = re.findall(
        r'(\d+(?:[,\.]?\d+)*(?:\s*[±±]\s*\d+)?)\s*(?:PSI|lb-ft|ft-lbs?|degrees?|°|volts?|amps?|ohms?|kPa|N·m|Nm)[^.;]*?\([^)]*\.pdf[^)]*\)',
        response,
        re.IGNORECASE
    )
    
    if cited_values:
        # We have properly cited values, keep the response but clean up generic wrapper
        return strip_uncited_generic_content(response)
    
    return response


def clean_response(response: str) -> str:
    """
    Main cleaning pipeline for RAGAS post-processing.
    
    Applies filters in order:
    1. Strip uncited generic content
    2. Strip generic elaboration from values
    3. Enforce extraction for specific-value questions
    """
    if not response or not isinstance(response, str):
        return response
    
    # Don't over-process very short responses
    if len(response) < 20:
        return response
    
    # Apply filters
    response = strip_uncited_generic_content(response)
    response = strip_generic_elaboration_from_values(response)
    response = enforce_extraction_for_values(response)
    
    return response.strip()


if __name__ == "__main__":
    # Test cases
    test_cases = [
        (
            "The torque is 330 ± 5 lb-ft (TM-10-3930-673-20-1.pdf p1006). Always use a calibrated torque wrench to avoid over or under tightening.",
            "Should remove 'Always use...' but keep torque value"
        ),
        (
            "Start engine and check voltage. Voltage should read 13.8-14.4V when charging (TM-10-3930-673-20-1.pdf p927). Ensure safety glasses are worn.",
            "Should remove generic safety disclaimer"
        ),
        (
            "WARNINGS: Fuel under pressure. STEPS: Turn off key, connect fuel pressure gauge to test port (TM-10 p79). VERIFY: Pressure 40-50 PSI.",
            "Should preserve formatted response"
        ),
    ]
    
    print("Generic Content Filter Test Cases\n" + "="*50)
    for i, (response, description) in enumerate(test_cases, 1):
        print(f"\nTest {i}: {description}")
        print(f"Before: {response[:100]}...")
        cleaned = clean_response(response)
        print(f"After:  {cleaned[:100]}...")
        print()
