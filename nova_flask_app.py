from flask import Flask, render_template, request, jsonify
import backend as backend_mod
from backend import (
    nova_text_handler, check_lm_studio_connection, export_session_to_text,
    save_session_report, session_state, list_recent_sessions,
    reset_session, start_new_session, retrieve as _retrieve_uncached, build_index,
    vision_model, vision_embeddings, vision_paths
)
import cache_utils
import re
import hmac
from pathlib import Path

retrieve = cache_utils.cache_retrieval(_retrieve_uncached)

import os
# Start LM Studio as a background subprocess on Flask startup
from lm_studio_manager import start_lm_studio_server, verify_lm_studio_models
print("\n" + "=" * 70)
print("Starting LM Studio Server (Background Process)...")
print("=" * 70)
if start_lm_studio_server():
    verify_lm_studio_models()
else:
    print("[WARNING] Failed to start LM Studio - verify it's installed and PATH is configured")
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

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

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
def api_ask():
    if not _check_auth():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    mode = data.get("mode", "Auto")
    fallback = data.get("fallback")  # e.g., "retrieval-only"

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
        
        return jsonify({
            "answer": answer,
            "confidence": f"{confidence_pct*100:.1f}%",
            "retrieval_score": round(retrieval_score, 4),
            "traced_sources": traced_sources,
            "model_used": model_info.split("|")[0].strip() if "|" in model_info else "auto",
            "session_id": session_state.get("session_id"),
            "session_active": session_state.get("active", False),
            "audit_status": "enabled" if "audit" in model_info.lower() else "disabled",
            "effective_safety": "strict" if "strict" in model_info.lower() else "standard"
        })
    except Exception as e:
        # Avoid returning 500 on encoding issues (e.g., emojis); respond gracefully
        msg = str(e)
        if "encoding" in msg.lower() or "codec" in msg.lower():
            return jsonify({"error": "Server encoding error"}), 400
        return jsonify({"error": msg}), 500

@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        lm_studio_ok = check_lm_studio_connection()
        return jsonify({"lm_studio": lm_studio_ok, "index_loaded": True})
    except:
        return jsonify({"lm_studio": False, "index_loaded": False})

@app.route("/api/retrieve", methods=["POST"])
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
