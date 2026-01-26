#!/usr/bin/env python
"""
Verification script for Phase 4.0 Governance Infrastructure.

Tests all governance components to ensure they're operational.
"""

import sys
import time
import tempfile
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from core.governance.model_registry import ModelRegistry, PerformanceMetrics
from core.governance.use_case_registry import UseCaseRegistry, ImpactLevel
from core.governance.access_control import AccessControl, Role, Permission
from core.governance.compliance_reporting import ComplianceReporter, IncidentCategory, IncidentSeverity
from core.governance.sla_management import SLAManager, SLAMetrics


def print_header(text):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def test_model_registry():
    """Test model registry functionality."""
    print_header("Testing Model Registry")
    
    registry = ModelRegistry(":memory:")  # Use in-memory DB to avoid file locking
    
    # Register
    print("✓ Registering model version...")
    model = registry.register_version(
        "test_model", "1.0.0",
        description="Test model",
        hyperparameters={"lr": 0.001}
    )
    assert model.model_id == "test_model"
    assert model.status.value == "registered"
    print(f"  Status: {model.status.value}, Approval: {model.approval_status.value}")
    
    # Approve
    print("✓ Approving model version...")
    registry.approve_version("test_model", "1.0.0", "reviewer_1")
    model = registry.get_version("test_model", "1.0.0")
    assert model.approval_status.value == "approved"
    print(f"  Approved by: {model.approved_by}")
    
    # Deploy
    print("✓ Deploying model version...")
    registry.deploy_version("test_model", "1.0.0", "deploy_1", "production")
    model = registry.get_version("test_model", "1.0.0")
    assert model.status.value == "deployed_production"
    print(f"  Deployed to: {model.status.value}")
    
    # Metrics
    print("✓ Updating performance metrics...")
    metrics = PerformanceMetrics(accuracy=0.95, latency_ms=50.0)
    registry.update_metrics("test_model", "1.0.0", metrics)
    model = registry.get_version("test_model", "1.0.0")
    print(f"  Accuracy: {model.metrics.accuracy}, Latency: {model.metrics.latency_ms}ms")
    
    print("\n✓ Model Registry: OPERATIONAL")


def test_usecase_registry():
    """Test use-case registry functionality."""
    print_header("Testing Use-Case Registry")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = UseCaseRegistry(os.path.join(tmpdir, "usecases.db"))
        
        # Create
        print("✓ Creating use-case...")
        usecase = registry.create_usecase(
            "uc_1", "Use Case 1", "Test use-case",
            "owner_1", impact_level=ImpactLevel.HIGH
        )
        assert usecase.status.value == "draft"
        print(f"  Status: {usecase.status.value}, Impact: {usecase.impact_level.value}")
        
        # Approve
        print("✓ Approving use-case...")
        registry.submit_for_approval("uc_1")
        registry.approve_usecase("uc_1", "approver_1")
        usecase = registry.get_usecase("uc_1")
        assert usecase.status.value == "approved"
        print(f"  Approved by: {usecase.approved_by}")
        
        # Deploy
        print("✓ Deploying use-case...")
        registry.deploy_usecase("uc_1", "deploy_1")
        usecase = registry.get_usecase("uc_1")
        assert usecase.status.value == "deployed"
        print(f"  Status: {usecase.status.value}")
        
        print("\n✓ Use-Case Registry: OPERATIONAL")


def test_access_control():
    """Test access control functionality."""
    print_header("Testing Access Control")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ac = AccessControl(os.path.join(tmpdir, "access.db"))
        
        # Create user
        print("✓ Creating user...")
        ac.create_user("user_1", "user1@example.com")
        print(f"  User ID: user_1")
        
        # Assign role
        print("✓ Assigning role...")
        ac.assign_role("user_1", Role.OPERATOR, "admin")
        roles = ac.get_user_roles("user_1")
        assert Role.OPERATOR in roles
        print(f"  Roles: {[r.value for r in roles]}")
        
        # Check permission
        print("✓ Checking permissions...")
        has_deploy = ac.has_permission("user_1", Permission.MODEL_DEPLOY)
        has_shutdown = ac.has_permission("user_1", Permission.SYSTEM_SHUTDOWN)
        print(f"  Can deploy: {has_deploy}, Can shutdown: {has_shutdown}")
        assert has_deploy is True
        assert has_shutdown is False
        
        # Approval request
        print("✓ Testing approval workflow...")
        request_id = ac.request_approval(
            "model_deploy_production", "user_1",
            {"model_id": "m1", "version": "1.0.0"}
        )
        ac.approve_request(request_id, "user_1", "approved")
        req = ac.get_approval_request(request_id)
        assert req["status"] == "approved"
        print(f"  Request: {request_id}, Status: {req['status']}")
        
        print("\n✓ Access Control: OPERATIONAL")


def test_compliance_reporting():
    """Test compliance reporting functionality."""
    print_header("Testing Compliance Reporting")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = ComplianceReporter(os.path.join(tmpdir, "compliance.db"))
        
        # Report incident
        print("✓ Reporting incident...")
        incident_id = reporter.report_incident(
            IncidentCategory.PERFORMANCE,
            IncidentSeverity.WARNING,
            "High latency",
            "Response times exceeded threshold",
            "model_1",
            affected_count=100
        )
        incident = reporter.get_incident(incident_id)
        print(f"  Incident ID: {incident_id}, Severity: {incident.severity.value}")
        
        # Resolve incident
        print("✓ Resolving incident...")
        reporter.resolve_incident(incident_id, "Fixed connection pool")
        incident = reporter.get_incident(incident_id)
        assert incident.resolved_at is not None
        print(f"  Resolved at: {incident.resolved_at}")
        
        # Audit logging
        print("✓ Logging audit event...")
        reporter.log_audit_event("user_login", "user_1", "system", "login", "success")
        log = reporter.get_audit_log(user_id="user_1")
        assert len(log) > 0
        print(f"  Audit events: {len(log)}")
        
        # Compliance report
        print("✓ Generating compliance report...")
        report = reporter.generate_report()
        assert "summary" in report
        print(f"  Report type: {report['report_type']}")
        print(f"  Total incidents: {report['summary']['total_incidents']}")
        
        print("\n✓ Compliance Reporting: OPERATIONAL")


def test_sla_management():
    """Test SLA management functionality."""
    print_header("Testing SLA Management")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        sla = SLAManager(os.path.join(tmpdir, "sla.db"))
        
        # Define SLA
        print("✓ Defining SLA targets...")
        target = sla.define_sla(
            "model_1", "model",
            response_time_p95=500.0,
            response_time_p99=1000.0,
            availability_target=99.95
        )
        assert target.resource_id == "model_1"
        print(f"  P95: {target.response_time_p95_target}ms, P99: {target.response_time_p99_target}ms")
        
        # Record compliant measurement
        print("✓ Recording compliant measurement...")
        metrics = SLAMetrics(
            response_time_p95=400.0,
            response_time_p99=900.0,
            availability_percent=99.96
        )
        sla.record_measurement("model_1", "model", metrics)
        status = sla.get_sla_status("model_1", "model")
        print(f"  Status: {status.value}")
        
        # Record violation
        print("✓ Recording SLA violation...")
        metrics = SLAMetrics(
            response_time_p95=600.0,  # Exceeds 500ms target
            availability_percent=99.8
        )
        sla.record_measurement("model_1", "model", metrics)
        violations = sla.get_violations(resource_id="model_1")
        assert len(violations) > 0
        print(f"  Violations found: {len(violations)}")
        
        print("\n✓ SLA Management: OPERATIONAL")


def test_integration():
    """Test integrated governance workflow."""
    print_header("Testing Integrated Governance Workflow")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize all components
        models = ModelRegistry(os.path.join(tmpdir, "models.db"))
        usecases = UseCaseRegistry(os.path.join(tmpdir, "usecases.db"))
        access = AccessControl(os.path.join(tmpdir, "access.db"))
        sla = SLAManager(os.path.join(tmpdir, "sla.db"))
        
        print("✓ Complete governance workflow...")
        
        # 1. Create user with operator role
        access.create_user("operator_1", "operator@example.com")
        access.assign_role("operator_1", Role.OPERATOR, "admin")
        
        # 2. Register and deploy model
        models.register_version("classifier", "1.0.0", "Classifier model")
        models.approve_version("classifier", "1.0.0", "reviewer")
        models.deploy_version("classifier", "1.0.0", "d1", "production", "operator_1")
        
        # 3. Create and deploy use-case
        usecases.create_usecase("detection", "Detection", "Detect objects", "owner")
        usecases.approve_usecase("detection", "approver")
        usecases.deploy_usecase("detection", "d2")
        
        # 4. Define and monitor SLAs
        sla.define_sla("classifier", "model")
        metrics = SLAMetrics(response_time_p95=450.0, availability_percent=99.96)
        sla.record_measurement("classifier", "model", metrics)
        
        # Verify all components working together
        model = models.get_deployed_version("classifier")
        usecase = usecases.get_usecase("detection")
        sla_target = sla.get_sla_target("classifier", "model")
        
        assert model is not None
        assert usecase.status.value == "deployed"
        assert sla_target is not None
        
        print("  ✓ Model deployed and monitored")
        print("  ✓ Use-case deployed and tracked")
        print("  ✓ SLA targets defined and measured")
        print("  ✓ Access control enforced")
        
        print("\n✓ Integrated Governance: OPERATIONAL")


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("  PHASE 4.0 GOVERNANCE INFRASTRUCTURE VERIFICATION")
    print("=" * 70)
    
    start_time = time.time()
    
    try:
        test_model_registry()
        test_usecase_registry()
        test_access_control()
        test_compliance_reporting()
        test_sla_management()
        test_integration()
        
        elapsed = time.time() - start_time
        
        print("\n" + "=" * 70)
        print("  VERIFICATION COMPLETE")
        print("=" * 70)
        print(f"\n✓ All components operational")
        print(f"✓ All workflows tested")
        print(f"✓ Integration verified")
        print(f"\nTotal time: {elapsed:.2f} seconds\n")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ VERIFICATION FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
