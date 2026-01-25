"""
Structured Logging Configuration for Nova NIC.

Provides JSON and text logging formats with query tracing, log rotation,
and structured fields for production observability.

Usage:
    from core.monitoring.logger_config import get_logger, QueryContext
    
    logger = get_logger(__name__)
    
    # Basic logging
    logger.info("Processing query", extra={"domain": "vehicle"})
    
    # With query context (auto-propagates query_id)
    with QueryContext(query="How do I check tire pressure?"):
        logger.info("Starting retrieval")
        # ... processing ...
        logger.info("Retrieval complete", extra={"latency_ms": 150})

Environment Variables:
    NOVA_LOG_FORMAT: "json" (default) or "text"
    NOVA_LOG_LEVEL: "DEBUG", "INFO" (default), "WARNING", "ERROR"
    NOVA_LOG_FILE: Path to log file (default: logs/nova.log)
    NOVA_LOG_MAX_SIZE: Max log file size in MB (default: 100)
    NOVA_LOG_BACKUP_COUNT: Number of backup files (default: 10)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ==============================================================================
# Configuration
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Environment configuration
LOG_FORMAT = os.environ.get("NOVA_LOG_FORMAT", "json").lower()
LOG_LEVEL = os.environ.get("NOVA_LOG_LEVEL", "INFO").upper()
LOG_FILE = Path(os.environ.get("NOVA_LOG_FILE", str(LOG_DIR / "nova.log")))
LOG_MAX_SIZE_MB = int(os.environ.get("NOVA_LOG_MAX_SIZE", "100"))
LOG_BACKUP_COUNT = int(os.environ.get("NOVA_LOG_BACKUP_COUNT", "10"))

# Ensure log file directory exists
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# Query Context (Thread-Safe)
# ==============================================================================

# Context variable for query tracking across async boundaries
_query_context: ContextVar[dict[str, Any]] = ContextVar("query_context", default={})


class QueryContext:
    """
    Context manager for tracking query metadata across the request lifecycle.
    
    Automatically generates a unique query_id and propagates it through all
    log messages within the context.
    
    Example:
        with QueryContext(query="How do I check tire pressure?", domain="vehicle"):
            logger.info("Processing query")  # Includes query_id automatically
            # ... processing ...
            logger.info("Complete", extra={"latency_ms": 150})
    
    Thread-safe: Uses contextvars for proper async/thread isolation.
    """
    
    def __init__(
        self,
        query: str | None = None,
        query_id: str | None = None,
        domain: str | None = None,
        **kwargs: Any,
    ):
        self.query_id = query_id or str(uuid.uuid4())
        self.context_data = {
            "query_id": self.query_id,
            "query": query,
            "domain": domain,
            **kwargs,
        }
        self._token = None
    
    def __enter__(self) -> "QueryContext":
        self._token = _query_context.set(self.context_data)
        return self
    
    def __exit__(self, *args: Any) -> None:
        if self._token is not None:
            _query_context.reset(self._token)
    
    def update(self, **kwargs: Any) -> None:
        """Update context with additional fields."""
        current = _query_context.get()
        current.update(kwargs)
        _query_context.set(current)
    
    @staticmethod
    def get_current() -> dict[str, Any]:
        """Get the current query context."""
        return _query_context.get().copy()
    
    @staticmethod
    def get_query_id() -> str | None:
        """Get the current query ID, if any."""
        return _query_context.get().get("query_id")


def set_query_context(**kwargs: Any) -> None:
    """Set query context fields without using context manager."""
    current = _query_context.get()
    current.update(kwargs)
    _query_context.set(current)


def clear_query_context() -> None:
    """Clear the current query context."""
    _query_context.set({})


# ==============================================================================
# JSON Formatter
# ==============================================================================

class JSONFormatter(logging.Formatter):
    """
    Format log records as JSON for structured logging.
    
    Output format:
    {
        "timestamp": "2026-01-25T10:30:15.123456Z",
        "level": "INFO",
        "query_id": "a3f8b2c1-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
        "module": "retrieval_engine",
        "message": "Retrieval complete",
        "domain": "vehicle_civilian",
        "confidence_score": 0.82,
        "latency_ms": 345,
        "safety_checks": ["injection_detection", "risk_assessment"]
    }
    """
    
    # Fields to always include at the top level
    STANDARD_FIELDS = {
        "timestamp", "level", "query_id", "module", "message",
        "domain", "query", "confidence_score", "latency_ms", "safety_checks",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        # Build the log entry
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        
        # Add query context if available
        context = _query_context.get()
        if context:
            for key in ["query_id", "query", "domain"]:
                if key in context and context[key] is not None:
                    log_entry[key] = context[key]
        
        # Add extra fields from the log record
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in {
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "pathname", "process", "processName", "relativeCreated",
                    "stack_info", "exc_info", "exc_text", "thread", "threadName",
                    "message", "taskName",
                }:
                    # Only include if not None and not private
                    if value is not None and not key.startswith("_"):
                        log_entry[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Ensure consistent field ordering
        ordered_entry: dict[str, Any] = {}
        for field in ["timestamp", "level", "query_id", "module", "message"]:
            if field in log_entry:
                ordered_entry[field] = log_entry.pop(field)
        ordered_entry.update(log_entry)
        
        return json.dumps(ordered_entry, ensure_ascii=False, default=str)


# ==============================================================================
# Text Formatter
# ==============================================================================

class TextFormatter(logging.Formatter):
    """
    Human-readable text format for development.
    
    Output format:
    2026-01-25 10:30:15 INFO  [retrieval_engine] Retrieval complete | query_id=a3f8b2c1 domain=vehicle latency_ms=345
    """
    
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        
        if self.use_colors:
            color = self.LEVEL_COLORS.get(level, "")
            level_str = f"{color}{level:5}{self.RESET}"
        else:
            level_str = f"{level:5}"
        
        # Base message
        msg = f"{timestamp} {level_str} [{record.name}] {record.getMessage()}"
        
        # Add context fields
        context_parts = []
        
        # Query context
        context = _query_context.get()
        if context.get("query_id"):
            context_parts.append(f"query_id={context['query_id'][:8]}")
        if context.get("domain"):
            context_parts.append(f"domain={context['domain']}")
        
        # Extra fields from record
        extra_fields = ["domain", "confidence_score", "latency_ms", "safety_checks"]
        for field in extra_fields:
            if hasattr(record, field) and getattr(record, field) is not None:
                value = getattr(record, field)
                if isinstance(value, list):
                    value = ",".join(str(v) for v in value)
                context_parts.append(f"{field}={value}")
        
        if context_parts:
            msg += " | " + " ".join(context_parts)
        
        # Add exception if present
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        
        return msg


# ==============================================================================
# Logger Factory
# ==============================================================================

# Cache of configured loggers
_loggers: dict[str, logging.Logger] = {}
_logger_lock = threading.Lock()

# Root logger configuration (done once)
_root_configured = False


def _configure_root_logger() -> None:
    """Configure the root Nova logger with handlers."""
    global _root_configured
    
    if _root_configured:
        return
    
    root_logger = logging.getLogger("nova")
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Choose formatter based on configuration
    if LOG_FORMAT == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter(use_colors=True)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            filename=str(LOG_FILE),
            maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        # Always use JSON for file logs (easier to parse)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Don't fail if we can't write to log file
        root_logger.warning(f"Could not configure file logging: {e}")
    
    # Don't propagate to root logger
    root_logger.propagate = False
    
    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the specified module.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Configured logger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"latency_ms": 150})
    """
    # Normalize name to be under nova hierarchy
    if not name.startswith("nova"):
        name = f"nova.{name}"
    
    with _logger_lock:
        if name not in _loggers:
            _configure_root_logger()
            logger = logging.getLogger(name)
            _loggers[name] = logger
        return _loggers[name]


# ==============================================================================
# Convenience Functions
# ==============================================================================

def log_query(
    logger: logging.Logger,
    message: str,
    *,
    query: str | None = None,
    domain: str | None = None,
    confidence_score: float | None = None,
    latency_ms: float | None = None,
    safety_checks: list[str] | None = None,
    level: int = logging.INFO,
    **kwargs: Any,
) -> None:
    """
    Log a query-related event with structured fields.
    
    Args:
        logger: Logger instance
        message: Log message
        query: The user's query text
        domain: Detected domain
        confidence_score: Retrieval confidence (0-1)
        latency_ms: Processing time in milliseconds
        safety_checks: List of safety checks performed
        level: Log level (default: INFO)
        **kwargs: Additional fields to include
    """
    extra: dict[str, Any] = {}
    
    if query is not None:
        extra["query"] = query
    if domain is not None:
        extra["domain"] = domain
    if confidence_score is not None:
        extra["confidence_score"] = round(confidence_score, 4)
    if latency_ms is not None:
        extra["latency_ms"] = round(latency_ms, 2)
    if safety_checks is not None:
        extra["safety_checks"] = safety_checks
    
    extra.update(kwargs)
    
    logger.log(level, message, extra=extra)


def log_safety_event(
    logger: logging.Logger,
    event_type: str,
    *,
    check_name: str,
    passed: bool,
    details: dict[str, Any] | None = None,
    level: int | None = None,
) -> None:
    """
    Log a safety check event.
    
    Args:
        logger: Logger instance
        event_type: Type of event (e.g., "injection_check", "risk_assessment")
        check_name: Name of the specific check
        passed: Whether the check passed
        details: Additional details about the check
        level: Log level (default: INFO if passed, WARNING if not)
    """
    if level is None:
        level = logging.INFO if passed else logging.WARNING
    
    extra: dict[str, Any] = {
        "event_type": event_type,
        "check_name": check_name,
        "passed": passed,
    }
    
    if details:
        extra["details"] = details
    
    status = "passed" if passed else "failed"
    logger.log(level, f"Safety check {check_name} {status}", extra=extra)


def log_retrieval_event(
    logger: logging.Logger,
    stage: str,
    *,
    chunks_retrieved: int | None = None,
    confidence: float | None = None,
    latency_ms: float | None = None,
    method: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Log a retrieval pipeline event.
    
    Args:
        logger: Logger instance
        stage: Pipeline stage (e.g., "faiss_search", "bm25_search", "rerank")
        chunks_retrieved: Number of chunks retrieved
        confidence: Average confidence score
        latency_ms: Stage latency
        method: Retrieval method used
        **kwargs: Additional fields
    """
    extra: dict[str, Any] = {"stage": stage}
    
    if chunks_retrieved is not None:
        extra["chunks_retrieved"] = chunks_retrieved
    if confidence is not None:
        extra["confidence"] = round(confidence, 4)
    if latency_ms is not None:
        extra["latency_ms"] = round(latency_ms, 2)
    if method is not None:
        extra["method"] = method
    
    extra.update(kwargs)
    
    logger.info(f"Retrieval stage: {stage}", extra=extra)


# ==============================================================================
# Module-level logger for this module
# ==============================================================================

_module_logger = get_logger("core.monitoring.logger_config")


def log_startup_config() -> None:
    """Log the current logging configuration at startup."""
    _module_logger.info(
        "Logging configured",
        extra={
            "log_format": LOG_FORMAT,
            "log_level": LOG_LEVEL,
            "log_file": str(LOG_FILE),
            "max_size_mb": LOG_MAX_SIZE_MB,
            "backup_count": LOG_BACKUP_COUNT,
        },
    )
