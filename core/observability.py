"""
Phase 4.1: Production Observability & Monitoring

Comprehensive observability framework for NIC:
- Real-time metrics collection
- Performance dashboards
- Alert management
- Structured audit logging
- Query analytics

This module provides visibility into all aspects of NIC operation
across all hardware tiers (ultra_lite to full).
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics tracked."""
    
    COUNTER = "counter"           # Monotonically increasing
    GAUGE = "gauge"               # Point-in-time value
    HISTOGRAM = "histogram"        # Distribution of values
    TIMER = "timer"               # Duration measurements


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class MetricPoint:
    """Single metric data point."""
    
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "labels": self.labels,
        }


@dataclass
class QueryLog:
    """Structured log entry for a query."""
    
    query_id: str
    timestamp: float
    query_text: str
    duration_ms: float
    latency_p95_ms: Optional[float] = None
    
    # Performance
    retrieval_time_ms: float = 0.0
    ranking_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    
    # Resources
    memory_delta_mb: float = 0.0
    cache_hit: bool = False
    models_loaded: List[str] = field(default_factory=list)
    
    # Safety & Quality
    safety_checks_passed: int = 0
    anomalies_detected: int = 0
    confidence_score: float = 0.0
    
    # Results
    documents_retrieved: int = 0
    documents_ranked: int = 0
    error: Optional[str] = None
    
    # Hardware Context
    hardware_tier: str = "standard"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AlertRule:
    """Rule for triggering alerts."""
    
    name: str
    description: str
    metric_name: str
    operator: str  # >, <, ==, !=
    threshold: float
    severity: AlertSeverity
    enabled: bool = True
    cooldown_seconds: int = 300  # Don't alert again within this period
    
    # Tracking
    last_triggered: Optional[float] = None
    trigger_count: int = 0


@dataclass
class Alert:
    """Triggered alert."""
    
    rule_name: str
    severity: AlertSeverity
    message: str
    metric_value: float
    threshold: float
    timestamp: float
    rule_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


class MetricsCollector:
    """
    Collects and stores metrics from NIC operations.
    
    Supports:
    - Time-series metrics
    - Per-hardware-tier metrics
    - Histogram/percentile calculations
    - Prometheus export format
    """
    
    def __init__(self, max_points_per_metric: int = 10000):
        """
        Initialize metrics collector.
        
        Args:
            max_points_per_metric: Maximum stored points per metric (circular buffer)
        """
        self.max_points = max_points_per_metric
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self.start_time = time.time()
    
    def record(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a metric point."""
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels or {},
        )
        self.metrics[name].append(point)
    
    def get_recent(self, name: str, limit: int = 100) -> List[MetricPoint]:
        """Get recent metric points."""
        if name not in self.metrics:
            return []
        return list(self.metrics[name])[-limit:]
    
    def get_percentile(self, name: str, percentile: float) -> Optional[float]:
        """Get percentile value for metric (e.g., p95, p99)."""
        if name not in self.metrics or len(self.metrics[name]) == 0:
            return None
        
        values = sorted([p.value for p in self.metrics[name]])
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]
    
    def get_stats(self, name: str) -> Dict[str, float]:
        """Get statistics for a metric."""
        if name not in self.metrics or len(self.metrics[name]) == 0:
            return {}
        
        values = [p.value for p in self.metrics[name]]
        return {
            "count": len(values),
            "sum": sum(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "p50": self.get_percentile(name, 50) or 0,
            "p95": self.get_percentile(name, 95) or 0,
            "p99": self.get_percentile(name, 99) or 0,
        }
    
    def to_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        lines.append("# HELP nova_nic_metrics NIC metrics")
        lines.append("# TYPE nova_nic_metrics gauge")
        
        uptime = time.time() - self.start_time
        lines.append(f"nova_nic_uptime_seconds {uptime}")
        
        for name, points in self.metrics.items():
            if len(points) == 0:
                continue
            
            latest = points[-1]
            labels_str = ",".join(f'{k}="{v}"' for k, v in latest.labels.items()) if latest.labels else ""
            if labels_str:
                lines.append(f"{name}{{{labels_str}}} {latest.value}")
            else:
                lines.append(f"{name} {latest.value}")
        
        return "\n".join(lines)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        return {
            "uptime_seconds": time.time() - self.start_time,
            "metrics_tracked": len(self.metrics),
            "total_points": sum(len(points) for points in self.metrics.values()),
            "metric_stats": {
                name: self.get_stats(name)
                for name in self.metrics.keys()
            },
        }


class AuditLogger:
    """
    Structured logging for audit trail.
    
    Logs all queries, safety events, configuration changes, etc.
    Supports file storage, searchable format.
    """
    
    def __init__(self, log_dir: Path = Path("logs")):
        """Initialize audit logger."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory circular buffer for recent logs
        self.recent_logs: deque = deque(maxlen=5000)
        
        # File paths
        self.query_log_file = self.log_dir / "queries.jsonl"
        self.safety_log_file = self.log_dir / "safety.jsonl"
        self.event_log_file = self.log_dir / "events.jsonl"
        
        logger.info(f"AuditLogger initialized: {self.log_dir}")
    
    def log_query(self, query_log: QueryLog) -> None:
        """Log a query execution."""
        entry = {
            "type": "query",
            "timestamp": datetime.fromtimestamp(query_log.timestamp).isoformat(),
            **query_log.to_dict(),
        }
        
        self.recent_logs.append(entry)
        
        try:
            with open(self.query_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write query log: {e}")
    
    def log_safety_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        query_id: Optional[str] = None,
    ) -> None:
        """Log a safety event."""
        entry = {
            "type": "safety",
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.recent_logs.append(entry)
        
        try:
            with open(self.safety_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write safety log: {e}")
    
    def log_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Log a general event."""
        entry = {
            "type": "event",
            "event_type": event_type,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        
        self.recent_logs.append(entry)
        
        try:
            with open(self.event_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write event log: {e}")
    
    def search_logs(
        self,
        log_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search recent logs."""
        results = list(self.recent_logs)
        
        if log_type:
            results = [r for r in results if r.get("type") == log_type]
        
        return sorted(results, key=lambda r: r.get("timestamp", ""), reverse=True)[:limit]


class AlertManager:
    """
    Manages alerting rules and triggers.
    
    Features:
    - Define alert rules
    - Track triggering state
    - Cooldown periods
    - Notification callbacks
    """
    
    def __init__(self):
        """Initialize alert manager."""
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: List[Alert] = []
        self.alert_history: deque = deque(maxlen=1000)
        
        # Callbacks
        self.on_alert_triggered: List = []
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self.rules[rule.name] = rule
        logger.info(f"Alert rule added: {rule.name}")
    
    def check_rule(self, rule: AlertRule, current_value: float) -> Optional[Alert]:
        """Check if a rule should trigger."""
        if not rule.enabled:
            return None
        
        # Check cooldown
        if rule.last_triggered:
            time_since_trigger = time.time() - rule.last_triggered
            if time_since_trigger < rule.cooldown_seconds:
                return None
        
        # Check threshold
        triggered = False
        if rule.operator == ">":
            triggered = current_value > rule.threshold
        elif rule.operator == "<":
            triggered = current_value < rule.threshold
        elif rule.operator == "==":
            triggered = current_value == rule.threshold
        elif rule.operator == "!=":
            triggered = current_value != rule.threshold
        
        if triggered:
            alert = Alert(
                rule_name=rule.name,
                severity=rule.severity,
                message=f"{rule.name}: {rule.description} (value: {current_value}, threshold: {rule.threshold})",
                metric_value=current_value,
                threshold=rule.threshold,
                timestamp=time.time(),
            )
            
            # Update rule state
            rule.last_triggered = time.time()
            rule.trigger_count += 1
            
            return alert
        
        return None
    
    def evaluate(self, metrics: Dict[str, float]) -> List[Alert]:
        """Evaluate all rules against metrics."""
        alerts = []
        
        for rule in self.rules.values():
            if rule.metric_name in metrics:
                alert = self.check_rule(rule, metrics[rule.metric_name])
                if alert:
                    alerts.append(alert)
                    self.active_alerts.append(alert)
                    self.alert_history.append(alert)
                    
                    # Trigger callbacks
                    for callback in self.on_alert_triggered:
                        try:
                            callback(alert)
                        except Exception as e:
                            logger.error(f"Alert callback error: {e}")
        
        return alerts
    
    def get_active_alerts(self) -> List[Alert]:
        """Get currently active alerts."""
        # Clear old alerts (older than 1 hour)
        cutoff = time.time() - 3600
        self.active_alerts = [a for a in self.active_alerts if a.timestamp > cutoff]
        return self.active_alerts
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        return {
            "rules_count": len(self.rules),
            "active_alerts": len(self.get_active_alerts()),
            "total_triggered": sum(r.trigger_count for r in self.rules.values()),
            "recent_alerts": [a.to_dict() for a in self.alert_history][-10:],
        }


class ObservabilityManager:
    """
    Central observability manager.
    
    Coordinates metrics, logging, and alerting.
    """
    
    _instance: Optional["ObservabilityManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.metrics = MetricsCollector()
        self.audit_log = AuditLogger()
        self.alert_manager = AlertManager()
        
        # Statistics
        self.query_count = 0
        self.error_count = 0
        self.last_query_time: Optional[float] = None
        
        self._initialized = True
        logger.info("ObservabilityManager initialized")
    
    def record_query(self, query_log: QueryLog) -> None:
        """Record query metrics and logs."""
        # Update counters
        self.query_count += 1
        if query_log.error:
            self.error_count += 1
        self.last_query_time = query_log.timestamp
        
        # Record metrics
        self.metrics.record("query_latency_ms", query_log.duration_ms, {"tier": query_log.hardware_tier})
        self.metrics.record("memory_delta_mb", query_log.memory_delta_mb, {"tier": query_log.hardware_tier})
        self.metrics.record("cache_hit", 1.0 if query_log.cache_hit else 0.0)
        self.metrics.record("retrieval_time_ms", query_log.retrieval_time_ms)
        self.metrics.record("generation_time_ms", query_log.generation_time_ms)
        self.metrics.record("confidence_score", query_log.confidence_score)
        
        # Log query
        self.audit_log.log_query(query_log)
        
        # Check alerts
        current_metrics = {
            "query_latency_ms": query_log.duration_ms,
            "memory_delta_mb": query_log.memory_delta_mb,
            "error_rate": self.error_count / max(1, self.query_count),
        }
        self.alert_manager.evaluate(current_metrics)
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for dashboard rendering."""
        return {
            "uptime": time.time() - self.metrics.start_time,
            "queries_total": self.query_count,
            "queries_failed": self.error_count,
            "error_rate": self.error_count / max(1, self.query_count),
            "last_query": self.last_query_time,
            "metrics": self.metrics.get_summary(),
            "active_alerts": self.alert_manager.get_active_alerts(),
            "alert_stats": self.alert_manager.get_stats(),
            "recent_queries": self.audit_log.search_logs(log_type="query", limit=20),
        }
    
    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        return self.metrics.to_prometheus()


def get_observability_manager() -> ObservabilityManager:
    """Get singleton observability manager."""
    return ObservabilityManager()
