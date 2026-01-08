# NIC — Offline RAG for Safety-Critical Systems

**Reference implementation of an offline, air-gapped RAG architecture for safety-critical, human-on-the-loop systems.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Validated](https://img.shields.io/badge/Adversarial%20Tests-111%2F111%20passed-brightgreen.svg)](docs/evaluation/EVALUATION_SUMMARY.md)
[![Hybrid Retrieval](https://img.shields.io/badge/Retrieval-Hybrid%20(Vector+BM25)-purple.svg)](#hybrid-retrieval)

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
| **Hybrid Retrieval** | Vector similarity (FAISS) unioned with BM25 lexical search, then reranked and diversified (MMR). Toggle via NOVA_HYBRID_SEARCH. |

Why hybrid: improves recall for exact terms, part names, and diagnostic codes in safety‑critical manuals.

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

### Option 1: Docker (Recommended)

```bash
# Start all services with Docker Compose
docker-compose up -d

# Pull LLM models
docker exec -it nic-ollama ollama pull llama3.2:3b

# Access at http://localhost:5000
```

See [Docker Deployment Guide](docs/deployment/DOCKER_DEPLOYMENT.md) for details.

### Option 2: Local Installation

```bash
# Clone and install
git clone https://github.com/yourusername/nic-public.git && cd nic-public
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Ollama with a local model
ollama pull llama3.2:3b

# Run NIC
python nova_flask_app.py
# → http://localhost:5000
```

---

## Testing

Run comprehensive test suite:

```bash
# Install test dependencies (included in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

**Test Coverage:** 45+ unit tests, ~75% coverage

See [tests/README.md](tests/README.md) for details.

---

## How to Run

### Docker Deployment (Recommended)

```bash
docker-compose up -d
docker exec -it nic-ollama ollama pull llama3.2:3b
# Access at http://localhost:5000
```

### Local Installation

Minimal offline run steps:

```bash
pip install -r requirements.txt
ollama pull llama3.2:3b   # or: ollama run llama3.2:3b to verify
python nova_flask_app.py
```

See the [Documentation Index](docs/INDEX.md) for detailed guides.

---

## Production Deployment

### Week 1 Enhancements Implemented ✅

1. **Docker Support** - Production-ready containerization
   - Multi-stage Dockerfile
   - Docker Compose with Ollama
   - Air-gap deployment ready
   
2. **Resource Requirements** - Complete hardware/software specs
   - See [RESOURCE_REQUIREMENTS.md](docs/deployment/RESOURCE_REQUIREMENTS.md)

3. **Unit Tests** - 45+ tests, ~75% coverage
   - Pytest framework
   - See [tests/README.md](tests/README.md)

4. **Rate Limiting** - DoS protection
   - Configurable limits
   - 20 requests/minute on API endpoints

5. **Security Audit** - Automated scanning
   - Bandit code analysis
   - pip-audit dependency checks
   - See [SECURITY_AUDIT.md](docs/annex/SECURITY_AUDIT.md)

### Deployment Guides

- [Docker Deployment](docs/deployment/DOCKER_DEPLOYMENT.md)
- [Resource Requirements](docs/deployment/RESOURCE_REQUIREMENTS.md)
- [Air-Gapped Deployment](docs/deployment/AIR_GAPPED_DEPLOYMENT.md)
- [Configuration Guide](docs/deployment/CONFIGURATION.md)

---

## Hybrid Retrieval

Hybrid search combines vector similarity (FAISS) with lexical BM25 to improve recall for specific terminology, codes, and procedures. It is enabled by default.

**BM25 index is cached to disk** and automatically rebuilt when the corpus changes, eliminating startup overhead for large document sets.

- Enable/disable:

```powershell
# Windows PowerShell
$env:NOVA_HYBRID_SEARCH="1"   # enable (default)
python nova_flask_app.py

# Disable
$env:NOVA_HYBRID_SEARCH="0"
python nova_flask_app.py
```

- Tuning (optional):

```powershell
$env:NOVA_BM25_K1="1.5"   # term saturation (default 1.5)
$env:NOVA_BM25_B="0.75"   # length normalization (default 0.75)
$env:NOVA_BM25_CACHE="1"  # enable disk caching (default on)
```

This feature is suitable to highlight in the README for safety‑critical contexts; it makes retrieval more robust to exact terms and diagnostic codes. For architecture details, see the [Documentation Index](docs/INDEX.md).

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
