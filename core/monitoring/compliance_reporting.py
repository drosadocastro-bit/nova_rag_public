"""
Compliance Reporting Module for Nova NIC.

Generates compliance reports for:
    - Safety event auditing
    - SLA compliance metrics
    - Data retention compliance
    - Audit trail generation
    - Incident summaries

Supports multiple output formats: JSON, Markdown, CSV.

Usage:
    from core.monitoring.compliance_reporting import ComplianceReporter
    
    reporter = ComplianceReporter()
    
    # Generate SLA compliance report
    sla_report = reporter.generate_sla_report(days=30)
    
    # Generate safety audit report
    safety_report = reporter.generate_safety_audit(days=7)
    
    # Export to Markdown
    markdown = reporter.export_markdown(sla_report)
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import os

from core.monitoring.logger_config import get_logger

logger = get_logger("core.monitoring.compliance_reporting")

# Database path (same as analytics.py)
BASE_DIR = Path(__file__).resolve().parents[2]
ANALYTICS_DIR = BASE_DIR / "vector_db"
DB_PATH = ANALYTICS_DIR / "analytics.db"
REPORTS_DIR = BASE_DIR / "reports"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SLAMetrics:
    """SLA compliance metrics."""
    period_days: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Uptime
    uptime_percentage: float = 0.0
    uptime_target: float = 99.5
    uptime_compliant: bool = False
    
    # Latency
    avg_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    latency_target_ms: float = 3000.0
    latency_compliant: bool = False
    
    # Error rate
    error_rate: float = 0.0
    error_rate_target: float = 0.01
    error_rate_compliant: bool = False
    
    # Overall
    overall_compliant: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyEvent:
    """Individual safety event for auditing."""
    timestamp: str
    event_type: str
    severity: str
    query_preview: str
    decision_tag: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyAuditReport:
    """Safety audit report."""
    period_days: int = 0
    total_events: int = 0
    blocked_queries: int = 0
    injection_attempts: int = 0
    low_confidence_responses: int = 0
    events: list[SafetyEvent] = field(default_factory=list)
    severity_breakdown: dict[str, int] = field(default_factory=dict)
    event_type_breakdown: dict[str, int] = field(default_factory=dict)
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class DataRetentionReport:
    """Data retention compliance report."""
    total_records: int = 0
    oldest_record: Optional[str] = None
    newest_record: Optional[str] = None
    retention_policy_days: int = 90
    records_within_policy: int = 0
    records_outside_policy: int = 0
    compliant: bool = True
    recommendation: str = ""
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IncidentSummary:
    """Summary of an operational incident."""
    incident_id: str
    start_time: str
    end_time: Optional[str]
    duration_minutes: float
    incident_type: str
    severity: str
    affected_requests: int
    description: str
    resolution: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceReport:
    """Comprehensive compliance report."""
    report_type: str
    period_start: str
    period_end: str
    sla_metrics: Optional[SLAMetrics] = None
    safety_audit: Optional[SafetyAuditReport] = None
    data_retention: Optional[DataRetentionReport] = None
    incidents: list[IncidentSummary] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        result = {
            "report_type": self.report_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at,
        }
        if self.sla_metrics:
            result["sla_metrics"] = self.sla_metrics.to_dict()
        if self.safety_audit:
            result["safety_audit"] = self.safety_audit.to_dict()
        if self.data_retention:
            result["data_retention"] = self.data_retention.to_dict()
        if self.incidents:
            result["incidents"] = [i.to_dict() for i in self.incidents]
        return result


# =============================================================================
# Compliance Reporter
# =============================================================================

class ComplianceReporter:
    """
    Generates compliance reports for auditing and regulatory purposes.
    """
    
    def __init__(
        self,
        uptime_target: float = 99.5,
        latency_target_ms: float = 3000.0,
        error_rate_target: float = 0.01,
        retention_days: int = 90,
    ):
        self.uptime_target = uptime_target
        self.latency_target_ms = latency_target_ms
        self.error_rate_target = error_rate_target
        self.retention_days = retention_days
        
        # Ensure reports directory exists
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    # =========================================================================
    # SLA Compliance
    # =========================================================================
    
    def generate_sla_report(self, days: int = 30) -> SLAMetrics:
        """
        Generate SLA compliance report for the specified period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            SLAMetrics with compliance status
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get overall stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN error IS NULL THEN 1 END) as successful,
                    COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as failed,
                    AVG(response_time_ms) as avg_time
                FROM request_log
                WHERE timestamp > ?
            """, (since,))
            
            stats = cursor.fetchone()
            
            # Get response times for percentile
            cursor.execute("""
                SELECT response_time_ms
                FROM request_log
                WHERE timestamp > ? AND response_time_ms IS NOT NULL
                ORDER BY response_time_ms
            """, (since,))
            
            times = [r["response_time_ms"] for r in cursor.fetchall()]
            conn.close()
            
            total = stats["total"] or 0
            successful = stats["successful"] or 0
            failed = stats["failed"] or 0
            avg_time = stats["avg_time"] or 0
            
            # Calculate metrics
            uptime_pct = (successful / total * 100) if total > 0 else 100.0
            error_rate = (failed / total) if total > 0 else 0.0
            p95_time = times[int(len(times) * 0.95)] if times else 0
            
            # Check compliance
            uptime_ok = uptime_pct >= self.uptime_target
            latency_ok = p95_time <= self.latency_target_ms
            error_ok = error_rate <= self.error_rate_target
            
            return SLAMetrics(
                period_days=days,
                total_requests=total,
                successful_requests=successful,
                failed_requests=failed,
                uptime_percentage=round(uptime_pct, 3),
                uptime_target=self.uptime_target,
                uptime_compliant=uptime_ok,
                avg_response_time_ms=round(avg_time, 2),
                p95_response_time_ms=p95_time,
                latency_target_ms=self.latency_target_ms,
                latency_compliant=latency_ok,
                error_rate=round(error_rate, 4),
                error_rate_target=self.error_rate_target,
                error_rate_compliant=error_ok,
                overall_compliant=uptime_ok and latency_ok and error_ok,
            )
            
        except Exception as e:
            logger.error(f"Failed to generate SLA report: {e}")
            return SLAMetrics(period_days=days)
    
    # =========================================================================
    # Safety Audit
    # =========================================================================
    
    def generate_safety_audit(self, days: int = 7, include_events: bool = True) -> SafetyAuditReport:
        """
        Generate safety audit report.
        
        Args:
            days: Number of days to analyze
            include_events: Whether to include individual event details
            
        Returns:
            SafetyAuditReport with safety event analysis
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get safety-related queries
            cursor.execute("""
                SELECT 
                    timestamp,
                    question,
                    decision_tag,
                    heuristic_trigger,
                    confidence,
                    error
                FROM request_log
                WHERE timestamp > ?
                  AND (decision_tag IS NOT NULL 
                       OR confidence < 0.5 
                       OR error IS NOT NULL)
                ORDER BY timestamp DESC
            """, (since,))
            
            rows = cursor.fetchall()
            conn.close()
            
            events: list[SafetyEvent] = []
            severity_breakdown: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
            event_type_breakdown: dict[str, int] = {}
            
            blocked_count = 0
            injection_count = 0
            low_conf_count = 0
            
            for row in rows:
                # Determine event type and severity
                decision_tag = row["decision_tag"] or ""
                confidence = row["confidence"] or 1.0
                
                if "blocked" in decision_tag.lower():
                    event_type = "blocked_query"
                    severity = "critical"
                    blocked_count += 1
                elif "injection" in decision_tag.lower():
                    event_type = "injection_attempt"
                    severity = "critical"
                    injection_count += 1
                elif confidence < 0.3:
                    event_type = "low_confidence"
                    severity = "warning"
                    low_conf_count += 1
                elif confidence < 0.5:
                    event_type = "low_confidence"
                    severity = "info"
                    low_conf_count += 1
                elif row["error"]:
                    event_type = "error"
                    severity = "warning"
                else:
                    event_type = "safety_decision"
                    severity = "info"
                
                severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1
                event_type_breakdown[event_type] = event_type_breakdown.get(event_type, 0) + 1
                
                if include_events:
                    events.append(SafetyEvent(
                        timestamp=row["timestamp"],
                        event_type=event_type,
                        severity=severity,
                        query_preview=row["question"][:100] if row["question"] else "",
                        decision_tag=decision_tag or None,
                        details={
                            "confidence": confidence,
                            "trigger": row["heuristic_trigger"],
                        },
                    ))
            
            return SafetyAuditReport(
                period_days=days,
                total_events=len(rows),
                blocked_queries=blocked_count,
                injection_attempts=injection_count,
                low_confidence_responses=low_conf_count,
                events=events[:100],  # Limit to 100 events
                severity_breakdown=severity_breakdown,
                event_type_breakdown=event_type_breakdown,
            )
            
        except Exception as e:
            logger.error(f"Failed to generate safety audit: {e}")
            return SafetyAuditReport(period_days=days)
    
    # =========================================================================
    # Data Retention
    # =========================================================================
    
    def generate_retention_report(self) -> DataRetentionReport:
        """
        Generate data retention compliance report.
        
        Returns:
            DataRetentionReport with retention analysis
        """
        cutoff = (datetime.now() - timedelta(days=self.retention_days)).isoformat()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get total records
            cursor.execute("SELECT COUNT(*) as total FROM request_log")
            total = cursor.fetchone()["total"]
            
            # Get date range
            cursor.execute("""
                SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest
                FROM request_log
            """)
            dates = cursor.fetchone()
            
            # Count records within/outside policy
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN timestamp >= ? THEN 1 END) as within_policy,
                    COUNT(CASE WHEN timestamp < ? THEN 1 END) as outside_policy
                FROM request_log
            """, (cutoff, cutoff))
            
            policy = cursor.fetchone()
            conn.close()
            
            within = policy["within_policy"] or 0
            outside = policy["outside_policy"] or 0
            compliant = outside == 0
            
            recommendation = ""
            if outside > 0:
                recommendation = f"Consider purging {outside} records older than {self.retention_days} days to comply with retention policy."
            
            return DataRetentionReport(
                total_records=total,
                oldest_record=dates["oldest"],
                newest_record=dates["newest"],
                retention_policy_days=self.retention_days,
                records_within_policy=within,
                records_outside_policy=outside,
                compliant=compliant,
                recommendation=recommendation,
            )
            
        except Exception as e:
            logger.error(f"Failed to generate retention report: {e}")
            return DataRetentionReport(retention_policy_days=self.retention_days)
    
    # =========================================================================
    # Full Compliance Report
    # =========================================================================
    
    def generate_full_report(self, days: int = 30) -> ComplianceReport:
        """
        Generate comprehensive compliance report.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            ComplianceReport with all compliance data
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Generate all sub-reports
        sla = self.generate_sla_report(days)
        safety = self.generate_safety_audit(days, include_events=False)
        retention = self.generate_retention_report()
        
        # Generate recommendations
        recommendations = []
        
        if not sla.uptime_compliant:
            recommendations.append(
                f"Uptime {sla.uptime_percentage:.2f}% is below target {sla.uptime_target}%. "
                "Investigate error causes and improve reliability."
            )
        
        if not sla.latency_compliant:
            recommendations.append(
                f"P95 latency {sla.p95_response_time_ms:.0f}ms exceeds target {sla.latency_target_ms:.0f}ms. "
                "Consider optimization or infrastructure scaling."
            )
        
        if safety.blocked_queries > 0:
            recommendations.append(
                f"{safety.blocked_queries} queries were blocked by safety filters. "
                "Review blocked queries for false positives."
            )
        
        if safety.injection_attempts > 0:
            recommendations.append(
                f"{safety.injection_attempts} injection attempts detected. "
                "Monitor for attack patterns and strengthen input validation."
            )
        
        if not retention.compliant:
            recommendations.append(retention.recommendation)
        
        return ComplianceReport(
            report_type="full_compliance",
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            sla_metrics=sla,
            safety_audit=safety,
            data_retention=retention,
            recommendations=recommendations,
        )
    
    # =========================================================================
    # Export Functions
    # =========================================================================
    
    def export_json(self, report: ComplianceReport, filepath: Optional[Path] = None) -> str:
        """
        Export report to JSON.
        
        Args:
            report: ComplianceReport to export
            filepath: Optional path to save file
            
        Returns:
            JSON string
        """
        json_str = json.dumps(report.to_dict(), indent=2)
        
        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(json_str, encoding="utf-8")
            logger.info(f"Exported compliance report to {filepath}")
        
        return json_str
    
    def export_markdown(self, report: ComplianceReport, filepath: Optional[Path] = None) -> str:
        """
        Export report to Markdown.
        
        Args:
            report: ComplianceReport to export
            filepath: Optional path to save file
            
        Returns:
            Markdown string
        """
        lines = [
            f"# Compliance Report",
            f"",
            f"**Report Type:** {report.report_type}",
            f"**Period:** {report.period_start} to {report.period_end}",
            f"**Generated:** {report.generated_at}",
            f"",
        ]
        
        # SLA Section
        if report.sla_metrics:
            sla = report.sla_metrics
            status = "✅ COMPLIANT" if sla.overall_compliant else "❌ NON-COMPLIANT"
            lines.extend([
                f"## SLA Compliance {status}",
                f"",
                f"| Metric | Value | Target | Status |",
                f"|--------|-------|--------|--------|",
                f"| Uptime | {sla.uptime_percentage:.2f}% | {sla.uptime_target}% | {'✅' if sla.uptime_compliant else '❌'} |",
                f"| P95 Latency | {sla.p95_response_time_ms:.0f}ms | {sla.latency_target_ms:.0f}ms | {'✅' if sla.latency_compliant else '❌'} |",
                f"| Error Rate | {sla.error_rate*100:.2f}% | {sla.error_rate_target*100:.1f}% | {'✅' if sla.error_rate_compliant else '❌'} |",
                f"",
                f"**Total Requests:** {sla.total_requests:,}",
                f"",
            ])
        
        # Safety Section
        if report.safety_audit:
            safety = report.safety_audit
            lines.extend([
                f"## Safety Audit",
                f"",
                f"| Metric | Count |",
                f"|--------|-------|",
                f"| Total Events | {safety.total_events} |",
                f"| Blocked Queries | {safety.blocked_queries} |",
                f"| Injection Attempts | {safety.injection_attempts} |",
                f"| Low Confidence Responses | {safety.low_confidence_responses} |",
                f"",
            ])
            
            if safety.severity_breakdown:
                lines.extend([
                    f"### Severity Breakdown",
                    f"",
                ])
                for severity, count in safety.severity_breakdown.items():
                    lines.append(f"- **{severity.title()}:** {count}")
                lines.append("")
        
        # Data Retention Section
        if report.data_retention:
            ret = report.data_retention
            status = "✅ COMPLIANT" if ret.compliant else "❌ NON-COMPLIANT"
            lines.extend([
                f"## Data Retention {status}",
                f"",
                f"- **Total Records:** {ret.total_records:,}",
                f"- **Retention Policy:** {ret.retention_policy_days} days",
                f"- **Records Within Policy:** {ret.records_within_policy:,}",
                f"- **Records Outside Policy:** {ret.records_outside_policy:,}",
                f"",
            ])
            
            if ret.recommendation:
                lines.append(f"**Recommendation:** {ret.recommendation}")
                lines.append("")
        
        # Recommendations Section
        if report.recommendations:
            lines.extend([
                f"## Recommendations",
                f"",
            ])
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")
        
        markdown = "\n".join(lines)
        
        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(markdown, encoding="utf-8")
            logger.info(f"Exported compliance report to {filepath}")
        
        return markdown
    
    def export_csv(self, safety_audit: SafetyAuditReport, filepath: Optional[Path] = None) -> str:
        """
        Export safety events to CSV.
        
        Args:
            safety_audit: SafetyAuditReport with events
            filepath: Optional path to save file
            
        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Timestamp", "Event Type", "Severity", "Query Preview", "Decision Tag"])
        
        # Events
        for event in safety_audit.events:
            writer.writerow([
                event.timestamp,
                event.event_type,
                event.severity,
                event.query_preview,
                event.decision_tag or "",
            ])
        
        csv_str = output.getvalue()
        
        if filepath:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(csv_str, encoding="utf-8")
            logger.info(f"Exported safety events to {filepath}")
        
        return csv_str
    
    def save_report(self, report: ComplianceReport, name_prefix: str = "compliance") -> dict[str, Path]:
        """
        Save report in multiple formats.
        
        Args:
            report: ComplianceReport to save
            name_prefix: Prefix for filename
            
        Returns:
            Dictionary of format -> filepath
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{name_prefix}_{timestamp}"
        
        paths = {}
        
        # JSON
        json_path = REPORTS_DIR / f"{base_name}.json"
        self.export_json(report, json_path)
        paths["json"] = json_path
        
        # Markdown
        md_path = REPORTS_DIR / f"{base_name}.md"
        self.export_markdown(report, md_path)
        paths["markdown"] = md_path
        
        logger.info(f"Saved compliance report: {paths}")
        return paths


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_reporter: Optional[ComplianceReporter] = None


def get_reporter() -> ComplianceReporter:
    """Get or create the default compliance reporter."""
    global _default_reporter
    if _default_reporter is None:
        _default_reporter = ComplianceReporter()
    return _default_reporter


def generate_sla_report(days: int = 30) -> SLAMetrics:
    """Convenience function to generate SLA report."""
    return get_reporter().generate_sla_report(days)


def generate_safety_audit(days: int = 7) -> SafetyAuditReport:
    """Convenience function to generate safety audit."""
    return get_reporter().generate_safety_audit(days)


def generate_full_report(days: int = 30) -> ComplianceReport:
    """Convenience function to generate full compliance report."""
    return get_reporter().generate_full_report(days)
