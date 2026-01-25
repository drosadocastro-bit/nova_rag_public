"""
Configuration Validation Module for Nova NIC.

Provides comprehensive configuration validation including:
    - Environment variable validation with type checking
    - Required vs optional config detection
    - Configuration schema definition
    - Startup validation with clear error messages
    - Configuration profiles (development, production, test)

Usage:
    from core.config.validation import (
        validate_config,
        get_config_report,
        ConfigProfile,
    )
    
    # Validate all configuration
    report = validate_config()
    if not report.is_valid:
        print(report.errors)
    
    # Get current configuration
    config = get_config_report()
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Union
import json

from core.monitoring.logger_config import get_logger

logger = get_logger("core.config.validation")


# =============================================================================
# Configuration Schema Definition
# =============================================================================

class ConfigType(str, Enum):
    """Configuration value types."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    PATH = "path"
    URL = "url"


class ConfigCategory(str, Enum):
    """Configuration categories."""
    CORE = "core"
    LLM = "llm"
    RETRIEVAL = "retrieval"
    SAFETY = "safety"
    CACHE = "cache"
    LOGGING = "logging"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCKER = "docker"


@dataclass
class ConfigSpec:
    """Specification for a configuration variable."""
    name: str
    description: str
    config_type: ConfigType
    category: ConfigCategory
    default: Optional[str] = None
    required: bool = False
    valid_values: Optional[list[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None  # Regex pattern for validation
    sensitive: bool = False  # Whether value should be masked in logs


# Complete configuration schema for Nova NIC
CONFIG_SCHEMA: list[ConfigSpec] = [
    # Core Configuration
    ConfigSpec(
        name="NOVA_FORCE_OFFLINE",
        description="Force offline mode (no network calls)",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.CORE,
        default="0",
    ),
    ConfigSpec(
        name="SECRET_KEY",
        description="Flask secret key for session security",
        config_type=ConfigType.STRING,
        category=ConfigCategory.SECURITY,
        required=True,
        sensitive=True,
    ),
    
    # LLM Configuration
    ConfigSpec(
        name="OLLAMA_BASE_URL",
        description="Ollama API base URL",
        config_type=ConfigType.URL,
        category=ConfigCategory.LLM,
        default="http://127.0.0.1:11434/v1",
    ),
    ConfigSpec(
        name="OLLAMA_URL",
        description="Ollama API URL (alternative)",
        config_type=ConfigType.URL,
        category=ConfigCategory.LLM,
        default="http://127.0.0.1:11434",
    ),
    ConfigSpec(
        name="NOVA_LLM_LLAMA",
        description="Llama model name for Ollama",
        config_type=ConfigType.STRING,
        category=ConfigCategory.LLM,
        default="llama3.2:3b",
    ),
    ConfigSpec(
        name="NOVA_LLM_OSS",
        description="OSS model name for Ollama",
        config_type=ConfigType.STRING,
        category=ConfigCategory.LLM,
        default="qwen2.5-coder:7b",
    ),
    ConfigSpec(
        name="NOVA_USE_NATIVE_LLM",
        description="Use native LLM instead of Ollama",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.LLM,
        default="0",
    ),
    
    # Retrieval Configuration
    ConfigSpec(
        name="NOVA_HYBRID_SEARCH",
        description="Enable hybrid search (vector + BM25)",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.RETRIEVAL,
        default="1",
    ),
    ConfigSpec(
        name="NOVA_BM25_K1",
        description="BM25 k1 parameter",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.RETRIEVAL,
        default="1.5",
        min_value=0.0,
        max_value=3.0,
    ),
    ConfigSpec(
        name="NOVA_BM25_B",
        description="BM25 b parameter",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.RETRIEVAL,
        default="0.75",
        min_value=0.0,
        max_value=1.0,
    ),
    ConfigSpec(
        name="NOVA_BM25_CACHE",
        description="Enable BM25 caching",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.CACHE,
        default="1",
    ),
    ConfigSpec(
        name="NOVA_EMBEDDING_MODEL",
        description="Path to embedding model",
        config_type=ConfigType.PATH,
        category=ConfigCategory.RETRIEVAL,
        default="models/nic-embeddings-v1.0",
    ),
    ConfigSpec(
        name="NOVA_EMBED_BATCH_SIZE",
        description="Embedding batch size",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.PERFORMANCE,
        default="32",
        min_value=1,
        max_value=256,
    ),
    ConfigSpec(
        name="NOVA_DOMAIN_BOOST",
        description="Enable domain-specific boosting",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.RETRIEVAL,
        default="1",
    ),
    ConfigSpec(
        name="NOVA_DOMAIN_BOOST_FACTOR",
        description="Domain boost factor",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.RETRIEVAL,
        default="0.25",
        min_value=0.0,
        max_value=1.0,
    ),
    
    # Safety Configuration
    ConfigSpec(
        name="NOVA_GAR_ENABLED",
        description="Enable Grounded Answer Refinement",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SAFETY,
        default="1",
    ),
    ConfigSpec(
        name="NOVA_CITATION_AUDIT",
        description="Enable citation auditing",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SAFETY,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_CITATION_STRICT",
        description="Enable strict citation mode",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SAFETY,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_ANOMALY_DETECTOR",
        description="Enable anomaly detection",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SAFETY,
        default="0",
    ),
    
    # Cache Configuration
    ConfigSpec(
        name="NOVA_ENABLE_RETRIEVAL_CACHE",
        description="Enable retrieval result caching",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.CACHE,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_RETRIEVAL_CACHE_SIZE",
        description="Retrieval cache size",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.CACHE,
        default="128",
        min_value=1,
        max_value=10000,
    ),
    ConfigSpec(
        name="NOVA_CACHE_SECRET",
        description="Secret key for cache encryption",
        config_type=ConfigType.STRING,
        category=ConfigCategory.SECURITY,
        sensitive=True,
    ),
    
    # Logging Configuration
    ConfigSpec(
        name="NOVA_LOG_FORMAT",
        description="Log format (json or text)",
        config_type=ConfigType.STRING,
        category=ConfigCategory.LOGGING,
        default="json",
        valid_values=["json", "text"],
    ),
    ConfigSpec(
        name="NOVA_LOG_LEVEL",
        description="Log level",
        config_type=ConfigType.STRING,
        category=ConfigCategory.LOGGING,
        default="INFO",
        valid_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    ),
    ConfigSpec(
        name="NOVA_LOG_FILE",
        description="Log file path",
        config_type=ConfigType.PATH,
        category=ConfigCategory.LOGGING,
        default="logs/nova.log",
    ),
    ConfigSpec(
        name="NOVA_LOG_MAX_SIZE",
        description="Maximum log file size in MB",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.LOGGING,
        default="100",
        min_value=1,
        max_value=10000,
    ),
    ConfigSpec(
        name="NOVA_LOG_BACKUP_COUNT",
        description="Number of log backup files",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.LOGGING,
        default="10",
        min_value=0,
        max_value=100,
    ),
    ConfigSpec(
        name="NOVA_ENABLE_SQL_LOG",
        description="Enable SQL query logging",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.LOGGING,
        default="0",
    ),
    
    # Rate Limiting
    ConfigSpec(
        name="NOVA_RATE_LIMIT_ENABLED",
        description="Enable rate limiting",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SECURITY,
        default="1",
    ),
    ConfigSpec(
        name="NOVA_RATE_LIMIT_PER_HOUR",
        description="Rate limit per hour",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.SECURITY,
        default="100",
        min_value=1,
    ),
    ConfigSpec(
        name="NOVA_RATE_LIMIT_PER_MINUTE",
        description="Rate limit per minute",
        config_type=ConfigType.INTEGER,
        category=ConfigCategory.SECURITY,
        default="20",
        min_value=1,
    ),
    
    # API Security
    ConfigSpec(
        name="NOVA_API_TOKEN",
        description="API authentication token",
        config_type=ConfigType.STRING,
        category=ConfigCategory.SECURITY,
        sensitive=True,
    ),
    ConfigSpec(
        name="NOVA_REQUIRE_TOKEN",
        description="Require API token for requests",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.SECURITY,
        default="0",
    ),
    
    # Health Check Configuration
    ConfigSpec(
        name="NOVA_HEALTH_DISK_MIN_GB",
        description="Minimum disk space in GB for health check",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.PERFORMANCE,
        default="1.0",
        min_value=0.1,
    ),
    ConfigSpec(
        name="NOVA_HEALTH_MEMORY_MAX_PERCENT",
        description="Maximum memory usage percent for health check",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.PERFORMANCE,
        default="90.0",
        min_value=50.0,
        max_value=100.0,
    ),
    ConfigSpec(
        name="NOVA_HEALTH_OLLAMA_TIMEOUT",
        description="Ollama health check timeout in seconds",
        config_type=ConfigType.FLOAT,
        category=ConfigCategory.LLM,
        default="5.0",
        min_value=1.0,
        max_value=60.0,
    ),
    
    # Performance Tuning
    ConfigSpec(
        name="NOVA_WARMUP_ON_START",
        description="Warm up models on startup",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.PERFORMANCE,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_DISABLE_VISION",
        description="Disable vision processing",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.PERFORMANCE,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_DISABLE_EMBED",
        description="Disable embeddings (use lexical only)",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.PERFORMANCE,
        default="0",
    ),
    ConfigSpec(
        name="NOVA_DISABLE_CROSS_ENCODER",
        description="Disable cross-encoder reranking",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.PERFORMANCE,
        default="0",
    ),
    
    # Docker/Container
    ConfigSpec(
        name="HF_HOME",
        description="HuggingFace cache directory",
        config_type=ConfigType.PATH,
        category=ConfigCategory.DOCKER,
    ),
    ConfigSpec(
        name="TRANSFORMERS_CACHE",
        description="Transformers cache directory",
        config_type=ConfigType.PATH,
        category=ConfigCategory.DOCKER,
    ),
    ConfigSpec(
        name="HF_HUB_OFFLINE",
        description="HuggingFace Hub offline mode",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.DOCKER,
        default="0",
    ),
    ConfigSpec(
        name="TRANSFORMERS_OFFLINE",
        description="Transformers offline mode",
        config_type=ConfigType.BOOLEAN,
        category=ConfigCategory.DOCKER,
        default="0",
    ),
]


# =============================================================================
# Validation Data Classes
# =============================================================================

@dataclass
class ValidationError:
    """Represents a configuration validation error."""
    config_name: str
    message: str
    severity: str = "error"  # error, warning
    current_value: Optional[str] = None
    expected: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfigValue:
    """Represents a configuration value with metadata."""
    name: str
    value: Optional[str]
    source: str  # "environment", "default", "unset"
    is_valid: bool
    category: str
    description: str
    sensitive: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.sensitive and self.value:
            result["value"] = "***REDACTED***"
        return result


@dataclass
class ValidationReport:
    """Complete validation report."""
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    config_values: list[ConfigValue] = field(default_factory=list)
    profile: str = "unknown"
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            from datetime import datetime
            self.generated_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "config_values": [c.to_dict() for c in self.config_values],
            "profile": self.profile,
            "generated_at": self.generated_at,
        }


# =============================================================================
# Configuration Profiles
# =============================================================================

class ConfigProfile(str, Enum):
    """Predefined configuration profiles."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"
    OFFLINE = "offline"


PROFILE_REQUIREMENTS: dict[ConfigProfile, dict[str, Any]] = {
    ConfigProfile.PRODUCTION: {
        "required": [
            "SECRET_KEY",
        ],
        "recommended": {
            "NOVA_RATE_LIMIT_ENABLED": "1",
            "NOVA_LOG_FORMAT": "json",
            "NOVA_GAR_ENABLED": "1",
            "NOVA_CITATION_AUDIT": "1",
        },
        "forbidden_values": {
            "SECRET_KEY": ["change-this-in-production-use-openssl-rand-hex-32"],
        },
    },
    ConfigProfile.DEVELOPMENT: {
        "required": [],
        "recommended": {
            "NOVA_LOG_FORMAT": "text",
            "NOVA_LOG_LEVEL": "DEBUG",
        },
    },
    ConfigProfile.TEST: {
        "required": [],
        "recommended": {
            "NOVA_FORCE_OFFLINE": "1",
            "NOVA_RATE_LIMIT_ENABLED": "0",
            "NOVA_DISABLE_VISION": "1",
        },
    },
    ConfigProfile.OFFLINE: {
        "required": [],
        "recommended": {
            "NOVA_FORCE_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
    },
}


# =============================================================================
# Validation Functions
# =============================================================================

def _get_config_value(name: str, default: Optional[str] = None) -> tuple[Optional[str], str]:
    """Get configuration value and its source."""
    value = os.environ.get(name)
    if value is not None:
        return value, "environment"
    if default is not None:
        return default, "default"
    return None, "unset"


def _validate_type(value: str, config_type: ConfigType, spec: ConfigSpec) -> Optional[str]:
    """Validate value against expected type."""
    if config_type == ConfigType.BOOLEAN:
        if value.lower() not in ("0", "1", "true", "false", "yes", "no"):
            return f"Expected boolean (0/1/true/false), got '{value}'"
    
    elif config_type == ConfigType.INTEGER:
        try:
            int_val = int(value)
            if spec.min_value is not None and int_val < spec.min_value:
                return f"Value {int_val} is below minimum {spec.min_value}"
            if spec.max_value is not None and int_val > spec.max_value:
                return f"Value {int_val} exceeds maximum {spec.max_value}"
        except ValueError:
            return f"Expected integer, got '{value}'"
    
    elif config_type == ConfigType.FLOAT:
        try:
            float_val = float(value)
            if spec.min_value is not None and float_val < spec.min_value:
                return f"Value {float_val} is below minimum {spec.min_value}"
            if spec.max_value is not None and float_val > spec.max_value:
                return f"Value {float_val} exceeds maximum {spec.max_value}"
        except ValueError:
            return f"Expected float, got '{value}'"
    
    elif config_type == ConfigType.URL:
        if not value.startswith(("http://", "https://")):
            return f"Expected URL starting with http:// or https://, got '{value}'"
    
    elif config_type == ConfigType.PATH:
        # Path validation is lenient - just check it's not empty
        if not value.strip():
            return "Path cannot be empty"
    
    return None


def _validate_spec(spec: ConfigSpec) -> tuple[ConfigValue, list[ValidationError]]:
    """Validate a single configuration specification."""
    errors = []
    value, source = _get_config_value(spec.name, spec.default)
    
    # Check required
    if spec.required and value is None:
        errors.append(ValidationError(
            config_name=spec.name,
            message=f"Required configuration '{spec.name}' is not set",
            severity="error",
        ))
    
    # Validate type and constraints
    if value is not None:
        type_error = _validate_type(value, spec.config_type, spec)
        if type_error:
            errors.append(ValidationError(
                config_name=spec.name,
                message=type_error,
                severity="error",
                current_value=value if not spec.sensitive else "***",
            ))
        
        # Check valid values
        if spec.valid_values and value.upper() not in [v.upper() for v in spec.valid_values]:
            errors.append(ValidationError(
                config_name=spec.name,
                message=f"Value '{value}' not in allowed values: {spec.valid_values}",
                severity="error",
                current_value=value,
                expected=str(spec.valid_values),
            ))
        
        # Check pattern
        if spec.pattern and not re.match(spec.pattern, value):
            errors.append(ValidationError(
                config_name=spec.name,
                message=f"Value does not match required pattern: {spec.pattern}",
                severity="error",
                current_value=value if not spec.sensitive else "***",
            ))
    
    config_value = ConfigValue(
        name=spec.name,
        value=value,
        source=source,
        is_valid=len(errors) == 0,
        category=spec.category.value,
        description=spec.description,
        sensitive=spec.sensitive,
    )
    
    return config_value, errors


def validate_config(profile: Optional[ConfigProfile] = None) -> ValidationReport:
    """
    Validate all configuration against schema.
    
    Args:
        profile: Optional configuration profile for additional validation
        
    Returns:
        ValidationReport with all errors and warnings
    """
    all_errors: list[ValidationError] = []
    all_warnings: list[ValidationError] = []
    config_values: list[ConfigValue] = []
    
    # Validate each spec
    for spec in CONFIG_SCHEMA:
        config_value, errors = _validate_spec(spec)
        config_values.append(config_value)
        all_errors.extend(errors)
    
    # Profile-specific validation
    if profile:
        profile_reqs = PROFILE_REQUIREMENTS.get(profile, {})
        
        # Check profile required configs
        for req in profile_reqs.get("required", []):
            value = os.environ.get(req)
            if not value:
                all_errors.append(ValidationError(
                    config_name=req,
                    message=f"Required for {profile.value} profile but not set",
                    severity="error",
                ))
        
        # Check recommended settings
        for name, expected in profile_reqs.get("recommended", {}).items():
            value = os.environ.get(name)
            if value != expected:
                all_warnings.append(ValidationError(
                    config_name=name,
                    message=f"Recommended value for {profile.value} profile is '{expected}'",
                    severity="warning",
                    current_value=value,
                    expected=expected,
                ))
        
        # Check forbidden values
        for name, forbidden in profile_reqs.get("forbidden_values", {}).items():
            value = os.environ.get(name)
            if value in forbidden:
                all_errors.append(ValidationError(
                    config_name=name,
                    message=f"Value is not allowed in {profile.value} profile",
                    severity="error",
                ))
    
    return ValidationReport(
        is_valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
        config_values=config_values,
        profile=profile.value if profile else "none",
    )


def get_config_report() -> dict[str, Any]:
    """
    Get current configuration as a report.
    
    Returns:
        Dictionary with all configuration values grouped by category
    """
    report: dict[str, list[dict[str, Any]]] = {}
    
    for spec in CONFIG_SCHEMA:
        value, source = _get_config_value(spec.name, spec.default)
        
        category = spec.category.value
        if category not in report:
            report[category] = []
        
        report[category].append({
            "name": spec.name,
            "value": "***REDACTED***" if spec.sensitive and value else value,
            "source": source,
            "description": spec.description,
            "type": spec.config_type.value,
        })
    
    return report


def validate_startup() -> bool:
    """
    Perform startup validation and log results.
    
    Returns:
        True if validation passed, False otherwise
    """
    # Detect profile from environment
    profile = None
    if os.environ.get("NOVA_ENV") == "production":
        profile = ConfigProfile.PRODUCTION
    elif os.environ.get("NOVA_ENV") == "test":
        profile = ConfigProfile.TEST
    elif os.environ.get("NOVA_FORCE_OFFLINE") == "1":
        profile = ConfigProfile.OFFLINE
    
    report = validate_config(profile)
    
    if report.errors:
        logger.error(
            "configuration_validation_failed",
            extra={
                "error_count": len(report.errors),
                "errors": [e.to_dict() for e in report.errors[:5]],
            },
        )
        for error in report.errors:
            logger.error(f"Config error: {error.config_name} - {error.message}")
    
    if report.warnings:
        for warning in report.warnings:
            logger.warning(f"Config warning: {warning.config_name} - {warning.message}")
    
    if report.is_valid:
        logger.info(
            "configuration_validation_passed",
            extra={"profile": report.profile},
        )
    
    return report.is_valid


def print_config_summary():
    """Print a human-readable configuration summary."""
    print("\n" + "=" * 60)
    print("Nova NIC Configuration Summary")
    print("=" * 60)
    
    report = get_config_report()
    
    for category, configs in sorted(report.items()):
        print(f"\n[{category.upper()}]")
        for config in configs:
            value_display = config["value"] if config["value"] else "(not set)"
            source_badge = f"[{config['source']}]"
            print(f"  {config['name']}: {value_display} {source_badge}")
    
    print("\n" + "=" * 60)


def export_config_template(filepath: Path, profile: ConfigProfile = ConfigProfile.PRODUCTION):
    """
    Export a configuration template file.
    
    Args:
        filepath: Path to write the template
        profile: Configuration profile to use as basis
    """
    lines = [
        "# Nova NIC Configuration Template",
        f"# Profile: {profile.value}",
        "# Generated by config validation module",
        "",
    ]
    
    current_category = None
    for spec in CONFIG_SCHEMA:
        if spec.category != current_category:
            current_category = spec.category
            lines.extend(["", f"# === {current_category.value.upper()} ===", ""])
        
        lines.append(f"# {spec.description}")
        if spec.valid_values:
            lines.append(f"# Valid values: {spec.valid_values}")
        if spec.min_value is not None or spec.max_value is not None:
            range_str = f"Range: {spec.min_value or ''} - {spec.max_value or ''}"
            lines.append(f"# {range_str}")
        
        default = spec.default or ""
        if spec.sensitive:
            default = "# CHANGE_ME"
        
        prefix = "" if spec.required else "# "
        lines.append(f"{prefix}{spec.name}={default}")
        lines.append("")
    
    filepath.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Exported configuration template to {filepath}")
