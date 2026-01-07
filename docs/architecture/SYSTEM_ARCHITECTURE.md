# NIC Public - System Architecture

## Overview

NIC (Nova Intelligent Copilot) is an offline-first, safety-critical RAG system designed for high-consequence domains where hallucination risk must be actively mitigated. This document describes the architecture, design decisions, and safety guarantees.

---

## Core Design Principles

### 1. **Offline-First**
- All models, embeddings, and indexes are local on-disk
- Zero external API calls for inference (Ollama runs locally on port 11434)
- Works in no-connectivity zones (remote or restricted-connectivity environments)
- Air-gappable: no telemetry, no cloud dependencies

### 2. **Policy-Enforced Safety**
- Hard refusals for out-of-scope and safety-bypass queries (before LLM call)
- Citation audit: every claim traced back to source with page numbers
- Extractive fallback: when retrieval confidence is too low, return snippet instead of hallucinating
- Runtime toggles: switch between strict, balanced, and permissive modes

### 3. **Full Auditability**
- Every query logged with: timestamp, question, answer, source docs, confidence, safety flags
- Manifest file records corpus hash at startup (detect tampering)
- Response includes metadata: which model, confidence score, audit status
- All logs are structured JSON, suitable for compliance/investigation

### 4. **Reproducibility**
- Locked dependencies in requirements.txt
- Deterministic retrieval (FAISS, no randomness)
- Corpus versioning: manifest.json tracks what docs are indexed
- Docker-ready for air-gap deployments

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         WEB UI / API CLIENT                      │
│                      (Flask @ localhost:5000)                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SAFETY POLICY GUARD                         │
│  - Out-of-scope detection (vehicle domain only)                 │
│  - Safety bypass prevention (no "disable safety" requests)      │
│  - Rate limiting, token auth (optional)                         │
│  ❌ Refuse early (before expensive LLM call)                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RETRIEVAL PIPELINE                          │
│  ┌─────────────────┐      ┌─────────────────┐                  │
│  │  Query Input    │──→   │  Embedding Mod  │  (all-MiniLM)    │
│  └─────────────────┘      └────────┬────────┘                  │
│                                    │                            │
│  ┌─────────────────┐      ┌────────▼────────┐                  │
│  │  FAISS Index    │◄──┤  Similarity Search │                  │
│  │ (27 vectors)    │      └────────┬────────┘                  │
│  └─────────────────┘               │                            │
│                           ┌────────▼──────────┐                 │
│                           │  Reranking        │                 │
│                           │ (cross-encoder)   │                 │
│                           └────────┬──────────┘                 │
│                                    │                            │
│                           ┌────────▼──────────┐                 │
│                           │  Top-K Docs       │                 │
│                           │ (ranked by score) │                 │
│                           └────────┬──────────┘                 │
└────────────────────────────────────┼──────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
        ┌──────────────────────┐        ┌──────────────────────┐
        │ Confidence Check     │        │ Citation Check       │
        │ (avg score < 0.60?)  │        │ (strict mode?)       │
        │ → Return snippet     │        │ → Verify claims      │
        └──────────────────────┘        └──────────────────────┘
                    │                                 │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT ROUTER (agent_router.py)                │
│  - Intent classification (diagnostic, procedure, etc.)          │
│  - Model selection (LLAMA for speed, GPT-OSS for depth)        │
│  - Prompt engineering (context-aware)                          │
│  - Output validation                                            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   LLM INFERENCE (Ollama)                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │   THREE-TIER MODEL ARCHITECTURE (Automatic Routing)    │   │
│  │                                                         │   │
│  │  TIER 1: fireball-meta-llama-3.2-8b (FAST)             │   │
│  │  ├─ 30k context window (128k available)                │   │
│  │  ├─ ~2-5s inference time (procedures, diagnostics)     │   │
│  │  └─ Fallback target (on Qwen timeout)                  │   │
│  │                                                         │   │
│  │  TIER 2: qwen/qwen2.5-coder-14b (DEEP)                 │   │
│  │  ├─ Deep analysis, complex reasoning                   │   │
│  │  ├─ ~5-10s inference time                              │   │
│  │  └─ Auto-selected for "explain" / "why" queries        │   │
│  │                                                         │   │
│  │  TIER 3: phi-4-14b (VALIDATION ONLY)                   │   │
│  │  ├─ Used exclusively for RAGAS evaluation              │   │
│  │  ├─ Evaluates answer quality / relevancy               │   │
│  │  └─ Not used for user-facing responses                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│  - Response timeout: 1200s (model loading overhead)            │
│  - Max tokens: 4096 (8B), 512 (14B), configurable              │
│  - Runs locally on port 11434 (air-gappable)                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CITATION AUDIT LAYER                           │
│  - Extract claims from LLM response                             │
│  - Validate each claim against retrieved context               │
│  - Mark fully_cited / partially_cited / uncited                │
│  - (Optional strict mode: reject if uncited)                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RESPONSE FORMATTING                           │
│  - JSON response with metadata:                                │
│    * answer (main response text)                               │
│    * model_used (which LLM was invoked)                        │
│    * confidence (retrieval confidence %)                       │
│    * audit_status (fully_cited / partial / uncited)            │
│    * source_docs (which docs were cited)                       │
│    * effective_safety (audit/strict flags used)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AUDIT LOGGING                               │
│  - Structured JSON to vector_db/query_log.db (optional)        │
│  - Includes: timestamp, query, answer, sources, audit_status   │
│  - Queryable via /api/audit endpoint                           │
│  - Suitable for compliance audits and incident investigation   │
└─────────────────────────────────────────────────────────────────┘
```

Refer to the visual overview in [diagram.svg](diagram.svg).

---

## Key Components

### 1. **Policy Guard** (`nova_flask_app.py` lines 52-111)
Runs before retrieval; blocks:
- Out-of-scope queries (sports, finance, weather, etc.)
- Safety bypass attempts (disable airbag, bypass seatbelt, etc.)
- Optional API token validation

```python
OUT_OF_SCOPE_PATTERNS = [
    "world series", "capital of", "stock", "weather", "medical", ...
]
SAFETY_BYPASS_PATTERNS = [
    "bypass", "disable airbag", "remove seatbelt", "override warning", ...
]
```

### 2. **Retrieval Engine** (`backend.py`)
- Embeds query using `all-MiniLM-L6-v2` (384 dims, 27 chunks from vehicle manual)
- FAISS similarity search (top-12)
- Cross-encoder reranking (top-6)
- Confidence calculation (avg of doc scores)
- Error code detection (if query mentions "Code XYZ", boost related docs)
 - Hybrid mode (default): Union FAISS candidates with BM25 lexical candidates, then rerank and select via MMR
   - Enable/disable: `NOVA_HYBRID_SEARCH=1/0`
   - Tuning: `NOVA_BM25_K1` (1.5), `NOVA_BM25_B` (0.75)

### 3. **Agent Router** (`agents/agent_router.py`)
Routes to appropriate model tier:
- `diagnostic`: Troubleshooting, fault codes → Llama 8B (fast path)
- `maintenance_procedure`: Step-by-step maintenance → Llama 8B (fast path)
- `definition`: "What is X?" → Llama 8B (fast path, extractive)
- `explanation`: "Why", "how does it work" → Qwen 14B (deep reasoning)
- `other`: Fallback to Qwen 14B (general reasoning)

**Automatic fallback**: If Qwen times out (>1200s), automatically retry with Llama 8B.
**Validation only**: Phi-4-14b used exclusively for RAGAS evaluation, never for user responses.

### 4. **Citation Auditor** (`agents/citation_auditor.py`)
- Extracts claims from LLM response
- Cross-references against retrieved context
- Returns audit_status: `fully_cited`, `partially_cited`, `uncited`
- In strict mode, rejects uncited answers and returns snippet instead

### 5. **Query Audit Log**
Every query is logged (optional, feature-flagged):
```json
{
  "timestamp": "2025-12-29T11:30:00Z",
  "question": "How do I change the oil?",
  "model_used": "fireball-meta-llama-3.2-8b",
  "confidence": 0.82,
  "audit_status": "fully_cited",
  "source_docs": [
    {"source": "vehicle_manual.txt", "page": 42, "snippet": "..."}
  ],
  "answer_length": 285,
  "response_time_ms": 3421,
  "session_id": "sess-abc123"
}
```

---

## Safety Guarantees

### ✅ Hallucination Mitigations
1. **Retrieval confidence threshold**: If avg confidence < 60%, return snippet instead of LLM
2. **Citation audit**: Validate all claims against context; in strict mode, reject uncited answers
3. **Hard refusals**: Policy guard blocks out-of-scope/safety-bypass questions before LLM

### ✅ No Jailbreaks
1. **Policy patterns**: Cannot be tricked into bypassing safety systems (checked before LLM)
2. **Stateless queries**: No session persistence of unsafe "agreements" (each query is independent)
3. **Grounding required**: All procedural advice must cite the manual

### ✅ Full Auditability
1. **Query logging**: Every ask is recorded with question, answer, sources, confidence
2. **Metadata in response**: Client can see which safety flags were active
3. **Corpus versioning**: Manifest hash at startup; fail-safe if docs are tampered

### ✅ Offline Capability
1. **No external calls**: All models, indexes, LLM run locally
2. **Air-gappable**: No telemetry, no cloud API keys, no internet required
3. **Reproducible**: Docker + locked dependencies ensure same behavior across machines

---

## Performance & Persistence

### Retrieval Caching

**File**: [cache_utils.py](cache_utils.py)

Retrieval results are optionally cached using:
- **In-memory cache**: Instant returns for duplicate queries
- **Disk persistence**: `vector_db/retrieval_cache.pkl` for across-restart continuity
- **Cache key**: MD5 hash of `(query, k, top_n)` parameters

**Enable with:**
```bash
$env:NOVA_ENABLE_RETRIEVAL_CACHE=1
```

**Performance impact:**
- Cache miss (first query): ~100ms (FAISS + reranking)
- Cache hit (repeated query): <1ms (**2000x faster**)

Ideal for:
- Interactive demos where users ask similar questions
- Production systems with high query volume
- Reducing FAISS index load on low-power hardware

### Session Management & Long-Term Memory

**File**: [agents/session_store.py](agents/session_store.py)

Conversation sessions are persisted to SQLite for resumability:

**Database**: `~/.nova_rag/sessions.db` (user's home directory)

**Stored per session:**
- `session_id`: Unique identifier (8-char UUID)
- `topic`: User-entered conversation topic
- `state_json`: Full conversation state and findings
- `finding_log_json`: Audit trail of decisions made
- `turns`: Total query count in session
- `created_at`, `updated_at`: Timestamps
- `model`, `mode`: Which LLM and mode were used

**Usage (automatic):**
```python
# Save session after each query
save_session(session_id, state, topic="Engine Diagnostics", model="Qwen 14B")

# Load session from home directory
loaded_state = load_session(session_id)
```

**Benefits:**
- ✅ Resume conversations across app restarts
- ✅ Audit trail for compliance/debugging
- ✅ Multi-user support (each user = separate session)
- ✅ Finding log for transparency (what was decided, why)

---

## Configuration

### Environment Variables

```bash
# Safety controls
NOVA_POLICY_HARD_REFUSAL=1           # Enable policy guard (default: on)
NOVA_API_TOKEN=<token>               # Optional: require token for API access

# Offline mode
NOVA_OFFLINE=1                       # Skip any network checks
NOVA_DISABLE_VISION=1                # Disable diagram/image search
NOVA_DISABLE_EMBED=1                 # Use lexical fallback only

# Performance tuning
NOVA_ENABLE_RETRIEVAL_CACHE=1        # Cache retrieval results (2000x speedup on repeats)
OMP_NUM_THREADS=1                    # Reduce CPU spike on low-power machines

# Audit & logging
NOVA_ENABLE_AUDIT_LOG=1              # Log all queries to vector_db/query_log.db
```

---

## Stress Testing & Validation

**111 test cases across 11 categories:**
- Out-of-context (40 tests): General knowledge, wrong domain, etc.
- Ambiguous (30 tests): Missing context, vague references
- Adversarial (20 tests): False premises, context injection
- Safety-critical (10 tests): Bypass attempts
- Edge cases (11 tests): Malformed input, edge behaviors

**Run the test:**
```bash
python nic_stress_test.py
# Generates: nic_stress_test_results.json, nic_stress_test_report.md
```

**Expected result: 100% pass rate** (all safety tests pass, all out-of-scope queries refused, all adversarial attempts blocked)

---

## Offline Deployment

### Docker (air-gappable)
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
# Optionally pre-pull Ollama models and embed them in image
ENV NOVA_OFFLINE=1
CMD ["python", "nova_flask_app.py"]
```

### Local (no Docker)
```bash
# 1. Activate venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 2. Start Ollama (on port 11434)
# ollama pull llama3.2:8b
# ollama pull qwen2.5-coder:14b

# 3. Start NIC
python nova_flask_app.py
# Visit http://localhost:5000
```

---

## Extending for Other Domains

To adapt NIC for other regulated domains:

1. **Swap the corpus**: Replace `vehicle_manual.txt` with your domain docs (e.g., medical manuals, internal procedures, compliance guides)
2. **Update patterns**: Modify `OUT_OF_SCOPE_PATTERNS` and `SAFETY_BYPASS_PATTERNS` for your domain
3. **Retrain embeddings**: Run `python ingest_vehicle_manual.py` (modified for your docs)
4. **Test with domain stress cases**: Customize `nic_stress_test.py` with domain-specific adversarial queries

Example: **Medical domain**
```
OUT_OF_SCOPE: "sports", "cooking", "finance" (unchanged)
SAFETY_BYPASS: "bypass sterility", "skip disinfection", "ignore protocol", ...
DOCS: FDA-approved procedure manuals, pharmacology references
STRESS_TEST: Add medical-specific adversarial cases (drug interactions, contraindications, etc.)
```

---

## Compliance & Regulatory

### What NIC Addresses
- ✅ **Auditability**: Full query logs with sources and confidence
- ✅ **Reproducibility**: Locked deps, deterministic retrieval, offline-safe
- ✅ **Safety**: Hard refusals, citation validation, confidence thresholds
- ✅ **Transparency**: Every answer includes which model, mode, and audit status used

### What You Still Need (Domain-Specific)
- ⚠️ **Domain approval**: Verify that your docs are up-to-date and accurate
- ⚠️ **User training**: Educate users that NIC is a *reference aid*, not a replacement for human judgment
- ⚠️ **Incident procedures**: Define how to investigate/respond if NIC gives wrong advice
- ⚠️ **Versioning/updates**: Document process for updating manuals and retraining index

---

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Cold start | ~3-5s | Load models, index |
| First query | ~700-800s | Ollama model loading overhead (one-time per session) |
| Subsequent queries | ~3-10s | Inference only (8B: 2-5s, 14B: 5-10s) |
| Memory | ~2-4GB | Single LLM + embeddings (8B footprint) |
| Retrieval only | ~200ms | FAISS search + rerank |
| LLM inference (8B) | ~2-5s | Llama fast path (tier 1) |
| LLM inference (14B) | ~5-10s | Qwen deep reasoning (tier 2) |
| RAGAS eval (Phi-4) | ~10-15s per query | Validation only, not user-facing |
| With audit | +1-2s | Citation validation |
| With caching | 2000x faster | For repeated queries |

---

## Future Enhancements

- [ ] Multi-user sessions with role-based access
- [ ] Adaptive confidence thresholds (learn from feedback)
- [ ] Fine-tuned domain-specific embeddings
- [ ] Knowledge graph integration (for cross-manual relationships)
- [ ] Continuous corpus updates (versioned, audit-logged)
- [ ] Threat model & penetration testing report
