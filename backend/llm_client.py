"""
LLM client for NovaRAG - handles all LLM calling logic.
Supports both native llama-cpp-python engine and HTTP Ollama API.
"""

from __future__ import annotations

import os
import requests
from openai import OpenAI

from backend.prompt_builder import LLM_LLAMA, LLM_OSS, get_max_tokens


# =======================
# TIMEOUT CONFIGURATION
# =======================

# Timeouts: prefer correctness over speed for safety-critical troubleshooting.
# These can be overridden per environment.
OLLAMA_TIMEOUT_S = float(os.environ.get("NOVA_OLLAMA_TIMEOUT_S", "1200"))
OLLAMA_MODEL_LOAD_TIMEOUT_S = float(os.environ.get("NOVA_OLLAMA_MODEL_LOAD_TIMEOUT_S", str(min(OLLAMA_TIMEOUT_S, 1200.0))))


# =======================
# NATIVE ENGINE SETUP
# =======================

# LLM Engine - Native Python integration (llama-cpp-python)
native_call_llm = None
USE_NATIVE_ENGINE = False

try:
    from llm_engine import get_engine, call_llm as native_call_llm, LLAMA_CPP_AVAILABLE
    USE_NATIVE_ENGINE = os.environ.get("NOVA_USE_NATIVE_LLM", "1") == "1" and LLAMA_CPP_AVAILABLE
    if USE_NATIVE_ENGINE:
        print("[NovaRAG] Using native llama-cpp-python engine (30k context, optimized)")
    else:
        print("[NovaRAG] Using HTTP client (Ollama API)")
except ImportError:
    USE_NATIVE_ENGINE = False
    print("[NovaRAG] llama-cpp-python not available, using HTTP client")


# =======================
# HTTP CLIENT SETUP
# =======================

# HTTP client (fallback when native engine not available)
client = None
if not USE_NATIVE_ENGINE:
    try:
        # Use a custom httpx client with SSL verification disabled to avoid
        # Windows SSL context initialization delays for local HTTP endpoints.
        import httpx
        _httpx_client = httpx.Client(verify=False, timeout=httpx.Timeout(OLLAMA_TIMEOUT_S))
        client = OpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            http_client=_httpx_client,
        )
        print("[NovaRAG] HTTP client initialized for Ollama (port 11434)")
    except Exception as e:
        print(f"[NovaRAG] Warning: Ollama client initialization failed ({e}); will retry on first LLM call")
        client = None


# =======================
# CONNECTION CHECK
# =======================

def check_ollama_connection() -> tuple[bool, str]:
    """Check if Ollama is reachable."""
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if response.status_code == 200:
            return True, "✅ Ollama Connected"
        else:
            return False, "⚠️ Ollama responded but with errors"
    except requests.exceptions.ConnectionError:
        return False, "❌ Ollama Offline - Check if server is running"
    except requests.exceptions.Timeout:
        return False, "⏱️ Ollama Timeout - Server slow to respond"
    except Exception as e:
        return False, f"❌ Connection Error: {str(e)[:50]}"


# =======================
# MODEL MANAGEMENT
# =======================

def ensure_model_loaded(model_name: str, max_tokens: int | None = None) -> None:
    """Force Ollama to load the requested model by sending a minimal request.
    This avoids 400 'Model is unloaded' errors on first call.
    """
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
    except Exception as e:
        print(f"[NovaRAG] Ollama model load check failed: {e}")


def resolve_model_name(requested_model: str) -> str:
    """Ensure the model exists in Ollama; fall back to the first available."""
    try:
        resp = requests.get("http://localhost:11434/v1/models", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            ids = [m.get("id") for m in models if m.get("id")]
            if requested_model in ids:
                print(f"[NovaRAG] ✅ Using requested model: {requested_model}")
                return requested_model
            if ids:
                fallback = ids[0]
                print(f"[NovaRAG] ⚠️ Model '{requested_model}' not loaded in Ollama")
                print(f"[NovaRAG] ⚠️ Falling back to: {fallback}")
                print(f"[NovaRAG]    Available models: {', '.join(ids)}")
                print(f"[NovaRAG]    Set NOVA_LLM_LLAMA or NOVA_LLM_OSS env vars to avoid fallback")
                return fallback
            else:
                print(f"[NovaRAG] ❌ No models loaded in Ollama. Load at least one model.")
    except Exception as e:
        print(f"[NovaRAG] ⚠️ Model resolution check failed: {e}")
        print(f"[NovaRAG]    Ensure Ollama is running on localhost:11434")
    return requested_model


# =======================
# LLM CALLING
# =======================

def call_llm(prompt: str, model_name: str, fallback_on_timeout: bool = True) -> str:
    """Call LLM with optional 8B fallback on timeout.
    
    Args:
        prompt: The prompt to send to the model
        model_name: Target model (LLM_LLAMA or LLM_OSS)
        fallback_on_timeout: If True and Qwen times out, retry with 8B model
    """
    system_instructions = (
        "You are an expert vehicle maintenance AI assistant: "
        "precise, helpful, and technically accurate. Use only the provided context; if "
        "something is unknown, say so clearly."
    )
    
    # Map model names to engine keys early (used in both native and HTTP paths)
    model_key = "llama" if "llama" in model_name.lower() or "8b" in model_name.lower() else "qwen"
    
    # === NATIVE ENGINE PATH (llama-cpp-python) ===
    if USE_NATIVE_ENGINE and native_call_llm is not None:
        try:
            # Build full prompt with system instructions
            full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
            
            # Call native engine
            print(f"[DEBUG] Calling native engine with model_key={model_key}")
            response = native_call_llm(full_prompt, model=model_key)
            print(f"[DEBUG] Native engine returned successfully, length={len(response)}")
            return response.strip()
            
        except Exception as e:
            print(f"[DEBUG] Native engine exception: {type(e).__name__}: {str(e)[:200]}")
            error_msg = str(e).lower()
            is_timeout = "timeout" in error_msg or "timed out" in error_msg
            
            # Fallback to 8B on Qwen timeout
            if is_timeout and fallback_on_timeout and model_key == "qwen":
                print(f"[NovaRAG] ⚠️ Qwen timeout, falling back to 8B...")
                try:
                    full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
                    response = native_call_llm(full_prompt, model="llama")
                    print(f"[NovaRAG] ✅ Fallback to 8B succeeded")
                    return response.strip()
                except Exception as fallback_error:
                    print(f"[NovaRAG] ❌ Fallback failed: {fallback_error}")
                    raise
            raise
    
    # === HTTP CLIENT PATH (Ollama API) ===
    # Ensure client exists (can be None if Ollama was unavailable at import time)
    global client
    if client is None:
        try:
            client = OpenAI(
                base_url="http://127.0.0.1:11434/v1",
                api_key="ollama",
                timeout=OLLAMA_TIMEOUT_S,
            )
        except Exception as e:
            raise RuntimeError(f"Ollama client unavailable: {e}")

    # Resolve to an available model and pre-load it
    resolved_model = resolve_model_name(model_name)
    ensure_model_loaded(resolved_model)
    
    try:
        completion = client.chat.completions.create(
            model=resolved_model,
            # Some local prompt templates only allow user/assistant roles;
            # fold the system prompt into the user message to avoid template errors.
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
        
        # If Qwen times out and fallback is enabled, retry with 8B
        if is_timeout and fallback_on_timeout and model_name == LLM_OSS:
            print(f"[NovaRAG] ⚠️ Qwen timeout detected, falling back to 8B model...")
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
                print(f"[NovaRAG] ✅ Fallback to 8B succeeded")
                return content.strip() if content else ""
            except Exception as fallback_error:
                print(f"[NovaRAG] ❌ Fallback also failed: {fallback_error}")
                raise
        
        # Retry once after an explicit load attempt if first call failed (non-timeout)
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
