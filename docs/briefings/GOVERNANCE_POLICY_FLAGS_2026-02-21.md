# Governance Policy Flags (Query Control Plane)
Date: 2026-02-21

## Purpose

This briefing documents runtime governance flags introduced for NIC query control-plane enforcement at FastAPI boundaries.

Scope covered:
- `/api/query`
- `/api/query/stream`

All behavior is offline-safe and deterministic with explicit allow/degrade/deny outcomes.

## New / Active Flags

- `NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION` (default: `1`)
  - When enabled, `vision_reranker` requests from `operator`, `analyst`, and `auditor` require approved action `system_config_change`.
  - If missing/unapproved, request is downgraded (or denied if hard-deny mode is enabled).

- `NOVA_POLICY_REQUIRE_APPROVAL_FOR_ASSISTANT_ELEVATION` (default: `1`)
  - Applies to `auditor` role requesting `assistant_enabled=true`.
  - Requires approved action `usecase_approve` to elevate assistant capability.

- `NOVA_POLICY_HARD_DENY` (default: `0`)
  - When `0`: policy violations produce safe-degrade behavior.
  - When `1`: selected unapproved high-risk requests return explicit deny.

- `NOVA_ACCESS_CONTROL_DB` (optional)
  - Path to AccessControl SQLite DB used for approval verification.
  - Approval token header is best-effort verified against this DB.

## Request Header Inputs

- `X-Session-Id`
- `X-User-Id`
- `X-User-Role`
- `X-Approval-Request-Id`

`X-Approval-Request-Id` is evaluated against `NOVA_ACCESS_CONTROL_DB` (if configured) and mapped to required action per feature.

## Decision Outcomes

- `allow`: requested features are permitted.
- `degrade`: feature toggles are safely reduced (e.g., disabling unapproved vision reranker).
- `deny`: request blocked before retrieval/generation when hard-deny mode is enabled.

## Observability & Audit

Policy decision audit includes:
- `action`, `role`, `risk_level`
- `requested_features`, `allowed_features`
- `degraded_features`, `denied_features`
- `approval_required_features`, `approval_requirements`, `approval_verified`
- `approval_request_id`

Audit event type: `POLICY_CHECK`.

### Tamper-Evident Chain (Phase 3)

Audit records now include hash-chain linkage fields:
- `previous_event_hash`
- `event_hash`

Each new event hash is computed from:
- canonical event payload (sorted JSON)
- previous event hash value

Integrity verification is available via audit subsystem API:
- `AuditTrailSystem.verify_integrity(limit: Optional[int] = None)`

Read-only operator endpoint:
- `GET /api/audit/integrity`
- Query params:
  - `limit` (optional, default full scan)
  - `include_details` (default `false`)

Offline CLI checker:
- `scripts/check_audit_integrity.py`
- Windows wrapper: `scripts/check_audit_integrity.ps1`
- Example:

```powershell
C:/nova_rag_public/.venv/Scripts/python.exe scripts/check_audit_integrity.py --db-path C:/nova_rag_public/audit_trail.db --include-details
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_audit_integrity.ps1 -IncludeDetails
```

Exit codes:
- `0`: integrity valid
- `2`: integrity mismatch/tamper detected
- `3`: strict-unhashed mode failed (legacy unhashed events present)

Hash-chain backfill utility:
- `scripts/backfill_audit_hash_chain.py`
- Recommended flow:

```powershell
# 1) preview (dry-run)
C:/nova_rag_public/.venv/Scripts/python.exe scripts/backfill_audit_hash_chain.py --db-path C:/nova_rag_public/audit_trail.db --rewrite-all

# 2) apply rewrite + immediate verification
C:/nova_rag_public/.venv/Scripts/python.exe scripts/backfill_audit_hash_chain.py --db-path C:/nova_rag_public/audit_trail.db --rewrite-all --apply

# 3) strict integrity check should now pass without unhashed events
C:/nova_rag_public/.venv/Scripts/python.exe scripts/check_audit_integrity.py --db-path C:/nova_rag_public/audit_trail.db --strict-unhashed
```

Verification output includes:
- `valid`, `mismatch_count`, `mismatches`
- `hashed_events`, `unhashed_events` (legacy compatibility visibility)

## Operator Guidance

- Default production-safe posture:
  - Keep approval flags enabled.
  - Keep `NOVA_POLICY_HARD_DENY=0` for degrade-first rollout.
- Security-tight posture:
  - Set `NOVA_POLICY_HARD_DENY=1` once workflows and approvals are operationally validated.
- For deterministic approval checks:
  - Set `NOVA_ACCESS_CONTROL_DB` to an initialized access-control database.

## Operator Runbook (Rollout Modes)

### Mode A — Degrade-First (Recommended Initial Rollout)

Use this mode to keep service availability while enforcing safe capability reductions.

```powershell
$env:FORCE_OFFLINE="1"
$env:NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION="1"
$env:NOVA_POLICY_REQUIRE_APPROVAL_FOR_ASSISTANT_ELEVATION="1"
$env:NOVA_POLICY_HARD_DENY="0"
$env:NOVA_ACCESS_CONTROL_DB="C:\nova_rag_public\artifacts\access_control.db"
```

Expected behavior:
- Unapproved high-risk requests are downgraded (degrade).
- Query execution continues in reduced-capability mode.
- Audit includes policy decision and approval verification metadata.

### Mode B — Hard-Deny (Tight Enforcement)

Use this mode after approval workflows are operationally validated.

```powershell
$env:FORCE_OFFLINE="1"
$env:NOVA_POLICY_REQUIRE_APPROVAL_FOR_VISION="1"
$env:NOVA_POLICY_REQUIRE_APPROVAL_FOR_ASSISTANT_ELEVATION="1"
$env:NOVA_POLICY_HARD_DENY="1"
$env:NOVA_ACCESS_CONTROL_DB="C:\nova_rag_public\artifacts\access_control.db"
```

Expected behavior:
- Selected unapproved high-risk requests are blocked (deny).
- `/api/query` returns blocked response before retrieval/generation.
- `/api/query/stream` emits policy deny marker and stops core stream execution.

### Quick Verification Commands

```powershell
# focused governance/API checks
C:/nova_rag_public/.venv/Scripts/python.exe -m pytest tests/test_api_streaming.py tests/test_optional_enhancements.py tests/unit/test_policy_control_plane.py -q --no-cov
```
