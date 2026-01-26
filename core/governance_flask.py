"""
Governance System Flask Integration.

Provides REST API endpoints for:
- Model registry management
- Use-case registry management
- Access control and RBAC
- Compliance reporting
- SLA management
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
import logging
import time
from typing import Any, Dict, Optional

from core.governance.access_control import AccessControl, Permission, Role
from core.governance.compliance_reporting import ComplianceReporter, IncidentCategory, IncidentSeverity
from core.governance.model_registry import ModelRegistry, DeploymentStatus, ApprovalStatus
from core.governance.sla_management import SLAManager, SLAMetrics
from core.governance.use_case_registry import UseCaseRegistry, UseCaseStatus, ImpactLevel

logger = logging.getLogger(__name__)


def create_governance_blueprint(
    model_registry: Optional[ModelRegistry] = None,
    usecase_registry: Optional[UseCaseRegistry] = None,
    access_control: Optional[AccessControl] = None,
    compliance_reporter: Optional[ComplianceReporter] = None,
    sla_manager: Optional[SLAManager] = None,
) -> Blueprint:
    """
    Create governance API blueprint.
    
    Args:
        model_registry: Model registry instance
        usecase_registry: Use-case registry instance
        access_control: Access control instance
        compliance_reporter: Compliance reporter instance
        sla_manager: SLA manager instance
    
    Returns:
        Flask blueprint with governance endpoints
    """
    
    bp = Blueprint('governance', __name__, url_prefix='/api/governance')
    
    # Initialize registries if not provided
    _model_registry = model_registry or ModelRegistry()
    _usecase_registry = usecase_registry or UseCaseRegistry()
    _access_control = access_control or AccessControl()
    _compliance_reporter = compliance_reporter or ComplianceReporter()
    _sla_manager = sla_manager or SLAManager()
    
    # ==================
    # Model Registry Endpoints
    # ==================
    
    @bp.route('/models/register', methods=['POST'])
    def register_model() -> ResponseReturnValue:
        """Register a new model version."""
        try:
            data = request.get_json() or {}
            
            model = _model_registry.register_version(
                model_id=data['model_id'],
                version=data['version'],
                description=data.get('description', ''),
                source_commit=data.get('source_commit'),
                training_data_hash=data.get('training_data_hash'),
                hyperparameters=data.get('hyperparameters'),
                model_path=data.get('model_path', ''),
                model_size_bytes=data.get('model_size_bytes', 0),
                artifacts=data.get('artifacts'),
            )
            
            return jsonify(model.to_dict()), 201
        except Exception as e:
            logger.error(f"Error registering model: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/models/<model_id>/versions', methods=['GET'])
    def list_model_versions(model_id: str) -> ResponseReturnValue:
        """List model versions."""
        try:
            versions = _model_registry.list_versions(model_id)
            return jsonify({
                "model_id": model_id,
                "versions": [v.to_dict() for v in versions],
                "count": len(versions),
            }), 200
        except Exception as e:
            logger.error(f"Error listing model versions: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/models/<model_id>/versions/<version>/approve', methods=['POST'])
    def approve_model_version(model_id: str, version: str) -> ResponseReturnValue:
        """Approve a model version."""
        try:
            data = request.get_json() or {}
            approved_by = data.get('approved_by', 'system')
            comments = data.get('comments', '')
            
            result = _model_registry.approve_version(
                model_id, version, approved_by, comments
            )
            
            if result:
                model = _model_registry.get_version(model_id, version)
                if not model:
                    return jsonify({"error": "Model not found"}), 404
                return jsonify(model.to_dict()), 200
            else:
                return jsonify({"error": "Model not found"}), 404
        except Exception as e:
            logger.error(f"Error approving model: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/models/<model_id>/versions/<version>/deploy', methods=['POST'])
    def deploy_model_version(model_id: str, version: str) -> ResponseReturnValue:
        """Deploy a model version."""
        try:
            data = request.get_json() or {}
            deployment_id = data.get('deployment_id', f"{model_id}_{version}_{int(time.time())}")
            environment = data.get('environment', 'production')
            deployed_by = data.get('deployed_by', 'system')
            
            result = _model_registry.deploy_version(
                model_id, version, deployment_id, environment, deployed_by
            )
            
            if result:
                model = _model_registry.get_version(model_id, version)
                if not model:
                    return jsonify({"error": "Model not found or not approved"}), 400
                return jsonify(model.to_dict()), 200
            else:
                return jsonify({"error": "Model not found or not approved"}), 400
        except Exception as e:
            logger.error(f"Error deploying model: {e}")
            return jsonify({"error": str(e)}), 400
    
    # ==================
    # Use-Case Registry Endpoints
    # ==================
    
    @bp.route('/usecases/create', methods=['POST'])
    def create_usecase() -> ResponseReturnValue:
        """Create a new use-case."""
        try:
            data = request.get_json() or {}
            
            usecase = _usecase_registry.create_usecase(
                usecase_id=data['usecase_id'],
                name=data['name'],
                description=data['description'],
                owner=data['owner'],
                model_ids=data.get('model_ids'),
                input_schema=data.get('input_schema'),
                output_schema=data.get('output_schema'),
                impact_level=ImpactLevel(data.get('impact_level', 'medium')),
                affected_systems=data.get('affected_systems'),
                dependencies=data.get('dependencies'),
            )
            
            return jsonify(usecase.to_dict()), 201
        except Exception as e:
            logger.error(f"Error creating use-case: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/usecases/<usecase_id>', methods=['GET'])
    def get_usecase(usecase_id: str) -> ResponseReturnValue:
        """Get use-case details."""
        try:
            usecase = _usecase_registry.get_usecase(usecase_id)
            if not usecase:
                return jsonify({"error": "Use-case not found"}), 404
            
            return jsonify(usecase.to_dict()), 200
        except Exception as e:
            logger.error(f"Error getting use-case: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/usecases/<usecase_id>/approve', methods=['POST'])
    def approve_usecase(usecase_id: str) -> ResponseReturnValue:
        """Approve a use-case."""
        try:
            data = request.get_json() or {}
            approved_by = data.get('approved_by', 'system')
            comments = data.get('comments', '')
            
            result = _usecase_registry.approve_usecase(usecase_id, approved_by, comments)
            
            if result:
                usecase = _usecase_registry.get_usecase(usecase_id)
                if not usecase:
                    return jsonify({"error": "Use-case not found"}), 404
                return jsonify(usecase.to_dict()), 200
            else:
                return jsonify({"error": "Use-case not found"}), 404
        except Exception as e:
            logger.error(f"Error approving use-case: {e}")
            return jsonify({"error": str(e)}), 400
    
    # ==================
    # Access Control Endpoints
    # ==================
    
    @bp.route('/users/create', methods=['POST'])
    def create_user() -> ResponseReturnValue:
        """Create a new user."""
        try:
            data = request.get_json() or {}
            
            result = _access_control.create_user(
                user_id=data['user_id'],
                email=data['email'],
                metadata=data.get('metadata'),
            )
            
            if result:
                return jsonify({"user_id": data['user_id'], "created": True}), 201
            else:
                return jsonify({"error": "User already exists"}), 409
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/users/<user_id>/roles', methods=['GET'])
    def get_user_roles(user_id: str) -> ResponseReturnValue:
        """Get user roles."""
        try:
            roles = _access_control.get_user_roles(user_id)
            return jsonify({
                "user_id": user_id,
                "roles": [r.value for r in roles],
            }), 200
        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/users/<user_id>/roles/<role>/assign', methods=['POST'])
    def assign_user_role(user_id: str, role: str) -> ResponseReturnValue:
        """Assign role to user."""
        try:
            data = request.get_json() or {}
            assigned_by = data.get('assigned_by', 'system')
            
            result = _access_control.assign_role(
                user_id, Role(role), assigned_by
            )
            
            if result:
                return jsonify({"user_id": user_id, "role": role, "assigned": True}), 200
            else:
                return jsonify({"error": "User not found"}), 404
        except Exception as e:
            logger.error(f"Error assigning role: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/users/<user_id>/permissions/<permission>', methods=['GET'])
    def check_permission(user_id: str, permission: str) -> ResponseReturnValue:
        """Check if user has permission."""
        try:
            has_perm = _access_control.has_permission(
                user_id, Permission(permission)
            )
            
            return jsonify({
                "user_id": user_id,
                "permission": permission,
                "granted": has_perm,
            }), 200
        except Exception as e:
            logger.error(f"Error checking permission: {e}")
            return jsonify({"error": str(e)}), 400
    
    # ==================
    # Compliance Reporting Endpoints
    # ==================
    
    @bp.route('/incidents/report', methods=['POST'])
    def report_incident() -> ResponseReturnValue:
        """Report an incident."""
        try:
            data = request.get_json() or {}
            
            incident_id = _compliance_reporter.report_incident(
                category=IncidentCategory(data['category']),
                severity=IncidentSeverity(data['severity']),
                title=data['title'],
                description=data['description'],
                resource=data['resource'],
                affected_count=data.get('affected_count', 0),
                metadata=data.get('metadata'),
            )
            
            return jsonify({"incident_id": incident_id, "reported": True}), 201
        except Exception as e:
            logger.error(f"Error reporting incident: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/incidents', methods=['GET'])
    def list_incidents() -> ResponseReturnValue:
        """List incidents."""
        try:
            severity = request.args.get('severity')
            resource = request.args.get('resource')
            
            incidents = _compliance_reporter.list_incidents(
                severity=IncidentSeverity(severity) if severity else None,
                resource=resource,
                resolved_only=request.args.get('resolved', '').lower() == 'true',
            )
            
            return jsonify({
                "incidents": [i.to_dict() for i in incidents],
                "count": len(incidents),
            }), 200
        except Exception as e:
            logger.error(f"Error listing incidents: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/compliance/report', methods=['GET'])
    def get_compliance_report() -> ResponseReturnValue:
        """Get compliance report."""
        try:
            period_days = request.args.get('period_days', 30, type=int)
            
            report = _compliance_reporter.generate_report(
                report_type="on_demand",
                period_days=period_days,
            )
            
            return jsonify(report), 200
        except Exception as e:
            logger.error(f"Error generating compliance report: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/audit-log', methods=['GET'])
    def get_audit_log() -> ResponseReturnValue:
        """Get audit log."""
        try:
            user_id = request.args.get('user_id')
            limit = request.args.get('limit', 100, type=int)
            
            log_entries = _compliance_reporter.get_audit_log(
                user_id=user_id,
                limit=limit,
            )
            
            return jsonify({
                "entries": log_entries,
                "count": len(log_entries),
            }), 200
        except Exception as e:
            logger.error(f"Error getting audit log: {e}")
            return jsonify({"error": str(e)}), 400
    
    # ==================
    # SLA Management Endpoints
    # ==================
    
    @bp.route('/sla/<resource_type>/<resource_id>/define', methods=['POST'])
    def define_sla(resource_type: str, resource_id: str) -> ResponseReturnValue:
        """Define SLA for a resource."""
        try:
            data = request.get_json() or {}
            
            target = _sla_manager.define_sla(
                resource_id=resource_id,
                resource_type=resource_type,
                response_time_p95=data.get('response_time_p95', 500.0),
                response_time_p99=data.get('response_time_p99', 1000.0),
                availability_target=data.get('availability_target', 99.9),
                error_rate_target=data.get('error_rate_target', 0.1),
                incident_response_minutes=data.get('incident_response_minutes', 15),
                incident_resolution_hours=data.get('incident_resolution_hours', 4),
            )
            
            return jsonify({
                "resource_id": resource_id,
                "resource_type": resource_type,
                "target": {
                    "response_time_p95_ms": target.response_time_p95_target,
                    "response_time_p99_ms": target.response_time_p99_target,
                    "availability_percent": target.availability_target,
                    "error_rate_percent": target.error_rate_target,
                },
            }), 201
        except Exception as e:
            logger.error(f"Error defining SLA: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/sla/<resource_type>/<resource_id>/status', methods=['GET'])
    def get_sla_status(resource_type: str, resource_id: str) -> ResponseReturnValue:
        """Get SLA status."""
        try:
            hours = request.args.get('hours', 24, type=int)
            
            status = _sla_manager.get_sla_status(resource_id, resource_type, hours)
            
            return jsonify({
                "resource_id": resource_id,
                "resource_type": resource_type,
                "status": status.value,
                "period_hours": hours,
            }), 200
        except Exception as e:
            logger.error(f"Error getting SLA status: {e}")
            return jsonify({"error": str(e)}), 400
    
    @bp.route('/sla/<resource_type>/<resource_id>/violations', methods=['GET'])
    def get_sla_violations(resource_type: str, resource_id: str) -> ResponseReturnValue:
        """Get SLA violations."""
        try:
            hours = request.args.get('hours', 24, type=int)
            
            violations = _sla_manager.get_violations(
                resource_id=resource_id,
                hours=hours,
            )
            
            return jsonify({
                "resource_id": resource_id,
                "violations": violations,
                "count": len(violations),
            }), 200
        except Exception as e:
            logger.error(f"Error getting SLA violations: {e}")
            return jsonify({"error": str(e)}), 400
    
    # ==================
    # Health Check
    # ==================
    
    @bp.route('/health', methods=['GET'])
    def governance_health() -> ResponseReturnValue:
        """Health check for governance system."""
        return jsonify({
            "status": "healthy",
            "components": {
                "model_registry": "operational",
                "usecase_registry": "operational",
                "access_control": "operational",
                "compliance_reporter": "operational",
                "sla_manager": "operational",
            },
        }), 200
    
    return bp


# Helper function to register with existing Flask app
def register_governance_api(app, **kwargs) -> None:
    """
    Register governance API with Flask app.
    
    Args:
        app: Flask application instance
        **kwargs: Registries to use (model_registry, usecase_registry, etc.)
    """
    bp = create_governance_blueprint(**kwargs)
    app.register_blueprint(bp)
    logger.info("Governance API registered")


