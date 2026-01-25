"""
Health Check Module for Nova NIC.

Provides comprehensive health checks for production monitoring,
Kubernetes probes, and load balancer integration.

Health Check Categories:
    - Database: SQLite analytics.db connectivity
    - FAISS Index: Vector index loaded and valid
    - BM25 Cache: Lexical search cache accessible
    - Ollama: LLM service reachability
    - Disk Space: Available storage (threshold: 1GB)
    - Memory: RAM usage (threshold: 90%)

Endpoints:
    - /health: Full health report with all checks
    - /health/ready: Kubernetes readiness probe
    - /health/live: Kubernetes liveness probe
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psutil
import requests

# ==============================================================================
# Configuration
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parents[2]
ANALYTICS_DB_PATH = BASE_DIR / "vector_db" / "analytics.db"
INDEX_DIR = BASE_DIR / "vector_db"
BM25_CACHE_PATH = INDEX_DIR / "bm25_index.pkl"

# Thresholds
DISK_SPACE_MIN_GB = float(os.environ.get("NOVA_HEALTH_DISK_MIN_GB", "1.0"))
MEMORY_MAX_PERCENT = float(os.environ.get("NOVA_HEALTH_MEMORY_MAX_PERCENT", "90.0"))
OLLAMA_TIMEOUT = float(os.environ.get("NOVA_HEALTH_OLLAMA_TIMEOUT", "5.0"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

# ==============================================================================
# Data Classes
# ==============================================================================

HealthStatus = Literal["pass", "warn", "fail"]


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    
    status: HealthStatus
    message: str = ""
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"status": self.status}
        if self.message:
            result["message"] = self.message
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        result.update(self.details)
        return result


@dataclass
class HealthReport:
    """Complete health report with all checks."""
    
    status: HealthStatus
    timestamp: str
    checks: dict[str, HealthCheckResult]
    version: str = "0.3.5"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
        }


# ==============================================================================
# Individual Health Checks
# ==============================================================================

def check_database() -> HealthCheckResult:
    """
    Check SQLite analytics database connectivity.
    
    Verifies that the database file exists and can be queried.
    """
    start = time.perf_counter()
    
    try:
        if not ANALYTICS_DB_PATH.exists():
            return HealthCheckResult(
                status="warn",
                message="Database file not found (will be created on first request)",
                details={"path": str(ANALYTICS_DB_PATH)},
            )
        
        conn = sqlite3.connect(str(ANALYTICS_DB_PATH), timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master")
        table_count = cursor.fetchone()[0]
        conn.close()
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        return HealthCheckResult(
            status="pass",
            latency_ms=latency_ms,
            details={"tables": table_count},
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Database error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def check_faiss_index() -> HealthCheckResult:
    """
    Check FAISS vector index is loaded and valid.
    
    Verifies that the index exists and reports vector count.
    """
    start = time.perf_counter()
    
    try:
        # Try to import the index from the retrieval engine
        from core.retrieval.retrieval_engine import index, docs
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        if index is None:
            return HealthCheckResult(
                status="warn",
                message="FAISS index not loaded (using fallback retrieval)",
                latency_ms=latency_ms,
            )
        
        vector_count = index.ntotal if hasattr(index, "ntotal") else 0
        chunk_count = len(docs) if docs else 0
        
        if vector_count == 0:
            return HealthCheckResult(
                status="warn",
                message="FAISS index is empty",
                latency_ms=latency_ms,
                details={"vectors": 0, "chunks": chunk_count},
            )
        
        return HealthCheckResult(
            status="pass",
            latency_ms=latency_ms,
            details={"vectors": vector_count, "chunks": chunk_count},
        )
    except ImportError as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="warn",
            message=f"FAISS module not available: {str(e)[:50]}",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"FAISS error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def check_bm25_cache() -> HealthCheckResult:
    """
    Check BM25 lexical search cache accessibility.
    
    Verifies that the BM25 index is ready or cache file exists.
    """
    start = time.perf_counter()
    
    try:
        from core.retrieval.retrieval_engine import _BM25_READY, BM25_CACHE_ENABLED
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        if _BM25_READY:
            return HealthCheckResult(
                status="pass",
                message="BM25 index loaded in memory",
                latency_ms=latency_ms,
                details={"cache_enabled": BM25_CACHE_ENABLED},
            )
        
        # Check if cache file exists
        if BM25_CACHE_PATH.exists():
            size_kb = BM25_CACHE_PATH.stat().st_size / 1024
            return HealthCheckResult(
                status="pass",
                message="BM25 cache file available",
                latency_ms=latency_ms,
                details={"cache_size_kb": round(size_kb, 2), "in_memory": False},
            )
        
        return HealthCheckResult(
            status="warn",
            message="BM25 cache not built (will build on first query)",
            latency_ms=latency_ms,
        )
    except ImportError:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="warn",
            message="BM25 module not available",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"BM25 error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def check_ollama() -> HealthCheckResult:
    """
    Check Ollama LLM service reachability.
    
    Verifies that Ollama is responding and reports loaded models.
    """
    start = time.perf_counter()
    
    try:
        # Check Ollama API
        response = requests.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=OLLAMA_TIMEOUT,
        )
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        if response.status_code != 200:
            return HealthCheckResult(
                status="fail",
                message=f"Ollama returned status {response.status_code}",
                latency_ms=latency_ms,
            )
        
        data = response.json()
        models = data.get("models", [])
        model_names = [m.get("name", "unknown") for m in models[:5]]  # Limit to 5
        
        if not models:
            return HealthCheckResult(
                status="warn",
                message="Ollama running but no models loaded",
                latency_ms=latency_ms,
            )
        
        return HealthCheckResult(
            status="pass",
            latency_ms=latency_ms,
            details={"models": model_names, "model_count": len(models)},
        )
    except requests.exceptions.Timeout:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Ollama timeout after {OLLAMA_TIMEOUT}s",
            latency_ms=latency_ms,
        )
    except requests.exceptions.ConnectionError:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Cannot connect to Ollama at {OLLAMA_URL}",
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Ollama error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def check_disk_space() -> HealthCheckResult:
    """
    Check available disk space.
    
    Warns if available space is below threshold (default: 1GB).
    """
    start = time.perf_counter()
    
    try:
        disk = psutil.disk_usage(str(BASE_DIR))
        available_gb = disk.free / (1024 ** 3)
        used_percent = disk.percent
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        if available_gb < DISK_SPACE_MIN_GB:
            return HealthCheckResult(
                status="fail",
                message=f"Low disk space: {available_gb:.1f}GB available",
                latency_ms=latency_ms,
                details={
                    "available_gb": round(available_gb, 2),
                    "used_percent": used_percent,
                    "threshold_gb": DISK_SPACE_MIN_GB,
                },
            )
        
        # Warn if less than 5GB
        if available_gb < 5.0:
            return HealthCheckResult(
                status="warn",
                message=f"Disk space getting low: {available_gb:.1f}GB",
                latency_ms=latency_ms,
                details={
                    "available_gb": round(available_gb, 2),
                    "used_percent": used_percent,
                },
            )
        
        return HealthCheckResult(
            status="pass",
            latency_ms=latency_ms,
            details={
                "available_gb": round(available_gb, 2),
                "used_percent": used_percent,
            },
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Disk check error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


def check_memory() -> HealthCheckResult:
    """
    Check system memory usage.
    
    Warns if memory usage exceeds threshold (default: 90%).
    """
    start = time.perf_counter()
    
    try:
        memory = psutil.virtual_memory()
        usage_percent = memory.percent
        available_gb = memory.available / (1024 ** 3)
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        if usage_percent >= MEMORY_MAX_PERCENT:
            return HealthCheckResult(
                status="fail",
                message=f"High memory usage: {usage_percent:.1f}%",
                latency_ms=latency_ms,
                details={
                    "usage_percent": round(usage_percent, 1),
                    "available_gb": round(available_gb, 2),
                    "threshold_percent": MEMORY_MAX_PERCENT,
                },
            )
        
        # Warn if above 80%
        if usage_percent >= 80:
            return HealthCheckResult(
                status="warn",
                message=f"Memory usage elevated: {usage_percent:.1f}%",
                latency_ms=latency_ms,
                details={
                    "usage_percent": round(usage_percent, 1),
                    "available_gb": round(available_gb, 2),
                },
            )
        
        return HealthCheckResult(
            status="pass",
            latency_ms=latency_ms,
            details={
                "usage_percent": round(usage_percent, 1),
                "available_gb": round(available_gb, 2),
            },
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return HealthCheckResult(
            status="fail",
            message=f"Memory check error: {str(e)[:100]}",
            latency_ms=latency_ms,
        )


# ==============================================================================
# Aggregate Health Checks
# ==============================================================================

def run_all_checks() -> HealthReport:
    """
    Run all health checks and return a complete report.
    
    Overall status is determined by:
        - "fail" if any check fails
        - "warn" if any check warns (and none fail)
        - "pass" if all checks pass
    """
    checks = {
        "database": check_database(),
        "faiss_index": check_faiss_index(),
        "bm25_cache": check_bm25_cache(),
        "ollama": check_ollama(),
        "disk_space": check_disk_space(),
        "memory": check_memory(),
    }
    
    # Determine overall status
    statuses = [check.status for check in checks.values()]
    if "fail" in statuses:
        overall_status: HealthStatus = "fail"
    elif "warn" in statuses:
        overall_status = "warn"
    else:
        overall_status = "pass"
    
    return HealthReport(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )


def run_readiness_checks() -> tuple[bool, dict[str, Any]]:
    """
    Run checks for Kubernetes readiness probe.
    
    Readiness indicates the service can accept traffic.
    Checks: database, FAISS index, Ollama (warn ok, fail = not ready)
    
    Returns:
        Tuple of (is_ready: bool, details: dict)
    """
    checks = {
        "database": check_database(),
        "faiss_index": check_faiss_index(),
        "ollama": check_ollama(),
    }
    
    # Ready if no checks failed (warnings are acceptable)
    is_ready = all(check.status != "fail" for check in checks.values())
    
    return is_ready, {
        "ready": is_ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {name: check.to_dict() for name, check in checks.items()},
    }


def run_liveness_checks() -> tuple[bool, dict[str, Any]]:
    """
    Run checks for Kubernetes liveness probe.
    
    Liveness indicates the service is running and not deadlocked.
    Only checks basic process health, not external dependencies.
    
    Returns:
        Tuple of (is_alive: bool, details: dict)
    """
    start = time.perf_counter()
    
    try:
        # Basic check: can we allocate memory and run code?
        _ = [i for i in range(1000)]
        
        # Check process memory
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 ** 2)
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        return True, {
            "alive": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round(latency_ms, 2),
            "process_memory_mb": round(memory_mb, 1),
        }
    except Exception as e:
        return False, {
            "alive": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)[:100],
        }
