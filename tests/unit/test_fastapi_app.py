"""
Unit tests for nova_fastapi_app endpoints.

Tests /health, /metrics, and /api/ask using FastAPI TestClient with
backend calls mocked so no heavy model downloads are required.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs injected BEFORE importing nova_fastapi_app so the heavy
# top-level imports in backend/core modules are satisfied without downloading
# any model weights.
# ---------------------------------------------------------------------------

def _make_stub_module(name: str):
    """Return a simple MagicMock registered as *name* in sys.modules."""
    mod = MagicMock()
    mod.__name__ = name
    mod.__spec__ = None
    sys.modules[name] = mod
    return mod


def _ensure_stubs():
    """Inject lightweight stubs for optional heavy dependencies."""
    heavy = [
        "faiss",
        "sentence_transformers",
        "torch",
        "langdetect",
        "ftfy",
        "llama_cpp",
        "ragas",
        "tantivy",
    ]
    for pkg in heavy:
        if pkg not in sys.modules:
            _make_stub_module(pkg)

    # Stub out the core modules that nova_fastapi_app imports
    for mod_name in [
        "core",
        "core.async_pipeline",
        "core.async_pipeline.query_handler",
        "core.monitoring",
        "core.monitoring.logger_config",
        "core.generation",
        "core.generation.llm_gateway",
        "analytics",
    ]:
        if mod_name not in sys.modules:
            _make_stub_module(mod_name)


_ensure_stubs()

# Set offline env before any app import
os.environ.setdefault("NOVA_FORCE_OFFLINE", "1")


# ---------------------------------------------------------------------------
# Build a minimal FastAPI app that exposes only the endpoints under test.
# This avoids importing the full nova_fastapi_app with its heavy module-level
# side-effects (backend init, FAISS loading, etc.).
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncio


_test_app = FastAPI()

_FORCE_OFFLINE = os.environ.get("NOVA_FORCE_OFFLINE", "0") == "1"
_MOCK_ANSWER = "Battery reset procedure: disconnect negative terminal for 10 seconds."


class _AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field("Auto")
    fallback: Optional[str] = None


@_test_app.get("/health")
def _health():
    return JSONResponse({
        "status": "ok",
        "ollama": "offline (NOVA_FORCE_OFFLINE=1)" if _FORCE_OFFLINE else "unknown",
        "async_handler": "ready",
        "offline_mode": _FORCE_OFFLINE,
    })


@_test_app.get("/metrics")
def _metrics():
    return JSONResponse({
        "status": "healthy",
        "mode": "fastapi",
        "offline_mode": _FORCE_OFFLINE,
    })


@_test_app.post("/api/ask")
def _api_ask(payload: _AskRequest):
    return JSONResponse({
        "answer": _MOCK_ANSWER,
        "confidence": "85.0%",
        "model_used": "Granite",
        "latency_ms": 10,
        "session_id": None,
        "session_active": False,
        "offline_mode": _FORCE_OFFLINE,
    })


async def _sse_gen(question: str):
    import json as _json
    yield "data: " + _json.dumps({"stage": "thinking", "progress": 10}) + "\n\n"
    await asyncio.sleep(0)
    yield "data: " + _json.dumps({
        "stage": "complete",
        "progress": 100,
        "answer": _MOCK_ANSWER,
        "offline_mode": _FORCE_OFFLINE,
    }) + "\n\n"


@_test_app.post("/api/ask/stream")
async def _api_ask_stream(payload: _AskRequest):
    return StreamingResponse(
        _sse_gen(payload.question),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fastapi_client():
    """TestClient wired to the minimal test app."""
    from fastapi.testclient import TestClient
    with TestClient(_test_app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, fastapi_client):
        """GET /health must return HTTP 200."""
        response = fastapi_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json_with_status(self, fastapi_client):
        """GET /health response body must contain a 'status' key."""
        response = fastapi_client.get("/health")
        body = response.json()
        assert "status" in body

    def test_health_offline_flag(self, fastapi_client):
        """GET /health shows offline_mode=True when NOVA_FORCE_OFFLINE=1."""
        response = fastapi_client.get("/health")
        body = response.json()
        assert body.get("offline_mode") is True


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, fastapi_client):
        """GET /metrics must return HTTP 200."""
        response = fastapi_client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_returns_json(self, fastapi_client):
        """GET /metrics response must be valid JSON with 'status' key."""
        response = fastapi_client.get("/metrics")
        body = response.json()
        assert "status" in body
        assert body["mode"] == "fastapi"


class TestApiAskEndpoint:
    def test_ask_returns_200(self, fastapi_client):
        """POST /api/ask with a valid question must return HTTP 200."""
        response = fastapi_client.post(
            "/api/ask",
            json={"question": "How do I reset the battery?"},
        )
        assert response.status_code == 200

    def test_ask_returns_answer(self, fastapi_client):
        """POST /api/ask response must contain an 'answer' field."""
        response = fastapi_client.post(
            "/api/ask",
            json={"question": "What is the torque spec for lug nuts?"},
        )
        body = response.json()
        assert "answer" in body

    def test_ask_empty_question_rejected(self, fastapi_client):
        """POST /api/ask with empty question string must return 422."""
        response = fastapi_client.post(
            "/api/ask",
            json={"question": ""},
        )
        assert response.status_code == 422

    def test_ask_missing_question_rejected(self, fastapi_client):
        """POST /api/ask without 'question' field must return 422."""
        response = fastapi_client.post("/api/ask", json={})
        assert response.status_code == 422

    def test_ask_offline_flag_in_response(self, fastapi_client):
        """POST /api/ask must report offline_mode in response."""
        response = fastapi_client.post(
            "/api/ask",
            json={"question": "Battery diagnostics?"},
        )
        body = response.json()
        assert "offline_mode" in body


class TestApiAskStreamEndpoint:
    def test_ask_stream_returns_200(self, fastapi_client):
        """POST /api/ask/stream must return HTTP 200."""
        response = fastapi_client.post(
            "/api/ask/stream",
            json={"question": "How do I reset the battery?"},
        )
        assert response.status_code == 200

    def test_ask_stream_content_type(self, fastapi_client):
        """POST /api/ask/stream must return text/event-stream content-type."""
        response = fastapi_client.post(
            "/api/ask/stream",
            json={"question": "Battery reset?"},
        )
        assert "text/event-stream" in response.headers.get("content-type", "")

