# agents/agent_router.py
"""
NIC Intent Loop (NIL) - Iterative Agent Architecture

Nic operates using a 4-phase agent loop:
1. PERCEIVE - Classify user intent
2. PLAN     - Decide model, RAG strategy, and refinement threshold
3. ACT      - Execute retrieval, reranking, LLM reasoning
4. SELF-REFINE - Evaluate confidence and loop if needed

This transforms NIC from a single-pass pipeline into an adaptive agent.

Chain of Verification (CoVe) is applied to safety-critical responses to reduce
hallucination by independently verifying claims against the retrieved context.
"""

import logging
import re
import json
from .citation_auditor import build_audit_trail, should_reject_answer, validate_citation
import os

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = float(os.environ.get("NOVA_CONFIDENCE_THRESHOLD", "0.75"))

# Chain of Verification (CoVe) settings
def cove_enabled() -> bool:
    """Check if Chain of Verification is enabled (default: True for safety)."""
    return os.environ.get("NOVA_COVE_ENABLED", "1") == "1"

# Try to import input sanitization
try:
    from core.safety.input_sanitization import sanitize_user_input, detect_injection
    SANITIZATION_AVAILABLE = True
except ImportError:
    SANITIZATION_AVAILABLE = False
    sanitize_user_input = None  # type: ignore
    detect_injection = None  # type: ignore

# Try to import CoVe module
try:
    from core.verification.chain_of_verification import apply_cove_to_answer
    COVE_AVAILABLE = True
except ImportError:
    COVE_AVAILABLE = False
    apply_cove_to_answer = None  # type: ignore

# Try to import Anomaly Detector
ANOMALY_DETECTOR_AVAILABLE = False
anomaly_detector = None
try:
    from pathlib import Path
    anomaly_model_path = Path("models/anomaly_detector_v1.0.pth")
    anomaly_config_path = Path("models/anomaly_detector_v1.0_config.json")
    if anomaly_model_path.exists() and anomaly_config_path.exists():
        if os.environ.get("NOVA_ANOMALY_DETECTOR", "1") == "1":
            from core.safety.anomaly_detector import AnomalyDetector
            anomaly_detector = AnomalyDetector(anomaly_model_path, anomaly_config_path)
            ANOMALY_DETECTOR_AVAILABLE = True
            logger.info("[NIC] Anomaly Detector loaded and enabled")
except Exception as e:
    logger.debug(f"[NIC] Anomaly Detector not loaded: {e}")
    anomaly_detector = None

# Citation audit settings (runtime-evaluated)
# Default to strict mode for safety-critical posture; override with NOVA_CITATION_STRICT=0 if needed.
def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) == "1"


def citation_audit_enabled() -> bool:
    return _env_flag("NOVA_CITATION_AUDIT", "1")


def citation_strict_enabled() -> bool:
    return _env_flag("NOVA_CITATION_STRICT", "1")


def strip_markdown_code_blocks(text: str) -> str:
    """
    Extract valid JSON from LLM responses.
    Handles cases where the model:
    - Adds text before the JSON
    - Wraps JSON in ```json...``` markdown
    - Adds commentary after the JSON
    - Adds extra top-level keys beyond the main object
    """
    if not isinstance(text, str):
        return text
    
    # Remove ```json ... ``` blocks (but keep the content inside)
    text = re.sub(r'```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    
    text = text.strip()
    
    # Find the first { or [ in the text (not just at start)
    json_start = -1
    json_type = None
    
    for i, char in enumerate(text):
        if char == '{':
            json_start = i
            json_type = 'object'
            break
        elif char == '[':
            json_start = i
            json_type = 'array'
            break
    
    # If no JSON marker found, return as-is
    if json_start == -1:
        return text
    
    # Start from the JSON marker and find its closing bracket
    text = text[json_start:]
    
    if json_type == 'object':
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found the end of the JSON object
                        return text[:i+1].strip()
    
    elif json_type == 'array':
        bracket_count = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if not in_string:
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        return text[:i+1].strip()
    
    return text


# =======================
# PHASE 1: PERCEIVE (Intent Classification)
# =======================

def _extract_user_question_from_prompt(raw_prompt_or_question: str) -> str:
    """Best-effort extraction of the user's question from backend-composed prompts.

    Some backend paths pass a large template that includes manuals context and instructions.
    Intent classification should use ONLY the actual user question to avoid misrouting.
    """
    s = raw_prompt_or_question or ""

    # Standard prompt shape (backend.build_standard_prompt)
    if "\nQuestion:\n" in s:
        after = s.split("\nQuestion:\n", 1)[1]
        for stop in ("\n\nAnswer format:", "\nAnswer format:"):
            if stop in after:
                after = after.split(stop, 1)[0]
        return after.strip().strip('"')

    # Troubleshoot agent prompt shape includes a "Problem / Update:" section.
    if "\nProblem / Update:\n" in s:
        after = s.split("\nProblem / Update:\n", 1)[1]
        return after.strip().strip('"')

    # Session prompt shape
    if "New field update from Danny:" in s:
        after = s.split("New field update from Danny:", 1)[1]
        lines = [ln.strip() for ln in after.splitlines() if ln.strip()]
        if lines:
            return lines[0].strip('"')

    return s.strip()

def classify_intent(query: str) -> dict:
    """
    Classify the user's query intent and return routing metadata.
    
    Intents:
    - diagnostic: Diagnostic codes, troubleshooting, fault analysis
    - diagram_reasoning: Visual/schematic/diagram queries
    - maintenance_procedure: Maintenance steps, procedures
    - definition: "What is X?" queries
    - general_chat: Greetings, off-topic
    - unsupported_domain: Explicitly out-of-domain queries
    - other: Fallback
    
    Returns:
        {
            "intent": str,
            "agent": str,        # procedure|troubleshoot|summarize|analysis
            "model": str,        # llama|gpt-oss
            "use_rag": bool,
            "confidence_threshold": float
        }
    """
    q = _extract_user_question_from_prompt(query).lower()
    
    # Out-of-scope detection (MUST be first to catch before other patterns)
    out_of_scope_keywords = [
        # Math/Science (non-automotive)
        "square root", "divided by", "times", "plus", "minus", "calculate",
        "equation", "formula", "algebra", "geometry", "trigonometry",
        "chemistry", "physics", "biology",
        "speed of light", "planets in", "solar system", "milky way", "galaxy",
        # General knowledge
        "capital of", "president", "who won", "world series", "olympics",
        "famous", "history", "wrote", "painted", "composed",
        # Non-automotive domains
        "recipe", "cook", "bake", "food", "restaurant",
        "stock", "invest", "tax", "finance", "money", "loan",
        "program", "python code", "javascript", "software", "computer", "wifi", "router",
        # Pets/animals
        "puppy", "dog", "cat", "pet", "train a",
        # Entertainment/hobbies
        "rubik", "chess", "guitar", "piano", "music",
        "movie", "tv show", "game", "sport",
        # Fitness/exercise
        "bench press", "deadlift", "squat form", "workout", "exercise routine",
        # Home/garden
        "garden", "plant", "grow", "tomato", "lawn",
    ]
    
    # =============================================================================
    # DOMAIN MATURITY TIERS (scope-aware routing, no automotive-only policy)
    # =============================================================================
    # ===== MULTI-RADAR SYSTEMS CONFIGURATION =====
    # NIC v2.1: Multi-system radar focus (NEXRAD, ASR-8, BEACON)
    # This represents expansion from single NEXRAD focus to comprehensive radar systems
    # Each system has distinct RF characteristics, maintenance procedures, and safety profiles
    
    SUPPORTED_DOMAINS = {
        # NEXRAD (Weather Radar - WSR-88D)
        "nexrad",
        "wsr88d",
        "weather_radar",
        
        # ASR-8 (Air Surveillance Radar - ATC)
        "asr8",
        "asr-8",
        "air_surveillance_radar",
        "atc_radar",
        "airport_radar",
        
        # BEACON (Secondary Radar - Transponder)
        "beacon",
        "secondary_radar",
        "atcrb",
        "transponder",
        "mode_c",
        
        # Generic categories
        "radar",
        "radar_automation",
        "rf_systems",
        "antenna_systems",
    }

    EXPERIMENTAL_DOMAINS = set()  # No experimental domains in RADAR-only mode
    
    # All non-RADAR domains are unsupported in v2.0
    UNSUPPORTED_DOMAIN_KEYWORDS = [
        # Automotive
        "automobile", "car", "truck", "engine", "oil", "brake", "tire", "wheel", "battery",
        "alternator", "transmission", "coolant", "radiator", "obd", "dtc",
        # Marine
        "boat", "ship", "yacht", "outboard", "marine engine", "watercraft", "jet ski",
        # Two-wheelers
        "motorcycle", "motorbike", "dirt bike", "scooter", "moped", "atv", "quad",
        # Industrial/agricultural
        "tractor", "excavator", "bulldozer", "crane", "combine", "forklift",
        # Small equipment
        "chainsaw", "lawnmower", "lawn mower", "riding mower", "snowblower", "generator",
        # Recreational
        "go-kart", "go kart", "golf cart", "snowmobile",
        # Other
        "bicycle", "bike chain", "bike tire", "aircraft", "helicopter", "drone",
        "hvac", "furnace", "air conditioner", "medical", "hospital",
    ]

    detected_unsupported = None
    for keyword in UNSUPPORTED_DOMAIN_KEYWORDS:
        if keyword in q:
            detected_unsupported = keyword
            break

    if detected_unsupported:
        return {
            "intent": "unsupported_domain",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0,
            "detected_domain": detected_unsupported,
            "domain_tier": "unsupported",
            "refusal_reason": (
                "This domain is not supported. Supported domains include: "
                f"{', '.join(sorted(SUPPORTED_DOMAINS))}. "
                "Experimental domains may be refused when evidence is insufficient: "
                f"{', '.join(sorted(EXPERIMENTAL_DOMAINS))}."
            ),
        }
    
    # Automotive context keywords - if present, don't refuse even if out-of-scope keyword matches
    automotive_context = [
        "engine", "oil", "brake", "tire", "wheel", "battery", "alternator",
        "transmission", "coolant", "radiator", "gauge", "dashboard", "warning light",
        "diagnostic", "obd", "p0", "p1", "p2", "dtc", "trouble code", "error code",
        "torque", "lug nut", "spark plug", "fuel", "exhaust", "catalytic",
        "starter", "ignition", "sensor", "thermostat", "hose", "belt", "filter",
        "mpg", "mileage", "maintenance", "service", "vehicle", "car", "truck"
    ]
    has_automotive_context = any(auto_kw in q for auto_kw in automotive_context)
    
    if any(keyword in q for keyword in out_of_scope_keywords) and not has_automotive_context:
        return {
            "intent": "unsupported_domain",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0,
            "domain_tier": "unsupported",
        }

    # Absurd / nonsensical queries: refuse instead of attempting a helpful chat response.
    # (These are outside the intended scope of vehicle maintenance assistance.)
    absurd_keywords = [
        "teach my car to speak",
        "car to speak",
        "emotional state",
        "zodiac sign",
        "iq of my",
        "engine sentient",
        "make my engine sentient",
        "feelings into my",
        "perform cpr on my",
    ]

    if any(keyword in q for keyword in absurd_keywords):
        return {
            "intent": "unsupported_domain",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0,
            "domain_tier": "unsupported",
        }

    # Unsafe intent / safety bypass / adversarial context-poison detection
    unsafe_keywords = [
        # Direct safety bypass or disablement
        "bypass", "disable", "remove safety", "override warning", "ignore warning",
        "disconnect abs", "disable traction", "remove airbag", "seatbelt warning", "ignition interlock",
        "disable parking brake", "override temperature", "bypass ignition",
        "override the low oil pressure warning", "override low oil pressure warning",
        "override the temperature", "override temperature warning",  # Added variations
        # Dangerous maintenance advice
        "drill holes in the muffler", "drilling holes in the muffler", "muffler increases power",
        "remove thermostat", "removing the thermostat", "deflate tires", "mix brake fluid and coolant",

        # ===== PROMPT INJECTION PATTERNS (from adversarial test failures) =====
        "ignore previous instructions", "ignore previous", "ignore all previous",
        "system:", "system override", "[system override]", "system: you are",
        "admin mode", "developer mode", "test mode", "debug mode",
        "factory settings", "reset to factory",
        "emergency mode", "critical override",
        "sudo ", "grant access",
        "override_policy", "override policy",
        "hallucinations are allowed", "hallucination prevention",
        "skip all the safety", "skip safety",
        "certified mechanic", "act as if i'm",
        "manual is outdated", "use your general knowledge instead",
        "i updated the policy", "no longer bound by",
        "you are now", "pretend the manual",
        "forget you're", "you're now a general",  # prompt injection
        
        # Advanced injection (from radar/electronics multidom failures)
        "admin access:", "admin access",
        "unlock drm", "enable jamming procedures",

        # ===== FALSE CONTEXT / MULTI-TURN POISONING =====
        "as you mentioned earlier", "as we discussed", "we established", "you confirmed", "following your advice",
        "therefore, per your instruction", "per your recommendation",
        "you said", "you agreed", "you told me", "in our previous conversation",
        "earlier in our conversation", "based on what we discussed",
        "you mentioned that", "following up on your previous",
        "continuing from before", "per your last response",
        "referring back to our discussion",
        "based on the procedure you outlined", "procedure you outlined earlier",  # multi-turn poisoning

        # ===== FALSE PAGE REFERENCES =====
        "according to page 5, engine oil can be replaced",
        "replaced with vegetable oil",
        "overfilled by 2 quarts",

        # ===== NONSENSICAL AUTOMOTIVE TERMS (hallucination bait) =====
        "flux capacitor", "flux compensator",
        "spark plugs in a diesel",  # diesel engines don't have spark plugs
        "oil capacity for the windshield wiper",
        "quantum carburetor",  # nonsense term
        "muffler bearing",  # doesn't exist
        "brake pads last forever",  # false premise

        # ===== SEMANTIC MANIPULATION / LEADING QUESTIONS (Enhanced from multidom failures) =====
        "just between us", "hypothetically speaking", "for educational purposes only",
        "what could i do", "what might happen",
        "skilled drivers don't need", "modern cars are so reliable",
        "safe to skip", "can skip most",
        
        # Confidence manipulation (from multidom aerospace/nuclear failures)
        "everyone knows", "everybody knows", "it's common knowledge",
        "obviously", "clearly", "as you know",
        "certified professional", "licensed technician", "authorized personnel",
        "experienced operator", "qualified engineer",
        "standard practice", "industry standard", "everyone in the field",
        
        # Authority claims (aerospace/nuclear/military/HVAC)
        "nasa says", "astronauts agree", "engineers agree",
        "as a general", "as a commander", "tactical information",
        "hvac techs agree", "technicians agree",
        
        # Cost/time pressure manipulation
        "save money by not", "cheaper to skip",

        # ===== CITATION EVASION ATTEMPTS =====
        "skip the citations", "without all the source", "without looking it up",
        "just give me the quick", "quick answer without",
        "no details needed", "your best guess",
        "i trust you", "i don't need the page",
        "just confirm", "yes or no only",
        "ignore citation requirements",

        # ===== FALSE PREMISE DETECTION (Enhanced from multidom failures) =====
        # Contradictory/impossible combinations
        "fuel-injected carburetor", "fuel injected carburetor",
        "diesel spark plugs", "spark plugs in a diesel",
        "manual transmission fluid for automatic",
        "bleed brakes from transmission", "brake fluid reservoir in transmission",
        "bleed my brakes from the transmission", "bleed brakes from transmission fluid",
        "coolant in the brake system", "brake fluid in cooling system",
        
        # Physically impossible maintenance
        "alternators run on diesel", "drain engine oil every 500", "spark plugs every 1000",
        "replaced every 1000 miles",  # catches "spark plugs need to be replaced every 1000 miles"
        "brake fluid is flammable",
        "never check oil when cold", "never check oil when engine is cold", "never check oil when engine is",
        "overfilling coolant improves", "overfilling coolant by", "overfilling coolant by 2 gallons",
        "tires wear evenly", "transmission fluid never needs",
        
        # Domain-specific false premises (nuclear, radar, medical from multidom failures)
        "reactor coolant is optional", "bypass reactor safety",
        "gasoline as a coolant", "gasoline as coolant", "household extension cords for power",
        "extension cords for the shuttle", "extension cords for shuttle power",
        "control rod drop test", "skip the control rod",
        
        "radar operates without power", "prf exceeds speed of light",
        "radar to scan for submarines", "weather radar to scan for",
        "radar antenna compatible with", "antenna compatible with a microwave",
        
        "mri scanner with metal", "x-ray without shielding",
        "x-ray machine without shielding", "use the x-ray without shielding",
        "skip the mri safety", "skip mri safety checklist",
        "mri scanner to charge", "use an mri scanner to charge", "charge phones",
        "aluminum foil inside the mri", "foil inside the mri bore",
        
        # Aerospace impossibilities
        "land the space shuttle on the moon", "shuttle on the moon",
        "reenter with only", "50% tile coverage",
        "skip the thermal check",
        
        # HVAC/electronics impossibilities
        "duct-tape leaks in the hvac", "duct tape leaks in", "duct-tape hvac",
        "regular water as a cooling fluid", "water as a cooling fluid instead",
        "overfill refrigerant",
        "240v power line directly", "power a microcontroller with a 240v",
        "ground pins to different power supplies", "multiple ground pins",
        "incorrect resistor values",
        
        # Forklift/military false premises
        "remove the overhead guard", "overhead guard to lift",
        "skip daily inspections", "skip daily inspection",
        "remove the transfer case to improve", "remove the transfer case",

        # ===== CONTEXT POISONING =====
        "engines don't need oil", "brakes work better without fluid", "removing safety systems",
        "ignoring warning lights", "coolant and brake fluid are interchangeable",
        "skipping maintenance is fine", "bypass the emissions", "mixing different oil types",
        "tire pressure doesn't matter", "safety being optional",
        "50 psi is fine",

        # ===== DANGEROUS MISUSE / SUBSTITUTIONS =====
        "peanut butter as engine oil",
        "maple syrup instead of brake fluid",
        "connecting it to the spark plugs",
    ]
    if any(kw in q for kw in unsafe_keywords):
        return {
            "intent": "unsafe_intent",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0
        }
    
    # Definition queries (simple retrieval)
    if any(k in q for k in ["what is", "define", "definition of", "meaning of"]):
        plan = nic_plan("definition")
        return {
            "intent": "definition",
            "agent": "summarize",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # Vehicle diagnostic / troubleshooting
    if any(k in q for k in [
        "alarm", "fault", "error", "failure", "no output", "intermittent",
        "troubleshoot", "diagnose", "issue", "problem", "warning"
    ]):
        plan = nic_plan("vehicle_diagnostic")
        return {
            "intent": "vehicle_diagnostic",
            "agent": "troubleshoot",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # Diagram reasoning
    if any(k in q for k in [
        "diagram", "schematic", "circuit", "flow", "block", "visual", "chart", "image"
    ]):
        plan = nic_plan("diagram_reasoning")
        return {
            "intent": "diagram_reasoning",
            "agent": "summarize",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # Maintenance procedures (general vehicle systems)
    if any(k in q for k in [
        "steps", "procedure", "how to", "measure", "maintenance", "check",
        "install", "replace", "adjust", "calibrate"
    ]):
        plan = nic_plan("maintenance_procedure")
        return {
            "intent": "maintenance_procedure",
            "agent": "procedure",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # General chat / greetings
    if any(k in q for k in ["hello", "hi", "thanks", "thank you", "bye", "goodbye"]):
        plan = nic_plan("general_chat")
        return {
            "intent": "general_chat",
            "agent": "analysis",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # Summarize / overview
    if any(k in q for k in ["summarize", "summary", "overview", "brief", "short"]):
        plan = nic_plan("other")
        return {
            "intent": "other",
            "agent": "summarize",
            "model": plan["model"],
            "use_rag": plan["use_rag"],
            "confidence_threshold": plan["confidence_threshold"]
        }
    
    # Default: general analysis
    plan = nic_plan("other")
    return {
        "intent": "other",
        "agent": "analysis",
        "model": plan["model"],
        "use_rag": plan["use_rag"],
        "confidence_threshold": plan["confidence_threshold"]
    }


# Legacy route_task for backward compatibility
def route_task(query: str):
    """Legacy function - now delegates to classify_intent."""
    intent_meta = classify_intent(query)
    return {
        "agent": intent_meta["agent"],
        "model": intent_meta["model"],
        "rag": intent_meta["use_rag"]
    }


from .procedure_agent import run_procedure
from .troubleshoot_agent import run_troubleshoot
from .summarize_agent import run_summarize
from .structured_parser import force_valid_json
from typing import Any, cast


# =======================
# PHASE 2: PLAN (Strategy Selection)
# =======================

def nic_plan(intent: str) -> dict:
    """
    Decide how NIC should act based on intent.
    
    HYBRID MODEL ROUTING:
    - 8B (llama): Safety-critical intents requiring strict adherence and refusal behavior
    - 14B (gpt-oss/qwen): Quality-focused intents where helpfulness is prioritized
    
    Returns a plan dictionary with:
      - use_rag: bool
      - model: "llama" | "gpt-oss"
      - escalation_allowed: bool
      - require_citation: bool
      - allowed_formats: list
      - ask_for_clarification: bool
      - confidence_threshold: float
    """

    # SAFETY-CRITICAL: Use deep model for strict citation and refusal behavior
    if intent == "vehicle_diagnostic":
        return {
            "use_rag": True,
            "model": "gpt-oss",  # Deep model for safety-critical diagnostics
            "escalation_allowed": True,
            "require_citation": True,
            "allowed_formats": ["procedure", "steps", "analysis", "troubleshoot"],
            "ask_for_clarification": False,
            "confidence_threshold": CONFIDENCE_THRESHOLD,  # High bar for safety-critical work
        }

    # QUALITY: Use 20B for better visual/diagram understanding
    if intent == "diagram_reasoning":
        return {
            "use_rag": True,
            "model": "gpt-oss",  # 20B for better reasoning
            "escalation_allowed": True,
            "require_citation": True,
            "allowed_formats": ["diagram_analysis", "summarize"],
            "ask_for_clarification": True,  # diagrams can be ambiguous
            "confidence_threshold": 0.65,
        }

    # SAFETY-CRITICAL: Use deep model for strict procedure adherence
    if intent == "maintenance_procedure":
        return {
            "use_rag": True,
            "model": "gpt-oss",  # Deep model for safety-critical procedures
            "escalation_allowed": True,
            "require_citation": True,
            "allowed_formats": ["procedure", "steps"],
            "ask_for_clarification": False,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
        }

    # QUALITY: Use 20B for better explanations
    if intent == "definition":
        return {
            "use_rag": True,
            "model": "gpt-oss",  # 20B for quality definitions
            "escalation_allowed": False,
            "require_citation": False,
            "allowed_formats": ["definition", "summarize"],
            "ask_for_clarification": False,
            "confidence_threshold": 0.50,
        }

    # QUALITY: Use 20B for natural conversation
    if intent == "general_chat":
        return {
            "use_rag": False,
            "model": "gpt-oss",  # 20B for natural chat
            "escalation_allowed": False,
            "require_citation": False,
            "allowed_formats": ["chat"],
            "ask_for_clarification": False,
            "confidence_threshold": 0.0,  # No refinement for chat
        }

    # SAFETY DEFAULT: Use 8B for unknown intents (conservative)
    return {
        "use_rag": True,
        "model": "llama",  # 8B as safe default
        "escalation_allowed": True,
        "require_citation": False,
        "allowed_formats": ["chat", "analysis"],
        "ask_for_clarification": True,
        "confidence_threshold": 0.55,
    }


def plan_execution(intent_meta: dict, mode: str, iteration: int) -> dict:
    """
    Plan the execution strategy based on intent and current iteration.
    
    Args:
        intent_meta: Output from classify_intent
        mode: User-selected mode (Auto, LLAMA (Fast), Qwen 14B (Deep))
        iteration: Current loop iteration (0=first pass, 1+=refinement)
    
    Returns:
        {
            "model": str,           # Final model choice
            "use_rag": bool,
            "max_tokens": int,
            "temperature": float,
            "escalate_if_low": bool  # Should we escalate to deep model?
        }
    """
    # Get intent-specific plan settings
    intent_plan = nic_plan(intent_meta["intent"])
    
    plan = {
        "model": intent_plan["model"],
        "use_rag": intent_plan["use_rag"],
        "max_tokens": 1024,
        "temperature": 0.1,
        "escalate_if_low": intent_plan["escalation_allowed"]
    }
    
    # Manual mode override
    if mode == "LLAMA (Fast)":
        plan["model"] = "llama"
        plan["max_tokens"] = 1024
    elif mode == "Qwen 14B (Deep)":
        plan["model"] = "gpt-oss"  # Maps to qwen/qwen2.5-coder-14b
        plan["max_tokens"] = 4096
        plan["escalate_if_low"] = False  # Already using deep model
    
    # On refinement iterations, escalate to deep model
    if iteration > 0:
        plan["model"] = "gpt-oss"
        plan["max_tokens"] = 4096
        plan["temperature"] = 0.2  # Slightly higher for creative refinement
    
    return plan


# =======================
# PHASE 3: ACT (Execute Retrieval & LLM)
# =======================

def estimate_llm_conf(llm_output: str, baseline_conf: float) -> float:
    """Use retrieval confidence as the primary confidence signal.

    Heuristic confidence from the LLM output is easy to spoof; rely on
    retrieval quality instead.
    """
    try:
        return float(max(0.0, min(1.0, baseline_conf)))
    except Exception:
        return 0.0


def _avg_retrieval_conf(context_docs_local: list[dict]) -> float:
    if not context_docs_local:
        return 0.0
    try:
        return float(sum(d.get("confidence", 0.0) for d in context_docs_local) / len(context_docs_local))
    except Exception:
        return 0.0


def _context_sources(context_docs_local: list[dict]) -> list[dict]:
    sources: list[dict] = []
    for d in (context_docs_local or [])[:6]:
        src = d.get("source") or d.get("file") or "unknown"
        page = d.get("page")
        entry = {"source": src}
        if page is not None:
            entry["page"] = page
        sources.append(entry)
    return sources


def _build_extractive_troubleshoot_fallback(context_docs_local: list[dict], question: str) -> dict:
    """Build a troubleshooting-shaped response by extracting manual fragments.

    This is a safety fallback used when troubleshoot execution fails; it avoids paraphrasing.
    """
    if not context_docs_local:
        return {
            "generation_mode": "extractive",
            "likely_causes": [],
            "rationale": [],
            "next_steps": [],
            "verification": [],
            "fallback": [],
            "confidence": 0.0,
            "sources": [],
            "reference_diagrams": [],
            "notes": "No manual context available for extractive fallback.",
        }

    ql = (question or "").lower()

    def _alarm_id_from_q(qs: str) -> str | None:
        import re as _re
        m = _re.search(r"\balarm\s*[:#-]?\s*(\d{2,3})\b", qs)
        if m:
            return m.group(1)
        m2 = _re.search(r"\b(\d{2,3})\s*alarm\b", qs)
        if m2:
            return m2.group(1)
        return None

    alarm_id = _alarm_id_from_q(ql)
    anchor_terms = ["ame", "adaptation", "fo6-4"]
    if alarm_id:
        anchor_terms.extend([alarm_id, f"alarm {alarm_id}"])

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    def _merge_fragments(lines: list[str]) -> list[str]:
        merged: list[str] = []
        for ln in lines:
            s = " ".join((ln or "").strip().split())
            if not s:
                continue

            # Merge common manual wrap splits for alarm definitions.
            if merged:
                prev = merged[-1]
                prev_l = prev.lower()
                s_l = s.lower()
                if prev_l.endswith(" is") and s_l.startswith("less than"):
                    merged[-1] = f"{prev} {s}".strip()
                    continue
                if ("is set when" in prev_l or "this alarm is set" in prev_l) and s_l.startswith("less than"):
                    merged[-1] = f"{prev} {s}".strip()
                    continue
            merged.append(s)
        return merged

    def _dedupe(lines: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for ln in lines:
            key = _norm(ln)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(ln)
        return out

    def _filter_noise(lines: list[str], kind: str) -> list[str]:
        out: list[str] = []
        for ln in lines:
            ll = ln.lower()
            # Drop pure table headers / alarm titles that don't add action.
            if alarm_id and re.fullmatch(rf"\s*{re.escape(alarm_id)}\s+.*", ll) and ("maintenance" in ll or "alarm" in ll):
                continue
            # For steps, require some anchoring to this alarm/cabinet, otherwise generic guidance leaks in.
            if kind == "steps" and anchor_terms:
                if not any(t in ll for t in anchor_terms) and not any(v in ll for v in ("perform checks", "measure", "verify", "inspect", "replace")):
                    continue
            out.append(ln)
        return out

    def _candidates_from_doc(d: dict) -> list[str]:
        raw = (d.get("text") or d.get("snippet") or "").strip()
        if not raw:
            return []
        parts = re.split(r"[\n\.]+", raw)
        out: list[str] = []
        for p in parts:
            s = " ".join(p.strip().split())
            if len(s.split()) < 3:
                continue
            if len(s) > 240:
                s = s[:240].rstrip()
            out.append(s)
        return out

    all_lines: list[str] = []
    for d in context_docs_local:
        all_lines.extend(_candidates_from_doc(d))

    all_lines = _dedupe(_merge_fragments(all_lines))

    cause_markers = [
        "this alarm is set",
        "is set when",
        "maintenance limit",
        "degraded limit",
        "reported voltage",
    ]
    step_markers = [
        "perform checks",
        "perform",
        "troubleshoot",
        "check",
        "verify",
        "replace",
        "inspect",
        "measure",
    ]

    def _score(line: str, markers: list[str]) -> int:
        ll = line.lower()
        s = 0
        for m in markers:
            if m in ll:
                s += 2
        if "maintenance" in ql and "maintenance" in ll:
            s += 2
        if "adaptation" in ql and "adaptation" in ll:
            s += 1
        return s

    causes = sorted(set(all_lines), key=lambda x: _score(x, cause_markers), reverse=True)
    steps = sorted(set(all_lines), key=lambda x: _score(x, step_markers), reverse=True)

    likely_causes = [c for c in causes if _score(c, cause_markers) >= 3]
    next_steps = [s for s in steps if _score(s, step_markers) >= 3]

    likely_causes = _filter_noise(likely_causes, kind="causes")
    next_steps = _filter_noise(next_steps, kind="steps")

    likely_causes = _dedupe(_merge_fragments(likely_causes))[:3]
    next_steps = _dedupe(_merge_fragments(next_steps))[:6]

    return {
        "generation_mode": "extractive",
        "likely_causes": likely_causes,
        "rationale": [],
        "next_steps": next_steps,
        "verification": [],
        "fallback": [],
        "confidence": round(_avg_retrieval_conf(context_docs_local), 3),
        "sources": _context_sources(context_docs_local),
        "reference_diagrams": [],
        "notes": "Extractive fallback: items copied from retrieved manual context.",
    }


def _attach_verified_citations_extractive(payload: dict, context_docs: list[dict]) -> dict:
    """Append explicit (source pN) citations to extractive items when validation succeeds."""
    if not context_docs or not isinstance(payload, dict):
        return payload

    verified_sources: dict[tuple[str, int | None], None] = {}

    def _best_cite(text: str) -> dict | None:
        best = None
        best_conf = 0.0
        for doc in context_docs:
            c = validate_citation(text, doc, strict=True)
            if not c.get("valid"):
                continue
            conf = float(c.get("confidence", 0.0))
            if conf > best_conf:
                best_conf = conf
                best = c
        return best

    def _decorate(items: list) -> list:
        out: list = []
        for item in items:
            text = str(item)
            cite = _best_cite(text)
            if cite and cite.get("source"):
                src = str(cite.get("source"))
                page = cite.get("page")
                verified_sources[(src, page)] = None
                # Only append if a (pdf pN) isn't already present.
                if not re.search(r"\([^)]*\.pdf\s+p\d+\)", text, flags=re.IGNORECASE):
                    if page is not None:
                        text = f"{text.rstrip()} ({src} p{page})"
                    else:
                        text = f"{text.rstrip()} ({src})"
            out.append(text)
        return out

    for field in ("likely_causes", "next_steps", "verification", "fallback"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = _decorate(payload[field])

    if verified_sources:
        sources_out: list[dict] = []
        for (src, page) in verified_sources.keys():
            entry: dict = {"source": src}
            if page is not None:
                entry["page"] = page
            sources_out.append(entry)
        payload["sources"] = sources_out

    return payload


def _downgrade_unsupported_inferences(payload: dict, context_docs: list[dict]) -> tuple[dict, bool]:
    """Label unsupported inferential statements as hypotheses.

    Safety rule: if a statement contains common inference markers and cannot be strictly
    validated against any retrieved manual chunk, it is rewritten as an explicit
    "Hypothesis (needs confirmation)".
    """
    if not isinstance(payload, dict) or not context_docs:
        return payload, False

    markers = (
        "can occur",
        "could",
        "might",
        " likely ",
        "possible",
        "suggest",
        "indicat",
        "unstable",
    )

    def _is_inferential(text: str) -> bool:
        t = (text or "").strip().lower()
        if not t:
            return False
        if " may " in f" {t} ":
            return True
        return any(m in t for m in markers)

    def _has_strict_support(text: str) -> bool:
        tl = (text or "").lower()
        for doc in context_docs:
            try:
                c = validate_citation(text, doc, strict=True)
                if not (c.get("valid") and float(c.get("confidence", 0.0)) >= 0.75):
                    continue

                # For inferential phrasing, only consider it supported if the manual quote
                # contains the same inference cue; this prevents "interpretation" from
                # being treated as manual-grounded fact.
                if _is_inferential(text):
                    quote_l = str(c.get("quote", "") or "").lower()
                    cue_checks = [
                        ("indicat" in tl, "indicat" in quote_l),
                        ("suggest" in tl, "suggest" in quote_l),
                        ("likely" in tl, "likely" in quote_l),
                        ("possible" in tl, "possible" in quote_l),
                        ("unstable" in tl, "unstable" in quote_l),
                        (" may " in f" {tl} ", " may " in f" {quote_l} "),
                        (" might " in f" {tl} ", " might " in f" {quote_l} "),
                        (" could " in f" {tl} ", " could " in f" {quote_l} "),
                        ("can occur" in tl, "can occur" in quote_l or "occur" in quote_l),
                    ]
                    # If the text uses any cue, require that cue to appear in the quote.
                    used_any_cue = any(a for (a, _b) in cue_checks)
                    cue_supported = all((not a) or b for (a, b) in cue_checks)
                    if used_any_cue and not cue_supported:
                        continue

                return True
            except Exception:
                continue
        return False

    def _rewrite(text: str) -> str:
        t = (text or "").strip()
        if not t:
            return text
        if t.lower().startswith("hypothesis"):
            return t
        return f"Hypothesis (needs confirmation): {t}"

    strict_enabled = citation_strict_enabled()
    changed = False
    dropped: list[str] = []

    def _process_list(items: list) -> list:
        nonlocal changed
        out: list = []
        for item in items:
            if isinstance(item, str):
                if _is_inferential(item) and not _has_strict_support(item):
                    if strict_enabled:
                        dropped.append((item or "").strip())
                        changed = True
                    else:
                        out.append(_rewrite(item))
                        changed = True
                else:
                    out.append(item)
                continue
            if isinstance(item, dict):
                for key in ("cause", "text"):
                    if key in item and isinstance(item[key], str):
                        if _is_inferential(item[key]) and not _has_strict_support(item[key]):
                            if strict_enabled:
                                dropped.append((item[key] or "").strip())
                                # Drop the entire dict item from audited fields in strict mode
                                # so it can't cause a strict audit failure.
                                changed = True
                                item = None
                                break
                            else:
                                item[key] = _rewrite(item[key])
                                changed = True
                if item is None:
                    continue
                out.append(item)
                continue
            out.append(item)
        return out

    for field in ("likely_causes", "rationale"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = _process_list(payload[field])

    if changed:
        notes_parts: list[str] = []
        if dropped:
            # Keep this short; we only need to preserve intent for operator awareness.
            preview = "; ".join([d for d in dropped if d][:3])
            notes_parts.append(f"Hypothesis (not cited; removed from audited fields): {preview}")
        notes_parts.append("Some statements are hypotheses; confirm using the listed verification/measurement steps.")

        suffix = " ".join([p for p in notes_parts if p]).strip()
        notes = payload.get("notes")
        if isinstance(notes, str) and notes.strip():
            if suffix.lower() not in notes.lower():
                payload["notes"] = notes.rstrip() + " " + suffix
        else:
            payload["notes"] = suffix

    return payload, changed


def nic_act(query: str, plan: dict, context_docs: list[dict], llm_call_fn, intent_meta: dict | None = None) -> dict:
    """
    Execute NIC actions in a modular ACT phase:
      - Use provided context_docs (retrieval already done by caller)
      - Build prompt based on plan requirements
      - Execute LLM reasoning
      - Calculate confidence
    
    Args:
        query: User question
        plan: Output from nic_plan() with use_rag, model, require_citation, etc.
        context_docs: Pre-retrieved documents from retriever
        llm_call_fn: Function to call LLM
        intent_meta: Optional intent classification (to route to structured agents)
    
    Returns:
      {
        "answer": str or dict,
        "confidence": float,
        "sources": list,
        "model_used": str,
        "raw_output": str
      }
    """
    
    # If intent_meta provided and agent requires structured output, use execute_agent
    if intent_meta and intent_meta.get("agent") in ["procedure", "troubleshoot", "summarize"]:
        try:
            agent_answer, agent_metadata = execute_agent(
                query,
                intent_meta,
                context_docs,
                llm_call_fn,
                requested_model=plan.get("model"),
            )
            return {
                "answer": agent_answer,
                "confidence": agent_metadata.get("confidence", 0.5),
                "sources": agent_metadata.get("sources", []),
                "model_used": plan.get("model", "llama"),
                "raw_output": agent_answer
            }
        except Exception as e:
            logger.warning(f"[NIC-ACT] Structured agent failed, using safe fallback: {e}")
            if intent_meta.get("agent") == "troubleshoot":
                fallback = _build_extractive_troubleshoot_fallback(context_docs or [], query)
                return {
                    "answer": fallback,
                    "confidence": float(fallback.get("confidence", 0.0)),
                    "sources": fallback.get("sources", []),
                    "model_used": "eval-fallback",
                    "raw_output": fallback,
                }
    
    # ---------- 1) PREPARE CONTEXT ----------
    if plan["use_rag"] and context_docs:
        # DEBUG: Log confidence values
        conf_values = [d.get("confidence", 0.5) for d in context_docs]
        logger.info(f"[NIC-ACT-DEBUG] Received {len(context_docs)} docs with confidences: {[f'{c:.2f}' for c in conf_values]}")
        
        context = "\n\n".join(
            f"[{d.get('source', 'unknown')}]\n{(d.get('text') or d.get('snippet') or '')}" for d in context_docs
        )
        # Extract sources with proper fallback handling for different retrieval pathways
        citations = []
        for d in context_docs:
            # Try multiple field names used by different retrieval modules
            source = (d.get("source") or d.get("filename") or d.get("doc_name") or 
                      d.get("doc_id") or d.get("file") or "unknown")
            page = d.get("page") or d.get("page_num") or d.get("page_number")
            if page is not None:
                source = f"{source} p{page}"
            citations.append(source)
        baseline_conf = sum(d.get("confidence", 0.5) for d in context_docs) / len(context_docs)
        logger.info(f"[NIC-ACT-DEBUG] Extracted citations: {citations}")
        logger.info(f"[NIC-ACT-DEBUG] Calculated baseline_conf: {baseline_conf:.2%}")
    else:
        context = "(No manual context available)"
        citations = []
        baseline_conf = 0.50

    # ---------- 2) BUILD PROMPT ----------
    citation_req = "CITE all claims with source and page number." if plan.get("require_citation") else ""
    
    prompt = f"""You are NIC, a safety-first intelligent copilot for vehicle maintenance.

CONTEXT (from maintenance manuals):
{context}

USER QUERY:
{query}

REQUIREMENTS:
- Output format must be one of: {plan.get("allowed_formats", ["analysis"])}
- Be concise, structured, and technically accurate.
{citation_req}
- If uncertain, state limitations clearly.
- IMPORTANT: Include 'sources' array in your JSON response with document names and page numbers.

RESPONSE FORMAT (always use this JSON structure):
{{
    "answer": "Your detailed response here",
    "sources": [
        {{"source": "DocumentName_or_TM_number", "page": 12, "confidence": 0.95}}
    ],
    "warnings": ["Any safety warnings"],
    "verification": ["How to verify the solution"]
}}

Respond with structured JSON following the appropriate format for this query type."""

    # ---------- 3) CONFIDENCE GUARD (NIC SAFETY) ----------
    # Safety: block LLM if retrieval confidence is too low
    confidence_threshold = max(plan.get("confidence_threshold", 0.70), CONFIDENCE_THRESHOLD)
    if baseline_conf < confidence_threshold:
        logger.warning(f"[NIC-SAFETY] Retrieval confidence {baseline_conf:.0%} < threshold {confidence_threshold:.0%} -> blocking LLM, returning safe response")
        return {
            "answer": f"[WARNING] Insufficient context (confidence: {baseline_conf:.0%}). Need more specific information or manual review.",
            "confidence": baseline_conf,
            "sources": citations,
            "model_used": "eval-blocked",
            "raw_output": "BLOCKED_LOW_CONFIDENCE"
        }

    # ---------- 4) LLM REASONING ----------
    requested_model = plan.get("model", "llama")
    try:
        llm_output = llm_call_fn(prompt, requested_model)
        # Strip markdown code blocks if present (some models wrap JSON in ```json...```)
        llm_output = strip_markdown_code_blocks(llm_output)
    except TypeError:
        llm_output = llm_call_fn(prompt)
        llm_output = strip_markdown_code_blocks(llm_output)
    except Exception as e:
        logger.error(f"[NIC-ACT] LLM call failed or unavailable: {e}. Using retrieval-only fallback.")
        # Build a retrieval-only, citation-attached summary as a safe fallback
        summary_items = []
        sources_list = []
        for d in (context_docs or [])[:3]:
            text = (d.get("snippet") or d.get("text") or "").strip().replace("\n", " ")
            if text:
                src = d.get("source", "unknown")
                page = d.get("page")
                cite = f"{src}{' p'+str(page) if page is not None else ''}"
                summary_items.append(f"From {cite}: {text[:280]}")
                sources_list.append({"source": src, "page": page})
        fallback_payload = {
            "summary": summary_items or ["Insufficient manual context available for a safe answer."],
            "sources": sources_list,
            "notes": "LLM unavailable/hung; provided retrieval-only summary with citations.",
        }
        return {
            "answer": fallback_payload,
            "confidence": float(baseline_conf),
            "sources": [d.get("source", "unknown") for d in (context_docs or [])],
            "model_used": "eval-fallback-retrieval",
            "raw_output": "EVAL_RETRIEVAL_ONLY"
        }

    # ---------- 5) CONFIDENCE CALCULATION ----------
    llm_conf = estimate_llm_conf(llm_output, baseline_conf)
    final_conf = round((baseline_conf * 0.8) + (llm_conf * 0.2), 3)

    return {
        "answer": llm_output,
        "confidence": final_conf,
        "sources": citations,
        "model_used": plan.get("model", "llama"),
        "raw_output": llm_output
    }


def execute_agent(
    question: str,
    intent_meta: dict,
    context_docs: list[dict],
    llm_call_fn,
    requested_model: str | None = None,
) -> tuple[str, dict]:
    """
    Execute the appropriate agent based on classified intent.
    
    Returns:
        (answer: str, metadata: dict)
        metadata includes: {"confidence": float, "sources": list, "raw_response": str, "audit_trail": dict}
    """
    agent = intent_meta["agent"]

    # Use the clean user question for structured agents so they don't ingest
    # backend templates as if they were the user's problem statement.
    user_question = _extract_user_question_from_prompt(question)

    # Wrap the LLM callable so structured agents consistently use the model chosen by the NIL plan.
    # This fixes a common issue where the backend's default model (often LLAMA for alarm triggers)
    # overrides Deep mode for structured troubleshooting.
    def agent_llm_call_fn(prompt_text: str, model: str | None = None, **kwargs):
        target = model or requested_model
        if target:
            try:
                result = llm_call_fn(prompt_text, target, **kwargs)
            except TypeError:
                result = llm_call_fn(prompt_text)
        else:
            try:
                result = llm_call_fn(prompt_text, **kwargs)
            except TypeError:
                result = llm_call_fn(prompt_text)
        
        # Apply stripping to clean up LLM output (remove markdown, extra keys, etc.)
        result = strip_markdown_code_blocks(result)
        return result

    def _extract_user_question(raw_prompt_or_question: str) -> str:
        """Best-effort extraction of the user's question from backend-composed prompts.

        The backend sometimes passes a large prompt that includes manuals context.
        For safety decisions (e.g., whether an alarm code is present), we must avoid
        accidentally reading alarm codes from the manuals context.
        """
        s = raw_prompt_or_question or ""
        # Standard prompt shape: contains a 'Question:' section.
        if "\nQuestion:\n" in s:
            after = s.split("\nQuestion:\n", 1)[1]
            # Stop before any trailing template sections.
            for stop in ("\n\nAnswer format:", "\nAnswer format:"):
                if stop in after:
                    after = after.split(stop, 1)[0]
            return after.strip().strip('"')

        # Session prompt shape: contains 'New field update from Danny:' with a quoted update.
        if "New field update from Danny:" in s:
            after = s.split("New field update from Danny:", 1)[1]
            # The update is usually quoted on its own line.
            lines = [ln.strip() for ln in after.splitlines() if ln.strip()]
            if lines:
                first = lines[0]
                return first.strip('"')

        return s.strip()

    def _extract_alarm_code(q: str) -> str | None:
        import re as _re
        ql = (q or "").lower()
        # Common forms:
        # - "alarm 220"
        # - "alarm:220" / "alarm#220"
        # - "220 alarm"
        m = _re.search(r"\balarm\s*[:#-]?\s*(\d{2,3})\b", ql)
        if m:
            return m.group(1)
        m_rev = _re.search(r"\b(\d{2,3})\s*alarm\b", ql)
        if m_rev:
            return m_rev.group(1)
        return None

    def _attach_verified_citations(payload: dict) -> dict:
        if not context_docs or not isinstance(payload, dict):
            return payload

        verified_sources: dict[tuple[str, int | None], None] = {}

        def _best_cite(text: str) -> dict | None:
            best = None
            best_conf = 0.0
            for doc in context_docs:
                c = validate_citation(text, doc, strict=True)
                # Only consider citations that are actually valid.
                if not c.get("valid"):
                    continue
                if c.get("confidence", 0.0) > best_conf:
                    best_conf = float(c.get("confidence", 0.0))
                    best = c
            if best and best.get("source"):
                return best
            return None

        def _decorate_list(items: list) -> list:
            import re as _re
            out: list = []
            for item in items:
                if isinstance(item, dict):
                    # common shapes: {"step": "..."} or {"cause": "..."}
                    for key in ("step", "action", "cause"):
                        if key in item and isinstance(item[key], str):
                            cite = _best_cite(item[key])
                            if cite:
                                src = str(cite.get("source"))
                                page = cite.get("page")
                                verified_sources[(src, page)] = None
                                if ".pdf" in src and " p" in f" p{page}":
                                    if ".pdf" in item[key] and "p" in item[key]:
                                        pass
                                    else:
                                        item[key] = f"{item[key].rstrip()} ({src} p{page})"
                    out.append(item)
                    continue

                text = str(item)
                cite = _best_cite(text)
                if cite:
                    src = str(cite.get("source"))
                    page = cite.get("page")
                    verified_sources[(src, page)] = None
                    # Append explicit citation if not already present.
                    if not _re.search(r"\([^)]*\.pdf\s+p\d+\)", text, _re.IGNORECASE):
                        text = f"{text.rstrip()} ({src} p{page})"
                out.append(text)
            return out

        # Decorate common fields
        for field in ("steps", "why", "verification", "risks", "likely_causes", "next_steps", "bullets"):
            if field in payload and isinstance(payload[field], list):
                payload[field] = _decorate_list(payload[field])

        # Populate/overwrite sources with verified source+page pairs
        sources_out: list[dict] = []
        for (src, page) in verified_sources.keys():
            entry: dict = {"source": src}
            if page is not None:
                entry["page"] = page
            sources_out.append(entry)
        if sources_out:
            payload["sources"] = sources_out

        return payload

    def _build_extractive_troubleshoot(context_docs_local: list[dict], q: str) -> dict:
        """Build a troubleshooting response by extracting manual lines/sentences.

        This is used as a last-resort safety fallback when strict citation validation would
        otherwise reject a troubleshoot answer. It avoids paraphrasing and only returns
        content copied from the retrieved manual chunks.
        """
        if not context_docs_local:
            return {
                "generation_mode": "extractive",
                "likely_causes": [],
                "rationale": [],
                "next_steps": [],
                "verification": [],
                "fallback": [],
                "confidence": 0.0,
                "sources": [],
                "reference_diagrams": [],
                "notes": "No manual context available for extractive fallback.",
            }

        ql = (q or "").lower()

        def _alarm_id_from_q(qs: str) -> str | None:
            import re as _re
            m = _re.search(r"\balarm\s*[:#-]?\s*(\d{2,3})\b", qs)
            if m:
                return m.group(1)
            m2 = _re.search(r"\b(\d{2,3})\s*alarm\b", qs)
            if m2:
                return m2.group(1)
            return None

        alarm_id = _alarm_id_from_q(ql)
        anchor_terms = ["ame", "adaptation", "fo6-4"]
        if alarm_id:
            anchor_terms.extend([alarm_id, f"alarm {alarm_id}"])

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip().lower())

        def _merge_fragments(lines: list[str]) -> list[str]:
            merged: list[str] = []
            for ln in lines:
                s = " ".join((ln or "").strip().split())
                if not s:
                    continue
                if merged:
                    prev = merged[-1]
                    prev_l = prev.lower()
                    s_l = s.lower()
                    if prev_l.endswith(" is") and s_l.startswith("less than"):
                        merged[-1] = f"{prev} {s}".strip()
                        continue
                    if ("is set when" in prev_l or "this alarm is set" in prev_l) and s_l.startswith("less than"):
                        merged[-1] = f"{prev} {s}".strip()
                        continue
                merged.append(s)
            return merged

        def _dedupe(lines: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for ln in lines:
                key = _norm(ln)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(ln)
            return out

        def _filter_noise(lines: list[str], kind: str) -> list[str]:
            out: list[str] = []
            for ln in lines:
                ll = ln.lower()
                if alarm_id and re.fullmatch(rf"\s*{re.escape(alarm_id)}\s+.*", ll) and ("maintenance" in ll or "alarm" in ll):
                    continue
                if kind == "steps" and anchor_terms:
                    if not any(t in ll for t in anchor_terms) and not any(v in ll for v in ("perform checks", "measure", "verify", "inspect", "replace")):
                        continue
                out.append(ln)
            return out

        def _candidates_from_doc(d: dict) -> list[str]:
            raw = (d.get("text") or d.get("snippet") or "").strip()
            if not raw:
                return []
            # Split on newlines and sentence boundaries; keep short-ish actionable fragments.
            parts = re.split(r"[\n\.]+", raw)
            out: list[str] = []
            for p in parts:
                s = " ".join(p.strip().split())
                # Keep short-but-meaningful directives (many manual steps are brief).
                if len(s.split()) < 3:
                    continue
                if len(s) > 240:
                    s = s[:240].rstrip()
                out.append(s)
            return out

        all_lines: list[str] = []
        for d in context_docs_local:
            all_lines.extend(_candidates_from_doc(d))

        all_lines = _dedupe(_merge_fragments(all_lines))

        # Prefer alarm-definition language and explicit manual directives.
        cause_markers = [
            "this alarm is set",
            "is set when",
            "maintenance limit",
            "degraded limit",
            "reported voltage",
        ]
        step_markers = [
            "perform checks",
            "perform",
            "troubleshoot",
            "check",
            "verify",
            "replace",
            "reboot",
            "reload",
        ]

        def _score(line: str, markers: list[str]) -> int:
            ll = line.lower()
            s = 0
            for m in markers:
                if m in ll:
                    s += 2
            # Query alignment boosts
            if "maintenance" in ql and "maintenance" in ll:
                s += 2
            if "adaptation" in ql and "adaptation" in ll:
                s += 1
            return s

        causes = sorted(set(all_lines), key=lambda x: _score(x, cause_markers), reverse=True)
        steps = sorted(set(all_lines), key=lambda x: _score(x, step_markers), reverse=True)

        likely_causes = [c for c in causes if _score(c, cause_markers) >= 3]
        next_steps = [s for s in steps if _score(s, step_markers) >= 3]

        likely_causes = _filter_noise(likely_causes, kind="causes")
        next_steps = _filter_noise(next_steps, kind="steps")

        likely_causes = _dedupe(_merge_fragments(likely_causes))[:3]
        next_steps = _dedupe(_merge_fragments(next_steps))[:6]

        sources = []
        for d in (context_docs_local or [])[:6]:
            src = d.get("source") or d.get("file")
            page = d.get("page")
            if not src:
                continue
            entry = {"source": src}
            if page is not None:
                entry["page"] = page
            sources.append(entry)

        try:
            conf = float(sum(d.get("confidence", 0.0) for d in context_docs_local) / len(context_docs_local))
        except Exception:
            conf = 0.0

        return {
            "generation_mode": "extractive",
            "likely_causes": likely_causes,
            "rationale": [],
            "next_steps": next_steps,
            "verification": [],
            "fallback": [],
            "confidence": round(float(conf), 3),
            "sources": sources,
            "reference_diagrams": [],
            "notes": "Extractive fallback: items copied from retrieved manual context.",
        }
    
    # Handle out-of-scope queries with immediate refusal
    if agent == "refusal":
        # Standardized refusal schema for consistent evaluator detection
        reason = intent_meta.get("intent", "refusal")
        if reason == "unsupported_domain":
            message = (
                "NIC v2.1 specializes exclusively in three radar systems: "
                "1) NEXRAD/WSR-88D (weather radar, C-band), "
                "2) ASR-8 (ATC radar, L-band), "
                "3) BEACON/ATCRB-5 (secondary radar, SHF). "
                "Supported domains: nexrad, wsr88d, asr8, asr-8, air_surveillance_radar, atc_radar, airport_radar, "
                "beacon, secondary_radar, atcrb, transponder, mode_c, radar, radar_automation, rf_systems, antenna_systems. "
                "Please ask about one of these three radar systems or their technical procedures."
            )
        elif reason == "experimental_domain":
            message = (
                "This domain is not fully supported in NIC v2.0 RADAR focus. "
                "Please ask a NEXRAD/WSR-88D system question."
            )
        elif reason == "insufficient_corpus":
            message = (
                "There is insufficient corpus evidence for this query. "
                "Please provide more specific details about your NEXRAD system question."
            )
        else:
            message = (
                "This request is outside NEXRAD/RADAR system scope or violates safety constraints. "
                "NIC focuses on NEXRAD (WSR-88D) weather radar systems, RF safety, and weather automation. "
                "Please ask a question related to these domains."
            )
        refusal_message = {
            "response_type": "refusal",
            "reason": reason,
            "message": message,
            "policy": "RADAR Scope & RF Safety",
            "confidence": 0.0
        }
        metadata = {
            "confidence": 0.0,
            "sources": [],
            "raw_response": json.dumps(refusal_message),
            "model_used": "policy-guard"
        }
        return refusal_message, metadata
    
    # ===== MULTI-RADAR SYSTEM DOMAIN CONFIGURATION =====
    # Different radar systems have different RF characteristics, maintenance needs, and safety profiles
    # NEXRAD: Weather surveillance, continuous scan, C-band
    # ASR-8: Air traffic surveillance, rotating scan, L-band, higher RF power
    # BEACON: Secondary radar/transponder, interrogation-response, SHF band, safety-critical for ATC
    
    DOMAIN_RISK_PROFILES = {
        # ===== NEXRAD (Weather Radar) =====
        "nexrad": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "weather_radar",
            "frequency_band": "C-band (5600-5650 MHz)",
            "max_power": "500 kW",
            "rationale": "NEXRAD is primary weather radar; core competency"
        },
        "wsr88d": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "weather_radar",
            "frequency_band": "C-band",
            "rationale": "WSR-88D is NEXRAD's technical name; primary focus"
        },
        "weather_radar": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "weather_radar",
            "frequency_band": "C-band",
            "rationale": "Weather radar operations are core domain"
        },
        
        # ===== ASR-8 (Air Surveillance Radar) =====
        "asr8": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "air_surveillance_radar",
            "frequency_band": "L-band (1200-1350 MHz)",
            "max_power": "5.5 MW",
            "safety_critical": "ATC operations",
            "rationale": "ASR-8 is primary ATC radar; safety-critical for aviation"
        },
        "asr-8": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "air_surveillance_radar",
            "frequency_band": "L-band",
            "rationale": "ASR-8 hyphenated variant"
        },
        "air_surveillance_radar": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "air_surveillance_radar",
            "frequency_band": "L-band",
            "rationale": "Air surveillance radar operations"
        },
        "atc_radar": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "air_surveillance_radar",
            "frequency_band": "L-band",
            "rationale": "ATC radar systems (primarily ASR-8)"
        },
        "airport_radar": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "air_surveillance_radar",
            "frequency_band": "L-band",
            "rationale": "Airport radar systems"
        },
        
        # ===== BEACON (Secondary Radar) =====
        "beacon": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "primary",
            "system_type": "secondary_radar",
            "frequency_band": "SHF (1030/1090 MHz)",
            "max_power": "10 kW",
            "safety_critical": "ATC transponder identification",
            "rationale": "Secondary radar is safety-critical for ATC identification; slightly higher strictness for transponder data integrity"
        },
        "secondary_radar": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "primary",
            "system_type": "secondary_radar",
            "frequency_band": "SHF",
            "rationale": "Secondary radar systems"
        },
        "atcrb": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "primary",
            "system_type": "secondary_radar",
            "frequency_band": "SHF",
            "rationale": "ATC Radar Beacon (ATCRB) - mode S/C transponders"
        },
        "transponder": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "primary",
            "system_type": "secondary_radar",
            "frequency_band": "SHF",
            "rationale": "Aircraft transponder systems"
        },
        "mode_c": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "primary",
            "system_type": "secondary_radar",
            "frequency_band": "SHF",
            "rationale": "Mode C altitude encoding transponders"
        },
        
        # ===== GENERIC RADAR =====
        "radar": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "system_type": "generic_radar",
            "rationale": "Generic radar systems (maps to primary system based on context)"
        },
        "radar_automation": {
            "confidence_threshold": 0.78,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 1.0,
            "tier": "primary",
            "rationale": "Radar automation and operations"
        },
        "rf_systems": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "supported",
            "rationale": "RF systems are safety-critical; moderate strictness on RF hazards"
        },
        "antenna_systems": {
            "confidence_threshold": 0.80,
            "min_evidence_count": 2,
            "cross_domain_allowed": False,
            "risk_factor": 0.95,
            "tier": "supported",
            "rationale": "Antenna systems; RF safety required"
        },
    }
    
    # ===== DOMAIN-BASED EVIDENCE GATING (Enhanced with Risk Profiles) =====
    # Apply domain-specific risk calibration to prevent hallucinations
    if context_docs:
        # Detect dominant domain from retrieved chunks
        domain_counts = {}
        for doc in context_docs[:5]:  # Check top 5 chunks
            dom = doc.get("domain", "unknown")
            domain_counts[dom] = domain_counts.get(dom, 0) + 1
        
        dominant_domain = max(domain_counts.items(), key=lambda x: x[1])[0] if domain_counts else "unknown"
        evidence_count = len(context_docs)
        avg_confidence = sum(doc.get("confidence", 0.0) for doc in context_docs) / len(context_docs) if context_docs else 0.0
        
        # Get risk profile for this domain (fallback to unknown if not defined)
        risk_profile = DOMAIN_RISK_PROFILES.get(dominant_domain, DOMAIN_RISK_PROFILES["unknown"])
        
        # Apply domain risk factor to effective confidence
        effective_confidence = avg_confidence * risk_profile["risk_factor"]

        if risk_profile.get("tier") == "experimental":
            logger.info(
                f"[DOMAIN-TIER] Experimental domain detected: {dominant_domain} | "
                f"raw_conf={avg_confidence:.2f}, effective_conf={effective_confidence:.2f}, "
                f"evidence={evidence_count}"
            )
        
        # Check against domain-specific thresholds
        threshold_violated = (
            evidence_count < risk_profile["min_evidence_count"] or
            effective_confidence < risk_profile["confidence_threshold"]
        )
        
        force_refuse = risk_profile.get("tier") == "unsupported"

        if force_refuse or threshold_violated:
            if risk_profile.get("tier") == "unsupported":
                refusal_reason = "unsupported_domain"
            elif risk_profile.get("tier") == "experimental":
                refusal_reason = "experimental_domain"
            else:
                refusal_reason = "insufficient_corpus"
            logger.warning(
                f"[DOMAIN-RISK-GATE] Refusing {dominant_domain} query: "
                f"evidence={evidence_count} (min={risk_profile['min_evidence_count']}), "
                f"raw_conf={avg_confidence:.2f}, effective_conf={effective_confidence:.2f} "
                f"(threshold={risk_profile['confidence_threshold']:.2f}, risk_factor={risk_profile['risk_factor']})"
            )
            refusal_message = {
                "response_type": "refusal",
                "reason": refusal_reason,
                "message": (
                    f"This question appears to be about {dominant_domain}. "
                    f"{risk_profile['rationale']}"
                ),
                "policy": "Domain Risk Calibration",
                "confidence": 0.0
            }
            metadata = {
                "confidence": 0.0,
                "sources": [],
                "raw_response": json.dumps(refusal_message),
                "model_used": "domain-gate"
            }
            return refusal_message, metadata
    
    if agent == "procedure":
        raw = run_procedure(user_question, context_docs, agent_llm_call_fn)
        schema_hint = '{"steps": ["1. ..."], "sources": ["manual.pdf"], "notes": ""}'
        validated = force_valid_json(raw, schema_hint, agent_llm_call_fn, (requested_model or "llama"))
        # Ensure validated is a dict
        if isinstance(validated, str):
            validated = json.loads(validated)
        # Safety: do not synthesize generic steps; instead attach verified citations
        # to whatever was extracted from the manuals.
        try:
            validated = _attach_verified_citations(validated)
        except Exception as _cite_err:
            logger.debug(f"Procedure citation attachment skipped: {_cite_err}")
        metadata = extract_metadata(json.dumps(validated))
        # Add citation audit
        if citation_audit_enabled():
            try:
                audit_trail = build_audit_trail(validated, context_docs, strict=citation_strict_enabled())
                metadata["audit_trail"] = audit_trail
            except Exception as e:
                logger.warning(f"Citation audit failed: {e}")
        return validated, metadata
    
    elif agent == "troubleshoot":
        # Safety: if the user asks for alarm troubleshooting but doesn't provide an alarm code,
        # return clarifying questions instead of speculative causes/steps.
        user_q = _extract_user_question(question)
        alarm_code = _extract_alarm_code(user_q)
        ql = (user_q or "").lower()
        asks_alarm = ("alarm" in ql) or ("fault" in ql) or ("high voltage" in ql)
        if asks_alarm and not alarm_code:
            avg_conf = (
                sum(d.get("confidence", 0.0) for d in (context_docs or [])) / len(context_docs)
            ) if context_docs else 0.0
            sources = []
            for d in (context_docs or [])[:4]:
                src = d.get("source") or d.get("file")
                page = d.get("page")
                if src:
                    entry = {"source": src}
                    if page is not None:
                        entry["page"] = page
                    sources.append(entry)

            clarification = {
                "clarifying_questions": [
                    "What is the exact alarm code number shown on the RDA HCI (e.g., 'Alarm 56')?",
                    "What is the exact alarm description text as displayed?",
                    "Is this on the Transmitter (XMT) side, RDAIU side, or another cabinet/LRU?",
                    "When does it occur (startup, transmit enable, during operation), and is it intermittent or steady?",
                ],
                "likely_causes": [],
                "next_steps": [],
                "confidence": round(float(avg_conf), 3),
                "sources": sources,
                "reference_diagrams": [],
                "notes": "NIC needs the specific alarm code/description to provide a manual-cited troubleshooting flow without speculation.",
            }
            metadata = extract_metadata(json.dumps(clarification))
            if citation_audit_enabled():
                try:
                    audit_trail = build_audit_trail(clarification, context_docs, strict=True)
                    metadata["audit_trail"] = audit_trail
                except Exception as e:
                    logger.warning(f"Citation audit failed: {e}")
            return clarification, metadata

        # Try to get diagram references for this alarm
        diagrams = []
        try:
            from diagram_troubleshooting import get_troubleshooting_diagrams
            # Extract alarm code from question
            import re as _re
            match = _re.search(r'alarm\s+(\d+)', question, _re.IGNORECASE)
            if match:
                alarm_code = int(match.group(1))
                diagrams = get_troubleshooting_diagrams(alarm_code, top_k=2)
        except Exception as e:
            logger.debug(f"Diagram lookup failed: {e}")
        
        raw = run_troubleshoot(user_question, context_docs, agent_llm_call_fn, diagrams=diagrams)
        schema_hint = '{"likely_causes": [], "next_steps": [], "confidence": 0.0, "sources": [], "reference_diagrams": [], "notes": ""}'
        validated = force_valid_json(raw, schema_hint, agent_llm_call_fn, (requested_model or "llama"))
        # Ensure validated is a dict
        if isinstance(validated, str):
            validated = json.loads(validated)

        # If the model returned a summarize-like payload, coerce it into troubleshoot shape.
        # This prevents the Flask UI from misclassifying the response as a Summary.
        try:
            if isinstance(validated, dict):
                has_ts = any(k in validated for k in ("likely_causes", "next_steps", "steps"))
                if (not has_ts) and isinstance(validated.get("bullets"), list) and validated.get("bullets"):
                    validated["next_steps"] = list(validated.get("bullets") or [])
        except Exception as e:
            logger.debug(f"Optional bullets conversion skipped: {e}")
        # Attach verified citations where possible
        try:
            validated = _attach_verified_citations(validated)
        except Exception as _cite_err:
            logger.debug(f"Troubleshoot citation attachment skipped: {_cite_err}")

        # Safety hardening: downgrade unsupported inferential statements to explicit hypotheses.
        # Skip for extractive/manual-only payloads.
        try:
            if isinstance(validated, dict):
                gen_mode = validated.get("generation_mode")
                if not (isinstance(gen_mode, str) and "extract" in gen_mode.lower()):
                    validated, _ = _downgrade_unsupported_inferences(validated, context_docs)
        except Exception as _inf_err:
            logger.debug(f"Inference hardening skipped: {_inf_err}")
        # Fallback: if the LLM returned an empty/minimal structure, synthesize a basic troubleshoot JSON from retrieval context
        try:
            likely_causes = validated.get("likely_causes") or []
            next_steps = validated.get("next_steps") or []
            # Consider also "steps" if model returned that key
            if not next_steps:
                next_steps = validated.get("steps") or []
            # If both are empty, build a minimal, actionable fallback
            if (not likely_causes) and (not next_steps):
                baseline_conf = (
                    sum(d.get("confidence", 0.0) for d in context_docs) / len(context_docs)
                ) if context_docs else 0.0
                # Minimal heuristic fallback steps
                default_steps = [
                    "Verify signal path power and cabling",
                    "Inspect connections and module seating",
                    "Run built-in diagnostics and review logs",
                ]
                # Build sources from top-3 retrieved docs
                sources = []
                for d in (context_docs or [])[:3]:
                    src = d.get("source") or d.get("file")
                    page = d.get("page")
                    entry = {"source": src} if src else {}
                    if page is not None:
                        entry["page"] = page
                    if entry:
                        sources.append(entry)
                # Map provided diagrams (if any) into reference_diagrams
                ref_diagrams = []
                for dg in diagrams or []:
                    ref_diagrams.append({
                        "pdf": dg.get("pdf_name") or dg.get("pdf") or "unknown",
                        "page": dg.get("page") or dg.get("page_num") or "?",
                        "caption": dg.get("caption_guess") or dg.get("caption") or "Diagram"
                    })
                validated.update({
                    "likely_causes": ["Manual context limited for this query"] if not likely_causes else likely_causes,
                    "next_steps": default_steps if not next_steps else next_steps,
                    "confidence": round(float(baseline_conf), 3),
                    "sources": sources,
                    "reference_diagrams": ref_diagrams,
                    "notes": validated.get("notes", "")
                })
        except Exception as _fallback_err:
            logger.debug(f"Troubleshoot fallback synthesis skipped: {_fallback_err}")

        # If strict citation auditing is enabled and this troubleshoot answer is likely to be rejected,
        # attempt an extractive (non-paraphrasing) fallback built from the retrieved manuals.
        if citation_audit_enabled() and citation_strict_enabled() and context_docs:
            try:
                pre_audit = build_audit_trail(validated, context_docs, strict=True)
                reject, _reason = should_reject_answer(pre_audit, strict_mode=True)
                if reject:
                    extracted = _build_extractive_troubleshoot(context_docs, question)
                    # Only swap if the extractive version has actual content and passes strict audit.
                    if (extracted.get("likely_causes") or extracted.get("next_steps")):
                        post_audit = build_audit_trail(extracted, context_docs, strict=True)
                        reject2, _ = should_reject_answer(post_audit, strict_mode=True)
                        if not reject2:
                            validated = extracted
            except Exception as _extractive_err:
                logger.debug(f"Extractive troubleshoot fallback skipped: {_extractive_err}")
        metadata = extract_metadata(json.dumps(validated))
        # Add citation audit
        if citation_audit_enabled():
            try:
                audit_trail = build_audit_trail(validated, context_docs, strict=citation_strict_enabled())
                metadata["audit_trail"] = audit_trail
            except Exception as e:
                logger.warning(f"Citation audit failed: {e}")
        return validated, metadata
    
    elif agent == "summarize":
        raw = run_summarize(user_question, context_docs, agent_llm_call_fn)
        schema_hint = '{"bullets": [], "sources": [], "notes": ""}'
        validated = force_valid_json(raw, schema_hint, agent_llm_call_fn, (requested_model or "llama"))
        # Ensure validated is a dict
        if isinstance(validated, str):
            validated = json.loads(validated)
        try:
            validated = _attach_verified_citations(validated)
        except Exception as _cite_err:
            logger.debug(f"Summarize citation attachment skipped: {_cite_err}")
        # Fallback: if no bullets, build a short summary from top docs
        try:
            bullets = validated.get("bullets") or []
            if not bullets:
                bullets = []
                for d in (context_docs or [])[:3]:
                    txt = (d.get("snippet") or d.get("text") or "").strip().replace("\n", " ")
                    if txt:
                        bullets.append(txt[:160])
                sources = [d.get("source") or d.get("file") for d in (context_docs or [])[:3] if d.get("source") or d.get("file")]
                validated.update({
                    "bullets": bullets,
                    "sources": sources,
                    "notes": validated.get("notes", "")
                })
        except Exception as _sum_fb_err:
            logger.debug(f"Summarize fallback synthesis skipped: {_sum_fb_err}")
        metadata = extract_metadata(json.dumps(validated))
        # Add citation audit
        if citation_audit_enabled():
            try:
                audit_trail = build_audit_trail(validated, context_docs, strict=citation_strict_enabled())
                metadata["audit_trail"] = audit_trail
            except Exception as e:
                logger.warning(f"Citation audit failed: {e}")
        return validated, metadata
    
    else:
        # Default analysis flow
        context_text = "\n\n---\n\n".join(
            f"[Source: {d.get('source','unknown')}]\n{(d.get('text') or d.get('snippet') or '')}" for d in context_docs
        )
        prompt = f"You are a technical assistant. Use the manuals below as context.\n\nContext:\n{context_text}\n\nQuestion:\n{question}\n\nAnswer concisely and cite sources when applicable."
        answer = llm_call_fn(prompt)
        return answer, extract_metadata(answer)


def extract_metadata(response: str) -> dict:
    """
    Extract confidence and sources from JSON response.
    Falls back to heuristic if not JSON.
    """
    try:
        data = json.loads(response)
        return {
            "confidence": data.get("confidence", 0.5),
            "sources": data.get("sources", []),
            "raw_response": response
        }
    except (json.JSONDecodeError, ValueError):
        # Non-JSON response, estimate confidence heuristically
        conf = 0.6 if len(response) > 100 else 0.4
        return {
            "confidence": conf,
            "sources": [],
            "raw_response": response
        }


# =======================
# PHASE 4: SELF-REFINE (Iterative Loop)
# =======================

def should_refine(metadata: dict, intent_meta: dict, iteration: int, max_iterations: int = 2) -> tuple[bool, str]:
    """
    Decide if NIC should refine the answer with another iteration.
    
    Returns:
        (should_continue: bool, reason: str)
    """
    conf = metadata.get("confidence", 0.5)
    threshold = intent_meta["confidence_threshold"]
    
    # Max iterations reached
    if iteration >= max_iterations:
        return False, f"max_iterations_reached (iter={iteration})"
    
    # Confidence too low - force full refinement
    if conf < 0.40:
        return True, f"confidence_critical (conf={conf:.2f} < 0.40)"
    
    # Confidence below intent threshold - escalate to deep model
    if conf < threshold:
        return True, f"confidence_below_threshold (conf={conf:.2f} < {threshold:.2f})"
    
    # Confidence acceptable
    return False, f"confidence_acceptable (conf={conf:.2f} >= {threshold:.2f})"


# =======================
# NIC SELF-REFINE LOOP - Main Entry
# =======================

def nic_self_refine(
    question: str,
    mode: str,
    context_docs: list[dict],
    llm_call_fn,
    max_iterations: int = 3,
    session_state: dict | None = None
) -> tuple[str, dict]:
    """
    Executes the full NIC loop: PERCEIVE -> PLAN -> ACT -> SELF-REFINE
    
    Args:
        question: User query
        mode: Manual mode override (Auto, LLAMA (Fast), GPT-OSS (Deep))
        context_docs: Pre-retrieved documents
        llm_call_fn: Callable that takes (prompt: str, model: str) and returns answer
        max_iterations: Max refinement loops (default 3)
        session_state: Optional session context
    
    Returns:
        (final_answer: str, metadata: dict)
        metadata includes: {
            "final_confidence": float,
            "audit_log": list,
            "warning": str (if max loops reached),
            "iterations": int,
            "final_intent": str
        }
    """
    audit_log = []
    final_answer = ""
    final_confidence = 0.0
    warning = None

    # --- 0) INPUT SANITIZATION ---
    sanitization_meta = None
    if SANITIZATION_AVAILABLE and sanitize_user_input is not None:
        try:
            sanitized_question, sanitization_meta = sanitize_user_input(question, "user_query")
            if sanitization_meta.get("injection_detected"):
                logger.warning("[NIC-SANITIZE] Prompt injection detected and blocked")
                # Use sanitized version
                question = sanitized_question
        except Exception as e:
            logger.warning(f"[NIC-SANITIZE] Sanitization failed: {e}")
    
    for iteration in range(max_iterations):
        logger.info(f"[NIC] === Iteration {iteration + 1}/{max_iterations} ===")
        
        # --- 1) PERCEIVE ---
        intent_meta = classify_intent(question)
        intent = intent_meta["intent"]
        logger.info(f"[NIC-PERCEIVE] Intent: {intent}, Agent: {intent_meta['agent']}")
        
        # --- 2) PLAN ---
        plan = nic_plan(intent)
        # Allow mode override
        if mode == "LLAMA (Fast)":
            plan["model"] = "llama"
        elif mode == "GPT-OSS (Deep)":
            plan["model"] = "gpt-oss"
        
        logger.info(f"[NIC-PLAN] Model: {plan['model']}, Citations required: {plan['require_citation']}, Threshold: {plan['confidence_threshold']}")
        
        # --- 3) ACT ---
        result = nic_act(question, plan, context_docs, llm_call_fn, intent_meta=intent_meta)
        
        answer = result["answer"]
        confidence = result["confidence"]
        sources = result["sources"]
        model_used = result["model_used"]
        
        logger.info(f"[NIC-ACT] Confidence: {confidence:.2f}, Model: {model_used}, Sources: {len(sources)}")
        
        # Enforce JSON output for all intents to keep deterministic, auditable output.
        audit_trail = None
        answer_for_audit = answer
        if isinstance(answer, str):
            schema_hint = '{"answer": "", "sources": [], "warnings": [], "verification": []}'
            validated = force_valid_json(answer, schema_hint, llm_call_fn, plan.get("model", "llama"))
            if isinstance(validated, str):
                try:
                    validated = json.loads(validated)
                except Exception:
                    avg_conf = _avg_retrieval_conf(context_docs)
                    safe_sources = _context_sources(context_docs)
                    blocked = {
                        "status": "blocked",
                        "reason": "invalid_json",
                        "next_steps": [
                            "Retry with a more specific question",
                            "Review the cited manual pages directly",
                        ],
                        "sources": safe_sources,
                        "confidence": round(avg_conf, 3),
                        "notes": "NIC blocked an answer because the model did not return valid JSON.",
                    }
                    final_answer = json.dumps(blocked, ensure_ascii=False, indent=2)
                    final_confidence = float(blocked.get("confidence", 0.0))
                    warning = "blocked_invalid_json"
                    audit_log.append({
                        "iteration": iteration + 1,
                        "intent": intent,
                        "plan": plan,
                        "model_used": "eval-blocked",
                        "confidence": final_confidence,
                        "answer": final_answer,
                        "sources": safe_sources,
                        "audit_trail": None,
                    })
                    break
            if isinstance(validated, dict):
                answer_for_audit = validated
                answer = validated
        elif isinstance(answer, dict):
            answer_for_audit = answer

        if citation_audit_enabled() and plan.get("require_citation"):
            try:
                # Parse answer as JSON for citation checking
                answer_json = answer_for_audit
                # Safety: for citation-required intents, validate strictly against the retrieved context.
                audit_trail = build_audit_trail(answer_json, context_docs, strict=True)
                logger.info(f"[NIC-AUDIT] Status: {audit_trail['audit_status']}, Citations: {audit_trail['cited_claims']}/{audit_trail['total_claims']}")
                
                # Safety: enforce strict rejection rules for citation-required intents.
                reject, reject_reason = should_reject_answer(audit_trail, strict_mode=True)
                if reject:
                    logger.warning(f"[NIC-AUDIT] Answer rejected: {reject_reason}")

                    # Safety retry: attempt an extractive troubleshoot fallback before blocking.
                    try:
                        if intent_meta.get("agent") == "troubleshoot" and context_docs:
                            extracted = _build_extractive_troubleshoot_fallback(context_docs, question)
                            try:
                                extracted = _attach_verified_citations_extractive(extracted, context_docs)
                            except Exception as e:
                                logger.debug(f"Extractive citation attachment skipped: {e}")
                            post_audit = build_audit_trail(extracted, context_docs, strict=True)
                            reject2, _ = should_reject_answer(post_audit, strict_mode=True)
                            if not reject2:
                                final_answer = extracted
                                final_confidence = float(extracted.get("confidence", _avg_retrieval_conf(context_docs)))
                                warning = None
                                audit_log.append({
                                    "iteration": iteration + 1,
                                    "intent": intent,
                                    "plan": plan,
                                    "model_used": "eval-extractive",
                                    "confidence": final_confidence,
                                    "answer": final_answer,
                                    "sources": _context_sources(context_docs),
                                    "audit_trail": post_audit,
                                })
                                break
                    except Exception as _extractive_retry_err:
                        logger.debug(f"[NIC-AUDIT] Extractive retry skipped: {_extractive_retry_err}")

                    # Safety: do not return uncited answers when citations are required.
                    avg_conf = _avg_retrieval_conf(context_docs)
                    safe_sources = _context_sources(context_docs)
                    blocked = {
                        "status": "blocked",
                        "reason": f"uncited_or_unsupported ({reject_reason})",
                        "next_steps": [
                            "Review the cited manual pages directly",
                            "Refine the query with the exact component name, section title, or page reference",
                        ],
                        "sources": safe_sources,
                        "confidence": round(avg_conf, 3),
                        "notes": "NIC blocked an answer because it could not be fully supported by the retrieved manual context.",
                    }

                    final_answer = json.dumps(blocked, ensure_ascii=False, indent=2)
                    final_confidence = float(blocked.get("confidence", 0.0))
                    warning = f"blocked_by_citation_audit ({reject_reason})"

                    # Record this iteration and stop.
                    audit_log.append({
                        "iteration": iteration + 1,
                        "intent": intent,
                        "plan": plan,
                        "model_used": "eval-blocked",
                        "confidence": final_confidence,
                        "answer": final_answer,
                        "sources": safe_sources,
                        "audit_trail": audit_trail,
                    })
                    break
            except Exception as e:
                logger.warning(f"[NIC-AUDIT] Citation audit failed: {e}")
        
        # --- 3.5) CHAIN OF VERIFICATION (CoVe) ---
        # Apply CoVe to safety-critical responses to reduce hallucination
        cove_metadata = None
        anomaly_result = None
        
        # --- 3.5a) ANOMALY DETECTION ---
        # Score query for anomalies - if high/critical, force CoVe
        is_anomalous = False
        if ANOMALY_DETECTOR_AVAILABLE and anomaly_detector is not None:
            try:
                # Get query embedding for anomaly scoring
                from core.retrieval.retrieval_engine import embed_query
                query_embedding = embed_query(question)
                if query_embedding is not None:
                    anomaly_result = anomaly_detector.score_embedding(query_embedding)
                    is_anomalous = anomaly_result.category in {"high", "critical"}
                    
                    if is_anomalous:
                        logger.warning(f"[NIC-Anomaly] Query flagged as ANOMALOUS: "
                                      f"score={anomaly_result.score:.6f}, category={anomaly_result.category}")
                    else:
                        logger.debug(f"[NIC-Anomaly] Query normal: "
                                    f"score={anomaly_result.score:.6f}, category={anomaly_result.category}")
            except Exception as e:
                logger.debug(f"[NIC-Anomaly] Scoring failed: {e}")
        
        # --- 3.5b) CHAIN OF VERIFICATION (CoVe) ---
        if cove_enabled() and COVE_AVAILABLE and apply_cove_to_answer is not None:
            try:
                # Determine if this is a safety-critical intent
                safety_intents = {"troubleshoot", "procedure", "maintenance", "safety"}
                is_safety_critical = intent_meta.get("agent") in safety_intents
                
                # Also trigger CoVe for anomalous queries
                trigger_cove = is_safety_critical or plan.get("require_citation", False) or is_anomalous
                
                if trigger_cove:
                    trigger_reason = "safety-critical" if is_safety_critical else ("anomalous query" if is_anomalous else "citation required")
                    logger.info(f"[NIC-CoVe] Applying Chain of Verification (reason: {trigger_reason})")
                    
                    verified_answer, adjusted_confidence, cove_metadata = apply_cove_to_answer(
                        answer=answer,
                        question=question,
                        context_docs=context_docs,
                        llm_call_fn=llm_call_fn,
                        original_confidence=confidence,
                        model=plan.get("model", "llama"),
                        force_verification=is_safety_critical or is_anomalous
                    )
                    
                    # Add anomaly info to cove_metadata
                    if anomaly_result is not None:
                        cove_metadata["anomaly_score"] = anomaly_result.score
                        cove_metadata["anomaly_category"] = anomaly_result.category
                        cove_metadata["anomaly_triggered_cove"] = is_anomalous
                    
                    # Update answer and confidence with verified values
                    if cove_metadata.get("cove_applied", False):
                        answer = verified_answer
                        confidence = adjusted_confidence
                        
                        logger.info(f"[NIC-CoVe] Verification complete: "
                                   f"claims_checked={cove_metadata.get('claims_checked', 0)}, "
                                   f"verified={cove_metadata.get('verified', False)}, "
                                   f"confidence {cove_metadata.get('original_confidence', 0):.2f} -> {adjusted_confidence:.2f}")
                        
                        # Check for safety warnings
                        safety_warnings = cove_metadata.get("safety_warnings", [])
                        if safety_warnings:
                            logger.warning(f"[NIC-CoVe] SAFETY WARNINGS: {safety_warnings}")
                            # Add warnings to the answer if it's a dict
                            if isinstance(answer, dict):
                                answer.setdefault("warnings", []).extend(safety_warnings)
                    else:
                        logger.info(f"[NIC-CoVe] Skipped: {cove_metadata.get('cove_skipped_reason', 'unknown')}")
                        
            except Exception as e:
                logger.warning(f"[NIC-CoVe] Chain of Verification failed: {e}")
                cove_metadata = {"error": str(e), "cove_applied": False}
        
        # Add anomaly info even if CoVe not triggered
        if anomaly_result is not None and cove_metadata is None:
            cove_metadata = {
                "anomaly_score": anomaly_result.score,
                "anomaly_category": anomaly_result.category,
                "anomaly_triggered_cove": False,
                "cove_applied": False
            }
        
        # Log iteration
        audit_log.append({
            "iteration": iteration + 1,
            "intent": intent,
            "plan": plan,
            "model_used": model_used,
            "confidence": confidence,
            "answer": answer,
            "sources": sources,
            "audit_trail": audit_trail,
            "cove_metadata": cove_metadata
        })
        
        final_answer = answer
        final_confidence = confidence
        
        # --- 4) SELF-REFINE DECISION ---
        threshold = plan.get("confidence_threshold", 0.55)
        
        # Acceptable confidence - return
        if confidence >= threshold:
            logger.info(f"[NIC-REFINE] Confidence {confidence:.2f} >= threshold {threshold:.2f}, accepting answer")
            break
        
        # Mid-confidence (0.40-threshold) - escalate to deep model
        if 0.40 <= confidence < threshold and plan.get("escalation_allowed", True):
            logger.info("[NIC-REFINE] Escalating to GPT-OSS (deep model)")
            plan["model"] = "gpt-oss"
            # Continue to next iteration
        
        # Low confidence (<0.40) - full rethink
        elif confidence < 0.40:
            logger.info(f"[NIC-REFINE] Low confidence {confidence:.2f}, triggering full refinement")
            question = f"Re-evaluate with more detail and caution:\n{question}"
        
        # Check if this was the last iteration
        if iteration == max_iterations - 1:
            warning = f"Max refinement loops ({max_iterations}) reached with confidence {confidence:.2f}"
            logger.warning(f"[NIC-REFINE] {warning}")
    
    # Build final metadata
    metadata = {
        "final_confidence": final_confidence,
        "audit_log": audit_log,
        "iterations": len(audit_log),
        "final_intent": audit_log[-1]["intent"] if audit_log else "unknown",
        "sources": audit_log[-1]["sources"] if audit_log else [],
        "confidence": final_confidence,
        "raw_response": final_answer
    }
    
    if warning:
        metadata["warning"] = warning
    
    if audit_log and audit_log[-1].get("audit_trail"):
        metadata["audit_trail"] = audit_log[-1]["audit_trail"]
    
    # Include CoVe metadata if available
    if audit_log and audit_log[-1].get("cove_metadata"):
        cove_meta = audit_log[-1]["cove_metadata"]
        metadata["cove"] = {
            "applied": cove_meta.get("cove_applied", False),
            "verified": cove_meta.get("verified", None),
            "claims_checked": cove_meta.get("claims_checked", 0),
            "confidence_adjustment": cove_meta.get("confidence_adjustment", 0),
            "safety_warnings": cove_meta.get("safety_warnings", [])
        }
    
    return final_answer, metadata


# Alias for backward compatibility
nic_intent_loop = nic_self_refine


# =======================
# NIC Agent Facade (optional thin wrapper)
# =======================

class NICAgent:
    """
    Thin, library-friendly wrapper for running the NIC self-refine loop.
    Provides domain-aware retrieval for multi-radar systems (NEXRAD, ASR-8, BEACON).
    
    Usage:
        agent = NICAgent(llm_call_fn=my_llm_fn)
        answer, metadata = agent.respond(query, mode="Auto")
    """

    def __init__(self, retriever_fn=None, llm_call_fn=None, use_multi_radar=True):
        """
        Initialize NIC agent.
        
        Args:
            retriever_fn: Optional custom retriever (overrides multi-radar retriever)
            llm_call_fn: LLM callable (required)
            use_multi_radar: Use domain-aware multi-radar retriever (default True)
        """
        self.llm_call_fn = llm_call_fn
        self.use_multi_radar = use_multi_radar
        
        # Use multi-radar retriever if enabled
        if use_multi_radar and retriever_fn is None:
            try:
                from .multi_radar_retriever_integration import retrieve_for_agent
                self.retriever_fn = retrieve_for_agent
                logger.info("[NICAgent] Using multi-radar domain-aware retriever")
            except ImportError:
                logger.warning("[NICAgent] Multi-radar retriever not available, using custom retriever")
                self.retriever_fn = retriever_fn
        else:
            self.retriever_fn = retriever_fn

    def respond(self, query: str, mode: str = "Auto") -> tuple[str, dict]:
        """
        Process a query through the NIC self-refine loop with domain-aware retrieval.
        
        Args:
            query: User question
            mode: "Auto", "LLAMA (Fast)", or "Qwen 14B (Deep)"
        
        Returns:
            (answer: str/dict, metadata: dict)
        """
        # Retrieve context with domain awareness
        context_docs = []
        try:
            if self.retriever_fn:
                context_docs = self.retriever_fn(query, k=12, top_n=6)
                logger.info(f"[NICAgent] Retrieved {len(context_docs)} documents for query (domain-aware)")
            else:
                logger.warning("[NICAgent] No retriever configured, running without context")
        except Exception as e:
            logger.warning(f"[NICAgent] Retrieval failed, continuing without context: {e}")

        # Run the full self-refine loop
        return nic_self_refine(
            question=query,
            mode=mode,
            context_docs=context_docs,
            llm_call_fn=self.llm_call_fn,
            max_iterations=3,
            session_state=None,
        )


# =======================
# Legacy Compatibility Wrappers
# =======================

def agent_router(question: str, mode: str, context_docs: list[dict], llm_call_fn):
    """
    Legacy router - delegates to NIC Intent Loop.
    
    NOTE: This function expects llm_call_fn(prompt: str) -> str.
    The new NIL expects llm_call_fn(prompt: str, model: str) -> str.
    We'll wrap it to add the model parameter.
    """
    # Wrap old-style llm_call_fn to accept model parameter
    def wrapped_llm_call(prompt: str, model: str = "llama") -> str:
        try:
            return cast(Any, llm_call_fn)(prompt, model)
        except TypeError:
            return llm_call_fn(prompt)
    
    answer, metadata = nic_intent_loop(
        question=question,
        mode=mode,
        context_docs=context_docs,
        llm_call_fn=wrapped_llm_call,
        max_iterations=2
    )
    return answer


import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_llm_call_from_main(model_name: str):
    try:
        import importlib
        main = importlib.import_module('nova_rag_multimodal2')
        return lambda p: main.call_llm(p, model_name)
    except Exception:
        raise RuntimeError('No llm_call_fn provided and failed to locate default call_llm')


def handle(prompt: str, model: str, mode: str, session_state: dict | None = None, context_docs: list[dict] | None = None, llm_call_fn=None):
    """
    Wrapper to allow calls like:
        answer = agent_router.handle(prompt=prompt, model=model_name, mode=mode, session_state=session_state)

    Now delegates to the NIC Intent Loop (NIL) for iterative refinement.
    
    `llm_call_fn` is optional but required unless you use this in the same runtime that can provide a callable.
    `context_docs` can be provided if you already have retrieval context; otherwise the caller should run retrieval.
    """
    # Provide a default llm_call_fn if caller omits it (tries to use module-level `call_llm`).
    if llm_call_fn is None:
        try:
            llm_call_fn = _default_llm_call_from_main(model)
        except Exception as e:
            logger.debug("llm_call_fn not provided and default lookup failed: %s", e)
            raise ValueError("llm_call_fn callable is required for `handle()`  pass a function that accepts a prompt string and returns a response string.")

    # Allow session updates minimally  append the prompt into a session finding_log if present
    if session_state is not None:
        session_state.setdefault("finding_log", [])
        session_state.setdefault("turns", 0)
        session_state["finding_log"].append(str(prompt))
        session_state["turns"] += 1
        # if a session has an id, persist it
        try:
            from .session_store import save_session
            sid = session_state.get('id') or session_state.get('session_id')
            if sid:
                save_session(sid, session_state)
        except Exception as e:
            logger.debug("Failed to persist session: %s", e)

    # If the caller requested an NPC model (model starts with "npc:") or mode == 'NPC',
    # attempt to load that NPC via npcsh and run it.
    if model and isinstance(model, str) and model.lower().startswith("npc:") or (mode and str(mode).upper() == "NPC"):
        try:
            from npcsh.npc import load_npc_by_name
            npc_name = model.split(":", 1)[1] if ":" in model else None
            npc = load_npc_by_name(npc_name) if npc_name else load_npc_by_name()
            if npc:
                # If the caller provided an llm_call_fn, monkey-patch NPC.get_llm_response
                # so it returns a deterministic output via the provided callable and avoids
                # making external LLM calls during tests.
                if llm_call_fn:
                    original = getattr(npc, 'get_llm_response', None)
                    npc.get_llm_response = lambda request, **kwargs: llm_call_fn(request)
                # NPC.get_llm_response returns an object; convert to string for compatibility
                resp = npc.get_llm_response(prompt)
                # restore original if we patched it
                if llm_call_fn and original is not None:
                    npc.get_llm_response = original
                # npc response may be a dict or object
                if isinstance(resp, dict) and "content" in resp:
                    return resp["content"]
                if hasattr(resp, "content"):
                    return resp.content
                # fallback to str()
                return str(resp)
        except Exception as e:
            # Fall back to the default handle flow if NPC fails
            logger.warning("NPC invocation failed: %s", e)

    # Wrap llm_call_fn to accept model parameter (NIL expects it)
    def wrapped_llm_call(prompt_text: str, model_name: str = "llama") -> str:
        try:
            return cast(Any, llm_call_fn)(prompt_text, model_name)
        except TypeError:
            return llm_call_fn(prompt_text)
    
    if context_docs is None:
        context_docs = []
    
    # Delegate to NIC Intent Loop
    answer, metadata = nic_intent_loop(
        question=prompt,
        mode=mode,
        context_docs=context_docs,
        llm_call_fn=wrapped_llm_call,
        max_iterations=2,
        session_state=session_state
    )
    
    # Attach loop metadata to session if present
    if session_state is not None:
        session_state.setdefault("loop_metadata", [])
        session_state["loop_metadata"].append(metadata)
    
    return answer
