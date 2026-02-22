# Core Package Guide

This folder contains NIC runtime core logic (retrieval, routing, governance, trust, generation adapters, and supporting services).

If you are new to the project, start with the repository landing page:
- [README.md](../README.md)

For full docs navigation:
- [docs/INDEX.md](../docs/INDEX.md)

---

## Core Subsystems

- [app_state.py](app_state.py) — central application state and initialization
- [handlers](handlers) — framework-agnostic query handling
- [retrieval](retrieval) — retrieval engine, hybrid search, reranking, indexing
- [governance](governance) — runtime policy and approvals integration
- [trust_context.py](trust_context.py) — trust/evidence tracking
- [generation](generation) — LLM gateway and model selection
- [safety](safety) — injection handling and output sanitization
- [monitoring](monitoring) — logging and health telemetry

---

## Recommended Reading Order (Developers)

1. [handlers/query_handler.py](handlers/query_handler.py)
2. [retrieval/retrieval_engine.py](retrieval/retrieval_engine.py)
3. [governance/policy_control_plane.py](governance/policy_control_plane.py)
4. [trust_context.py](trust_context.py)
5. [safety](safety)

---

## Design Constraints

- Preserve offline-first operation and deterministic behavior where feasible.
- Prefer refusal or extractive fallback over unsupported synthesis.
- Do not introduce hidden network dependencies in core inference paths.
- Keep changes auditable and minimal.

---

## Validation

From repo root:

```bash
python -m pytest -q
```

Focused tests for recent governance/query changes:

```bash
python -m pytest tests/test_api_streaming.py tests/test_optional_enhancements.py tests/unit/test_policy_control_plane.py -q --no-cov
```
