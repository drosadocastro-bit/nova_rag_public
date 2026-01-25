"""
Session management package exposing shared session helpers.
"""

from . import session_manager
from .session_manager import *  # noqa: F401,F403

# Redis session store (optional)
try:
    from .redis_session import (
        RedisSessionStore,
        SessionConfig,
        Session,
        SessionMiddleware,
        get_session_store,
        set_session_store,
    )
    REDIS_SESSION_AVAILABLE = True
except ImportError:
    REDIS_SESSION_AVAILABLE = False

__all__ = list(session_manager.__all__) + ["REDIS_SESSION_AVAILABLE"]

if REDIS_SESSION_AVAILABLE:
    __all__.extend([
        "RedisSessionStore",
        "SessionConfig",
        "Session",
        "SessionMiddleware",
        "get_session_store",
        "set_session_store",
    ])