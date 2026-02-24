from __future__ import annotations


from core.governance.policy_control_plane import (
    SessionContext,
    evaluate_query_policy,
    extract_session_context,
)
from core.session.session_manager import session_state


class _DummyRequest:
    def __init__(self, headers: dict | None = None):
        """
        Initialize a minimal request stub with optional headers.
        
        Parameters:
            headers (dict | None): Dictionary of HTTP headers to attach to the request. If None, an empty dict is used.
        """
        self.headers = headers or {}


def test_evaluate_query_policy_operator_degrades_vision() -> None:
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="operator"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=True,
    )

    assert decision.action == "degrade"
    assert decision.allowed_features["assistant_enabled"] is True
    assert decision.allowed_features["graph_rag"] is True
    assert decision.allowed_features["vision_reranker"] is False
    assert "vision_reranker" in decision.degraded_features


def test_evaluate_query_policy_analyst_degrades_vision_without_approval() -> None:
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="analyst"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=True,
    )

    assert decision.action == "degrade"
    assert decision.allowed_features["assistant_enabled"] is True
    assert decision.allowed_features["graph_rag"] is True
    assert decision.allowed_features["vision_reranker"] is False
    assert "vision_reranker" in decision.approval_required_features
    assert decision.approval_requirements.get("vision_reranker") == "system_config_change"
    assert decision.approval_verified is False


def test_evaluate_query_policy_analyst_allows_when_approval_rule_disabled(monkeypatch) -> None:
    monkeypatch.setenv("NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION", "0")
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="analyst"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=True,
    )

    assert decision.action == "allow"
    assert decision.allowed_features["vision_reranker"] is True


def test_evaluate_query_policy_auditor_assistant_requires_approval() -> None:
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="auditor"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=False,
    )

    assert decision.action == "degrade"
    assert decision.allowed_features["assistant_enabled"] is False
    assert "assistant_enabled" in decision.approval_required_features
    assert decision.approval_requirements.get("assistant_enabled") == "usecase_approve"


def test_evaluate_query_policy_auditor_assistant_allows_with_verified_approval(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.governance.policy_control_plane._is_approval_verified_for_action",
        lambda _request_id, action: action == "usecase_approve",
    )
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="auditor", approval_request_id="req-approved"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=False,
    )

    assert decision.allowed_features["assistant_enabled"] is True
    assert decision.approval_verified is True


def test_evaluate_query_policy_hard_deny_blocks_unapproved_vision(monkeypatch) -> None:
    monkeypatch.setenv("NOVA_POLICY_HARD_DENY", "1")
    decision = evaluate_query_policy(
        session_ctx=SessionContext(role="analyst"),
        strict_mode=True,
        assistant_enabled=True,
        graph_rag_enabled=True,
        vision_reranker_enabled=True,
    )

    assert decision.action == "deny"
    assert "vision_reranker" in decision.denied_features


def test_extract_session_context_uses_active_session_role() -> None:
    previous = dict(session_state)
    try:
        session_state["active"] = True
        session_state["session_id"] = "sess-1"
        session_state["role"] = "admin"
        session_state["user_id"] = "user-admin"

        context = extract_session_context(
            _DummyRequest(
                headers={
                    "X-Session-Id": "sess-1",
                    "X-Approval-Request-Id": "req-123",
                }
            )
        )

        assert context.role == "admin"
        assert context.user_id == "user-admin"
        assert context.session_id == "sess-1"
        assert context.approval_request_id == "req-123"
    finally:
        session_state.clear()
        session_state.update(previous)