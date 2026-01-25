#!/usr/bin/env python3
"""
Docker Health Check Script for Nova NIC.

Performs comprehensive health checks for container orchestration.
Returns exit code 0 for healthy, 1 for unhealthy.

Usage:
    python scripts/docker_healthcheck.py
    
Exit Codes:
    0 - Healthy (all checks pass)
    1 - Unhealthy (one or more critical checks failed)
"""

import sys
import os
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    # Fallback if requests not available
    import urllib.request
    import urllib.error
    
    def simple_get(url: str, timeout: float = 5.0) -> dict:
        """Simple GET request without requests library."""
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return {"ok": True, "status": response.status, "data": response.read().decode()}
        except urllib.error.URLError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    requests = None


def check_flask_status(port: int = 5000, timeout: float = 5.0) -> tuple[bool, str]:
    """Check if Flask app is responding."""
    url = f"http://localhost:{port}/api/status"
    
    try:
        if requests:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                return True, f"Flask OK: {data.get('status', 'running')}"
            return False, f"Flask returned status {response.status_code}"
        else:
            result = simple_get(url, timeout)
            if result["ok"]:
                return True, "Flask OK"
            return False, f"Flask error: {result.get('error', 'unknown')}"
    except Exception as e:
        return False, f"Flask unreachable: {e}"


def check_index_loaded() -> tuple[bool, str]:
    """Check if vector index is loaded."""
    index_path = Path("/app/vector_db/faiss_index.index")
    if not index_path.exists():
        # Try alternate paths
        index_path = Path("./vector_db/faiss_index.index")
    
    if index_path.exists():
        size_mb = index_path.stat().st_size / (1024 * 1024)
        return True, f"Index loaded ({size_mb:.1f} MB)"
    return False, "Index not found"


def check_ollama_connection(timeout: float = 5.0) -> tuple[bool, str]:
    """Check Ollama connectivity."""
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    url = f"{ollama_url}/api/tags"
    
    try:
        if requests:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return True, f"Ollama OK ({len(models)} models)"
            return False, f"Ollama returned {response.status_code}"
        else:
            result = simple_get(url, timeout)
            if result["ok"]:
                return True, "Ollama OK"
            return False, f"Ollama error: {result.get('error', 'unknown')}"
    except Exception as e:
        # Ollama is optional - warn but don't fail
        return True, f"Ollama not available (optional): {e}"


def check_disk_space(min_gb: float = 1.0) -> tuple[bool, str]:
    """Check available disk space."""
    try:
        import shutil
        usage = shutil.disk_usage("/app")
        free_gb = usage.free / (1024**3)
        if free_gb < min_gb:
            return False, f"Low disk: {free_gb:.1f}GB (need {min_gb}GB)"
        return True, f"Disk OK ({free_gb:.1f}GB free)"
    except Exception as e:
        return True, f"Disk check skipped: {e}"


def check_memory_usage(max_percent: float = 90.0) -> tuple[bool, str]:
    """Check memory usage."""
    try:
        import psutil
        memory = psutil.virtual_memory()
        if memory.percent > max_percent:
            return False, f"High memory: {memory.percent:.1f}% (max {max_percent}%)"
        return True, f"Memory OK ({memory.percent:.1f}%)"
    except ImportError:
        return True, "Memory check skipped (psutil not installed)"
    except Exception as e:
        return True, f"Memory check skipped: {e}"


def run_health_checks() -> tuple[bool, dict]:
    """
    Run all health checks.
    
    Returns:
        Tuple of (overall_healthy, results_dict)
    """
    results = {}
    critical_failed = False
    
    # Critical checks (failure = unhealthy)
    critical_checks = [
        ("flask", check_flask_status),
        ("index", check_index_loaded),
    ]
    
    for name, check_fn in critical_checks:
        try:
            ok, msg = check_fn()
            results[name] = {"ok": ok, "message": msg}
            if not ok:
                critical_failed = True
        except Exception as e:
            results[name] = {"ok": False, "message": f"Check failed: {e}"}
            critical_failed = True
    
    # Non-critical checks (failure = warning only)
    optional_checks = [
        ("ollama", check_ollama_connection),
        ("disk", check_disk_space),
        ("memory", check_memory_usage),
    ]
    
    for name, check_fn in optional_checks:
        try:
            ok, msg = check_fn()
            results[name] = {"ok": ok, "message": msg, "optional": True}
        except Exception as e:
            results[name] = {"ok": False, "message": f"Check failed: {e}", "optional": True}
    
    return not critical_failed, results


def main():
    """Main entry point for Docker HEALTHCHECK."""
    try:
        healthy, results = run_health_checks()
        
        # Output JSON for debugging
        output = {
            "healthy": healthy,
            "checks": results,
        }
        
        if os.environ.get("HEALTH_CHECK_VERBOSE", "0") == "1":
            print(json.dumps(output, indent=2))
        else:
            # Compact output for logs
            status = "HEALTHY" if healthy else "UNHEALTHY"
            failed = [k for k, v in results.items() if not v["ok"] and not v.get("optional")]
            print(f"{status}: {', '.join(failed) if failed else 'all checks pass'}")
        
        sys.exit(0 if healthy else 1)
        
    except Exception as e:
        print(f"UNHEALTHY: Health check error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
