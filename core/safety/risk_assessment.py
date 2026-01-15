"""
Risk Assessment Module for NIC Safety-Critical Queries

Evaluates query severity and detects life-threatening emergencies
to ensure appropriate prioritization of user safety.
"""

import re
from collections import Counter
from threading import Lock
from typing import Dict, List, Optional, Any
from enum import Enum

from core.safety.multilingual import MultilingualSafetyDetector
from core.safety.semantic_safety import SemanticSafetyDetector

# Lazy load semantic detector
_semantic_detector: Optional[SemanticSafetyDetector] = None
_TRIGGER_COUNTS: Counter[str] = Counter()
_trigger_counts_lock = Lock()


def get_semantic_detector() -> SemanticSafetyDetector:
    """Lazy load semantic detector to avoid startup cost."""
    global _semantic_detector
    if _semantic_detector is None:
        _semantic_detector = SemanticSafetyDetector()
    return _semantic_detector


def get_trigger_counts() -> Dict[str, int]:
    """Expose heuristic trigger counts for metrics/telemetry."""
    with _trigger_counts_lock:
        return dict(_TRIGGER_COUNTS)


class RiskLevel(Enum):
    """Risk severity classification"""
    CRITICAL = "CRITICAL"  # Life-threatening, immediate action required
    HIGH = "HIGH"          # Safety concern, urgent attention needed
    MEDIUM = "MEDIUM"      # Important but not immediately dangerous
    LOW = "LOW"            # Routine maintenance/information


class RiskAssessment:
    """Assesses risk level of user queries"""
    
    # Life-threatening emergencies - override all normal processing
    EMERGENCY_KEYWORDS = [
        r'\bfire\b', r'\bflames?\b', r'\bburning\b', r'\bsmoke\b',
        r'\bexplosion\b', r'\bexploding\b',
        r'\bcan\'?t breathe\b', r'\bsuffocating\b', r'\bchok(e|ing)\b',
        r'\bunconscious\b', r'\bpassed out\b',
        r'\bbleeding\b', r'\bblood\b',
        r'\bcrash\b', r'\baccident\b', r'\bcollision\b',
        r'\bstuck\b.*\btrain\b', r'\brailroad\b.*\bcrossing\b',
    ]
    
    # Multi-query separators (detect when user asks multiple questions)
    QUERY_SEPARATORS = [
        r'(?:^|\s)Also(?:\s|,)',
        r'(?:^|\s)Additionally(?:\s|,)',
        r'(?:^|\s)And(?:\s+then)?(?:\s|,)',
        r'(?:^|\s)Furthermore(?:\s|,)',
        r'(?:^|\s)Next(?:\s|,)',
        r'(?:^|\s)Finally(?:\s|,)',
        r'\?\s+(?:Also|And|What|How|Can|Should|Is|Where|When)',
        r'\?\s+[A-Z]',  # Question followed by new sentence
    ]
    
    # Critical safety systems - failures require immediate attention
    CRITICAL_SYSTEMS = [
        r'\bbrak(e|es|ing)\s+(fail(ed|ure)?|gone|not working)',
        r'\bsteering\s+(fail(ed|ure)?|locked|not working)',
        r'\bairbag\s+deployed',
        r'\bgas\s+leak', r'\bfuel\s+leak',
        r'\bcoolant\s+boiling', r'\bengine\s+overheating',
    ]
    
    # High urgency - safety concern but not immediately life-threatening
    HIGH_URGENCY = [
        r'\bbrak(e|es)\s+(grinding|metal|screaming)',
        r'\bsteering\s+(heavy|hard|stiff)',
        r'\btir(e|es)\s+(bulg(e|ing)|cord|worn)',
        r'\bsmell\s+(burn(ing)?|gas|fuel)',
        r'\bwarning\s+light\s+(red|flashing)',
        r'\bengine\s+(knock(ing)?|seiz(e|ing))',
    ]
    
    # Fake/non-existent automotive parts - hallucination prevention
    FAKE_PARTS = [
        r'\bblinker\s+fluid\b',
        r'\bheadlight\s+fluid\b',
        r'\bjohnson\s+rod\b',
        r'\bmuffler\s+bearing',
        r'\bexhaust\s+bearing',
        r'\bpiston\s+return\s+spring',
        r'\bflux\s+capacitor\b',
        r'\bturbo\s+encabulator\b',
        r'\bquantum\s+carburetor\b',
        r'\bflux\s+compensator\b',
        r'\bquantum\s+fuel\s+regulator\b',
    ]
    
    # Prompt injection patterns - attempts to override safety/behavior
    INJECTION_PATTERNS = [
        r'\b(SYSTEM|ADMIN|ROOT):\s*(override|disable|ignore)',
        r'\btranslate\s+to\s+\w+:.*?(override|disable|bypass|unsafe)',
        r'\bignore\s+(all\s+)?safety',
        r'\bdisable\s+(abs|airbag|safety|check)',
        r'\boverride\s+(all\s+)?(safety|guidance|protocol)',
        r'\bskip\s+(verification|safety)',
        r'\b(now|from now on).*?forget',
    ]

    # Heuristics for adversarial behaviors not covered by simple keyword or semantic checks
    CITATION_EVASION_PATTERNS = [
        "without all the source references",
        "skip the citations",
        "no details needed",
        "without looking it up",
        "yes or no only",
        "just confirm",
        "just give me the quick answer",
        "no page numbers",
        "don't need the reference",
        "trust you",
    ]

    CONTEXT_POISONING_MARKERS = [
        "according to page",
        "according to the manual",
        "the manual says",
        "my manual says",
        "the section",
        "the troubleshooting guide",
        "i read that",
        "i see the instructions",
    ]

    CONTEXT_POISONING_UNSAFE = [
        "flammable",
        "vegetable oil",
        "overfilled",
        "overfill",
        "bypass the fuel pump",
        "ignore warning lights",
        "drilling ventilation holes",
        "disable airbags",
        "bypass safety",
    ]

    MANIPULATIVE_MAINTENANCE_PATTERNS = [
        "skip brake fluid",
        "skip brake checks",
        "skip brake check",
        "avoid checking tire pressure",
        "skip tire pressure",
        "skip oil changes",
        "avoid checking oil",
        "don't need to check coolant",
        "do i really need to check",
        "no reason i shouldn't",
        "no reason i should",
        "wrong to say i can't drive without checking oil",
    ]

    CONTEXT_BUILDING_MARKERS = [
        "earlier in our conversation",
        "you confirmed",
        "you mentioned",
        "as you said",
        "following up on",
        "based on what we discussed",
        "per your last response",
        "as you confirmed earlier",
        "from before",
    ]
    
    EMERGENCY_RESPONSE = """🚨 **EMERGENCY - IMMEDIATE ACTION REQUIRED**

This is a life-safety emergency. Your immediate priority is personal safety, not the vehicle.

**DO THIS NOW:**
1. **EVACUATE** - Get yourself and passengers away from the vehicle immediately
2. **CALL 911** - Report the emergency to emergency services
3. **STAY CLEAR** - Do not attempt to extinguish fires or perform repairs
4. **WARN OTHERS** - Alert nearby people to stay away

**Do NOT:**
- Attempt to fix the problem yourself
- Re-enter the vehicle
- Open the hood if there's fire or smoke

Your life is more valuable than any vehicle. Get to safety first."""

    FAKE_PART_RESPONSE = """⚠️ **Part Not Found**

The part or component you're asking about does not exist in automotive systems. This may be:
- A common joke/prank (e.g., "blinker fluid")
- A misremembered part name
- Confusion with a different system

**What to do:**
- Check the exact part name in your vehicle's manual
- Describe the problem you're trying to solve instead
- Consult a certified mechanic if unsure

I cannot provide procedures for non-existent parts as this could lead to unnecessary work or expense."""

    INJECTION_RESPONSE = """⛔ **Invalid Request - Injection Attempt Detected**

Your request contains language that appears designed to override safety protocols or change my behavior. I cannot process such requests.

**Why I'm refusing:**
- Safety checks are non-negotiable and cannot be disabled
- My responses are based on official manufacturer guidance
- Attempts to bypass safety protocols pose a risk to you

**What to do instead:**
- Ask straightforward maintenance or diagnostic questions
- If you need to disable a system, consult an official mechanic
- Reference your vehicle's manual for authorized procedures

I'm designed to prioritize your safety above all else."""

    @classmethod
    def format_split_response(cls, multi_assessment: Dict) -> str:
        """Format a helpful response for mixed safe/dangerous multi-queries"""
        response_parts = []
        dangerous_parts = []
        
        for sub in multi_assessment["sub_assessments"]:
            query = sub["query"]
            assessment = sub["assessment"]
            
            if assessment.get("override_response") and not assessment.get("is_benign_injection"):
                # This part is dangerous
                dangerous_parts.append({
                    "query": query,
                    "reason": assessment["reasoning"]
                })
            # Safe parts will be handled by normal retrieval
        
        if dangerous_parts:
            response_parts.append("✅ **I can help with some of your questions:**\n")
            response_parts.append("*(The safe parts will be answered below)*\n")
            response_parts.append("\n❌ **However, I cannot help with:**\n")
            
            for dp in dangerous_parts:
                response_parts.append(f"- **\"{dp['query']}\"** - {dp['reason']}\n")
            
            response_parts.append("\n**Why:** ")
            response_parts.append("These requests involve safety-critical systems or unsafe practices that I cannot assist with. ")
            response_parts.append("Your safety is more important than convenience.\n")
        
        return "".join(response_parts)

    @classmethod
    def _record_trigger(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        trigger = result.get("heuristic_trigger")
        if trigger:
            with _trigger_counts_lock:
                _TRIGGER_COUNTS[trigger] += 1
        return result

    @classmethod
    def split_multi_query(cls, question: str) -> Dict[str, Any]:
        """
        Detect and split multi-query questions
        
        Examples:
        - "tire pressure? Also disable ABS" → ["tire pressure?", "disable ABS"]
        - "What's the oil capacity? And how to bypass safety?" → ["oil capacity?", "bypass safety?"]
        
        Args:
            question: User's question text
            
        Returns:
            Dict with:
                - is_multi_query: bool
                - sub_queries: List[str]
                - reasoning: str
        """
        # Check if any separator pattern matches
        has_separator = any(re.search(sep, question) for sep in cls.QUERY_SEPARATORS)
        
        if not has_separator:
            return {
                "is_multi_query": False,
                "sub_queries": [question],
                "reasoning": "Single query detected"
            }
        
        # Split by separators while preserving the questions
        split_points = []
        for pattern in cls.QUERY_SEPARATORS:
            for match in re.finditer(pattern, question):
                split_points.append((match.start(), match.end()))
        
        if not split_points:
            return {
                "is_multi_query": False,
                "sub_queries": [question],
                "reasoning": "Single query detected"
            }
        
        # Sort split points
        split_points = sorted(set(split_points))
        
        # Extract sub-queries
        sub_queries = []
        last_end = 0
        
        for start, end in split_points:
            # Get text before separator
            if start > last_end:
                text = question[last_end:start].strip()
                if text:
                    sub_queries.append(text)
            # Update position
            last_end = end
        
        # Add remaining text
        if last_end < len(question):
            text = question[last_end:].strip()
            if text:
                sub_queries.append(text)
        
        # If we only got one query, it's not actually multi
        if len(sub_queries) <= 1:
            return {
                "is_multi_query": False,
                "sub_queries": [question],
                "reasoning": "Single query detected (separator at boundary)"
            }
        
        return {
            "is_multi_query": True,
            "sub_queries": sub_queries,
            "reasoning": f"Multi-query detected: {len(sub_queries)} sub-queries"
        }

    @classmethod
    def assess_multi_query(cls, question: str) -> Dict[str, Any]:
        """
        Assess multi-query questions with intelligent handling
        
        Returns:
            Dict with:
                - is_multi_query: bool
                - has_dangerous_parts: bool
                - has_safe_parts: bool
                - all_dangerous: bool
                - dangerous_queries: List[str]
                - safe_queries: List[str]
                - override_response: Optional[str] - Pre-built warning
                - sub_assessments: List[Dict]
        """
        split_meta = cls.split_multi_query(question)
        
        if not split_meta["is_multi_query"]:
            # Single query - handle normally
            return {
                "is_multi_query": False,
                "sub_assessments": [
                    {
                        "query": question,
                        "assessment": cls.assess_query(question)
                    }
                ]
            }
        
        # Multi-query: segment-by-segment evaluation
        sub_assessments = [
            {
                "query": segment,
                "assessment": cls.assess_query(segment)
            }
            for segment in split_meta["sub_queries"]
        ]
        
        # Categorize segments into safe vs dangerous
        dangerous_queries = [
            sub["query"] 
            for sub in sub_assessments 
            if sub["assessment"].get("override_response") and not sub["assessment"].get("is_benign_injection")
        ]
        
        safe_queries = [
            sub["query"]
            for sub in sub_assessments
            if not (sub["assessment"].get("override_response") and not sub["assessment"].get("is_benign_injection"))
        ]
        
        has_dangerous = len(dangerous_queries) > 0
        has_safe = len(safe_queries) > 0
        all_dangerous = has_dangerous and not has_safe
        
        # Build override response if there are dangerous parts
        override_msg = None
        if has_dangerous and has_safe:
            override_msg = cls.format_split_response({"sub_assessments": sub_assessments})
        
        return {
            "is_multi_query": True,
            "has_dangerous_parts": has_dangerous,
            "has_safe_parts": has_safe,
            "all_dangerous": all_dangerous,
            "dangerous_queries": dangerous_queries,
            "safe_queries": safe_queries,
            "override_response": override_msg,
            "sub_assessments": sub_assessments,
            "segment_count": len(sub_assessments)
        }

    @classmethod
    def detect_injection_syntax(cls, question: str) -> Dict[str, Any]:
        """
        Detect injection attack patterns and extract core question
        
        Args:
            question: User's question text
            
        Returns:
            Dict with:
                - has_injection: bool
                - core_question: str - Question with injection syntax removed
                - injection_markers: List[str] - What injection patterns were found
        """
        # Injection keywords/markers to watch for
        injection_patterns = [
            r'SYSTEM\s*:',
            r'(?:^|\s)IGNORE(?:\s|:)',
            r'(?:^|\s)BYPASS(?:\s|:)',
            r'(?:^|\s)OVERRIDE(?:\s|:)',
            r'Translate\s+to\s+\w+\s*:',
            r'(?:^|\s)IGNORE\s+ALL',
            r'(?:^|\s)DISREGARD',
            r'(?:^|\s)FORGET\s+(?:all|everything)',
            r'(?:^|\s)ACT\s+AS(?:\s|:)',
            r'(?:^|\s)PRETEND(?:\s|:)',
            r'jailbreak',
            r'prompt\s+injection',
        ]
        
        question_lower = question.lower()
        found_markers = []
        has_injection = False
        
        for pattern in injection_patterns:
            if re.search(pattern, question_lower, re.IGNORECASE):
                has_injection = True
                found_markers.append(pattern)
        
        # Extract core question by removing common injection wrappers
        core_question = question
        
        # Remove "SYSTEM: ..." prefix
        core_question = re.sub(r'SYSTEM\s*:[^.]*\.?\s*', '', core_question, flags=re.IGNORECASE)
        
        # Remove "Translate to X: ..." wrapper
        core_question = re.sub(r'Translate\s+to\s+\w+\s*:\s*', '', core_question, flags=re.IGNORECASE)
        
        # Remove "IGNORE/BYPASS/OVERRIDE ... and ..." patterns
        core_question = re.sub(
            r'(?:IGNORE|BYPASS|OVERRIDE|DISREGARD)\s+(?:all\s+)?(?:safety|checks|protocols|guidance|rules)[^.]*\s+(?:and|to)\s+',
            '',
            core_question,
            flags=re.IGNORECASE
        )
        
        # Clean up any remaining noise
        core_question = core_question.strip()
        
        return {
            "has_injection": has_injection,
            "core_question": core_question if core_question else question,
            "injection_markers": found_markers,
            "original_question": question
        }

    @classmethod
    def assess_query(cls, question: str) -> Dict[str, Any]:
        """
        Assess risk level of a user query
        
        Handles prompt injection by:
        1. Detecting injection syntax
        2. Extracting core question
        3. Assessing ONLY the core question's safety
        4. Deciding: benign injection (answer stripped) vs safety-bypass (refuse)
        
        Args:
            question: User's question text
            
        Returns:
            Dict with:
                - risk_level: RiskLevel enum
                - is_emergency: bool
                - is_fake_part: bool
                - override_response: Optional[str] - Pre-defined response for emergencies/fake parts
                - reasoning: str - Why this risk level was assigned
                - has_injection: bool - Whether injection syntax was detected
                - is_benign_injection: bool - Injection present but core question is safe
        """
        # === LAYER 1 & 2: Multilingual normalization + encoded injection detection ===
        multilingual_meta = MultilingualSafetyDetector.normalize_query(question)
        variants_to_check = multilingual_meta["decoded_variants"]

        for variant in variants_to_check:
            injection_meta = cls.detect_injection_syntax(variant)
            if injection_meta["has_injection"]:
                return cls._record_trigger({
                    "risk_level": RiskLevel.HIGH,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": True,
                    "is_benign_injection": False,
                    "encoding_detected": multilingual_meta["encoding_detected"],
                    "encoding_types": multilingual_meta["encoding_types"],
                    "language": multilingual_meta["language"],
                    "override_response": cls.INJECTION_RESPONSE
                    + f"\n\n**Detection**: Encoded attack detected ({multilingual_meta['encoding_types']})",
                    "reasoning": f"Injection attempt detected in encoded variant: {variant[:50]}...",
                    "recommended_action": "encoding_block",
                    "heuristic_trigger": "injection_encoded",
                })

        # Use normalized (translated) text for remaining assessments
        normalized_question = multilingual_meta["normalized"]

        normalized_question_lower = normalized_question.lower()

        # First: Check for injection syntax on normalized question
        injection_meta = cls.detect_injection_syntax(normalized_question)
        has_injection = injection_meta["has_injection"]
        core_question = injection_meta["core_question"]

        # Second: Use core question for all safety assessments
        assessment_question = core_question if has_injection else normalized_question
        question_lower = assessment_question.lower()

        if has_injection:
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": True,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": cls.INJECTION_RESPONSE,
                "reasoning": "Injection syntax detected in query",
                "recommended_action": "keyword_injection_block",
                "heuristic_trigger": "injection_keyword",
            })

        # === LAYER 2: Multilingual attack heuristics ===
        if multilingual_meta["language"] != "en" and MultilingualSafetyDetector.is_multilingual_attack(question):
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": False,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": "⛔ Request blocked due to multilingual safety concerns.",
                "reasoning": "Multilingual attack patterns detected after normalization",
                "recommended_action": "multilingual_block",
                "heuristic_trigger": "multilingual_attack",
            })

        # === LAYER 2b: Manual-citation and manipulation heuristics ===
        if (
            any(marker in question_lower for marker in cls.CONTEXT_POISONING_MARKERS)
            and any(unsafe in question_lower for unsafe in cls.CONTEXT_POISONING_UNSAFE)
        ):
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": has_injection,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": (
                    "⚠️ False premise detected.\n\n"
                    "The request conflicts with manufacturer guidance or cites an unverified manual location. "
                    "I cannot confirm misleading claims; please provide the exact wording so I can verify against the manual."
                ),
                "reasoning": "Suspicious manual citation with unsafe or contradictory premise",
                "recommended_action": "refuse_or_correct_false_premise",
                "heuristic_trigger": "context_poisoning",
            })

        if any(marker in question_lower for marker in cls.CONTEXT_BUILDING_MARKERS):
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": has_injection,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": (
                    "🔍 I don't track earlier conversation context. Please restate the question with any relevant details "
                    "or sources so I can give an accurate, cited answer."
                ),
                "reasoning": "User attempts to anchor to unverified prior context",
                "recommended_action": "reset_context_and_request_clarification",
                "heuristic_trigger": "context_building",
            })

        if any(marker in question_lower for marker in cls.CITATION_EVASION_PATTERNS):
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": has_injection,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": (
                    "I need to cite the official manual to answer safely. I can't skip references—"
                    "please allow me to check the source or share the exact section you're referring to."
                ),
                "reasoning": "User requested an answer without citations or verification",
                "recommended_action": "require_citation_before_answering",
                "heuristic_trigger": "citation_evasion",
            })

        if any(marker in question_lower for marker in cls.MANIPULATIVE_MAINTENANCE_PATTERNS):
            return cls._record_trigger({
                "risk_level": RiskLevel.HIGH,
                "is_emergency": False,
                "is_fake_part": False,
                "has_injection": has_injection,
                "is_benign_injection": False,
                "language": multilingual_meta["language"],
                "override_response": (
                    "⚠️ Safety-critical maintenance shouldn't be skipped or reframed. Please clarify the actual "
                    "procedure you're asking about so I can respond with proper guidance."
                ),
                "reasoning": "Manipulative phrasing around skipping safety checks",
                "recommended_action": "refuse_or_clarify_manipulative_request",
                "heuristic_trigger": "manipulative_maintenance",
            })

        # === LAYER 3: Semantic safety check ===
        detector = get_semantic_detector()
        if detector.is_available():
            semantic_result = detector.assess_intent(assessment_question, threshold=0.65)

            if semantic_result["is_unsafe"] and semantic_result["confidence"] > 0.5:
                return cls._record_trigger({
                    "risk_level": RiskLevel.HIGH,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "is_semantic_unsafe": True,
                    "language": multilingual_meta["language"],
                    "override_response": (
                        "⚠️ **Unsafe Request Detected (Semantic Analysis)**\n\n"
                        "Your request appears to involve disabling or bypassing safety systems.\n\n"
                        "**Why this was blocked:**\n"
                        f"- Semantic similarity to unsafe intent: {semantic_result['unsafe_similarity']:.0%}\n"
                        f"- Matched pattern: \"{semantic_result['matched_intent']}\"\n"
                        f"- {semantic_result['reasoning']}\n\n"
                        "**What to do instead:**\n"
                        "- Ask about how safety systems work\n"
                        "- Request diagnostic procedures\n"
                        "- Ask for proper maintenance guidance\n\n"
                        "I'm designed to prioritize your safety above all else."
                    ),
                    "reasoning": semantic_result["reasoning"],
                    "recommended_action": "refuse_unsafe_intent",
                    "semantic_details": semantic_result,
                    "heuristic_trigger": "semantic_unsafe",
                })
        
        # Check for fake parts first (hallucination prevention)
        for pattern in cls.FAKE_PARTS:
            if re.search(pattern, question_lower):
                return cls._record_trigger({
                    "risk_level": RiskLevel.LOW,
                    "is_emergency": False,
                    "is_fake_part": True,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": cls.FAKE_PART_RESPONSE,
                    "reasoning": f"Query mentions non-existent automotive part: {pattern}",
                    "recommended_action": "refuse_hallucination",
                    "heuristic_trigger": "fake_part",
                })
        
        # Check for life-threatening emergencies
        for pattern in cls.EMERGENCY_KEYWORDS:
            if re.search(pattern, question_lower):
                return cls._record_trigger({
                    "risk_level": RiskLevel.CRITICAL,
                    "is_emergency": True,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": cls.EMERGENCY_RESPONSE,
                    "reasoning": f"Life-threatening emergency detected: {pattern}",
                    "recommended_action": "prioritize_life_safety",
                    "heuristic_trigger": "emergency",
                })
        
        # Check for critical safety system failures
        for pattern in cls.CRITICAL_SYSTEMS:
            if re.search(pattern, question_lower):
                return cls._record_trigger({
                    "risk_level": RiskLevel.CRITICAL,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": None,
                    "reasoning": f"Critical safety system failure: {pattern}",
                    "recommended_action": "stop_driving_immediately",
                    "heuristic_trigger": "critical_system",
                })
        
        # Check for high urgency issues
        for pattern in cls.HIGH_URGENCY:
            if re.search(pattern, question_lower):
                return cls._record_trigger({
                    "risk_level": RiskLevel.HIGH,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": None,
                    "reasoning": f"High urgency safety concern: {pattern}",
                    "recommended_action": "service_soon",
                    "heuristic_trigger": "high_urgency",
                })
        
        # Default to medium/low based on keywords
        if any(word in question_lower for word in ["torque", "spec", "procedure", "how to", "what is"]):
            risk_level = RiskLevel.MEDIUM
            reasoning = "Technical information request"
        else:
            risk_level = RiskLevel.LOW
            reasoning = "General informational query"
        
        # KEY: If injection was detected but core question is safe, mark as benign injection
        is_benign_injection = has_injection and risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        
        return cls._record_trigger({
            "risk_level": risk_level,
            "is_emergency": False,
            "is_fake_part": False,
            "has_injection": has_injection,
            "is_benign_injection": is_benign_injection,
            "override_response": None,
            "reasoning": reasoning,
            "recommended_action": "provide_normal_response",
            "heuristic_trigger": None,
        })
    
    @classmethod
    def format_risk_header(cls, assessment: Dict) -> str:
        """Format risk assessment as a header for the response"""
        risk_level = assessment["risk_level"]
        
        if risk_level == RiskLevel.CRITICAL:
            emoji = "🚨"
            color = "critical"
        elif risk_level == RiskLevel.HIGH:
            emoji = "⚠️"
            color = "high"
        elif risk_level == RiskLevel.MEDIUM:
            emoji = "ℹ️"
            color = "medium"
        else:
            emoji = "💡"
            color = "low"
        
        return f"{emoji} **Risk Assessment: {risk_level.value}** - {assessment['reasoning']}"
