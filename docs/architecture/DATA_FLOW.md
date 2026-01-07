# NIC Public - Data Flow Architecture

## Overview

This document describes how data flows through the NIC RAG system from query input to response output, including all safety checkpoints and decision branches.

---

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER QUERY INPUT                               │
│                    (Web UI / API / CLI)                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    1. POLICY GUARD (Pre-Filter)                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ • Check for safety-bypass attempts                              │   │
│  │ • Check for out-of-scope queries                                │   │
│  │ • Validate API token (if enabled)                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                         │                    │                          │
│                    [PASS]                [BLOCK]                        │
│                         │                    │                          │
│                         ▼                    ▼                          │
│                    Continue          Return Refusal Message             │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    2. QUERY EXPANSION (GAR)                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Glossary Augmented Retrieval:                                   │   │
│  │ "Engine cranks but won't start" →                               │   │
│  │ "Engine cranks but won't start fails to fire no start..."       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    3. EMBEDDING & RETRIEVAL                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │ Query        │ →  │ Embed Query  │ →  │ FAISS Search │             │
│  │ Text         │    │ (MiniLM)     │    │ (27 vectors) │             │
│  └──────────────┘    └──────────────┘    └──────────────┘             │
│                                                  │                      │
│                                                  ▼                      │
│                                          Top-K Candidates               │
│                                          (k=20, raw)                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. RERANKING                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Cross-Encoder Reranking (ms-marco-MiniLM)                       │   │
│  │ • Score each candidate against original query                   │   │
│  │ • Sort by relevance score                                       │   │
│  │ • Return top-6 documents                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    5. CONFIDENCE GATING                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Calculate average confidence of top-6 docs                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                         │                    │                          │
│               [avg ≥ 0.60]            [avg < 0.60]                      │
│                         │                    │                          │
│                         ▼                    ▼                          │
│                    Continue         Return Best Snippet                 │
│                                     (Skip LLM - prevent hallucination)  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    6. AGENT ROUTING                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Intent Classification:                                          │   │
│  │ • Procedure → procedure_agent                                   │   │
│  │ • Diagnostic → troubleshoot_agent                               │   │
│  │ • Summary → summarize_agent                                     │   │
│  │ • General → default handler                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    7. LLM INFERENCE (Ollama)                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Model Selection (Three-Tier):                                   │   │
│  │ • llama3.2-8b: Fast responses, simple queries                   │   │
│  │ • phi-4-14b: Balanced, complex reasoning                        │   │
│  │ • qwen2.5-coder-14b: Technical/code tasks                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Prompt Construction:                                            │   │
│  │ • System prompt (safety constraints)                            │   │
│  │ • Retrieved context (with page references)                      │   │
│  │ • User query                                                    │   │
│  │ • Output format instructions                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    8. CITATION AUDIT                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ In Strict Mode:                                                 │   │
│  │ • Extract claims from LLM response                              │   │
│  │ • Verify each claim against retrieved context                   │   │
│  │ • Mark: fully_cited / partially_cited / uncited                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                         │                    │                          │
│               [PASS/PARTIAL]           [UNCITED]                        │
│                         │                    │                          │
│                         ▼                    ▼                          │
│                 Return Response      Return Snippet + Warning           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    9. RESPONSE + AUDIT TRAIL                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Response Payload:                                               │   │
│  │ • answer: Generated text with citations                         │   │
│  │ • sources: [{source, page, confidence}]                         │   │
│  │ • metadata: {model, audit_status, confidence_avg}               │   │
│  │ • audit_trail: Full decision log for compliance                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Hybrid Retrieval (Vector + BM25)

- Candidate Generation:
    - Vector: FAISS over `all-MiniLM-L6-v2` embeddings (top-k)
    - Lexical: BM25 over chunked corpus (top-k)
- Union + Deduplicate:
    - Merge candidates by `(id, source, page)`; preserve vector ordering
- Reranking:
    - Prefer sklearn or cross-encoder scores when available
    - Apply MMR for diversity and select `top_n`
- Confidence Gating:
    - Use average reranker confidence; if < 0.60, skip LLM and return snippet

Environment flags:
- `NOVA_HYBRID_SEARCH=1` (default on)
- `NOVA_BM25_K1` (default 1.5), `NOVA_BM25_B` (default 0.75)

See [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) and the [README](../../README.md#hybrid-retrieval) for usage.

## Data Stores

| Store | Location | Purpose |
|-------|----------|---------|
| FAISS Index | `vector_db/` | Vector similarity search |
| Document Chunks | `vector_db/` | Original text with metadata |
| Embedding Model | `models/all-MiniLM-L6-v2/` | Query/doc embeddings |
| Cross-Encoder | `models/ms-marco-MiniLM-L6/` | Reranking |
| LLM Models | Ollama (`~/.ollama/`) | Generation |
| Logs | `flask_server.log` | Audit trail |

---

## Key Decision Points

1. **Policy Guard**: Block unsafe queries before any processing
2. **Confidence Gate**: Skip LLM if retrieval confidence < 60%
3. **Citation Audit**: Reject uncited responses in strict mode
4. **Agent Routing**: Select appropriate handler for query type
5. **Model Selection**: Choose LLM based on task complexity

---

## Related Documents

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - Overall system design
- [THREAT_MODEL.md](THREAT_MODEL.md) - Security threat analysis
- [../safety/SAFETY_MODEL.md](../safety/SAFETY_MODEL.md) - Safety guarantees
