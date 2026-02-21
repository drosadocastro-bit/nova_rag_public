import pytest
from fastapi.testclient import TestClient
from app.nic_fastapi_app import app

pytestmark = pytest.mark.integration


client = TestClient(app)


def test_audit_integrity_summary_ok(monkeypatch):
    monkeypatch.setattr(
        "app.api.health.get_audit_system",
        lambda: type(
            "_Audit",
            (),
            {
                "verify_integrity": staticmethod(
                    lambda limit=None: {
                        "valid": True,
                        "total_events": 5,
                        "hashed_events": 5,
                        "unhashed_events": 0,
                        "mismatch_count": 0,
                        "verified_at": "2026-02-21T00:00:00",
                        "mismatches": [],
                    }
                )
            },
        )(),
    )

    response = client.get("/api/audit/integrity")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["integrity"]["valid"] is True
    assert "mismatches" not in data["integrity"]


def test_audit_integrity_include_details_and_degraded(monkeypatch):
    monkeypatch.setattr(
        "app.api.health.get_audit_system",
        lambda: type(
            "_Audit",
            (),
            {
                "verify_integrity": staticmethod(
                    lambda limit=None: {
                        "valid": False,
                        "total_events": 4,
                        "hashed_events": 4,
                        "unhashed_events": 0,
                        "mismatch_count": 1,
                        "verified_at": "2026-02-21T00:00:00",
                        "mismatches": [{"event_id": "e1"}],
                    }
                )
            },
        )(),
    )

    response = client.get("/api/audit/integrity?include_details=true&limit=100")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["integrity"]["mismatch_count"] == 1
    assert len(data["integrity"]["mismatches"]) == 1
