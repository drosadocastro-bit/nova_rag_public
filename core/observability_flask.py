"""
Flask Integration for Observability

Integrates observability components into Flask application:
- Metrics middleware
- Observability API endpoints
- Dashboard integration
- Prometheus metrics endpoint
"""

import time
import uuid
from functools import wraps
from typing import Optional, Dict, Any

from flask import Blueprint, request, jsonify, render_template_string, g
import logging

logger = logging.getLogger(__name__)


def create_observability_middleware(observability_manager, app=None):
    """
    Create Flask middleware for automatic metrics collection.
    
    Args:
        observability_manager: Instance of ObservabilityManager
        app: Flask application (optional)
    """
    
    def before_request():
        """Track request start time."""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()
        g.start_memory = 0  # Would get actual memory if psutil available
    
    def after_request(response):
        """Record metrics after request."""
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000  # Convert to ms
            
            # Record basic request metric
            observability_manager.metrics.record(
                "http_request_duration_ms",
                duration,
                {"method": request.method, "path": request.path, "status": response.status_code}
            )
        
        return response
    
    if app:
        app.before_request(before_request)
        app.after_request(after_request)
    
    return before_request, after_request


def create_observability_blueprint(observability_manager, notification_manager=None):
    """
    Create Flask blueprint for observability endpoints.
    
    Args:
        observability_manager: Instance of ObservabilityManager
        notification_manager: Instance of NotificationManager (optional)
    
    Returns:
        Flask Blueprint
    """
    
    obs_bp = Blueprint('observability', __name__, url_prefix='/api/observability')
    
    @obs_bp.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "timestamp": time.time(),
            "service": "nova-nic",
        })
    
    @obs_bp.route('/metrics', methods=['GET'])
    def metrics_prometheus():
        """Prometheus metrics endpoint."""
        return observability_manager.get_prometheus_metrics(), 200, {
            'Content-Type': 'text/plain'
        }
    
    @obs_bp.route('/metrics/json', methods=['GET'])
    def metrics_json():
        """JSON format metrics endpoint."""
        return jsonify(observability_manager.metrics.get_summary())
    
    @obs_bp.route('/dashboard', methods=['GET'])
    def dashboard_data():
        """Dashboard data endpoint."""
        data = observability_manager.get_dashboard_data()
        
        # Convert alerts to serializable format
        if 'active_alerts' in data:
            data['active_alerts'] = [
                a.to_dict() if hasattr(a, 'to_dict') else a
                for a in data['active_alerts']
            ]
        
        return jsonify(data)
    
    @obs_bp.route('/queries', methods=['GET'])
    def get_queries():
        """Get recent query logs."""
        limit = request.args.get('limit', default=50, type=int)
        queries = observability_manager.audit_log.search_logs(log_type="query", limit=limit)
        return jsonify(queries)
    
    @obs_bp.route('/events', methods=['GET'])
    def get_events():
        """Get recent events."""
        event_type = request.args.get('type', default=None, type=str)
        limit = request.args.get('limit', default=100, type=int)
        events = observability_manager.audit_log.search_logs(log_type=event_type, limit=limit)
        return jsonify(events)
    
    @obs_bp.route('/alerts', methods=['GET'])
    def get_alerts():
        """Get active alerts."""
        alerts = observability_manager.alert_manager.get_active_alerts()
        return jsonify({
            "active": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
            "stats": observability_manager.alert_manager.get_stats(),
        })
    
    @obs_bp.route('/alerts/rules', methods=['GET'])
    def get_alert_rules():
        """Get all alert rules."""
        rules = observability_manager.alert_manager.rules
        return jsonify({
            "count": len(rules),
            "rules": [
                {
                    "name": r.name,
                    "description": r.description,
                    "metric_name": r.metric_name,
                    "operator": r.operator,
                    "threshold": r.threshold,
                    "severity": r.severity.value,
                    "enabled": r.enabled,
                    "triggered": r.trigger_count,
                }
                for r in rules.values()
            ],
        })
    
    @obs_bp.route('/alerts/rules', methods=['POST'])
    def create_alert_rule():
        """Create new alert rule."""
        data = request.get_json()
        
        from core.observability import AlertRule, AlertSeverity
        
        rule = AlertRule(
            name=data.get('name'),
            description=data.get('description'),
            metric_name=data.get('metric_name'),
            operator=data.get('operator'),
            threshold=data.get('threshold'),
            severity=AlertSeverity(data.get('severity', 'warning')),
            enabled=data.get('enabled', True),
            cooldown_seconds=data.get('cooldown_seconds', 300),
        )
        
        observability_manager.alert_manager.add_rule(rule)
        
        return jsonify({
            "status": "created",
            "rule": data,
        }), 201
    
    @obs_bp.route('/notifications', methods=['GET'])
    def get_notifications():
        """Get recent notifications."""
        if notification_manager is None:
            return jsonify({"error": "Notification manager not available"}), 503
        
        limit = request.args.get('limit', default=50, type=int)
        notifications = notification_manager.get_recent_notifications(limit)
        
        return jsonify({
            "count": len(notifications),
            "notifications": notifications,
        })
    
    @obs_bp.route('/status', methods=['GET'])
    def system_status():
        """Get overall system status."""
        dashboard_data = observability_manager.get_dashboard_data()
        
        # Determine overall status
        error_rate = dashboard_data.get('error_rate', 0)
        active_alerts = len(dashboard_data.get('active_alerts', []))
        
        if error_rate > 0.1 or active_alerts > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        return jsonify({
            "status": status,
            "error_rate": error_rate,
            "active_alerts": active_alerts,
            "uptime_seconds": dashboard_data.get('uptime', 0),
            "queries_total": dashboard_data.get('queries_total', 0),
            "queries_failed": dashboard_data.get('queries_failed', 0),
        })
    
    @obs_bp.route('/test/alert', methods=['POST'])
    def test_alert():
        """Trigger a test alert (for testing notification system)."""
        from core.observability import Alert, AlertSeverity
        
        alert = Alert(
            rule_name="test_alert",
            severity=AlertSeverity.INFO,
            message="Test alert for notification system validation",
            metric_value=42.0,
            threshold=100.0,
            timestamp=time.time(),
        )
        
        observability_manager.alert_manager.active_alerts.append(alert)
        
        # Trigger notification if manager available
        if notification_manager:
            import asyncio
            try:
                asyncio.run(notification_manager.notify_alert(
                    rule_name=alert.rule_name,
                    severity=alert.severity.value,
                    message=alert.message,
                    metric_value=alert.metric_value,
                    threshold=alert.threshold,
                ))
            except Exception as e:
                logger.error(f"Failed to send test notification: {e}")
        
        return jsonify({
            "status": "alert_triggered",
            "alert": alert.to_dict(),
        })
    
    return obs_bp


def track_query_execution(observability_manager):
    """
    Decorator to automatically track query execution.
    
    Args:
        observability_manager: Instance of ObservabilityManager
    
    Example:
        @track_query_execution(obs_manager)
        def handle_query(query_text):
            # Implementation
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from core.observability import QueryLog
            
            start_time = time.time()
            start_memory = 0
            
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                
                # Create query log
                query_log = QueryLog(
                    query_id=str(uuid.uuid4())[:8],
                    timestamp=start_time,
                    query_text=kwargs.get('query_text', 'unknown'),
                    duration_ms=duration,
                    hardware_tier="standard",
                )
                
                # Record in observability
                observability_manager.record_query(query_log)
                
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                
                # Create error log
                query_log = QueryLog(
                    query_id=str(uuid.uuid4())[:8],
                    timestamp=start_time,
                    query_text=kwargs.get('query_text', 'unknown'),
                    duration_ms=duration,
                    error=str(e),
                    hardware_tier="standard",
                )
                
                observability_manager.record_query(query_log)
                raise
        
        return wrapper
    return decorator


def configure_observability(app):
    """
    Configure complete observability for Flask app.
    
    Args:
        app: Flask application instance
    """
    from core.observability import get_observability_manager
    from core.notifications import get_notification_manager
    
    # Get or create managers
    obs_manager = get_observability_manager()
    notif_manager = get_notification_manager()
    
    # Add middleware
    create_observability_middleware(obs_manager, app)
    
    # Register blueprint
    obs_bp = create_observability_blueprint(obs_manager, notif_manager)
    app.register_blueprint(obs_bp)
    
    # Register dashboard blueprint
    from core.dashboard import create_dashboard_blueprint
    dashboard_bp = create_dashboard_blueprint()
    app.register_blueprint(dashboard_bp)
    
    logger.info("Observability configured successfully")
    
    return obs_manager, notif_manager
