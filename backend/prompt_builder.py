"""
Prompt building and model selection for NovaRAG.
Handles prompt templates, model selection logic, and error suggestions.
"""

from __future__ import annotations

import os


# =======================
# MODEL CONFIGURATION
# =======================

# Allow overriding LLAMA model via env to avoid GPU OOM with heavier builds
LLM_LLAMA = os.environ.get(
    "NOVA_LLM_LLAMA",
    "llama3.2:8b",
)
LLM_OSS = os.environ.get(
    "NOVA_LLM_OSS",
    "qwen2.5-coder:14b",
)

# Max output tokens per response (configurable via env)
MAX_TOKENS_LLAMA = int(os.environ.get("NOVA_MAX_TOKENS_LLAMA", "4096"))
MAX_TOKENS_OSS   = int(os.environ.get("NOVA_MAX_TOKENS_OSS", "512"))  # Balanced for speed + quality


def get_max_tokens(model_name: str) -> int:
    """Get max tokens for a given model."""
    return MAX_TOKENS_LLAMA if model_name == LLM_LLAMA else MAX_TOKENS_OSS


# =======================
# KEYWORDS FOR MODEL SELECTION
# =======================

DEEP_KEYWORDS = [
    "explain", "why", "root cause", "analysis", "analyze",
    "detailed", "theory", "concept", "in depth", "deep",
    "diagnosis", "reasoning"
]

FAST_KEYWORDS = [
    "steps", "procedure", "process", "checklist", "sequence",
    "how do i", "how to", "replace", "remove", "install",
    "test", "verify", "adjust", "reset", "configure", "runbook"
]


# =======================
# COMMON SUBSYSTEMS (for suggestions)
# =======================

COMMON_SUBSYSTEMS = [
    "engine", "transmission", "brakes", "steering", "suspension",
    "cooling", "electrical", "fuel", "exhaust", "drivetrain",
    "battery", "alternator", "starter", "ignition", "sensors",
    "HVAC", "power", "diagnostic", "maintenance"
]


# =======================
# PROMPT TEMPLATES
# =======================

def build_standard_prompt(query: str, context_docs: list[dict]) -> str:
    """Build standard prompt for one-shot queries."""
    context_text = "\n\n---\n\n".join(
        f"[Source: {d['source']}{f" (pg. {d['page']})" if 'page' in d else ''}]\n{d['text']}" for d in context_docs
    )

    return f"""
You are a precise and helpful vehicle maintenance AI assistant.
You help users troubleshoot and understand vehicle systems.

Always respond in clear professional English.

RULES:
- Use ONLY the manual context below as ground truth.
- If the manual does not contain an answer, say: "The provided manual does not specify this."
- Be structured, practical, and easy to understand.
- When citing sources, include page/paragraph references (e.g., "Para 6-3" or "Table 4-1")

Manuals Context:
-----------------
{context_text}

Question:
---------
{query}

Answer format:
- Short explanation (if needed)
- Then numbered steps (1…N)
- Cite sources by filename and page/paragraph number
"""


def build_session_prompt(user_update: str, context_docs: list[dict], session_state: dict | None = None) -> str:
    """Build prompt for multi-turn troubleshooting sessions."""
    if session_state is None:
        # Import lazily to avoid circular dependency
        from backend.session_manager import session_state as global_session_state
        session_state = global_session_state
    
    context_text = "\n\n---\n\n".join(
        f"[Source: {d['source']}{f" (pg. {d['page']})" if 'page' in d else ''}]\n{d['text']}" for d in context_docs
    )
    findings = "\n".join(f"- {f}" for f in session_state["finding_log"])

    return f"""
You are a vehicle maintenance troubleshooting assistant.
You are in the MIDDLE of an ongoing diagnostic session.

Session:
- Topic: {session_state['topic']}
- Findings so far:
{findings}

RULES:
- Continue the SAME session (do not restart from zero).
- Provide clear, practical guidance for the user.
- Use ONLY the manuals context below as ground truth.
- If manuals do not cover something, say so.
- Cite sources with page numbers when referencing manuals.

Manuals Context:
----------------
{context_text}

User update:
----------------------------
"{user_update}"

Do:
1) Interpret what the update implies
2) Refine likely root cause (confirm/eliminate)
3) Give the next 1–3 concrete steps
4) If resolved, how to confirm stability

Respond concise and numbered.
"""


# =======================
# MODEL SELECTION
# =======================

def choose_model(query_lower: str, mode: str, troubleshoot_triggers: list[str]) -> tuple[str, str]:
    """Returns (model_name, decision_reason)"""
    if mode == "LLAMA (Fast)":
        return LLM_LLAMA, "Manual: LLAMA (Fast)"
    if mode == "GPT-OSS (Deep)":
        return LLM_OSS, "Manual: GPT-OSS (Deep)"

    if any(k in query_lower for k in DEEP_KEYWORDS):
        return LLM_OSS, "Auto: deep keywords detected → GPT-OSS"
    if any(k in query_lower for k in FAST_KEYWORDS):
        return LLM_LLAMA, "Auto: procedure keywords detected → LLAMA"
    if any(t in query_lower for t in troubleshoot_triggers):
        return LLM_LLAMA, "Auto: troubleshooting keywords detected → LLAMA"

    return LLM_OSS, "Auto: fallback → GPT-OSS"


# =======================
# ERROR HANDLING & SUGGESTIONS
# =======================

def suggest_keywords(query: str) -> str:
    """Suggest related keywords when no results found."""
    query_lower = query.lower()
    
    mentioned = [s for s in COMMON_SUBSYSTEMS if s.lower() in query_lower]
    
    if mentioned:
        return f"Try being more specific about the issue with {', '.join(mentioned)}. Include alarm codes, symptoms, or component names."
    else:
        suggestions = ", ".join(COMMON_SUBSYSTEMS[:12])
        return f"No subsystem keywords detected. Try including: {suggestions}"
