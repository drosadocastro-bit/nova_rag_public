from __future__ import annotations

import sqlite3

import pytest

from governance.audit_trail_system import AuditEvent, AuditTrailSystem, EventType, Severity

pytestmark = pytest.mark.unit


def _event(session_id: str) -> AuditEvent:
    return AuditEvent(
        event_type=EventType.POLICY_CHECK,
        session_id=session_id,
        decision="allow",
        severity=Severity.MEDIUM,
        query_hash=f"q-{session_id}",
    )


def test_backfill_rewrite_all_rehashes_legacy_rows(tmp_path):
    db_path = tmp_path / "audit_backfill.db"
    audit = AuditTrailSystem(str(db_path))

    assert audit.log_event(_event("s1"))
    assert audit.log_event(_event("s2"))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE audit_events SET event_hash = NULL, previous_event_hash = NULL")
        conn.commit()

    before = audit.verify_integrity()
    assert before["unhashed_events"] == 2

    result = audit.backfill_hash_chain(rewrite_all=True, dry_run=False)
    assert result["updated_events"] == 2

    after = audit.verify_integrity()
    assert after["valid"] is True
    assert after["unhashed_events"] == 0


def test_backfill_dry_run_does_not_modify_db(tmp_path):
    db_path = tmp_path / "audit_backfill_dry.db"
    audit = AuditTrailSystem(str(db_path))

    assert audit.log_event(_event("s1"))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE audit_events SET event_hash = NULL, previous_event_hash = NULL")
        conn.commit()

    result = audit.backfill_hash_chain(rewrite_all=True, dry_run=True)
    assert result["updated_events"] == 1

    verify = audit.verify_integrity()
    assert verify["unhashed_events"] == 1
