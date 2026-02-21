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
    """
    Report readiness and basic diagnostics for the index, router, and machine learning models.
    
    Returns:
        dict: Health snapshot with the following keys:
            status (str): "ok" if the index is loaded and the router is initialized, "degraded" otherwise.
            index_loaded (bool): True when an index exists and no index error is recorded.
            router_initialized (bool): True when the router is considered import-ready.
            model_ready (bool): True when the text embedding model was successfully resolved.
            stats (dict): Runtime statistics provided by the application state.
            errors (dict): Error indicators with:
                index_error (str|None): "index load failure" when an index error exists, otherwise None.
                embed_error (str|None): "embedding load failure" when an embed error exists, otherwise None.
                model_errors (list[str]): Collected generic model initialization error messages.
    """
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
    """
    Provide a read-only summary of the audit chain's tamper-evident integrity.
    
    Builds a structured response from the audit system's verification result. The response contains a top-level `status` ("ok" when verification is valid, "degraded" otherwise), an `integrity` object with verification metrics, and an optional `error` message when the audit system reports an error. When `include_details` is true, the `integrity` object includes a `mismatches` list from the verification.
    
    Parameters:
        limit (int): Maximum number of events to verify; 0 means no limit (default 0).
        include_details (bool): If true, include detailed `mismatches` in the `integrity` object (default False).
    
    Returns:
        dict: {
            "status": "ok" | "degraded",
            "integrity": {
                "valid": bool,
                "total_events": int,
                "hashed_events": int,
                "unhashed_events": int,
                "mismatch_count": int,
                "verified_at": timestamp | None,
                // optional when include_details is True:
                "mismatches": list
            },
            // optional when verification reports an error:
            "error": "audit integrity verification failed"
        }
    """
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