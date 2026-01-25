"""
Nova NIC Monitoring Module.

Provides Prometheus metrics for observability and production monitoring.
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

__all__ = [
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
]
