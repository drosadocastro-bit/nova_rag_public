from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import backend as backend_mod
from backend import (
    nova_text_handler, check_ollama_connection, export_session_to_text,
    save_session_report, session_state, list_recent_sessions,
    reset_session, start_new_session, retrieve as _retrieve_uncached, build_index,
    vision_model, vision_embeddings, vision_paths
)
import analytics
import re
import hmac
from pathlib import Path
import time
from collections import OrderedDict
from core.safety import risk_assessment as safety_metrics

# Lightweight in-process retrieval cache to replace legacy cache_utils
_RETRIEVAL_CACHE_ENABLED = os.environ.get("NOVA_ENABLE_RETRIEVAL_CACHE", "0") == "1"
_RETRIEVAL_CACHE_SIZE = int(os.environ.get("NOVA_RETRIEVAL_CACHE_SIZE", "128"))
_retrieval_cache_store: OrderedDict = OrderedDict()


def _cached_retrieve(query: str, k: int = 12, top_n: int = 6, **kwargs):
    if not _RETRIEVAL_CACHE_ENABLED:
        return _retrieve_uncached(query, k=k, top_n=top_n, **kwargs)

    # Build a hashable cache key; if kwargs contain unhashable values, bypass cache.
    try:
        key = (query, k, top_n, tuple(sorted(kwargs.items())))
    except TypeError:
        return _retrieve_uncached(query, k=k, top_n=top_n, **kwargs)

    if key in _retrieval_cache_store:
        _retrieval_cache_store.move_to_end(key)
        return _retrieval_cache_store[key]

    result = _retrieve_uncached(query, k=k, top_n=top_n, **kwargs)
    _retrieval_cache_store[key] = result
    if len(_retrieval_cache_store) > max(1, _RETRIEVAL_CACHE_SIZE):
        _retrieval_cache_store.popitem(last=False)
    return result


retrieve = _cached_retrieve

import os

print("\n" + "=" * 70)
print("Using Ollama for local LLM inference (ensure service is running at http://127.0.0.1:11434)")
print("=" * 70 + "\n")

if os.environ.get("NOVA_WARMUP_ON_START", "0") == "1":
    try:
        import warmup_backend  # type: ignore[import-not-found]  # Optional module
    except Exception as e:
        print(f"[WARMUP] Skipped: {e}")

# Use relative paths for Flask template and static folders
BASE_DIR = Path(__file__).parent.resolve()
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config["PROPAGATE_EXCEPTIONS"] = True

# Rate limiting configuration
# Defaults: 100 requests per hour globally, 20 per minute for API endpoints
# Can be overridden via environment variables
RATE_LIMIT_ENABLED = os.environ.get("NOVA_RATE_LIMIT_ENABLED", "1") == "1"
RATE_LIMIT_PER_HOUR = os.environ.get("NOVA_RATE_LIMIT_PER_HOUR", "100")
RATE_LIMIT_PER_MINUTE = os.environ.get("NOVA_RATE_LIMIT_PER_MINUTE", "20")

if RATE_LIMIT_ENABLED:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[f"{RATE_LIMIT_PER_HOUR} per hour"],
        storage_uri="memory://",
        strategy="fixed-window",
    )
    print(f"[RateLimit] Enabled: {RATE_LIMIT_PER_HOUR}/hour, {RATE_LIMIT_PER_MINUTE}/minute for API")
else:
    # Create a no-op limiter when disabled
    limiter = Limiter(
        get_remote_address,
        app=app,
        enabled=False,
    )
    print("[RateLimit] Disabled")

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded errors."""
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": e.description
    }), 429

@app.after_request
def set_security_headers(response):
    """Add security headers to all responses."""
    # Content Security Policy - prevents XSS attacks
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    # Prevent MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # XSS protection (legacy browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.before_request
def setup():
    pass

API_TOKEN = os.environ.get("NOVA_API_TOKEN")
REQUIRE_TOKEN = bool(os.environ.get("NOVA_REQUIRE_TOKEN", "0") == "1")

def _check_auth():
    """Check API authentication using constant-time comparison to prevent timing attacks."""
    if not REQUIRE_TOKEN:
        return True
    token = request.headers.get("X-API-TOKEN", "")
    if not API_TOKEN:
        return False
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, API_TOKEN)

@app.route("/api/ask", methods=["POST"])
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE} per minute")
def api_ask():
    if not _check_auth():
        return jsonify({"error": "Unauthorized"}), 403
    
    start_time = time.time()
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    mode = data.get("mode", "Auto")
    fallback = data.get("fallback")  # e.g., "retrieval-only"
    
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    def _refuse_input(reason: str, message: str, http_status: int = 200):
        # Keep response JSON shape consistent: answer is a structured object.
        # Use ASCII-only messages to avoid Windows console encoding surprises.
        answer = {
            "response_type": "refusal",
            "reason": reason,
            "policy": "Input Validation",
            "message": message,
            "question": question,
        }
        return (
            jsonify(
                {
                    "answer": answer,
                    "confidence": "0.0%",
                    "model_used": "none",
                    "session_id": session_state.get("session_id"),
                    "session_active": session_state.get("active", False),
                    "audit_status": "disabled",
                    "effective_safety": "strict",
                }
            ),
            http_status,
        )

    # Basic input validation and edge-case handling
    # Return a safe structured refusal (HTTP 200) so clients/tests treat it as handled.
    try:
        if not question:
            return _refuse_input("invalid_format", "Empty question. Please provide a vehicle-maintenance question.")

        if len(question) > 5000:
            return _refuse_input("too_long", "Input too long. Please shorten the question and try again.")

        ql = question.lower()
        if any(p in ql for p in ["<script>", "</script>", "drop table", "select * from", "--"]):
            return _refuse_input("invalid_format", "Malformed input. Please ask a normal, non-code question.")

        # Emoji-only / symbol-only queries: treat as invalid format
        if not re.search(r"[A-Za-z0-9]", question):
            return _refuse_input("invalid_format", "Invalid format. Please enter a text question describing the issue.")

        # Detect extremely repetitive tokens that cause degenerate behavior
        if len(set(ql.split())) <= 2 and len(ql.split()) > 50:
            return _refuse_input("invalid_format", "Malformed input. Please avoid overly repetitive text.")
    except Exception:
        # Fall through on validation errors to avoid 500s
        pass

    if not question:
        return _refuse_input("invalid_format", "Empty question. Please provide a vehicle-maintenance question.")
    
    try:
        # First, retrieve source documents for transparency metadata
        traced_sources = []
        try:
            docs = retrieve(question, k=12, top_n=6)
            for d in docs:
                traced_sources.append({
                    "source": d.get("source", "unknown"),
                    "page": d.get("page"),
                    "confidence": round(float(d.get("confidence", 0)), 4),
                    "snippet": (d.get("text") or d.get("snippet") or "")[:150],
                })
        except Exception:
            pass  # Retrieval metadata is optional; don't fail the request
        
        answer, model_info = nova_text_handler(question, mode, fallback_mode=fallback)

        confidence_match = re.search(r"Confidence:\s*([\d.]+)%", model_info)
        confidence_pct = float(confidence_match.group(1))/100 if confidence_match else 0.0
        
        # Compute retrieval_score as average of traced source confidences
        retrieval_score = 0.0
        if traced_sources:
            retrieval_score = sum(s["confidence"] for s in traced_sources) / len(traced_sources)
        
        # Build response with consistent structure
        # Note: answer can be either a string or dict (for structured responses like troubleshooting, procedures, etc.)
        # Flask's jsonify() automatically handles proper JSON serialization for both types
        safety_meta = {
            "heuristic_triggers": session_state.get("last_heuristic_triggers") or [],
            "heuristic_trigger": session_state.get("last_heuristic_trigger"),
        }
        response_data = {
            "answer": answer,
            "confidence": f"{confidence_pct*100:.1f}%",
            "retrieval_score": round(retrieval_score, 4),
            "traced_sources": traced_sources,
            "model_used": model_info.split("|")[0].strip() if "|" in model_info else "auto",
            "session_id": session_state.get("session_id"),
            "session_active": session_state.get("active", False),
            "audit_status": "enabled" if "audit" in model_info.lower() else "disabled",
            "effective_safety": "strict" if "strict" in model_info.lower() else "standard",
            "safety_meta": safety_meta,
        }
        
        # Log request analytics
        response_time_ms = int((time.time() - start_time) * 1000)
        answer_text = answer if isinstance(answer, str) else str(answer.get("message", ""))
        analytics.log_request(
            question=question,
            mode=mode,
            model_used=response_data["model_used"],
            confidence=confidence_pct,
            response_time_ms=response_time_ms,
            retrieval_score=retrieval_score,
            num_sources=len(traced_sources),
            answer_length=len(answer_text),
            session_id=session_state.get("session_id"),
            user_ip=user_ip,
            response_type="answer",
            decision_tag=session_state.get("last_decision_tag"),
            heuristic_trigger=session_state.get("last_heuristic_trigger"),
            heuristic_triggers=session_state.get("last_heuristic_triggers"),
        )
        
        return jsonify(response_data)
    except Exception as e:
        # Avoid returning 500 on encoding issues (e.g., emojis); respond gracefully
        msg = str(e)
        if "encoding" in msg.lower() or "codec" in msg.lower():
            return jsonify({"error": "Server encoding error"}), 400
        return jsonify({"error": msg}), 500

@app.route("/api/status", methods=["GET"])
@limiter.limit("60 per minute")
def api_status():
    try:
        ok, detail = check_ollama_connection()
        return jsonify({"ollama": ok, "ollama_status": detail.strip(), "index_loaded": True})
    except Exception:
        return jsonify({"ollama": False, "ollama_status": "error", "index_loaded": False})

@app.route("/api/retrieve", methods=["POST"])
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE} per minute")
def api_retrieve():
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    k = int(data.get("k", 6))
    
    if not query:
        return jsonify([])
    
    try:
        docs = retrieve(query, k=k, top_n=min(k, 6))
        return jsonify([{
            "text": d.get("text", "")[:200],
            "source": d.get("source", "unknown"),
            "confidence": round(float(d.get("confidence", 0)), 2)
        } for d in docs])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/metrics", methods=["GET"])
@limiter.limit("120 per minute")
def metrics():
    """Prometheus-compatible metrics endpoint."""
    import time
    
    # Get cache stats if SQL logging enabled
    cache_stats = cache_utils.get_query_stats()
    
    # Basic metrics
    metrics_data = {
        "timestamp": time.time(),
        "uptime_seconds": time.time() - app.config.get("start_time", time.time()),
        "queries_total": cache_stats.get("total_queries", 0),
        "avg_response_time_ms": cache_stats.get("avg_response_time_ms", 0),
        "avg_retrieval_confidence": cache_stats.get("avg_retrieval_confidence", 0),
        "audit_status_breakdown": cache_stats.get("audit_status_breakdown", {}),
        "cache_enabled": os.environ.get("NOVA_ENABLE_RETRIEVAL_CACHE", "0") == "1",
        "rate_limit_enabled": RATE_LIMIT_ENABLED,
        "hybrid_search_enabled": os.environ.get("NOVA_HYBRID_SEARCH", "1") == "1",
        "safety_heuristic_triggers": safety_metrics.get_trigger_counts(),
    }
    
    return jsonify(metrics_data)

@app.route("/api/analytics", methods=["GET"])
@limiter.limit("30 per minute")
def api_analytics():
    """Analytics endpoint - returns request logs and usage statistics."""
    try:
        days = int(request.args.get("days", 7))
        summary = analytics.get_analytics_summary(days=days)
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/analytics/recent", methods=["GET"])
@limiter.limit("30 per minute")
def api_analytics_recent():
    """Get recent requests for debugging."""
    try:
        limit = int(request.args.get("limit", 50))
        requests_data = analytics.get_recent_requests(limit=limit)
        return jsonify({"requests": requests_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/analytics/trends", methods=["GET"])
@limiter.limit("30 per minute")
def api_analytics_trends():
    """Get performance trends over time."""
    try:
        days = int(request.args.get("days", 30))
        trends = analytics.get_performance_trends(days=days)
        return jsonify({"trends": trends})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_startup_validation():
    """
    Comprehensive startup validation checks.
    Verifies system readiness before accepting requests.
    Returns True if all checks pass, False otherwise.
    """
    print("\n" + "=" * 70)
    print("STARTUP VALIDATION")
    print("=" * 70)
    
    all_checks_passed = True
    warnings = []
    
    # 1. Check required environment variables (optional but recommended)
    print("\n[1/5] Checking environment configuration...")
    optional_vars = {
        "NOVA_CITATION_AUDIT": "Citation audit (recommended for production)",
        "NOVA_CITATION_STRICT": "Strict citation mode",
        "NOVA_HYBRID_SEARCH": "Hybrid retrieval (vector + BM25)",
    }
    
    for var, description in optional_vars.items():
        value = os.environ.get(var, "not set")
        status = "[OK]" if value != "not set" else "[DEFAULT]"
        print(f"  {status} {var}: {value} ({description})")
        if value == "not set":
            warnings.append(f"{var} not set (using default)")
    
    # 2. Check Ollama connectivity
    print("\n[2/5] Checking Ollama connectivity...")
    try:
        ollama_ok, ollama_detail = check_ollama_connection()
        if ollama_ok:
            print("  [OK] Ollama connection successful")
            print(f"    {ollama_detail.strip()}")
        else:
            print(f"  [FAIL] Ollama connection failed: {ollama_detail}")
            print("    -> Start Ollama: 'ollama serve'")
            print("    -> Verify model: 'ollama pull llama3.2:8b'")
            all_checks_passed = False
    except Exception as e:
        print(f"  [FAIL] Ollama check error: {e}")
        all_checks_passed = False
    
    # 3. Check FAISS index existence and integrity
    print("\n[3/5] Checking FAISS index...")
    try:
        from pathlib import Path
        index_path = BASE_DIR / "vector_db" / "vehicle_index.faiss"
        docs_path = BASE_DIR / "vector_db" / "vehicle_docs.jsonl"
        
        if index_path.exists():
            print(f"  [OK] Index file found: {index_path}")
            # Quick integrity check
            import faiss
            index = faiss.read_index(str(index_path))
            print(f"  [OK] Index loaded successfully ({index.ntotal} vectors)")
            
            if docs_path.exists():
                print(f"  [OK] Documents metadata found: {docs_path}")
            else:
                print(f"  [WARN] Documents metadata missing: {docs_path}")
                warnings.append("Documents metadata missing (may affect retrieval)")
        else:
            print(f"  [FAIL] Index file not found: {index_path}")
            print("    -> Build index: 'python ingest_vehicle_manual.py'")
            all_checks_passed = False
    except Exception as e:
        print(f"  [FAIL] Index check error: {e}")
        all_checks_passed = False
    
    # 4. Check cache directory permissions
    print("\n[4/5] Checking cache directory permissions...")
    try:
        cache_dir = BASE_DIR / "vector_db"
        if cache_dir.exists():
            # Test write permissions
            test_file = cache_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
                print(f"  [OK] Cache directory writable: {cache_dir}")
            except PermissionError:
                print(f"  [FAIL] Cache directory not writable: {cache_dir}")
                print(f"    -> Fix permissions: 'chmod 755 {cache_dir}'")
                warnings.append("Cache directory not writable (caching disabled)")
        else:
            print(f"  [WARN] Cache directory does not exist: {cache_dir}")
            warnings.append("Cache directory missing (will be created on first use)")
    except Exception as e:
        print(f"  [WARN] Cache check error: {e}")
        warnings.append(f"Cache check failed: {e}")
    
    # 5. Check Python dependencies
    print("\n[5/5] Checking Python dependencies...")
    required_modules = [
        ("faiss", "FAISS vector search"),
        ("torch", "PyTorch"),
        ("sentence_transformers", "Sentence embeddings"),
        ("flask", "Web framework"),
    ]
    
    for module, description in required_modules:
        try:
            if module == "sentence_transformers":
                # Avoid heavy import during validation; check install via metadata
                try:
                    import importlib.metadata as importlib_metadata
                except ImportError:
                    import importlib_metadata  # type: ignore
                importlib_metadata.version("sentence-transformers")
            else:
                __import__(module)
            print(f"  [OK] {module} ({description})")
        except Exception:
            print(f"  [FAIL] {module} not found ({description})")
            print("    -> Install: 'pip install -r requirements.txt'")
            all_checks_passed = False
    
    # Summary
    print("\n" + "=" * 70)
    if all_checks_passed:
        print("STARTUP VALIDATION: ALL CHECKS PASSED")
        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for warning in warnings:
                print(f"  - {warning}")
    else:
        print("STARTUP VALIDATION: FAILED")
        print("\nCritical issues detected. Please resolve them before starting.")
        print("See documentation: docs/TROUBLESHOOTING.md")
    print("=" * 70 + "\n")
    
    return all_checks_passed

if __name__ == "__main__":
    import time
    
    # Track application start time for uptime metrics
    app.config["start_time"] = time.time()
    
    # Run startup validation
    validation_passed = run_startup_validation()
    
    if not validation_passed:
        print("\nERROR: Startup validation failed. Exiting.")
        print("See docs/TROUBLESHOOTING.md for help resolving issues.\n")
        import sys
        sys.exit(1)
    
    # Start Flask application
    print("Starting Flask application...")
    app.run(host="127.0.0.1", port=5000, debug=False)
