# NIC — Offline RAG for Safety-Critical Systems

Reference implementation for building an offline, air-gapped, human-on-the-loop RAG system with explicit safety controls and auditability.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/ci.yml)

---

## What NIC Is

NIC is designed for environments where:
- internet access is unavailable or prohibited,
- incorrect answers can cause harm,
- operator oversight and traceability are required.

Core properties:
- Offline-first / air-gapped operation (`FORCE_OFFLINE=1`)
- Human authority over all real-world actions
- Evidence-gated responses (confidence + grounding checks)
- Deterministic audit trail with tamper-evident integrity checks

---

## Quick Start (5 minutes)

### Option A: Docker

```bash
docker-compose up -d
```

Query endpoint:

```bash
curl -X POST http://localhost:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I troubleshoot STALO instability?"}'
```

### Option B: Local Python

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python backend.py
```

For complete setup guidance, use [QUICKSTART.md](QUICKSTART.md).

---

## Safety Operating Rules

- Keep `FORCE_OFFLINE=1` in regulated or air-gapped deployments.
- Treat retrieval as evidence gathering, not guaranteed truth.
- Prefer refusal or extractive fallback over unsupported synthesis.
- Keep approval and policy controls enabled in production.

Governance and policy flags: [docs/briefings/GOVERNANCE_POLICY_FLAGS_2026-02-21.md](docs/briefings/GOVERNANCE_POLICY_FLAGS_2026-02-21.md)

---

## Architecture at a Glance

NIC pipeline (simplified):
1. Input safety and intent checks
2. Domain-aware retrieval (vector + BM25)
3. Reranking and evidence selection
4. Generation (when allowed)
5. Post-generation grounding/quality gate
6. Response with citations + audit event logging

Deep architecture docs:
- [docs/architecture/SYSTEM_ARCHITECTURE.md](docs/architecture/SYSTEM_ARCHITECTURE.md)
- [docs/architecture/DATA_FLOW.md](docs/architecture/DATA_FLOW.md)
- [docs/architecture/THREAT_MODEL.md](docs/architecture/THREAT_MODEL.md)

---

## Choose Your Path

### Operators
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/runbooks](docs/runbooks)

### Developers
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/api/API_REFERENCE.md](docs/api/API_REFERENCE.md)
- [docs/INDEX.md](docs/INDEX.md)

### Safety / Governance Reviewers
- [docs/safety/SAFETY_MODEL.md](docs/safety/SAFETY_MODEL.md)
- [docs/safety/HALLUCINATION_DEFENSE.md](docs/safety/HALLUCINATION_DEFENSE.md)
- [docs/evaluation/EVALUATION_SUMMARY.md](docs/evaluation/EVALUATION_SUMMARY.md)
- [governance](governance)

### Deployment Engineers
- [docs/deployment/AIR_GAPPED_DEPLOYMENT.md](docs/deployment/AIR_GAPPED_DEPLOYMENT.md)
- [docs/deployment/CONFIGURATION.md](docs/deployment/CONFIGURATION.md)
- [Dockerfile](Dockerfile), [docker-compose.yml](docker-compose.yml)

---

## Frequently Used Commands

```bash
# run tests
python -m pytest -q

# run focused governance checks
python -m pytest tests/test_api_streaming.py tests/test_optional_enhancements.py tests/unit/test_policy_control_plane.py -q --no-cov

# audit chain integrity
python scripts/check_audit_integrity.py --db-path ./audit_trail.db --include-details
```

---

## Documentation Index

Start here for full documentation map: [docs/INDEX.md](docs/INDEX.md)

---

## License

MIT — see [LICENSE](LICENSE)
