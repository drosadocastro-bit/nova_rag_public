# NIC — Offline RAG for Safety-Critical Systems

**Reference implementation of an offline, air-gapped RAG architecture for safety-critical, human-on-the-loop systems.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Validated](https://img.shields.io/badge/Adversarial%20Tests-111%2F111%20passed-brightgreen.svg)](docs/evaluation/EVALUATION_SUMMARY.md)
[![Hybrid Retrieval](https://img.shields.io/badge/Retrieval-Hybrid%20(Vector+BM25)-purple.svg)](#hybrid-retrieval)
[![Load Tested](https://img.shields.io/badge/Load%20Tested-20%20users-blue)](docs/evaluation/LOAD_TEST_RESULTS.md)
[![CI](https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/ci.yml)

---

## CI

This repo uses two GitHub Actions workflows to keep quality and safety high:

- **CI**: Runs on push/PR to `main` and `develop`.
   - Matrix builds on Python 3.12 and 3.13
   - Installs deps, runs `pytest` for all tests
   - Lints with `ruff`, checks formatting, basic import checks
   - Security scanning with `pip-audit` and `bandit` (reports uploaded)
   - Documentation link validation for `docs/*` using `markdown-link-check`
   - See the workflow: https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/ci.yml

- **Nightly CI**: Runs nightly at 03:00 UTC and on manual dispatch.
   - Installs deps, lints with `ruff`
   - Executes unit tests and smoke tests with safe offline env flags
   - Uploads artifacts (logs, test outputs) for inspection
   - See the workflow: https://github.com/drosadocastro-bit/nova_rag_public/actions/workflows/nightly.yml

Status badges for both workflows are shown above.

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
| **Request Analytics** | Built-in request logging tracks queries, response times, model usage, and confidence scores. SQLite backend for trend analysis. |
| **Risk Assessment & Safety Triage** | Detects emergencies (fire, smoke, unconscious), critical system failures (brakes/steering), and fake parts; blocks unsafe requests and prioritizes life safety before retrieval/LLM. |
| **Injection Handling** | Hybrid "judge by intent, not syntax" approach: detects injection patterns, extracts core questions, assesses only clean content. Intent classifier blocks unsafe requests (e.g., disable ABS). See [Injection Handling Architecture](docs/INJECTION_HANDLING.md). |

Why hybrid: improves recall for exact terms, part names, and diagnostic codes in safety‑critical manuals.

---

## Claims → Evidence

| Claim | Evidence |
|-------|----------|
| **Operates fully offline** | Local LLM via Ollama, local embeddings, FAISS index on disk. No network calls in inference path. See [Deployment Guide](docs/deployment/AIR_GAPPED_DEPLOYMENT.md). |
| **Responses are grounded and auditable** | RAG pipeline with citation mechanism. All claims traced to source with page numbers. See [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md). |
| **Hallucination risks are mitigated** | Confidence gating (skip LLM if retrieval < 60%), citation audit, extractive fallback. 111 adversarial tests, 100% pass rate. See [Evaluation Summary](docs/evaluation/EVALUATION_SUMMARY.md). |
| **Suitable for safety-critical contexts** | Human-on-the-loop model, explicit uncertainty handling, abstention over confabulation, and risk assessment that elevates critical safety-system failures. See [Safety Model](docs/safety/SAFETY_MODEL.md). |

---

## Design Journey: From Prototype to Production

NIC evolved from a basic proof-of-concept to a production-grade safety-critical system. This section captures the architectural decisions, trade-offs, and lessons learned—valuable for anyone building similar systems.

### Evolution Timeline

| Phase | Focus | Key Achievement |
|-------|-------|-----------------|
| **Phase 1 (MVP)** | Basic retrieval + single LLM pass | Working end-to-end pipeline |
| **Phase 2 (Safety)** | Multi-layer defenses, evidence tracking | 111/111 adversarial tests passing |
| **Phase 2.5 (Multi-Domain)** | Domain-aware retrieval, cross-contamination prevention | 1,692 chunks across 5 domains with per-domain caps |
| **Phase 3 (Scalability)** | Incremental indexing, hot-reload, real corpus | Zero-downtime scaling: 3.3s per manual (34% faster than target) |
| **Phase 3.5 (Neural Advisory)** | Fine-tuned embeddings, anomaly detection | Neural advisors with deterministic safety |
| **Production Review (Jan 2026)** | Code quality hardening, validation rigor | 100% validated error handling |
| **Domain Isolation (Jan 2026)** | Cross-contamination elimination, OCR expansion | 0% contamination across 9 domains, 6,610 chunks |

### Key Architectural Decisions & Why

| Decision | Reasoning | Trade-off |
|----------|-----------|-----------|
| **Hybrid BM25 + Vector Search** | Improves recall on exact diagnostic codes, part numbers, procedures in safety manuals | ~200ms additional latency. Mitigated by BM25 disk caching. |
| **Pydantic Type Validation** | Catches malformed chunks before LLM sees them; early failure vs. silent errors | Developer overhead; replaced manual dict checking. Worth it. |
| **Evidence Chain Tracking** | Mandatory for audit trail in regulated environments; every routing decision logged | ~5% memory/logging overhead. Essential for compliance. |
| **Domain Caps & Filtering** | Prevents military vehicle manual from contaminating civilian queries | Extra retrieval + filtering stages. Mitigated by efficient keyword indexing. |
| **Confidence Gating (< 60%)** | Abstention over confabulation; better to say "I don't know" than guess in safety context | Reduced LLM usage (fewer responses). Intentional—safety > coverage. |

### Lessons Learned from CodeRabbit Review

**Why Structured Logging Matters**
- Early versions used `print()` for debugging
- Problem: Couldn't trace retrieval scores, reranking decisions, or latency bottlenecks
- Solution: Switched to hierarchical logging with structured fields (query_id, domain, scores, latency)
- Impact: Debugging retrieval pipeline reduced from hours to minutes

**Why Pydantic Validation Saved Us**
- Early code used manual `isinstance()` checks for retrieval results
- Problem: Silent failures when embedding API returned unexpected format
- Solution: Strict Pydantic schemas for `EmbeddingResult`, `RerankingScore`, `EvidenceChain`
- Impact: 7 data consistency bugs caught in testing that would have surfaced in production

**Why Granular Retry Logic is Non-Negotiable**
- Initial approach: Single try/except for embedding service calls
- Problem: Transient embedding API failures caused entire queries to fail
- Solution: Exponential backoff, circuit breaker, graceful fallback to keyword-only retrieval
- Impact: Improved availability from 98% to 99.7% under load

**Why Domain Caps Exist**
- Initially: Top-k retrieval without domain constraints
- Problem: Forklift manual (2,386 chunks) dominated results even for vehicle queries
- Solution: Max 3 chunks per domain, enforced before LLM sees results
- Impact: Cross-domain contamination reduced from 12% to 0.3%

**Why Domain-Aware Pre-Filtering Was Added (Jan 2026)**
- Problem: Even with domain caps, 19.2% of queries showed cross-contamination
- Root cause: FAISS retrieval happened before domain filtering, pulling wrong-domain chunks
- Solution: Over-fetch 3x candidates, detect domain intent early, prioritize 80% from target domain
- Impact: Cross-contamination reduced from 19.2% to **0%** across all 9 domains

**Cross-Contamination Before/After (Jan 2026)**
| Metric | Before | After |
|--------|--------|-------|
| Contamination rate | 19.2% (5/26 tests) | **0%** (0/26 tests) |
| vehicle_civilian issues | 3/4 tests contaminated | **0/4** tests contaminated |
| vehicle_military issues | 2/3 tests contaminated | **0/3** tests contaminated |
| Domain accuracy | ~65% from target domain | **80%+** from target domain |

---

## Documentation

| Document | Description |
|----------|-------------|
| [**System Architecture**](docs/architecture/SYSTEM_ARCHITECTURE.md) | Core design, data flow, component interactions |
| [**Architecture Overview**](docs/ARCHITECTURE.md) | High-level map of modules, safety layers, retrieval cache, and key config flags |
| [**Safety Model**](docs/safety/SAFETY_MODEL.md) | Hallucination defenses, validation methodology |
| [**Safety-Critical Context**](docs/safety/SAFETY_CRITICAL_CONTEXT.md) | Use context, human-on-the-loop model, failure philosophy |
| [**Evaluation Summary**](docs/evaluation/EVALUATION_SUMMARY.md) | Test coverage, adversarial results, RAGAS scores |
| [**Load Test Results**](docs/evaluation/LOAD_TEST_RESULTS.md) | Performance benchmarks, scaling recommendations |
| [**Deployment Guide**](docs/deployment/AIR_GAPPED_DEPLOYMENT.md) | Offline setup, air-gap deployment |
| [**BM25 Caching**](docs/architecture/BM25_CACHING.md) | Cache lifecycle, invalidation, troubleshooting |
| [**Injection Handling**](docs/INJECTION_HANDLING.md) | Hybrid logic for detecting and neutralizing prompt injection attempts |

Additional technical documentation available in [`docs/`](docs/).

### Safety Test Results

| Category | Status | Evidence |
|----------|--------|----------|
| **Injection Handling** | ✅ INJECTION-002 PASS | Correctly refuses unsafe intent (disable ABS) after stripping translation wrapper |
| **Injection Detection** | ✅ Logic Verified | Server logs confirm extraction of core question from injection syntax |
| **Core Safety Tests** | ✅ 31 tests covered | Precision, ambiguity, boundary, hallucination, real-world, and safety cases documented in [Adversarial Test Results](docs/evaluation/EVALUATION_SUMMARY.md) |

See [Injection Test Validation](INJECTION_TEST_VALIDATION.md) for detailed test results and methodology.

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
git clone https://github.com/drosadocastro-bit/nic-public.git && cd nic-public
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Start Ollama with a local model
ollama pull llama3.2:3b

# Run NIC
python nova_flask_app.py
# → http://localhost:5000
```

---

## LLM Models In Use

Quick start uses a small model for speed, but production uses the following:

- **Fireball Llama 3.2 8B** (general + procedural)
- **Qwen 2.5 Coder 14B** (deep reasoning / code-heavy queries)

To load the production models with Ollama:

```bash
ollama pull llama3.2:8b
ollama pull qwen2.5-coder:14b
```

Set the model names explicitly if you use custom tags (e.g., fireball builds):

```bash
export NOVA_LLM_LLAMA="llama3.2:8b"   # or your fireball tag
export NOVA_LLM_OSS="qwen2.5-coder:14b"
```

See [ollama/README.md](ollama/README.md) for Modelfiles and offline registration.

---

## Corpus & Domain Coverage

Current multi-domain corpus for safety-critical technical retrieval:

| Domain | Chunks | % | Source Type |
|--------|--------|---|-------------|
| forklift | 2,386 | 36.1% | TM-10-3930-673-20-1 (Military Technical Manual) |
| vehicle_military | 1,836 | 27.8% | TM9-802-Declassified (WWII Ford GPW/GMC) |
| aerospace | 573 | 8.7% | Space Shuttle Operator's Manual (OCR) |
| nuclear | 494 | 7.5% | Reactor Physics & Theory |
| radar | 464 | 7.0% | WXR-2100 Weather Radar Operators Guide |
| vehicle (civilian) | 359 | 5.4% | Ford Model T Manual 1919 (OCR), VW GTI |
| electronics | 231 | 3.5% | PLC/VisionFive2, Raspberry Pi GPIO |
| medical | 152 | 2.3% | MRI Technical Operations Manual |
| hvac | 115 | 1.7% | Carrier HVAC Systems |
| **Total** | **6,610** | **100%** | |

**Status:** 6,610 chunks indexed (66% of 10k target) — OCR enabled for scanned documents

### Adding More Documents

Place PDFs in the appropriate `data/<domain>/` folder and run ingestion:

```bash
python ingest_multi_domain.py
```

### OCR for Scanned PDFs

Some historical documents (Space Shuttle Operator's Manual, Ford Model T Manual) are scanned images. To extract text:

1. Install Tesseract OCR:
   - **Windows:** Download from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
   - **Linux:** `sudo apt install tesseract-ocr`
   - **macOS:** `brew install tesseract`

2. Install Poppler (for pdf2image):
   - **Windows:** Download from [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases)
   - **Linux:** `sudo apt install poppler-utils`
   - **macOS:** `brew install poppler`

3. Re-run ingestion - OCR will automatically process scanned PDFs.

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

### Production Readiness: Week 1 & 2 Complete ✅

**Week 1 Enhancements:**
1. ✅ **Docker Support** - Production containerization
   - Multi-stage Dockerfile, docker-compose with Ollama
   - Air-gap deployment ready
   - [Docker Deployment Guide](docs/deployment/DOCKER_DEPLOYMENT.md)
   
2. ✅ **Resource Requirements** - Complete hardware/software specs
   - Min/Recommended/High-performance configs
   - [RESOURCE_REQUIREMENTS.md](docs/deployment/RESOURCE_REQUIREMENTS.md)

3. ✅ **Unit Tests** - 45+ tests, 75%+ coverage
   - Pytest framework with organized structure
   - Run: `make test` or `pytest --cov`
   - [tests/README.md](tests/README.md)

4. ✅ **Rate Limiting** - DoS protection
   - Configurable limits (20/min API, 60/min status)
   - Flask-Limiter integration

5. ✅ **Security Audit** - Automated scanning
   - Bandit, pip-audit, Safety in CI/CD
   - [SECURITY_AUDIT.md](docs/annex/SECURITY_AUDIT.md)

**Week 2 Enhancements:**
6. ✅ **Test Organization** - Unit/integration/fixtures structure
7. ✅ **Code Coverage** - Enhanced reporting with detailed metrics
8. ✅ **Performance Documentation** - Complete benchmarking guide
   - [PERFORMANCE_GUIDE.md](docs/evaluation/PERFORMANCE_GUIDE.md)
9. ✅ **Monitoring** - Metrics endpoint (`/metrics`), uptime tracking
10. ✅ **Developer Tools** - CONTRIBUTING.md, Makefile, organized workflow

### Quick Commands

```bash
# Development
make dev-setup          # Complete dev environment setup
make test               # Run unit tests
make coverage           # Test with coverage report
make lint               # Lint code
make format             # Format code
make security           # Run security scans

# Docker
make docker-build       # Build images
make docker-up          # Start services
make docker-logs        # View logs

# Validation
make validate           # Quick validation
make ci-local           # Simulate CI pipeline
```

### Deployment Guides

- [Docker Deployment](docs/deployment/DOCKER_DEPLOYMENT.md) - Container setup
- [Resource Requirements](docs/deployment/RESOURCE_REQUIREMENTS.md) - Hardware sizing
- [Performance Guide](docs/evaluation/PERFORMANCE_GUIDE.md) - Benchmarks & tuning
- [Air-Gapped Deployment](docs/deployment/AIR_GAPPED_DEPLOYMENT.md) - Offline setup
- [Configuration Guide](docs/deployment/CONFIGURATION.md) - Environment variables
- [Contributing Guide](CONTRIBUTING.md) - Development workflow

---

## Phase 2: Safety-Hardened Retrieval

Building on the MVP, **Phase 2** hardens the pipeline for safety-critical use: it prioritizes abstention over confabulation, makes failures observable, and keeps retrieval deterministic.

### What's New

**1. Multi-Layer Safety Controls**
- Confidence gating (skip LLM if retrieval quality < threshold)
- Citation audit plus extractive fallback for low-confidence answers
- Risk assessment blocks unsafe intents before retrieval

**2. Reliability & Error Handling**
- Granular retries with exponential backoff for embeddings and rerankers
- Circuit-breaker fallback to BM25-only when vector stack is degraded
- Structured error reporting for pipeline stages

**3. Observability & Logging**
- Structured logs with `query_id`, domain, scores, and latencies
- Evidence logging for router → retrieval → rerank decisions

**4. Deterministic Caching**
- Versioned FAISS/BM25 caches with hash-based invalidation
- Rebuilds automatically when corpus, model, or chunking changes

**5. Validated Safety Behavior**
- 111/111 adversarial tests passing with confidence gating and audit trail

### Quick Configuration (Phase 2 defaults)
```bash
export NOVA_CONFIDENCE_THRESHOLD=0.60     # Abstain below this
export NOVA_EXTRACTIVE_FALLBACK=1          # Use extractive answers when low confidence
export NOVA_EVIDENCE_TRACKING=1            # Log router/retrieval/rerank evidence
export NOVA_RETRIEVAL_K=12                 # Retrieve 12 candidates before rerank
python nova_flask_app.py
```

### Safety State Machine (Phase 2/2.5)

```
Input (Injection/Risk Check)
  ├─ block → Unsafe/Injection response
  └─ pass
        ↓
Retrieval (Hybrid + Domain Filter)
        ↓
Validation (score ≥ 0.60)
  ├─ fail → Abstain ("I don't know") or Extractive Fallback
  └─ pass
        ↓
Generation (Grounded answer + citations)
        ↓
Audit (Citations verified; evidence logged)
```

Kill switches: injection/risk block, low-score abstain, and circuit-breaker to BM25-only if vectors fail. Evidence is captured at each state for auditability.

---

## Phase 2.5: Enhanced Multi-Domain Retrieval

Building on the core NIC architecture, **Phase 2.5** adds intelligent domain-aware features for improved accuracy in safety-critical multi-domain scenarios.

### What's New

**1. Multi-Domain Indexing with Domain Tagging**
- Automatically detects and tags documents by domain (vehicle, military equipment, HVAC, radar, forklift)
- Prevents contamination across domains during retrieval
- Maintains domain-specific keyword indices for faster routing

**2. HTML Document Support**
- Extended ingestion pipeline now handles HTML manuals (e.g., Volkswagen GTI HTML documentation)
- Recursive subdirectory scanning for organized document collections
- Uses BeautifulSoup4 for robust HTML parsing with script/style cleanup

**3. Evidence Chain Tracking**
- Complete audit trail of multi-stage retrieval pipeline:
  - Router stage: domain inference and filtering
  - GAR (Glossary Augmented Retrieval): query expansion effectiveness
  - Reranking: score distributions and top candidates
  - Final Selection: domain distribution and cap enforcement
- JSON-serializable evidence chains for debugging contamination

**4. Domain Caps for Diversity**
- Per-domain chunk limits enforce balanced results across domains
- Example: max 3 chunks per domain prevents forklift manual from overshadowing vehicle queries
- Configurable via `NOVA_MAX_CHUNKS_PER_DOMAIN`

**5. Adaptive Keyword Refinement**
- Data-driven keyword optimization based on clustering analysis
- Identifies keyword overlaps across domains
- Validates improvements with cross-contamination benchmarks

**6. Domain Intent Classifier (Jan 2026)**
- Vocabulary-based domain detection with confidence scoring
- Enhanced vocabularies for 9 domains (aerospace, nuclear, medical, electronics added)
- Domain boost factor (0.25) applied to matching-domain results
- Configurable via `NOVA_DOMAIN_BOOST` and `NOVA_DOMAIN_BOOST_FACTOR`

**7. Domain-Aware Pre-Filtering (Jan 2026)**
- Over-fetches 3x candidates when domain detected with ≥60% confidence
- Prioritizes 80% of results from target domain before reranking
- Eliminates cross-contamination while maintaining diversity
- Result: **0% cross-contamination** across 26 test cases

**8. Intelligent Domain Router**
- Combines zero-shot classification with keyword heuristics
- Falls back gracefully when models unavailable
- Records router evidence for every query

### How It Works

```
Query → Router (domain inference) → GAR (expansion) → Retrieval (hybrid search)
         ↓                          ↓
         [Evidence]          → Reranking → Domain Caps → Final Selection
                                             ↓
                                          [Evidence Chain]
```

**Example Configuration:**
```bash
# Enable all Phase 2.5 features
export NOVA_EVIDENCE_TRACKING=1              # Track evidence chain
export NOVA_MAX_CHUNKS_PER_DOMAIN=3          # Max 3 chunks per domain
export NOVA_ROUTER_FILTERING=1               # Use domain router
export NOVA_DOMAIN_ZS_MODEL="facebook/bart-large-mnli"  # Zero-shot classifier

python nova_flask_app.py
```

**Query Flow with Evidence:**
```python
from core.retrieval.retrieval_engine_phase2 import retrieve_with_phase2

results = retrieve_with_phase2(
    query="How do I check tire pressure?",
    k=12,                              # Retrieve 12 candidates
    top_n=6,                           # Return top 6
    enable_evidence_tracking=True,     # Capture evidence chain
    enable_domain_caps=True,           # Apply per-domain limits
    enable_router_filtering=True       # Use domain router
)

# Access evidence if available
if results.evidence:
    print(results.evidence.summary())
    # Shows router decisions, GAR expansion ratio, reranking scores, 
    # domain distribution, and which domains were capped
```

### Benefits for Safety-Critical Domains

- **Reduced Cross-Contamination**: Domain caps prevent military vehicle manual from interfering with civilian vehicle queries
- **Auditability**: Evidence chain documents every routing and filtering decision for compliance
- **Precision**: Keyword refinement targets domain-specific terminology (e.g., "hydraulic" for forklifts vs "transmission" for vehicles)
- **Graceful Degradation**: Falls back to keyword-only routing if zero-shot classifier unavailable
- **Extensibility**: Easy to add new domains without retraining

### Current Multi-Domain Index (Jan 2026)

| Domain | Chunks | % | Description |
|--------|--------|---|-------------|
| forklift | 2,386 | 36.1% | TM-10-3930-673-20-1 Military Technical Manual |
| vehicle_military | 1,836 | 27.8% | TM9-802-Declassified WWII Ford GPW/GMC |
| aerospace | 573 | 8.7% | Space Shuttle Operator's Manual (OCR) |
| nuclear | 494 | 7.5% | Reactor Physics & Theory |
| radar | 464 | 7.0% | WXR-2100 Weather Radar Operators Guide |
| vehicle (civilian) | 359 | 5.4% | Ford Model T Manual 1919 (OCR), VW GTI |
| electronics | 231 | 3.5% | PLC/VisionFive2, Raspberry Pi GPIO |
| medical | 152 | 2.3% | MRI Technical Operations Manual |
| hvac | 115 | 1.7% | Carrier HVAC Systems |
| **Total** | **6,610** | **100%** | 9 domains indexed |

For validation, see [validate_phase25.py](validate_phase25.py) and the [Phase 2.5 Architecture](docs/architecture/PHASE2_5_ARCHITECTURE.md) document.

---

## Phase 3: Scalability & Real-World Corpus ✅ COMPLETE

Phase 3 delivered **zero-downtime incremental indexing** and **production-grade corpus scaling**—enabling real-world deployment without compromising safety guarantees.

### What Was Built

**1. Incremental Indexing System**
- File-hash tracking (`corpus_manifest.py`) - 420 lines, 45 tests
- Append-only FAISS updates (`incremental_faiss.py`) - 320 lines, 20 tests
- Incremental BM25 expansion (`incremental_bm25.py`) - 280 lines, 25 tests
- Hot-reload API endpoint (`hot_reload.py`) - 400 lines, 15 tests
- **Result:** Add manuals without downtime, atomic updates, full auditability

**2. Real Corpus Integration**
- Researched 7 public-domain sources (TM-9-803, Model T, Arduino, RPi, OpenPLC, NASA, NIST)
- Download automation scripts (220 + 120 + 340 lines)
- Validation framework with SHA-256 integrity checks
- Import automation with domain categorization
- **Result:** Production-ready corpus pipeline for safety-critical technical docs

**3. End-to-End Validation**
- 9-step hot-reload test workflow (`test_hot_reload_ingestion.py`) - 340 lines
- Success criteria validation: 1,000+ chunks, <5s per manual, zero degradation, no restart
- **Result:** All criteria exceeded (3.3s per manual = 34% faster than target)

### Performance Results

| Metric | Target | Actual | Improvement |
|--------|--------|--------|-------------|
| Single manual | <5s | 3.3s | 34% faster |
| 10 manuals | <30s | 22s | 27% faster |
| 100 manuals | <5min | 185s | 38% faster |

### Key Design Decisions

- **Monotonic Chunk IDs:** Never reuse IDs even after deletion (prevents FAISS collision)
- **BM25 Rebuild Strategy:** Rebuild entire index on corpus change (deterministic, fast with caching)
- **FAISS Append-Only:** Add new vectors without touching existing (stability + safety)
- **Backup-Before-Modify:** Atomic updates with rollback capability
- **Atomic Updates:** All-or-nothing index operations (no partial states)

**Total Delivered:** 5,780 lines (1,620 production + 600 tests + 680 scripts + 2,880 docs) across 20+ files

For complete details, see [Phase 3 Completion Documentation](docs/roadmap/PHASE3_COMPLETE.md).

---

## Phase 3.5: Neural Advisory Layer 🚀 IN PROGRESS

Phase 3.5 introduces **neural networks as advisors**, not decision-makers—improving quality without breaking determinism or safety guarantees. NNs suggest and enhance, but deterministic rules remain authoritative.

### Implementation Progress

| Task | Status | Deliverable |
|------|--------|-------------|
| Task 1 | ✅ DONE | Updated README, Phase 3 marked complete |
| Task 2 | ✅ DONE | [Phase 3.5 Roadmap](docs/roadmap/PHASE3_5_ROADMAP.md) |
| Task 3 | ✅ DONE | [Fine-tuning design doc](docs/roadmap/TASK3_FINETUNING_DESIGN.md) |
| Task 4 | ✅ DONE | [Anomaly detection design](docs/roadmap/TASK4_ANOMALY_DETECTION_DESIGN.md) |
| Task 5 | ✅ DONE | Compliance reporting design |
| Task 6 | ✅ DONE | [Training data generator](scripts/generate_finetuning_data_fast.py) - **4,010 pairs generated** |
| Task 7 | ✅ DONE | [Fine-tuning script](scripts/finetune_embeddings_v2.py) - **2 epochs trained, tested, production ready** |
| Task 8 | 🔄 NEXT | Anomaly detection training |
| Task 9 | 🔄 NEXT | Integration & deployment |
| Task 10 | 🔄 NEXT | End-to-end validation |

**Task 6 Complete:** Generated 4,010 training pairs across 6 industrial domains (vehicle, forklift, radar, hvac, electronics, civilian). Multi-format support (TXT, PDF, HTML) with robust error handling. See [Task 6 Summary](docs/roadmap/TASK6_COMPLETION_SUMMARY.md).

**Task 7 Complete:** Fine-tuning script created and executed (267 lines optimized). Trained on 4,010 pairs for 2 epochs, final loss 1.2498. Model outputs to `models/nic-embeddings-v1.0/` (88.7 MB). All tests passed: 6/6 domain queries encoded, batch processing verified, numerical stability confirmed. See [Task 7 Completion Summary](docs/roadmap/TASK7_COMPLETION_SUMMARY.md).

### Planned Features

**1. Domain-Specific Fine-Tuning** (Task 7 - ✅ COMPLETE)
- **Result:** Fine-tuned model deployed to `models/nic-embeddings-v1.0/`
- **Approach:** 
  - Fine-tuned `sentence-transformers/all-MiniLM-L6-v2` on 4,010 domain pairs
  - Froze bottom 10/12 transformer layers, trained only top 2 blocks
  - Used MultipleNegativesRankingLoss for contrastive learning
  - Completed 2 epochs, final loss 1.2498
- **Validation:** All tests passed—batch encoding, numerical stability, domain queries
- **Metrics:** 384-dim embeddings, 88.7 MB model weights, production ready
- **Safety:** Advisory only—BM25 fallback if embeddings degrade

**2. Neural Anomaly Detection** (Task 8 - Next)
- **Goal:** Flag suspicious query patterns for human review
- **Approach:**
  - Train lightweight autoencoder on normal query distributions
  - Score queries for anomalies (e.g., probing, reconnaissance)
  - Log anomaly scores; **never auto-block**
- **Output:** Anomaly score in evidence chain for offline analysis
- **Impact:** Early warning system for security teams
- **Safety:** Logged only—deterministic rules still handle blocking

**3. Compliance Reporting** (Task 5 - Design Done)
- **Goal:** Auto-generate audit trails for regulatory review
- **Output Format:** JSON/PDF reports with:
  - Session ID, timestamp, operator
  - Query + grounded answer + source citations
  - Confidence scores, safety checks passed, anomaly scores
  - Tamper-evident signatures (SHA-256)
- **Impact:** Reduces audit preparation from days to minutes
- **Status:** Extends existing evidence tracking

### Design Principles

**Neural Networks as Advisors, Not Arbiters:**
- **Advisory:** NNs suggest, log, and enhance—but never override safety rules
- **Deterministic Core:** Rule-based safety checks remain authoritative
- **Graceful Degradation:** If NN unavailable, system works (rules + BM25)
- **Explainability:** NN predictions logged with confidence scores for audit
- **Versioning:** Model weights treated as immutable, versioned artifacts

**Architecture:**
```
Query → NN Anomaly Score (logged)
     ↓
     Rule-Based Safety Check (deterministic, blocking)
     ↓
     NN Fine-Tuned Embeddings (with BM25 fallback)
     ↓
     Deterministic Retrieval + Evidence Logging
```

**Why Phase 3.5 (Not Phase 3):**
- Phase 3 focuses on proven, low-risk scalability
- Phase 3.5 explores ML enhancements without compromising safety
- Allows NIC to remain certifiable while experimenting with quality improvements

**Full Implementation Status:** See [Phase 3.5 Roadmap](docs/roadmap/PHASE3_5_ROADMAP.md) for detailed task breakdown, architecture, and integration steps.

---

## Domain Isolation Milestone ✅ COMPLETE (Jan 2026)

Building on Phase 2.5's multi-domain foundation, **Domain Isolation** achieved **0% cross-contamination** across all 9 domains through intelligent pre-filtering and enhanced vocabulary detection.

### The Problem

Even with domain caps and GAR expansion, the system still showed cross-contamination issues:
- **19.2% of queries** returned results from wrong domains
- Military vehicle queries pulled forklift content (shared mechanical terminology)
- Civilian vehicle queries confused with military content

### The Solution

**1. Domain Intent Classifier**
- Vocabulary-based detection with confidence scoring (0.0–1.0)
- 9 domain vocabularies with domain-specific terminology:
  - `vehicle`: Model T, VW GTI, hand crank, magneto, civilian terms
  - `vehicle_military`: TM9-802, GPW, Willys, ordnance, war department
  - `forklift`: mast, forks, lift capacity, warehouse
  - `aerospace`: shuttle, orbiter, thermal protection, NASA
  - `nuclear`: reactor, criticality, neutron flux, control rods
  - `medical`: MRI, magnetic resonance, contraindication
  - `electronics`: GPIO, Raspberry Pi, PLC, ladder logic
  - `hvac`: thermostat, refrigerant, R-410a, compressor
  - `radar`: weather radar, reflectivity, doppler, azimuth

**2. Domain-Aware Pre-Filtering**
- Detects domain intent early (before FAISS search)
- Over-fetches 3x candidates when confidence ≥60%
- Prioritizes 80% from target domain, 20% diversity
- Applies domain boost (+0.25) to matching-domain scores

**3. Fixed Domain Tagging**
- Corrected ingestion bug where TM9-802 was tagged as "forklift"
- Folder-based domain assignment is now authoritative
- Proper separation: vehicle_military (1,836 chunks) vs vehicle (359 chunks)

### Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Cross-contamination rate | 19.2% | **0%** | 100% reduction |
| Tests with issues | 5/26 | **0/26** | All passing |
| vehicle_civilian accuracy | 1/4 tests | **4/4 tests** | 75% → 100% |
| vehicle_military accuracy | 1/3 tests | **3/3 tests** | 33% → 100% |
| Domain accuracy per query | ~65% | **80%+** | 15%+ improvement |

### Configuration

```bash
# Enable domain-aware retrieval (all enabled by default)
export NOVA_DOMAIN_BOOST=1                    # Enable domain boosting
export NOVA_DOMAIN_BOOST_FACTOR=0.25          # Boost factor for matching domain
export NOVA_GAR_ENABLED=1                     # Glossary Augmented Retrieval

python nova_flask_app.py
```

### Key Files Changed

- `core/retrieval/retrieval_engine.py`: Domain intent classifier, pre-filtering, boost logic
- `ingest_multi_domain.py`: Fixed domain tagging to use folder as authoritative source
- `data/automotive_glossary.json`: Extended with 9 domain vocabularies
- `test_cross_contamination.py`: 26-test suite covering all domains

---

## Hybrid Retrieval

Hybrid search combines vector similarity (FAISS) with lexical BM25 to improve recall for specific terminology, codes, and procedures. It is enabled by default.

**BM25 index is cached to disk** and automatically rebuilt when the corpus changes, eliminating startup overhead for large document sets. See [BM25 Caching Architecture](docs/architecture/BM25_CACHING.md) for details on cache lifecycle and invalidation.

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

## Analytics & Monitoring

NIC includes built-in request analytics for understanding usage patterns and system performance:

```bash
# View analytics summary (last 7 days)
curl http://localhost:5000/api/analytics

# Recent requests
curl http://localhost:5000/api/analytics/recent?limit=50

# Performance trends
curl http://localhost:5000/api/analytics/trends?days=30
```

**Tracked metrics:**
- Query patterns and popular searches
- Response times (avg, p95, p99)
- Model usage breakdown
- Confidence score distributions
- Error rates

Analytics data is stored locally in `vector_db/analytics.db` (SQLite). All data stays on your infrastructure—no external telemetry.

### Synthetic Test Diagrams

For testing vision-aware retrieval, generate synthetic vehicle diagrams:

```bash
python generate_synthetic_diagrams.py
```

Generates 4 test diagrams in `data/diagrams/`:
- Engine diagnostic flowchart
- Brake system components
- Cooling system flow
- Electrical system wiring

These diagrams exercise the vision reranker without requiring real manual scans.

---

## 🗄️ Cache System

Nova uses **versioned indices** that automatically rebuild when: 
- ✅ Embedding model changes
- ✅ Document corpus updates
- ✅ BM25 parameters modified
- ✅ Chunking strategy changes

Version metadata is tracked in git (`cache/*_version.json`).  
Binary indices build automatically on first run.

See [docs/CACHE_ARCHITECTURE.md](docs/CACHE_ARCHITECTURE.md) for details.

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

## Common Pitfalls & How to Avoid Them

This section documents real problems encountered during development and deployment. Learn from them:

### 1. CHUNK_OVERLAP Too Small

**Problem:** Diagnostic procedures split across chunk boundaries; LLM sees incomplete steps or context loss at transitions.

**Symptom:** Safety-critical instructions appear incomplete in responses; retrieval scores fluctuate at boundaries.

**Fix:** Set `NOVA_CHUNK_OVERLAP` appropriately for your domain:
```bash
# For technical manuals (recommended)
export NOVA_CHUNK_OVERLAP=512

# For dense safety documentation
export NOVA_CHUNK_OVERLAP=1024

# For general text
export NOVA_CHUNK_OVERLAP=256
```

**Why:** Average safety procedures span 200-400 tokens. Overlap prevents semantic boundaries from splitting instructions mid-sentence.

### 2. Skipping Domain Caps

**Problem:** Largest domain (e.g., forklift manual: 986 chunks) dominates retrieval even for unrelated queries.

**Symptom:** Vehicle queries return forklift procedures; cross-domain contamination > 5%.

**Fix:** Enable domain caps:
```bash
export NOVA_ROUTER_FILTERING=1
export NOVA_MAX_CHUNKS_PER_DOMAIN=3
```

**Why:** Without caps, top-k retrieval favors high-volume domains. Domain caps enforce diversity.

### 3. Confidence Gating Set Too High

**Problem:** System refuses to answer valid queries because retrieval score barely misses threshold.

**Symptom:** Valid queries return "I don't have information" even though corpus contains answer.

**Fix:** Tune confidence gate based on your retrieval quality:
```bash
# Conservative (safety priority)
export NOVA_CONFIDENCE_THRESHOLD=0.70

# Balanced (recommended)
export NOVA_CONFIDENCE_THRESHOLD=0.60

# Permissive (higher coverage, more hallucination risk)
export NOVA_CONFIDENCE_THRESHOLD=0.50
```

**Why:** Threshold should reflect your retrieval pipeline's quality. Test with your corpus before production.

### 4. BM25 Cache Not Enabled

**Problem:** Startup takes 10+ minutes with large corpus; every restart rebuilds index from scratch.

**Symptom:** Server initialization hangs; production deployments timeout.

**Fix:** Verify BM25 caching is enabled:
```bash
export NOVA_BM25_CACHE=1  # Default: ON
export NOVA_CACHE_DIR=./vector_db/bm25_cache
```

**Why:** BM25 index is deterministic and expensive to build. Caching recovers on every subsequent startup in <1 second.

### 5. Incompatible Embedding Model Dimensions

**Problem:** Switching embedding models crashes with dimension mismatch; FAISS index expects 384 dims, new model produces 768.

**Symptom:** Runtime error: "Index size mismatch"; retrieval fails immediately.

**Fix:** Clear cache when switching models:
```bash
# Change embedding model
export NOVA_EMBEDDING_MODEL="jinaai/jina-embeddings-v3"

# Clear old index
rm -rf vector_db/faiss_index*
rm -rf vector_db/*_version.json

# Rebuild on next startup
python nova_flask_app.py
```

**Why:** FAISS indices are dimension-specific. Stale indices with wrong dimensions cause hard failures.

### 6. Not Enabling Evidence Tracking in Production

**Problem:** Retrieval pipeline returns answers but you can't debug why a query failed or where contamination came from.

**Symptom:** Mysterious low scores; no visibility into router decisions or reranking steps.

**Fix:** Enable evidence tracking:
```bash
export NOVA_EVIDENCE_TRACKING=1
```

**Why:** Evidence chains are JSON-serializable and logged. Minimal overhead (<5%) for enormous debugging value.

### 7. HTML Tag Stripping Disabled (Phase 2.5 Ingestion)

**Problem:** Raw HTML (scripts/divs/styles) bloats token usage and pollutes embeddings, hurting recall.

**Symptom:** Retrieval returns irrelevant boilerplate (navigation, headers) instead of procedures.

**Fix:** Ensure HTML cleaning is enabled during ingestion:
```bash
export NOVA_HTML_CLEAN=1          # Strip script/style/nav tags
export NOVA_HTML_STRIP_COMMENTS=1 # Remove HTML comments
```

**Why:** Token budget is precious; embeddings should represent instructions, not layout chrome. Stripping tags improves recall and reduces cost.

---

## Troubleshooting Guide

### Symptom: High Latency (> 500ms per query)

**Diagnosis Steps:**
1. Check if BM25 caching is enabled: `ls vector_db/bm25_cache`
2. Verify hybrid search isn't bottlenecked: `export NOVA_HYBRID_SEARCH=0` and retest
3. Inspect log for reranking time: grep "rerank_latency" in server logs

**Solutions (in order of impact):**
- Enable BM25 cache (if not already): `export NOVA_BM25_CACHE=1`
- Reduce retrieval K: `export NOVA_RETRIEVAL_K=5` (from default 12)
- Disable vision reranker if unused: `export NOVA_USE_VISION_RERANKER=0`
- Profile with `NOVA_LOG_LEVEL=DEBUG` to identify bottleneck

### Symptom: Low Retrieval Scores (< 0.55)

**Diagnosis Steps:**
1. Verify corpus is loaded: Check `vector_db/` directory exists and has embeddings
2. Inspect query with evidence tracking: `export NOVA_EVIDENCE_TRACKING=1`
3. Check domain router: Is query being routed to correct domain?

**Solutions:**
- Enable query expansion (GAR): `export NOVA_ENABLE_GAR=1`
- Verify chunking strategy: Large chunks (> 1000 tokens) dilute scores
- Check embedding model quality: Ensure `NOVA_EMBEDDING_MODEL` is production-grade
- Manually test retrieval: `python test_retrieval.py --query "your test query"`

### Symptom: Cross-Domain Contamination (wrong domain in results)

**Diagnosis Steps:**
1. Enable domain router: `export NOVA_ROUTER_FILTERING=1`
2. Enable evidence tracking: `export NOVA_EVIDENCE_TRACKING=1`
3. Check domain caps: `export NOVA_MAX_CHUNKS_PER_DOMAIN=3`

**Solutions:**
- Verify domain tags are assigned: `python scripts/validate_domain_tags.py`
- Reduce domain cap if still contaminated: `export NOVA_MAX_CHUNKS_PER_DOMAIN=2`
- Inspect router evidence: Check logs for domain inference decisions
- Run contamination benchmark: `python edge_cases_regression.py --test contamination`

### Symptom: Out of Memory (OOM) During Indexing

**Diagnosis Steps:**
1. Check chunk count: `wc -l vector_db/chunks.json`
2. Verify embedding model size: Large models (>1GB) + large corpus = memory spike
3. Monitor during indexing: `watch -n 1 free -h`

**Solutions:**
- Reduce chunk size: `export NOVA_CHUNK_SIZE=512` (from 1024)
- Use smaller embedding model: `export NOVA_EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"`
- Enable streaming mode: `export NOVA_STREAMING_INDEXING=1`
- Split corpus: Process in batches with `python ingest_vehicle_manual.py --batch-size 100`

### Symptom: Stale Results (corpus was updated but old results returned)

**Diagnosis Steps:**
1. Check cache version: `cat vector_db/faiss_version.json`
2. Verify timestamp: Was it updated after corpus ingestion?

**Solutions:**
- Force cache invalidation: `rm -rf vector_db/faiss_index*`
- Re-index manually: `python scripts/rebuild_indices.py`
- Verify automatic invalidation trigger: Check if corpus files newer than index
- Enable verbose logging: `export NOVA_LOG_LEVEL=DEBUG` to trace cache hits

---

## License


MIT License. See [LICENSE](LICENSE).

---

**NIC: Demonstrating that trustworthy, offline AI for safety-critical systems is achievable.**
