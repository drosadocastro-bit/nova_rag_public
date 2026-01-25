"""
Analytics Dashboard Module for Nova NIC.

Provides aggregated metrics, trend analysis, and dashboard-ready data
for operational visibility and decision-making.

Features:
    - Real-time query metrics and throughput
    - Domain usage breakdown
    - Latency percentiles and trends
    - Error rate tracking
    - Model performance comparison
    - Session analytics

Usage:
    from core.monitoring.analytics_dashboard import (
        get_dashboard_summary,
        get_latency_breakdown,
        get_domain_analytics,
    )
    
    # Get dashboard data
    summary = get_dashboard_summary(hours=24)
    
    # Get latency breakdown
    latency = get_latency_breakdown(hours=1)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import json
import os

# Database path (same as analytics.py)
BASE_DIR = Path(__file__).resolve().parents[2]
ANALYTICS_DIR = BASE_DIR / "vector_db"
DB_PATH = ANALYTICS_DIR / "analytics.db"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QueryMetrics:
    """Aggregate query metrics for a time period."""
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    avg_confidence: float = 0.0
    queries_per_minute: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DomainMetrics:
    """Metrics for a specific domain."""
    domain: str
    query_count: int = 0
    avg_response_time_ms: float = 0.0
    avg_confidence: float = 0.0
    error_rate: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelMetrics:
    """Metrics for a specific model."""
    model_name: str
    query_count: int = 0
    avg_response_time_ms: float = 0.0
    avg_confidence: float = 0.0
    error_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DashboardSummary:
    """Complete dashboard summary."""
    period_hours: int
    query_metrics: QueryMetrics
    domain_breakdown: list[DomainMetrics] = field(default_factory=list)
    model_breakdown: list[ModelMetrics] = field(default_factory=list)
    hourly_trend: list[dict[str, Any]] = field(default_factory=list)
    top_queries: list[dict[str, Any]] = field(default_factory=list)
    safety_stats: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "period_hours": self.period_hours,
            "query_metrics": self.query_metrics.to_dict(),
            "domain_breakdown": [d.to_dict() for d in self.domain_breakdown],
            "model_breakdown": [m.to_dict() for m in self.model_breakdown],
            "hourly_trend": self.hourly_trend,
            "top_queries": self.top_queries,
            "safety_stats": self.safety_stats,
            "generated_at": self.generated_at,
        }


# =============================================================================
# Database Helpers
# =============================================================================

def _get_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile from a list of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    index = min(index, len(sorted_values) - 1)
    return sorted_values[index]


# =============================================================================
# Dashboard Functions
# =============================================================================

def get_dashboard_summary(hours: int = 24) -> DashboardSummary:
    """
    Get comprehensive dashboard summary for the specified time period.
    
    Args:
        hours: Number of hours to look back (default: 24)
        
    Returns:
        DashboardSummary with all metrics
    """
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        # Get query metrics
        query_metrics = _get_query_metrics(cursor, since, hours)
        
        # Get domain breakdown
        domain_breakdown = _get_domain_breakdown(cursor, since)
        
        # Get model breakdown
        model_breakdown = _get_model_breakdown(cursor, since)
        
        # Get hourly trend
        hourly_trend = _get_hourly_trend(cursor, since)
        
        # Get top queries
        top_queries = _get_top_queries(cursor, limit=10)
        
        # Get safety stats
        safety_stats = _get_safety_stats(cursor, since)
        
        conn.close()
        
        return DashboardSummary(
            period_hours=hours,
            query_metrics=query_metrics,
            domain_breakdown=domain_breakdown,
            model_breakdown=model_breakdown,
            hourly_trend=hourly_trend,
            top_queries=top_queries,
            safety_stats=safety_stats,
            generated_at=datetime.now().isoformat(),
        )
        
    except Exception as e:
        # Return empty summary on error
        return DashboardSummary(
            period_hours=hours,
            query_metrics=QueryMetrics(),
            generated_at=datetime.now().isoformat(),
        )


def _get_query_metrics(cursor: sqlite3.Cursor, since: str, hours: int) -> QueryMetrics:
    """Get aggregate query metrics."""
    # Basic counts
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN error IS NULL THEN 1 END) as successful,
            COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as failed,
            AVG(response_time_ms) as avg_time,
            AVG(confidence) as avg_conf
        FROM request_log
        WHERE timestamp > ?
    """, (since,))
    
    row = cursor.fetchone()
    if not row or row["total"] == 0:
        return QueryMetrics()
    
    # Get response times for percentiles
    cursor.execute("""
        SELECT response_time_ms
        FROM request_log
        WHERE timestamp > ? AND response_time_ms IS NOT NULL
        ORDER BY response_time_ms
    """, (since,))
    
    times = [r["response_time_ms"] for r in cursor.fetchall()]
    
    return QueryMetrics(
        total_queries=row["total"] or 0,
        successful_queries=row["successful"] or 0,
        failed_queries=row["failed"] or 0,
        avg_response_time_ms=round(row["avg_time"] or 0, 2),
        p50_response_time_ms=_calculate_percentile(times, 50),
        p95_response_time_ms=_calculate_percentile(times, 95),
        p99_response_time_ms=_calculate_percentile(times, 99),
        avg_confidence=round(row["avg_conf"] or 0, 4),
        queries_per_minute=round(row["total"] / (hours * 60), 2) if hours > 0 else 0,
    )


def _get_domain_breakdown(cursor: sqlite3.Cursor, since: str) -> list[DomainMetrics]:
    """Get metrics broken down by domain."""
    cursor.execute("""
        SELECT 
            COALESCE(mode, 'unknown') as domain,
            COUNT(*) as count,
            AVG(response_time_ms) as avg_time,
            AVG(confidence) as avg_conf,
            CAST(COUNT(CASE WHEN error IS NOT NULL THEN 1 END) AS FLOAT) / COUNT(*) as error_rate
        FROM request_log
        WHERE timestamp > ?
        GROUP BY mode
        ORDER BY count DESC
    """, (since,))
    
    return [
        DomainMetrics(
            domain=row["domain"] or "unknown",
            query_count=row["count"],
            avg_response_time_ms=round(row["avg_time"] or 0, 2),
            avg_confidence=round(row["avg_conf"] or 0, 4),
            error_rate=round(row["error_rate"] or 0, 4),
        )
        for row in cursor.fetchall()
    ]


def _get_model_breakdown(cursor: sqlite3.Cursor, since: str) -> list[ModelMetrics]:
    """Get metrics broken down by model."""
    cursor.execute("""
        SELECT 
            COALESCE(model_used, 'unknown') as model,
            COUNT(*) as count,
            AVG(response_time_ms) as avg_time,
            AVG(confidence) as avg_conf,
            COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
        FROM request_log
        WHERE timestamp > ?
        GROUP BY model_used
        ORDER BY count DESC
    """, (since,))
    
    return [
        ModelMetrics(
            model_name=row["model"] or "unknown",
            query_count=row["count"],
            avg_response_time_ms=round(row["avg_time"] or 0, 2),
            avg_confidence=round(row["avg_conf"] or 0, 4),
            error_count=row["errors"],
        )
        for row in cursor.fetchall()
    ]


def _get_hourly_trend(cursor: sqlite3.Cursor, since: str) -> list[dict[str, Any]]:
    """Get hourly query trend."""
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d %H:00', timestamp) as hour,
            COUNT(*) as queries,
            AVG(response_time_ms) as avg_time,
            COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
        FROM request_log
        WHERE timestamp > ?
        GROUP BY hour
        ORDER BY hour DESC
        LIMIT 48
    """, (since,))
    
    return [
        {
            "hour": row["hour"],
            "queries": row["queries"],
            "avg_response_time_ms": round(row["avg_time"] or 0, 2),
            "errors": row["errors"],
        }
        for row in cursor.fetchall()
    ]


def _get_top_queries(cursor: sqlite3.Cursor, limit: int = 10) -> list[dict[str, Any]]:
    """Get most common queries."""
    cursor.execute("""
        SELECT 
            query_normalized,
            count,
            avg_confidence,
            avg_response_time_ms,
            last_seen
        FROM query_stats
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    
    return [
        {
            "query": row["query_normalized"],
            "count": row["count"],
            "avg_confidence": round(row["avg_confidence"] or 0, 4),
            "avg_response_time_ms": row["avg_response_time_ms"],
            "last_seen": row["last_seen"],
        }
        for row in cursor.fetchall()
    ]


def _get_safety_stats(cursor: sqlite3.Cursor, since: str) -> dict[str, Any]:
    """Get safety-related statistics."""
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN decision_tag IS NOT NULL THEN 1 END) as safety_decisions,
            COUNT(CASE WHEN decision_tag LIKE '%blocked%' THEN 1 END) as blocked_queries,
            COUNT(CASE WHEN decision_tag LIKE '%injection%' THEN 1 END) as injection_attempts
        FROM request_log
        WHERE timestamp > ?
    """, (since,))
    
    row = cursor.fetchone()
    return {
        "safety_decisions": row["safety_decisions"] or 0,
        "blocked_queries": row["blocked_queries"] or 0,
        "injection_attempts": row["injection_attempts"] or 0,
    }


def get_latency_breakdown(hours: int = 1) -> dict[str, Any]:
    """
    Get detailed latency breakdown for recent queries.
    
    Args:
        hours: Number of hours to look back
        
    Returns:
        Dictionary with latency statistics and distribution
    """
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT response_time_ms
            FROM request_log
            WHERE timestamp > ? AND response_time_ms IS NOT NULL
        """, (since,))
        
        times = [r["response_time_ms"] for r in cursor.fetchall()]
        conn.close()
        
        if not times:
            return {
                "count": 0,
                "min_ms": 0,
                "max_ms": 0,
                "avg_ms": 0,
                "p50_ms": 0,
                "p75_ms": 0,
                "p90_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "distribution": {},
            }
        
        # Calculate distribution buckets
        buckets = {"<100ms": 0, "100-500ms": 0, "500-1000ms": 0, 
                   "1-2s": 0, "2-5s": 0, ">5s": 0}
        for t in times:
            if t < 100:
                buckets["<100ms"] += 1
            elif t < 500:
                buckets["100-500ms"] += 1
            elif t < 1000:
                buckets["500-1000ms"] += 1
            elif t < 2000:
                buckets["1-2s"] += 1
            elif t < 5000:
                buckets["2-5s"] += 1
            else:
                buckets[">5s"] += 1
        
        return {
            "count": len(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "avg_ms": round(sum(times) / len(times), 2),
            "p50_ms": _calculate_percentile(times, 50),
            "p75_ms": _calculate_percentile(times, 75),
            "p90_ms": _calculate_percentile(times, 90),
            "p95_ms": _calculate_percentile(times, 95),
            "p99_ms": _calculate_percentile(times, 99),
            "distribution": buckets,
        }
        
    except Exception:
        return {"count": 0, "error": "Failed to retrieve latency data"}


def get_domain_analytics(domain: str, hours: int = 24) -> dict[str, Any]:
    """
    Get detailed analytics for a specific domain.
    
    Args:
        domain: Domain to analyze (e.g., "vehicle", "medical")
        hours: Number of hours to look back
        
    Returns:
        Dictionary with domain-specific analytics
    """
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(response_time_ms) as avg_time,
                AVG(confidence) as avg_conf,
                MIN(response_time_ms) as min_time,
                MAX(response_time_ms) as max_time,
                COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
            FROM request_log
            WHERE timestamp > ? AND mode = ?
        """, (since, domain))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row["total"] == 0:
            return {"domain": domain, "total_queries": 0}
        
        return {
            "domain": domain,
            "period_hours": hours,
            "total_queries": row["total"],
            "avg_response_time_ms": round(row["avg_time"] or 0, 2),
            "min_response_time_ms": row["min_time"],
            "max_response_time_ms": row["max_time"],
            "avg_confidence": round(row["avg_conf"] or 0, 4),
            "error_count": row["errors"],
            "error_rate": round(row["errors"] / row["total"], 4) if row["total"] > 0 else 0,
        }
        
    except Exception:
        return {"domain": domain, "error": "Failed to retrieve domain analytics"}


def get_real_time_stats() -> dict[str, Any]:
    """
    Get real-time statistics for the last 5 minutes.
    
    Returns:
        Dictionary with current operational stats
    """
    since = (datetime.now() - timedelta(minutes=5)).isoformat()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as queries,
                AVG(response_time_ms) as avg_time,
                COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
            FROM request_log
            WHERE timestamp > ?
        """, (since,))
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "period": "5m",
            "queries": row["queries"] or 0,
            "qps": round((row["queries"] or 0) / 300, 2),  # queries per second
            "avg_response_time_ms": round(row["avg_time"] or 0, 2),
            "errors": row["errors"] or 0,
            "timestamp": datetime.now().isoformat(),
        }
        
    except Exception:
        return {"period": "5m", "queries": 0, "qps": 0, "errors": 0}
