"""Query endpoint for NIC FastAPI app (Nova Intelligent Radar Copilot)."""

from __future__ import annotations

import os
import json
import re
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from agents.agent_router import classify_intent
from core.app_state import get_app_state
from core.config.request_config import set_request_config, clear_request_config
from core.governance.policy_control_plane import (
    evaluate_query_policy,
    extract_session_context,
    log_policy_decision,
)
from core.handlers.query_handler import nova_query_core
from core.retrieval.retrieval_engine import get_last_retrieval_debug

router = APIRouter()

# Per-route rate limit for LLM query endpoint (expensive inference)
_QUERY_RATE = os.environ.get("NOVA_RATE_LIMIT_QUERY", "20/minute")
limiter = Limiter(key_func=get_remote_address)

BASE_DIR = Path(__file__).resolve().parents[2]
INDEX_DIR = BASE_DIR / "vector_db"


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Operator query (max 2000 chars)",
    )
    strict_mode: bool = Field(True, description="Enable strict safety gates")
    assistant_enabled: bool = Field(True, description="Enable Nova assistant")
    options: dict | None = Field(None, description="Optional per-request feature overrides")


class QueryResponse(BaseModel):
    intent: str
    domain: str | None
    confidence: float | None
    path: str
    answer: str | dict
    sources: list[dict]
    evidence_summary: str | None = None
    warnings: list[str]
    trust_status: str | None = None
    debug: dict | None = None


def _option_bool(options: dict | None, key: str, default: bool = False) -> bool:
    if not isinstance(options, dict):
        return default
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@contextmanager
def _runtime_env(strict_mode: bool, assistant_enabled: bool):
    """Apply per-request config via contextvars (no os.environ mutation).

    H2 security fix: uses request-scoped ContextVar instead of mutating
    process-global environment, eliminating race conditions between
    concurrent requests and background LLM threads.
    """
    best_effort = not strict_mode and assistant_enabled
    set_request_config(strict_mode=strict_mode, best_effort=best_effort)
    try:
        yield
    finally:
        clear_request_config()


def _index_version() -> str | None:
    """Return index file mtime for debug display."""
    domain = os.environ.get("NOVA_INDEX_DOMAIN", "").strip().lower()
    suffix = f"_{domain}" if domain and domain != "all" else ""
    index_path = INDEX_DIR / f"nic_index{suffix}.faiss"
    if not index_path.exists():
        return None
    return str(int(index_path.stat().st_mtime))


def _determine_path(status: str, decision_tag: str, response_type: str) -> str:
    if status == "blocked" or "eval-blocked" in decision_tag:
        return "blocked"
    if (
        response_type == "extractive_fallback"
        or "retrieval-only" in decision_tag
        or decision_tag.startswith("forced |")
    ):
        return "extractive_fallback"
    return "generative"


def _infer_domain_hint(query: str) -> str | None:
    q = (query or "").lower()
    patterns = [
        (r"\bnexrad\b|\bwsr-?88d\b|\bweather radar\b", "nexrad"),
        (r"\basr-?8\b|\bair surveillance radar\b|\bairport radar\b", "asr-8"),
        (r"\bbeacon\b|\batcrb\b|\batcbi\b|\batcbi-?5\b|\bsecondary radar\b", "beacon"),
    ]
    for pattern, domain in patterns:
        if re.search(pattern, q):
            return domain
    return None


def _build_sources(debug: dict | None) -> list[dict]:
    if not debug:
        return []
    retrieval = debug.get("retrieval", {})
    selected = retrieval.get("selected_chunks", [])
    if selected:
        return selected

    last_debug = get_last_retrieval_debug() or {}
    ranked = last_debug.get("ranked_chunks", [])
    sources = []
    for item in ranked[:10]:
        sources.append({
            "id": item.get("id"),
            "source": item.get("source"),
            "page": item.get("page"),
            "domain": item.get("domain"),
            "radar_system": item.get("radar_system") or item.get("system"),
            "confidence": item.get("score_mmr") or item.get("score"),
        })
    return sources


def _extract_sources_from_answer_text(answer_text: str) -> list[dict]:
    if not answer_text:
        return []
    matches = re.findall(r"([\w\-./ ]+\.pdf)\s*p\s*(\d+)", answer_text, flags=re.IGNORECASE)
    extracted = []
    seen = set()
    for src_name, page in matches:
        source_name = src_name.strip()
        page_num = int(page)
        key = (source_name.lower(), page_num)
        if key in seen:
            continue
        seen.add(key)
        extracted.append({"source": source_name, "page": page_num})
    return extracted


def _build_evidence_summary(*, path: str, confidence: float | None, sources: list[dict], strict_mode: bool) -> str:
    if confidence is None:
        confidence_label = "confidence unavailable"
    elif confidence >= 0.85:
        confidence_label = "high confidence"
    elif confidence >= 0.70:
        confidence_label = "moderate confidence"
    else:
        confidence_label = "low confidence"

    source_count = len(sources)
    path_label = "generative synthesis" if path == "generative" else "extractive fallback"
    strict_label = "strict mode" if strict_mode else "non-strict mode"

    if source_count == 0:
        return f"{path_label} in {strict_label}; {confidence_label}; no explicit source list returned"

    top = sources[0]
    top_source = top.get("source") or "unknown source"
    top_page = top.get("page")
    if top_page is None:
        top_ref = f"{top_source}"
    else:
        top_ref = f"{top_source} p{top_page}"
    return f"{path_label} in {strict_label}; {confidence_label}; {source_count} source(s), top evidence: {top_ref}"


def _normalize_text_artifacts(text: str) -> str:
    if not text:
        return text
    normalized = text
    replacements = {
        "Â±": "±",
        "â€”": "—",
        "â€“": "–",
        "â€˜": "‘",
        "â€™": "’",
        "â€œ": "“",
        "â€\x9d": "”",
        "â€¢": "•",
        "ð ": "• ",
        "ð\u009f": "",
        "📚 Sources:": "Sources:",
    }
    for bad, good in replacements.items():
        normalized = normalized.replace(bad, good)
    normalized = re.sub(r"Â(?=[^\w\s])", "", normalized)
    normalized = normalized.replace("ð Sources", "• Sources")
    normalized = normalized.replace(" | ð ", " | • ")
    return normalized


@router.post("/query", response_model=QueryResponse)
@limiter.limit(_QUERY_RATE)
def query(request: Request, payload: QueryRequest, debug: bool = Query(False)) -> QueryResponse:
    """Run a NIC query via the authoritative core pipeline."""
    state = get_app_state()
    state.ensure_initialized()

    domain_hint = _infer_domain_hint(payload.query)
    intent_meta = classify_intent(payload.query)
    intent = intent_meta.get("intent", "unknown") if isinstance(intent_meta, dict) else "unknown"

    force_strict = os.environ.get("NOVA_FORCE_STRICT_MODE", "1") == "1"
    effective_strict_mode = True if force_strict else payload.strict_mode

    requested_graph_rag = _option_bool(payload.options, "graph_rag", False)
    requested_vision_reranker = _option_bool(payload.options, "vision_reranker", False)
    session_ctx = extract_session_context(request)
    policy_decision = evaluate_query_policy(
        session_ctx=session_ctx,
        strict_mode=effective_strict_mode,
        assistant_enabled=payload.assistant_enabled,
        graph_rag_enabled=requested_graph_rag,
        vision_reranker_enabled=requested_vision_reranker,
    )
    log_policy_decision(query=payload.query, session_ctx=session_ctx, decision=policy_decision)

    if policy_decision.action == "deny":
        deny_warnings = [f"Policy: {reason}" for reason in policy_decision.reasons]
        response = QueryResponse(
            intent=intent,
            domain=domain_hint,
            confidence=0.0,
            path="blocked",
            answer="Request blocked by governance policy. Obtain required approval and retry.",
            sources=[],
            evidence_summary="blocked by policy control-plane before retrieval/generation",
            warnings=deny_warnings,
            trust_status="blocked",
            debug=None,
        )
        if debug:
            response.debug = {
                "routing_decision": intent,
                "index_version": _index_version(),
                "policy_decision": policy_decision.to_dict(),
                "feature_toggles": {
                    "strict_mode": effective_strict_mode,
                    "assistant_enabled": False,
                    "graph_rag": False,
                    "vision_reranker": False,
                },
            }
        return response

    effective_assistant_enabled = policy_decision.allowed_features["assistant_enabled"]
    graph_rag_enabled = policy_decision.allowed_features["graph_rag"]
    vision_reranker_enabled = policy_decision.allowed_features["vision_reranker"]
    fallback_mode = "retrieval-only" if not effective_assistant_enabled else None

    with _runtime_env(effective_strict_mode, effective_assistant_enabled):
        result = nova_query_core(
            question=payload.query,
            mode="Auto",
            fallback_mode=fallback_mode,
            domain_hint=domain_hint,
            graph_rag_enabled=graph_rag_enabled,
            vision_reranker_enabled=vision_reranker_enabled,
        )

    decision_tag = result.get("decision_tag", "")
    status = result.get("status", "unknown")
    confidence = result.get("confidence")
    answer = result.get("answer", "")
    answer_sources: list[dict] = []
    debug_info = result.get("debug")

    # Normalise dict answers into human-readable strings so the UI always
    # receives clean text rather than raw JSON structures.
    if isinstance(answer, dict):
        response_type = answer.get("response_type", "")
        raw_sources = answer.get("sources") or answer.get("citations") or []
        if isinstance(raw_sources, list):
            for item in raw_sources:
                if isinstance(item, dict):
                    answer_sources.append(item)
                elif isinstance(item, str) and item.strip():
                    answer_sources.append({"source": item.strip()})
        if isinstance(answer.get("answer"), str) and answer["answer"].strip():
            # Structured agent response with a clean text "answer" field
            answer = answer["answer"]
        elif "message" in answer:
            answer = answer["message"]
        elif "reason" in answer:
            answer = answer.get("message", answer.get("reason", str(answer)))
        else:
            # Last resort: pretty-print but strip internal keys
            display = {k: v for k, v in answer.items() if k not in ("response_type",)}
            answer = json.dumps(display, indent=2, ensure_ascii=False)
    elif isinstance(answer, str):
        response_type = ""
    else:
        response_type = ""
        answer = str(answer)

    if isinstance(answer, str):
        answer = _normalize_text_artifacts(answer)

    # Also check debug_info for response_type (may override)
    if debug_info and debug_info.get("response_type"):
        response_type = debug_info["response_type"]
    path = _determine_path(status, decision_tag, response_type)

    domain = None
    if debug_info:
        domain = debug_info.get("query_system") or debug_info.get("domain")
    if domain is None and domain_hint:
        domain = domain_hint

    sources = _build_sources(debug_info)
    if answer_sources:
        merged = []
        seen = set()
        for src in [*sources, *answer_sources]:
            key = (
                str(src.get("id", "")),
                str(src.get("source", "")),
                str(src.get("page", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(src)
        sources = merged

    if not sources and isinstance(answer, str):
        sources = _extract_sources_from_answer_text(answer)

    warnings: list[str] = []
    threshold = float(os.environ.get("NOVA_CONFIDENCE_THRESHOLD", "0.75"))
    if confidence is None:
        warnings.append("No confidence score available; verify against manuals.")
    elif confidence < threshold:
        warnings.append("Low confidence: verify with official manuals before action.")

    if debug_info and debug_info.get("domain_purity", 1.0) < 1.0:
        warnings.append("Domain purity < 1.0: potential cross-domain contamination.")

    if any((s or {}).get("cousin_domain") for s in sources):
        warnings.append("Cousin-domain corroboration used (shared component evidence); procedural steps remain domain-locked.")

    if path != "generative":
        warnings.append("Extractive or blocked path used; no synthesis performed.")

    if not effective_assistant_enabled:
        warnings.append("Nova assistant is OFF: extractive-only response.")

    for reason in policy_decision.reasons:
        warnings.append(f"Policy: {reason}")

    if effective_strict_mode:
        warnings.append("Strict mode ON: purity gate and confidence gate enforced.")

    response = QueryResponse(
        intent=intent,
        domain=domain,
        confidence=confidence,
        path=path,
        answer=answer,
        sources=sources,
        evidence_summary=_build_evidence_summary(
            path=path,
            confidence=confidence,
            sources=sources,
            strict_mode=effective_strict_mode,
        ),
        warnings=warnings,
        trust_status=result.get("trust_status"),
        debug=None,
    )

    if debug:
        debug_payload = debug_info or {}
        debug_payload = dict(debug_payload)
        debug_payload["routing_decision"] = intent
        debug_payload["chunk_ids"] = [s.get("id") for s in sources if s.get("id")]
        debug_payload["index_version"] = _index_version()
        debug_payload["feature_toggles"] = {
            "strict_mode": effective_strict_mode,
            "assistant_enabled": effective_assistant_enabled,
            "graph_rag": graph_rag_enabled,
            "vision_reranker": vision_reranker_enabled,
        }
        debug_payload["policy_decision"] = policy_decision.to_dict()
        response.debug = debug_payload

    return response


@router.post("/query/stream")
@limiter.limit(_QUERY_RATE)
def query_stream(request: Request, payload: QueryRequest):
    """Run a NIC query via the core pipeline with STREAMING response."""
    from fastapi.responses import StreamingResponse
    from core.handlers.query_handler import nova_stream_query

    state = get_app_state()
    state.ensure_initialized()

    force_strict = os.environ.get("NOVA_FORCE_STRICT_MODE", "1") == "1"
    effective_strict_mode = True if force_strict else payload.strict_mode
    requested_graph_rag = _option_bool(payload.options, "graph_rag", False)
    requested_vision_reranker = _option_bool(payload.options, "vision_reranker", False)
    session_ctx = extract_session_context(request)
    policy_decision = evaluate_query_policy(
        session_ctx=session_ctx,
        strict_mode=effective_strict_mode,
        assistant_enabled=payload.assistant_enabled,
        graph_rag_enabled=requested_graph_rag,
        vision_reranker_enabled=requested_vision_reranker,
    )
    log_policy_decision(query=payload.query, session_ctx=session_ctx, decision=policy_decision)

    if policy_decision.action == "deny":
        def denied_stream():
            reason_text = "; ".join(policy_decision.reasons) or "request denied by policy"
            yield f"[POLICY_DENY] {reason_text}\n"

        return StreamingResponse(denied_stream(), media_type="text/plain")

    effective_assistant_enabled = policy_decision.allowed_features["assistant_enabled"]
    graph_rag_enabled = policy_decision.allowed_features["graph_rag"]
    vision_reranker_enabled = policy_decision.allowed_features["vision_reranker"]

    def event_stream():
        with _runtime_env(effective_strict_mode, effective_assistant_enabled):
            if policy_decision.reasons:
                reason_text = "; ".join(policy_decision.reasons)
                yield f"[POLICY] {reason_text}\n"
            for chunk in nova_stream_query(
                question=payload.query,
                mode="Auto",
                app_state=state,
                graph_rag_enabled=graph_rag_enabled,
                vision_reranker_enabled=vision_reranker_enabled,
            ):
                yield chunk

    return StreamingResponse(event_stream(), media_type="text/plain")
