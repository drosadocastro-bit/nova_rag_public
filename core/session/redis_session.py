"""
Redis Session Store for NOVA NIC.

Distributed session storage for horizontal scaling with:
- Session persistence across instances
- Automatic expiration
- Session locking for concurrent access
- Session data compression
"""

import json
import logging
import os
import pickle
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Try to import redis
try:
    import redis  # type: ignore
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class SessionConfig:
    """Configuration for session store."""
    
    host: str = "localhost"
    port: int = 6379
    db: int = 1  # Separate DB from cache
    password: Optional[str] = None
    
    # Session settings
    default_ttl_seconds: int = 3600  # 1 hour
    max_session_size_bytes: int = 1024 * 1024  # 1MB
    key_prefix: str = "session:"
    
    # Locking
    lock_timeout_seconds: float = 10.0
    lock_retry_delay: float = 0.1
    
    # Compression
    enable_compression: bool = True
    compression_threshold: int = 512
    
    @classmethod
    def from_env(cls) -> "SessionConfig":
        """Create config from environment."""
        return cls(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            db=int(os.environ.get("REDIS_SESSION_DB", "1")),
            password=os.environ.get("REDIS_PASSWORD"),
            default_ttl_seconds=int(
                os.environ.get("SESSION_TTL_SECONDS", "3600")
            ),
        )


@dataclass
class Session:
    """Session data container."""
    
    session_id: str
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    expires_at: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Conversation history
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Query context
    last_query: Optional[str] = None
    last_domain: Optional[str] = None
    last_chunks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Preferences
    preferences: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if session is expired."""
        return time.time() > self.expires_at if self.expires_at > 0 else False
    
    @property
    def age_seconds(self) -> float:
        """Session age in seconds."""
        return time.time() - self.created_at
    
    def touch(self) -> None:
        """Update last accessed time."""
        self.last_accessed = time.time()
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add message to conversation history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })
    
    def get_conversation_context(
        self,
        max_messages: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent conversation for context."""
        return self.messages[-max_messages:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "expires_at": self.expires_at,
            "data": self.data,
            "messages": self.messages,
            "last_query": self.last_query,
            "last_domain": self.last_domain,
            "last_chunks": self.last_chunks,
            "preferences": self.preferences,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            user_id=data.get("user_id"),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            expires_at=data.get("expires_at", 0.0),
            data=data.get("data", {}),
            messages=data.get("messages", []),
            last_query=data.get("last_query"),
            last_domain=data.get("last_domain"),
            last_chunks=data.get("last_chunks", []),
            preferences=data.get("preferences", {}),
        )


class RedisSessionStore:
    """
    Redis-based session store for horizontal scaling.
    
    Features:
    - Distributed session storage
    - Automatic expiration
    - Session locking
    - Compression for large sessions
    """
    
    def __init__(self, config: Optional[SessionConfig] = None):
        """
        Initialize session store.
        
        Args:
            config: Session configuration
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "redis-py is required. Install with: pip install redis"
            )
        
        self.config = config or SessionConfig.from_env()
        
        # Connection
        self._client = redis.Redis(  # type: ignore
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            decode_responses=False,
        )
        
        # Local lock tracking
        self._local_locks: Dict[str, threading.Lock] = {}
        
        # Metrics
        self._sessions_created = 0
        self._sessions_loaded = 0
        self._sessions_expired = 0
        
        logger.info(
            f"RedisSessionStore initialized: {self.config.host}:{self.config.port}, "
            f"db={self.config.db}"
        )
    
    def _make_key(self, session_id: str) -> str:
        """Create session key."""
        return f"{self.config.key_prefix}{session_id}"
    
    def _make_lock_key(self, session_id: str) -> str:
        """Create lock key."""
        return f"{self.config.key_prefix}lock:{session_id}"
    
    def _serialize(self, session: Session) -> bytes:
        """Serialize session."""
        data = pickle.dumps(session.to_dict(), protocol=pickle.HIGHEST_PROTOCOL)
        
        if self.config.enable_compression and len(data) > self.config.compression_threshold:
            compressed = zlib.compress(data, 6)
            return b"C" + compressed
        
        return b"U" + data
    
    def _deserialize(self, data: bytes) -> Session:
        """Deserialize session."""
        if data[0:1] == b"C":
            data = zlib.decompress(data[1:])
        else:
            data = data[1:]
        
        return Session.from_dict(pickle.loads(data))
    
    def create_session(
        self,
        user_id: Optional[str] = None,
        ttl: Optional[int] = None,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """
        Create a new session.
        
        Args:
            user_id: Optional user ID
            ttl: Session TTL in seconds
            initial_data: Initial session data
            
        Returns:
            New session
        """
        session_id = str(uuid.uuid4())
        ttl = ttl or self.config.default_ttl_seconds
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            expires_at=time.time() + ttl,
            data=initial_data or {},
        )
        
        # Store
        self._save_session(session, ttl)
        self._sessions_created += 1
        
        logger.debug(f"Created session: {session_id}")
        return session
    
    def _save_session(self, session: Session, ttl: Optional[int] = None) -> bool:
        """Save session to Redis."""
        key = self._make_key(session.session_id)
        ttl = ttl or self.config.default_ttl_seconds
        
        try:
            data = self._serialize(session)
            
            if len(data) > self.config.max_session_size_bytes:
                logger.warning(
                    f"Session {session.session_id} exceeds max size "
                    f"({len(data)} > {self.config.max_session_size_bytes})"
                )
                return False
            
            self._client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session or None if not found/expired
        """
        key = self._make_key(session_id)
        
        try:
            data = self._client.get(key)
            
            if data is None:
                return None
            
            session = self._deserialize(data)
            
            if session.is_expired:
                self.delete_session(session_id)
                self._sessions_expired += 1
                return None
            
            session.touch()
            self._sessions_loaded += 1
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None
    
    def update_session(
        self,
        session: Session,
        extend_ttl: bool = True,
    ) -> bool:
        """
        Update a session.
        
        Args:
            session: Session to update
            extend_ttl: Whether to extend TTL
            
        Returns:
            True if successful
        """
        session.touch()
        
        ttl = None
        if extend_ttl:
            ttl = self.config.default_ttl_seconds
            session.expires_at = time.time() + ttl
        
        return self._save_session(session, ttl)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        key = self._make_key(session_id)
        
        try:
            return self._client.delete(key) > 0
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False
    
    def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        key = self._make_key(session_id)
        try:
            return self._client.exists(key) > 0
        except Exception:
            return False
    
    def acquire_lock(
        self,
        session_id: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Acquire distributed lock on session.
        
        Args:
            session_id: Session to lock
            timeout: Lock timeout (None = default)
            
        Returns:
            True if lock acquired
        """
        lock_key = self._make_lock_key(session_id)
        timeout = timeout or self.config.lock_timeout_seconds
        
        lock_value = str(uuid.uuid4())
        
        try:
            acquired = self._client.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if not exists
                ex=int(timeout),
            )
            
            if acquired:
                # Track locally for release
                if session_id not in self._local_locks:
                    self._local_locks[session_id] = threading.Lock()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False
    
    def release_lock(self, session_id: str) -> bool:
        """Release distributed lock."""
        lock_key = self._make_lock_key(session_id)
        
        try:
            return self._client.delete(lock_key) > 0
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
            return False
    
    def get_user_sessions(
        self,
        user_id: str,
        limit: int = 10,
    ) -> List[Session]:
        """Get all sessions for a user."""
        pattern = f"{self.config.key_prefix}*"
        sessions = []
        
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                
                for key in keys:
                    if b"lock:" in key:
                        continue
                    
                    data = self._client.get(key)
                    if data:
                        session = self._deserialize(data)
                        if session.user_id == user_id and not session.is_expired:
                            sessions.append(session)
                
                if cursor == 0:
                    break
            
            # Sort by last accessed
            sessions.sort(key=lambda s: s.last_accessed, reverse=True)
            return sessions[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []
    
    def cleanup_expired(self) -> int:
        """Clean up expired sessions (Redis handles this via TTL)."""
        # This is mostly a no-op since Redis handles expiration
        # But we can track sessions that were explicitly expired
        return self._sessions_expired
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session store statistics."""
        try:
            info = self._client.info("keyspace")
            db_info = info.get(f"db{self.config.db}", {})
            keys = db_info.get("keys", 0)
        except Exception:
            keys = "unknown"
        
        return {
            "sessions_created": self._sessions_created,
            "sessions_loaded": self._sessions_loaded,
            "sessions_expired": self._sessions_expired,
            "active_sessions": keys,
            "host": self.config.host,
            "port": self.config.port,
            "db": self.config.db,
        }
    
    def health_check(self) -> tuple[bool, str]:
        """Check Redis connection health."""
        try:
            self._client.ping()
            return True, "Redis session store connected"
        except Exception as e:
            return False, f"Redis error: {e}"
    
    def close(self) -> None:
        """Close connection."""
        self._client.close()
        logger.info("RedisSessionStore closed")


class SessionMiddleware:
    """
    Middleware for automatic session handling.
    
    Usage with Flask:
        app = Flask(__name__)
        session_store = RedisSessionStore()
        middleware = SessionMiddleware(session_store)
        
        @app.before_request
        def load_session():
            middleware.load_session(request)
        
        @app.after_request
        def save_session(response):
            return middleware.save_session(request, response)
    """
    
    SESSION_COOKIE_NAME = "nova_session"
    SESSION_HEADER_NAME = "X-Session-ID"
    
    def __init__(
        self,
        store: RedisSessionStore,
        cookie_name: str = SESSION_COOKIE_NAME,
        header_name: str = SESSION_HEADER_NAME,
    ):
        self.store = store
        self.cookie_name = cookie_name
        self.header_name = header_name
    
    def get_session_id(self, request: Any) -> Optional[str]:
        """Extract session ID from request."""
        # Try header first
        session_id = request.headers.get(self.header_name)
        if session_id:
            return session_id
        
        # Try cookie
        if hasattr(request, "cookies"):
            return request.cookies.get(self.cookie_name)
        
        return None
    
    def load_session(self, request: Any) -> Optional[Session]:
        """Load session for request."""
        session_id = self.get_session_id(request)
        
        if session_id:
            session = self.store.get_session(session_id)
            if session:
                request.session = session
                return session
        
        # Create new session
        session = self.store.create_session()
        request.session = session
        return session
    
    def save_session(self, request: Any, response: Any) -> Any:
        """Save session after request."""
        session = getattr(request, "session", None)
        
        if session:
            self.store.update_session(session)
            
            # Set cookie on response
            if hasattr(response, "set_cookie"):
                response.set_cookie(
                    self.cookie_name,
                    session.session_id,
                    httponly=True,
                    samesite="Lax",
                    max_age=self.store.config.default_ttl_seconds,
                )
        
        return response


# ==================
# Global Instance
# ==================

_global_store: Optional[RedisSessionStore] = None


def get_session_store() -> RedisSessionStore:
    """Get or create global session store."""
    global _global_store
    
    if _global_store is None:
        _global_store = RedisSessionStore()
    
    return _global_store


def set_session_store(store: RedisSessionStore) -> None:
    """Set global session store."""
    global _global_store
    _global_store = store
