"""
Caching utilities for NIC retrieval and audit operations.

Feature-flagged via environment variables:
- NOVA_ENABLE_RETRIEVAL_CACHE=1
- NOVA_ENABLE_SQL_LOG=1

Security: Uses HMAC-verified pickle to prevent code execution from tampered cache files.
"""

import os
import hashlib
import json
from pathlib import Path
from functools import wraps
from typing import List, Dict, Any, Optional, Callable
import sqlite3
from datetime import datetime
from threading import Lock

# Import secure pickle functions
try:
    from secure_cache import secure_pickle_dump, secure_pickle_load
    SECURE_CACHE_AVAILABLE = True
except ImportError:
    # Fallback to regular pickle if secure_cache not available
    import pickle
    SECURE_CACHE_AVAILABLE = False
    print("[WARNING] secure_cache module not found, using standard pickle (less secure)")

# ===========================
# Retrieval Cache
# ===========================

_retrieval_cache: Dict[str, List[Dict[str, Any]]] = {}
_retrieval_cache_lock = Lock()
_retrieval_cache_file = Path("vector_db/retrieval_cache.pkl")


def _cache_key(query: str, k: int, top_n: int) -> str:
    """Generate cache key for retrieval parameters."""
    return hashlib.md5(f"{query}|{k}|{top_n}".encode()).hexdigest()


def cache_retrieval(func: Callable) -> Callable:
    """Decorator to cache retrieval results.
    
    Only active when NOVA_ENABLE_RETRIEVAL_CACHE=1.
    Cache is in-memory + persisted to disk on write.
    """
    @wraps(func)
    def wrapper(query: str, k: int = 12, top_n: int = 6, **kwargs) -> List[Dict[str, Any]]:
        if os.environ.get("NOVA_ENABLE_RETRIEVAL_CACHE", "0") != "1":
            return func(query, k=k, top_n=top_n, **kwargs)
        
        cache_key = _cache_key(query, k, top_n)
        
        # Check in-memory cache
        with _retrieval_cache_lock:
            if cache_key in _retrieval_cache:
                return _retrieval_cache[cache_key]
        
        # Cache miss: run retrieval
        result = func(query, k=k, top_n=top_n, **kwargs)
        
        # Store in cache
        with _retrieval_cache_lock:
            _retrieval_cache[cache_key] = result
            # Persist to disk with HMAC verification (best-effort; don't fail if write errors)
            try:
                _retrieval_cache_file.parent.mkdir(parents=True, exist_ok=True)
                if SECURE_CACHE_AVAILABLE:
                    secure_pickle_dump(_retrieval_cache, _retrieval_cache_file)
                else:
                    import pickle
                    with open(_retrieval_cache_file, "wb") as f:
                        pickle.dump(_retrieval_cache, f)
            except Exception as e:
                print(f"[Cache] Warning: Failed to persist cache: {e}")
                pass
        
        return result
    
    return wrapper


def load_retrieval_cache():
    """Load retrieval cache from disk on startup with HMAC verification."""
    if os.environ.get("NOVA_ENABLE_RETRIEVAL_CACHE", "0") != "1":
        return
    
    global _retrieval_cache
    if _retrieval_cache_file.exists():
        try:
            if SECURE_CACHE_AVAILABLE:
                _retrieval_cache = secure_pickle_load(_retrieval_cache_file)
            else:
                import pickle
                with open(_retrieval_cache_file, "rb") as f:
                    _retrieval_cache = pickle.load(f)
            print(f"[Cache] Loaded {len(_retrieval_cache)} retrieval cache entries")
        except Exception as e:
            print(f"[Cache] Failed to load retrieval cache: {e}")
            print(f"[Cache] Cache file may be corrupted or from different SECRET_KEY. Clearing cache.")
            # Clear corrupted cache
            _retrieval_cache = {}
            if _retrieval_cache_file.exists():
                try:
                    _retrieval_cache_file.unlink()
                except Exception:
                    pass


def clear_retrieval_cache():
    """Clear retrieval cache (useful after index rebuild)."""
    global _retrieval_cache
    with _retrieval_cache_lock:
        _retrieval_cache.clear()
        if _retrieval_cache_file.exists():
            _retrieval_cache_file.unlink()
    print("[Cache] Retrieval cache cleared")


# ===========================
# SQL Query Logging
# ===========================

_sql_log_db = Path("vector_db/query_log.db")
_sql_log_lock = Lock()


def init_sql_log():
    """Initialize SQLite database for query logging.
    
    Only active when NOVA_ENABLE_SQL_LOG=1.
    """
    if os.environ.get("NOVA_ENABLE_SQL_LOG", "0") != "1":
        return
    
    _sql_log_db.parent.mkdir(parents=True, exist_ok=True)
    
    with _sql_log_lock:
        conn = sqlite3.connect(_sql_log_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                question TEXT NOT NULL,
                mode TEXT,
                model_used TEXT,
                retrieval_confidence REAL,
                audit_status TEXT,
                citation_audit_enabled INTEGER,
                citation_strict_enabled INTEGER,
                answer_length INTEGER,
                session_id TEXT,
                response_time_ms REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON query_log(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_status ON query_log(audit_status)
        """)
        conn.commit()
        conn.close()
    
    print(f"[SQL Log] Initialized at {_sql_log_db}")


def log_query(
    question: str,
    mode: str,
    model_used: str,
    retrieval_confidence: float,
    audit_status: Optional[str],
    citation_audit_enabled: bool,
    citation_strict_enabled: bool,
    answer_length: int,
    session_id: Optional[str],
    response_time_ms: float
):
    """Log query and response metadata to SQLite.
    
    Only active when NOVA_ENABLE_SQL_LOG=1.
    Non-blocking: failures are logged but don't affect operation.
    """
    if os.environ.get("NOVA_ENABLE_SQL_LOG", "0") != "1":
        return
    
    try:
        with _sql_log_lock:
            conn = sqlite3.connect(_sql_log_db)
            conn.execute("""
                INSERT INTO query_log (
                    timestamp, question, mode, model_used, retrieval_confidence,
                    audit_status, citation_audit_enabled, citation_strict_enabled,
                    answer_length, session_id, response_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                question,
                mode,
                model_used,
                retrieval_confidence,
                audit_status,
                1 if citation_audit_enabled else 0,
                1 if citation_strict_enabled else 0,
                answer_length,
                session_id,
                response_time_ms
            ))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[SQL Log] Warning: failed to log query: {e}")


def get_query_stats() -> Dict[str, Any]:
    """Get query log statistics.
    
    Returns basic stats if SQL logging is enabled, else empty dict.
    """
    if os.environ.get("NOVA_ENABLE_SQL_LOG", "0") != "1":
        return {}
    
    if not _sql_log_db.exists():
        return {}
    
    try:
        with _sql_log_lock:
            conn = sqlite3.connect(_sql_log_db)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM query_log")
            total = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT audit_status, COUNT(*) 
                FROM query_log 
                WHERE audit_status IS NOT NULL
                GROUP BY audit_status
            """)
            audit_counts = dict(cursor.fetchall())
            
            cursor.execute("""
                SELECT AVG(response_time_ms), AVG(retrieval_confidence)
                FROM query_log
            """)
            avg_time, avg_conf = cursor.fetchone()
            
            conn.close()
            
            return {
                "total_queries": total,
                "audit_status_breakdown": audit_counts,
                "avg_response_time_ms": round(avg_time, 1) if avg_time else 0,
                "avg_retrieval_confidence": round(avg_conf, 2) if avg_conf else 0,
            }
    except Exception as e:
        print(f"[SQL Log] Warning: failed to get stats: {e}")
        return {}
