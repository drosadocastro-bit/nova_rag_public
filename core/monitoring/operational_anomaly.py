"""
Operational Anomaly Detection for Nova NIC.

Monitors system behavior patterns and detects anomalies in:
    - Latency spikes (sudden increases in response time)
    - Error rate surges (unusual error patterns)
    - Traffic anomalies (unusual query volumes)
    - Confidence drops (model performance degradation)

Uses statistical methods (Z-score, moving averages) for detection.
Integrates with Prometheus metrics and structured logging.

Usage:
    from core.monitoring.operational_anomaly import OperationalAnomalyDetector
    
    detector = OperationalAnomalyDetector()
    
    # Record a metric observation
    detector.observe_latency(response_time_ms=1500)
    
    # Check for anomalies
    report = detector.get_anomaly_report()
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Optional
import json
import os

from core.monitoring.logger_config import get_logger, log_safety_event

logger = get_logger("core.monitoring.operational_anomaly")

# Database path (same as analytics.py)
BASE_DIR = Path(__file__).resolve().parents[2]
ANALYTICS_DIR = BASE_DIR / "vector_db"
DB_PATH = ANALYTICS_DIR / "analytics.db"


# =============================================================================
# Configuration
# =============================================================================

class AnomalySeverity(str, Enum):
    """Severity levels for detected anomalies."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnomalyThresholds:
    """Configurable thresholds for anomaly detection."""
    # Latency thresholds
    latency_warning_ms: float = 3000.0  # 3 seconds
    latency_critical_ms: float = 10000.0  # 10 seconds
    latency_zscore_threshold: float = 2.5  # Z-score for spike detection
    
    # Error rate thresholds
    error_rate_warning: float = 0.05  # 5%
    error_rate_critical: float = 0.15  # 15%
    
    # Traffic thresholds (compared to baseline)
    traffic_spike_multiplier: float = 3.0  # 3x baseline
    traffic_drop_threshold: float = 0.2  # 80% drop
    
    # Confidence thresholds
    confidence_warning: float = 0.5
    confidence_critical: float = 0.3
    
    # Time windows
    baseline_hours: int = 24  # Hours for baseline calculation
    detection_minutes: int = 5  # Recent window for detection


@dataclass
class AnomalyEvent:
    """Represents a detected anomaly."""
    anomaly_type: str
    severity: AnomalySeverity
    value: float
    baseline: float
    threshold: float
    description: str
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "severity": self.severity.value,
        }


@dataclass
class AnomalyReport:
    """Complete anomaly report."""
    anomalies: list[AnomalyEvent] = field(default_factory=list)
    status: str = "healthy"  # healthy, warning, critical
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "anomalies": [a.to_dict() for a in self.anomalies],
            "status": self.status,
            "summary": self.summary,
            "generated_at": self.generated_at,
        }


# =============================================================================
# Operational Anomaly Detector
# =============================================================================

class OperationalAnomalyDetector:
    """
    Detects operational anomalies in system behavior.
    
    Uses rolling statistics and database queries to identify:
    - Latency spikes
    - Error rate surges
    - Traffic anomalies
    - Confidence degradation
    """
    
    def __init__(self, thresholds: Optional[AnomalyThresholds] = None):
        self.thresholds = thresholds or AnomalyThresholds()
        self._lock = Lock()
        
        # Rolling windows for real-time detection
        self._latency_window: deque = deque(maxlen=100)
        self._error_window: deque = deque(maxlen=100)
        self._confidence_window: deque = deque(maxlen=100)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    # =========================================================================
    # Real-time Observation Methods
    # =========================================================================
    
    def observe_latency(self, response_time_ms: float) -> Optional[AnomalyEvent]:
        """
        Record a latency observation and check for anomalies.
        
        Args:
            response_time_ms: Response time in milliseconds
            
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        """
        with self._lock:
            self._latency_window.append(response_time_ms)
        
        # Check against absolute thresholds
        if response_time_ms >= self.thresholds.latency_critical_ms:
            event = AnomalyEvent(
                anomaly_type="latency_spike",
                severity=AnomalySeverity.CRITICAL,
                value=response_time_ms,
                baseline=self._calculate_baseline_latency(),
                threshold=self.thresholds.latency_critical_ms,
                description=f"Critical latency: {response_time_ms:.0f}ms exceeds {self.thresholds.latency_critical_ms:.0f}ms threshold",
            )
            self._log_anomaly(event)
            return event
        
        elif response_time_ms >= self.thresholds.latency_warning_ms:
            event = AnomalyEvent(
                anomaly_type="latency_spike",
                severity=AnomalySeverity.WARNING,
                value=response_time_ms,
                baseline=self._calculate_baseline_latency(),
                threshold=self.thresholds.latency_warning_ms,
                description=f"High latency: {response_time_ms:.0f}ms exceeds {self.thresholds.latency_warning_ms:.0f}ms warning threshold",
            )
            self._log_anomaly(event)
            return event
        
        # Check for statistical anomaly (Z-score)
        zscore = self._calculate_latency_zscore(response_time_ms)
        if zscore and zscore > self.thresholds.latency_zscore_threshold:
            event = AnomalyEvent(
                anomaly_type="latency_spike",
                severity=AnomalySeverity.WARNING,
                value=response_time_ms,
                baseline=self._calculate_baseline_latency(),
                threshold=zscore,
                description=f"Latency Z-score {zscore:.2f} indicates statistical anomaly",
                metadata={"zscore": zscore},
            )
            self._log_anomaly(event)
            return event
        
        return None
    
    def observe_error(self, is_error: bool) -> None:
        """Record an error observation."""
        with self._lock:
            self._error_window.append(1 if is_error else 0)
    
    def observe_confidence(self, confidence: float) -> Optional[AnomalyEvent]:
        """
        Record a confidence observation and check for degradation.
        
        Args:
            confidence: Confidence score (0-1)
            
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        """
        with self._lock:
            self._confidence_window.append(confidence)
        
        if confidence <= self.thresholds.confidence_critical:
            event = AnomalyEvent(
                anomaly_type="confidence_degradation",
                severity=AnomalySeverity.CRITICAL,
                value=confidence,
                baseline=self._calculate_baseline_confidence(),
                threshold=self.thresholds.confidence_critical,
                description=f"Critical confidence: {confidence:.3f} below {self.thresholds.confidence_critical} threshold",
            )
            self._log_anomaly(event)
            return event
        
        elif confidence <= self.thresholds.confidence_warning:
            event = AnomalyEvent(
                anomaly_type="confidence_degradation",
                severity=AnomalySeverity.WARNING,
                value=confidence,
                baseline=self._calculate_baseline_confidence(),
                threshold=self.thresholds.confidence_warning,
                description=f"Low confidence: {confidence:.3f} below {self.thresholds.confidence_warning} warning threshold",
            )
            self._log_anomaly(event)
            return event
        
        return None
    
    # =========================================================================
    # Statistical Helpers
    # =========================================================================
    
    def _calculate_latency_zscore(self, value: float) -> Optional[float]:
        """Calculate Z-score for a latency observation."""
        with self._lock:
            if len(self._latency_window) < 10:
                return None
            
            values = list(self._latency_window)
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance ** 0.5
        
        if std == 0:
            return None
        
        return (value - mean) / std
    
    def _calculate_baseline_latency(self) -> float:
        """Calculate baseline latency from rolling window."""
        with self._lock:
            if not self._latency_window:
                return 0.0
            return sum(self._latency_window) / len(self._latency_window)
    
    def _calculate_baseline_confidence(self) -> float:
        """Calculate baseline confidence from rolling window."""
        with self._lock:
            if not self._confidence_window:
                return 1.0
            return sum(self._confidence_window) / len(self._confidence_window)
    
    def _get_current_error_rate(self) -> float:
        """Get current error rate from rolling window."""
        with self._lock:
            if not self._error_window:
                return 0.0
            return sum(self._error_window) / len(self._error_window)
    
    # =========================================================================
    # Database-Based Detection
    # =========================================================================
    
    def detect_latency_anomaly(self) -> Optional[AnomalyEvent]:
        """
        Detect latency anomalies by comparing recent data to baseline.
        
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get baseline (last 24 hours, excluding last 5 minutes)
            baseline_since = (datetime.now() - timedelta(hours=self.thresholds.baseline_hours)).isoformat()
            recent_since = (datetime.now() - timedelta(minutes=self.thresholds.detection_minutes)).isoformat()
            
            cursor.execute("""
                SELECT AVG(response_time_ms) as avg_time,
                       COUNT(*) as count
                FROM request_log
                WHERE timestamp > ? AND timestamp < ?
                  AND response_time_ms IS NOT NULL
            """, (baseline_since, recent_since))
            
            baseline = cursor.fetchone()
            
            # Get recent average
            cursor.execute("""
                SELECT AVG(response_time_ms) as avg_time,
                       COUNT(*) as count
                FROM request_log
                WHERE timestamp > ? AND response_time_ms IS NOT NULL
            """, (recent_since,))
            
            recent = cursor.fetchone()
            conn.close()
            
            if not baseline or not recent or baseline["count"] < 10 or recent["count"] < 3:
                return None
            
            baseline_avg = baseline["avg_time"] or 0
            recent_avg = recent["avg_time"] or 0
            
            if baseline_avg > 0:
                ratio = recent_avg / baseline_avg
                if ratio >= 3.0:  # 3x baseline
                    return AnomalyEvent(
                        anomaly_type="latency_spike",
                        severity=AnomalySeverity.CRITICAL,
                        value=recent_avg,
                        baseline=baseline_avg,
                        threshold=3.0,
                        description=f"Recent latency {recent_avg:.0f}ms is {ratio:.1f}x baseline {baseline_avg:.0f}ms",
                        metadata={"ratio": ratio, "recent_count": recent["count"]},
                    )
                elif ratio >= 2.0:  # 2x baseline
                    return AnomalyEvent(
                        anomaly_type="latency_spike",
                        severity=AnomalySeverity.WARNING,
                        value=recent_avg,
                        baseline=baseline_avg,
                        threshold=2.0,
                        description=f"Recent latency {recent_avg:.0f}ms is {ratio:.1f}x baseline {baseline_avg:.0f}ms",
                        metadata={"ratio": ratio, "recent_count": recent["count"]},
                    )
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to detect latency anomaly: {e}")
            return None
    
    def detect_error_rate_anomaly(self) -> Optional[AnomalyEvent]:
        """
        Detect error rate anomalies by comparing recent data to baseline.
        
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            recent_since = (datetime.now() - timedelta(minutes=self.thresholds.detection_minutes)).isoformat()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
                FROM request_log
                WHERE timestamp > ?
            """, (recent_since,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row or row["total"] < 5:
                return None
            
            error_rate = row["errors"] / row["total"]
            
            if error_rate >= self.thresholds.error_rate_critical:
                return AnomalyEvent(
                    anomaly_type="error_rate_surge",
                    severity=AnomalySeverity.CRITICAL,
                    value=error_rate,
                    baseline=0.0,
                    threshold=self.thresholds.error_rate_critical,
                    description=f"Critical error rate: {error_rate*100:.1f}% exceeds {self.thresholds.error_rate_critical*100:.0f}% threshold",
                    metadata={"total": row["total"], "errors": row["errors"]},
                )
            elif error_rate >= self.thresholds.error_rate_warning:
                return AnomalyEvent(
                    anomaly_type="error_rate_surge",
                    severity=AnomalySeverity.WARNING,
                    value=error_rate,
                    baseline=0.0,
                    threshold=self.thresholds.error_rate_warning,
                    description=f"Elevated error rate: {error_rate*100:.1f}% exceeds {self.thresholds.error_rate_warning*100:.0f}% warning threshold",
                    metadata={"total": row["total"], "errors": row["errors"]},
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to detect error rate anomaly: {e}")
            return None
    
    def detect_traffic_anomaly(self) -> Optional[AnomalyEvent]:
        """
        Detect traffic anomalies (spikes or drops).
        
        Returns:
            AnomalyEvent if anomaly detected, None otherwise
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get baseline hourly rate (last 24 hours)
            baseline_since = (datetime.now() - timedelta(hours=24)).isoformat()
            recent_since = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM request_log WHERE timestamp > ?
            """, (baseline_since,))
            
            baseline_total = cursor.fetchone()["total"]
            baseline_per_5min = baseline_total / (24 * 12) if baseline_total else 0
            
            cursor.execute("""
                SELECT COUNT(*) as total FROM request_log WHERE timestamp > ?
            """, (recent_since,))
            
            recent_total = cursor.fetchone()["total"]
            conn.close()
            
            if baseline_per_5min < 1:
                return None  # Not enough baseline data
            
            ratio = recent_total / baseline_per_5min
            
            if ratio >= self.thresholds.traffic_spike_multiplier:
                return AnomalyEvent(
                    anomaly_type="traffic_spike",
                    severity=AnomalySeverity.WARNING,
                    value=float(recent_total),
                    baseline=baseline_per_5min,
                    threshold=self.thresholds.traffic_spike_multiplier,
                    description=f"Traffic spike: {recent_total} queries in 5min is {ratio:.1f}x baseline",
                    metadata={"ratio": ratio},
                )
            elif ratio <= self.thresholds.traffic_drop_threshold and recent_total < 2:
                return AnomalyEvent(
                    anomaly_type="traffic_drop",
                    severity=AnomalySeverity.INFO,
                    value=float(recent_total),
                    baseline=baseline_per_5min,
                    threshold=self.thresholds.traffic_drop_threshold,
                    description=f"Traffic drop: {recent_total} queries in 5min is {ratio:.1f}x baseline",
                    metadata={"ratio": ratio},
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to detect traffic anomaly: {e}")
            return None
    
    # =========================================================================
    # Anomaly Report Generation
    # =========================================================================
    
    def get_anomaly_report(self) -> AnomalyReport:
        """
        Generate a comprehensive anomaly report.
        
        Returns:
            AnomalyReport with all detected anomalies
        """
        anomalies: list[AnomalyEvent] = []
        
        # Check all anomaly types
        latency_anomaly = self.detect_latency_anomaly()
        if latency_anomaly:
            anomalies.append(latency_anomaly)
        
        error_anomaly = self.detect_error_rate_anomaly()
        if error_anomaly:
            anomalies.append(error_anomaly)
        
        traffic_anomaly = self.detect_traffic_anomaly()
        if traffic_anomaly:
            anomalies.append(traffic_anomaly)
        
        # Determine overall status
        status = "healthy"
        if any(a.severity == AnomalySeverity.CRITICAL for a in anomalies):
            status = "critical"
        elif any(a.severity == AnomalySeverity.WARNING for a in anomalies):
            status = "warning"
        
        # Generate summary
        summary = {
            "total_anomalies": len(anomalies),
            "critical_count": sum(1 for a in anomalies if a.severity == AnomalySeverity.CRITICAL),
            "warning_count": sum(1 for a in anomalies if a.severity == AnomalySeverity.WARNING),
            "types_detected": list(set(a.anomaly_type for a in anomalies)),
        }
        
        report = AnomalyReport(
            anomalies=anomalies,
            status=status,
            summary=summary,
        )
        
        if anomalies:
            logger.warning(
                "anomaly_report_generated",
                extra={
                    "status": status,
                    "anomaly_count": len(anomalies),
                    "types": summary["types_detected"],
                },
            )
        
        return report
    
    def _log_anomaly(self, event: AnomalyEvent) -> None:
        """Log an anomaly event."""
        log_level = "error" if event.severity == AnomalySeverity.CRITICAL else "warning"
        log_safety_event(
            logger,
            "operational_anomaly",
            check_name=event.anomaly_type,
            passed=False,
            details={
                "severity": event.severity.value,
                "value": event.value,
                "baseline": event.baseline,
                "threshold": event.threshold,
                "description": event.description,
            },
        )


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_detector: Optional[OperationalAnomalyDetector] = None


def get_detector() -> OperationalAnomalyDetector:
    """Get or create the default anomaly detector."""
    global _default_detector
    if _default_detector is None:
        _default_detector = OperationalAnomalyDetector()
    return _default_detector


def observe_request(
    response_time_ms: float,
    confidence: float,
    is_error: bool = False,
) -> list[AnomalyEvent]:
    """
    Convenience function to observe a complete request.
    
    Args:
        response_time_ms: Response time in milliseconds
        confidence: Confidence score (0-1)
        is_error: Whether the request resulted in an error
        
    Returns:
        List of detected anomalies (empty if none)
    """
    detector = get_detector()
    anomalies = []
    
    latency_event = detector.observe_latency(response_time_ms)
    if latency_event:
        anomalies.append(latency_event)
    
    confidence_event = detector.observe_confidence(confidence)
    if confidence_event:
        anomalies.append(confidence_event)
    
    detector.observe_error(is_error)
    
    return anomalies


def get_anomaly_report() -> AnomalyReport:
    """Convenience function to get the anomaly report."""
    return get_detector().get_anomaly_report()
