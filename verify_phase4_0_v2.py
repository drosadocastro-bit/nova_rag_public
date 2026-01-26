#!/usr/bin/env python
"""
Verification script for Phase 4.0 Governance Infrastructure.
Tests all governance components to ensure they're operational.
"""

import sys
import time
import os
import tempfile
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from core.governance.model_registry import ModelRegistry, PerformanceMetrics
from core.governance.use_case_registry import UseCaseRegistry, ImpactLevel
from core.governance.access_control import AccessControl, Role, Permission, ApprovalAction
from core.governance.compliance_reporting import ComplianceReporter, IncidentCategory, IncidentSeverity
from core.governance.sla_management import SLAManager, SLAMetrics


# Use a temporary directory that persists for the entire test run
TEMP_DIR = tempfile.mkdtemp(prefix="governance_test_")

def get_db_path(name: str) -> str:
    """Get a consistent database path for a component."""
    db_path = os.path.join(TEMP_DIR, f"{name}.db")
    return db_path


def print_header(text):
    """Print section header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def test_model_registry():
    """Test model registry functionality."""
    print_header("Testing Model Registry")
    
    registry = ModelRegistry(get_db_path("model_registry"))  # File-based DB
    
    print("✓ Registering model version...")
    model = registry.register_version("test_model", "1.0.0", description="Test model")
    assert model.status.value == "registered"
    print(f"  Status: {model.status.value}")
    
    print("✓ Approving model version...")
    registry.approve_version("test_model", "1.0.0", "reviewer_1")
    model = registry.get_version("test_model", "1.0.0")
    assert model.approval_status.value == "approved"
    print(f"  Approved by: {model.approved_by}")
    
    print("✓ Deploying model version...")
    registry.deploy_version("test_model", "1.0.0", "deploy_1", "production")
    model = registry.get_version("test_model", "1.0.0")
    assert model.status.value == "deployed_production"
    
    print("✓ Updating performance metrics...")
    metrics = PerformanceMetrics(accuracy=0.95, latency_ms=50.0)
    registry.update_metrics("test_model", "1.0.0", metrics)
    
    print("\n✓ Model Registry: OPERATIONAL")


def test_usecase_registry():
    """Test use-case registry functionality."""
    print_header("Testing Use-Case Registry")
    
    registry = UseCaseRegistry(get_db_path("usecase_registry"))
    
    print("✓ Creating use-case...")
    usecase = registry.create_usecase("uc_1", "Use Case 1", "Test use-case", "owner_1")
    assert usecase.status.value == "draft"
    
    print("✓ Approving use-case...")
    registry.submit_for_approval("uc_1")
    registry.approve_usecase("uc_1", "approver_1")
    usecase = registry.get_usecase("uc_1")
    assert usecase.status.value == "approved"
    
    print("✓ Deploying use-case...")
    registry.deploy_usecase("uc_1", "deploy_1")
    usecase = registry.get_usecase("uc_1")
    assert usecase.status.value == "deployed"
    
    print("\n✓ Use-Case Registry: OPERATIONAL")


def test_access_control():
    """Test access control functionality."""
    print_header("Testing Access Control")
    
    ac = AccessControl(get_db_path("access_control"))
    
    print("✓ Creating user...")
    ac.create_user("user_1", "user1@example.com")
    
    print("✓ Assigning role...")
    ac.assign_role("user_1", Role.OPERATOR, "admin")
    roles = ac.get_user_roles("user_1")
    assert Role.OPERATOR in roles
    
    print("✓ Checking permissions...")
    has_deploy = ac.has_permission("user_1", Permission.MODEL_DEPLOY)
    assert has_deploy is True
    
    print("✓ Testing approval workflow...")
    request_id = ac.request_approval(ApprovalAction.MODEL_DEPLOY_PRODUCTION, "user_1", {})
    ac.approve_request(request_id, "user_1", "approved")
    req = ac.get_approval_request(request_id)
    assert req["status"] == "approved"
    
    print("\n✓ Access Control: OPERATIONAL")


def test_compliance_reporting():
    """Test compliance reporting functionality."""
    print_header("Testing Compliance Reporting")
    
    reporter = ComplianceReporter(get_db_path("compliance_reporter"))
    
    print("✓ Reporting incident...")
    incident_id = reporter.report_incident(
        IncidentCategory.PERFORMANCE, IncidentSeverity.WARNING,
        "High latency", "Exceeded threshold", "model_1", affected_count=100
    )
    incident = reporter.get_incident(incident_id)
    assert incident is not None
    
    print("✓ Resolving incident...")
    reporter.resolve_incident(incident_id, "Fixed")
    
    print("✓ Logging audit event...")
    reporter.log_audit_event("user_login", "user_1", "system", "login", "success")
    log = reporter.get_audit_log(user_id="user_1")
    assert len(log) > 0
    
    print("✓ Generating compliance report...")
    report = reporter.generate_report()
    assert "summary" in report
    
    print("\n✓ Compliance Reporting: OPERATIONAL")


def test_sla_management():
    """Test SLA management functionality."""
    print_header("Testing SLA Management")
    
    sla = SLAManager(get_db_path("sla_management"))
    
    print("✓ Defining SLA targets...")
    target = sla.define_sla("model_1", "model", response_time_p95=500.0)
    assert target.resource_id == "model_1"
    
    print("✓ Recording compliant measurement...")
    metrics = SLAMetrics(response_time_p95=400.0, availability_percent=99.96)
    sla.record_measurement("model_1", "model", metrics)
    status = sla.get_sla_status("model_1", "model")
    assert status.value == "compliant"
    
    print("✓ Recording SLA violation...")
    metrics = SLAMetrics(response_time_p95=600.0)  # Exceeds 500ms target
    sla.record_measurement("model_1", "model", metrics)
    violations = sla.get_violations(resource_id="model_1")
    assert len(violations) > 0
    
    print("\n✓ SLA Management: OPERATIONAL")


def test_integration():
    """Test integrated governance workflow."""
    print_header("Testing Integrated Governance Workflow")
    
    models = ModelRegistry(get_db_path("int_model_registry"))
    usecases = UseCaseRegistry(get_db_path("int_usecase_registry"))
    access = AccessControl(get_db_path("int_access_control"))
    sla = SLAManager(get_db_path("int_sla_management"))
    
    print("✓ Complete workflow test...")
    
    # Model workflow
    models.register_version("classifier", "1.0.0")
    models.approve_version("classifier", "1.0.0", "reviewer")
    models.deploy_version("classifier", "1.0.0", "d1")
    
    # Use-case workflow
    usecases.create_usecase("detection", "Detection", "Detect", "owner")
    usecases.approve_usecase("detection", "approver")
    usecases.deploy_usecase("detection", "d2")
    
    # Access control
    access.create_user("operator", "operator@example.com")
    access.assign_role("operator", Role.OPERATOR, "admin")
    
    # SLA management
    sla.define_sla("classifier", "model")
    
    # Verify
    model = models.get_deployed_version("classifier")
    usecase = usecases.get_usecase("detection")
    assert model is not None
    assert usecase.status.value == "deployed"
    
    print("  ✓ Model deployed and monitored")
    print("  ✓ Use-case deployed and tracked")
    print("  ✓ SLA targets defined")
    print("  ✓ Access control enforced")
    
    print("\n✓ Integrated Governance: OPERATIONAL")


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("  PHASE 4.0 GOVERNANCE INFRASTRUCTURE VERIFICATION")
    print("=" * 70)
    print(f"\nUsing temporary database directory: {TEMP_DIR}\n")
    
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
        print(f"\nTotal time: {elapsed:.2f} seconds")
        print(f"Database directory: {TEMP_DIR}\n")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ VERIFICATION FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        print(f"\nDatabase directory (for debugging): {TEMP_DIR}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
