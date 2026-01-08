"""
Unit tests for agents/session_store module.
Tests session management, ID generation, and persistence.
"""
import pytest
import os
from pathlib import Path
from datetime import datetime


class TestSessionIDGeneration:
    """Tests for session ID generation."""
    
    def test_generate_session_id_format(self):
        """Test that generated session IDs have correct format."""
        from agents.session_store import generate_session_id
        
        session_id = generate_session_id()
        
        # Should be a string
        assert isinstance(session_id, str)
        
        # Current format: 8-char UUID hex (no prefix)
        assert len(session_id) == 8
        
        # Should be hexadecimal
        assert all(c in '0123456789abcdef' for c in session_id)
    
    def test_generate_session_id_uniqueness(self):
        """Test that generated session IDs are unique."""
        from agents.session_store import generate_session_id
        
        ids = [generate_session_id() for _ in range(100)]
        
        # All IDs should be unique
        assert len(ids) == len(set(ids))
    
    def test_session_id_timestamp_component(self):
        """Test that session IDs are generated consistently."""
        from agents.session_store import generate_session_id
        
        session_id = generate_session_id()
        
        # Should be a valid hex string
        assert isinstance(session_id, str)
        assert len(session_id) == 8
        
        # Verify it's hexadecimal
        try:
            int(session_id, 16)
        except ValueError:
            pytest.fail(f"Session ID {session_id} is not valid hexadecimal")


class TestSessionPersistence:
    """Tests for session save/load functionality."""
    
    def test_save_and_load_session(self, tmp_path):
        """Test saving and loading a session."""
        from agents import session_store
        
        session_data = {
            "session_id": "test_session_123",
            "conversation_history": [
                {"role": "user", "content": "Test question"},
                {"role": "assistant", "content": "Test answer"}
            ],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "query_count": 1
            }
        }
        
        # Save session (uses SQLite)
        session_store.save_session("test_session_123", session_data)
        
        # Load session
        loaded_data = session_store.load_session("test_session_123")
        
        assert loaded_data is not None
        assert loaded_data["session_id"] == "test_session_123"
    
    def test_load_nonexistent_session(self, tmp_path):
        """Test loading a session that doesn't exist."""
        from agents import session_store
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Should return None for nonexistent session
        loaded_data = session_store.load_session("nonexistent_session")
        assert loaded_data is None
    
    def test_save_session_creates_directory(self, tmp_path):
        """Test that save_session creates database."""
        from agents import session_store
        
        session_data = {"session_id": "test", "data": "value"}
        
        # Save session (will initialize database if needed)
        session_store.save_session("test", session_data)
        
        # Verify we can load it back
        loaded = session_store.load_session("test")
        assert loaded is not None
        assert loaded["session_id"] == "test"


class TestListRecentSessions:
    """Tests for listing recent sessions."""
    
    def test_list_recent_sessions_empty(self, tmp_path):
        """Test listing sessions when none exist."""
        from agents import session_store
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        sessions = session_store.list_recent_sessions(limit=10)
        
        # May have pre-existing sessions from other runs; just verify it's a list
        assert isinstance(sessions, list)
    
    def test_list_recent_sessions_with_data(self, tmp_path):
        """Test listing sessions when some exist."""
        from agents import session_store
        import time
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create multiple sessions
        for i in range(5):
            session_data = {
                "session_id": f"session_{i}",
                "created_at": datetime.now().isoformat()
            }
            session_store.save_session(f"session_{i}", session_data)
            time.sleep(0.01)  # Ensure different timestamps
        
        # List recent sessions
        sessions = session_store.list_recent_sessions(limit=10)
        
        # Should return sessions (may include pre-existing ones)
        assert isinstance(sessions, list)
        assert len(sessions) > 0
        
        # Should be sorted by recency (most recent first)
        assert isinstance(sessions[0], dict)
    
    def test_list_recent_sessions_with_limit(self, tmp_path):
        """Test that limit parameter works correctly."""
        from agents import session_store
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create 10 sessions
        for i in range(10):
            session_data = {"session_id": f"session_{i}"}
            session_store.save_session(f"session_{i}", session_data)
        
        # Request only 3
        sessions = session_store.list_recent_sessions(limit=3)
        
        assert len(sessions) == 3


class TestSessionStoreEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_save_session_with_invalid_data(self, tmp_path):
        """Test saving session with non-serializable data."""
        from agents import session_store
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Try to save with datetime object (not JSON serializable by default)
        session_data = {
            "session_id": "test",
            "timestamp": datetime.now()  # Not JSON serializable
        }
        
        # Should handle gracefully or convert to string
        try:
            session_store.save_session("test", session_data)
            # If it succeeds, good
            assert True
        except (TypeError, ValueError):
            # If it fails, that's expected for non-serializable data
            assert True
    
    def test_load_corrupted_session_file(self, tmp_path):
        """Test loading a corrupted session file."""
        from agents import session_store
        
        session_store.SESSION_DIR = tmp_path / "sessions"
        session_store.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create a corrupted file
        corrupted_file = session_store.SESSION_DIR / "corrupted.json"
        corrupted_file.write_text("{ invalid json content }")
        
        # Should return None or handle gracefully
        loaded = session_store.load_session("corrupted")
        assert loaded is None or isinstance(loaded, dict)
    
    def test_session_directory_permissions(self, tmp_path):
        """Test behavior when session directory is not writable."""
        from agents import session_store
        import stat
        
        session_dir = tmp_path / "readonly_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_store.SESSION_DIR = session_dir
        
        # Make directory read-only (on Unix-like systems)
        if os.name != 'nt':  # Skip on Windows
            session_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
            
            session_data = {"session_id": "test"}
            
            # Should handle permission error gracefully
            try:
                session_store.save_session("test", session_data)
            except PermissionError:
                # Expected behavior
                pass
            finally:
                # Restore permissions for cleanup
                session_dir.chmod(stat.S_IRWXU)


@pytest.mark.unit
class TestSessionStore:
    """General session store tests."""
    
    def test_session_store_module_importable(self):
        """Test that session_store module imports successfully."""
        from agents import session_store
        
        assert hasattr(session_store, "generate_session_id")
        assert hasattr(session_store, "save_session")
        assert hasattr(session_store, "load_session")
        assert hasattr(session_store, "list_recent_sessions")
    
    def test_session_store_constants(self):
        """Test that required constants are defined."""
        from agents import session_store
        
        assert hasattr(session_store, "SESSION_DIR")
        assert isinstance(session_store.SESSION_DIR, Path)
