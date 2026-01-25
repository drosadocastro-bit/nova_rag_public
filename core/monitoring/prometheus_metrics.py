"""
Prometheus Metrics for Nova NIC.

Exposes system metrics in Prometheus format for monitoring dashboards.
Designed for production observability of RAG pipeline performance,
safety controls, and operational health.

Usage:
    from core.monitoring import record_query, observe_query_latency
    
    # Record a query
    record_query(domain="vehicle", safety_check_passed=True)
    
    # Observe latency
    observe_query_latency(stage="retrieval", duration_seconds=0.15)

Metrics Exposed:
    - nova_queries_total: Counter of total queries by domain and safety status
    - nova_query_latency_seconds: Histogram of query latency by processing stage
    - nova_retrieval_confidence_score: Gauge of current retrieval confidence
    - nova_hallucination_preventions_total: Counter of prevented hallucinations
    - nova_active_sessions: Gauge of currently active sessions
    - nova_cache_hits_total / nova_cache_misses_total: Cache performance counters
    - nova_index_build_seconds: Histogram of index build times
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    make_wsgi_app,
)

# Create a custom registry to avoid conflicts with default metrics
REGISTRY = CollectorRegistry(auto_describe=True)

# =============================================================================
# Query Metrics
# =============================================================================

nova_queries_total = Counter(
    name="nova_queries_total",
    documentation="Total number of queries processed",
    labelnames=["domain", "safety_check_passed"],
    registry=REGISTRY,
)

nova_query_latency_seconds = Histogram(
    name="nova_query_latency_seconds",
    documentation="Query processing latency in seconds by stage",
    labelnames=["stage"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# =============================================================================
# Retrieval Metrics
# =============================================================================

nova_retrieval_confidence_score = Gauge(
    name="nova_retrieval_confidence_score",
    documentation="Current retrieval confidence score (0-1)",
    registry=REGISTRY,
)

# =============================================================================
# Safety Metrics
# =============================================================================

nova_hallucination_preventions_total = Counter(
    name="nova_hallucination_preventions_total",
    documentation="Total hallucination preventions by reason",
    labelnames=["reason"],
    registry=REGISTRY,
)

# =============================================================================
# Session Metrics
# =============================================================================

nova_active_sessions = Gauge(
    name="nova_active_sessions",
    documentation="Number of currently active sessions",
    registry=REGISTRY,
)

# =============================================================================
# Cache Metrics
# =============================================================================

nova_cache_hits_total = Counter(
    name="nova_cache_hits_total",
    documentation="Total cache hits",
    registry=REGISTRY,
)

nova_cache_misses_total = Counter(
    name="nova_cache_misses_total",
    documentation="Total cache misses",
    registry=REGISTRY,
)

# =============================================================================
# Index Metrics
# =============================================================================

nova_index_build_seconds = Histogram(
    name="nova_index_build_seconds",
    documentation="Index build time in seconds",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    registry=REGISTRY,
)


# =============================================================================
# Helper Functions
# =============================================================================

def get_metrics_registry() -> CollectorRegistry:
    """Return the Prometheus metrics registry."""
    return REGISTRY


def get_metrics_wsgi_app():
    """Return a WSGI app that serves Prometheus metrics."""
    return make_wsgi_app(REGISTRY)


def record_query(domain: str = "unknown", safety_check_passed: bool = True) -> None:
    """
    Record a query with its domain and safety check status.
    
    Args:
        domain: The domain of the query (e.g., "vehicle", "medical", "aerospace")
        safety_check_passed: Whether the query passed safety checks
    """
    nova_queries_total.labels(
        domain=domain,
        safety_check_passed=str(safety_check_passed).lower(),
    ).inc()


def observe_query_latency(stage: str, duration_seconds: float) -> None:
    """
    Record query latency for a specific processing stage.
    
    Args:
        stage: Processing stage (e.g., "retrieval", "generation", "safety", "total")
        duration_seconds: Duration in seconds
    """
    nova_query_latency_seconds.labels(stage=stage).observe(duration_seconds)


def set_retrieval_confidence(score: float) -> None:
    """
    Set the current retrieval confidence score.
    
    Args:
        score: Confidence score between 0 and 1
    """
    nova_retrieval_confidence_score.set(max(0.0, min(1.0, score)))


def record_hallucination_prevention(reason: str) -> None:
    """
    Record a hallucination prevention event.
    
    Args:
        reason: Reason for prevention (e.g., "low_confidence", "no_sources", 
                "conflicting_evidence", "safety_filter")
    """
    nova_hallucination_preventions_total.labels(reason=reason).inc()


def set_active_sessions(count: int) -> None:
    """
    Set the number of active sessions.
    
    Args:
        count: Number of currently active sessions
    """
    nova_active_sessions.set(max(0, count))


def record_cache_hit() -> None:
    """Record a cache hit."""
    nova_cache_hits_total.inc()


def record_cache_miss() -> None:
    """Record a cache miss."""
    nova_cache_misses_total.inc()


def observe_index_build_time(duration_seconds: float) -> None:
    """
    Record index build time.
    
    Args:
        duration_seconds: Build duration in seconds
    """
    nova_index_build_seconds.observe(duration_seconds)


def generate_metrics() -> bytes:
    """
    Generate Prometheus metrics output.
    
    Returns:
        Bytes containing the metrics in Prometheus text format
    """
    return generate_latest(REGISTRY)


def get_content_type() -> str:
    """
    Get the content type for Prometheus metrics.
    
    Returns:
        The content type string for Prometheus metrics
    """
    return CONTENT_TYPE_LATEST
