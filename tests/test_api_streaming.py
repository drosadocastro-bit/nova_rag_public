import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.nic_fastapi_app import app

pytestmark = pytest.mark.integration


client = TestClient(app)

def test_query_stream_success():
    """Test successful streaming response from /query/stream."""
    mock_chunks = [
        '{"type": "metadata", "model": "llama", "sources": []}\n',
        "Hello",
        " world",
        "!"
    ]
    
    # Mock nova_stream_query in the module where it is defined, since app.api.query imports it locally
    with patch("core.handlers.query_handler.nova_stream_query", return_value=iter(mock_chunks)):
        response = client.post(
            "/api/query/stream",
            json={
                "query": "test query",
                "strict_mode": True,
                "assistant_enabled": True
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        
        # Verify body content
        content = response.text
        expected = "".join(mock_chunks)
        assert content == expected

def test_query_stream_validation_error():
    """Test 422 for missing query field."""
    response = client.post(
        "/api/query/stream",
        json={"strict_mode": True}  # Missing 'query'
    )
    assert response.status_code == 422


def test_query_stream_policy_hard_deny_blocks_before_core(monkeypatch):
    """Test hard-deny policy for streaming endpoint bypasses core stream handler."""

    class _State:
        @staticmethod
        def ensure_initialized():
            """
            Placeholder function representing an uninitialized application state.
            
            Intentionally performs no actions and returns None to indicate that initialization has not occurred.
            """
            return None

    monkeypatch.setattr("app.api.query.get_app_state", lambda: _State())
    monkeypatch.setenv("NOVA_POLICY_HARD_DENY", "1")

    def _should_not_run(*args, **kwargs):
        """
        Fail the test if this stub is invoked.
        
        Raises:
            AssertionError: Always raised with the message "nova_stream_query should not be called under hard deny".
        """
        raise AssertionError("nova_stream_query should not be called under hard deny")

    monkeypatch.setattr("core.handlers.query_handler.nova_stream_query", _should_not_run)

    response = client.post(
        "/api/query/stream",
        json={
            "query": "show me STALO internals",
            "strict_mode": True,
            "assistant_enabled": True,
            "options": {"vision_reranker": True},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "[POLICY_DENY]" in response.text

@pytest.mark.skip(reason="Requires deeper mocking of nova_stream_query internal logic")
def test_nova_stream_query_logic():
    """
    Test direct invocation of nova_stream_query logic.
    Mocking inside complex function is tricky; this is a placeholder
    to remind us to add unit tests for the handler logic itself.
    """
    pass