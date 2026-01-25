"""
Nova NIC Monitoring Module.

Provides Prometheus metrics, analytics dashboard, anomaly detection,
and compliance reporting for observability and production monitoring.
"""

from .prometheus_metrics import (
    # Metrics registry and WSGI app
    get_metrics_registry,
    get_metrics_wsgi_app,
    # Query metrics
    record_query,
    observe_query_latency,
    # Retrieval metrics
    set_retrieval_confidence,
    # Safety metrics
    record_hallucination_prevention,
    # Session metrics
    set_active_sessions,
    # Cache metrics
    record_cache_hit,
    record_cache_miss,
    # Index metrics
    observe_index_build_time,
)

from .analytics_dashboard import (
    get_dashboard_summary,
    get_latency_breakdown,
    get_domain_analytics,
    get_real_time_stats,
    DashboardSummary,
    QueryMetrics,
    DomainMetrics,
    ModelMetrics,
)

from .operational_anomaly import (
    OperationalAnomalyDetector,
    AnomalyThresholds,
    AnomalyEvent,
    AnomalyReport,
    AnomalySeverity,
    get_anomaly_report,
    observe_request,
)

from .compliance_reporting import (
    ComplianceReporter,
    generate_sla_report,
    generate_safety_audit,
    generate_full_report,
    SLAMetrics,
    SafetyAuditReport,
    ComplianceReport,
)

from .memory_profiler import (
    MemoryProfiler,
    MemorySnapshot,
    MemoryLeak,
    MemoryReport,
    MemoryRecommendation,
    MemorySeverity,
    track_memory,
    get_memory_profiler,
    reset_memory_profiler,
)

__all__ = [
    # Prometheus metrics
    "get_metrics_registry",
    "get_metrics_wsgi_app",
    "record_query",
    "observe_query_latency",
    "set_retrieval_confidence",
    "record_hallucination_prevention",
    "set_active_sessions",
    "record_cache_hit",
    "record_cache_miss",
    "observe_index_build_time",
    # Analytics dashboard
    "get_dashboard_summary",
    "get_latency_breakdown",
    "get_domain_analytics",
    "get_real_time_stats",
    "DashboardSummary",
    "QueryMetrics",
    "DomainMetrics",
    "ModelMetrics",
    # Anomaly detection
    "OperationalAnomalyDetector",
    "AnomalyThresholds",
    "AnomalyEvent",
    "AnomalyReport",
    "AnomalySeverity",
    "get_anomaly_report",
    "observe_request",
    # Compliance reporting
    "ComplianceReporter",
    "generate_sla_report",
    "generate_safety_audit",
    "generate_full_report",
    "SLAMetrics",
    "SafetyAuditReport",
    "ComplianceReport",
    # Memory profiler
    "MemoryProfiler",
    "MemorySnapshot",
    "MemoryLeak",
    "MemoryReport",
    "MemoryRecommendation",
    "MemorySeverity",
    "track_memory",
    "get_memory_profiler",
    "reset_memory_profiler",
]
