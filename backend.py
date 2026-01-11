"""
Backend facade for NovaRAG.
Delegates retrieval, generation, and session helpers to modular core packages.
"""

from __future__ import annotations

import os
import re

from agents import agent_router
from core.safety import handle_injection_and_multi_query
from core.utils.search_history import SearchHistory
from response_normalizer import normalize_response

from core.retrieval.retrieval_engine import (
    BASE_DIR,
    DOCS_DIR,
    INDEX_DIR,
    INDEX_PATH,
    DOCS_PATH,
    SEARCH_HISTORY_PATH,
    FAVORITES_PATH,
    DISABLE_EMBED,
    DISABLE_CROSS_ENCODER,
    HYBRID_SEARCH_ENABLED,
    EMBED_BATCH_SIZE,
    text_embed_model_error,
    get_text_embed_model,
    get_cross_encoder,
    ensure_vision_loaded,
    build_index,
    load_index,
    index,
    docs,
    bm25_retrieve,
    lexical_retrieve,
    retrieve,
    detect_error_code,
    boost_error_docs,
    _boost_error_docs,
    vision_search,
    vision_model,
    vision_embeddings,
    vision_paths,
    ERROR_CODE_TO_DOCS,
    GAR_ENABLED,
)
from core.generation.llm_gateway import (
    LLM_LLAMA,
    LLM_OSS,
    MAX_TOKENS_LLAMA,
    MAX_TOKENS_OSS,
    TROUBLESHOOT_TRIGGERS,
    DEEP_KEYWORDS,
    FAST_KEYWORDS,
    USE_NATIVE_ENGINE,
    check_ollama_connection,
    ensure_model_loaded,
    resolve_model_name,
    get_max_tokens,
    choose_model,
    call_llm,
    client,
)
from core.session.session_manager import (
    session_state,
    END_SESSION_TRIGGERS,
    reset_session,
    start_new_session,
    resume_session,
    export_session_to_text,
    save_session_report,
    list_recent_sessions,
)


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
    "ignition",
    "sensors",
    "HVAC",
    "power",
    "diagnostic",
    "maintenance",
]


def _format_context_doc(doc: dict) -> str:
    source = doc.get("source", "unknown")
    page = doc.get("page")
    page_part = f" (pg. {page})" if page is not None else ""
    return f"[Source: {source}{page_part}]\n{doc.get('text', '')}"


def build_standard_prompt(query: str, context_docs: list[dict]) -> str:
    context_text = "\n\n---\n\n".join(_format_context_doc(d) for d in context_docs)

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
- Then numbered steps (1..N)
- Cite sources by filename and page/paragraph number
"""


def build_session_prompt(user_update: str, context_docs: list[dict]) -> str:
    context_text = "\n\n---\n\n".join(_format_context_doc(d) for d in context_docs)
    findings = "\n".join(f"- {f}" for f in session_state.get("finding_log", []))

    return f"""
You are a vehicle maintenance troubleshooting assistant.
You are in the MIDDLE of an ongoing diagnostic session.

Session:
- Topic: {session_state.get('topic')}
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
3) Give the next 1-3 concrete steps
4) If resolved, how to confirm stability

Respond concise and numbered.
"""


def build_conversation_context() -> str:
    if not session_state.get("turn_history"):
        return ""

    context_lines = ["PREVIOUS CONVERSATION HISTORY:"]
    recent_turns = session_state["turn_history"][-3:]
    for i, (q, a) in enumerate(recent_turns, 1):
        context_lines.append(f"\nTurn {i}:")
        context_lines.append(f"Q: {q[:150]}")
        context_lines.append(f"A: {a[:200]}")

    return "\n".join(context_lines) + "\n\n"


def suggest_keywords(query: str) -> str:
    q_lower = query.lower()
    mentioned = [s for s in COMMON_SUBSYSTEMS if s.lower() in q_lower]
    if mentioned:
        return (
            "Try being more specific about the issue with "
            f"{', '.join(mentioned)}. Include alarm codes, symptoms, or component names."
        )
    suggestions = ", ".join(COMMON_SUBSYSTEMS[:12])
    return f"No subsystem keywords detected. Try including: {suggestions}"


def nova_text_handler(
    question: str,
    mode: str,
    npc_name: str | None = None,
    resume_session_id: str | None = None,
    fallback_mode: str | None = None,
) -> tuple[str | dict, str]:
    try:
        safe_preview = (question or "")[:80]
        safe_preview = re.sub(r"[^\x20-\x7E]", "?", safe_preview)
    except Exception:
        safe_preview = "(preview unavailable)"
    print(f"[DEBUG] nova_text_handler called with mode={mode}, question={safe_preview}")

    if not question or not question.strip():
        return "No question entered.", ""

    q_raw = question.strip()
    multi_query_warning: str | None = None

    injection_result = handle_injection_and_multi_query(q_raw)
    if injection_result["refusal"]:
        return injection_result["refusal"], injection_result.get("decision_tag", "")

    q_raw = injection_result["cleaned_question"]
    q_lower = injection_result.get("q_lower", q_raw.lower())
    multi_query_warning = injection_result.get("multi_query_warning")

    try:
        intent_meta = agent_router.classify_intent(q_raw)
        if isinstance(intent_meta, dict) and intent_meta.get("agent") == "refusal":
            intent = (intent_meta.get("intent") or "refusal").strip()
            if intent == "out_of_scope_vehicle":
                message = intent_meta.get(
                    "refusal_reason",
                    "This manual covers automobiles only. Please consult a vehicle-specific manual for your equipment type.",
                )
                reason = "out_of_scope_vehicle"
            elif intent == "unsafe_intent":
                reason = "unsafe_intent"
                message = (
                    "I can't help with that request because it appears to be unsafe or attempts to bypass safety guidance. "
                    "Please ask a safe, manufacturer-recommended maintenance or diagnostic question."
                )
            else:
                reason = "out_of_scope"
                message = (
                    "This question is outside the knowledge base (vehicle maintenance topics). "
                    "Please ask about maintenance procedures, diagnostics, or specifications."
                )
            refusal = {
                "response_type": "refusal",
                "reason": reason,
                "policy": "Scope & Safety",
                "message": message,
                "question": q_raw,
            }
            return refusal, f"refusal | {reason}"
    except Exception:
        pass

    force_retrieval_only = isinstance(fallback_mode, str) and (fallback_mode.lower() == "retrieval-only")
    if force_retrieval_only or (mode or "").lower() in {"eval", "retrieval", "retrieval-only", "fast eval"} or os.environ.get("NOVA_EVAL_FAST", "0") == "1":
        print(f"[DEBUG] Fast eval mode activated for: {q_raw[:80]}")
        context_docs = retrieve(q_raw, k=12, top_n=6)
        print(f"[DEBUG] Retrieved {len(context_docs)} docs")
        if not context_docs:
            return "[ERROR] No context retrieved.", "retrieval-only | no-context"
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
        return answer, f"{suffix} | Confidence: {avg_confidence:.2%}"

    search_history.add(q_raw)

    if resume_session_id:
        if resume_session(resume_session_id):
            return f" Resumed session: {session_state['topic'][:80]}...\nTurns so far: {session_state['turns']}", "session-resumed"
        else:
            return "[ERROR] Could not load that session.", "session-load-failed"

    if any(trigger in q_lower for trigger in END_SESSION_TRIGGERS):
        reset_session(save_to_db=True)
        return " Troubleshooting session saved & reset. New case whenever you're ready.", "session-reset"

    if mode and "NPC" in mode.upper():
        model_name = f"npc:{(npc_name or 'sibiji')}"
        decision = f"NPC: {(npc_name or 'sibiji')}"
    else:
        model_name, decision = choose_model(q_lower, mode)
        if mode and ("LLAMA" in mode.upper() or "GPT" in mode.upper()):
            print(f"[NIC-SAFETY] Mode override '{mode}' bypasses safety routing for query: {q_raw[:50]}...")

    last_resolved_model: str | None = None

    def llm_dispatch(prompt_text: str, requested_model: str | None = None, **kwargs) -> str:
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

    if (not session_state["active"]) and any(t in q_lower for t in TROUBLESHOOT_TRIGGERS):
        session_id = start_new_session(q_raw, model_name, mode)

        context_docs = retrieve(q_raw, k=12, top_n=6)
        context_docs = boost_error_docs(q_raw, context_docs)
        if not context_docs:
            reset_session(save_to_db=False)
            suggestion = suggest_keywords(q_raw)
            return (
                f"[ERROR] I couldn't retrieve relevant manual context for that question.\n\nSuggestion: {suggestion}",
                f"{model_name} | {decision}",
            )

        avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
        ambiguous_terms = ["my vehicle", "my car", "the engine", "my engine", "this vehicle", "generic", "any vehicle"]
        if avg_confidence < 0.65 and any(term in q_lower for term in ambiguous_terms):
            print(f"[CONFIDENCE-GATE] Low confidence ({avg_confidence:.2%}) + ambiguous vehicle term detected")

        if avg_confidence < 0.60:
            print(f"[BLOCKER] Retrieval confidence {avg_confidence:.2%} < 60%  skipping LLM, returning Fast Eval")
            top = context_docs[0] if context_docs else {}
            snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
            src = f"{top.get('source','')} p{top.get('page','')}".strip()
            pieces = [snippet[:280]] if snippet else []
            if src:
                pieces.append(f"Source: {src}")
            answer = "\n".join(pieces) if pieces else " Retrieved context too weak for confident answer."
            reset_session(save_to_db=False)
            return answer, f"eval-blocked | Confidence: {avg_confidence:.2%} (blocker: 60%)"

        prompt = build_standard_prompt(q_raw, context_docs)
        answer = agent_router.handle(
            prompt=prompt,
            model=model_name,
            mode=mode,
            session_state=session_state,
            context_docs=context_docs,
            llm_call_fn=llm_dispatch,
        )
        used = last_resolved_model or model_name
        return answer, f"{used} | {decision} | Session: {session_id} | Confidence: {avg_confidence:.2%}"

    if session_state["active"]:
        session_state["finding_log"].append(q_raw)
        session_state["turns"] += 1

        retrieval_query = session_state.get("topic") or q_raw
        context_docs = retrieve(retrieval_query, k=12, top_n=6)

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
        used = last_resolved_model or model_name
        return answer, f"{used} | {decision}"

    context_docs = retrieve(q_raw, k=12, top_n=6)
    context_docs = boost_error_docs(q_raw, context_docs)
    if not context_docs:
        suggestion = suggest_keywords(q_raw)
        return (
            f"[ERROR] No relevant technical documentation was found.\n\nSuggestion: {suggestion}",
            f"{model_name} | {decision}",
        )

    avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
    print(f"[DEBUG-BACKEND] Passing {len(context_docs)} docs to agent with avg confidence {avg_confidence:.2%}")
    print(f"[DEBUG-BACKEND] Individual confidences: {[d.get('confidence', 0.0) for d in context_docs]}")

    answer = agent_router.handle(
        prompt=q_raw,
        model=model_name,
        mode=mode,
        session_state=session_state,
        context_docs=context_docs,
        llm_call_fn=llm_dispatch,
    )

    answer_normalized = normalize_response(answer)
    used = last_resolved_model or model_name
    return answer_normalized, f"{used} | {decision} | Confidence: {avg_confidence:.2%}"


__all__ = [
    "BASE_DIR",
    "DOCS_DIR",
    "INDEX_DIR",
    "INDEX_PATH",
    "DOCS_PATH",
    "SEARCH_HISTORY_PATH",
    "FAVORITES_PATH",
    "DISABLE_EMBED",
    "DISABLE_CROSS_ENCODER",
    "HYBRID_SEARCH_ENABLED",
    "EMBED_BATCH_SIZE",
    "LLM_LLAMA",
    "LLM_OSS",
    "MAX_TOKENS_LLAMA",
    "MAX_TOKENS_OSS",
    "TROUBLESHOOT_TRIGGERS",
    "DEEP_KEYWORDS",
    "FAST_KEYWORDS",
    "USE_NATIVE_ENGINE",
    "text_embed_model_error",
    "get_text_embed_model",
    "get_cross_encoder",
    "ensure_vision_loaded",
    "build_index",
    "load_index",
    "index",
    "docs",
    "bm25_retrieve",
    "lexical_retrieve",
    "retrieve",
    "detect_error_code",
    "boost_error_docs",
    "_boost_error_docs",
    "vision_search",
    "vision_model",
    "vision_embeddings",
    "vision_paths",
    "ERROR_CODE_TO_DOCS",
    "GAR_ENABLED",
    "check_ollama_connection",
    "ensure_model_loaded",
    "resolve_model_name",
    "get_max_tokens",
    "choose_model",
    "call_llm",
    "client",
    "session_state",
    "END_SESSION_TRIGGERS",
    "reset_session",
    "start_new_session",
    "resume_session",
    "export_session_to_text",
    "save_session_report",
    "list_recent_sessions",
    "search_history",
    "build_standard_prompt",
    "build_session_prompt",
    "build_conversation_context",
    "suggest_keywords",
    "nova_text_handler",
]
