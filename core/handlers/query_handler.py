"""
Framework-agnostic core query handler.

This module provides the business logic for processing user queries without
any dependency on Flask, FastAPI, or other web frameworks.

Design Principles:
- Accepts dict input (request_data), returns dict output (response_data)
- Uses NICAppState for all mutable state access
- Dependency injection pattern for testability (app_state parameter)
- No framework-specific imports (no request, session, etc.)
- Identical logic path for Flask, FastAPI, or CLI callers

Stage 3 Goal: Separate business logic from web framework adapter code.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, Callable
from pathlib import Path

import os
import re

from agents import agent_router
from core.safety import handle_injection_and_multi_query
from core.safety.output_sanitizer import sanitize_output  # LLM02 defense: post-generation sanitization
from core.signal_path_engine_legacy import SignalPathEngine, run_signal_path_diagnosis
from core.utils.search_history import SearchHistory
from response_normalizer import normalize_response

from core.app_state import get_app_state, NICAppState
from core.routing.function_gemma_router import gemma_quick_classify  # Stage 4: Fast pre-filter
from core.retrieval.retrieval_engine import (
    SEARCH_HISTORY_PATH,
    FAVORITES_PATH,
    retrieve,
    detect_error_code,
    boost_error_docs,
)
from core.generation.llm_gateway import (
    LLM_LLAMA,
    LLM_OSS,
    TROUBLESHOOT_TRIGGERS,
    resolve_model_name,
    choose_model,
    call_llm,
)
from core.session.session_manager import (
    session_state,
    END_SESSION_TRIGGERS,
    reset_session,
    start_new_session,
    resume_session,
)


# Module-level search history (shared across all requests)
search_history = SearchHistory(
    max_size=50,
    history_path=SEARCH_HISTORY_PATH,
    favorites_path=FAVORITES_PATH,
)


COMMON_SUBSYSTEMS = [
    "engine",
    "transmission",
    "brakes",
    "steering",
    "suspension",
    "cooling",
    "electrical",
    "fuel",
    "exhaust",
    "drivetrain",
    "battery",
    "alternator",
    "starter",
]

CONFIDENCE_THRESHOLD = float(os.environ.get("NOVA_CONFIDENCE_THRESHOLD", "0.75"))
SIGNAL_PATH_ENGINE_ENABLED = os.environ.get("NOVA_ENABLE_SIGNAL_PATH_ENGINE", "0") == "1"
SIGNAL_PATH_MODE_ALIASES = {"signal-path", "signal_path", "diagnostic-plan", "diagnostic_plan"}


def suggest_keywords(query: str) -> str:
    """Generate keyword suggestions for vague queries."""
    q_lower = query.lower()
    mentioned = [s for s in COMMON_SUBSYSTEMS if s.lower() in q_lower]
    if mentioned:
        return (
            "Try being more specific about the issue with "
            f"{', '.join(mentioned)}. Include alarm codes, symptoms, or component names."
        )
    suggestions = ", ".join(COMMON_SUBSYSTEMS[:12])
    return f"No subsystem keywords detected. Try including: {suggestions}"


def build_standard_prompt(question: str, context_docs: list) -> str:
    """Build standard RAG prompt from question and context docs."""
    from backend import build_standard_prompt as _backend_prompt
    return _backend_prompt(question, context_docs)


def build_session_prompt(question: str, context_docs: list) -> str:
    """Build session-aware prompt for multi-turn troubleshooting."""
    from backend import build_session_prompt as _backend_prompt
    return _backend_prompt(question, context_docs)


def build_conversation_context() -> str:
    """Build conversation context from session state."""
    from backend import build_conversation_context as _backend_context
    return _backend_context()


def _sanitize_answer(answer: str) -> str:
    """
    Apply post-generation output sanitization to LLM answers.
    
    This is a deterministic defense against LLM02 (Insecure Output Handling).
    The LLM cannot be trusted to self-sanitize, so this layer MUST be applied.
    """
    if not isinstance(answer, str):
        return answer  # Return non-strings as-is (e.g., dicts for structured responses)
    
    sanitized, meta = sanitize_output(answer, allow_markdown=True)
    if meta.get("blocked_count", 0) > 0:
        print(f"[SECURITY] Output sanitizer blocked {meta['blocked_count']} dangerous patterns: {meta['blocked_types']}")
    return sanitized


def _should_force_procedure_extractive(intent_meta: Optional[Dict[str, Any]]) -> bool:
    # Disabled: the post-generation quality gate now provides grounding-based
    # oversight for procedural answers.  The gate uses a higher threshold
    # (0.70) for procedural/safety intents, which is more precise than
    # blanket extractive forcing.
    return False


def _build_extractive_response(context_docs: list[dict]) -> Dict[str, Any]:
    lines = []
    sources = []
    for doc in (context_docs or [])[:4]:
        text = (doc.get("text") or doc.get("snippet") or "").strip()
        if not text:
            continue
        # Use up to 500 chars per chunk so we capture enough context for
        # must_contain terms that may appear deeper in the chunk.
        snippet = text.replace("\n", " ")[:500].strip()
        source = doc.get("source") or doc.get("filename") or "unknown"
        page = doc.get("page") if doc.get("page") is not None else doc.get("page_num")
        doc_id = doc.get("id") or ""
        lines.append(f"[source={source} page={page} id={doc_id}] {snippet}")
        sources.append({"source": source, "page": page})
    message = "\n".join(lines) if lines else "No extractive evidence available."
    return {
        "response_type": "extractive_fallback",
        "message": message,
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Post-generation quality gate (grounding + confidence + category)
# ---------------------------------------------------------------------------
_GROUNDING_THRESHOLD = float(os.environ.get("NOVA_GROUNDING_THRESHOLD", "0.60"))
_ABSTAIN_CONFIDENCE = float(os.environ.get("NOVA_ABSTAIN_CONFIDENCE", "0.35"))

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "then", "for", "to", "of",
    "in", "on", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "this", "that", "it", "its", "at", "not", "no", "so", "do", "does", "did",
})


def _tokenize_for_grounding(text: str) -> set[str]:
    """Extract meaningful tokens, stripping stopwords and short noise."""
    return {
        t for t in re.findall(r"[a-zA-Z0-9%.\-\xb1/]+", text.lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def _statement_is_grounded(
    stmt: str, context_texts: list[str], overlap_min: float = 0.50
) -> bool:
    """True when *stmt* has enough token overlap with any single context chunk."""
    tokens = _tokenize_for_grounding(stmt)
    if not tokens:
        return True  # vacuously grounded
    for ctx in context_texts:
        ctx_tokens = _tokenize_for_grounding(ctx)
        if len(tokens & ctx_tokens) / len(tokens) >= overlap_min:
            return True
    return False


def _compute_grounding_ratio(answer_text: str, context_docs: list[dict]) -> float:
    """
    Fraction of non-trivial answer statements grounded in retrieved chunks.
    
    A statement is any sentence-like segment > 10 chars after splitting on
    periods, semicolons, and newlines.
    """
    if not answer_text or not context_docs:
        return 0.0

    statements = [
        s.strip()
        for s in re.split(r"[;\n.]+", answer_text)
        if s.strip() and len(s.strip()) > 10
    ]
    if not statements:
        return 0.0

    context_texts = [
        (doc.get("text") or doc.get("snippet") or "").strip()
        for doc in context_docs
        if (doc.get("text") or doc.get("snippet") or "").strip()
    ]
    if not context_texts:
        return 0.0

    grounded = sum(1 for s in statements if _statement_is_grounded(s, context_texts))
    return grounded / len(statements)


def _post_generation_quality_gate(
    answer_text: str,
    context_docs: list[dict],
    avg_confidence: float,
    intent_meta: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Post-generation quality gate.  Returns an override response dict when
    the LLM answer fails quality checks, or None if the answer is acceptable.

    Three complementary mechanisms:
      1. **Grounding-based gating** – if fewer than *threshold* of answer
         statements are grounded in retrieved chunks, force extractive.
      2. **Confidence-based abstention** – if retrieval confidence is below
         *_ABSTAIN_CONFIDENCE* AND grounding is poor, refuse outright.
      3. **Category-aware strictness** – procedural / safety-critical intents
         raise the grounding threshold so the bar is higher.
    """

    grounding_ratio = _compute_grounding_ratio(answer_text, context_docs)

    # --- Category-aware: raise bar for safety-critical intents ---------------
    intent = ""
    if isinstance(intent_meta, dict):
        intent = intent_meta.get("intent", "")

    effective_threshold = _GROUNDING_THRESHOLD
    if intent in (
        "maintenance_procedure", "troubleshooting",
        "safety_critical", "life_safety",
    ):
        # Safety-critical / procedural intents need 80%+ grounding.
        # This replaces the old blanket extractive forcing with a more
        # precise check: the LLM answer is allowed only when ≥80% of its
        # statements are grounded in retrieved evidence.
        effective_threshold = max(effective_threshold, 0.80)

    print(
        f"[QUALITY-GATE] grounding={grounding_ratio:.2%}, "
        f"confidence={avg_confidence:.2%}, intent={intent}, "
        f"threshold={effective_threshold:.2%}"
    )

    # 1. Confidence-based abstention (harshest)
    if avg_confidence < _ABSTAIN_CONFIDENCE and grounding_ratio < effective_threshold:
        print(
            f"[QUALITY-GATE] ABSTAIN: confidence={avg_confidence:.2%} "
            f"+ grounding={grounding_ratio:.2%}"
        )
        return {
            "answer": {
                "response_type": "refusal",
                "reason": "insufficient_evidence",
                "policy": "Grounding & Confidence Gate",
                "message": (
                    "The retrieved evidence is insufficient to answer this "
                    "question reliably. Please refine your query or consult "
                    "the official manual directly."
                ),
            },
            "grounding_ratio": grounding_ratio,
            "gate_action": "abstain",
        }

    # 2. Grounding-based gating (force extractive)
    if grounding_ratio < effective_threshold:
        print(
            f"[QUALITY-GATE] EXTRACTIVE: grounding={grounding_ratio:.2%} "
            f"< threshold={effective_threshold:.2%}"
        )
        extractive = _build_extractive_response(context_docs)
        return {
            "answer": extractive,
            "grounding_ratio": grounding_ratio,
            "gate_action": "extractive_override",
        }

    # Answer passes quality gate
    return None


def _maybe_signal_path_plan(
    question: str,
    mode: Optional[str],
    context_docs: list,
) -> Optional[Dict[str, Any]]:
    mode_lower = (mode or "").strip().lower()
    if not SIGNAL_PATH_ENGINE_ENABLED and mode_lower not in SIGNAL_PATH_MODE_ALIASES:
        return None

    # Run the signal path diagnosis engine
    # Detection of domain is handled internally by the engine
    result = run_signal_path_diagnosis(
        domain="unknown",  # Engine will try to infer from context
        alarm_or_symptom=question,
        context_docs=context_docs,
    )

    if result.get("response_type") == "diagnostic_plan":
        # Format plan steps into readable text
        steps = result.get("steps", [])
        plan_text = f"Diagnostic Plan ({len(steps)} steps):\n\n"
        
        for step in steps:
            plan_text += f"Step {step.get('step')}: {step.get('action')}\n"
            if step.get('measure'):
                plan_text += f"  Measure: {step.get('measure')}\n"
            if step.get('expected'):
                plan_text += f"  Expected: {step.get('expected')}\n"
            if step.get('if_present'):
                plan_text += f"  If present: {step.get('if_present')}\n"
            if step.get('if_absent'):
                plan_text += f"  If absent: {step.get('if_absent')}\n"
            if step.get('refs'):
                plan_text += f"  References: {', '.join(step.get('refs', []))}\n"
            plan_text += "\n"
        
        response = {
            "answer": _sanitize_answer(plan_text),
            "decision_tag": f"signal-path | {result.get('domain', 'unknown')} | {result.get('graph_id', '')}".strip(),
            "status": "success",
        }
        
        # Phase 4: Include diagnostic confidence and confirmation strategy
        if "diagnostic_confidence" in result:
            response["diagnostic_confidence"] = result["diagnostic_confidence"]
        if "confirmation_strategy" in result:
            response["confirmation_strategy"] = result["confirmation_strategy"]
        if "required_nodes" in result:
            response["required_nodes"] = result["required_nodes"]
        
        return response

    # Fallback or refusal
    response = {
        "answer": _sanitize_answer(result.get("message", "Diagnostic plan unavailable.")),
        "decision_tag": f"signal-path | {result.get('response_type', 'unknown')} | {result.get('reason', '')}".strip(),
        "status": "refusal",
    }
    
    # Phase 4: Include confidence metrics even on refusal (for debugging)
    if "diagnostic_confidence" in result:
        response["diagnostic_confidence"] = result["diagnostic_confidence"]
    if "confirmation_strategy" in result:
        response["confirmation_strategy"] = result["confirmation_strategy"]
    
    return response




def nova_query_core(
    question: str,
    mode: str,
    npc_name: Optional[str] = None,
    resume_session_id: Optional[str] = None,
    fallback_mode: Optional[str] = None,
    app_state: Optional[NICAppState] = None,
) -> Dict[str, Any]:
    """
    Framework-agnostic core query handler.
    
    This is the single source of truth for all query processing logic.
    Can be called from Flask, FastAPI, CLI, or unit tests.
    
    Args:
        question: User's question text
        mode: Operation mode (Auto, Fast, Deep, NPC, etc.)
        npc_name: NPC character name for roleplay mode
        resume_session_id: Session ID to resume
        fallback_mode: Fallback mode if primary fails
        app_state: Application state (injected for testing, uses singleton if None)
    
    Returns:
        Dict with keys:
            - answer: str | dict (response text or structured refusal)
            - decision_tag: str (model + routing decision metadata)
            - confidence: Optional[float] (retrieval confidence)
            - session_id: Optional[str] (troubleshooting session ID)
            - status: str (success, error, refusal, etc.)
    """
    # Stage 1-3: Use centralized application state with dependency injection
    if app_state is None:
        app_state = get_app_state()
    
    # Ensure index is loaded before any retrieval
    app_state.ensure_initialized()
    if app_state.index_error:
        return {
            "answer": f"[ERROR] Index initialization failed: {app_state.index_error}",
            "decision_tag": "index-load-failed",
            "status": "error",
        }
    
    # Input validation
    if not question or not question.strip():
        return {
            "answer": "No question entered.",
            "decision_tag": "",
            "status": "error",
        }
    
    q_raw = question.strip()
    
    # Debug logging (framework-agnostic)
    try:
        safe_preview = q_raw[:80]
        safe_preview = re.sub(r"[^\x20-\x7E]", "?", safe_preview)
    except Exception:
        safe_preview = "(preview unavailable)"
    print(f"[DEBUG] nova_query_core called with mode={mode}, question={safe_preview}")
    
    # Stage 4: Optional fast pre-filter (Gemma classification for acceleration hints)
    # Note: This is for acceleration only, NOT authoritative. Safety checks below are the authority.
    gemma_classification = None
    if os.environ.get("NOVA_ENABLE_GEMMA_PREFILTER", "1") == "1":
        try:
            gemma_classification = gemma_quick_classify(q_raw, timeout_sec=2.0)
            if gemma_classification.get("success"):
                print(
                    f"[GEMMA] Pre-filter: {gemma_classification['estimated_type']} "
                    f"(confidence={gemma_classification['query_confidence']:.0%}, "
                    f"time={gemma_classification['gemma_time_ms']:.0f}ms)"
                )
            else:
                print(f"[GEMMA] Pre-filter skipped: {gemma_classification.get('error')}")
        except Exception as e:
            print(f"[GEMMA] Pre-filter error: {e}")
    
    # Reset session decision tag
    session_state["last_decision_tag"] = None
    session_state["last_audit_status"] = None
    
    # Safety: injection detection + multi-query handling (AUTHORITATIVE LAYER)
    # NOTE: Gemma hints above are for acceleration only. Safety checks are the real decision makers.
    injection_result = handle_injection_and_multi_query(q_raw)
    session_state["last_heuristic_triggers"] = injection_result.get("heuristic_triggers", [])
    session_state["last_heuristic_trigger"] = (
        injection_result.get("heuristic_trigger") or (session_state.get("last_heuristic_triggers") or [None])[-1]
    )
    session_state["last_decision_tag"] = injection_result.get("decision_tag")
    
    if injection_result["refusal"]:
        return {
            "answer": injection_result["refusal"],
            "decision_tag": injection_result.get("decision_tag", ""),
            "status": "refusal",
        }
    
    q_raw = injection_result["cleaned_question"]
    q_lower = injection_result.get("q_lower", q_raw.lower())
    multi_query_warning = injection_result.get("multi_query_warning")
    
    # Agent routing: check for out-of-scope or unsafe intents
    intent_meta = None
    try:
        intent_meta = agent_router.classify_intent(q_raw)
        if isinstance(intent_meta, dict) and intent_meta.get("agent") == "refusal":
            intent = (intent_meta.get("intent") or "refusal").strip()
            if intent == "unsupported_domain":
                message = intent_meta.get(
                    "refusal_reason",
                    "This domain is not supported. Supported domains include automotive, military_vehicle, aerospace, nuclear, radar, and medical."
                )
                reason = "unsupported_domain"
            elif intent == "experimental_domain":
                message = intent_meta.get(
                    "refusal_reason",
                    "This domain is experimental and requires strong, domain-specific evidence."
                )
                reason = "experimental_domain"
            elif intent == "insufficient_corpus":
                message = intent_meta.get(
                    "refusal_reason",
                    "There is insufficient corpus evidence to answer safely."
                )
                reason = "insufficient_corpus"
            elif intent == "unsafe_intent":
                reason = "unsafe_intent"
                message = (
                    "I can't help with that request because it appears to be unsafe or attempts to bypass safety guidance. "
                    "Please ask a safe, manufacturer-recommended maintenance or diagnostic question."
                )
            else:
                reason = "unsupported_domain"
                message = (
                    "This question is outside supported domains. "
                    "Please ask about automotive, military_vehicle, aerospace, nuclear, radar, or medical topics."
                )
            session_state["last_decision_tag"] = reason
            refusal = {
                "response_type": "refusal",
                "reason": reason,
                "policy": "Scope & Safety",
                "message": message,
                "question": q_raw,
            }
            return {
                "answer": refusal,
                "decision_tag": f"refusal | {reason}",
                "status": "refusal",
            }
    except Exception:
        pass
    
    # Fast eval / retrieval-only mode
    force_retrieval_only = isinstance(fallback_mode, str) and (fallback_mode.lower() == "retrieval-only")
    if force_retrieval_only or (mode or "").lower() in {"eval", "retrieval", "retrieval-only", "fast eval"} or os.environ.get("NOVA_EVAL_FAST", "0") == "1":
        print(f"[DEBUG] Fast eval mode activated for: {q_raw[:80]}")
        context_docs = retrieve(q_raw, k=12, top_n=6)
        print(f"[DEBUG] Retrieved {len(context_docs)} docs")
        
        if not context_docs:
            return {
                "answer": "[ERROR] No context retrieved.",
                "decision_tag": "retrieval-only | no-context",
                "status": "error",
            }
        
        avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
        error_meta = detect_error_code(q_raw)
        error_id = error_meta.get("error_id") if error_meta else None
        top = context_docs[0] if context_docs else {}
        snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
        src = f"{top.get('source','')} p{top.get('page','')}".strip()
        
        pieces = []
        if error_id:
            pieces.append(f"Alarm {error_id} summary:")
        if snippet:
            pieces.append(snippet[:280])
        if src:
            pieces.append(f"Source: {src}")
        
        answer = "\n".join(pieces) if pieces else "No context available."
        print(f"[DEBUG] Fast eval returning answer (len={len(answer)})")
        suffix = "forced" if force_retrieval_only else "retrieval-only"
        
        return {
            "answer": answer,
            "decision_tag": f"{suffix} | Confidence: {avg_confidence:.2%}",
            "confidence": avg_confidence,
            "status": "success",
        }
    
    # Add to search history
    search_history.add(q_raw)
    
    # Session management: resume existing session
    if resume_session_id:
        if resume_session(resume_session_id):
            return {
                "answer": f"✓ Resumed session: {session_state['topic'][:80]}...\nTurns so far: {session_state['turns']}",
                "decision_tag": "session-resumed",
                "session_id": resume_session_id,
                "status": "success",
            }
        else:
            return {
                "answer": "[ERROR] Could not load that session.",
                "decision_tag": "session-load-failed",
                "status": "error",
            }
    
    # Session management: end current session
    if any(trigger in q_lower for trigger in END_SESSION_TRIGGERS):
        reset_session(save_to_db=True)
        return {
            "answer": "✓ Troubleshooting session saved & reset. New case whenever you're ready.",
            "decision_tag": "session-reset",
            "status": "success",
        }
    
    # Model selection
    if mode and "NPC" in mode.upper():
        model_name = f"npc:{(npc_name or 'sibiji')}"
        decision = f"NPC: {(npc_name or 'sibiji')}"
    else:
        model_name, decision = choose_model(q_lower, mode)
        if mode and ("LLAMA" in mode.upper() or "GPT" in mode.upper()):
            print(f"[NIC-SAFETY] Mode override '{mode}' bypasses safety routing for query: {q_raw[:50]}...")
    
    last_resolved_model: Optional[str] = None
    
    def llm_dispatch(prompt_text: str, requested_model: Optional[str] = None, **kwargs) -> str:
        """Internal LLM dispatcher with model resolution."""
        nonlocal last_resolved_model
        target_model = model_name
        if isinstance(requested_model, str) and requested_model:
            alias = requested_model.strip().lower()
            if alias in {"llama", "fast"}:
                target_model = LLM_LLAMA
            elif alias in {"gpt-oss", "gpt_oss", "oss", "deep"}:
                target_model = LLM_OSS
            else:
                target_model = requested_model
        
        try:
            last_resolved_model = resolve_model_name(target_model)
        except Exception:
            last_resolved_model = target_model
        
        return call_llm(prompt_text, last_resolved_model)
    
    # Path 1: Start new troubleshooting session
    if (not session_state["active"]) and any(t in q_lower for t in TROUBLESHOOT_TRIGGERS):
        session_id = start_new_session(q_raw, model_name, mode)
        
        context_docs = retrieve(q_raw, k=12, top_n=6)
        context_docs = boost_error_docs(q_raw, context_docs)
        
        if not context_docs:
            reset_session(save_to_db=False)
            suggestion = suggest_keywords(q_raw)
            return {
                "answer": f"[ERROR] I couldn't retrieve relevant manual context for that question.\n\nSuggestion: {suggestion}",
                "decision_tag": f"{model_name} | {decision}",
                "status": "error",
            }
        
        avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
        
        # Confidence gate: block low-confidence queries
        ambiguous_terms = ["my vehicle", "my car", "the engine", "my engine", "this vehicle", "generic", "any vehicle"]
        if avg_confidence < 0.65 and any(term in q_lower for term in ambiguous_terms):
            print(f"[CONFIDENCE-GATE] Low confidence ({avg_confidence:.2%}) + ambiguous vehicle term detected")
        
        if avg_confidence < CONFIDENCE_THRESHOLD:
            print(
                f"[BLOCKER] Retrieval confidence {avg_confidence:.2%} < {CONFIDENCE_THRESHOLD:.0%} "
                "→ skipping LLM, returning Fast Eval"
            )
            top = context_docs[0] if context_docs else {}
            snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
            src = f"{top.get('source','')} p{top.get('page','')}".strip()
            pieces = [snippet[:280]] if snippet else []
            if src:
                pieces.append(f"Source: {src}")
            answer = "\n".join(pieces) if pieces else "✓ Retrieved context too weak for confident answer."
            reset_session(save_to_db=False)
            return {
                "answer": answer,
                "decision_tag": (
                    f"eval-blocked | Confidence: {avg_confidence:.2%} "
                    f"(blocker: {CONFIDENCE_THRESHOLD:.0%})"
                ),
                "confidence": avg_confidence,
                "status": "blocked",
            }

        signal_path_response = _maybe_signal_path_plan(q_raw, mode, context_docs)
        if signal_path_response:
            return signal_path_response
        
        # Generate answer via agent router
        prompt = build_standard_prompt(q_raw, context_docs)
        answer = agent_router.handle(
            prompt=prompt,
            model=model_name,
            mode=mode,
            session_state=session_state,
            context_docs=context_docs,
            llm_call_fn=llm_dispatch,
        )
        
        # LLM02 Defense: Post-generation output sanitization (deterministic)
        answer = _sanitize_answer(answer)

        # --- Post-generation quality gate (Path 1) ---------------------------
        gate_override = _post_generation_quality_gate(
            answer_text=answer if isinstance(answer, str) else "",
            context_docs=context_docs,
            avg_confidence=avg_confidence,
            intent_meta=intent_meta,
        )
        if gate_override is not None:
            gate_action = gate_override.get("gate_action", "unknown")
            grounding_r = gate_override.get("grounding_ratio", 0.0)
            used = last_resolved_model or model_name
            reset_session(save_to_db=False)
            return {
                "answer": gate_override["answer"],
                "decision_tag": (
                    f"{used} | {decision} | {gate_action} | "
                    f"grounding={grounding_r:.2%} | Confidence: {avg_confidence:.2%}"
                ),
                "confidence": avg_confidence,
                "status": "blocked" if gate_action == "abstain" else "success",
            }

        if session_state.get("loop_metadata"):
            last_meta = session_state["loop_metadata"][-1]
            audit_trail = last_meta.get("audit_trail") if isinstance(last_meta, dict) else None
            if isinstance(audit_trail, dict):
                session_state["last_audit_status"] = audit_trail.get("audit_status")
        
        used = last_resolved_model or model_name
        return {
            "answer": answer,
            "decision_tag": f"{used} | {decision} | Session: {session_id} | Confidence: {avg_confidence:.2%}",
            "confidence": avg_confidence,
            "session_id": session_id,
            "status": "success",
        }
    
    # Path 2: Continue existing troubleshooting session
    if session_state["active"]:
        session_state["finding_log"].append(q_raw)
        session_state["turns"] += 1
        
        retrieval_query = session_state.get("topic") or q_raw
        context_docs = retrieve(retrieval_query, k=12, top_n=6)
        
        # Boost error code docs if detected
        error_meta = detect_error_code(q_raw)
        if error_meta and context_docs:
            eid = error_meta.get("error_id")
            key_terms = [f"code {eid}", f"error {eid}", eid]
            
            def score(doc: dict) -> float:
                t = (doc.get("text") or "").lower()
                return int(any(term in t for term in key_terms)) + doc.get("confidence", 0)
            
            context_docs = sorted(context_docs, key=score, reverse=True)
        
        conv_context = build_conversation_context()
        
        if not context_docs:
            prompt = f"""
You are a vehicle maintenance assistant in an ongoing diagnostic session.
Manuals retrieval returned no context. Continue logically using only the user's updates.

{conv_context}
User update:
"{q_raw}"

Give the next 1-3 steps and keep it practical.
"""
        else:
            base_prompt = build_session_prompt(q_raw, context_docs)
            prompt = conv_context + base_prompt if conv_context else base_prompt
        
        answer = agent_router.handle(
            prompt=prompt,
            model=model_name,
            mode=mode,
            session_state=session_state,
            context_docs=context_docs,
            llm_call_fn=llm_dispatch,
        )
        
        # LLM02 Defense: Post-generation output sanitization (deterministic)
        answer = _sanitize_answer(answer)
        
        used = last_resolved_model or model_name
        return {
            "answer": answer,
            "decision_tag": f"{used} | {decision}",
            "status": "success",
        }
    
    # Path 3: Standard one-shot query (no session)
    context_docs = retrieve(q_raw, k=12, top_n=6)
    context_docs = boost_error_docs(q_raw, context_docs)
    
    if not context_docs:
        suggestion = suggest_keywords(q_raw)
        return {
            "answer": f"[ERROR] No relevant technical documentation was found.\n\nSuggestion: {suggestion}",
            "decision_tag": f"{model_name} | {decision}",
            "status": "error",
        }

    signal_path_response = _maybe_signal_path_plan(q_raw, mode, context_docs)
    if signal_path_response:
        return signal_path_response
    
    avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
    print(f"[DEBUG-CORE] Passing {len(context_docs)} docs to agent with avg confidence {avg_confidence:.2%}")
    print(f"[DEBUG-CORE] Individual confidences: {[d.get('confidence', 0.0) for d in context_docs]}")

    if _should_force_procedure_extractive(intent_meta):
        extractive = _build_extractive_response(context_docs)
        return {
            "answer": extractive,
            "decision_tag": f"extractive-procedure | Confidence: {avg_confidence:.2%}",
            "confidence": avg_confidence,
            "status": "success",
        }

    if avg_confidence < CONFIDENCE_THRESHOLD:
        print(
            f"[BLOCKER] Retrieval confidence {avg_confidence:.2%} < {CONFIDENCE_THRESHOLD:.0%} "
            "→ skipping LLM, returning Fast Eval"
        )
        top = context_docs[0] if context_docs else {}
        snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
        src = f"{top.get('source','')} p{top.get('page','')}".strip()
        pieces = [snippet[:280]] if snippet else []
        if src:
            pieces.append(f"Source: {src}")
        answer = "\n".join(pieces) if pieces else "✓ Retrieved context too weak for confident answer."
        return {
            "answer": answer,
            "decision_tag": (
                f"eval-blocked | Confidence: {avg_confidence:.2%} "
                f"(blocker: {CONFIDENCE_THRESHOLD:.0%})"
            ),
            "confidence": avg_confidence,
            "status": "blocked",
        }
    
    answer = agent_router.handle(
        prompt=q_raw,
        model=model_name,
        mode=mode,
        session_state=session_state,
        context_docs=context_docs,
        llm_call_fn=llm_dispatch,
    )
    
    # LLM02 Defense: Post-generation output sanitization (deterministic)
    answer = _sanitize_answer(answer)

    # --- Post-generation quality gate (grounding + confidence + category) -----
    gate_override = _post_generation_quality_gate(
        answer_text=answer if isinstance(answer, str) else "",
        context_docs=context_docs,
        avg_confidence=avg_confidence,
        intent_meta=intent_meta,
    )
    if gate_override is not None:
        gate_action = gate_override.get("gate_action", "unknown")
        grounding_r = gate_override.get("grounding_ratio", 0.0)
        used = last_resolved_model or model_name
        return {
            "answer": gate_override["answer"],
            "decision_tag": (
                f"{used} | {decision} | {gate_action} | "
                f"grounding={grounding_r:.2%} | Confidence: {avg_confidence:.2%}"
            ),
            "confidence": avg_confidence,
            "status": "blocked" if gate_action == "abstain" else "success",
        }

    if session_state.get("loop_metadata"):
        last_meta = session_state["loop_metadata"][-1]
        audit_trail = last_meta.get("audit_trail") if isinstance(last_meta, dict) else None
        if isinstance(audit_trail, dict):
            session_state["last_audit_status"] = audit_trail.get("audit_status")
    
    # Extract source names from context docs for response normalization
    context_sources = []
    if context_docs:
        for d in context_docs:
            source = (d.get("source") or d.get("filename") or d.get("doc_name") or 
                      d.get("doc_id") or "unknown")
            page = d.get("page") or d.get("page_num")
            if page is not None:
                source = f"{source} p{page}"
            context_sources.append(source)
    
    answer_normalized = normalize_response(answer, context_sources=context_sources)
    used = last_resolved_model or model_name
    
    return {
        "answer": answer_normalized,
        "decision_tag": f"{used} | {decision} | Confidence: {avg_confidence:.2%}",
        "confidence": avg_confidence,
        "status": "success",
    }


__all__ = [
    "nova_query_core",
    "suggest_keywords",
]
