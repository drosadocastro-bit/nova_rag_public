# Legacy Flask Implementation

> **⚠️ Deprecated — for reference only.**
>
> The Flask-based server (`nova_flask_app.py`) is **no longer the supported
> entrypoint**. It is kept here solely for historical reference and is **not
> actively maintained**.

## What is here

| File | Description |
|------|-------------|
| `nova_flask_app.py` | Original Flask API server (≤ v1.x) |
| `run_waitress.py` | Waitress WSGI runner for the Flask app |

## Use FastAPI instead

The supported server is now **FastAPI** (`nova_fastapi_app.py` at the
repository root).

```bash
# Start the FastAPI server (recommended)
uvicorn nova_fastapi_app:app --host 127.0.0.1 --port 5678 --reload
```

Key endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ask` | POST | Primary query endpoint |
| `/api/ask/stream` | POST | Streaming query (SSE) |
| `/health` | GET | Health check (fast, no LLM call) |
| `/metrics` | GET | Basic runtime metrics |

## Offline mode

Set `NOVA_FORCE_OFFLINE=1` to disable all remote-LLM paths.  The server
will automatically fall back to retrieval-only mode so no network calls are
made to Ollama or any other remote service.

## Why was Flask replaced?

- FastAPI provides native async support, enabling streaming responses.
- Pydantic models offer built-in request validation.
- The OpenAPI docs UI (`/docs`) is generated automatically.
- Better performance under concurrent load.
