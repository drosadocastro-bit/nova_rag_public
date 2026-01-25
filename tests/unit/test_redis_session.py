"""
Tests for Redis Session Store.

Tests the distributed session management including:
- Session creation and retrieval
- Session updates
- Expiration handling
- Distributed locking
"""

import time
from unittest.mock import Mock, patch, MagicMock

import pytest

# Skip all tests if redis not available
pytest.importorskip("redis")

from core.session.redis_session import (
    RedisSessionStore,
    SessionConfig,
    Session,
    SessionMiddleware,
    get_session_store,
    set_session_store,
)


class TestSessionConfig:
    """Tests for SessionConfig."""
    
    def test_default_values(self):
        """Test default configuration."""
        config = SessionConfig()
        
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 1  # Separate from cache
        assert config.default_ttl_seconds == 3600
    
    def test_from_env(self):
        """Test configuration from environment."""
        with patch.dict("os.environ", {
            "REDIS_HOST": "session.redis.local",
            "REDIS_PORT": "6381",
            "REDIS_SESSION_DB": "3",
            "SESSION_TTL_SECONDS": "7200",
        }):
            config = SessionConfig.from_env()
            
            assert config.host == "session.redis.local"
            assert config.port == 6381
            assert config.db == 3
            assert config.default_ttl_seconds == 7200


class TestSession:
    """Tests for Session dataclass."""
    
    def test_default_values(self):
        """Test default session values."""
        session = Session(session_id="test-123")
        
        assert session.session_id == "test-123"
        assert session.user_id is None
        assert session.data == {}
        assert session.messages == []
        assert session.created_at > 0
    
    def test_is_expired(self):
        """Test expiration check."""
        # Not expired
        session1 = Session(
            session_id="test",
            expires_at=time.time() + 3600,
        )
        assert session1.is_expired is False
        
        # Expired
        session2 = Session(
            session_id="test",
            expires_at=time.time() - 3600,
        )
        assert session2.is_expired is True
        
        # No expiration set
        session3 = Session(session_id="test")
        assert session3.is_expired is False
    
    def test_age(self):
        """Test session age calculation."""
        session = Session(
            session_id="test",
            created_at=time.time() - 100,
        )
        
        assert 99 < session.age_seconds < 101
    
    def test_touch(self):
        """Test updating last accessed time."""
        session = Session(session_id="test")
        old_accessed = session.last_accessed
        
        time.sleep(0.1)
        session.touch()
        
        assert session.last_accessed > old_accessed
    
    def test_add_message(self):
        """Test adding messages."""
        session = Session(session_id="test")
        
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello"
    
    def test_get_conversation_context(self):
        """Test getting conversation context."""
        session = Session(session_id="test")
        
        for i in range(15):
            session.add_message("user", f"Message {i}")
        
        context = session.get_conversation_context(max_messages=5)
        
        assert len(context) == 5
        assert context[0]["content"] == "Message 10"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        session = Session(
            session_id="test-123",
            user_id="user-456",
            data={"key": "value"},
        )
        
        d = session.to_dict()
        
        assert d["session_id"] == "test-123"
        assert d["user_id"] == "user-456"
        assert d["data"] == {"key": "value"}
    
    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "session_id": "test-123",
            "user_id": "user-456",
            "created_at": 1000.0,
            "last_accessed": 2000.0,
            "data": {"key": "value"},
            "messages": [{"role": "user", "content": "hi"}],
        }
        
        session = Session.from_dict(data)
        
        assert session.session_id == "test-123"
        assert session.user_id == "user-456"
        assert session.data == {"key": "value"}
        assert len(session.messages) == 1


class TestRedisSessionStoreMocked:
    """Tests for RedisSessionStore with mocked Redis."""
    
    @pytest.fixture
    def mock_store(self):
        """Create store with mocked Redis."""
        mock_client = MagicMock()
        
        with patch("redis.Redis", return_value=mock_client):
            store = RedisSessionStore()
            store._client = mock_client
            yield store, mock_client
    
    def test_create_session(self, mock_store):
        """Test session creation."""
        store, mock_client = mock_store
        
        session = store.create_session(user_id="user-123")
        
        assert session.session_id is not None
        assert session.user_id == "user-123"
        assert session.expires_at > time.time()
        mock_client.setex.assert_called_once()
    
    def test_create_session_with_data(self, mock_store):
        """Test session creation with initial data."""
        store, _ = mock_store
        
        session = store.create_session(
            initial_data={"role": "admin"},
        )
        
        assert session.data == {"role": "admin"}
    
    def test_get_session_found(self, mock_store):
        """Test getting existing session."""
        store, mock_client = mock_store
        
        # Create serialized session data
        import pickle
        import zlib
        
        original = Session(
            session_id="test-123",
            expires_at=time.time() + 3600,
        )
        data = pickle.dumps(original.to_dict())
        mock_client.get.return_value = b"U" + data
        
        session = store.get_session("test-123")
        
        assert session is not None
        assert session.session_id == "test-123"
    
    def test_get_session_not_found(self, mock_store):
        """Test getting non-existent session."""
        store, mock_client = mock_store
        mock_client.get.return_value = None
        
        session = store.get_session("nonexistent")
        
        assert session is None
    
    def test_get_session_expired(self, mock_store):
        """Test getting expired session."""
        store, mock_client = mock_store
        
        # Create expired session
        import pickle
        
        expired = Session(
            session_id="expired-123",
            expires_at=time.time() - 3600,
        )
        data = pickle.dumps(expired.to_dict())
        mock_client.get.return_value = b"U" + data
        
        session = store.get_session("expired-123")
        
        assert session is None
        mock_client.delete.assert_called_once()
    
    def test_update_session(self, mock_store):
        """Test session update."""
        store, mock_client = mock_store
        
        session = Session(session_id="test-123")
        session.data["updated"] = True
        
        result = store.update_session(session)
        
        assert result is True
        mock_client.setex.assert_called_once()
    
    def test_update_session_extends_ttl(self, mock_store):
        """Test that update extends TTL."""
        store, _ = mock_store
        
        original_expires = time.time() + 100
        session = Session(
            session_id="test-123",
            expires_at=original_expires,
        )
        
        store.update_session(session, extend_ttl=True)
        
        # Expiration should be extended
        assert session.expires_at > original_expires
    
    def test_delete_session(self, mock_store):
        """Test session deletion."""
        store, mock_client = mock_store
        mock_client.delete.return_value = 1
        
        result = store.delete_session("test-123")
        
        assert result is True
    
    def test_exists(self, mock_store):
        """Test session exists check."""
        store, mock_client = mock_store
        mock_client.exists.return_value = 1
        
        result = store.exists("test-123")
        
        assert result is True
    
    def test_acquire_lock(self, mock_store):
        """Test distributed lock acquisition."""
        store, mock_client = mock_store
        mock_client.set.return_value = True
        
        result = store.acquire_lock("session-123")
        
        assert result is True
        mock_client.set.assert_called_once()
    
    def test_acquire_lock_fails(self, mock_store):
        """Test lock acquisition failure."""
        store, mock_client = mock_store
        mock_client.set.return_value = None  # Lock not acquired
        
        result = store.acquire_lock("session-123")
        
        assert result is False
    
    def test_release_lock(self, mock_store):
        """Test lock release."""
        store, mock_client = mock_store
        mock_client.delete.return_value = 1
        
        result = store.release_lock("session-123")
        
        assert result is True
    
    def test_get_stats(self, mock_store):
        """Test statistics."""
        store, mock_client = mock_store
        mock_client.info.return_value = {"db1": {"keys": 100}}
        
        store._sessions_created = 50
        store._sessions_loaded = 200
        
        stats = store.get_stats()
        
        assert stats["sessions_created"] == 50
        assert stats["sessions_loaded"] == 200
    
    def test_health_check_success(self, mock_store):
        """Test health check success."""
        store, mock_client = mock_store
        mock_client.ping.return_value = True
        
        healthy, message = store.health_check()
        
        assert healthy is True
        assert "connected" in message.lower()
    
    def test_health_check_failure(self, mock_store):
        """Test health check failure."""
        store, mock_client = mock_store
        mock_client.ping.side_effect = Exception("Connection lost")
        
        healthy, message = store.health_check()
        
        assert healthy is False


class TestSessionMiddleware:
    """Tests for SessionMiddleware."""
    
    @pytest.fixture
    def mock_middleware(self):
        """Create middleware with mock store."""
        mock_store = MagicMock()
        middleware = SessionMiddleware(mock_store)
        return middleware, mock_store
    
    def test_get_session_id_from_header(self, mock_middleware):
        """Test extracting session ID from header."""
        middleware, _ = mock_middleware
        
        request = MagicMock()
        request.headers = {"X-Session-ID": "header-session-123"}
        
        session_id = middleware.get_session_id(request)
        
        assert session_id == "header-session-123"
    
    def test_get_session_id_from_cookie(self, mock_middleware):
        """Test extracting session ID from cookie."""
        middleware, _ = mock_middleware
        
        request = MagicMock()
        request.headers = {}
        request.cookies = {"nova_session": "cookie-session-123"}
        
        session_id = middleware.get_session_id(request)
        
        assert session_id == "cookie-session-123"
    
    def test_get_session_id_none(self, mock_middleware):
        """Test when no session ID present."""
        middleware, _ = mock_middleware
        
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        
        session_id = middleware.get_session_id(request)
        
        assert session_id is None
    
    def test_load_session_existing(self, mock_middleware):
        """Test loading existing session."""
        middleware, mock_store = mock_middleware
        
        existing_session = Session(session_id="existing-123")
        mock_store.get_session.return_value = existing_session
        
        request = MagicMock()
        request.headers = {"X-Session-ID": "existing-123"}
        
        session = middleware.load_session(request)
        
        assert session.session_id == "existing-123"
        assert request.session is session
    
    def test_load_session_creates_new(self, mock_middleware):
        """Test creating new session when none exists."""
        middleware, mock_store = mock_middleware
        
        mock_store.get_session.return_value = None
        new_session = Session(session_id="new-123")
        mock_store.create_session.return_value = new_session
        
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        
        session = middleware.load_session(request)
        
        assert session.session_id == "new-123"
        mock_store.create_session.assert_called_once()
    
    def test_save_session(self, mock_middleware):
        """Test saving session to response."""
        middleware, mock_store = mock_middleware
        
        request = MagicMock()
        request.session = Session(session_id="save-123")
        
        response = MagicMock()
        
        result = middleware.save_session(request, response)
        
        mock_store.update_session.assert_called_once()
        response.set_cookie.assert_called_once()
        assert result is response


class TestGlobalStoreFunctions:
    """Tests for global store functions."""
    
    @pytest.fixture(autouse=True)
    def reset_global(self):
        """Reset global store."""
        import core.session.redis_session as module
        module._global_store = None
        yield
        module._global_store = None
    
    def test_set_and_get_session_store(self):
        """Test setting and getting global store."""
        mock_client = MagicMock()
        
        with patch("redis.Redis", return_value=mock_client):
            store = RedisSessionStore()
            
            set_session_store(store)
            retrieved = get_session_store()
            
            assert retrieved is store


class TestSessionCompression:
    """Tests for session compression."""
    
    @pytest.fixture
    def store(self):
        """Create store with mock."""
        mock_client = MagicMock()
        
        with patch("redis.Redis", return_value=mock_client):
            config = SessionConfig(enable_compression=True)
            store = RedisSessionStore(config)
            return store
    
    def test_small_session_not_compressed(self, store):
        """Small sessions are not compressed."""
        session = Session(session_id="small", data={"key": "value"})
        
        serialized = store._serialize(session)
        
        # Should start with 'U' (uncompressed)
        assert serialized[0:1] == b"U"
    
    def test_large_session_compressed(self, store):
        """Large sessions are compressed."""
        # Create session with lots of data
        large_data = {"key": "x" * 10000}
        session = Session(session_id="large", data=large_data)
        
        serialized = store._serialize(session)
        
        # Should start with 'C' (compressed)
        assert serialized[0:1] == b"C"
    
    def test_roundtrip_compression(self, store):
        """Test serialization/deserialization with compression."""
        original = Session(
            session_id="roundtrip",
            user_id="user-123",
            data={"large": "x" * 5000},
            messages=[{"role": "user", "content": "Hello"}],
        )
        
        serialized = store._serialize(original)
        restored = store._deserialize(serialized)
        
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.data == original.data
        assert restored.messages == original.messages
