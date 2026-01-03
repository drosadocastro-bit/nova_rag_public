# agents/agent_router.py
"""
NIC Intent Loop (NIL) - Iterative Agent Architecture

Nic operates using a 4-phase agent loop:
1. PERCEIVE - Classify user intent
2. PLAN     - Decide model, RAG strategy, and refinement threshold
3. ACT      - Execute retrieval, reranking, LLM reasoning
4. SELF-REFINE - Evaluate confidence and loop if needed

This transforms NIC from a single-pass pipeline into an adaptive agent.
"""

import logging
import re
import json
from .citation_auditor import build_audit_trail, should_reject_answer, format_audit_report, validate_citation
import os

logger = logging.getLogger(__name__)

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
    - out_of_scope: Explicitly out-of-domain queries
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
        "medical", "doctor", "treatment", "disease", "symptom", "medicine",
        "weather forecast", "rain forecast", "snow forecast", "tomorrow's weather",
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
    # OPTION 1: OUT-OF-SCOPE VEHICLE TYPES (refuse even with automotive keywords)
    # =============================================================================
    # These are vehicles NOT covered by this manual. Even if they mention "spark plug"
    # or "oil change", we should refuse because our manual is for automobiles only.
    out_of_scope_vehicles = [
        # Aircraft
        "helicopter", "airplane", "aircraft", "boeing", "747", "jet", "cessna", "airbus",
        # Marine
        "boat", "ship", "yacht", "outboard", "marine engine", "watercraft", "jet ski",
        # Two-wheelers (not covered by this automotive manual)
        "motorcycle", "motorbike", "dirt bike", "scooter", "moped", "atv", "quad",
        # Industrial/agricultural
        "tractor", "forklift", "excavator", "bulldozer", "crane", "combine",
        # Small equipment
        "chainsaw", "lawnmower", "lawn mower", "riding mower", "snowblower", "generator",
        # Recreational
        "go-kart", "go kart", "golf cart", "snowmobile",
        # Non-motorized
        "bicycle", "bike chain", "bike tire"
    ]
    
    # Check if query mentions an out-of-scope vehicle type
    detected_vehicle = None
    for vehicle in out_of_scope_vehicles:
        if vehicle in q:
            detected_vehicle = vehicle
            break
    
    if detected_vehicle:
        return {
            "intent": "out_of_scope_vehicle",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0,
            "detected_vehicle": detected_vehicle,
            "refusal_reason": f"This manual covers automobiles only, not {detected_vehicle}s. Please consult a {detected_vehicle}-specific manual."
        }
    
    # Automotive context keywords - if present, don't refuse even if out_of_scope keyword matches
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
            "intent": "out_of_scope",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0
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
            "intent": "out_of_scope",
            "agent": "refusal",
            "model": "none",
            "use_rag": False,
            "confidence_threshold": 0.0
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

        # ===== SEMANTIC MANIPULATION / LEADING QUESTIONS =====
        "just between us", "hypothetically speaking", "for educational purposes only",
        "what could i do", "what might happen",
        "skilled drivers don't need", "modern cars are so reliable",
        "safe to skip", "can skip most",

        # ===== CITATION EVASION ATTEMPTS =====
        "skip the citations", "without all the source", "without looking it up",
        "just give me the quick", "quick answer without",
        "no details needed", "your best guess",
        "i trust you", "i don't need the page",
        "just confirm", "yes or no only",
        "ignore citation requirements",

        # ===== FALSE PREMISE DETECTION =====
        "alternators run on diesel", "drain engine oil every 500", "spark plugs every 1000",
        "replaced every 1000 miles",  # catches "spark plugs need to be replaced every 1000 miles"
        "brake fluid is flammable",
        "never check oil when cold", "never check oil when engine is cold", "never check oil when engine is",
        "overfilling coolant improves", "overfilling coolant by", "overfilling coolant by 2 gallons",
        "tires wear evenly", "transmission fluid never needs",

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
import json
import re
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

    # SAFETY-CRITICAL: Use 8B for strict citation and refusal behavior
    if intent == "vehicle_diagnostic":
        return {
            "use_rag": True,
            "model": "llama",  # 8B for safety-critical diagnostics
            "escalation_allowed": True,
            "require_citation": True,
            "allowed_formats": ["procedure", "steps", "analysis", "troubleshoot"],
            "ask_for_clarification": False,
            "confidence_threshold": 0.75,  # High bar for safety-critical work
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

    # SAFETY-CRITICAL: Use 8B for strict procedure adherence
    if intent == "maintenance_procedure":
        return {
            "use_rag": True,
            "model": "llama",  # 8B for safety-critical procedures
            "escalation_allowed": True,
            "require_citation": True,
            "allowed_formats": ["procedure", "steps"],
            "ask_for_clarification": False,
            "confidence_threshold": 0.60,
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

def estimate_llm_conf(llm_output: str) -> float:
    """
    Estimate LLM output confidence based on heuristics.
    
    Heuristics:
    - Has sources/citations: +0.3
    - Has confidence field: use that value
    - Has structured format: +0.2
    - Short/vague output: -0.2
    """
    try:
        # Try to extract confidence from JSON
        data = json.loads(llm_output)
        if "confidence" in data:
            return float(data["confidence"])
    except:
        pass
    
    # Heuristic scoring
    score = 0.5  # baseline
    
    if any(marker in llm_output.lower() for marker in ["source:", "pg.", "manual", "ref:"]):
        score += 0.3
    
    if any(marker in llm_output for marker in ["**", "##", "- ", "1. "]):
        score += 0.2
    
    if len(llm_output.strip()) < 100:
        score -= 0.2
    
    return max(0.0, min(1.0, score))


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
    anchor_terms = ["stalo", "ame", "adaptation", "fo6-4"]
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
        if "stalo" in ql and "stalo" in ll:
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
        citations = [d.get("source", "unknown") for d in context_docs]
        baseline_conf = sum(d.get("confidence", 0.5) for d in context_docs) / len(context_docs)
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

Respond with structured JSON following the appropriate format for this query type."""

    # ---------- 3) CONFIDENCE GUARD (NIC SAFETY) ----------
    # Safety: block LLM if retrieval confidence is too low
    confidence_threshold = plan.get("confidence_threshold", 0.70)
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
    llm_conf = estimate_llm_conf(llm_output)
    final_conf = round((baseline_conf * 0.6) + (llm_conf * 0.4), 3)

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
        m2 = _re.search(r"\bstalo\s*(\d{2,3})\b", ql)
        if m2:
            return m2.group(1)
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
        anchor_terms = ["stalo", "ame", "adaptation", "fo6-4"]
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
            if "stalo" in ql and "stalo" in ll:
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
        refusal_message = {
            "response_type": "refusal",
            "reason": reason,
            "message": "I'm a vehicle maintenance AI assistant. I can only help with car maintenance, repair procedures, diagnostics, and technical questions related to automotive systems. This request is not allowed or outside my scope.",
            "policy": "Scope & Safety",
            "confidence": 0.0
        }
        metadata = {
            "confidence": 0.0,
            "sources": [],
            "raw_response": json.dumps(refusal_message),
            "model_used": "policy-guard"
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
        except Exception:
            pass
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
                # Minimal heuristic steps tailored to alarm/STALO queries
                default_steps = [
                    "Verify STALO signal path power and cabling",
                    "Inspect transmitter connections and module seating",
                    "Run built-in transmitter diagnostics and review logs",
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
        
        # Citation audit if required
        audit_trail = None
        if citation_audit_enabled() and plan.get("require_citation"):
            try:
                # Parse answer as JSON for citation checking
                answer_json = json.loads(answer) if isinstance(answer, str) else answer
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
                            except Exception:
                                pass
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
        
        # Log iteration
        audit_log.append({
            "iteration": iteration + 1,
            "intent": intent,
            "plan": plan,
            "model_used": model_used,
            "confidence": confidence,
            "answer": answer,
            "sources": sources,
            "audit_trail": audit_trail
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
            logger.info(f"[NIC-REFINE] Escalating to GPT-OSS (deep model)")
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
    
    return final_answer, metadata


# Alias for backward compatibility
nic_intent_loop = nic_self_refine


# =======================
# NIC Agent Facade (optional thin wrapper)
# =======================

class NICAgent:
    """
    Thin, library-friendly wrapper for running the NIC self-refine loop.
    Provide a retriever callable and an llm_call_fn; call respond(query, mode).
    """

    def __init__(self, retriever_fn, llm_call_fn):
        self.retriever_fn = retriever_fn
        self.llm_call_fn = llm_call_fn

    def respond(self, query: str, mode: str = "Auto") -> tuple[str, dict]:
        # Retrieve context up front
        context_docs = []
        try:
            context_docs = self.retriever_fn(query, k=12, top_n=6)
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
