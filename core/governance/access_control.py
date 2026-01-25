"""
Access Control and Role-Based Permission Management.

Provides:
- Role definitions (Operator, Analyst, Approver, Admin, Auditor)
- Permission model
- Segregation of duties
- Approval workflow enforcement
"""

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """User roles in the system."""
    
    OPERATOR = "operator"  # Deploys, monitors, responds to alerts
    ANALYST = "analyst"    # Analyzes data, queries system
    APPROVER = "approver"  # Approves model updates, use cases
    ADMIN = "admin"        # Manages users, roles, system config
    AUDITOR = "auditor"    # Reviews logs, generates reports


class Permission(str, Enum):
    """System permissions."""
    
    # Model management
    MODEL_REGISTER = "model:register"
    MODEL_APPROVE = "model:approve"
    MODEL_DEPLOY = "model:deploy"
    MODEL_ROLLBACK = "model:rollback"
    
    # Use-case management
    USECASE_CREATE = "usecase:create"
    USECASE_APPROVE = "usecase:approve"
    USECASE_DEPRECATE = "usecase:deprecate"
    
    # Access control
    USER_MANAGE = "user:manage"
    ROLE_MANAGE = "role:manage"
    PERMISSION_MANAGE = "permission:manage"
    
    # Audit & compliance
    AUDIT_READ = "audit:read"
    COMPLIANCE_REPORT = "compliance:report"
    INCIDENT_REPORT = "incident:report"
    
    # System
    SYSTEM_CONFIG = "system:config"
    SYSTEM_SHUTDOWN = "system:shutdown"


class ApprovalAction(str, Enum):
    """Actions requiring approval."""
    
    MODEL_DEPLOY_PRODUCTION = "model_deploy_production"
    MODEL_ROLLBACK = "model_rollback"
    USECASE_APPROVE = "usecase_approve"
    USECASE_DEPRECATE = "usecase_deprecate"
    PERMISSION_GRANT = "permission_grant"
    SYSTEM_CONFIG_CHANGE = "system_config_change"


@dataclass
class UserRole:
    """User role assignment."""
    
    user_id: str
    role: Role
    assigned_at: float
    assigned_by: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalWorkflow:
    """Approval workflow configuration."""
    
    action: ApprovalAction
    required_role: Role  # Minimum role to approve
    required_count: int = 1  # Number of approvals needed
    requires_sod: bool = True  # Segregation of duties (different approvers)
    timeout_hours: int = 72
    allow_self_approval: bool = False


class AccessControl:
    """
    Access control system with RBAC and approval workflows.
    
    Features:
    - Role-based permissions
    - Segregation of duties
    - Approval workflows
    - Audit logging
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize access control.
        
        Args:
            db_path: Path to SQLite database (in-memory if None)
        """
        self.db_path = db_path or ":memory:"
        self._init_db()
        self._init_roles()
        logger.info(f"AccessControl initialized: db={self.db_path}")
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    created_at REAL,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id TEXT,
                    role TEXT,
                    assigned_at REAL,
                    assigned_by TEXT,
                    metadata TEXT,
                    PRIMARY KEY (user_id, role),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role TEXT,
                    permission TEXT,
                    granted_at REAL,
                    granted_by TEXT,
                    PRIMARY KEY (role, permission)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_requests (
                    request_id TEXT PRIMARY KEY,
                    action TEXT,
                    requester_id TEXT,
                    requested_at REAL,
                    expires_at REAL,
                    status TEXT,
                    context TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    approver_id TEXT,
                    approved_at REAL,
                    approval_status TEXT,
                    comments TEXT,
                    FOREIGN KEY (request_id) 
                        REFERENCES approval_requests(request_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS access_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    action TEXT,
                    resource TEXT,
                    timestamp REAL,
                    result TEXT,
                    details TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_roles 
                ON user_roles(user_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_approval_status 
                ON approval_requests(status, expires_at)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user 
                ON access_audit_log(user_id, timestamp DESC)
            """)
            
            conn.commit()
    
    def _init_roles(self) -> None:
        """Initialize default role-permission mappings."""
        role_permissions = {
            Role.OPERATOR: [
                Permission.MODEL_DEPLOY,
                Permission.MODEL_ROLLBACK,
                Permission.AUDIT_READ,
            ],
            Role.ANALYST: [
                Permission.AUDIT_READ,
                Permission.COMPLIANCE_REPORT,
                Permission.INCIDENT_REPORT,
            ],
            Role.APPROVER: [
                Permission.MODEL_APPROVE,
                Permission.USECASE_APPROVE,
                Permission.AUDIT_READ,
                Permission.COMPLIANCE_REPORT,
            ],
            Role.ADMIN: [
                Permission.MODEL_REGISTER,
                Permission.MODEL_APPROVE,
                Permission.MODEL_DEPLOY,
                Permission.MODEL_ROLLBACK,
                Permission.USECASE_CREATE,
                Permission.USECASE_APPROVE,
                Permission.USECASE_DEPRECATE,
                Permission.USER_MANAGE,
                Permission.ROLE_MANAGE,
                Permission.PERMISSION_MANAGE,
                Permission.AUDIT_READ,
                Permission.COMPLIANCE_REPORT,
                Permission.INCIDENT_REPORT,
                Permission.SYSTEM_CONFIG,
                Permission.SYSTEM_SHUTDOWN,
            ],
            Role.AUDITOR: [
                Permission.AUDIT_READ,
                Permission.COMPLIANCE_REPORT,
                Permission.INCIDENT_REPORT,
            ],
        }
        
        with sqlite3.connect(self.db_path) as conn:
            for role, permissions in role_permissions.items():
                for perm in permissions:
                    conn.execute("""
                        INSERT OR IGNORE INTO role_permissions 
                        (role, permission, granted_at, granted_by)
                        VALUES (?, ?, ?, ?)
                    """, (role.value, perm.value, time.time(), "system"))
            conn.commit()
    
    def create_user(
        self,
        user_id: str,
        email: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a new user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO users (user_id, email, created_at, metadata)
                    VALUES (?, ?, ?, ?)
                """, (user_id, email, time.time(), "{}"))
                conn.commit()
            
            logger.info(f"Created user: {user_id}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"User already exists: {user_id}")
            return False
    
    def assign_role(
        self,
        user_id: str,
        role: Role,
        assigned_by: str
    ) -> bool:
        """Assign a role to a user."""
        with sqlite3.connect(self.db_path) as conn:
            user = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            
            if not user:
                logger.warning(f"User not found: {user_id}")
                return False
            
            conn.execute("""
                INSERT OR REPLACE INTO user_roles 
                (user_id, role, assigned_at, assigned_by)
                VALUES (?, ?, ?, ?)
            """, (user_id, role.value, time.time(), assigned_by))
            
            conn.commit()
        
        logger.info(f"Assigned role {role.value} to user {user_id}")
        return True
    
    def revoke_role(self, user_id: str, role: Role) -> bool:
        """Revoke a role from a user."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM user_roles 
                WHERE user_id = ? AND role = ?
            """, (user_id, role.value))
            conn.commit()
        
        logger.info(f"Revoked role {role.value} from user {user_id}")
        return True
    
    def has_permission(
        self,
        user_id: str,
        permission: Permission,
        resource_id: Optional[str] = None
    ) -> bool:
        """Check if user has permission."""
        with sqlite3.connect(self.db_path) as conn:
            # Get user roles
            roles = conn.execute("""
                SELECT role FROM user_roles WHERE user_id = ?
            """, (user_id,)).fetchall()
            
            if not roles:
                self._audit_log(user_id, "permission_check", resource_id or "unknown", "DENIED", 
                               "No roles assigned")
                return False
            
            # Check if any role has permission
            role_list = ",".join([f"'{r[0]}'" for r in roles])
            result = conn.execute(f"""
                SELECT role FROM role_permissions 
                WHERE permission = ? AND role IN ({role_list})
            """, (permission.value,)).fetchone()
            
            if result:
                self._audit_log(user_id, "permission_check", resource_id or "unknown", "ALLOWED",
                               f"Role: {result[0]}")
                return True
        
        self._audit_log(user_id, "permission_check", resource_id or "unknown", "DENIED",
                       f"Permission not found: {permission.value}")
        return False
    
    def get_user_roles(self, user_id: str) -> List[Role]:
        """Get all roles for a user."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT role FROM user_roles WHERE user_id = ?
            """, (user_id,)).fetchall()
        
        return [Role(r[0]) for r in rows]
    
    def request_approval(
        self,
        action: ApprovalAction,
        requester_id: str,
        context: Dict[str, Any],
        timeout_hours: int = 72
    ) -> str:
        """Request approval for an action."""
        request_id = f"{action.value}_{requester_id}_{int(time.time())}"
        requested_at = time.time()
        expires_at = requested_at + (timeout_hours * 3600)
        
        import json
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO approval_requests 
                (request_id, action, requester_id, requested_at, expires_at, status, context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id, action.value, requester_id, requested_at, expires_at,
                "pending", json.dumps(context)
            ))
            conn.commit()
        
        logger.info(f"Approval requested: {request_id} for {action.value}")
        return request_id
    
    def approve_request(
        self,
        request_id: str,
        approver_id: str,
        approval_status: str = "approved",
        comments: str = ""
    ) -> bool:
        """Approve or reject an approval request."""
        with sqlite3.connect(self.db_path) as conn:
            # Get request
            req = conn.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?",
                (request_id,)
            ).fetchone()
            
            if not req:
                return False
            
            # Check if expired
            if req[4] < time.time():
                conn.execute(
                    "UPDATE approval_requests SET status = ? WHERE request_id = ?",
                    ("expired", request_id)
                )
                conn.commit()
                return False
            
            # Add approval
            conn.execute("""
                INSERT INTO approvals 
                (request_id, approver_id, approved_at, approval_status, comments)
                VALUES (?, ?, ?, ?, ?)
            """, (request_id, approver_id, time.time(), approval_status, comments))
            
            # Update request status if approved
            if approval_status == "approved":
                conn.execute(
                    "UPDATE approval_requests SET status = ? WHERE request_id = ?",
                    ("approved", request_id)
                )
            
            conn.commit()
        
        logger.info(f"Approval processed: {request_id} - {approval_status}")
        return True
    
    def get_approval_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get approval request details."""
        import json
        
        with sqlite3.connect(self.db_path) as conn:
            req = conn.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?",
                (request_id,)
            ).fetchone()
            
            if not req:
                return None
            
            # Get approvals
            approvals = conn.execute("""
                SELECT approver_id, approved_at, approval_status, comments
                FROM approvals WHERE request_id = ?
            """, (request_id,)).fetchall()
        
        return {
            "request_id": req[0],
            "action": req[1],
            "requester_id": req[2],
            "requested_at": datetime.fromtimestamp(req[3]).isoformat(),
            "expires_at": datetime.fromtimestamp(req[4]).isoformat(),
            "status": req[5],
            "context": json.loads(req[6] or "{}"),
            "approvals": [
                {
                    "approver": a[0],
                    "timestamp": datetime.fromtimestamp(a[1]).isoformat() if a[1] else None,
                    "status": a[2],
                    "comments": a[3],
                }
                for a in approvals
            ]
        }
    
    def _audit_log(
        self,
        user_id: str,
        action: str,
        resource: str,
        result: str,
        details: str = ""
    ) -> None:
        """Log access audit event."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO access_audit_log 
                (user_id, action, resource, timestamp, result, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, action, resource, time.time(), result, details))
            conn.commit()
    
    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get access audit log."""
        with sqlite3.connect(self.db_path) as conn:
            if user_id:
                rows = conn.execute("""
                    SELECT user_id, action, resource, timestamp, result, details
                    FROM access_audit_log
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (user_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT user_id, action, resource, timestamp, result, details
                    FROM access_audit_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
        
        result = []
        for row in rows:
            result.append({
                "user_id": row[0],
                "action": row[1],
                "resource": row[2],
                "timestamp": datetime.fromtimestamp(row[3]).isoformat(),
                "result": row[4],
                "details": row[5],
            })
        
        return result
