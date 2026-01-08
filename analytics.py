"""
Request logging and analytics for NIC.
Tracks queries, response times, model usage, and user patterns.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import time

# Analytics database path
BASE_DIR = Path(__file__).parent.resolve()
ANALYTICS_DIR = BASE_DIR / "vector_db"
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = ANALYTICS_DIR / "analytics.db"


def _init_db():
    """Initialize analytics database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Main request log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            question TEXT NOT NULL,
            mode TEXT,
            model_used TEXT,
            confidence REAL,
            response_time_ms INTEGER,
            retrieval_score REAL,
            num_sources INTEGER,
            answer_length INTEGER,
            session_id TEXT,
            user_ip TEXT,
            response_type TEXT,
            error TEXT
        )
    ''')
    
    # Popular queries aggregation
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS query_stats (
            query_normalized TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1,
            last_seen TIMESTAMP,
            avg_confidence REAL,
            avg_response_time_ms INTEGER
        )
    ''')
    
    # Performance metrics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_metrics (
            date TEXT PRIMARY KEY,
            total_requests INTEGER,
            avg_response_time_ms INTEGER,
            p95_response_time_ms INTEGER,
            avg_confidence REAL,
            error_count INTEGER
        )
    ''')
    
    # Create indexes for common queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON request_log(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_model ON request_log(model_used)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_session ON request_log(session_id)')
    
    conn.commit()
    conn.close()


def log_request(
    question: str,
    mode: str,
    model_used: str,
    confidence: float,
    response_time_ms: int,
    retrieval_score: float = 0.0,
    num_sources: int = 0,
    answer_length: int = 0,
    session_id: Optional[str] = None,
    user_ip: Optional[str] = None,
    response_type: str = "answer",
    error: Optional[str] = None
):
    """Log a request to the analytics database."""
    _init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO request_log (
                timestamp, question, mode, model_used, confidence,
                response_time_ms, retrieval_score, num_sources, answer_length,
                session_id, user_ip, response_type, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            question,
            mode,
            model_used,
            confidence,
            response_time_ms,
            retrieval_score,
            num_sources,
            answer_length,
            session_id,
            user_ip,
            response_type,
            error
        ))
        
        # Update query stats
        normalized = _normalize_query(question)
        cursor.execute('''
            INSERT INTO query_stats (query_normalized, count, last_seen, avg_confidence, avg_response_time_ms)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(query_normalized) DO UPDATE SET
                count = count + 1,
                last_seen = excluded.last_seen,
                avg_confidence = (avg_confidence * count + excluded.avg_confidence) / (count + 1),
                avg_response_time_ms = (avg_response_time_ms * count + excluded.avg_response_time_ms) / (count + 1)
        ''', (normalized, datetime.now().isoformat(), confidence, response_time_ms))
        
        conn.commit()
    except Exception as e:
        print(f"[Analytics] Failed to log request: {e}")
    finally:
        conn.close()


def _normalize_query(query: str) -> str:
    """Normalize query for aggregation (lowercase, strip extra whitespace)."""
    return ' '.join(query.lower().split())[:200]


def get_analytics_summary(days: int = 7) -> Dict[str, Any]:
    """Get analytics summary for the last N days."""
    _init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Overall stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_requests,
            AVG(response_time_ms) as avg_response_time,
            AVG(confidence) as avg_confidence,
            COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as error_count
        FROM request_log
        WHERE timestamp > ?
    ''', (since,))
    
    overall = cursor.fetchone()
    
    # Model usage
    cursor.execute('''
        SELECT model_used, COUNT(*) as count
        FROM request_log
        WHERE timestamp > ?
        GROUP BY model_used
        ORDER BY count DESC
    ''', (since,))
    
    model_usage = dict(cursor.fetchall())
    
    # Popular queries
    cursor.execute('''
        SELECT query_normalized, count, avg_confidence
        FROM query_stats
        ORDER BY count DESC
        LIMIT 10
    ''')
    
    popular_queries = [
        {"query": q, "count": c, "avg_confidence": conf}
        for q, c, conf in cursor.fetchall()
    ]
    
    # Response time percentiles
    cursor.execute('''
        SELECT response_time_ms
        FROM request_log
        WHERE timestamp > ?
        ORDER BY response_time_ms
    ''', (since,))
    
    times = [r[0] for r in cursor.fetchall() if r[0]]
    p95 = times[int(len(times) * 0.95)] if times else 0
    p99 = times[int(len(times) * 0.99)] if times else 0
    
    conn.close()
    
    return {
        "period_days": days,
        "total_requests": overall[0] or 0,
        "avg_response_time_ms": int(overall[1] or 0),
        "avg_confidence": round(overall[2] or 0, 3),
        "error_count": overall[3] or 0,
        "p95_response_time_ms": p95,
        "p99_response_time_ms": p99,
        "model_usage": model_usage,
        "popular_queries": popular_queries
    }


def get_recent_requests(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent requests for debugging."""
    _init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT timestamp, question, model_used, confidence, response_time_ms, error
        FROM request_log
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    requests = [
        {
            "timestamp": r[0],
            "question": r[1][:100],
            "model": r[2],
            "confidence": r[3],
            "response_time_ms": r[4],
            "error": r[5]
        }
        for r in cursor.fetchall()
    ]
    
    conn.close()
    return requests


def get_performance_trends(days: int = 30) -> List[Dict[str, Any]]:
    """Get daily performance trends."""
    _init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).isoformat()
    
    cursor.execute('''
        SELECT 
            DATE(timestamp) as date,
            COUNT(*) as requests,
            AVG(response_time_ms) as avg_time,
            AVG(confidence) as avg_conf
        FROM request_log
        WHERE timestamp > ?
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
    ''', (since,))
    
    trends = [
        {
            "date": r[0],
            "requests": r[1],
            "avg_response_time_ms": int(r[2] or 0),
            "avg_confidence": round(r[3] or 0, 3)
        }
        for r in cursor.fetchall()
    ]
    
    conn.close()
    return trends
