from __future__ import annotations

from pathlib import Path

import pytest

from core.config_features import FeatureFlags, apply_request_overrides
from core.retrieval.graphrag.graph_store import GraphStore, ensure_graph_index_ready
from core.retrieval.vision_reranker_v0 import apply_vision_reranker_v0
from core.trust_context import TrustContext

pytestmark = pytest.mark.unit



def test_feature_flags_request_overrides():
    base = FeatureFlags(graph_rag=False, vision_reranker=False, zero_trust=True)
    merged = apply_request_overrides(
        base,
        {
            "graph_rag": True,
            "vision_reranker": True,
            "zero_trust": False,
        },
    )
    assert merged.graph_rag is True
    assert merged.vision_reranker is True
    assert merged.zero_trust is True


def test_trust_context_status_verified():
    trust = TrustContext.from_query("What is STALO?", {"zero_trust": True})
    trust.record_input_sanitization("What is STALO?", {"injection_detected": False})
    trust.record_retrieval(
        [{"id": "c1", "source": "manual.pdf", "page": 1, "confidence": 0.9}],
        {"domain_purity": 1.0},
    )
    trust.record_output("Stable local oscillator")
    status = trust.finalize()
    assert status == "verified"


def test_graphrag_store_related_chunks(tmp_path):
    db_path = Path(tmp_path) / "graph.sqlite"
    store = GraphStore(db_path=db_path)
    docs = [
        {
            "id": "d1",
            "source": "manual.pdf",
            "page": 10,
            "domain": "nexrad",
            "text": "STALO signal path and oscillator calibration troubleshooting.",
        },
        {
            "id": "d2",
            "source": "manual.pdf",
            "page": 11,
            "domain": "nexrad",
            "text": "Flowchart for oscillator signal fault isolation.",
        },
    ]
    store.rebuild_from_docs(docs)
    related = store.related_chunks("stalo oscillator", limit=2, domain_hint="nexrad")
    assert related
    assert any(item.get("id") == "d1" for item in related)


def test_graphrag_ensure_index_ready_rebuilds_empty_db(tmp_path):
    db_path = Path(tmp_path) / "graph-empty.sqlite"
    store = GraphStore(db_path=db_path)
    assert store.chunk_count() == 0

    docs = [
        {
            "id": "g1",
            "source": "manual.pdf",
            "page": 5,
            "domain": "nexrad",
            "text": "STALO oscillator reference maintenance procedure and calibration checks.",
        },
        {
            "id": "g2",
            "source": "manual.pdf",
            "page": 6,
            "domain": "nexrad",
            "text": "Signal path block diagram includes RF generator and STALO path.",
        },
    ]

    seeded = ensure_graph_index_ready(docs, db_path=db_path)
    assert seeded == len(docs)

    related = store.related_chunks("stalo oscillator signal path", limit=3, domain_hint="nexrad")
    assert related
    assert any(item.get("id") == "g1" for item in related)


def test_vision_reranker_v0_boosts_diagram_chunks():
    candidates = [
        {"id": "a", "text": "See Figure 3 signal path diagram.", "source": "manual.pdf"},
        {"id": "b", "text": "General text only.", "source": "manual.pdf"},
    ]
    scores, meta = apply_vision_reranker_v0("show signal path diagram", candidates, [0.70, 0.70])
    assert meta["applied"] is True
    assert meta["boosted_chunks"] >= 1
    assert scores[0] >= scores[1]


def test_api_query_options_passthrough(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    assert fastapi is not None
    from starlette.requests import Request
    from app.api.query import QueryRequest, query
    from core.session.session_manager import session_state

    captured = {}

    class _State:
        @staticmethod
        def ensure_initialized():
            return None

    monkeypatch.setattr("app.api.query.get_app_state", lambda: _State())
    monkeypatch.setattr("app.api.query.classify_intent", lambda q, domain_hint=None: {"intent": "definition"})
    monkeypatch.setenv("NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION", "0")

    def _fake_core(**kwargs):
        captured.update(kwargs)
        return {
            "answer": "ok",
            "status": "success",
            "decision_tag": "test",
            "confidence": 0.9,
            "trust_status": "verified",
            "debug": {
                "response_type": "text",
                "retrieval": {"selected_chunks": []},
                "domain_purity": 1.0,
            },
        }

    monkeypatch.setattr("app.api.query.nova_query_core", _fake_core)

    previous_state = dict(session_state)
    try:
        session_state["active"] = True
        session_state["session_id"] = "sess-test-analyst"
        session_state["role"] = "analyst"
        request = Request({"type": "http", "headers": [(b"x-session-id", b"sess-test-analyst")]})
        response = query.__wrapped__(
            request=request,
            payload=QueryRequest(
                query="What is STALO?",
                strict_mode=True,
                assistant_enabled=True,
                options={"graph_rag": True, "vision_reranker": True},
            ),
            debug=False,
        )
    finally:
        session_state.clear()
        session_state.update(previous_state)

    assert captured.get("graph_rag_enabled") is True
    assert captured.get("vision_reranker_enabled") is True
    assert response.trust_status == "verified"


def test_api_query_policy_hard_deny_blocks_before_core(monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    assert fastapi is not None
    from starlette.requests import Request
    from app.api.query import QueryRequest, query

    class _State:
        @staticmethod
        def ensure_initialized():
            return None

    monkeypatch.setattr("app.api.query.get_app_state", lambda: _State())
    monkeypatch.setattr("app.api.query.classify_intent", lambda q, domain_hint=None: {"intent": "definition"})
    monkeypatch.setenv("NOVA_POLICY_HARD_DENY", "1")

    def _should_not_run(**kwargs):
        raise AssertionError("nova_query_core should not be called under hard deny")

    monkeypatch.setattr("app.api.query.nova_query_core", _should_not_run)

    request = Request({"type": "http", "headers": []})
    response = query.__wrapped__(
        request=request,
        payload=QueryRequest(
            query="What is STALO?",
            strict_mode=True,
            assistant_enabled=True,
            options={"vision_reranker": True},
        ),
        debug=True,
    )

    assert response.path == "blocked"
    assert response.trust_status == "blocked"
    assert response.debug is not None
    assert response.debug.get("policy_decision", {}).get("action") == "deny"
