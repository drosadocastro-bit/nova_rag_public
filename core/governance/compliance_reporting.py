"""
Compliance Reporting and Incident Tracking.

Provides:
- Incident report generation
- Audit trail tracking
- Compliance metrics
- Automated report generation
"""

import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IncidentSeverity(str, Enum):
    """Incident severity level."""
    
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentCategory(str, Enum):
    """Incident category."""
    
    PERFORMANCE = "performance"
    SAFETY = "safety"
    SECURITY = "security"
    RELIABILITY = "reliability"
    COMPLIANCE = "compliance"
    OTHER = "other"


@dataclass
class IncidentReport:
    """Incident report."""
    
    incident_id: str
    category: IncidentCategory
    severity: IncidentSeverity
    title: str
    description: str
    reported_at: float
    
    # Details
    resource: str  # Model ID, UseCase ID, etc.
    affected_count: int = 0
    
    # Resolution
    resolved_at: Optional[float] = None
    resolution: str = ""
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ComplianceMetrics:
    """Compliance metrics."""
    
    total_incidents: int = 0
    critical_incidents: int = 0
    average_resolution_time: float = 0.0
    availability_percent: float = 100.0
    
    # Safety metrics
    safety_violations: int = 0
    security_violations: int = 0
    performance_violations: int = 0
    
    # Audit metrics
    audit_events: int = 0
    policy_violations: int = 0


class ComplianceReporter:
    """
    Compliance reporting system.
    
    Features:
    - Incident tracking
    - Audit logging
    - Report generation
    - Metrics aggregation
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize compliance reporter.
        
        Args:
            db_path: Path to SQLite database (in-memory if None)
        """
        self.db_path = db_path or ":memory:"
        self._init_db()
        logger.info(f"ComplianceReporter initialized: db={self.db_path}")
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    category TEXT,
                    severity TEXT,
                    title TEXT,
                    description TEXT,
                    reported_at REAL,
                    resource TEXT,
                    affected_count INTEGER,
                    resolved_at REAL,
                    resolution TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    user_id TEXT,
                    resource TEXT,
                    action TEXT,
                    timestamp REAL,
                    status TEXT,
                    details TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compliance_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT,
                    generated_at REAL,
                    period_start REAL,
                    period_end REAL,
                    summary TEXT,
                    metrics TEXT,
                    metrics_json TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incident_severity 
                ON incidents(severity, reported_at DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incident_resource 
                ON incidents(resource)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user 
                ON audit_events(user_id, timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_events(timestamp DESC)
            """)
            
            conn.commit()
    
    def report_incident(
        self,
        category: IncidentCategory,
        severity: IncidentSeverity,
        title: str,
        description: str,
        resource: str,
        affected_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Report an incident."""
        incident_id = f"{category.value}_{int(time.time())}"
        reported_at = time.time()
        
        incident = IncidentReport(
            incident_id=incident_id,
            category=category,
            severity=severity,
            title=title,
            description=description,
            reported_at=reported_at,
            resource=resource,
            affected_count=affected_count,
            metadata=metadata or {},
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO incidents
                (incident_id, category, severity, title, description,
                 reported_at, resource, affected_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident_id, category.value, severity.value, title, description,
                reported_at, resource, affected_count, json.dumps(metadata or {})
            ))
            conn.commit()
        
        logger.warning(
            f"Incident reported: {incident_id} - {title} ({severity.value})"
        )
        return incident_id
    
    def resolve_incident(
        self,
        incident_id: str,
        resolution: str = ""
    ) -> bool:
        """Resolve an incident."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE incidents
                SET resolved_at = ?, resolution = ?
                WHERE incident_id = ?
            """, (time.time(), resolution, incident_id))
            conn.commit()
        
        logger.info(f"Incident resolved: {incident_id}")
        return True
    
    def get_incident(self, incident_id: str) -> Optional[IncidentReport]:
        """Get incident details."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,)
            ).fetchone()
        
        if not row:
            return None
        
        (incident_id, category, severity, title, description, reported_at,
         resource, affected_count, resolved_at, resolution, metadata) = row
        
        return IncidentReport(
            incident_id=incident_id,
            category=IncidentCategory(category),
            severity=IncidentSeverity(severity),
            title=title,
            description=description,
            reported_at=reported_at,
            resource=resource,
            affected_count=affected_count,
            resolved_at=resolved_at,
            resolution=resolution,
            metadata=json.loads(metadata or '{}'),
        )
    
    def list_incidents(
        self,
        severity: Optional[IncidentSeverity] = None,
        resource: Optional[str] = None,
        resolved_only: bool = False,
        limit: int = 100,
    ) -> List[IncidentReport]:
        """List incidents."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM incidents WHERE 1=1"
            params = []
            
            if severity:
                query += " AND severity = ?"
                params.append(severity.value)
            
            if resource:
                query += " AND resource = ?"
                params.append(resource)
            
            if resolved_only:
                query += " AND resolved_at IS NOT NULL"
            else:
                query += " AND resolved_at IS NULL"
            
            query += " ORDER BY reported_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
        
        result = []
        for row in rows:
            (incident_id, category, severity, title, description, reported_at,
             resource, affected_count, resolved_at, resolution, metadata) = row
            
            result.append(IncidentReport(
                incident_id=incident_id,
                category=IncidentCategory(category),
                severity=IncidentSeverity(severity),
                title=title,
                description=description,
                reported_at=reported_at,
                resource=resource,
                affected_count=affected_count,
                resolved_at=resolved_at,
                resolution=resolution,
                metadata=json.loads(metadata or '{}'),
            ))
        
        return result
    
    def log_audit_event(
        self,
        event_type: str,
        user_id: str,
        resource: str,
        action: str,
        status: str = "success",
        details: str = ""
    ) -> None:
        """Log an audit event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_events
                (event_type, user_id, resource, action, timestamp, status, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_type, user_id, resource, action, time.time(), status, details))
            conn.commit()
    
    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit log."""
        with sqlite3.connect(self.db_path) as conn:
            if user_id:
                rows = conn.execute("""
                    SELECT event_type, user_id, resource, action, timestamp, status, details
                    FROM audit_events
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (user_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT event_type, user_id, resource, action, timestamp, status, details
                    FROM audit_events
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "event_type": row[0],
                "user_id": row[1],
                "resource": row[2],
                "action": row[3],
                "timestamp": datetime.fromtimestamp(row[4]).isoformat(),
                "status": row[5],
                "details": row[6],
            })
        
        return result
    
    def get_compliance_metrics(
        self,
        period_days: int = 30
    ) -> ComplianceMetrics:
        """Calculate compliance metrics."""
        cutoff = time.time() - (period_days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            # Total incidents
            total = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE reported_at > ?",
                (cutoff,)
            ).fetchone()[0]
            
            # Critical incidents
            critical = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE severity = ? AND reported_at > ?",
                (IncidentSeverity.CRITICAL.value, cutoff)
            ).fetchone()[0]
            
            # Violations by category
            safety_viol = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE category = ? AND reported_at > ?",
                (IncidentCategory.SAFETY.value, cutoff)
            ).fetchone()[0]
            
            security_viol = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE category = ? AND reported_at > ?",
                (IncidentCategory.SECURITY.value, cutoff)
            ).fetchone()[0]
            
            perf_viol = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE category = ? AND reported_at > ?",
                (IncidentCategory.PERFORMANCE.value, cutoff)
            ).fetchone()[0]
            
            # Audit events
            audit_events = conn.execute(
                "SELECT COUNT(*) FROM audit_events WHERE timestamp > ?",
                (cutoff,)
            ).fetchone()[0]
            
            # Resolution time
            resolved = conn.execute("""
                SELECT AVG(resolved_at - reported_at) FROM incidents
                WHERE resolved_at IS NOT NULL AND reported_at > ?
            """, (cutoff,)).fetchone()[0]
        
        return ComplianceMetrics(
            total_incidents=total,
            critical_incidents=critical,
            safety_violations=safety_viol,
            security_violations=security_viol,
            performance_violations=perf_viol,
            audit_events=audit_events,
            average_resolution_time=resolved or 0.0,
        )
    
    def generate_report(
        self,
        report_type: str = "monthly",
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Generate compliance report."""
        period_start = time.time() - (period_days * 86400)
        period_end = time.time()
        
        metrics = self.get_compliance_metrics(period_days)
        
        report = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "period": {
                "start": datetime.fromtimestamp(period_start).isoformat(),
                "end": datetime.fromtimestamp(period_end).isoformat(),
                "days": period_days,
            },
            "summary": {
                "total_incidents": metrics.total_incidents,
                "critical_incidents": metrics.critical_incidents,
                "violations": {
                    "safety": metrics.safety_violations,
                    "security": metrics.security_violations,
                    "performance": metrics.performance_violations,
                },
                "audit_events": metrics.audit_events,
                "average_resolution_hours": metrics.average_resolution_time / 3600.0,
            },
        }
        
        # Get unresolved incidents
        unresolved = self.list_incidents(resolved_only=False, limit=50)
        report["unresolved_incidents"] = [
            {
                "id": i.incident_id,
                "category": i.category.value,
                "severity": i.severity.value,
                "title": i.title,
                "resource": i.resource,
            }
            for i in unresolved
        ]
        
        # Store report
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO compliance_reports
                (report_type, generated_at, period_start, period_end, metrics_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                report_type, time.time(), period_start, period_end,
                json.dumps(report)
            ))
            conn.commit()
        
        return report
