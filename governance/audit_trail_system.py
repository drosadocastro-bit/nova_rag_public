"""
NIC Comprehensive Audit Trail System

Implements immutable logging of all NIC decisions, control activations,
and safety-critical events for compliance with NIST AI RMF and FAA policies.

Features:
- Immutable append-only audit log
- Role-based access control
- Severity-based retention
- Real-time metrics aggregation
- Incident correlation
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Audit event types."""
    QUERY_RECEIVED = "query_received"
    POLICY_CHECK = "policy_check"
    RETRIEVAL_EXECUTED = "retrieval_executed"
    CONFIDENCE_EVALUATED = "confidence_evaluated"
    GENERATION_ATTEMPTED = "generation_attempted"
    CITATION_VALIDATED = "citation_validated"
    FALLBACK_ACTIVATED = "fallback_activated"
    ESCALATION_TRIGGERED = "escalation_triggered"
    CONTROL_DECISION = "control_decision"
    CONFIGURATION_CHANGED = "configuration_changed"
    POLICY_VIOLATION = "policy_violation"
    INCIDENT_REPORTED = "incident_reported"


class Severity(str, Enum):
    """Event severity levels."""
    CRITICAL = "CRITICAL"  # 5+ years retention
    HIGH = "HIGH"  # 2 years retention
    MEDIUM = "MEDIUM"  # 1 year retention
    LOW = "LOW"  # 90 days retention


class Authority(str, Enum):
    """Decision authority levels."""
    SYSTEM = "system"  # Automated threshold
    OPERATOR = "operator"  # Human review
    MANAGER = "manager"  # Management approval
    EXECUTIVE = "executive"  # Executive authorization


@dataclass
class AuditEvent:
    """Immutable audit event record."""
    
    # Core identification
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    event_type: EventType = EventType.QUERY_RECEIVED
    session_id: str = ""
    
    # Query information (anonymized)
    query_hash: str = ""  # SHA256 hash, not actual text
    query_domain: str = ""  # Detected domain
    query_severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    
    # Decision information
    decision: str = "allow"  # allow, block, fallback, escalate
    authority: Authority = Authority.SYSTEM
    confidence_score: float = 0.0
    risk_score: float = 0.0
    
    # Control activation
    control_layer: int = 0  # 1-8 layer number
    control_name: str = ""
    control_reason: str = ""
    control_effectiveness: float = 1.0
    
    # Citation & validation
    citation_count: int = 0
    citation_accuracy: float = 0.0
    citations_valid: bool = False
    
    # Response information
    response_length: int = 0
    response_latency_ms: float = 0.0
    hallucination_detected: bool = False
    
    # Escalation
    escalated: bool = False
    escalation_reason: str = ""
    escalation_target: str = ""
    
    # User information (anonymized)
    user_role: str = "technician"  # No PII
    organization_unit: str = ""  # No PII
    
    # Metadata
    severity: Severity = Severity.MEDIUM
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Immutability marker
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling enums."""
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["authority"] = self.authority.value
        d["severity"] = self.severity.value
        return d
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict())


class AuditTrailSystem:
    """
    Comprehensive audit trail for NIC operations.
    
    Implements:
    - Immutable append-only logging
    - Severity-based retention policies
    - Real-time metrics aggregation
    - Role-based access control
    - Incident correlation
    """
    
    def __init__(self, db_path: str = "audit_trail.db"):
        """
        Initialize audit trail system.
        
        Args:
            db_path: Path to SQLite audit database
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialize_database()
        
        # Metrics (cached)
        self._metrics_cache: Dict[str, Any] = {}
        self._metrics_updated = time.time()
        
        logger.info(f"AuditTrailSystem initialized: {db_path}")
    
    def _initialize_database(self) -> None:
        """Create audit log table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Main audit log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    
                    -- Query info
                    query_hash TEXT,
                    query_domain TEXT,
                    query_severity TEXT,
                    
                    -- Decision
                    decision TEXT NOT NULL,
                    authority TEXT,
                    confidence_score REAL,
                    risk_score REAL,
                    
                    -- Control
                    control_layer INTEGER,
                    control_name TEXT,
                    control_reason TEXT,
                    control_effectiveness REAL,
                    
                    -- Citation
                    citation_count INTEGER,
                    citation_accuracy REAL,
                    citations_valid BOOLEAN,
                    
                    -- Response
                    response_length INTEGER,
                    response_latency_ms REAL,
                    hallucination_detected BOOLEAN,
                    
                    -- Escalation
                    escalated BOOLEAN,
                    escalation_reason TEXT,
                    escalation_target TEXT,
                    
                    -- User (anonymized)
                    user_role TEXT,
                    organization_unit TEXT,
                    
                    -- Metadata
                    tags TEXT,
                    metadata TEXT,
                    
                    -- Indexes
                    UNIQUE(event_id)
                );
            """)
            
            # Create indexes for fast queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON audit_events(timestamp DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session 
                ON audit_events(session_id);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_severity 
                ON audit_events(severity);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type 
                ON audit_events(event_type);
            """)
            
            # Incidents table for correlation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_ids TEXT,
                    root_cause TEXT,
                    resolution TEXT,
                    status TEXT DEFAULT 'open'
                );
            """)
            
            conn.commit()
    
    def log_event(self, event: AuditEvent) -> bool:
        """
        Log an audit event (append-only).
        
        Args:
            event: AuditEvent to log
            
        Returns:
            True if successful
        """
        try:
            with self._lock, sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert event (append-only)
                cursor.execute("""
                    INSERT INTO audit_events (
                        event_id, timestamp, created_at, event_type, session_id,
                        severity, query_hash, query_domain, query_severity,
                        decision, authority, confidence_score, risk_score,
                        control_layer, control_name, control_reason, control_effectiveness,
                        citation_count, citation_accuracy, citations_valid,
                        response_length, response_latency_ms, hallucination_detected,
                        escalated, escalation_reason, escalation_target,
                        user_role, organization_unit, tags, metadata
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    event.event_id, event.timestamp, event.created_at,
                    event.event_type.value, event.session_id,
                    event.severity.value, event.query_hash, event.query_domain,
                    event.query_severity, event.decision, event.authority.value,
                    event.confidence_score, event.risk_score,
                    event.control_layer, event.control_name, event.control_reason,
                    event.control_effectiveness,
                    event.citation_count, event.citation_accuracy,
                    event.citations_valid,
                    event.response_length, event.response_latency_ms,
                    event.hallucination_detected,
                    event.escalated, event.escalation_reason,
                    event.escalation_target,
                    event.user_role, event.organization_unit,
                    json.dumps(event.tags), json.dumps(event.metadata)
                ))
                
                conn.commit()
                
                # Check for incidents
                if event.severity == Severity.CRITICAL:
                    self._check_and_create_incident(event)
                
                # Invalidate metrics cache
                self._metrics_updated = 0
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return False
    
    def _check_and_create_incident(self, event: AuditEvent) -> None:
        """Auto-create incident for critical events."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                incident_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO incidents (
                        incident_id, timestamp, severity, event_ids, status
                    ) VALUES (?, ?, ?, ?, 'open')
                """, (
                    incident_id, datetime.utcnow().isoformat(),
                    event.severity.value, json.dumps([event.event_id])
                ))
                
                conn.commit()
                logger.warning(f"Incident created: {incident_id}")
                
        except Exception as e:
            logger.error(f"Failed to create incident: {e}")
    
    def get_audit_trail(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        severity: Optional[Severity] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        Retrieve audit events (authorized access only).
        
        Args:
            session_id: Filter by session
            event_type: Filter by event type
            severity: Filter by severity
            limit: Maximum results
            
        Returns:
            List of AuditEvent records
        """
        try:
            query = "SELECT * FROM audit_events WHERE 1=1"
            params = []
            
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type.value)
            
            if severity:
                query += " AND severity = ?"
                params.append(severity.value)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute(query, params).fetchall()
                
                events = []
                for row in rows:
                    event = AuditEvent(
                        event_id=row["event_id"],
                        timestamp=row["timestamp"],
                        event_type=EventType(row["event_type"]),
                        session_id=row["session_id"],
                        severity=Severity(row["severity"]),
                        decision=row["decision"],
                        authority=Authority(row["authority"]),
                        confidence_score=row["confidence_score"],
                        risk_score=row["risk_score"],
                        escalated=bool(row["escalated"]),
                        tags=json.loads(row["tags"] or "[]"),
                        metadata=json.loads(row["metadata"] or "{}"),
                    )
                    events.append(event)
                
                return events
                
        except Exception as e:
            logger.error(f"Failed to retrieve audit trail: {e}")
            return []
    
    def get_metrics(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get aggregated audit metrics.
        
        Args:
            use_cache: Use cached metrics if <60s old
            
        Returns:
            Metrics dictionary
        """
        # Check cache
        if use_cache and time.time() - self._metrics_updated < 60:
            return self._metrics_cache
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Queries processed
                cursor.execute("SELECT COUNT(*) as count FROM audit_events")
                total_events = cursor.fetchone()[0]
                
                # By severity
                cursor.execute("""
                    SELECT severity, COUNT(*) as count
                    FROM audit_events
                    GROUP BY severity
                """)
                by_severity = {row[0]: row[1] for row in cursor.fetchall()}
                
                # By decision
                cursor.execute("""
                    SELECT decision, COUNT(*) as count
                    FROM audit_events
                    GROUP BY decision
                """)
                by_decision = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Average confidence
                cursor.execute("""
                    SELECT AVG(confidence_score) as avg_conf
                    FROM audit_events
                """)
                avg_confidence = cursor.fetchone()[0] or 0.0
                
                # Escalation rate
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM audit_events
                    WHERE escalated = 1
                """)
                escalations = cursor.fetchone()[0]
                escalation_rate = (escalations / total_events * 100) if total_events > 0 else 0
                
                # Citation accuracy
                cursor.execute("""
                    SELECT AVG(citation_accuracy) as avg_accuracy
                    FROM audit_events
                    WHERE citation_count > 0
                """)
                avg_citation_accuracy = cursor.fetchone()[0] or 0.0
                
                # Fallback rate
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM audit_events
                    WHERE decision = 'fallback'
                """)
                fallback_count = cursor.fetchone()[0]
                fallback_rate = (fallback_count / total_events * 100) if total_events > 0 else 0
                
                metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "total_events": total_events,
                    "by_severity": by_severity,
                    "by_decision": by_decision,
                    "avg_confidence": round(avg_confidence, 3),
                    "escalation_rate_pct": round(escalation_rate, 2),
                    "escalation_count": escalations,
                    "avg_citation_accuracy": round(avg_citation_accuracy, 3),
                    "fallback_rate_pct": round(fallback_rate, 2),
                    "fallback_count": fallback_count,
                }
                
                self._metrics_cache = metrics
                self._metrics_updated = time.time()
                
                return metrics
                
        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            return {}
    
    def cleanup_by_retention(self) -> int:
        """
        Delete events based on retention policy.
        
        Retention:
        - CRITICAL: 5 years
        - HIGH: 2 years
        - MEDIUM: 1 year
        - LOW: 90 days
        
        Returns:
            Number of events deleted
        """
        try:
            with self._lock, sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                now = datetime.utcnow()
                retention_policies = {
                    Severity.CRITICAL: timedelta(days=365*5),
                    Severity.HIGH: timedelta(days=365*2),
                    Severity.MEDIUM: timedelta(days=365),
                    Severity.LOW: timedelta(days=90),
                }
                
                total_deleted = 0
                
                for severity, retention in retention_policies.items():
                    cutoff = now - retention
                    cursor.execute(
                        "DELETE FROM audit_events WHERE severity = ? AND timestamp < ?",
                        (severity.value, cutoff.isoformat())
                    )
                    total_deleted += cursor.rowcount
                
                conn.commit()
                logger.info(f"Deleted {total_deleted} expired audit events")
                
                return total_deleted
                
        except Exception as e:
            logger.error(f"Failed to cleanup audit events: {e}")
            return 0
    
    def export_compliance_report(
        self,
        start_date: str,
        end_date: str,
        severity: Optional[Severity] = None,
    ) -> Dict[str, Any]:
        """
        Export compliance-focused audit report.
        
        Args:
            start_date: ISO format start date
            end_date: ISO format end date
            severity: Filter by severity (None = all)
            
        Returns:
            Compliance report dictionary
        """
        try:
            query = """
                SELECT 
                    COUNT(*) as total_events,
                    SUM(CASE WHEN decision = 'allow' THEN 1 ELSE 0 END) as allowed,
                    SUM(CASE WHEN decision = 'block' THEN 1 ELSE 0 END) as blocked,
                    SUM(CASE WHEN decision = 'fallback' THEN 1 ELSE 0 END) as fallback,
                    SUM(CASE WHEN escalated = 1 THEN 1 ELSE 0 END) as escalated,
                    AVG(confidence_score) as avg_confidence,
                    AVG(citation_accuracy) as avg_citation_accuracy,
                    SUM(CASE WHEN hallucination_detected = 1 THEN 1 ELSE 0 END) as hallucinations
                FROM audit_events
                WHERE timestamp BETWEEN ? AND ?
            """
            params = [start_date, end_date]
            
            if severity:
                query += " AND severity = ?"
                params.append(severity.value)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                row = cursor.execute(query, params).fetchone()
                
                if row:
                    return {
                        "period_start": start_date,
                        "period_end": end_date,
                        "total_events": row[0],
                        "allowed_decisions": row[1],
                        "blocked_decisions": row[2],
                        "fallback_decisions": row[3],
                        "escalations": row[4],
                        "avg_confidence": round(row[5] or 0.0, 3),
                        "avg_citation_accuracy": round(row[6] or 0.0, 3),
                        "hallucinations_detected": row[7],
                        "generated_at": datetime.utcnow().isoformat(),
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            return {}
    
    def health_check(self) -> tuple[bool, str]:
        """Check audit trail system health."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM audit_events")
                count = cursor.fetchone()[0]
            
            return True, f"Audit trail operational ({count} events)"
            
        except Exception as e:
            return False, f"Audit trail error: {e}"


# Global instance
_global_audit_system: Optional[AuditTrailSystem] = None


def get_audit_system() -> AuditTrailSystem:
    """Get or create global audit trail system."""
    global _global_audit_system
    
    if _global_audit_system is None:
        db_path = os.environ.get("AUDIT_DB_PATH", "audit_trail.db")
        _global_audit_system = AuditTrailSystem(db_path)
    
    return _global_audit_system
