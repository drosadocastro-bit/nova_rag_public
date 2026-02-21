from __future__ import annotations

import sqlite3

import pytest

from governance.audit_trail_system import AuditEvent, AuditTrailSystem, EventType, Severity

pytestmark = pytest.mark.unit


def _new_event(session_id: str, decision: str = "allow") -> AuditEvent:
    """
    Create a preconfigured AuditEvent for tests representing a policy check.
    
    Parameters:
        session_id (str): Identifier for the event; also used to derive the event's query_hash.
        decision (str): Decision associated with the event (e.g., "allow", "degrade").
    
    Returns:
        AuditEvent: An event with EventType.POLICY_CHECK, Severity.MEDIUM, query_hash set to "hash-{session_id}", and user_role "operator".
    """
    return AuditEvent(
        event_type=EventType.POLICY_CHECK,
        session_id=session_id,
        decision=decision,
        severity=Severity.MEDIUM,
        query_hash=f"hash-{session_id}",
        user_role="operator",
    )


def test_audit_hash_chain_integrity_passes(tmp_path):
    db_path = tmp_path / "audit_chain.db"
    audit = AuditTrailSystem(str(db_path))

    assert audit.log_event(_new_event("s1"))
    assert audit.log_event(_new_event("s2", decision="degrade"))

    report = audit.verify_integrity()

    assert report["valid"] is True
    assert report["total_events"] == 2
    assert report["hashed_events"] == 2
    assert report["mismatch_count"] == 0


def test_audit_hash_chain_detects_tamper(tmp_path):
    """
    Verifies that AuditTrailSystem.verify_integrity detects a tampered event hash.
    
    Creates an AuditTrailSystem using a temporary SQLite file, logs two events, directly modifies the first event's stored hash, runs verify_integrity, and asserts the report marks the chain invalid with at least one mismatch and a non-empty mismatches list.
    
    Parameters:
        tmp_path (pathlib.Path): pytest fixture providing a temporary directory for the database file.
    """
    db_path = tmp_path / "audit_chain_tamper.db"
    audit = AuditTrailSystem(str(db_path))

    assert audit.log_event(_new_event("s1"))
    assert audit.log_event(_new_event("s2"))

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT event_id FROM audit_events ORDER BY timestamp ASC, event_id ASC LIMIT 1"
        ).fetchone()
        assert row is not None
        conn.execute(
            "UPDATE audit_events SET event_hash = ? WHERE event_id = ?",
            ("tampered_hash", row[0]),
        )
        conn.commit()

    report = audit.verify_integrity()

    assert report["valid"] is False
    assert report["mismatch_count"] >= 1
    assert report["mismatches"]