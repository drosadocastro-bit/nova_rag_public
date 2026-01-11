# NIC Architecture Overview

This document summarizes the current structure of NIC with emphasis on safety and retrieval changes.

## Core Flow
1. **Flask API (`nova_flask_app.py`)**
   - Accepts UI/API traffic and applies optional rate limits.
   - Dispatches to `backend` for retrieval + generation.
2. **Backend Facade (`backend.py`)**
   - Central entry for retrieval, LLM calls, session management, and safety utilities.
   - Exposes symbols used by tests and the Flask layer.
3. **Retrieval Engine (`core/retrieval/retrieval_engine.py`)**
   - Hybrid retrieval: FAISS vectors + BM25 lexical union, plus MMR diversification.
   - Fallbacks: lexical/BM25 when embeddings or index are unavailable.
   - GAR query expansion (optional) and error-code boosting for diagnostics.
4. **Generation (`core/generation/llm_gateway.py`)**
   - Selects model (LLM_LLAMA/LLM_OSS) and routes calls; supports fallback models.
5. **Sessions (`core/session/session_manager.py`)**
   - Tracks troubleshooting sessions, turn history, and exports.
6. **Analytics (`analytics.py`)**
   - Records request metrics and model usage.

## Safety & Risk Layers
- **Risk Assessment (`agents/risk_assessment.py`)**: Detects emergencies (fire/smoke/unconscious), critical system failures (brakes/steering), fake parts, and injection patterns. Can refuse unsafe requests or short-circuit with safety messaging.
- **Injection Handling**: “Judge by intent, not syntax” approach strips injection wrappers, evaluates core question, and blocks unsafe intent. See `docs/INJECTION_HANDLING.md`.
- **Confidence Gating**: Low-retrieval-confidence paths can bypass LLM and return retrieval-only answers.
- **Human-on-the-loop**: System is advisory; no actuation.

## Retrieval Caching
- **Lightweight LRU Cache (opt-in)**: `nova_flask_app.py` wraps `_retrieve_uncached` when `NOVA_ENABLE_RETRIEVAL_CACHE=1`.
  - Size: `NOVA_RETRIEVAL_CACHE_SIZE` (default 128 entries).
  - Evicts least-recently-used items; bypasses cache when kwargs are unhashable.
- **Legacy `cache_utils`**: Deprecated; retained for backward compatibility only. New code should use the in-process wrapper or migrate to `core.caching.cache_manager`.

## Files & Responsibilities
- `nova_flask_app.py`: API surface, rate limiting, retrieval cache wrapper.
- `backend.py`: Facade aggregating retrieval, generation, safety helpers, and session utilities.
- `core/retrieval/retrieval_engine.py`: Index management, hybrid retrieval, rerankers, GAR, error-code boosting.
- `agents/risk_assessment.py`: Risk triage and injection detection helpers.
- `core/generation/llm_gateway.py`: Model selection and LLM dispatch.
- `core/session/session_manager.py`: Session lifecycle and exports.
- `analytics.py`: Request logging.

## Configuration Flags (selected)
- `NOVA_ENABLE_RETRIEVAL_CACHE` / `NOVA_RETRIEVAL_CACHE_SIZE`: Enable and size the LRU retrieval cache.
- `NOVA_FORCE_OFFLINE`, `NOVA_DISABLE_VISION`, `NOVA_DISABLE_CROSS_ENCODER`: Control model loading paths.
- `NOVA_HYBRID_SEARCH`: Toggle BM25 + vector union.
- `NOVA_RATE_LIMIT_ENABLED`, `NOVA_RATE_LIMIT_PER_MINUTE`: API throttling.
- `NOVA_CACHE_SECRET`: HMAC key for secure cache files (used by legacy secure_pickle).

## Safety Rationale
- Retrieval and generation are gated by risk assessment and injection handling before model calls.
- Critical safety-system failures and emergencies are surfaced early; unsafe or fabricated requests are refused.
- Offline-first design avoids external dependencies to reduce attack surface and data exfiltration risk.
