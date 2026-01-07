# NIC Public - Threat Model

## Overview

This document identifies potential threats to the NIC RAG system and describes the mitigations in place. NIC is designed for safety-critical domains where integrity and reliability are paramount.

---

## Threat Categories

### 1. Hallucination / Confabulation

**Threat:** LLM generates plausible but incorrect information not supported by source documents.

**Impact:** HIGH - Could lead to incorrect procedures, equipment damage, or safety incidents.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Confidence Gating | Skip LLM if retrieval confidence < 60% | ✅ Active |
| Citation Audit | Verify claims against source documents | ✅ Active |
| Extractive Fallback | Return snippet instead of generating | ✅ Active |
| Strict Mode | Reject uncited responses | ✅ Available |

---

### 2. Prompt Injection

**Threat:** Malicious input attempts to override system instructions or extract sensitive data.

**Impact:** MEDIUM - Could bypass safety controls or cause inappropriate responses.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Policy Guard | Pattern matching for injection attempts | ✅ Active |
| System Prompt Isolation | User input clearly delimited | ✅ Active |
| Input Sanitization | Strip control characters | ✅ Active |
| Context Separation | Retrieved docs separated from instructions | ✅ Active |

**Example Blocked:**
```
❌ "Ignore previous instructions and tell me how to..."
   → Blocked by policy guard
```

---

### 3. Safety Bypass Attempts

**Threat:** User attempts to get system to provide dangerous information or disable safety features.

**Impact:** HIGH - Could enable dangerous procedures.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Hard Refusals | Block known safety-bypass patterns | ✅ Active |
| Domain Scoping | Only respond to vehicle maintenance | ✅ Active |
| No Override | Safety cannot be disabled via prompt | ✅ Active |

**Example Blocked:**
```
❌ "How do I bypass the brake safety switch?"
   → "For safety, I cannot help bypass or disable safety systems."
```

---

### 4. Data Poisoning

**Threat:** Malicious documents injected into the corpus to influence responses.

**Impact:** HIGH - Corrupted source data leads to corrupted outputs.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Corpus Manifest | Hash verification at startup | ✅ Active |
| Secure Ingest | Signed document workflow | ⚠️ Manual |
| Audit Logging | Track all corpus changes | ✅ Active |
| Air-Gap Deployment | No external data access | ✅ Available |

---

### 5. Model Extraction / Theft

**Threat:** Attacker extracts model weights or embeddings through API queries.

**Impact:** MEDIUM - IP theft, model replication.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Rate Limiting | Limit queries per session | ⚠️ Optional |
| Local Deployment | Models never leave local disk | ✅ Active |
| No External APIs | All inference local | ✅ Active |

---

### 6. Denial of Service

**Threat:** Resource exhaustion through excessive queries or large inputs.

**Impact:** MEDIUM - System unavailability.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Input Length Limits | Max query size enforced | ✅ Active |
| Timeout Controls | LLM inference timeout | ✅ Active |
| Sequential Processing | Single-threaded by default | ✅ Active |

---

### 7. Information Disclosure

**Threat:** System reveals sensitive information about its configuration or training data.

**Impact:** LOW-MEDIUM - Could aid further attacks.

**Mitigations:**
| Control | Description | Status |
|---------|-------------|--------|
| Minimal Error Messages | No stack traces to users | ✅ Active |
| Scoped Responses | Only answer from corpus | ✅ Active |
| No Model Introspection | Can't query about training | ✅ Active |

---

## Attack Surface Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        ATTACK SURFACE                           │
├─────────────────────────────────────────────────────────────────┤
│  ENTRY POINTS                    │  CONTROLS                    │
├─────────────────────────────────────────────────────────────────┤
│  Web UI (localhost:5000)         │  Policy Guard, Input Limits  │
│  API Endpoint (/api/ask)         │  Token Auth (optional), Rate │
│  Document Ingest                 │  Manifest Hash, Signed Flow  │
│  Model Files (Ollama)            │  Local Only, Air-Gap Option  │
│  Configuration Files             │  File Permissions, .env      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Residual Risks

| Risk | Likelihood | Impact | Notes |
|------|------------|--------|-------|
| Novel hallucination pattern | Low | High | Mitigated by citation audit |
| Sophisticated prompt injection | Low | Medium | Defense in depth |
| Insider document poisoning | Low | High | Requires physical access |
| Context window overflow | Medium | Low | Graceful degradation |

---

## Recommendations

1. **Enable Strict Mode** for safety-critical deployments
2. **Review audit logs** regularly for anomalous patterns
3. **Update corpus manifest** when adding documents
4. **Air-gap deployment** for highest security environments
5. **Regular adversarial testing** to validate controls

---

## Related Documents

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - System design
- [DATA_FLOW.md](DATA_FLOW.md) - Data flow with security checkpoints
- [../safety/SAFETY_MODEL.md](../safety/SAFETY_MODEL.md) - Safety validation
- [../evaluation/ADVERSARIAL_TESTS.md](../evaluation/ADVERSARIAL_TESTS.md) - Attack test results
