import sqlite3
import json
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import uuid

SESSIONS_DIR = Path.home() / '.nova_rag'
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SESSIONS_DIR / 'sessions.db'


def _init_db():
    """Initialize SQLite database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            model TEXT,
            mode TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            state_json TEXT,
            finding_log_json TEXT,
            turns INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()


def generate_session_id() -> str:
    """Generate unique session ID."""
    return str(uuid.uuid4())[:8]


def save_session(session_id: str, state: dict, topic: str = "", model: str = "", mode: str = ""):
    """Save or update a session in SQLite."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    state_json = json.dumps(state, ensure_ascii=False)
    finding_log_json = json.dumps(state.get("finding_log", []), ensure_ascii=False)
    turns = state.get("turns", 0)
    
    # Check if session exists
    cursor.execute('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
    exists = cursor.fetchone() is not None
    
    if exists:
        cursor.execute('''
            UPDATE sessions 
            SET topic = ?, model = ?, mode = ?, updated_at = ?, 
                state_json = ?, finding_log_json = ?, turns = ?
            WHERE session_id = ?
        ''', (topic, model, mode, now, state_json, finding_log_json, turns, session_id))
    else:
        cursor.execute('''
            INSERT INTO sessions 
            (session_id, topic, model, mode, created_at, updated_at, state_json, finding_log_json, turns)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, topic, model, mode, now, now, state_json, finding_log_json, turns))
    
    conn.commit()
    conn.close()


def load_session(session_id: str) -> Optional[dict]:
    """Load a session from SQLite."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT state_json FROM sessions WHERE session_id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        try:
            return json.loads(row[0])
        except:
            return None
    return None


def list_recent_sessions(limit: int = 10) -> List[dict]:
    """Get recent sessions (newest first) with metadata."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT session_id, topic, model, mode, created_at, updated_at, turns
        FROM sessions
        ORDER BY updated_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        results.append({
            'session_id': row[0],
            'topic': row[1],
            'model': row[2],
            'mode': row[3],
            'created_at': row[4],
            'updated_at': row[5],
            'turns': row[6],
            'display': f"{row[1][:50]}... | {row[2]} | {row[6]} turns | {row[5][:10]}"  # For UI dropdown
        })
    
    return results


def delete_session(session_id: str) -> bool:
    """Delete a session from SQLite."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return success
