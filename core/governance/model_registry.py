"""
Model Version Registry.

Tracks model versions, approvals, deployments, and rollback history.
Ensures all models are properly versioned, tested, and approved before deployment.
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DeploymentStatus(str, Enum):
    """Status of model deployment."""
    
    REGISTERED = "registered"
    APPROVED = "approved"
    DEPLOYED_STAGING = "deployed_staging"
    DEPLOYED_PRODUCTION = "deployed_production"
    DEPRECATED = "deprecated"
    ROLLED_BACK = "rolled_back"


class ApprovalStatus(str, Enum):
    """Status of model approval request."""
    
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUIRES_CHANGES = "requires_changes"


@dataclass
class PerformanceMetrics:
    """Model performance metrics."""
    
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    latency_ms: Optional[float] = None
    throughput_qps: Optional[float] = None
    
    # Reliability metrics
    error_rate: float = 0.0
    availability_percent: float = 100.0
    
    # Custom metrics (JSON serializable)
    custom_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ModelVersion:
    """Represents a model version."""
    
    # Identity
    model_id: str
    version: str
    created_at: float
    
    # Metadata
    description: str = ""
    source_commit: Optional[str] = None
    training_data_hash: Optional[str] = None
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    
    # Storage
    model_path: str = ""
    model_size_bytes: int = 0
    artifacts: Dict[str, str] = field(default_factory=dict)
    
    # Status
    status: DeploymentStatus = DeploymentStatus.REGISTERED
    deployment_id: Optional[str] = None
    deployed_at: Optional[float] = None
    deployed_by: Optional[str] = None
    
    # Approval workflow
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    approval_comments: str = ""
    
    # Performance metrics
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    # Rollback information
    rolled_back_at: Optional[float] = None
    rollback_reason: str = ""
    rollback_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d['metrics'] = self.metrics.to_dict()
        return d


class ModelRegistry:
    """
    Registry for model versions with approval and deployment workflows.
    
    Features:
    - Version tracking
    - Approval workflows
    - Deployment history
    - Rollback capability
    - Performance tracking
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize model registry.
        
        Args:
            db_path: Path to SQLite database (creates in-memory if None)
        """
        self.db_path = db_path or ":memory:"
        self._init_db()
        logger.info(f"ModelRegistry initialized: db={self.db_path}")
    
    def _connect(self) -> sqlite3.Connection:
        """Create a short-lived SQLite connection with safe pragmas for tests (Windows-friendly)."""
        conn = sqlite3.connect(self.db_path, timeout=0.1, isolation_level=None)
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=OFF;")
        return conn
    
    def close(self) -> None:
        """Close any open handles (best-effort) to release Windows file locks."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=0.1)
            conn.close()
        except Exception:
            pass
    
    def __del__(self):
        self.close()
        try:
            if self.db_path and os.path.exists(self.db_path) and self.db_path != ":memory:":
                os.remove(self.db_path)
        except Exception:
            pass
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_versions (
                    model_id TEXT,
                    version TEXT,
                    created_at REAL,
                    description TEXT,
                    source_commit TEXT,
                    training_data_hash TEXT,
                    hyperparameters TEXT,
                    model_path TEXT,
                    model_size_bytes INTEGER,
                    artifacts TEXT,
                    status TEXT,
                    deployment_id TEXT,
                    deployed_at REAL,
                    deployed_by TEXT,
                    approval_status TEXT,
                    approved_by TEXT,
                    approved_at REAL,
                    approval_comments TEXT,
                    metrics_json TEXT,
                    rolled_back_at REAL,
                    rollback_reason TEXT,
                    rollback_by TEXT,
                    PRIMARY KEY (model_id, version)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT,
                    version TEXT,
                    approval_status TEXT,
                    reviewer TEXT,
                    reviewed_at REAL,
                    comments TEXT,
                    FOREIGN KEY (model_id, version) 
                        REFERENCES model_versions(model_id, version)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deployment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT,
                    version TEXT,
                    deployment_id TEXT,
                    environment TEXT,
                    deployed_at REAL,
                    deployed_by TEXT,
                    status TEXT,
                    notes TEXT,
                    FOREIGN KEY (model_id, version) 
                        REFERENCES model_versions(model_id, version)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_version 
                ON model_versions(model_id, version DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_status 
                ON model_versions(model_id, status)
            """)
            
            conn.commit()
    
    def register_version(
        self,
        model_id: str,
        version: str,
        description: str = "",
        source_commit: Optional[str] = None,
        training_data_hash: Optional[str] = None,
        hyperparameters: Optional[Dict[str, Any]] = None,
        model_path: str = "",
        model_size_bytes: int = 0,
        artifacts: Optional[Dict[str, str]] = None,
    ) -> ModelVersion:
        """Register a new model version."""
        
        created_at = time.time()
        model_version = ModelVersion(
            model_id=model_id,
            version=version,
            created_at=created_at,
            description=description,
            source_commit=source_commit,
            training_data_hash=training_data_hash,
            hyperparameters=hyperparameters or {},
            model_path=model_path,
            model_size_bytes=model_size_bytes,
            artifacts=artifacts or {},
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO model_versions 
                (model_id, version, created_at, description, source_commit,
                 training_data_hash, hyperparameters, model_path, model_size_bytes,
                 artifacts, status, approval_status, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                model_id, version, created_at, description, source_commit,
                training_data_hash, json.dumps(hyperparameters or {}),
                model_path, model_size_bytes, json.dumps(artifacts or {}),
                DeploymentStatus.REGISTERED.value,
                ApprovalStatus.PENDING.value,
                json.dumps(model_version.metrics.to_dict()),
            ))
            conn.commit()
        
        logger.info(f"Registered model version: {model_id}:{version}")
        return model_version
    
    def get_version(self, model_id: str, version: str) -> Optional[ModelVersion]:
        """Get a specific model version."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? AND version = ?",
                (model_id, version)
            ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_model_version(row)
    
    def get_latest_version(self, model_id: str) -> Optional[ModelVersion]:
        """Get latest version of a model."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? ORDER BY created_at DESC LIMIT 1",
                (model_id,)
            ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_model_version(row)
    
    def get_deployed_version(
        self,
        model_id: str,
        environment: str = "production"
    ) -> Optional[ModelVersion]:
        """Get currently deployed version in environment."""
        status_map = {
            "production": DeploymentStatus.DEPLOYED_PRODUCTION,
            "staging": DeploymentStatus.DEPLOYED_STAGING,
        }
        status = status_map.get(environment, DeploymentStatus.DEPLOYED_PRODUCTION)
        
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? AND status = ?",
                (model_id, status.value)
            ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_model_version(row)
    
    def list_versions(self, model_id: str, limit: int = 50) -> List[ModelVersion]:
        """List versions for a model."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM model_versions WHERE model_id = ? ORDER BY created_at DESC LIMIT ?",
                (model_id, limit)
            ).fetchall()
        
        return [self._row_to_model_version(row) for row in rows]
    
    def request_approval(
        self,
        model_id: str,
        version: str,
        comments: str = ""
    ) -> bool:
        """Request approval for a model version."""
        model = self.get_version(model_id, version)
        if not model:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET approval_status = ?, approval_comments = ?
                WHERE model_id = ? AND version = ?
            """, (ApprovalStatus.PENDING.value, comments, model_id, version))
            
            conn.execute("""
                INSERT INTO approval_history 
                (model_id, version, approval_status, comments, reviewed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (model_id, version, ApprovalStatus.PENDING.value, comments, time.time()))
            
            conn.commit()
        
        logger.info(f"Requested approval: {model_id}:{version}")
        return True
    
    def approve_version(
        self,
        model_id: str,
        version: str,
        approved_by: str,
        comments: str = ""
    ) -> bool:
        """Approve a model version."""
        model = self.get_version(model_id, version)
        if not model:
            return False
        
        approved_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET approval_status = ?, approved_by = ?, approved_at = ?, 
                    approval_comments = ?, status = ?
                WHERE model_id = ? AND version = ?
            """, (
                ApprovalStatus.APPROVED.value, approved_by, approved_at, comments,
                DeploymentStatus.APPROVED.value, model_id, version
            ))
            
            conn.execute("""
                INSERT INTO approval_history 
                (model_id, version, approval_status, reviewer, reviewed_at, comments)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                model_id, version, ApprovalStatus.APPROVED.value, 
                approved_by, approved_at, comments
            ))
            
            conn.commit()
        
        logger.info(f"Approved model version: {model_id}:{version} by {approved_by}")
        return True
    
    def reject_version(
        self,
        model_id: str,
        version: str,
        rejected_by: str,
        reason: str = ""
    ) -> bool:
        """Reject a model version."""
        model = self.get_version(model_id, version)
        if not model:
            return False
        
        reviewed_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET approval_status = ?, approval_comments = ?
                WHERE model_id = ? AND version = ?
            """, (ApprovalStatus.REJECTED.value, reason, model_id, version))
            
            conn.execute("""
                INSERT INTO approval_history 
                (model_id, version, approval_status, reviewer, reviewed_at, comments)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                model_id, version, ApprovalStatus.REJECTED.value,
                rejected_by, reviewed_at, reason
            ))
            
            conn.commit()
        
        logger.info(f"Rejected model version: {model_id}:{version}")
        return True
    
    def deploy_version(
        self,
        model_id: str,
        version: str,
        deployment_id: str,
        environment: str = "production",
        deployed_by: str = "system",
    ) -> bool:
        """Deploy a model version."""
        model = self.get_version(model_id, version)
        if not model or model.approval_status != ApprovalStatus.APPROVED:
            logger.warning(f"Cannot deploy unapproved version: {model_id}:{version}")
            return False
        
        # Determine deployment status
        status_map = {
            "production": DeploymentStatus.DEPLOYED_PRODUCTION,
            "staging": DeploymentStatus.DEPLOYED_STAGING,
        }
        status = status_map.get(environment, DeploymentStatus.DEPLOYED_PRODUCTION)
        
        deployed_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET status = ?, deployment_id = ?, deployed_at = ?, deployed_by = ?
                WHERE model_id = ? AND version = ?
            """, (status.value, deployment_id, deployed_at, deployed_by, model_id, version))
            
            conn.execute("""
                INSERT INTO deployment_history 
                (model_id, version, deployment_id, environment, deployed_at, deployed_by, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (model_id, version, deployment_id, environment, deployed_at, deployed_by, status.value))
            
            conn.commit()
        
        logger.info(f"Deployed model version: {model_id}:{version} to {environment}")
        return True
    
    def rollback_version(
        self,
        model_id: str,
        version: str,
        reason: str = "",
        rolled_back_by: str = "system",
    ) -> bool:
        """Rollback a deployed model version."""
        model = self.get_version(model_id, version)
        if not model:
            return False
        
        rolled_back_at = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET status = ?, rolled_back_at = ?, rollback_reason = ?, rollback_by = ?
                WHERE model_id = ? AND version = ?
            """, (
                DeploymentStatus.ROLLED_BACK.value, rolled_back_at, reason,
                rolled_back_by, model_id, version
            ))
            conn.commit()
        
        logger.warning(f"Rolled back model version: {model_id}:{version} - {reason}")
        return True
    
    def update_metrics(
        self,
        model_id: str,
        version: str,
        metrics: PerformanceMetrics
    ) -> bool:
        """Update performance metrics for a version."""
        model = self.get_version(model_id, version)
        if not model:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE model_versions 
                SET metrics_json = ?
                WHERE model_id = ? AND version = ?
            """, (json.dumps(metrics.to_dict()), model_id, version))
            conn.commit()
        
        logger.info(f"Updated metrics for {model_id}:{version}")
        return True
    
    def get_approval_history(
        self,
        model_id: str,
        version: str
    ) -> List[Dict[str, Any]]:
        """Get approval history for a version."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT approval_status, reviewer, reviewed_at, comments
                FROM approval_history
                WHERE model_id = ? AND version = ?
                ORDER BY reviewed_at DESC
            """, (model_id, version)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "status": row[0],
                "reviewer": row[1],
                "timestamp": datetime.fromtimestamp(row[2]).isoformat() if row[2] else None,
                "comments": row[3],
            })
        
        return result
    
    def get_deployment_history(
        self,
        model_id: str,
        version: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get deployment history for a model."""
        with sqlite3.connect(self.db_path) as conn:
            if version:
                rows = conn.execute("""
                    SELECT deployment_id, environment, deployed_at, deployed_by, status
                    FROM deployment_history
                    WHERE model_id = ? AND version = ?
                    ORDER BY deployed_at DESC
                    LIMIT ?
                """, (model_id, version, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT deployment_id, environment, deployed_at, deployed_by, status
                    FROM deployment_history
                    WHERE model_id = ?
                    ORDER BY deployed_at DESC
                    LIMIT ?
                """, (model_id, limit)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "deployment_id": row[0],
                "environment": row[1],
                "timestamp": datetime.fromtimestamp(row[2]).isoformat() if row[2] else None,
                "deployed_by": row[3],
                "status": row[4],
            })
        
        return result
    
    def _row_to_model_version(self, row: Tuple[Any, ...]) -> ModelVersion:
        """Convert database row to ModelVersion."""
        (model_id, version, created_at, description, source_commit,
         training_data_hash, hyperparameters, model_path, model_size_bytes,
         artifacts, status, deployment_id, deployed_at, deployed_by,
         approval_status, approved_by, approved_at, approval_comments,
         metrics_json, rolled_back_at, rollback_reason, rollback_by) = row
        
        metrics_dict = json.loads(metrics_json or '{}')
        metrics = PerformanceMetrics(**metrics_dict) if metrics_dict else PerformanceMetrics()
        
        return ModelVersion(
            model_id=model_id,
            version=version,
            created_at=created_at,
            description=description,
            source_commit=source_commit,
            training_data_hash=training_data_hash,
            hyperparameters=json.loads(hyperparameters or '{}'),
            model_path=model_path,
            model_size_bytes=model_size_bytes,
            artifacts=json.loads(artifacts or '{}'),
            status=DeploymentStatus(status),
            deployment_id=deployment_id,
            deployed_at=deployed_at,
            deployed_by=deployed_by,
            approval_status=ApprovalStatus(approval_status),
            approved_by=approved_by,
            approved_at=approved_at,
            approval_comments=approval_comments,
            metrics=metrics,
            rolled_back_at=rolled_back_at,
            rollback_reason=rollback_reason,
            rollback_by=rollback_by,
        )
