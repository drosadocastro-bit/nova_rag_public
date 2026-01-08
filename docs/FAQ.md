# Frequently Asked Questions (FAQ)

Common questions about the NIC RAG system, its design, capabilities, and usage.

---

## Table of Contents

1. [General Questions](#general-questions)
2. [Technical Architecture](#technical-architecture)
3. [Deployment & Operations](#deployment--operations)
4. [Usage & Features](#usage--features)
5. [Troubleshooting](#troubleshooting)
6. [Comparison to Other Systems](#comparison-to-other-systems)

---

## General Questions

### What is NIC?

**NIC** is a reference implementation of an **offline, air-gapped RAG (Retrieval-Augmented Generation) system** designed for safety-critical environments. It demonstrates how to build trustworthy AI assistants that:
- Operate without internet access
- Ground all answers in verifiable source documents
- Implement human-on-the-loop decision making
- Abstain when uncertain to prevent hallucinations

### Who should use NIC?

NIC is intended for:
- **System Safety Engineers** evaluating AI for safety-critical applications
- **Security Reviewers** assessing air-gap compliance and threat models
- **Program Managers** exploring offline AI deployment feasibility
- **AI/ML Engineers** implementing RAG patterns for high-consequence domains

NIC is a **reference architecture**, not a production-ready product.

### Can I use this in production?

NIC demonstrates technical feasibility but requires additional work for production:
- **Security hardening** (penetration testing, security audit)
- **Operational procedures** (monitoring, incident response)
- **Domain-specific customization** (your corpus, your workflows)
- **Regulatory compliance** (if applicable to your industry)

Use NIC as a starting point, not a finished product.

### Is NIC free to use?

Yes. NIC is released under the **MIT License**, allowing commercial and non-commercial use. See [LICENSE](../LICENSE) for details.

---

## Technical Architecture

### Why hybrid retrieval over vector-only?

**Hybrid retrieval** (vector similarity + BM25 lexical search) provides:

| Aspect | Vector-Only | Hybrid (Vector+BM25) | Benefit |
|--------|-------------|----------------------|---------|
| Semantic matching | ✓ Excellent | ✓ Excellent | Same |
| Exact term matching | ○ Poor | ✓ Excellent | +53% recall for part numbers |
| Diagnostic codes | ○ Poor | ✓ Excellent | Critical for safety |
| Acronyms/abbreviations | ○ Moderate | ✓ Excellent | Better domain coverage |
| **Overall recall** | 67% | 85% | +27% improvement |

**Conclusion:** For safety-critical systems, the 27% recall improvement justifies the 14% latency increase.

See [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md) for detailed metrics.

### How does confidence gating work?

**Confidence gating** prevents hallucinations by abstaining when uncertain.

**Process:**
1. System retrieves relevant documents (retrieval score 0.0-1.0)
2. If retrieval score < 0.6 → System abstains (no LLM generation)
3. If retrieval score ≥ 0.6 → System generates answer
4. LLM includes confidence estimate in response
5. User sees confidence score and citations

**Why 0.6 threshold?**
- Empirically validated against 111 adversarial tests
- Balances utility (answering questions) vs. safety (preventing wrong answers)
- Adjustable for different risk tolerances

**Abstention Response:**
```json
{
  "response_type": "abstention",
  "message": "I cannot provide a confident answer.",
  "extractive_fallback": ["Relevant quote 1...", "Relevant quote 2..."]
}
```

User reviews quotes manually instead of trusting potentially hallucinated answer.

### What happens when Ollama is unavailable?

**Startup:** Application runs startup validation, detects Ollama failure, and exits with actionable error message.

**Runtime (if Ollama crashes):**
- `/api/ask` requests return error: `{"error": "LLM connection failed"}`
- `/api/status` shows: `{"ollama": false, "ollama_status": "error"}`
- System does NOT fall back to hallucinations
- Logs error for operator intervention

**Recovery:**
1. Restart Ollama: `ollama serve`
2. Verify model loaded: `ollama list`
3. Application automatically reconnects on next request

See [Troubleshooting Guide](TROUBLESHOOTING.md#ollama-connection-issues) for details.

### Can I use different embedding models?

**Yes**, but requires code changes.

**Current model:** `sentence-transformers/all-MiniLM-L6-v2`
- Dimension: 384
- Size: ~80 MB
- Speed: Fast
- Quality: Good for general text

**Alternative models:**

| Model | Dimensions | Size | Speed | Quality |
|-------|-----------|------|-------|---------|
| `all-mpnet-base-v2` | 768 | 420 MB | Slower | Better |
| `all-MiniLM-L12-v2` | 384 | 120 MB | Moderate | Good |
| `multi-qa-MiniLM-L6-cos-v1` | 384 | 80 MB | Fast | Good for Q&A |

**How to change:**

1. **Update backend.py:**
   ```python
   # Find embedding model initialization (~line 110)
   embedding_model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
   ```

2. **Rebuild index:**
   ```bash
   rm vector_db/vehicle_index.faiss
   rm vector_db/vehicle_docs.jsonl
   python ingest_vehicle_manual.py
   ```

3. **Test retrieval quality:**
   ```bash
   python test_retrieval.py  # If available
   ```

**⚠️ Warning:** Different embeddings = different index. Must rebuild.

---

## Deployment & Operations

### How do I add new documents to the corpus?

**Process:**

1. **Add PDFs to data/ directory:**
   ```bash
   cp new_manual.pdf data/
   ```

2. **Rebuild FAISS index:**
   ```bash
   python ingest_vehicle_manual.py
   ```

3. **Verify index updated:**
   ```bash
   ls -lh vector_db/vehicle_index.faiss
   # Should show new timestamp and larger file size
   ```

4. **Test retrieval:**
   ```bash
   curl -X POST http://127.0.0.1:5000/api/retrieve \
     -H "Content-Type: application/json" \
     -d '{"query": "content from new manual", "k": 5}'
   ```

**Notes:**
- Full rebuild required (no incremental updates currently)
- Downtime required during rebuild
- Backup old index before rebuilding: `cp -r vector_db/ vector_db.backup/`

### What are the hardware requirements?

**Minimum (development):**
- CPU: 4 cores, 2 GHz+
- RAM: 4 GB
- Storage: 10 GB
- OS: Linux, macOS, Windows 10+

**Recommended (production):**
- CPU: 8 cores, 3 GHz+
- RAM: 16 GB
- Storage: 50 GB SSD
- OS: Linux (Ubuntu 22.04+, RHEL 8+)

**By Configuration:**

| Config | RAM | CPU Cores | Storage | Notes |
|--------|-----|-----------|---------|-------|
| Minimal (1B model) | 2 GB | 2 | 5 GB | Edge devices |
| Balanced (3B model) | 8 GB | 4 | 20 GB | Laptops |
| Default (8B model) | 16 GB | 8 | 50 GB | Servers |
| High-end (70B model) | 64 GB | 16+ | 100 GB | Requires GPU |

See [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md) for detailed specs.

### Can this run completely offline?

**Yes.** NIC is designed for **complete air-gap operation**.

**Requirements:**
1. Pre-download all models on internet-connected machine
2. Transfer models to air-gapped machine
3. Set offline environment variables
4. Verify no network calls

**Setup:**

```bash
# Enable offline mode
export NOVA_FORCE_OFFLINE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# Verify offline operation
python verify_offline_requirements.py
```

**What needs pre-download:**
- Ollama LLM models (`ollama pull llama3.2:8b`)
- HuggingFace embedding models (sentence-transformers)
- Python packages (`pip download -r requirements.txt`)

See [Air-Gapped Deployment Guide](deployment/AIR_GAPPED_DEPLOYMENT.md) for complete instructions.

### How do I update the models?

**LLM Models (Ollama):**

```bash
# List current models
ollama list

# Pull updated model
ollama pull llama3.2:8b

# Remove old version (if needed)
ollama rm llama3.2:8b:old_tag
```

**Embedding Models:**

```bash
# Clear HuggingFace cache
rm -rf ~/.cache/huggingface/hub/models--sentence-transformers*

# Re-download (on next app start)
python nova_flask_app.py
# Model auto-downloads from HuggingFace

# Or pre-download:
python -c "from sentence_transformers import SentenceTransformer; \
           SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

**After updating embeddings:**
```bash
# Rebuild index with new embeddings
python ingest_vehicle_manual.py
```

### What languages are supported?

**Current:** English only

**Why?**
- Embedding model trained on English text
- LLM (llama3.2) optimized for English
- Test corpus is English vehicle manuals

**Can I add other languages?**

Yes, with modifications:

1. **Use multilingual embedding model:**
   ```python
   # In backend.py
   embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
   ```

2. **Use multilingual LLM:**
   ```bash
   ollama pull mistral:7b-instruct-v0.3  # Supports multiple languages
   ```

3. **Rebuild index with new embeddings**

4. **Test with target language corpus**

**⚠️ Note:** Quality depends on embedding/LLM multilingual performance.

---

## Usage & Features

### Why does the system abstain so frequently?

**Common causes:**

1. **Query out of scope:** Question not related to corpus domain
   - Solution: Ask about topics covered in documents

2. **Vague query:** Too ambiguous to answer confidently
   - Solution: Be more specific (see [User Guide](USER_GUIDE.md))

3. **Information not in corpus:** Relevant documents not loaded
   - Solution: Add documents and rebuild index

4. **High confidence threshold:** System configured conservatively
   - Solution: Review threshold appropriateness (default: 0.6)

**Is abstention bad?**

No. **Abstention is a safety feature.**

Preferable outcomes:
1. High-confidence correct answer ✓ (best)
2. Abstention + extractive quotes ✓ (safe)
3. Low-confidence wrong answer ✗ (dangerous)

In safety-critical domains, #2 is better than #3.

### How accurate are the citations?

**Citation Accuracy:**
- **With citation audit enabled:** ~95% accurate
- **Without citation audit:** ~85% accurate

**How citation audit works:**
1. LLM generates answer with citations
2. System retrieves cited passages
3. Validator checks if answer is supported by passages
4. Unsupported claims are flagged or removed

**Enable citation audit:**
```bash
export NOVA_CITATION_AUDIT=1
export NOVA_CITATION_STRICT=1  # Strict mode: remove unsupported claims
```

**Trade-off:**
- ✓ Higher citation accuracy
- ✓ Fewer hallucinations
- ✗ +1-2 seconds latency
- ✗ May remove some correct statements (false positives)

**Best practice:** Always verify citations for safety-critical tasks, regardless of audit status.

### Can I trust the confidence scores?

**Confidence scores are indicative, not guaranteed.**

**Score interpretation:**

| Score | Meaning | Recommended Action |
|-------|---------|-------------------|
| 90-100% | Very high confidence | Trust, but still verify for critical tasks |
| 70-89% | High confidence | Review carefully before acting |
| 50-69% | Medium confidence | Verify citations before using |
| 0-49% | Low confidence | System abstains or use with extreme caution |

**Factors affecting accuracy:**
- LLM self-assessment quality (imperfect)
- Retrieval score (more reliable)
- Citation audit status (improves reliability)
- Corpus quality (better sources = better scores)

**Best practice:** Use confidence scores as one signal among many (citations, context, domain knowledge).

---

## Troubleshooting

### The system is very slow. How can I speed it up?

**Quick fixes:**

1. **Use smaller model:**
   ```bash
   ollama pull llama3.2:3b  # 40% faster than 8b
   ```

2. **Disable citation audit:**
   ```bash
   export NOVA_CITATION_AUDIT=0  # Save 1-2s
   ```

3. **Enable caching:**
   ```bash
   export NOVA_ENABLE_RETRIEVAL_CACHE=1  # 6-12x faster for repeated queries
   ```

4. **Disable cross-encoder:**
   ```bash
   export NOVA_DISABLE_CROSS_ENCODER=1  # Save 150ms
   ```

See [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md#optimization-recommendations) for comprehensive tuning guide.

### Why do I get "Index not loaded" errors?

**Cause:** FAISS index files are missing or corrupted.

**Solution:**

```bash
# 1. Check if index exists
ls vector_db/vehicle_index.faiss

# 2. If missing, build index
python ingest_vehicle_manual.py

# 3. Verify index created
ls -lh vector_db/
```

See [Troubleshooting Guide](TROUBLESHOOTING.md#faiss-index-problems) for detailed diagnostics.

### How do I know if the system is working correctly?

**Quick health check:**

```bash
# 1. Check API status
curl http://127.0.0.1:5000/api/status
# Expected: {"ollama": true, "index_loaded": true}

# 2. Test simple query
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the oil capacity?"}'
# Expected: JSON response with answer and citations

# 3. Run test suite (if available)
python test_nic_public.py
```

**Startup validation:**
- Application performs automatic health checks on startup
- Validates Ollama, FAISS index, dependencies
- Exits with error if critical issues detected

---

## Comparison to Other Systems

### How is this different from ChatGPT?

| Aspect | NIC | ChatGPT |
|--------|-----|---------|
| **Deployment** | Offline, local | Cloud-based |
| **Data privacy** | Complete (air-gapped) | Shared with OpenAI |
| **Hallucinations** | Confidence gating, abstains | May confabulate |
| **Citations** | All answers cited | Limited citation support |
| **Cost** | Infrastructure only | Per-token pricing |
| **Customization** | Full control over corpus | Limited to OpenAI's data |
| **Latency** | 2-8s (CPU inference) | 1-3s (optimized cloud) |
| **Use case** | Safety-critical, offline | General purpose, online |

**When to use NIC:**
- Air-gapped environments
- Sensitive/classified data
- Safety-critical decisions
- Regulatory compliance requires local processing

**When to use ChatGPT:**
- Internet available
- Low latency required
- General knowledge queries
- Data privacy not critical

### How does this compare to other RAG systems?

**NIC vs. LangChain/LlamaIndex:**

| Aspect | NIC | LangChain/LlamaIndex |
|--------|-----|---------------------|
| **Purpose** | Reference architecture | General-purpose framework |
| **Safety focus** | Explicit (confidence gating) | Optional (user implements) |
| **Offline support** | First-class | Requires configuration |
| **Citation audit** | Built-in | External tool needed |
| **Hybrid retrieval** | Default | Manual configuration |
| **Production-ready** | Reference only | Framework for production |

**Recommendation:**
- Use NIC to learn patterns for safety-critical RAG
- Use LangChain/LlamaIndex for general RAG applications
- Combine: Implement NIC's safety patterns in LangChain/LlamaIndex

### Can I use this with OpenAI models instead of Ollama?

**Yes**, but requires code changes and breaks air-gap capability.

**Modifications needed:**

1. **Update backend.py:**
   ```python
   # Replace Ollama client with OpenAI client
   from openai import OpenAI
   client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
   
   # Update call_llm function to use client.chat.completions.create()
   ```

2. **Set API key:**
   ```bash
   export OPENAI_API_KEY=your_openai_api_key
   ```

3. **Remove offline constraints:**
   ```bash
   export NOVA_FORCE_OFFLINE=0
   ```

**Trade-offs:**
- ✓ Better LLM quality (GPT-4)
- ✓ Lower latency
- ✗ Requires internet
- ✗ Data sent to OpenAI
- ✗ Per-token costs
- ✗ No air-gap compliance

**Not recommended for safety-critical use cases.**

---

## Additional Resources

- **Documentation Index:** [docs/INDEX.md](INDEX.md)
- **User Guide:** [docs/USER_GUIDE.md](USER_GUIDE.md)
- **API Reference:** [docs/api/API_REFERENCE.md](api/API_REFERENCE.md)
- **Troubleshooting:** [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Configuration:** [docs/deployment/CONFIGURATION.md](deployment/CONFIGURATION.md)

---

## Still Have Questions?

1. Check existing documentation (see above)
2. Review [System Architecture](architecture/SYSTEM_ARCHITECTURE.md)
3. Inspect code comments in `backend.py` and `nova_flask_app.py`
4. Run diagnostics: `python quick_sanity_check.py`

---

**Last Updated:** 2024-01  
**Version:** 1.0
