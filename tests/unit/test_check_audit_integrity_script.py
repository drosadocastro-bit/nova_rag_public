from __future__ import annotations

import sqlite3

import pytest

from governance.audit_trail_system import AuditEvent, AuditTrailSystem, EventType, Severity
from scripts.check_audit_integrity import run_check

pytestmark = pytest.mark.unit


def _event(session_id: str) -> AuditEvent:
    return AuditEvent(
        event_type=EventType.POLICY_CHECK,
        session_id=session_id,
        decision="allow",
        severity=Severity.MEDIUM,
        query_hash=f"q-{session_id}",
    )


def test_run_check_returns_zero_for_valid_chain(tmp_path):
    db_path = tmp_path / "audit_ok.db"
    audit = AuditTrailSystem(str(db_path))
    assert audit.log_event(_event("s1"))
    assert audit.log_event(_event("s2"))

    report, code = run_check(
        db_path=str(db_path),
        limit=0,
        include_details=False,
        strict_unhashed=False,
    )

    assert report["valid"] is True
    assert code == 0


def test_run_check_detects_tamper_with_nonzero_exit(tmp_path):
    db_path = tmp_path / "audit_tamper.db"
    audit = AuditTrailSystem(str(db_path))
    assert audit.log_event(_event("s1"))
    assert audit.log_event(_event("s2"))

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT event_id FROM audit_events ORDER BY timestamp ASC, event_id ASC LIMIT 1"
        ).fetchone()
        assert row is not None
        conn.execute(
            "UPDATE audit_events SET event_hash = ? WHERE event_id = ?",
            ("tampered", row[0]),
        )
        conn.commit()

    report, code = run_check(
        db_path=str(db_path),
        limit=0,
        include_details=True,
        strict_unhashed=False,
    )

    assert report["valid"] is False
    assert report["mismatch_count"] >= 1
    assert code == 2
