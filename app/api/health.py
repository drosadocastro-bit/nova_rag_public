"""Health endpoint for NIC FastAPI app."""

from __future__ import annotations

import os

from fastapi import APIRouter, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.app_state import get_app_state
from core.retrieval.retrieval_engine import get_text_embed_model, get_cross_encoder
from governance.audit_trail_system import get_audit_system

router = APIRouter()

_HEALTH_RATE = os.environ.get("NOVA_RATE_LIMIT_HEALTH", "120/minute")
limiter = Limiter(key_func=get_remote_address)


@router.get("/health")
@limiter.limit(_HEALTH_RATE)
def health(request: Request) -> dict:
    """Report readiness of index, router, and models."""
    state = get_app_state()
    state.ensure_initialized()

    index_loaded = state.index is not None and state.index_error is None
    router_ready = True  # router is import-safe; classify_intent is deterministic

    # Best-effort model readiness: try to resolve text embedding and cross-encoder
    model_ready = False
    model_errors = []
    try:
        _ = get_text_embed_model()
        model_ready = True
    except Exception as exc:  # pragma: no cover - for runtime diagnostics
        # SECURITY: never expose raw exception details on unauthenticated endpoint
        model_errors.append("text_embed_model: initialization error")
        import logging
        logging.getLogger("nova.health").warning("text_embed_model init failed: %s", exc)

    try:
        _ = get_cross_encoder()
    except Exception as exc:  # pragma: no cover
        model_errors.append("cross_encoder: initialization error")
        import logging
        logging.getLogger("nova.health").warning("cross_encoder init failed: %s", exc)

    stats = state.get_stats()
    return {
        "status": "ok" if index_loaded and router_ready else "degraded",
        "index_loaded": index_loaded,
        "router_initialized": router_ready,
        "model_ready": model_ready,
        "stats": stats,
        "errors": {
            "index_error": "index load failure" if state.index_error else None,
            "embed_error": "embedding load failure" if state.embed_error else None,
            "model_errors": model_errors,
        },
    }


@router.get("/audit/integrity")
@limiter.limit(_HEALTH_RATE)
def audit_integrity(
    request: Request,
    limit: int = Query(0, ge=0, le=100000),
    include_details: bool = Query(False),
) -> dict:
    """Read-only tamper-evident audit chain integrity summary."""
    verification = get_audit_system().verify_integrity(limit=limit if limit > 0 else None)

    response = {
        "status": "ok" if verification.get("valid", False) else "degraded",
        "integrity": {
            "valid": verification.get("valid", False),
            "total_events": verification.get("total_events", 0),
            "hashed_events": verification.get("hashed_events", 0),
            "unhashed_events": verification.get("unhashed_events", 0),
            "mismatch_count": verification.get("mismatch_count", 0),
            "verified_at": verification.get("verified_at"),
        },
    }

    if include_details:
        response["integrity"]["mismatches"] = verification.get("mismatches", [])

    if verification.get("error"):
        response["error"] = "audit integrity verification failed"

    return response
