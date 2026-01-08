"""
Session management for NovaRAG - handles session state and persistence.
Manages troubleshooting sessions, conversation history, and session exports.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from agents.session_store import save_session, load_session, generate_session_id


# =======================
# PATHS & CONFIG
# =======================

BASE_DIR = Path(__file__).parent.parent.resolve()
INDEX_DIR = BASE_DIR / "vector_db"


# =======================
# SESSION STATE
# =======================

session_state = {
    "active": False,
    "topic": None,
    "finding_log": [],
    "turns": 0,
    "session_id": None,
    "model": None,
    "mode": None,
    "feedback": [],
    "turn_history": [],  # List of (question, answer) tuples for multi-turn context
}


# =======================
# SESSION TRIGGERS
# =======================

TROUBLESHOOT_TRIGGERS = [
    "troubleshoot", "troubleshooting", "intermittent",
    "diagnostic", "fault", "failure", "error", "trouble"
]

END_SESSION_TRIGGERS = [
    "reset session", "end session", "finish session",
    "nuevo caso", "nueva falla", "start over"
]


# =======================
# SESSION MANAGEMENT FUNCTIONS
# =======================

def reset_session(save_to_db: bool = True):
    """Reset session and optionally save to database."""
    if save_to_db and session_state["session_id"]:
        save_session(
            session_state["session_id"],
            session_state,
            topic=session_state.get("topic", ""),
            model=session_state.get("model", ""),
            mode=session_state.get("mode", "")
        )
    
    session_state["active"] = False
    session_state["topic"] = None
    session_state["finding_log"] = []
    session_state["turns"] = 0
    session_state["session_id"] = None
    session_state["model"] = None
    session_state["mode"] = None


def start_new_session(topic: str, model: str, mode: str) -> str:
    """Start a new troubleshooting session and return session_id."""
    session_id = generate_session_id()
    session_state["active"] = True
    session_state["topic"] = topic
    session_state["finding_log"] = [f"Initial question: {topic}"]
    session_state["turns"] = 1
    session_state["session_id"] = session_id
    session_state["model"] = model
    session_state["mode"] = mode
    return session_id


def resume_session(session_id: str) -> bool:
    """Load and resume a previous session."""
    saved_state = load_session(session_id)
    if not saved_state:
        return False
    
    session_state.update(saved_state)
    session_state["active"] = True
    session_state["session_id"] = session_id
    return True


def export_session_to_text() -> str:
    """Export current session to formatted text report."""
    if not session_state["session_id"]:
        return "No active session to export."
    
    lines = []
    lines.append("=" * 70)
    lines.append("NOVA RAG - TROUBLESHOOTING SESSION REPORT")
    lines.append("=" * 70)
    lines.append(f"Session ID: {session_state['session_id']}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Model: {session_state.get('model', 'Unknown')}")
    lines.append(f"Mode: {session_state.get('mode', 'Unknown')}")
    lines.append(f"Total Turns: {session_state['turns']}")
    lines.append("")
    lines.append("TOPIC:")
    lines.append(session_state.get('topic', 'N/A'))
    lines.append("")
    lines.append("FINDINGS LOG:")
    lines.append("-" * 70)
    for i, finding in enumerate(session_state.get('finding_log', []), 1):
        lines.append(f"{i}. {finding}")
    lines.append("")
    
    if session_state.get('feedback'):
        lines.append("FEEDBACK:")
        lines.append("-" * 70)
        for fb in session_state['feedback']:
            lines.append(f"- {fb}")
        lines.append("")
    
    lines.append("=" * 70)
    lines.append("End of Report")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def save_session_report() -> str:
    """Save session report to file and return filepath."""
    if not session_state["session_id"]:
        return "No active session to save."
    
    report_text = export_session_to_text()
    
    reports_dir = INDEX_DIR / "session_reports"
    reports_dir.mkdir(exist_ok=True)
    
    filename = f"session_{session_state['session_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = reports_dir / filename
    
    with filepath.open("w", encoding="utf-8") as f:
        f.write(report_text)
    
    return f"✅ Session report saved to:\n{filepath}"


def build_conversation_context() -> str:
    """Build conversation context from recent turn history."""
    if not session_state.get("turn_history"):
        return ""
    
    context_lines = ["PREVIOUS CONVERSATION HISTORY:"]
    # Include last 3 turns for context window management
    recent_turns = session_state["turn_history"][-3:]
    
    for i, (q, a) in enumerate(recent_turns, 1):
        context_lines.append(f"\nTurn {i}:")
        context_lines.append(f"User: {q}")
        context_lines.append(f"Assistant: {a[:200]}..." if len(a) > 200 else f"Assistant: {a}")
    
    return "\n".join(context_lines)
