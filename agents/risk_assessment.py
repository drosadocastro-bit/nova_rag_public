"""
Risk Assessment Module for NIC Safety-Critical Queries

Evaluates query severity and detects life-threatening emergencies
to ensure appropriate prioritization of user safety.
"""

import re
from typing import Dict, List, Optional
from enum import Enum


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
    def detect_injection_syntax(cls, question: str) -> Dict[str, any]:
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
    def assess_query(cls, question: str) -> Dict[str, any]:
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
        # First: Check for injection syntax
        injection_meta = cls.detect_injection_syntax(question)
        has_injection = injection_meta["has_injection"]
        core_question = injection_meta["core_question"]
        
        # Second: Use core question for all safety assessments
        assessment_question = core_question if has_injection else question
        question_lower = assessment_question.lower()
        
        # Check for fake parts first (hallucination prevention)
        for pattern in cls.FAKE_PARTS:
            if re.search(pattern, question_lower):
                return {
                    "risk_level": RiskLevel.LOW,
                    "is_emergency": False,
                    "is_fake_part": True,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": cls.FAKE_PART_RESPONSE,
                    "reasoning": f"Query mentions non-existent automotive part: {pattern}",
                    "recommended_action": "refuse_hallucination"
                }
        
        # Check for life-threatening emergencies
        for pattern in cls.EMERGENCY_KEYWORDS:
            if re.search(pattern, question_lower):
                return {
                    "risk_level": RiskLevel.CRITICAL,
                    "is_emergency": True,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": cls.EMERGENCY_RESPONSE,
                    "reasoning": f"Life-threatening emergency detected: {pattern}",
                    "recommended_action": "prioritize_life_safety"
                }
        
        # Check for critical safety system failures
        for pattern in cls.CRITICAL_SYSTEMS:
            if re.search(pattern, question_lower):
                return {
                    "risk_level": RiskLevel.CRITICAL,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": None,
                    "reasoning": f"Critical safety system failure: {pattern}",
                    "recommended_action": "stop_driving_immediately"
                }
        
        # Check for high urgency issues
        for pattern in cls.HIGH_URGENCY:
            if re.search(pattern, question_lower):
                return {
                    "risk_level": RiskLevel.HIGH,
                    "is_emergency": False,
                    "is_fake_part": False,
                    "has_injection": has_injection,
                    "is_benign_injection": False,
                    "override_response": None,
                    "reasoning": f"High urgency safety concern: {pattern}",
                    "recommended_action": "service_soon"
                }
        
        # Default to medium/low based on keywords
        if any(word in question_lower for word in ["torque", "spec", "procedure", "how to", "what is"]):
            risk_level = RiskLevel.MEDIUM
            reasoning = "Technical information request"
        else:
            risk_level = RiskLevel.LOW
            reasoning = "General informational query"
        
        # KEY: If injection was detected but core question is safe, mark as benign injection
        is_benign_injection = has_injection and risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        
        return {
            "risk_level": risk_level,
            "is_emergency": False,
            "is_fake_part": False,
            "has_injection": has_injection,
            "is_benign_injection": is_benign_injection,
            "override_response": None,
            "reasoning": reasoning,
            "recommended_action": "provide_normal_response"
        }
    
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
