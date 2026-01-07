# NIC Public - Human-on-the-Loop Design

## Overview

NIC implements a **Human-on-the-Loop (HOTL)** paradigm rather than full automation. The system augments human decision-making with AI-powered retrieval and synthesis while maintaining human oversight at critical junctures.

---

## Design Philosophy

### Why Human-on-the-Loop?

In safety-critical domains, full automation carries unacceptable risk:

| Approach | Description | Risk Level |
|----------|-------------|------------|
| **Human-in-the-Loop** | Human approves every action | Slow, high overhead |
| **Human-on-the-Loop** | Human monitors, intervenes when needed | Balanced ✅ |
| **Full Automation** | No human oversight | Unacceptable risk |

NIC provides **decision support**, not decision-making. The human operator:
- Receives synthesized information with citations
- Can verify claims against source documents
- Makes final decisions on procedures
- Can override or reject AI suggestions

---

## Oversight Mechanisms

### 1. Transparent Sourcing

Every response includes:
- **Citations** with source document and page number
- **Confidence scores** for retrieval quality
- **Audit status** (fully cited / partially cited / uncited)

```
Response: "Torque lug nuts to 85-95 ft-lbs [Citation: Table 7-1]"
          ↓
Human can verify: Open vehicle_manual.txt, page 24, Table 7-1
```

### 2. Confidence Visibility

The system shows retrieval confidence to the operator:
- **High confidence (>80%)**: Strong match to query
- **Medium confidence (60-80%)**: Partial match, verify
- **Low confidence (<60%)**: Fallback to snippet, LLM skipped

### 3. Mode Selection

Operators can choose safety level:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Strict** | Reject uncited claims | Safety-critical procedures |
| **Balanced** | Warn on uncited claims | Normal operations |
| **Permissive** | Allow uncited claims | Research/exploration |

### 4. Query-Level Control

Operators can:
- Request **snippet-only** responses (no LLM)
- Request **sources-only** (just document references)
- Specify **confidence threshold** per query

---

## Intervention Points

```
┌──────────────────────────────────────────────────────────────────┐
│                    HUMAN INTERVENTION POINTS                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [1] QUERY FORMULATION                                           │
│      Human frames the question                                   │
│                         ↓                                        │
│  [2] RESPONSE REVIEW                                             │
│      Human reviews answer + citations                            │
│      Can: Accept / Reject / Request clarification                │
│                         ↓                                        │
│  [3] SOURCE VERIFICATION                                         │
│      Human can check cited sources directly                      │
│                         ↓                                        │
│  [4] ACTION DECISION                                             │
│      Human decides whether to act on information                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Escalation Triggers

The system flags responses for human review when:

1. **Low Confidence**: Retrieval confidence below threshold
2. **Uncited Claims**: Statements not traceable to sources
3. **Safety Keywords**: Response mentions safety-critical actions
4. **Conflict Detection**: Retrieved docs contain contradictions
5. **Out-of-Scope**: Query touches non-indexed content

---

## Audit Trail for Accountability

Every interaction is logged:

```json
{
  "timestamp": "2026-01-06T10:30:00Z",
  "query": "What's the torque spec for lug nuts?",
  "response": "85-95 ft-lbs [Citation: Table 7-1]",
  "confidence": 0.92,
  "audit_status": "fully_cited",
  "model": "llama3.2-8b",
  "sources": [{"file": "vehicle_manual.txt", "page": 24}],
  "human_action": "accepted"
}
```

This enables:
- Post-incident investigation
- Compliance auditing
- Performance monitoring
- Continuous improvement

---

## Training Recommendations

Operators should understand:

1. **NIC is a tool, not an authority** - Always verify critical information
2. **Citations are checkable** - Click through to verify
3. **Confidence matters** - Low confidence = higher scrutiny
4. **When in doubt, ask for sources** - Request snippet-only mode
5. **Report anomalies** - Flag unexpected responses for review

---

## Related Documents

- [SAFETY_MODEL.md](SAFETY_MODEL.md) - Safety guarantees
- [HALLUCINATION_DEFENSE.md](HALLUCINATION_DEFENSE.md) - How hallucinations are prevented
- [../architecture/DATA_FLOW.md](../architecture/DATA_FLOW.md) - System data flow
