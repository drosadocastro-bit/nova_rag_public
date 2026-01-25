"""
Tests for Configuration Validation Module.

Tests config schema validation, profile requirements, and startup validation.
"""

import pytest
from unittest.mock import patch
import os

from core.config.validation import (
    validate_config,
    get_config_report,
    validate_startup,
    ConfigSpec,
    ConfigType,
    ConfigCategory,
    ConfigProfile,
    ValidationReport,
    ValidationError,
    ConfigValue,
    CONFIG_SCHEMA,
    PROFILE_REQUIREMENTS,
    _validate_type,
    _get_config_value,
)


class TestConfigType:
    """Tests for ConfigType enum."""
    
    def test_config_types(self):
        """Test all config types exist."""
        assert ConfigType.STRING.value == "string"
        assert ConfigType.INTEGER.value == "integer"
        assert ConfigType.FLOAT.value == "float"
        assert ConfigType.BOOLEAN.value == "boolean"
        assert ConfigType.PATH.value == "path"
        assert ConfigType.URL.value == "url"


class TestConfigCategory:
    """Tests for ConfigCategory enum."""
    
    def test_categories(self):
        """Test all categories exist."""
        assert ConfigCategory.CORE.value == "core"
        assert ConfigCategory.LLM.value == "llm"
        assert ConfigCategory.RETRIEVAL.value == "retrieval"
        assert ConfigCategory.SAFETY.value == "safety"
        assert ConfigCategory.SECURITY.value == "security"


class TestConfigProfile:
    """Tests for ConfigProfile enum."""
    
    def test_profiles(self):
        """Test all profiles exist."""
        assert ConfigProfile.DEVELOPMENT.value == "development"
        assert ConfigProfile.PRODUCTION.value == "production"
        assert ConfigProfile.TEST.value == "test"
        assert ConfigProfile.OFFLINE.value == "offline"


class TestConfigSpec:
    """Tests for ConfigSpec dataclass."""
    
    def test_basic_spec(self):
        """Test basic spec creation."""
        spec = ConfigSpec(
            name="TEST_VAR",
            description="Test variable",
            config_type=ConfigType.STRING,
            category=ConfigCategory.CORE,
        )
        assert spec.name == "TEST_VAR"
        assert spec.required is False
        assert spec.sensitive is False
    
    def test_required_spec(self):
        """Test required spec."""
        spec = ConfigSpec(
            name="REQUIRED_VAR",
            description="Required variable",
            config_type=ConfigType.STRING,
            category=ConfigCategory.SECURITY,
            required=True,
            sensitive=True,
        )
        assert spec.required is True
        assert spec.sensitive is True


class TestValidationError:
    """Tests for ValidationError dataclass."""
    
    def test_error_creation(self):
        """Test error creation."""
        error = ValidationError(
            config_name="TEST_VAR",
            message="Invalid value",
            severity="error",
            current_value="bad",
            expected="good",
        )
        assert error.config_name == "TEST_VAR"
        assert error.severity == "error"
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        error = ValidationError(
            config_name="VAR",
            message="Error message",
        )
        result = error.to_dict()
        assert result["config_name"] == "VAR"
        assert result["message"] == "Error message"


class TestConfigValue:
    """Tests for ConfigValue dataclass."""
    
    def test_value_creation(self):
        """Test config value creation."""
        value = ConfigValue(
            name="TEST",
            value="test_value",
            source="environment",
            is_valid=True,
            category="core",
            description="Test config",
        )
        assert value.name == "TEST"
        assert value.source == "environment"
    
    def test_sensitive_value_redacted(self):
        """Test sensitive values are redacted."""
        value = ConfigValue(
            name="SECRET",
            value="super_secret",
            source="environment",
            is_valid=True,
            category="security",
            description="Secret key",
            sensitive=True,
        )
        result = value.to_dict()
        assert result["value"] == "***REDACTED***"


class TestValidationReport:
    """Tests for ValidationReport dataclass."""
    
    def test_valid_report(self):
        """Test valid report creation."""
        report = ValidationReport(
            is_valid=True,
            errors=[],
            warnings=[],
            profile="production",
        )
        assert report.is_valid is True
        assert len(report.errors) == 0
    
    def test_invalid_report(self):
        """Test invalid report with errors."""
        error = ValidationError(config_name="VAR", message="Missing")
        report = ValidationReport(
            is_valid=False,
            errors=[error],
        )
        assert report.is_valid is False
        assert len(report.errors) == 1
    
    def test_auto_timestamp(self):
        """Test automatic timestamp generation."""
        report = ValidationReport(is_valid=True)
        assert report.generated_at  # Should be set


class TestValidateType:
    """Tests for _validate_type function."""
    
    def test_valid_boolean(self):
        """Test valid boolean values."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.BOOLEAN,
            category=ConfigCategory.CORE,
        )
        assert _validate_type("1", ConfigType.BOOLEAN, spec) is None
        assert _validate_type("0", ConfigType.BOOLEAN, spec) is None
        assert _validate_type("true", ConfigType.BOOLEAN, spec) is None
        assert _validate_type("false", ConfigType.BOOLEAN, spec) is None
    
    def test_invalid_boolean(self):
        """Test invalid boolean value."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.BOOLEAN,
            category=ConfigCategory.CORE,
        )
        result = _validate_type("maybe", ConfigType.BOOLEAN, spec)
        assert result is not None
        assert "boolean" in result.lower()
    
    def test_valid_integer(self):
        """Test valid integer values."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.INTEGER,
            category=ConfigCategory.CORE,
            min_value=1,
            max_value=100,
        )
        assert _validate_type("50", ConfigType.INTEGER, spec) is None
    
    def test_integer_out_of_range(self):
        """Test integer out of range."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.INTEGER,
            category=ConfigCategory.CORE,
            min_value=1,
            max_value=100,
        )
        result = _validate_type("200", ConfigType.INTEGER, spec)
        assert result is not None
        assert "exceeds" in result.lower()
    
    def test_valid_float(self):
        """Test valid float values."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.FLOAT,
            category=ConfigCategory.CORE,
        )
        assert _validate_type("3.14", ConfigType.FLOAT, spec) is None
    
    def test_valid_url(self):
        """Test valid URL values."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.URL,
            category=ConfigCategory.CORE,
        )
        assert _validate_type("http://localhost:5000", ConfigType.URL, spec) is None
        assert _validate_type("https://example.com", ConfigType.URL, spec) is None
    
    def test_invalid_url(self):
        """Test invalid URL value."""
        spec = ConfigSpec(
            name="TEST", description="Test",
            config_type=ConfigType.URL,
            category=ConfigCategory.CORE,
        )
        result = _validate_type("ftp://example.com", ConfigType.URL, spec)
        assert result is not None


class TestGetConfigValue:
    """Tests for _get_config_value function."""
    
    def test_from_environment(self, monkeypatch):
        """Test getting value from environment."""
        monkeypatch.setenv("TEST_VAR", "env_value")
        value, source = _get_config_value("TEST_VAR", "default")
        assert value == "env_value"
        assert source == "environment"
    
    def test_from_default(self, monkeypatch):
        """Test getting default value."""
        monkeypatch.delenv("UNSET_VAR", raising=False)
        value, source = _get_config_value("UNSET_VAR", "default_value")
        assert value == "default_value"
        assert source == "default"
    
    def test_unset(self, monkeypatch):
        """Test unset value."""
        monkeypatch.delenv("UNSET_VAR", raising=False)
        value, source = _get_config_value("UNSET_VAR")
        assert value is None
        assert source == "unset"


class TestValidateConfig:
    """Tests for validate_config function."""
    
    def test_basic_validation(self, monkeypatch):
        """Test basic config validation."""
        # Set required config
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")
        
        report = validate_config()
        
        assert isinstance(report, ValidationReport)
        assert len(report.config_values) > 0
    
    def test_production_profile_validation(self, monkeypatch):
        """Test production profile validation."""
        monkeypatch.setenv("SECRET_KEY", "proper-production-key")
        
        report = validate_config(profile=ConfigProfile.PRODUCTION)
        
        assert report.profile == "production"
    
    def test_missing_required_config(self, monkeypatch):
        """Test missing required configuration."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        
        report = validate_config()
        
        # Should have error for missing SECRET_KEY
        secret_errors = [e for e in report.errors if e.config_name == "SECRET_KEY"]
        assert len(secret_errors) > 0


class TestConfigSchema:
    """Tests for CONFIG_SCHEMA completeness."""
    
    def test_schema_not_empty(self):
        """Test schema has entries."""
        assert len(CONFIG_SCHEMA) > 0
    
    def test_all_specs_have_required_fields(self):
        """Test all specs have required fields."""
        for spec in CONFIG_SCHEMA:
            assert spec.name, "Spec missing name"
            assert spec.description, f"Spec {spec.name} missing description"
            assert spec.config_type, f"Spec {spec.name} missing config_type"
            assert spec.category, f"Spec {spec.name} missing category"
    
    def test_known_env_vars_in_schema(self):
        """Test known environment variables are in schema."""
        known_vars = [
            "SECRET_KEY",
            "NOVA_HYBRID_SEARCH",
            "NOVA_GAR_ENABLED",
            "NOVA_LOG_FORMAT",
            "OLLAMA_URL",
        ]
        schema_names = {spec.name for spec in CONFIG_SCHEMA}
        for var in known_vars:
            assert var in schema_names, f"{var} not in schema"


class TestProfileRequirements:
    """Tests for PROFILE_REQUIREMENTS."""
    
    def test_production_profile_exists(self):
        """Test production profile requirements exist."""
        assert ConfigProfile.PRODUCTION in PROFILE_REQUIREMENTS
        reqs = PROFILE_REQUIREMENTS[ConfigProfile.PRODUCTION]
        assert "required" in reqs
        assert "recommended" in reqs
    
    def test_production_requires_secret_key(self):
        """Test production requires SECRET_KEY."""
        reqs = PROFILE_REQUIREMENTS[ConfigProfile.PRODUCTION]
        assert "SECRET_KEY" in reqs["required"]


class TestGetConfigReport:
    """Tests for get_config_report function."""
    
    def test_returns_grouped_config(self):
        """Test config report is grouped by category."""
        report = get_config_report()
        
        assert isinstance(report, dict)
        # Should have category keys
        assert any(cat.value in report for cat in ConfigCategory)
    
    def test_sensitive_values_redacted(self, monkeypatch):
        """Test sensitive values are redacted in report."""
        monkeypatch.setenv("SECRET_KEY", "super-secret-value")
        
        report = get_config_report()
        
        # Find SECRET_KEY in report
        for category, configs in report.items():
            for config in configs:
                if config["name"] == "SECRET_KEY":
                    assert config["value"] == "***REDACTED***"


class TestValidateStartup:
    """Tests for validate_startup function."""
    
    def test_startup_validation(self, monkeypatch):
        """Test startup validation runs."""
        monkeypatch.setenv("SECRET_KEY", "test-key")
        monkeypatch.delenv("NOVA_ENV", raising=False)
        
        # Should not raise
        result = validate_startup()
        
        assert isinstance(result, bool)
    
    def test_production_env_detection(self, monkeypatch):
        """Test production environment detection."""
        monkeypatch.setenv("SECRET_KEY", "prod-key")
        monkeypatch.setenv("NOVA_ENV", "production")
        
        # Should detect production profile
        result = validate_startup()
        assert isinstance(result, bool)
    
    def test_offline_env_detection(self, monkeypatch):
        """Test offline environment detection."""
        monkeypatch.setenv("SECRET_KEY", "offline-key")
        monkeypatch.setenv("NOVA_FORCE_OFFLINE", "1")
        monkeypatch.delenv("NOVA_ENV", raising=False)
        
        result = validate_startup()
        assert isinstance(result, bool)
