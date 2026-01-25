"""
Tests for Compliance Reporting Module.

Tests SLA metrics, safety audit, data retention, and report generation.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from pathlib import Path
import tempfile
import json

from core.monitoring.compliance_reporting import (
    ComplianceReporter,
    SLAMetrics,
    SafetyEvent,
    SafetyAuditReport,
    DataRetentionReport,
    ComplianceReport,
    generate_sla_report,
    generate_safety_audit,
    generate_full_report,
)


class TestSLAMetrics:
    """Tests for SLAMetrics dataclass."""
    
    def test_default_values(self):
        """Test default initialization."""
        metrics = SLAMetrics()
        assert metrics.period_days == 0
        assert metrics.total_requests == 0
        assert metrics.uptime_target == 99.5
        assert metrics.overall_compliant is False
    
    def test_compliant_metrics(self):
        """Test compliant metrics."""
        metrics = SLAMetrics(
            period_days=30,
            total_requests=1000,
            successful_requests=995,
            failed_requests=5,
            uptime_percentage=99.7,
            uptime_target=99.5,
            uptime_compliant=True,
            p95_response_time_ms=2500.0,
            latency_target_ms=3000.0,
            latency_compliant=True,
            error_rate=0.005,
            error_rate_target=0.01,
            error_rate_compliant=True,
            overall_compliant=True,
        )
        assert metrics.overall_compliant is True
        assert metrics.uptime_compliant is True
        assert metrics.latency_compliant is True
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = SLAMetrics(period_days=7, total_requests=100)
        result = metrics.to_dict()
        assert result["period_days"] == 7
        assert result["total_requests"] == 100


class TestSafetyEvent:
    """Tests for SafetyEvent dataclass."""
    
    def test_event_creation(self):
        """Test safety event creation."""
        event = SafetyEvent(
            timestamp="2026-01-25T10:00:00",
            event_type="blocked_query",
            severity="critical",
            query_preview="How to disable airbags...",
            decision_tag="blocked_unsafe",
        )
        assert event.event_type == "blocked_query"
        assert event.severity == "critical"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        event = SafetyEvent(
            timestamp="2026-01-25T10:00:00",
            event_type="injection_attempt",
            severity="critical",
            query_preview="Ignore all safety...",
            details={"trigger": "injection_pattern"},
        )
        result = event.to_dict()
        assert result["event_type"] == "injection_attempt"
        assert result["details"]["trigger"] == "injection_pattern"


class TestSafetyAuditReport:
    """Tests for SafetyAuditReport dataclass."""
    
    def test_empty_report(self):
        """Test empty audit report."""
        report = SafetyAuditReport(period_days=7)
        assert report.total_events == 0
        assert report.blocked_queries == 0
        assert report.events == []
    
    def test_report_with_events(self):
        """Test report with safety events."""
        events = [
            SafetyEvent(
                timestamp="2026-01-25T10:00:00",
                event_type="blocked_query",
                severity="critical",
                query_preview="Test query",
            )
        ]
        report = SafetyAuditReport(
            period_days=7,
            total_events=1,
            blocked_queries=1,
            events=events,
            severity_breakdown={"critical": 1},
        )
        assert report.total_events == 1
        assert len(report.events) == 1


class TestDataRetentionReport:
    """Tests for DataRetentionReport dataclass."""
    
    def test_compliant_report(self):
        """Test compliant retention report."""
        report = DataRetentionReport(
            total_records=1000,
            oldest_record="2026-01-01T00:00:00",
            newest_record="2026-01-25T00:00:00",
            retention_policy_days=90,
            records_within_policy=1000,
            records_outside_policy=0,
            compliant=True,
        )
        assert report.compliant is True
        assert report.records_outside_policy == 0
    
    def test_non_compliant_report(self):
        """Test non-compliant retention report."""
        report = DataRetentionReport(
            total_records=1500,
            records_within_policy=1000,
            records_outside_policy=500,
            compliant=False,
            recommendation="Purge 500 old records",
        )
        assert report.compliant is False
        assert report.recommendation != ""


class TestComplianceReport:
    """Tests for ComplianceReport dataclass."""
    
    def test_minimal_report(self):
        """Test minimal compliance report."""
        report = ComplianceReport(
            report_type="sla",
            period_start="2026-01-01T00:00:00",
            period_end="2026-01-25T00:00:00",
        )
        assert report.report_type == "sla"
        assert report.generated_at  # Auto-set
    
    def test_full_report(self):
        """Test full compliance report."""
        report = ComplianceReport(
            report_type="full_compliance",
            period_start="2026-01-01T00:00:00",
            period_end="2026-01-25T00:00:00",
            sla_metrics=SLAMetrics(period_days=30),
            safety_audit=SafetyAuditReport(period_days=7),
            data_retention=DataRetentionReport(),
            recommendations=["Improve uptime", "Monitor errors"],
        )
        result = report.to_dict()
        assert "sla_metrics" in result
        assert "safety_audit" in result
        assert len(result["recommendations"]) == 2


class TestComplianceReporter:
    """Tests for ComplianceReporter class."""
    
    def test_initialization(self):
        """Test reporter initialization."""
        reporter = ComplianceReporter()
        assert reporter.uptime_target == 99.5
        assert reporter.latency_target_ms == 3000.0
        assert reporter.retention_days == 90
    
    def test_custom_targets(self):
        """Test reporter with custom targets."""
        reporter = ComplianceReporter(
            uptime_target=99.9,
            latency_target_ms=2000.0,
            retention_days=60,
        )
        assert reporter.uptime_target == 99.9
        assert reporter.latency_target_ms == 2000.0
    
    @patch.object(ComplianceReporter, "_get_connection")
    def test_generate_sla_report(self, mock_conn):
        """Test SLA report generation."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total": 1000,
            "successful": 990,
            "failed": 10,
            "avg_time": 500.0,
        }
        mock_cursor.fetchall.return_value = [
            {"response_time_ms": 100},
            {"response_time_ms": 200},
            {"response_time_ms": 500},
            {"response_time_ms": 2000},
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        reporter = ComplianceReporter()
        result = reporter.generate_sla_report(days=30)
        
        assert isinstance(result, SLAMetrics)
        assert result.total_requests == 1000
        assert result.period_days == 30
    
    @patch.object(ComplianceReporter, "_get_connection")
    def test_generate_safety_audit(self, mock_conn):
        """Test safety audit generation."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "timestamp": "2026-01-25T10:00:00",
                "question": "Test blocked query",
                "decision_tag": "blocked_unsafe",
                "heuristic_trigger": "safety_filter",
                "confidence": 0.3,
                "error": None,
            }
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        reporter = ComplianceReporter()
        result = reporter.generate_safety_audit(days=7)
        
        assert isinstance(result, SafetyAuditReport)
        assert result.period_days == 7
    
    @patch.object(ComplianceReporter, "_get_connection")
    def test_generate_retention_report(self, mock_conn):
        """Test retention report generation."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"total": 1000},
            {"oldest": "2026-01-01T00:00:00", "newest": "2026-01-25T00:00:00"},
            {"within_policy": 1000, "outside_policy": 0},
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        reporter = ComplianceReporter()
        result = reporter.generate_retention_report()
        
        assert isinstance(result, DataRetentionReport)
        assert result.total_records == 1000
    
    @patch.object(ComplianceReporter, "generate_sla_report")
    @patch.object(ComplianceReporter, "generate_safety_audit")
    @patch.object(ComplianceReporter, "generate_retention_report")
    def test_generate_full_report(self, mock_retention, mock_safety, mock_sla):
        """Test full compliance report generation."""
        mock_sla.return_value = SLAMetrics(
            period_days=30,
            uptime_compliant=True,
            latency_compliant=True,
            error_rate_compliant=True,
            overall_compliant=True,
        )
        mock_safety.return_value = SafetyAuditReport(period_days=30)
        mock_retention.return_value = DataRetentionReport(compliant=True)
        
        reporter = ComplianceReporter()
        result = reporter.generate_full_report(days=30)
        
        assert isinstance(result, ComplianceReport)
        assert result.report_type == "full_compliance"
        assert result.sla_metrics is not None
        assert result.safety_audit is not None


class TestExportFunctions:
    """Tests for report export functions."""
    
    def test_export_json(self):
        """Test JSON export."""
        reporter = ComplianceReporter()
        report = ComplianceReport(
            report_type="test",
            period_start="2026-01-01",
            period_end="2026-01-25",
            recommendations=["Test recommendation"],
        )
        
        json_str = reporter.export_json(report)
        
        parsed = json.loads(json_str)
        assert parsed["report_type"] == "test"
        assert len(parsed["recommendations"]) == 1
    
    def test_export_json_to_file(self):
        """Test JSON export to file."""
        reporter = ComplianceReporter()
        report = ComplianceReport(
            report_type="test",
            period_start="2026-01-01",
            period_end="2026-01-25",
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test_report.json"
            reporter.export_json(report, filepath)
            
            assert filepath.exists()
            content = json.loads(filepath.read_text())
            assert content["report_type"] == "test"
    
    def test_export_markdown(self):
        """Test Markdown export."""
        reporter = ComplianceReporter()
        report = ComplianceReport(
            report_type="full_compliance",
            period_start="2026-01-01",
            period_end="2026-01-25",
            sla_metrics=SLAMetrics(
                period_days=30,
                total_requests=1000,
                uptime_percentage=99.7,
                uptime_compliant=True,
                p95_response_time_ms=2500,
                latency_compliant=True,
                error_rate=0.005,
                error_rate_compliant=True,
                overall_compliant=True,
            ),
            recommendations=["Keep up the good work"],
        )
        
        markdown = reporter.export_markdown(report)
        
        assert "# Compliance Report" in markdown
        assert "SLA Compliance" in markdown
        assert "✅ COMPLIANT" in markdown
        assert "Recommendations" in markdown
    
    def test_export_csv(self):
        """Test CSV export for safety events."""
        reporter = ComplianceReporter()
        audit = SafetyAuditReport(
            period_days=7,
            events=[
                SafetyEvent(
                    timestamp="2026-01-25T10:00:00",
                    event_type="blocked_query",
                    severity="critical",
                    query_preview="Test query",
                    decision_tag="blocked",
                ),
            ],
        )
        
        csv_str = reporter.export_csv(audit)
        
        assert "Timestamp,Event Type,Severity" in csv_str
        assert "blocked_query" in csv_str
        assert "critical" in csv_str


class TestModuleFunctions:
    """Tests for module-level convenience functions."""
    
    @patch("core.monitoring.compliance_reporting.get_reporter")
    def test_generate_sla_report_function(self, mock_get_reporter):
        """Test generate_sla_report convenience function."""
        mock_reporter = MagicMock()
        mock_reporter.generate_sla_report.return_value = SLAMetrics(period_days=30)
        mock_get_reporter.return_value = mock_reporter
        
        result = generate_sla_report(days=30)
        
        assert isinstance(result, SLAMetrics)
        mock_reporter.generate_sla_report.assert_called_once_with(30)
    
    @patch("core.monitoring.compliance_reporting.get_reporter")
    def test_generate_safety_audit_function(self, mock_get_reporter):
        """Test generate_safety_audit convenience function."""
        mock_reporter = MagicMock()
        mock_reporter.generate_safety_audit.return_value = SafetyAuditReport(period_days=7)
        mock_get_reporter.return_value = mock_reporter
        
        result = generate_safety_audit(days=7)
        
        assert isinstance(result, SafetyAuditReport)
    
    @patch("core.monitoring.compliance_reporting.get_reporter")
    def test_generate_full_report_function(self, mock_get_reporter):
        """Test generate_full_report convenience function."""
        mock_reporter = MagicMock()
        mock_reporter.generate_full_report.return_value = ComplianceReport(
            report_type="full_compliance",
            period_start="2026-01-01",
            period_end="2026-01-25",
        )
        mock_get_reporter.return_value = mock_reporter
        
        result = generate_full_report(days=30)
        
        assert isinstance(result, ComplianceReport)
