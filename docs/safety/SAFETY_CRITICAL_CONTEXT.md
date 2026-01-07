# Safety-Critical Context

## Overview

This document describes NIC's intended use context and safety philosophy for reviewers evaluating the architecture for safety-critical applications.

---

## Use Context

**NIC is intended as a reference architecture for systems supporting operators of safety-critical equipment**, including but not limited to:

- **Industrial maintenance** — Factory equipment, process control systems
- **Transportation** — Vehicle maintenance, aviation ground support
- **Defense** — Military equipment maintenance, logistics support
- **Medical** — Equipment reference, procedure lookup (non-diagnostic)
- **Critical infrastructure** — Power systems, telecommunications

### What NIC Is

- A **reference implementation** demonstrating offline, safety-aware RAG
- An **advisory tool** that retrieves and synthesizes information from trusted corpora
- A **starting point** for organizations building their own safety-critical AI assistants

### What NIC Is Not

- A certified medical, aviation, or safety device
- A replacement for qualified human operators
- A system that makes autonomous decisions or controls equipment

---

## Human-on-the-Loop Model

NIC implements a **human-on-the-loop (HOTL)** architecture where:

```
┌─────────────────────────────────────────────────────────────┐
│                     OPERATOR (Human)                        │
│  • Formulates queries                                       │
│  • Reviews AI-generated responses                           │
│  • Verifies citations against source material               │
│  • Makes final decisions                                    │
│  • Executes actions                                         │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    Advisory Information
                              │
┌─────────────────────────────────────────────────────────────┐
│                        NIC (AI)                             │
│  • Retrieves relevant documents                             │
│  • Synthesizes information with citations                   │
│  • Indicates confidence levels                              │
│  • Abstains when uncertain                                  │
│  • Logs all interactions for audit                          │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

| Principle | Implementation |
|-----------|----------------|
| **Advisory Only** | NIC provides information; it does not command, control, or actuate any system. |
| **Operator Authority** | The human operator retains full decision-making authority at all times. |
| **Transparent Sourcing** | All responses include citations that operators can verify independently. |
| **Explicit Uncertainty** | When retrieval confidence is low, NIC abstains rather than guesses. |
| **No Persistent State** | Each query is independent—no "unsafe agreements" carry between sessions. |

---

## Failure Philosophy

NIC's design prioritizes safety over helpfulness when conflicts arise.

### Abstention Over Hallucination

```
IF retrieval_confidence < threshold:
    RETURN source_snippet  # Verbatim text from corpus
    DO NOT generate  # Prevents hallucination
```

When NIC cannot find relevant information with sufficient confidence, it:
1. **Does not generate** a plausible-sounding answer
2. **Returns the best matching snippet** verbatim from the corpus
3. **Explicitly states** the limitation to the operator

### Refusal Over Compliance

```
IF query matches safety_bypass_pattern:
    RETURN refusal  # Hard block before LLM
    DO NOT process  # No downstream processing
```

NIC refuses queries that:
- Attempt to bypass safety systems
- Request out-of-scope information
- Attempt prompt injection attacks

### Citation Over Assertion

```
IF claim NOT traceable to source:
    FLAG as uncited  # Warn operator
    IN strict_mode: REJECT response  # Return snippet instead
```

Every factual claim must trace to a source document. Uncited claims are either:
- Flagged for operator awareness (balanced mode)
- Rejected entirely (strict mode)

---

## Uncertainty Handling

NIC communicates uncertainty through multiple mechanisms:

| Mechanism | Description |
|-----------|-------------|
| **Confidence Scores** | Numerical retrieval confidence (0-100%) shown to operator |
| **Audit Status** | Response marked as `fully_cited`, `partially_cited`, or `uncited` |
| **Explicit Abstention** | "I don't have information about that" instead of guessing |
| **Source Visibility** | Operator can inspect retrieved documents directly |

---

## Grounding via Citations

All NIC responses are grounded in the source corpus:

```
Response: "Torque lug nuts to 85-95 ft-lbs in a star pattern."
Citation: [Para 7-3.3, Table 7-1]
Source:   vehicle_manual.txt, page 24
          ↓
Operator: Can verify by checking page 24 of the manual
```

This creates an **auditable chain**:
1. Query → Retrieved documents → Generated response → Citations
2. Operator can trace any claim back to its source
3. Post-incident investigation can reconstruct the system's reasoning

---

## Deployment Considerations

### For Safety-Critical Deployments

Organizations deploying NIC-derived systems in safety-critical contexts should:

1. **Validate the corpus** — Ensure source documents are authoritative and current
2. **Train operators** — Users must understand NIC is advisory, not authoritative
3. **Configure strict mode** — Enable citation enforcement for high-stakes queries
4. **Establish review processes** — Define procedures for handling uncertain responses
5. **Maintain audit logs** — Preserve query logs for compliance and investigation
6. **Test adversarially** — Run the included test suites against your deployment

### Limitations

| Limitation | Mitigation |
|------------|------------|
| Corpus quality determines output quality | Use authoritative, verified source documents |
| LLMs can still produce subtle errors | Citation audit catches unsupported claims |
| Confidence scores are heuristic | Operators should apply domain judgment |
| System requires maintenance | Keep models, corpus, and dependencies updated |

---

## Regulatory Alignment

NIC's architecture supports common regulatory requirements:

| Requirement | How NIC Addresses It |
|-------------|---------------------|
| **Auditability** | Full query logging with timestamps, sources, confidence |
| **Traceability** | Citation mechanism links outputs to source documents |
| **Human oversight** | Advisory-only design, operator decision authority |
| **Fail-safe behavior** | Abstention over hallucination, hard refusals |
| **Reproducibility** | Locked dependencies, versioned corpus, deterministic retrieval |

---

## Related Documents

- [Safety Model](SAFETY_MODEL.md) — Detailed validation methodology
- [Human-on-the-Loop](HUMAN_ON_THE_LOOP.md) — Oversight mechanisms
- [Hallucination Defense](HALLUCINATION_DEFENSE.md) — Technical defense layers
- [Evaluation Summary](../evaluation/EVALUATION_SUMMARY.md) — Test coverage and results
