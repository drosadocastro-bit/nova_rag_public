"""
Use-Case Registry.

Tracks approved use-cases, their deployment status, and impact assessment.
Ensures all deployments are properly documented and approved.
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


class UseCaseStatus(str, Enum):
    """Status of a use-case."""
    
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ImpactLevel(str, Enum):
    """Impact level of a use-case."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class UseCaseMetrics:
    """Metrics for a use-case."""
    
    deployments: int = 0
    total_queries: int = 0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0
    availability_percent: float = 100.0
    user_satisfaction: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class UseCase:
    """Represents a use-case."""
    
    # Identity
    usecase_id: str
    name: str
    description: str
    created_at: float
    
    # Definition
    owner: str
    model_ids: List[str] = field(default_factory=list)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    
    # Impact
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    affected_systems: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    
    # Status
    status: UseCaseStatus = UseCaseStatus.DRAFT
    approved_at: Optional[float] = None
    approved_by: Optional[str] = None
    deployed_at: Optional[float] = None
    
    # Approval
    approval_comments: str = ""
    rejection_reason: str = ""
    
    # Metrics
    metrics: UseCaseMetrics = field(default_factory=UseCaseMetrics)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d['metrics'] = self.metrics.to_dict()
        return d


class UseCaseRegistry:
    """
    Registry for use-cases with approval workflows.
    
    Features:
    - Use-case definitions
    - Approval workflows
    - Impact assessment
    - Deployment tracking
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize use-case registry.
        
        Args:
            db_path: Path to SQLite database (in-memory if None)
        """
        self.db_path = db_path or ":memory:"
        self._init_db()
        logger.info(f"UseCaseRegistry initialized: db={self.db_path}")
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS use_cases (
                    usecase_id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    created_at REAL,
                    owner TEXT,
                    model_ids TEXT,
                    input_schema TEXT,
                    output_schema TEXT,
                    impact_level TEXT,
                    affected_systems TEXT,
                    dependencies TEXT,
                    status TEXT,
                    approved_at REAL,
                    approved_by TEXT,
                    deployed_at REAL,
                    approval_comments TEXT,
                    rejection_reason TEXT,
                    metrics_json TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usecase_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usecase_id TEXT,
                    reviewer TEXT,
                    reviewed_at REAL,
                    status TEXT,
                    comments TEXT,
                    FOREIGN KEY (usecase_id) REFERENCES use_cases(usecase_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usecase_deployments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usecase_id TEXT,
                    deployed_at REAL,
                    deployed_by TEXT,
                    environment TEXT,
                    deployment_id TEXT,
                    status TEXT,
                    notes TEXT,
                    FOREIGN KEY (usecase_id) REFERENCES use_cases(usecase_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usecase_status 
                ON use_cases(status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usecase_owner 
                ON use_cases(owner)
            """)
            
            conn.commit()
    
    def create_usecase(
        self,
        usecase_id: str,
        name: str,
        description: str,
        owner: str,
        model_ids: Optional[List[str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        impact_level: ImpactLevel = ImpactLevel.MEDIUM,
        affected_systems: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> UseCase:
        """Create a new use-case."""
        
        created_at = time.time()
        usecase = UseCase(
            usecase_id=usecase_id,
            name=name,
            description=description,
            created_at=created_at,
            owner=owner,
            model_ids=model_ids or [],
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            impact_level=impact_level,
            affected_systems=affected_systems or [],
            dependencies=dependencies or [],
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO use_cases
                (usecase_id, name, description, created_at, owner,
                 model_ids, input_schema, output_schema, impact_level,
                 affected_systems, dependencies, status, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usecase_id, name, description, created_at, owner,
                json.dumps(model_ids or []),
                json.dumps(input_schema or {}),
                json.dumps(output_schema or {}),
                impact_level.value,
                json.dumps(affected_systems or []),
                json.dumps(dependencies or []),
                UseCaseStatus.DRAFT.value,
                json.dumps(usecase.metrics.to_dict()),
            ))
            conn.commit()
        
        logger.info(f"Created use-case: {usecase_id}")
        return usecase
    
    def get_usecase(self, usecase_id: str) -> Optional[UseCase]:
        """Get a use-case by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM use_cases WHERE usecase_id = ?",
                (usecase_id,)
            ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_usecase(row)
    
    def list_usecases(
        self,
        status: Optional[UseCaseStatus] = None,
        owner: Optional[str] = None,
        limit: int = 100
    ) -> List[UseCase]:
        """List use-cases."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM use_cases WHERE 1=1"
            params = []
            
            if status:
                query += " AND status = ?"
                params.append(status.value)
            
            if owner:
                query += " AND owner = ?"
                params.append(owner)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
        
        return [self._row_to_usecase(row) for row in rows]
    
    def submit_for_approval(
        self,
        usecase_id: str,
        comments: str = ""
    ) -> bool:
        """Submit use-case for approval."""
        usecase = self.get_usecase(usecase_id)
        if not usecase or usecase.status != UseCaseStatus.DRAFT:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases SET status = ?, approval_comments = ?
                WHERE usecase_id = ?
            """, (UseCaseStatus.SUBMITTED.value, comments, usecase_id))
            conn.commit()
        
        logger.info(f"Submitted use-case for approval: {usecase_id}")
        return True
    
    def approve_usecase(
        self,
        usecase_id: str,
        approved_by: str,
        comments: str = ""
    ) -> bool:
        """Approve a use-case."""
        usecase = self.get_usecase(usecase_id)
        if not usecase:
            return False
        
        approved_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases
                SET status = ?, approved_at = ?, approved_by = ?, approval_comments = ?
                WHERE usecase_id = ?
            """, (
                UseCaseStatus.APPROVED.value, approved_at, approved_by, comments,
                usecase_id
            ))
            
            conn.execute("""
                INSERT INTO usecase_approvals
                (usecase_id, reviewer, reviewed_at, status, comments)
                VALUES (?, ?, ?, ?, ?)
            """, (usecase_id, approved_by, approved_at, "approved", comments))
            
            conn.commit()
        
        logger.info(f"Approved use-case: {usecase_id}")
        return True
    
    def reject_usecase(
        self,
        usecase_id: str,
        rejected_by: str,
        reason: str = ""
    ) -> bool:
        """Reject a use-case."""
        usecase = self.get_usecase(usecase_id)
        if not usecase:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases
                SET status = ?, rejection_reason = ?
                WHERE usecase_id = ?
            """, (UseCaseStatus.DRAFT.value, reason, usecase_id))
            
            conn.execute("""
                INSERT INTO usecase_approvals
                (usecase_id, reviewer, reviewed_at, status, comments)
                VALUES (?, ?, ?, ?, ?)
            """, (usecase_id, rejected_by, time.time(), "rejected", reason))
            
            conn.commit()
        
        logger.info(f"Rejected use-case: {usecase_id}")
        return True
    
    def deploy_usecase(
        self,
        usecase_id: str,
        deployment_id: str,
        environment: str = "production",
        deployed_by: str = "system",
        notes: str = ""
    ) -> bool:
        """Deploy a use-case."""
        usecase = self.get_usecase(usecase_id)
        if not usecase or usecase.status != UseCaseStatus.APPROVED:
            logger.warning(f"Cannot deploy non-approved use-case: {usecase_id}")
            return False
        
        deployed_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases
                SET status = ?, deployed_at = ?
                WHERE usecase_id = ?
            """, (UseCaseStatus.DEPLOYED.value, deployed_at, usecase_id))
            
            conn.execute("""
                INSERT INTO usecase_deployments
                (usecase_id, deployed_at, deployed_by, environment, deployment_id, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (usecase_id, deployed_at, deployed_by, environment, deployment_id, "active", notes))
            
            conn.commit()
        
        logger.info(f"Deployed use-case: {usecase_id} to {environment}")
        return True
    
    def deprecate_usecase(
        self,
        usecase_id: str,
        deprecated_by: str,
        reason: str = ""
    ) -> bool:
        """Deprecate a use-case."""
        usecase = self.get_usecase(usecase_id)
        if not usecase:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases
                SET status = ?, rejection_reason = ?
                WHERE usecase_id = ?
            """, (UseCaseStatus.DEPRECATED.value, reason, usecase_id))
            conn.commit()
        
        logger.info(f"Deprecated use-case: {usecase_id}")
        return True
    
    def update_metrics(
        self,
        usecase_id: str,
        metrics: UseCaseMetrics
    ) -> bool:
        """Update metrics for a use-case."""
        usecase = self.get_usecase(usecase_id)
        if not usecase:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE use_cases
                SET metrics_json = ?
                WHERE usecase_id = ?
            """, (json.dumps(metrics.to_dict()), usecase_id))
            conn.commit()
        
        logger.info(f"Updated metrics for use-case: {usecase_id}")
        return True
    
    def get_deployment_history(
        self,
        usecase_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get deployment history for a use-case."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT deployment_id, environment, deployed_at, deployed_by, status, notes
                FROM usecase_deployments
                WHERE usecase_id = ?
                ORDER BY deployed_at DESC
                LIMIT ?
            """, (usecase_id, limit)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "deployment_id": row[0],
                "environment": row[1],
                "timestamp": datetime.fromtimestamp(row[2]).isoformat() if row[2] else None,
                "deployed_by": row[3],
                "status": row[4],
                "notes": row[5],
            })
        
        return result
    
    def _row_to_usecase(self, row: tuple) -> UseCase:
        """Convert database row to UseCase."""
        (usecase_id, name, description, created_at, owner, model_ids,
         input_schema, output_schema, impact_level, affected_systems,
         dependencies, status, approved_at, approved_by, deployed_at,
         approval_comments, rejection_reason, metrics_json) = row
        
        metrics_dict = json.loads(metrics_json or '{}')
        metrics = UseCaseMetrics(**metrics_dict) if metrics_dict else UseCaseMetrics()
        
        return UseCase(
            usecase_id=usecase_id,
            name=name,
            description=description,
            created_at=created_at,
            owner=owner,
            model_ids=json.loads(model_ids or '[]'),
            input_schema=json.loads(input_schema or '{}'),
            output_schema=json.loads(output_schema or '{}'),
            impact_level=ImpactLevel(impact_level),
            affected_systems=json.loads(affected_systems or '[]'),
            dependencies=json.loads(dependencies or '[]'),
            status=UseCaseStatus(status),
            approved_at=approved_at,
            approved_by=approved_by,
            deployed_at=deployed_at,
            approval_comments=approval_comments,
            rejection_reason=rejection_reason,
            metrics=metrics,
        )
