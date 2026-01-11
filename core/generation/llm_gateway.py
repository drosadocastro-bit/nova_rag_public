"""
LLM gateway utilities: Ollama connectivity checks, model resolution, and
LLM invocation with native llama-cpp or HTTP fallback.
"""

from __future__ import annotations

import os
from typing import Tuple

import requests
from openai import OpenAI

# LLM Engine - Native Python integration (llama-cpp-python)
native_call_llm = None
try:
    from llm_engine import get_engine, call_llm as native_call_llm, LLAMA_CPP_AVAILABLE  # type: ignore

    USE_NATIVE_ENGINE = os.environ.get("NOVA_USE_NATIVE_LLM", "1") == "1" and LLAMA_CPP_AVAILABLE
    if USE_NATIVE_ENGINE:
        print("[NovaRAG] Using native llama-cpp-python engine (30k context, optimized)")
    else:
        print("[NovaRAG] Using HTTP client (Ollama API)")
except ImportError:  # pragma: no cover - runtime detection only
    USE_NATIVE_ENGINE = False
    print("[NovaRAG] llama-cpp-python not available, using HTTP client")

# =======================
# CONNECTION STATUS
# =======================


def check_ollama_connection() -> Tuple[bool, str]:
    """Check if Ollama is reachable."""
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if response.status_code == 200:
            return True, " Ollama Connected"
        else:
            return False, " Ollama responded but with errors"
    except requests.exceptions.ConnectionError:
        return False, " Ollama Offline - Check if server is running"
    except requests.exceptions.Timeout:
        return False, " Ollama Timeout - Server slow to respond"
    except Exception as e:  # pragma: no cover - runtime logging
        return False, f" Connection Error: {str(e)[:50]}"


# =======================
# MODEL CONFIG
# =======================

OLLAMA_TIMEOUT_S = float(os.environ.get("NOVA_OLLAMA_TIMEOUT_S", "1200"))
OLLAMA_MODEL_LOAD_TIMEOUT_S = float(
    os.environ.get("NOVA_OLLAMA_MODEL_LOAD_TIMEOUT_S", str(min(OLLAMA_TIMEOUT_S, 1200.0)))
)

client = None
if not USE_NATIVE_ENGINE:
    try:
        import httpx

        _httpx_client = httpx.Client(verify=False, timeout=httpx.Timeout(OLLAMA_TIMEOUT_S))
        client = OpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            http_client=_httpx_client,
        )
        print("[NovaRAG] HTTP client initialized for Ollama (port 11434)")
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG] Warning: Ollama client initialization failed ({e}); will retry on first LLM call")
        client = None

LLM_LLAMA = os.environ.get("NOVA_LLM_LLAMA", "llama3.2:8b")
LLM_OSS = os.environ.get("NOVA_LLM_OSS", "qwen2.5-coder:14b")

MAX_TOKENS_LLAMA = int(os.environ.get("NOVA_MAX_TOKENS_LLAMA", "4096"))
MAX_TOKENS_OSS = int(os.environ.get("NOVA_MAX_TOKENS_OSS", "512"))


# Heuristic keyword sets used by choose_model
TROUBLESHOOT_TRIGGERS = [
    "troubleshoot",
    "troubleshooting",
    "intermittent",
    "diagnostic",
    "fault",
    "failure",
    "error",
    "trouble",
]

DEEP_KEYWORDS = [
    "explain",
    "why",
    "root cause",
    "analysis",
    "analyze",
    "detailed",
    "theory",
    "concept",
    "in depth",
    "deep",
    "diagnosis",
    "reasoning",
]

FAST_KEYWORDS = [
    "steps",
    "procedure",
    "process",
    "checklist",
    "sequence",
    "how do i",
    "how to",
    "replace",
    "remove",
    "install",
    "test",
    "verify",
    "adjust",
    "reset",
    "configure",
    "runbook",
]


# =======================
# HELPERS
# =======================


def get_max_tokens(model_name: str) -> int:
    return MAX_TOKENS_LLAMA if model_name == LLM_LLAMA else MAX_TOKENS_OSS


def ensure_model_loaded(model_name: str, max_tokens: int | None = None) -> None:
    """Force Ollama to load the requested model by sending a minimal request."""
    try:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": max_tokens or min(64, get_max_tokens(model_name)),
            "temperature": 0.1,
            "stream": False,
        }
        requests.post(
            "http://localhost:11434/v1/chat/completions",
            json=payload,
            timeout=OLLAMA_MODEL_LOAD_TIMEOUT_S,
        )
    except Exception as e:  # pragma: no cover - runtime logging
        print(f"[NovaRAG] Ollama model load check failed: {e}")


def resolve_model_name(requested_model: str) -> str:
    """Ensure the model exists in Ollama; fall back to the first available."""
    try:
        resp = requests.get("http://localhost:11434/v1/models", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            ids = [m.get("id") for m in models if m.get("id")]
            if requested_model in ids:
                print(f"[NovaRAG]  Using requested model: {requested_model}")
                return requested_model
            if ids:
                fallback = ids[0]
                print(f"[NovaRAG]  Model '{requested_model}' not loaded in Ollama")
                print(f"[NovaRAG]  Falling back to: {fallback}")
                print(f"[NovaRAG]  Available models: {', '.join(ids)}")
                print("[NovaRAG]  Set NOVA_LLM_LLAMA or NOVA_LLM_OSS env vars to avoid fallback")
                return fallback
            else:
                print("[NovaRAG]  No models loaded in Ollama. Load at least one model.")
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG]  Model resolution check failed: {e}")
        print("[NovaRAG]  Ensure Ollama is running on localhost:11434")
    return requested_model


def choose_model(query_lower: str, mode: str) -> tuple[str, str]:
    """Return (model_name, decision_reason)."""
    if mode == "LLAMA (Fast)":
        return LLM_LLAMA, "Manual: LLAMA (Fast)"
    if mode in {"GPT-OSS (Deep)", "Qwen 14B (Deep)", "Qwen 14B (Deep Reasoning)"}:
        return LLM_OSS, f"Manual: {mode}"

    if any(k in query_lower for k in DEEP_KEYWORDS):
        return LLM_OSS, "Auto: deep keywords detected  GPT-OSS"
    if any(k in query_lower for k in FAST_KEYWORDS):
        return LLM_LLAMA, "Auto: procedure keywords detected  LLAMA"
    if any(t in query_lower for t in TROUBLESHOOT_TRIGGERS):
        return LLM_LLAMA, "Auto: troubleshooting keywords detected  LLAMA"

    return LLM_OSS, "Auto: fallback  GPT-OSS"


# =======================
# LLM CALLER
# =======================


def call_llm(prompt: str, model_name: str, fallback_on_timeout: bool = True) -> str:
    """Call LLM with optional 8B fallback on timeout."""
    system_instructions = (
        "You are an expert vehicle maintenance AI assistant: "
        "precise, helpful, and technically accurate. Use only the provided context; if "
        "something is unknown, say so clearly."
    )

    model_key = "llama" if "llama" in model_name.lower() or "8b" in model_name.lower() else "qwen"

    if USE_NATIVE_ENGINE and native_call_llm is not None:
        try:
            full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
            print(f"[DEBUG] Calling native engine with model_key={model_key}")
            response = native_call_llm(full_prompt, model=model_key)
            print(f"[DEBUG] Native engine returned successfully, length={len(response)}")
            return response.strip()
        except Exception as e:  # pragma: no cover
            print(f"[DEBUG] Native engine exception: {type(e).__name__}: {str(e)[:200]}")
            error_msg = str(e).lower()
            is_timeout = "timeout" in error_msg or "timed out" in error_msg

            if is_timeout and fallback_on_timeout and model_key == "qwen":
                print("[NovaRAG] ⚠️  Qwen timeout, falling back to 8B...")
                try:
                    full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
                    response = native_call_llm(full_prompt, model="llama")
                    print("[NovaRAG] ✅ Fallback to 8B succeeded")
                    return response.strip()
                except Exception as fallback_error:  # pragma: no cover
                    print(f"[NovaRAG] ❌ Fallback failed: {fallback_error}")
                    raise
            raise

    global client
    if client is None:
        try:
            client = OpenAI(
                base_url="http://127.0.0.1:11434/v1",
                api_key="ollama",
                timeout=OLLAMA_TIMEOUT_S,
            )
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Ollama client unavailable: {e}")

    resolved_model = resolve_model_name(model_name)
    ensure_model_loaded(resolved_model)

    try:
        completion = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {
                    "role": "user",
                    "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                },
            ],
            temperature=0.15,
            max_tokens=get_max_tokens(resolved_model),
        )
        content = completion.choices[0].message.content
        return content.strip() if content else ""

    except Exception as e:
        error_msg = str(e).lower()
        is_timeout = "timeout" in error_msg or "timed out" in error_msg

        if is_timeout and fallback_on_timeout and model_name == LLM_OSS:
            print("[NovaRAG] ⚠️  Qwen timeout detected, falling back to 8B model...")
            try:
                fallback_model = resolve_model_name(LLM_LLAMA)
                ensure_model_loaded(fallback_model)
                completion = client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {
                            "role": "user",
                            "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                        },
                    ],
                    temperature=0.15,
                    max_tokens=get_max_tokens(fallback_model),
                )
                content = completion.choices[0].message.content
                print("[NovaRAG] ✅ Fallback to 8B succeeded")
                return content.strip() if content else ""
            except Exception as fallback_error:  # pragma: no cover
                print(f"[NovaRAG] ❌ Fallback also failed: {fallback_error}")
                raise

        print(f"[NovaRAG] LLM call failed: {e}. Retrying after load...")
        ensure_model_loaded(resolved_model)
        completion = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {
                    "role": "user",
                    "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                },
            ],
            temperature=0.15,
            max_tokens=get_max_tokens(resolved_model),
        )

        content = completion.choices[0].message.content
        return content.strip() if content else ""


__all__ = [
    "LLM_LLAMA",
    "LLM_OSS",
    "MAX_TOKENS_LLAMA",
    "MAX_TOKENS_OSS",
    "TROUBLESHOOT_TRIGGERS",
    "DEEP_KEYWORDS",
    "FAST_KEYWORDS",
    "USE_NATIVE_ENGINE",
    "check_ollama_connection",
    "ensure_model_loaded",
    "resolve_model_name",
    "get_max_tokens",
    "choose_model",
    "call_llm",
]
