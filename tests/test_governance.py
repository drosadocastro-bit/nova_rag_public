"""
Comprehensive Test Suite for Governance System.

Tests all governance components including:
- Model registry (versioning, approval, deployment)
- Use-case registry (lifecycle, approval, metrics)
- Access control (RBAC, permissions, audit)
- Compliance reporting (incidents, audits, reports)
- SLA management (targets, measurements, violations)
"""

import pytest
import time
import tempfile
import os
from pathlib import Path

from core.governance.model_registry import (
    ModelRegistry, ModelVersion, DeploymentStatus, ApprovalStatus,
    PerformanceMetrics
)
from core.governance.use_case_registry import (
    UseCaseRegistry, UseCase, UseCaseStatus, ImpactLevel, UseCaseMetrics
)
from core.governance.access_control import (
    AccessControl, Role, Permission, ApprovalAction, ApprovalWorkflow
)
from core.governance.compliance_reporting import (
    ComplianceReporter, IncidentCategory, IncidentSeverity, IncidentReport
)
from core.governance.sla_management import (
    SLAManager, SLAMetrics, SLATarget, SLAStatus
)


# ==================
# Model Registry Tests
# ==================

class TestModelRegistry:
    """Tests for model registry."""
    
    @pytest.fixture
    def registry(self):
        """Create temporary model registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "models.db")
            reg = ModelRegistry(db_path)
            yield reg
            reg.close()  # Release file locks before tempdir cleanup
    
    def test_register_model_version(self, registry):
        """Test registering a model version."""
        model = registry.register_version(
            model_id="vehicle_classifier_v1",
            version="1.0.0",
            description="Vehicle type classifier",
            source_commit="abc123",
        )
        
        assert model.model_id == "vehicle_classifier_v1"
        assert model.version == "1.0.0"
        assert model.status == DeploymentStatus.REGISTERED
        assert model.approval_status == ApprovalStatus.PENDING
    
    def test_get_model_version(self, registry):
        """Test retrieving a model version."""
        registry.register_version("test_model", "1.0.0", "Test model")
        
        model = registry.get_version("test_model", "1.0.0")
        assert model is not None
        assert model.model_id == "test_model"
        assert model.version == "1.0.0"
    
    def test_approval_workflow(self, registry):
        """Test model approval workflow."""
        registry.register_version("test_model", "1.0.0", "Test model")
        
        # Request approval
        result = registry.request_approval("test_model", "1.0.0", "Ready for review")
        assert result is True
        
        # Approve
        result = registry.approve_version("test_model", "1.0.0", "reviewer_1")
        assert result is True
        
        model = registry.get_version("test_model", "1.0.0")
        assert model.approval_status == ApprovalStatus.APPROVED
        assert model.approved_by == "reviewer_1"
    
    def test_deployment_workflow(self, registry):
        """Test model deployment workflow."""
        registry.register_version("test_model", "1.0.0")
        registry.approve_version("test_model", "1.0.0", "reviewer")
        
        # Deploy to staging
        result = registry.deploy_version(
            "test_model", "1.0.0", "deploy_1", "staging", "operator"
        )
        assert result is True
        
        model = registry.get_version("test_model", "1.0.0")
        assert model.status == DeploymentStatus.DEPLOYED_STAGING
        assert model.deployment_id == "deploy_1"
        assert model.deployed_by == "operator"
    
    def test_rollback(self, registry):
        """Test model rollback."""
        registry.register_version("test_model", "1.0.0")
        registry.approve_version("test_model", "1.0.0", "reviewer")
        registry.deploy_version("test_model", "1.0.0", "deploy_1", "production")
        
        # Rollback
        result = registry.rollback_version(
            "test_model", "1.0.0", "Critical bug found", "operator"
        )
        assert result is True
        
        model = registry.get_version("test_model", "1.0.0")
        assert model.status == DeploymentStatus.ROLLED_BACK
        assert "Critical bug" in model.rollback_reason
    
    def test_performance_metrics(self, registry):
        """Test updating performance metrics."""
        registry.register_version("test_model", "1.0.0")
        
        metrics = PerformanceMetrics(
            accuracy=0.95,
            precision=0.94,
            recall=0.96,
            f1_score=0.95,
            latency_ms=50.0,
            throughput_qps=200.0,
        )
        
        result = registry.update_metrics("test_model", "1.0.0", metrics)
        assert result is True
        
        model = registry.get_version("test_model", "1.0.0")
        assert model.metrics.accuracy == 0.95
        assert model.metrics.latency_ms == 50.0
    
    def test_list_versions(self, registry):
        """Test listing model versions."""
        registry.register_version("model_1", "1.0.0")
        registry.register_version("model_1", "1.1.0")
        registry.register_version("model_1", "2.0.0")
        
        versions = registry.list_versions("model_1")
        assert len(versions) == 3
        assert versions[0].version in ["2.0.0", "1.1.0", "1.0.0"]  # Order may vary


# ==================
# Use-Case Registry Tests
# ==================

class TestUseCaseRegistry:
    """Tests for use-case registry."""
    
    @pytest.fixture
    def registry(self):
        """Create temporary use-case registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "usecases.db")
            yield UseCaseRegistry(db_path)
    
    def test_create_usecase(self, registry):
        """Test creating a use-case."""
        usecase = registry.create_usecase(
            usecase_id="vehicle_detection",
            name="Vehicle Detection",
            description="Detect vehicles in images",
            owner="team_a",
            impact_level=ImpactLevel.HIGH,
        )
        
        assert usecase.usecase_id == "vehicle_detection"
        assert usecase.status == UseCaseStatus.DRAFT
        assert usecase.owner == "team_a"
    
    def test_usecase_approval_workflow(self, registry):
        """Test use-case approval workflow."""
        registry.create_usecase("uc_1", "UC 1", "Desc", "owner_1")
        
        # Submit for approval
        result = registry.submit_for_approval("uc_1", "Ready for review")
        assert result is True
        
        usecase = registry.get_usecase("uc_1")
        assert usecase.status == UseCaseStatus.SUBMITTED
        
        # Approve
        result = registry.approve_usecase("uc_1", "approver_1", "Looks good")
        assert result is True
        
        usecase = registry.get_usecase("uc_1")
        assert usecase.status == UseCaseStatus.APPROVED
        assert usecase.approved_by == "approver_1"
    
    def test_usecase_deployment(self, registry):
        """Test use-case deployment."""
        registry.create_usecase("uc_1", "UC 1", "Desc", "owner_1")
        registry.approve_usecase("uc_1", "approver_1")
        
        result = registry.deploy_usecase("uc_1", "deploy_1", "production", "operator_1")
        assert result is True
        
        usecase = registry.get_usecase("uc_1")
        assert usecase.status == UseCaseStatus.DEPLOYED
        assert usecase.deployed_at is not None
    
    def test_usecase_deprecation(self, registry):
        """Test use-case deprecation."""
        registry.create_usecase("uc_1", "UC 1", "Desc", "owner_1")
        
        result = registry.deprecate_usecase("uc_1", "admin", "Replaced by v2")
        assert result is True
        
        usecase = registry.get_usecase("uc_1")
        assert usecase.status == UseCaseStatus.DEPRECATED
    
    def test_usecase_metrics(self, registry):
        """Test updating use-case metrics."""
        registry.create_usecase("uc_1", "UC 1", "Desc", "owner_1")
        
        metrics = UseCaseMetrics(
            deployments=3,
            total_queries=50000,
            average_latency_ms=100.0,
            error_rate=0.1,
        )
        
        result = registry.update_metrics("uc_1", metrics)
        assert result is True
        
        usecase = registry.get_usecase("uc_1")
        assert usecase.metrics.total_queries == 50000
        assert usecase.metrics.average_latency_ms == 100.0


# ==================
# Access Control Tests
# ==================

class TestAccessControl:
    """Tests for access control system."""
    
    @pytest.fixture
    def ac(self):
        """Create temporary access control."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "access.db")
            yield AccessControl(db_path)
    
    def test_create_user(self, ac):
        """Test creating a user."""
        result = ac.create_user("user_1", "user1@example.com")
        assert result is True
        
        # Creating same user twice fails
        result = ac.create_user("user_1", "user1@example.com")
        assert result is False
    
    def test_assign_role(self, ac):
        """Test assigning roles."""
        ac.create_user("user_1", "user1@example.com")
        
        result = ac.assign_role("user_1", Role.OPERATOR, "admin")
        assert result is True
        
        roles = ac.get_user_roles("user_1")
        assert Role.OPERATOR in roles
    
    def test_permission_check(self, ac):
        """Test permission checking."""
        ac.create_user("user_1", "user1@example.com")
        ac.assign_role("user_1", Role.OPERATOR, "admin")
        
        # Operator has MODEL_DEPLOY permission
        result = ac.has_permission("user_1", Permission.MODEL_DEPLOY)
        assert result is True
        
        # Operator doesn't have ROLE_MANAGE permission
        result = ac.has_permission("user_1", Permission.ROLE_MANAGE)
        assert result is False
    
    def test_admin_permissions(self, ac):
        """Test admin role permissions."""
        ac.create_user("admin_user", "admin@example.com")
        ac.assign_role("admin_user", Role.ADMIN, "system")
        
        # Admin has all permissions
        assert ac.has_permission("admin_user", Permission.MODEL_DEPLOY)
        assert ac.has_permission("admin_user", Permission.USER_MANAGE)
        assert ac.has_permission("admin_user", Permission.SYSTEM_SHUTDOWN)
    
    def test_approval_request(self, ac):
        """Test approval request workflow."""
        ac.create_user("requester", "requester@example.com")
        ac.create_user("approver", "approver@example.com")
        
        ac.assign_role("approver", Role.APPROVER, "admin")
        
        # Request approval
        request_id = ac.request_approval(
            ApprovalAction.MODEL_DEPLOY_PRODUCTION,
            "requester",
            {"model_id": "m1", "version": "1.0.0"}
        )
        
        assert request_id is not None
        
        # Approve
        result = ac.approve_request(request_id, "approver", "approved")
        assert result is True
        
        # Check status
        req = ac.get_approval_request(request_id)
        assert req["status"] == "approved"
        assert len(req["approvals"]) > 0


# ==================
# Compliance Reporting Tests
# ==================

class TestComplianceReporter:
    """Tests for compliance reporting."""
    
    @pytest.fixture
    def reporter(self):
        """Create temporary compliance reporter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "compliance.db")
            yield ComplianceReporter(db_path)
    
    def test_report_incident(self, reporter):
        """Test reporting an incident."""
        incident_id = reporter.report_incident(
            category=IncidentCategory.PERFORMANCE,
            severity=IncidentSeverity.WARNING,
            title="High latency detected",
            description="Response times exceeded 1 second",
            resource="model_1",
            affected_count=100,
        )
        
        assert incident_id is not None
        
        incident = reporter.get_incident(incident_id)
        assert incident is not None
        assert incident.title == "High latency detected"
        assert incident.severity == IncidentSeverity.WARNING
    
    def test_resolve_incident(self, reporter):
        """Test resolving an incident."""
        incident_id = reporter.report_incident(
            IncidentCategory.PERFORMANCE,
            IncidentSeverity.ERROR,
            "Critical error",
            "System failed",
            "system",
        )
        
        result = reporter.resolve_incident(incident_id, "Fixed database connection")
        assert result is True
        
        incident = reporter.get_incident(incident_id)
        assert incident.resolved_at is not None
        assert "Fixed database" in incident.resolution
    
    def test_list_incidents(self, reporter):
        """Test listing incidents."""
        reporter.report_incident(
            IncidentCategory.SAFETY,
            IncidentSeverity.CRITICAL,
            "Safety violation",
            "Desc",
            "model_1",
        )
        
        reporter.report_incident(
            IncidentCategory.PERFORMANCE,
            IncidentSeverity.WARNING,
            "Perf warning",
            "Desc",
            "model_2",
        )
        
        # Get all open
        incidents = reporter.list_incidents()
        assert len(incidents) == 2
        
        # Filter by severity
        critical = reporter.list_incidents(severity=IncidentSeverity.CRITICAL)
        assert len(critical) == 1
    
    def test_audit_logging(self, reporter):
        """Test audit event logging."""
        reporter.log_audit_event(
            "user_login",
            "user_1",
            "system",
            "login",
            "success",
            "Login from 192.168.1.1"
        )
        
        log_entries = reporter.get_audit_log(user_id="user_1")
        assert len(log_entries) == 1
        assert log_entries[0]["event_type"] == "user_login"
    
    def test_compliance_report(self, reporter):
        """Test generating compliance report."""
        # Create some incidents
        for i in range(5):
            reporter.report_incident(
                IncidentCategory.SAFETY if i < 2 else IncidentCategory.PERFORMANCE,
                IncidentSeverity.WARNING,
                f"Incident {i}",
                "Desc",
                f"resource_{i}",
            )
        
        report = reporter.generate_report(period_days=30)
        
        assert "summary" in report
        assert report["summary"]["total_incidents"] == 5
        assert report["summary"]["violations"]["safety"] == 2


# ==================
# SLA Management Tests
# ==================

class TestSLAManager:
    """Tests for SLA management."""
    
    @pytest.fixture
    def sla_manager(self):
        """Create temporary SLA manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "sla.db")
            yield SLAManager(db_path)
    
    def test_define_sla(self, sla_manager):
        """Test defining SLA targets."""
        target = sla_manager.define_sla(
            resource_id="model_1",
            resource_type="model",
            response_time_p95=500.0,
            response_time_p99=1000.0,
            availability_target=99.9,
            error_rate_target=0.1,
        )
        
        assert target.resource_id == "model_1"
        assert target.response_time_p95_target == 500.0
        assert target.maximum_downtime_hours_monthly > 0
    
    def test_get_sla_target(self, sla_manager):
        """Test retrieving SLA targets."""
        sla_manager.define_sla("model_1", "model")
        
        target = sla_manager.get_sla_target("model_1", "model")
        assert target is not None
        assert target.response_time_p95_target == 500.0
    
    def test_record_compliant_measurement(self, sla_manager):
        """Test recording SLA-compliant measurement."""
        sla_manager.define_sla("model_1", "model")
        
        metrics = SLAMetrics(
            response_time_p95=400.0,  # Below target
            response_time_p99=900.0,  # Below target
            availability_percent=99.95,  # Above target
            error_rate=0.05,  # Below target
        )
        
        sla_manager.record_measurement("model_1", "model", metrics)
        
        status = sla_manager.get_sla_status("model_1", "model")
        assert status == SLAStatus.COMPLIANT
    
    def test_record_violated_measurement(self, sla_manager):
        """Test recording SLA violations."""
        sla_manager.define_sla("model_1", "model")
        
        metrics = SLAMetrics(
            response_time_p95=600.0,  # Exceeds target of 500
            availability_percent=99.8,  # Below target of 99.9
        )
        
        sla_manager.record_measurement("model_1", "model", metrics)
        
        violations = sla_manager.get_violations(resource_id="model_1")
        assert len(violations) > 0
        assert any(v["violation_type"] == "response_time_p95" for v in violations)
    
    def test_acknowledge_violation(self, sla_manager):
        """Test acknowledging violations."""
        sla_manager.define_sla("model_1", "model")
        
        metrics = SLAMetrics(response_time_p95=600.0)
        sla_manager.record_measurement("model_1", "model", metrics)
        
        violations = sla_manager.get_violations(resource_id="model_1")
        violation_id = violations[0]["id"]
        
        result = sla_manager.acknowledge_violation(
            violation_id, "operator", "Investigating issue"
        )
        assert result is True


# ==================
# Integration Tests
# ==================

class TestGovernanceIntegration:
    """Integration tests across governance components."""
    
    @pytest.fixture
    def governance_suite(self):
        """Create complete governance suite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield {
                "models": ModelRegistry(os.path.join(tmpdir, "models.db")),
                "usecases": UseCaseRegistry(os.path.join(tmpdir, "usecases.db")),
                "access": AccessControl(os.path.join(tmpdir, "access.db")),
                "compliance": ComplianceReporter(os.path.join(tmpdir, "compliance.db")),
                "sla": SLAManager(os.path.join(tmpdir, "sla.db")),
            }
    
    def test_complete_workflow(self, governance_suite):
        """Test complete governance workflow."""
        models = governance_suite["models"]
        usecases = governance_suite["usecases"]
        access = governance_suite["access"]
        sla = governance_suite["sla"]
        
        # 1. Create and approve model
        models.register_version("model_1", "1.0.0", "Test model")
        models.approve_version("model_1", "1.0.0", "reviewer")
        models.deploy_version("model_1", "1.0.0", "deploy_1")
        
        # 2. Create and approve use-case
        usecases.create_usecase("uc_1", "Use case 1", "Desc", "owner")
        usecases.approve_usecase("uc_1", "approver")
        usecases.deploy_usecase("uc_1", "deploy_1")
        
        # 3. Set up access control
        access.create_user("operator", "operator@example.com")
        access.assign_role("operator", Role.OPERATOR, "admin")
        assert access.has_permission("operator", Permission.MODEL_DEPLOY)
        
        # 4. Define SLAs
        sla.define_sla("model_1", "model")
        target = sla.get_sla_target("model_1", "model")
        assert target is not None
        
        # All components working together
        assert models.get_deployed_version("model_1") is not None
        assert usecases.get_usecase("uc_1").status == UseCaseStatus.DEPLOYED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
