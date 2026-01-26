"""
Flask integration for Phase 4.3 Advanced Analytics.

Provides REST API endpoints for analytics, dashboards, forecasts, and recommendations.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from typing import Dict, Any
import logging

from core.analytics import get_analytics_manager, QueryCategory
from core.trend_analysis import get_performance_predictor

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


def handle_analytics_error(f):
    """Decorator to handle analytics errors."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return jsonify({"error": "Internal server error"}), 500
    return decorated_function


@analytics_bp.route("/dashboard", methods=["GET"])
@handle_analytics_error
def get_analytics_dashboard():
    """
    Get comprehensive analytics dashboard.
    
    Returns:
        Dashboard with query analytics, performance metrics, anomalies, costs.
    """
    manager = get_analytics_manager()
    predictor = get_performance_predictor()
    
    return jsonify({
        "status": "success",
        "dashboard": manager.get_dashboard_data(),
        "forecast_summary": predictor.get_summary(),
    }), 200


@analytics_bp.route("/queries", methods=["GET"])
@handle_analytics_error
def get_query_analytics():
    """
    Get detailed query analytics.
    
    Query parameters:
        - category: Filter by query category
        - limit: Limit slowest queries (default: 10)
        - include_complexity: Include complexity stats (default: true)
    
    Returns:
        Query category distribution, feature adoption, complexity stats, slowest queries.
    """
    manager = get_analytics_manager()
    limit = request.args.get("limit", 10, type=int)
    include_complexity = request.args.get("include_complexity", "true").lower() == "true"
    category_filter = request.args.get("category")
    
    query_analytics = manager.query_analytics
    
    response = {
        "status": "success",
        "category_distribution": query_analytics.get_category_distribution(),
        "top_features": query_analytics.get_top_features(limit=5),
        "slowest_queries": [
            q.to_dict()
            for q in query_analytics.get_slowest_queries(limit)
        ],
        "total_queries": len(query_analytics.queries),
    }
    
    if include_complexity:
        response["complexity_stats"] = query_analytics.get_complexity_stats()
    
    if category_filter:
        try:
            category = QueryCategory[category_filter.upper()]
            count = query_analytics.category_counts.get(category, 0)
            response["filtered_category"] = {
                "name": category_filter,
                "count": count,
                "percentage": (count / len(query_analytics.queries) * 100) if query_analytics.queries else 0,
            }
        except KeyError:
            return jsonify({"error": f"Unknown category: {category_filter}"}), 400
    
    return jsonify(response), 200


@analytics_bp.route("/anomalies", methods=["GET"])
@handle_analytics_error
def get_anomalies():
    """
    Get detected anomalies.
    
    Query parameters:
        - limit: Max anomalies to return (default: 50)
        - anomaly_type: Filter by anomaly type
        - min_severity: Minimum severity level (low, medium, high)
    
    Returns:
        List of detected anomalies with details.
    """
    manager = get_analytics_manager()
    limit = request.args.get("limit", 50, type=int)
    anomaly_type = request.args.get("anomaly_type")
    min_severity = request.args.get("min_severity")
    
    anomalies = manager.anomaly_detector.get_recent_anomalies(limit)
    
    # Filter by type
    if anomaly_type:
        anomalies = [a for a in anomalies if a.anomaly_type.value == anomaly_type]
    
    # Filter by severity
    if min_severity:
        severity_levels = {"low": 1, "medium": 2, "high": 3}
        min_level = severity_levels.get(min_severity, 1)
        severity_map = {"low": 1, "medium": 2, "high": 3}
        anomalies = [
            a for a in anomalies
            if severity_map.get(a.severity, 1) >= min_level
        ]
    
    return jsonify({
        "status": "success",
        "total_anomalies": len(anomalies),
        "anomalies": [
            {
                "timestamp": a.detected_at,
                "metric": a.details.get("metric") if hasattr(a, "details") else None,
                "anomaly_type": a.anomaly_type.value,
                "value": getattr(a, "metric_value", None),
                "expected": getattr(a, "expected_value", None),
                "deviation": getattr(a, "deviation", a.details.get("deviation") if hasattr(a, "details") else None),
                "z_score": a.details.get("z_score") if hasattr(a, "details") else None,
                "severity": a.severity,
            }
            for a in anomalies
        ],
    }), 200


@analytics_bp.route("/performance", methods=["GET"])
@handle_analytics_error
def get_performance_metrics():
    """
    Get performance metrics and trends.
    
    Query parameters:
        - metric: Specific metric (latency_ms, memory_delta_mb)
        - include_trend: Include trend direction (default: true)
        - include_baseline: Include baseline for comparison (default: true)
    
    Returns:
        Performance trends, baseline metrics, trend direction.
    """
    manager = get_analytics_manager()
    metric = request.args.get("metric", "latency_ms")
    include_trend = request.args.get("include_trend", "true").lower() == "true"
    include_baseline = request.args.get("include_baseline", "true").lower() == "true"
    
    perf_analytics = manager.performance_analytics
    
    response = {
        "status": "success",
        "metric": metric,
        "trend_data": [
            {
                "timestamp": t.timestamp,
                "count": t.count,
                "mean": t.mean_value,
                "p50": t.p50_value,
                "p95": t.p95_value,
                "p99": t.p99_value,
            }
            for t in perf_analytics.get_trend(metric)
        ],
    }
    
    if include_trend:
        trend_direction = perf_analytics.detect_trend_direction(metric)
        response["trend_direction"] = trend_direction
    
    if include_baseline and metric in perf_analytics.baseline_metrics:
        response["baseline"] = perf_analytics.baseline_metrics[metric]
    
    return jsonify(response), 200


@analytics_bp.route("/costs", methods=["GET"])
@handle_analytics_error
def get_cost_analysis():
    """
    Get cost analysis and breakdown.
    
    Query parameters:
        - by_tier: Break down by hardware tier (default: true)
        - include_recommendations: Include optimization recommendations (default: true)
    
    Returns:
        Total costs, per-query costs, tier breakdown, optimization recommendations.
    """
    manager = get_analytics_manager()
    by_tier = request.args.get("by_tier", "true").lower() == "true"
    include_recommendations = request.args.get("include_recommendations", "true").lower() == "true"
    
    cost_analytics = manager.cost_analytics
    summary = cost_analytics.get_cost_summary()
    
    response = {
        "status": "success",
        "total_cost": summary["total_cost"],
        "total_queries": summary["total_queries"],
        "mean_cost_per_query": summary["mean_cost_per_query"],
        "median_cost_per_query": summary["median_cost_per_query"],
    }
    
    if by_tier:
        tier_costs = {}
        for tier_name, queries in cost_analytics.tier_costs.items():
            if queries:
                tier_costs[tier_name] = {
                    "total_cost": sum(queries),
                    "count": len(queries),
                    "mean": sum(queries) / len(queries),
                }
        response["by_tier"] = tier_costs
    
    if include_recommendations:
        response["recommendations"] = cost_analytics.get_optimization_recommendations()
    
    return jsonify(response), 200


@analytics_bp.route("/forecasts", methods=["GET"])
@handle_analytics_error
def get_forecasts():
    """
    Get performance forecasts.
    
    Query parameters:
        - metric: Metric to forecast (latency_ms, memory_delta_mb, error_rate)
        - hardware_tier: Hardware tier (default: standard)
        - include_confidence: Include confidence scores (default: true)
    
    Returns:
        1-hour, 1-day, 1-week forecasts with confidence intervals.
    """
    predictor = get_performance_predictor()
    metric = request.args.get("metric", "latency_ms")
    hardware_tier = request.args.get("hardware_tier", "standard")
    include_confidence = request.args.get("include_confidence", "true").lower() == "true"
    
    forecast = predictor.forecast_metric(metric)
    
    if not forecast:
        return jsonify({"error": f"No forecast available for {metric}"}), 404
    
    forecast_dict = forecast.to_dict()
    response = {
        "status": "success",
        "metric": metric,
        "current_value": forecast_dict["current"],
        "baseline_value": forecast_dict["baseline"],
        "forecast_1h": forecast_dict["forecasts"]["1h"],
        "forecast_1d": forecast_dict["forecasts"]["1d"],
        "forecast_1w": forecast_dict["forecasts"]["1w"],
    }
    
    if include_confidence:
        response["confidence"] = forecast_dict.get("confidence")
        response["direction"] = forecast_dict.get("direction")
        response["change_percent"] = forecast_dict.get("change_percent")
    
    return jsonify(response), 200


@analytics_bp.route("/resource-forecast/<hardware_tier>", methods=["GET"])
@handle_analytics_error
def get_resource_forecast(hardware_tier: str):
    """
    Get resource forecasts for a hardware tier.
    
    Args:
        hardware_tier: Hardware tier (ultra_lite, lite, standard, full)
    
    Returns:
        Forecasted latency, memory, and error rates for next periods.
    """
    predictor = get_performance_predictor()
    
    valid_tiers = ["ultra_lite", "lite", "standard", "full"]
    if hardware_tier not in valid_tiers:
        return jsonify({"error": f"Unknown tier: {hardware_tier}"}), 400
    
    forecast = predictor.get_resource_forecast(hardware_tier)
    
    return jsonify({
        "status": "success",
        "hardware_tier": hardware_tier,
        "forecast": forecast,
    }), 200


@analytics_bp.route("/recommendations", methods=["GET"])
@handle_analytics_error
def get_recommendations():
    """
    Get optimization recommendations.
    
    Query parameters:
        - category: Filter by recommendation category
    
    Returns:
        List of actionable optimization recommendations.
    """
    manager = get_analytics_manager()
    
    # Gather recommendations from multiple sources
    recommendations = {
        "cost": manager.cost_analytics.get_optimization_recommendations(),
        "performance": [],
        "reliability": [],
    }
    
    # Add performance recommendations
    perf_analytics = manager.performance_analytics
    for metric, direction in [("latency_ms", perf_analytics.detect_trend_direction("latency_ms"))]:
        if direction == "up":
            recommendations["performance"].append({
                "metric": metric,
                "issue": "Metric is increasing",
                "recommendation": f"Investigate {metric} increase. Consider adding caching or optimizing queries.",
                "priority": "high",
            })
    
    # Filter by category
    category_filter = request.args.get("category")
    if category_filter and category_filter in recommendations:
        recommendations = {category_filter: recommendations[category_filter]}
    
    return jsonify({
        "status": "success",
        "recommendations": recommendations,
    }), 200


@analytics_bp.route("/report/summary", methods=["GET"])
@handle_analytics_error
def get_summary_report():
    """
    Get comprehensive summary report.
    
    Returns:
        Executive summary with key metrics, trends, anomalies, and recommendations.
    """
    manager = get_analytics_manager()
    predictor = get_performance_predictor()
    
    dashboard = manager.get_dashboard_data()
    anomalies = manager.anomaly_detector.get_recent_anomalies(10)
    recommendations = manager.cost_analytics.get_optimization_recommendations()
    
    return jsonify({
        "status": "success",
        "report": {
            "timestamp": dashboard.get("timestamp"),
            "summary": {
                "total_queries": dashboard["query_analytics"]["total_queries"],
                "avg_latency_ms": dashboard["query_analytics"].get("average_latency_ms", 0),
                "cache_hit_rate": dashboard["query_analytics"].get("cache_hit_rate", 0),
            },
            "top_query_categories": dashboard["query_analytics"].get("category_distribution", {}),
            "recent_anomalies": len(anomalies),
            "anomaly_types": list(set(a.anomaly_type.value for a in anomalies)),
            "cost_summary": dashboard["cost_analysis"],
            "top_recommendations": recommendations[:5],
        },
    }), 200


@analytics_bp.route("/export/json", methods=["GET"])
@handle_analytics_error
def export_analytics_json():
    """
    Export all analytics data as JSON.
    
    Returns:
        Complete analytics dataset suitable for external analysis.
    """
    manager = get_analytics_manager()
    
    return jsonify({
        "status": "success",
        "export_format": "json",
        "data": manager.get_dashboard_data(),
    }), 200


def register_analytics_blueprint(app):
    """Register analytics blueprint with Flask app."""
    app.register_blueprint(analytics_bp)
    logger.info("Analytics API registered")


if __name__ == "__main__":
    from nova_flask_app import app
    
    register_analytics_blueprint(app)
    
    with app.test_client() as client:
        # Test endpoints
        print("Testing /api/analytics/dashboard...")
        response = client.get("/api/analytics/dashboard")
        print(f"Status: {response.status_code}")
