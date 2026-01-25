"""
SLA Management and Performance Tracking.

Provides:
- SLA definition and tracking
- Response time targets
- Availability targets
- Incident escalation procedures
"""

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SLAStatus(str, Enum):
    """SLA compliance status."""
    
    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


@dataclass
class SLAMetrics:
    """SLA performance metrics."""
    
    # Response time metrics (in milliseconds)
    response_time_p50: float = 0.0  # Median
    response_time_p95: float = 0.0  # 95th percentile
    response_time_p99: float = 0.0  # 99th percentile
    
    # Availability metrics
    availability_percent: float = 100.0
    uptime_seconds: int = 0
    downtime_seconds: int = 0
    
    # Error metrics
    error_rate: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    
    # Incident metrics
    incidents_total: int = 0
    incidents_critical: int = 0
    incidents_mean_resolution_hours: float = 0.0
    
    # Timestamp
    measured_at: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class SLATarget:
    """SLA target for a resource."""
    
    # Identification
    resource_id: str
    resource_type: str  # "model", "usecase", "system"
    
    # Response time targets (milliseconds)
    response_time_p95_target: float = 500.0
    response_time_p99_target: float = 1000.0
    
    # Availability targets (percentage)
    availability_target: float = 99.9
    maximum_downtime_hours_monthly: float = 0.43  # 99.9% availability
    
    # Error rate target (percentage)
    error_rate_target: float = 0.1
    
    # Incident response targets
    critical_incident_response_minutes: int = 15
    critical_incident_resolution_hours: int = 4
    
    # Created/updated
    created_at: float = 0.0
    updated_at: float = 0.0
    updated_by: str = "system"
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class SLAManager:
    """
    SLA management system.
    
    Features:
    - SLA definition and tracking
    - Response time monitoring
    - Availability tracking
    - Incident escalation
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SLA manager.
        
        Args:
            db_path: Path to SQLite database (in-memory if None)
        """
        self.db_path = db_path or ":memory:"
        self._init_db()
        logger.info(f"SLAManager initialized: db={self.db_path}")
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sla_targets (
                    resource_id TEXT,
                    resource_type TEXT,
                    response_time_p95 REAL,
                    response_time_p99 REAL,
                    availability_target REAL,
                    max_downtime_hours REAL,
                    error_rate_target REAL,
                    incident_response_minutes INTEGER,
                    incident_resolution_hours INTEGER,
                    created_at REAL,
                    updated_at REAL,
                    updated_by TEXT,
                    metadata TEXT,
                    PRIMARY KEY (resource_id, resource_type)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sla_measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT,
                    resource_type TEXT,
                    measured_at REAL,
                    response_time_p50 REAL,
                    response_time_p95 REAL,
                    response_time_p99 REAL,
                    availability_percent REAL,
                    uptime_seconds INTEGER,
                    downtime_seconds INTEGER,
                    error_rate REAL,
                    total_requests INTEGER,
                    failed_requests INTEGER,
                    incidents_total INTEGER,
                    incidents_critical INTEGER,
                    incidents_mean_resolution REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sla_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT,
                    resource_type TEXT,
                    violation_type TEXT,
                    violation_at REAL,
                    target_value REAL,
                    actual_value REAL,
                    severity TEXT,
                    acknowledged BOOLEAN DEFAULT 0,
                    acknowledged_at REAL,
                    acknowledged_by TEXT,
                    resolution_notes TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS escalation_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT,
                    violation_type TEXT,
                    threshold INTEGER,
                    escalation_level TEXT,
                    notify_users TEXT,
                    notify_teams TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sla_violations 
                ON sla_violations(resource_id, violation_at DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sla_measurements 
                ON sla_measurements(resource_id, measured_at DESC)
            """)
            
            conn.commit()
    
    def define_sla(
        self,
        resource_id: str,
        resource_type: str,
        response_time_p95: float = 500.0,
        response_time_p99: float = 1000.0,
        availability_target: float = 99.9,
        error_rate_target: float = 0.1,
        incident_response_minutes: int = 15,
        incident_resolution_hours: int = 4,
        updated_by: str = "system",
    ) -> SLATarget:
        """Define SLA for a resource."""
        
        now = time.time()
        target = SLATarget(
            resource_id=resource_id,
            resource_type=resource_type,
            response_time_p95_target=response_time_p95,
            response_time_p99_target=response_time_p99,
            availability_target=availability_target,
            error_rate_target=error_rate_target,
            critical_incident_response_minutes=incident_response_minutes,
            critical_incident_resolution_hours=incident_resolution_hours,
            created_at=now,
            updated_at=now,
            updated_by=updated_by,
        )
        
        # Calculate monthly downtime allowance
        uptime_fraction = availability_target / 100.0
        downtime_fraction = 1.0 - uptime_fraction
        monthly_minutes = 30 * 24 * 60
        target.maximum_downtime_hours_monthly = (downtime_fraction * monthly_minutes) / 60.0
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sla_targets
                (resource_id, resource_type, response_time_p95, response_time_p99,
                 availability_target, max_downtime_hours, error_rate_target,
                 incident_response_minutes, incident_resolution_hours,
                 created_at, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                resource_id, resource_type, response_time_p95, response_time_p99,
                availability_target, target.maximum_downtime_hours_monthly,
                error_rate_target, incident_response_minutes,
                incident_resolution_hours, target.created_at, target.updated_at,
                updated_by
            ))
            conn.commit()
        
        logger.info(f"Defined SLA for {resource_type}:{resource_id}")
        return target
    
    def get_sla_target(
        self,
        resource_id: str,
        resource_type: str
    ) -> Optional[SLATarget]:
        """Get SLA target for a resource."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT * FROM sla_targets
                WHERE resource_id = ? AND resource_type = ?
            """, (resource_id, resource_type)).fetchone()
        
        if not row:
            return None
        
        (res_id, res_type, p95, p99, avail_target, max_downtime,
         error_target, incident_resp, incident_res, created, updated, updated_by) = row
        
        return SLATarget(
            resource_id=res_id,
            resource_type=res_type,
            response_time_p95_target=p95,
            response_time_p99_target=p99,
            availability_target=avail_target,
            error_rate_target=error_target,
            critical_incident_response_minutes=incident_resp,
            critical_incident_resolution_hours=incident_res,
            created_at=created,
            updated_at=updated,
            updated_by=updated_by,
        )
    
    def record_measurement(
        self,
        resource_id: str,
        resource_type: str,
        metrics: SLAMetrics
    ) -> str:
        """Record SLA measurement and check violations."""
        
        # Get SLA target
        target = self.get_sla_target(resource_id, resource_type)
        if not target:
            logger.warning(f"No SLA defined for {resource_type}:{resource_id}")
            return ""
        
        metrics.measured_at = time.time()
        
        # Record measurement
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sla_measurements
                (resource_id, resource_type, measured_at,
                 response_time_p50, response_time_p95, response_time_p99,
                 availability_percent, uptime_seconds, downtime_seconds,
                 error_rate, total_requests, failed_requests,
                 incidents_total, incidents_critical, incidents_mean_resolution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                resource_id, resource_type, metrics.measured_at,
                metrics.response_time_p50, metrics.response_time_p95,
                metrics.response_time_p99, metrics.availability_percent,
                metrics.uptime_seconds, metrics.downtime_seconds,
                metrics.error_rate, metrics.total_requests,
                metrics.failed_requests, metrics.incidents_total,
                metrics.incidents_critical,
                metrics.incidents_mean_resolution_hours
            ))
        
        # Check for violations
        violations = []
        
        if metrics.response_time_p95 > target.response_time_p95_target:
            violations.append(("response_time_p95", target.response_time_p95_target, metrics.response_time_p95))
        
        if metrics.response_time_p99 > target.response_time_p99_target:
            violations.append(("response_time_p99", target.response_time_p99_target, metrics.response_time_p99))
        
        if metrics.availability_percent < target.availability_target:
            violations.append(("availability", target.availability_target, metrics.availability_percent))
        
        if metrics.error_rate > target.error_rate_target:
            violations.append(("error_rate", target.error_rate_target, metrics.error_rate))
        
        # Record violations
        for vtype, target_val, actual_val in violations:
            self.record_violation(
                resource_id, resource_type, vtype, target_val, actual_val
            )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.commit()
        
        return resource_id
    
    def record_violation(
        self,
        resource_id: str,
        resource_type: str,
        violation_type: str,
        target_value: float,
        actual_value: float,
        severity: str = "warning"
    ) -> None:
        """Record SLA violation."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sla_violations
                (resource_id, resource_type, violation_type, violation_at,
                 target_value, actual_value, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                resource_id, resource_type, violation_type, time.time(),
                target_value, actual_value, severity
            ))
            conn.commit()
        
        logger.warning(
            f"SLA violation: {resource_type}:{resource_id} - "
            f"{violation_type} ({actual_value} > {target_value})"
        )
    
    def get_sla_status(
        self,
        resource_id: str,
        resource_type: str,
        hours: int = 24
    ) -> SLAStatus:
        """Get current SLA status for a resource."""
        
        cutoff = time.time() - (hours * 3600)
        
        with sqlite3.connect(self.db_path) as conn:
            violations = conn.execute("""
                SELECT COUNT(*) FROM sla_violations
                WHERE resource_id = ? AND resource_type = ? AND violation_at > ?
            """, (resource_id, resource_type, cutoff)).fetchone()[0]
        
        if violations == 0:
            return SLAStatus.COMPLIANT
        elif violations < 5:
            return SLAStatus.AT_RISK
        else:
            return SLAStatus.VIOLATED
    
    def get_violations(
        self,
        resource_id: Optional[str] = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get SLA violations."""
        
        cutoff = time.time() - (hours * 3600)
        
        with sqlite3.connect(self.db_path) as conn:
            if resource_id:
                rows = conn.execute("""
                    SELECT * FROM sla_violations
                    WHERE resource_id = ? AND violation_at > ?
                    ORDER BY violation_at DESC
                    LIMIT ?
                """, (resource_id, cutoff, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM sla_violations
                    WHERE violation_at > ?
                    ORDER BY violation_at DESC
                    LIMIT ?
                """, (cutoff, limit)).fetchall()
        
        result = []
        for row in rows:
            (vid, res_id, res_type, vtype, violation_at, target_val,
             actual_val, severity, acked, acked_at, acked_by, notes) = row
            
            result.append({
                "id": vid,
                "resource_id": res_id,
                "resource_type": res_type,
                "violation_type": vtype,
                "timestamp": datetime.fromtimestamp(violation_at).isoformat(),
                "target": target_val,
                "actual": actual_val,
                "severity": severity,
                "acknowledged": acked,
                "acknowledged_at": datetime.fromtimestamp(acked_at).isoformat() if acked_at else None,
                "notes": notes,
            })
        
        return result
    
    def acknowledge_violation(
        self,
        violation_id: int,
        acknowledged_by: str,
        notes: str = ""
    ) -> bool:
        """Acknowledge an SLA violation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE sla_violations
                SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ?, resolution_notes = ?
                WHERE id = ?
            """, (time.time(), acknowledged_by, notes, violation_id))
            conn.commit()
        
        return True
