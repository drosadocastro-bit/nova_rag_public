"""Runtime policy control-plane decisions for NIC query endpoints.

Phase 1 scope:
- Session-based role resolution
- Capability allow/deny/degrade decisions
- Canonical policy decision audit logging
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict

from fastapi import Request

from core.session.session_manager import session_state
from governance.audit_trail_system import AuditEvent, Authority, EventType, Severity, get_audit_system

logger = logging.getLogger(__name__)

_VALID_ROLES = {"operator", "analyst", "approver", "admin", "auditor"}


@dataclass
class SessionContext:
    """Resolved session/user context for policy checks."""

    session_id: str | None = None
    user_id: str | None = None
    role: str = "operator"
    approval_request_id: str | None = None


@dataclass
class PolicyDecision:
    """Outcome of runtime governance checks for a query request."""

    action: str
    role: str
    requested_features: Dict[str, bool]
    allowed_features: Dict[str, bool]
    degraded_features: list[str] = field(default_factory=list)
    denied_features: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    risk_level: str = "low"
    approval_required_features: list[str] = field(default_factory=list)
    approval_verified: bool = False
    approval_requirements: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the PolicyDecision into a plain dictionary suitable for logging or JSON encoding.
        
        Returns:
            decision_dict (Dict[str, Any]): Dictionary with the following keys:
                - "action" (str): Decision action, e.g. "allow", "degrade", or "deny".
                - "role" (str): Resolved user role that produced the decision.
                - "requested_features" (Dict[str, bool]): Features requested by the query.
                - "allowed_features" (Dict[str, bool]): Features permitted for the role after policy evaluation.
                - "degraded_features" (List[str]): Features that were downgraded.
                - "denied_features" (List[str]): Features that were denied.
                - "reasons" (List[str]): Human-readable reasons explaining the decision.
                - "risk_level" (str): Risk classification, e.g. "low", "medium", or "high".
                - "approval_required_features" (List[str]): Features requiring approval.
                - "approval_verified" (bool): Whether required approvals were verified.
                - "approval_requirements" (Dict[str, str]): Mapping of feature to required approval action or note.
        """
        return {
            "action": self.action,
            "role": self.role,
            "requested_features": dict(self.requested_features),
            "allowed_features": dict(self.allowed_features),
            "degraded_features": list(self.degraded_features),
            "denied_features": list(self.denied_features),
            "reasons": list(self.reasons),
            "risk_level": self.risk_level,
            "approval_required_features": list(self.approval_required_features),
            "approval_verified": self.approval_verified,
            "approval_requirements": dict(self.approval_requirements),
        }


def extract_session_context(request: Request) -> SessionContext:
    """
    Resolve session and user role context from an incoming Request.
    
    Determines session_id, user_id, role, and approval_request_id using request headers and the global session_state. When a request session ID matches an active session_state, values from the session_state take precedence; if no session ID is provided but session_state is active, session_state values are used. If a valid role is not obtained from session_state, a valid X-User-Role header is used; otherwise the role defaults to "operator".
    
    Returns:
        SessionContext: Resolved session_id, user_id, role, and approval_request_id.
    """
    default_role = os.environ.get("NOVA_DEFAULT_SESSION_ROLE", "operator").strip().lower() or "operator"
    session_id = request.headers.get("X-Session-Id")
    user_id = request.headers.get("X-User-Id")
    header_role = (request.headers.get("X-User-Role") or "").strip().lower()
    approval_request_id = request.headers.get("X-Approval-Request-Id")

    role = default_role
    state_session_id = session_state.get("session_id")

    if session_id and state_session_id and session_id == state_session_id:
        state_role = str(session_state.get("role") or "").strip().lower()
        state_user = str(session_state.get("user_id") or "").strip()
        if state_role in _VALID_ROLES:
            role = state_role
        if state_user:
            user_id = user_id or state_user
    elif not session_id and session_state.get("active"):
        state_role = str(session_state.get("role") or "").strip().lower()
        state_user = str(session_state.get("user_id") or "").strip()
        if state_role in _VALID_ROLES:
            role = state_role
        if state_user:
            user_id = user_id or state_user
        if state_session_id:
            session_id = str(state_session_id)

    if role not in _VALID_ROLES and header_role in _VALID_ROLES:
        role = header_role

    if role not in _VALID_ROLES:
        role = "operator"

    return SessionContext(
        session_id=session_id,
        user_id=user_id,
        role=role,
        approval_request_id=approval_request_id,
    )


def _is_approval_verified_for_action(approval_request_id: str | None, required_action: str) -> bool:
    """
    Verify whether an approval request is recorded as approved for a specific action.
    
    Performs a best-effort check against the access-control database referenced by the
    NOVA_ACCESS_CONTROL_DB environment variable. If no approval_request_id is provided,
    the access-control DB path is missing, the request is not found, or any error
    occurs while fetching the request, the approval is treated as unverified and
    the function returns False.
    
    Parameters:
        approval_request_id (str | None): Approval request identifier to verify.
        required_action (str): Action name that the approval must match.
    
    Returns:
        bool: `True` if the approval request exists, has status `"approved"`, and its
        `"action"` equals `required_action`; `False` otherwise.
    """
    if not approval_request_id:
        return False

    access_db_path = os.environ.get("NOVA_ACCESS_CONTROL_DB", "").strip()
    if not access_db_path:
        return False

    try:
        from core.governance.access_control import AccessControl

        access = AccessControl(access_db_path)
        req = access.get_approval_request(approval_request_id)
        if not req:
            return False
        return req.get("status") == "approved" and req.get("action") == required_action
    except Exception:
        return False


def evaluate_query_policy(
    *,
    session_ctx: SessionContext,
    strict_mode: bool,
    assistant_enabled: bool,
    graph_rag_enabled: bool,
    vision_reranker_enabled: bool,
) -> PolicyDecision:
    """
    Determine allowed, degraded, or denied query features based on session role, requested capabilities, and configured approval and hard-deny rules.
    
    Parameters:
        session_ctx (SessionContext): Resolved session context (includes role, user id, and optional approval_request_id) used to evaluate role-based capabilities and approval status.
        strict_mode (bool): Whether strict mode was requested for the query (propagated into the decision).
        assistant_enabled (bool): Whether assistant features were requested.
        graph_rag_enabled (bool): Whether graph RAG features were requested.
        vision_reranker_enabled (bool): Whether the vision re-ranker feature was requested.
    
    Returns:
        PolicyDecision: A decision object containing:
            - action: "allow", "degrade", or "deny" indicating the overall policy outcome.
            - role: resolved role used for evaluation.
            - requested_features: map of the original requested feature flags.
            - allowed_features: map of which requested features are permitted after policy checks.
            - degraded_features: list of features requested but disabled by policy (safe-degraded).
            - denied_features: list of features explicitly denied (only in hard-deny mode).
            - reasons: human-readable reasons for degradations/denials.
            - risk_level: assessed risk level ("low", "medium", or "high").
            - approval_required_features: features that require explicit approval for the session/role.
            - approval_verified: whether an applicable approval was verified for the session.
            - approval_requirements: mapping of features to the required approval action name.
    """
    requested = {
        "strict_mode": strict_mode,
        "assistant_enabled": assistant_enabled,
        "graph_rag": graph_rag_enabled,
        "vision_reranker": vision_reranker_enabled,
    }

    # Baseline role capability matrix (phase 1)
    role_caps = {
        "operator": {"assistant_enabled": True, "graph_rag": True, "vision_reranker": False},
        "analyst": {"assistant_enabled": True, "graph_rag": True, "vision_reranker": True},
        "approver": {"assistant_enabled": True, "graph_rag": True, "vision_reranker": True},
        "admin": {"assistant_enabled": True, "graph_rag": True, "vision_reranker": True},
        "auditor": {"assistant_enabled": False, "graph_rag": True, "vision_reranker": False},
    }
    caps = role_caps.get(session_ctx.role, role_caps["operator"])

    allowed = {
        "strict_mode": requested["strict_mode"],
        "assistant_enabled": requested["assistant_enabled"] and caps["assistant_enabled"],
        "graph_rag": requested["graph_rag"] and caps["graph_rag"],
        "vision_reranker": requested["vision_reranker"] and caps["vision_reranker"],
    }

    approval_required = []
    approval_requirements: Dict[str, str] = {}
    approval_verified = False
    require_vision_approval = os.environ.get("NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION", "1") == "1"
    require_assistant_elevation_approval = (
        os.environ.get("NOVA_POLICY_REQUIRE_APPROVAL_FOR_ASSISTANT_ELEVATION", "1") == "1"
    )

    degraded = []
    reasons = []
    denied = []

    if (
        require_vision_approval
        and requested["vision_reranker"]
        and session_ctx.role in {"operator", "analyst", "auditor"}
    ):
        approval_required.append("vision_reranker")
        approval_requirements["vision_reranker"] = "system_config_change"
        vision_approved = _is_approval_verified_for_action(
            session_ctx.approval_request_id,
            "system_config_change",
        )
        approval_verified = approval_verified or vision_approved
        if not vision_approved:
            allowed["vision_reranker"] = False
            reasons.append("vision_reranker requires approved SYSTEM_CONFIG_CHANGE request")

    if (
        require_assistant_elevation_approval
        and requested["assistant_enabled"]
        and not caps["assistant_enabled"]
        and session_ctx.role in {"auditor"}
    ):
        approval_required.append("assistant_enabled")
        approval_requirements["assistant_enabled"] = "usecase_approve"
        assistant_approved = _is_approval_verified_for_action(
            session_ctx.approval_request_id,
            "usecase_approve",
        )
        approval_verified = approval_verified or assistant_approved
        if assistant_approved:
            allowed["assistant_enabled"] = True
        else:
            allowed["assistant_enabled"] = False
            reasons.append("assistant_enabled requires approved USECASE_APPROVE request for auditor role")

    for feature in ("assistant_enabled", "graph_rag", "vision_reranker"):
        if requested[feature] and not allowed[feature]:
            degraded.append(feature)
            reasons.append(f"{feature} disabled by policy for role={session_ctx.role}")

    action = "allow"
    if degraded:
        action = "degrade"

    hard_deny_enabled = os.environ.get("NOVA_POLICY_HARD_DENY", "0") == "1"
    if hard_deny_enabled:
        if "vision_reranker" in approval_required and requested["vision_reranker"] and not allowed["vision_reranker"]:
            denied.append("vision_reranker")
        if (
            "assistant_enabled" in approval_required
            and requested["assistant_enabled"]
            and not allowed["assistant_enabled"]
        ):
            denied.append("assistant_enabled")
        if denied:
            action = "deny"
            reasons.append("request denied by hard policy mode")

    risk_level = "low"
    if requested["vision_reranker"]:
        risk_level = "medium"
    if requested["vision_reranker"] and not allowed["vision_reranker"]:
        risk_level = "high"
    if requested["assistant_enabled"] and not allowed["assistant_enabled"] and session_ctx.role == "auditor":
        risk_level = "high"
    if denied:
        risk_level = "high"

    return PolicyDecision(
        action=action,
        role=session_ctx.role,
        requested_features=requested,
        allowed_features=allowed,
        degraded_features=degraded,
        denied_features=denied,
        reasons=reasons,
        risk_level=risk_level,
        approval_required_features=approval_required,
        approval_verified=approval_verified,
        approval_requirements=approval_requirements,
    )


def log_policy_decision(*, query: str, session_ctx: SessionContext, decision: PolicyDecision) -> None:
    """
    Emit a canonical audit event recording a query policy decision.
    
    Parameters:
    	query (str): The original query string; a SHA-256 hash of this value is stored in the audit event (query itself is not logged).
    	session_ctx (SessionContext): Resolved session context containing session_id, user_id, role, and approval_request_id.
    	decision (PolicyDecision): Policy decision describing action, requested/allowed features, degradations/denials, reasons, risk level, and approval details.
    
    Notes:
    	This function maps decision.risk_level to a numeric risk_score, sets event severity to MEDIUM for degradations (LOW otherwise),
    	includes decision fields in event metadata, and performs best-effort logging — any exceptions during audit emission are caught and logged locally.
    """
    try:
        query_hash = hashlib.sha256((query or "").encode("utf-8", errors="ignore")).hexdigest()
        severity = Severity.MEDIUM if decision.action == "degrade" else Severity.LOW
        risk_score = 0.2
        if decision.risk_level == "medium":
            risk_score = 0.6
        elif decision.risk_level == "high":
            risk_score = 0.85
        event = AuditEvent(
            event_type=EventType.POLICY_CHECK,
            session_id=session_ctx.session_id or "unknown",
            query_hash=query_hash,
            decision=decision.action,
            authority=Authority.SYSTEM,
            risk_score=risk_score,
            user_role=session_ctx.role,
            severity=severity,
            control_name="query_policy_control_plane",
            control_reason="; ".join(decision.reasons) if decision.reasons else "policy check passed",
            metadata={
                "role": session_ctx.role,
                "user_id": session_ctx.user_id,
                "approval_request_id": session_ctx.approval_request_id,
                "requested_features": decision.requested_features,
                "allowed_features": decision.allowed_features,
                "degraded_features": decision.degraded_features,
                "denied_features": decision.denied_features,
                "risk_level": decision.risk_level,
                "approval_required_features": decision.approval_required_features,
                "approval_verified": decision.approval_verified,
                "approval_requirements": decision.approval_requirements,
            },
        )
        get_audit_system().log_event(event)
    except Exception as exc:
        logger.warning("Failed to log policy decision", extra={"error": str(exc)[:200]})