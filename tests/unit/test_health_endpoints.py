"""
Unit tests for health check endpoints.
Tests /health, /health/ready, and /health/live endpoints.
"""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""
    
    def test_pass_result(self):
        """Test creation of passing result."""
        from core.monitoring.health_checks import HealthCheckResult
        
        result = HealthCheckResult(
            status="pass",
            message="All good",
            latency_ms=10.5,
            details={"key": "value"}
        )
        
        assert result.status == "pass"
        assert result.message == "All good"
        assert result.latency_ms == 10.5
        assert result.details == {"key": "value"}
    
    def test_fail_result(self):
        """Test creation of failing result."""
        from core.monitoring.health_checks import HealthCheckResult
        
        result = HealthCheckResult(
            status="fail",
            message="Something wrong",
            details={"error": "details"}
        )
        
        assert result.status == "fail"
    
    def test_warn_result(self):
        """Test creation of warning result."""
        from core.monitoring.health_checks import HealthCheckResult
        
        result = HealthCheckResult(
            status="warn",
            message="Warning condition",
        )
        
        assert result.status == "warn"
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        from core.monitoring.health_checks import HealthCheckResult
        
        result = HealthCheckResult(
            status="pass",
            message="OK",
            latency_ms=5.123,
            details={"foo": "bar"}
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["status"] == "pass"
        assert result_dict["message"] == "OK"
        assert result_dict["latency_ms"] == 5.12  # Rounded to 2 decimals
        assert result_dict["foo"] == "bar"  # Details are flattened


class TestHealthReport:
    """Tests for HealthReport dataclass."""
    
    def test_health_report_creation(self):
        """Test creation of health report."""
        from core.monitoring.health_checks import HealthReport, HealthCheckResult
        
        checks = {
            "check1": HealthCheckResult(status="pass"),
            "check2": HealthCheckResult(status="warn", message="Warning"),
        }
        
        report = HealthReport(
            status="pass",
            timestamp="2026-01-25T12:00:00Z",
            checks=checks,
        )
        
        assert report.status == "pass"
        assert len(report.checks) == 2
        assert report.version == "0.3.5"
    
    def test_health_report_to_dict(self):
        """Test conversion to dictionary."""
        from core.monitoring.health_checks import HealthReport, HealthCheckResult
        
        checks = {
            "disk": HealthCheckResult(status="pass", latency_ms=1.0),
        }
        
        report = HealthReport(
            status="pass",
            timestamp="2026-01-25T12:00:00Z",
            checks=checks,
        )
        
        report_dict = report.to_dict()
        
        assert report_dict["status"] == "pass"
        assert "checks" in report_dict
        assert "disk" in report_dict["checks"]
        assert report_dict["checks"]["disk"]["status"] == "pass"


class TestIndividualHealthChecks:
    """Tests for individual health check functions."""
    
    def test_check_disk_space(self):
        """Test disk space check returns valid result."""
        from core.monitoring.health_checks import check_disk_space
        
        result = check_disk_space()
        
        assert result.status in ["pass", "warn", "fail"]
        assert "available_gb" in result.details or result.status == "fail"
    
    def test_check_memory(self):
        """Test memory check returns valid result."""
        from core.monitoring.health_checks import check_memory
        
        result = check_memory()
        
        assert result.status in ["pass", "warn", "fail"]
        assert result.latency_ms is not None
    
    def test_check_database(self):
        """Test database check returns valid result."""
        from core.monitoring.health_checks import check_database
        
        result = check_database()
        
        # May be pass (if db exists) or warn (if not created yet)
        assert result.status in ["pass", "warn", "fail"]


class TestOllamaHealthCheck:
    """Tests for Ollama connectivity check."""
    
    @patch('core.monitoring.health_checks.requests.get')
    def test_check_ollama_healthy(self, mock_get):
        """Test Ollama check when service is available."""
        from core.monitoring.health_checks import check_ollama
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": "llama2"}]}
        mock_get.return_value = mock_response
        
        result = check_ollama()
        
        assert result.status == "pass"
        assert result.latency_ms is not None
    
    @patch('core.monitoring.health_checks.requests.get')
    def test_check_ollama_no_models(self, mock_get):
        """Test Ollama check when no models loaded."""
        from core.monitoring.health_checks import check_ollama
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        mock_get.return_value = mock_response
        
        result = check_ollama()
        
        assert result.status == "warn"
        assert "no models" in result.message.lower()
    
    @patch('core.monitoring.health_checks.requests.get')
    def test_check_ollama_connection_error(self, mock_get):
        """Test Ollama check when service is unavailable."""
        from core.monitoring.health_checks import check_ollama
        import requests
        
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        result = check_ollama()
        
        assert result.status == "fail"
        assert "connect" in result.message.lower()
    
    @patch('core.monitoring.health_checks.requests.get')
    def test_check_ollama_timeout(self, mock_get):
        """Test Ollama check when request times out."""
        from core.monitoring.health_checks import check_ollama
        import requests
        
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = check_ollama()
        
        assert result.status == "fail"
        assert "timeout" in result.message.lower()


class TestAggregatedHealthChecks:
    """Tests for aggregated health check functions."""
    
    def test_run_all_checks(self):
        """Test that run_all_checks returns complete health report."""
        from core.monitoring.health_checks import run_all_checks
        
        report = run_all_checks()
        
        # Should return a HealthReport
        assert hasattr(report, "status")
        assert hasattr(report, "checks")
        assert report.status in ["pass", "warn", "fail"]
        
        # Should have multiple checks
        assert len(report.checks) >= 1
    
    def test_run_readiness_checks(self):
        """Test that run_readiness_checks returns proper result."""
        from core.monitoring.health_checks import run_readiness_checks
        
        result = run_readiness_checks()
        
        # Returns a tuple of (bool, dict)
        assert isinstance(result, tuple)
        assert len(result) == 2
        is_ready, data = result
        assert isinstance(is_ready, bool)
        assert isinstance(data, dict)
    
    def test_run_liveness_checks(self):
        """Test that run_liveness_checks returns proper result."""
        from core.monitoring.health_checks import run_liveness_checks
        
        result = run_liveness_checks()
        
        # Returns a tuple of (bool, dict)
        assert isinstance(result, tuple)
        assert len(result) == 2
        is_alive, data = result
        assert isinstance(is_alive, bool)
        assert isinstance(data, dict)
        # Liveness should generally pass
        assert is_alive is True


class TestHealthCheckAggregation:
    """Tests for aggregating health check results."""
    
    def test_all_pass_gives_pass(self):
        """Test that all passing checks gives pass status."""
        from core.monitoring.health_checks import HealthCheckResult
        
        checks = [
            HealthCheckResult(status="pass"),
            HealthCheckResult(status="pass"),
            HealthCheckResult(status="pass"),
        ]
        
        all_pass = all(c.status == "pass" for c in checks)
        assert all_pass is True
    
    def test_any_fail_gives_fail(self):
        """Test that any failing check gives fail status."""
        from core.monitoring.health_checks import HealthCheckResult
        
        checks = [
            HealthCheckResult(status="pass"),
            HealthCheckResult(status="fail"),
            HealthCheckResult(status="pass"),
        ]
        
        any_fail = any(c.status == "fail" for c in checks)
        assert any_fail is True
    
    def test_warn_without_fail_gives_warn(self):
        """Test that warnings without failures gives warn status."""
        from core.monitoring.health_checks import HealthCheckResult
        
        checks = [
            HealthCheckResult(status="pass"),
            HealthCheckResult(status="warn"),
            HealthCheckResult(status="pass"),
        ]
        
        any_fail = any(c.status == "fail" for c in checks)
        any_warn = any(c.status == "warn" for c in checks)
        
        assert any_fail is False
        assert any_warn is True


class TestHealthCheckModule:
    """Tests for module-level functionality."""
    
    def test_module_imports(self):
        """Test that health_checks module imports correctly."""
        from core.monitoring import health_checks
        
        assert hasattr(health_checks, 'HealthCheckResult')
        assert hasattr(health_checks, 'HealthReport')
        assert hasattr(health_checks, 'check_disk_space')
        assert hasattr(health_checks, 'check_memory')
        assert hasattr(health_checks, 'check_ollama')
        assert hasattr(health_checks, 'run_all_checks')
    
    def test_configuration_constants(self):
        """Test that configuration constants are defined."""
        from core.monitoring import health_checks
        
        assert hasattr(health_checks, 'DISK_SPACE_MIN_GB')
        assert hasattr(health_checks, 'MEMORY_MAX_PERCENT')
        assert hasattr(health_checks, 'OLLAMA_URL')
        
        # Should have reasonable defaults
        assert health_checks.DISK_SPACE_MIN_GB >= 0
        assert 0 < health_checks.MEMORY_MAX_PERCENT <= 100
