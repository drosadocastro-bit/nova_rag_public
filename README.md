# NIC — Offline RAG for Safety-Critical Systems

**Reference implementation of an offline, air-gapped RAG architecture for safety-critical, human-on-the-loop systems.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Validated](https://img.shields.io/badge/Adversarial%20Tests-111%2F111%20passed-brightgreen.svg)](docs/evaluation/EVALUATION_SUMMARY.md)

---

## Purpose

NIC demonstrates how to build trustworthy AI assistants for environments where:
- **Network access is unavailable or prohibited** (air-gapped, remote, classified)
- **Incorrect information causes harm** (maintenance, medical, aviation, defense)
- **Auditability is mandatory** (regulated industries, compliance requirements)

This is not a product—it's a **reference architecture** showing that safety-aware, offline AI is achievable with open-source components.

---

## Intended Audience

| Role | Interest |
|------|----------|
| **System Safety Engineers** | Hallucination defenses, failure modes, human-on-the-loop design |
| **Security Reviewers** | Air-gap compliance, threat model, audit trail |
| **Program Managers** | Deployment feasibility in regulated environments |
| **AI/ML Engineers** | RAG architecture patterns for high-consequence domains |

---

## Key Properties

| Property | Implementation |
|----------|----------------|
| **Offline / Air-Gapped** | All models, embeddings, and indexes run locally. Zero external API calls. No telemetry. |
| **Safety-Oriented** | Multi-layer hallucination defenses: confidence gating, citation audit, extractive fallback. |
| **Human-on-the-Loop** | Advisory only—no direct actuation. Operator retains decision authority. |
| **Auditable** | Every query logged with question, answer, sources, confidence, and audit status. |
| **Reproducible** | Locked dependencies, versioned corpus, deterministic retrieval. |

---

## Claims → Evidence

| Claim | Evidence |
|-------|----------|
| **Operates fully offline** | Local LLM via Ollama, local embeddings, FAISS index on disk. No network calls in inference path. See [Deployment Guide](docs/deployment/AIR_GAPPED_DEPLOYMENT.md). |
| **Responses are grounded and auditable** | RAG pipeline with citation mechanism. All claims traced to source with page numbers. See [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md). |
| **Hallucination risks are mitigated** | Confidence gating (skip LLM if retrieval < 60%), citation audit, extractive fallback. 111 adversarial tests, 100% pass rate. See [Evaluation Summary](docs/evaluation/EVALUATION_SUMMARY.md). |
| **Suitable for safety-critical contexts** | Human-on-the-loop model, explicit uncertainty handling, abstention over confabulation. See [Safety Model](docs/safety/SAFETY_MODEL.md). |

---

## Documentation

| Document | Description |
|----------|-------------|
| [**System Architecture**](docs/architecture/SYSTEM_ARCHITECTURE.md) | Core design, data flow, component interactions |
| [**Safety Model**](docs/safety/SAFETY_MODEL.md) | Hallucination defenses, validation methodology |
| [**Safety-Critical Context**](docs/safety/SAFETY_CRITICAL_CONTEXT.md) | Use context, human-on-the-loop model, failure philosophy |
| [**Evaluation Summary**](docs/evaluation/EVALUATION_SUMMARY.md) | Test coverage, adversarial results, RAGAS scores |
| [**Deployment Guide**](docs/deployment/AIR_GAPPED_DEPLOYMENT.md) | Offline setup, air-gap deployment |

Additional technical documentation available in [`docs/`](docs/).

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/nic-public.git && cd nic-public
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Ollama with a local model
ollama pull llama3.2:8b

# Run NIC
python nova_flask_app.py
# → http://localhost:5000
```

---

## Repository Structure

```
├── README.md                 # This document
├── QUICKSTART.md            # Detailed setup instructions
├── nova_flask_app.py        # Main application
├── backend.py               # RAG pipeline
├── agents/                  # Query handlers
├── ollama/                  # Ollama Modelfiles for local LLMs
├── docs/
│   ├── architecture/        # System design
│   ├── safety/              # Safety validation
│   ├── evaluation/          # Test results
│   ├── deployment/          # Deployment guides
│   └── annex/               # Internal notes (development logs, templates)
├── governance/              # Policy files, test suites
└── data/                    # Corpus documents
```

---

## License

MIT License. See [LICENSE](LICENSE).

---

**NIC: Demonstrating that trustworthy, offline AI for safety-critical systems is achievable.**
