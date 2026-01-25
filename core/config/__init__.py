"""
Core Configuration Module.

Provides configuration validation, schema definition, and startup checks.
"""

from .validation import (
    # Main functions
    validate_config,
    validate_startup,
    get_config_report,
    print_config_summary,
    export_config_template,
    # Data classes
    ValidationReport,
    ValidationError,
    ConfigValue,
    ConfigSpec,
    # Enums
    ConfigType,
    ConfigCategory,
    ConfigProfile,
    # Schema
    CONFIG_SCHEMA,
    PROFILE_REQUIREMENTS,
)

__all__ = [
    "validate_config",
    "validate_startup",
    "get_config_report",
    "print_config_summary",
    "export_config_template",
    "ValidationReport",
    "ValidationError",
    "ConfigValue",
    "ConfigSpec",
    "ConfigType",
    "ConfigCategory",
    "ConfigProfile",
    "CONFIG_SCHEMA",
    "PROFILE_REQUIREMENTS",
]
