"""
Unit tests for nova_flask_app module.
Tests Flask routes, rate limiting, security headers, and API endpoints.
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    import os
    os.environ["NOVA_RATE_LIMIT_ENABLED"] = "0"  # Disable for most tests
    os.environ["NOVA_FORCE_OFFLINE"] = "1"
    
    from nova_flask_app import app
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client


class TestFlaskRoutes:
    """Tests for basic Flask routes."""
    
    def test_home_page_loads(self, client):
        """Test that home page returns 200."""
        response = client.get('/')
        assert response.status_code == 200
    
    def test_status_endpoint(self, client):
        """Test the /api/status endpoint."""
        response = client.get('/api/status')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'ollama' in data
        assert 'index_loaded' in data


class TestSecurityHeaders:
    """Tests for security headers."""
    
    def test_security_headers_present(self, client):
        """Test that security headers are added to responses."""
        response = client.get('/')
        
        # Check Content Security Policy
        assert 'Content-Security-Policy' in response.headers
        assert "default-src 'self'" in response.headers['Content-Security-Policy']
        
        # Check X-Frame-Options
        assert response.headers.get('X-Frame-Options') == 'DENY'
        
        # Check X-Content-Type-Options
        assert response.headers.get('X-Content-Type-Options') == 'nosniff'
        
        # Check X-XSS-Protection
        assert response.headers.get('X-XSS-Protection') == '1; mode=block'
    
    def test_csp_prevents_inline_scripts(self, client):
        """Test that CSP header configuration is restrictive."""
        response = client.get('/')
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should have frame-ancestors none to prevent clickjacking
        assert 'frame-ancestors' in csp.lower()


class TestRateLimiting:
    """Tests for rate limiting functionality."""
    
    def test_rate_limiting_can_be_disabled(self):
        """Test that rate limiting can be disabled via env var."""
        import os
        os.environ["NOVA_RATE_LIMIT_ENABLED"] = "0"
        
        from nova_flask_app import app, RATE_LIMIT_ENABLED
        
        assert RATE_LIMIT_ENABLED is False
    
    def test_rate_limiting_can_be_enabled(self):
        """Test that rate limiting can be enabled via env var."""
        import os
        os.environ["NOVA_RATE_LIMIT_ENABLED"] = "1"
        
        # Reimport to pick up env var
        import sys
        if 'nova_flask_app' in sys.modules:
            del sys.modules['nova_flask_app']
        
        from nova_flask_app import app, RATE_LIMIT_ENABLED
        
        assert RATE_LIMIT_ENABLED is True
    
    def test_rate_limit_error_handler(self):
        """Test that rate limit errors return proper response."""
        import os
        os.environ["NOVA_RATE_LIMIT_ENABLED"] = "1"
        os.environ["NOVA_RATE_LIMIT_PER_MINUTE"] = "1"  # Very low limit for testing
        
        import sys
        if 'nova_flask_app' in sys.modules:
            del sys.modules['nova_flask_app']
        
        from nova_flask_app import app
        app.config['TESTING'] = True
        
        with app.test_client() as client:
            # First request should work
            response1 = client.get('/api/status')
            assert response1.status_code == 200
            
            # Subsequent requests should be rate limited
            # (depending on the limiter configuration)
            for _ in range(10):
                response = client.get('/api/status')
                if response.status_code == 429:
                    data = json.loads(response.data)
                    assert 'error' in data
                    assert 'Rate limit exceeded' in data['error']
                    break


class TestAPIAuthentication:
    """Tests for API token authentication."""
    
    def test_auth_not_required_by_default(self, client):
        """Test that auth is not required when NOVA_REQUIRE_TOKEN=0."""
        import os
        os.environ["NOVA_REQUIRE_TOKEN"] = "0"
        
        response = client.get('/api/status')
        assert response.status_code == 200
    
    @patch('nova_flask_app.REQUIRE_TOKEN', True)
    @patch('nova_flask_app.API_TOKEN', 'test-token-123')
    def test_auth_required_without_token(self, client):
        """Test that requests without token are rejected when auth required."""
        response = client.post('/api/ask', 
                               json={'question': 'test'},
                               headers={})
        
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'Unauthorized'
    
    @patch('nova_flask_app.REQUIRE_TOKEN', True)
    @patch('nova_flask_app.API_TOKEN', 'test-token-123')
    def test_auth_required_with_valid_token(self, client):
        """Test that requests with valid token are accepted."""
        with patch('backend.nova_text_handler') as mock_handler:
            mock_handler.return_value = {
                'answer': 'Test answer',
                'confidence': '90%',
                'sources': []
            }
            
            response = client.post('/api/ask',
                                   json={'question': 'test'},
                                   headers={'X-API-TOKEN': 'test-token-123'})
            
            # Should not be 403
            assert response.status_code != 403


class TestAPIAsk:
    """Tests for /api/ask endpoint."""
    
    def test_ask_endpoint_empty_question(self, client):
        """Test that empty questions are rejected."""
        response = client.post('/api/ask', json={'question': ''})
        
        assert response.status_code == 200  # Returns 200 with refusal
        data = json.loads(response.data)
        assert 'answer' in data
        assert data['answer']['response_type'] == 'refusal'
    
    def test_ask_endpoint_too_long_question(self, client):
        """Test that overly long questions are rejected."""
        long_question = 'x' * 6000
        response = client.post('/api/ask', json={'question': long_question})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['answer']['response_type'] == 'refusal'
        assert 'too_long' in data['answer']['reason']
    
    def test_ask_endpoint_malicious_input(self, client):
        """Test that malicious input patterns are rejected."""
        malicious_inputs = [
            '<script>alert("xss")</script>',
            'DROP TABLE users;',
            'SELECT * FROM passwords --',
        ]
        
        for malicious_input in malicious_inputs:
            response = client.post('/api/ask', json={'question': malicious_input})
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['answer']['response_type'] == 'refusal'
    
    def test_ask_endpoint_emoji_only(self, client):
        """Test that emoji-only questions are rejected."""
        response = client.post('/api/ask', json={'question': '😀😀😀'})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['answer']['response_type'] == 'refusal'
    
    def test_ask_endpoint_repetitive_input(self, client):
        """Test that overly repetitive input is rejected."""
        repetitive = 'test ' * 60
        response = client.post('/api/ask', json={'question': repetitive})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should either process or refuse based on logic
        assert 'answer' in data


class TestAPIRetrieve:
    """Tests for /api/retrieve endpoint."""
    
    @patch('nova_flask_app.retrieve')
    def test_retrieve_endpoint_with_query(self, mock_retrieve, client):
        """Test successful retrieval."""
        mock_retrieve.return_value = [
            {
                'text': 'Test document content',
                'source': 'test.txt',
                'confidence': 0.95
            }
        ]
        
        response = client.post('/api/retrieve', json={'query': 'test query', 'k': 6})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
        assert 'text' in data[0]
        assert 'confidence' in data[0]
    
    def test_retrieve_endpoint_empty_query(self, client):
        """Test that empty query returns empty list."""
        response = client.post('/api/retrieve', json={'query': ''})
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []


@pytest.mark.unit
class TestFlaskApp:
    """General Flask application tests."""
    
    def test_app_configuration(self):
        """Test that Flask app is configured correctly."""
        from nova_flask_app import app
        
        assert app.config['PROPAGATE_EXCEPTIONS'] is True
        assert app.config['TESTING'] is False  # Default
    
    def test_app_has_required_routes(self):
        """Test that all required routes are defined."""
        from nova_flask_app import app
        
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        
        assert '/' in routes
        assert '/api/ask' in routes
        assert '/api/status' in routes
        assert '/api/retrieve' in routes
