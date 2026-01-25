"""
Tests for Operational Anomaly Detection Module.

Tests anomaly detection for latency spikes, error rates, and traffic patterns.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from core.monitoring.operational_anomaly import (
    OperationalAnomalyDetector,
    AnomalyThresholds,
    AnomalyEvent,
    AnomalyReport,
    AnomalySeverity,
    get_anomaly_report,
    observe_request,
)


class TestAnomalySeverity:
    """Tests for AnomalySeverity enum."""
    
    def test_severity_values(self):
        """Test severity level values."""
        assert AnomalySeverity.INFO.value == "info"
        assert AnomalySeverity.WARNING.value == "warning"
        assert AnomalySeverity.CRITICAL.value == "critical"


class TestAnomalyThresholds:
    """Tests for AnomalyThresholds configuration."""
    
    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = AnomalyThresholds()
        assert thresholds.latency_warning_ms == 3000.0
        assert thresholds.latency_critical_ms == 10000.0
        assert thresholds.error_rate_warning == 0.05
        assert thresholds.error_rate_critical == 0.15
    
    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = AnomalyThresholds(
            latency_warning_ms=2000.0,
            latency_critical_ms=5000.0,
            error_rate_warning=0.10,
        )
        assert thresholds.latency_warning_ms == 2000.0
        assert thresholds.latency_critical_ms == 5000.0


class TestAnomalyEvent:
    """Tests for AnomalyEvent dataclass."""
    
    def test_event_creation(self):
        """Test event creation with required fields."""
        event = AnomalyEvent(
            anomaly_type="latency_spike",
            severity=AnomalySeverity.WARNING,
            value=5000.0,
            baseline=500.0,
            threshold=3000.0,
            description="High latency detected",
        )
        assert event.anomaly_type == "latency_spike"
        assert event.severity == AnomalySeverity.WARNING
        assert event.value == 5000.0
    
    def test_auto_timestamp(self):
        """Test automatic timestamp generation."""
        event = AnomalyEvent(
            anomaly_type="test",
            severity=AnomalySeverity.INFO,
            value=0,
            baseline=0,
            threshold=0,
            description="Test event",
        )
        assert event.timestamp  # Should be set automatically
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        event = AnomalyEvent(
            anomaly_type="error_rate_surge",
            severity=AnomalySeverity.CRITICAL,
            value=0.20,
            baseline=0.01,
            threshold=0.15,
            description="Error rate critical",
            metadata={"errors": 20},
        )
        result = event.to_dict()
        assert result["anomaly_type"] == "error_rate_surge"
        assert result["severity"] == "critical"  # Converted from enum
        assert result["metadata"]["errors"] == 20


class TestAnomalyReport:
    """Tests for AnomalyReport dataclass."""
    
    def test_empty_report(self):
        """Test empty report creation."""
        report = AnomalyReport()
        assert report.anomalies == []
        assert report.status == "healthy"
        assert report.summary == {}
    
    def test_report_with_anomalies(self):
        """Test report with anomalies."""
        event = AnomalyEvent(
            anomaly_type="latency_spike",
            severity=AnomalySeverity.WARNING,
            value=5000.0,
            baseline=500.0,
            threshold=3000.0,
            description="Test",
        )
        report = AnomalyReport(
            anomalies=[event],
            status="warning",
            summary={"total_anomalies": 1},
        )
        assert len(report.anomalies) == 1
        assert report.status == "warning"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        report = AnomalyReport(status="healthy", summary={"total": 0})
        result = report.to_dict()
        assert result["status"] == "healthy"
        assert "generated_at" in result


class TestOperationalAnomalyDetector:
    """Tests for OperationalAnomalyDetector class."""
    
    def test_initialization(self):
        """Test detector initialization."""
        detector = OperationalAnomalyDetector()
        assert detector.thresholds is not None
    
    def test_custom_thresholds(self):
        """Test detector with custom thresholds."""
        thresholds = AnomalyThresholds(latency_warning_ms=1000.0)
        detector = OperationalAnomalyDetector(thresholds=thresholds)
        assert detector.thresholds.latency_warning_ms == 1000.0
    
    def test_observe_latency_normal(self):
        """Test normal latency observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_latency(500.0)
        assert result is None  # No anomaly for normal latency
    
    def test_observe_latency_warning(self):
        """Test warning latency observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_latency(4000.0)  # Above 3000ms warning
        assert result is not None
        assert result.severity == AnomalySeverity.WARNING
    
    def test_observe_latency_critical(self):
        """Test critical latency observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_latency(15000.0)  # Above 10000ms critical
        assert result is not None
        assert result.severity == AnomalySeverity.CRITICAL
    
    def test_observe_confidence_normal(self):
        """Test normal confidence observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_confidence(0.85)
        assert result is None  # No anomaly for good confidence
    
    def test_observe_confidence_warning(self):
        """Test low confidence observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_confidence(0.4)  # Below 0.5 warning
        assert result is not None
        assert result.severity == AnomalySeverity.WARNING
    
    def test_observe_confidence_critical(self):
        """Test critical confidence observation."""
        detector = OperationalAnomalyDetector()
        result = detector.observe_confidence(0.2)  # Below 0.3 critical
        assert result is not None
        assert result.severity == AnomalySeverity.CRITICAL
    
    def test_observe_error(self):
        """Test error observation."""
        detector = OperationalAnomalyDetector()
        detector.observe_error(True)
        detector.observe_error(False)
        # Should track in rolling window
        rate = detector._get_current_error_rate()
        assert rate == 0.5  # 1 error out of 2
    
    @patch.object(OperationalAnomalyDetector, "_get_connection")
    def test_detect_latency_anomaly(self, mock_conn):
        """Test database-based latency anomaly detection."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"avg_time": 200.0, "count": 100},  # baseline
            {"avg_time": 800.0, "count": 10},   # recent (4x baseline)
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        detector = OperationalAnomalyDetector()
        result = detector.detect_latency_anomaly()
        
        assert result is not None
        assert result.anomaly_type == "latency_spike"
    
    @patch.object(OperationalAnomalyDetector, "_get_connection")
    def test_detect_error_rate_anomaly(self, mock_conn):
        """Test error rate anomaly detection."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total": 100, "errors": 20}  # 20% error rate
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        detector = OperationalAnomalyDetector()
        result = detector.detect_error_rate_anomaly()
        
        assert result is not None
        assert result.severity == AnomalySeverity.CRITICAL
    
    @patch.object(OperationalAnomalyDetector, "detect_latency_anomaly")
    @patch.object(OperationalAnomalyDetector, "detect_error_rate_anomaly")
    @patch.object(OperationalAnomalyDetector, "detect_traffic_anomaly")
    def test_get_anomaly_report_healthy(self, mock_traffic, mock_error, mock_latency):
        """Test healthy anomaly report."""
        mock_latency.return_value = None
        mock_error.return_value = None
        mock_traffic.return_value = None
        
        detector = OperationalAnomalyDetector()
        report = detector.get_anomaly_report()
        
        assert report.status == "healthy"
        assert len(report.anomalies) == 0
    
    @patch.object(OperationalAnomalyDetector, "detect_latency_anomaly")
    @patch.object(OperationalAnomalyDetector, "detect_error_rate_anomaly")
    @patch.object(OperationalAnomalyDetector, "detect_traffic_anomaly")
    def test_get_anomaly_report_with_warning(self, mock_traffic, mock_error, mock_latency):
        """Test report with warning anomaly."""
        mock_latency.return_value = AnomalyEvent(
            anomaly_type="latency_spike",
            severity=AnomalySeverity.WARNING,
            value=5000.0,
            baseline=500.0,
            threshold=3000.0,
            description="Test warning",
        )
        mock_error.return_value = None
        mock_traffic.return_value = None
        
        detector = OperationalAnomalyDetector()
        report = detector.get_anomaly_report()
        
        assert report.status == "warning"
        assert len(report.anomalies) == 1


class TestModuleFunctions:
    """Tests for module-level convenience functions."""
    
    def test_observe_request_normal(self):
        """Test normal request observation."""
        events = observe_request(
            response_time_ms=500.0,
            confidence=0.85,
            is_error=False,
        )
        assert events == []  # No anomalies
    
    def test_observe_request_with_anomaly(self):
        """Test request observation with anomaly."""
        events = observe_request(
            response_time_ms=15000.0,  # Critical latency
            confidence=0.85,
            is_error=False,
        )
        assert len(events) >= 1
        assert any(e.anomaly_type == "latency_spike" for e in events)
    
    @patch("core.monitoring.operational_anomaly.get_detector")
    def test_get_anomaly_report_function(self, mock_get_detector):
        """Test get_anomaly_report convenience function."""
        mock_detector = MagicMock()
        mock_detector.get_anomaly_report.return_value = AnomalyReport(status="healthy")
        mock_get_detector.return_value = mock_detector
        
        report = get_anomaly_report()
        
        assert report.status == "healthy"
        mock_detector.get_anomaly_report.assert_called_once()
