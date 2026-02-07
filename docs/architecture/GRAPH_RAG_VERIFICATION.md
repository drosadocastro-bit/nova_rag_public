# GraphRAG Verification + Diagram Reranker (Offline, Deterministic)

## Purpose

Add a **supplemental verification layer** to NIC that can validate claims against a knowledge graph and diagram evidence. The system must remain **offline, deterministic, and auditable**. The verifier is not a fallback generator. It only **vetoes** or **forces extractive** responses when evidence is insufficient or inconsistent.

## Non-Negotiable Constraints

- Offline-only: no external APIs.
- Deterministic: same input must produce the same decision.
- Evidence-bound: every verification must point to **original source spans** (page + bounding box).
- Non-creative: verifier never invents or rewrites content.
- Conservative: graph mismatch triggers abstain or extractive fallback.

## High-Level Flow

```
User Query
  ↓
Hybrid Retrieval (vector + BM25)
  ↓
LLM Draft Answer
  ↓
Post-Generation Quality Gate (lexical grounding)
  ↓
GraphRAG + Diagram Verifier (supplemental)
  ├─ pass → deliver answer
  └─ fail → force extractive or abstain
```

## Data Model

### 1) Evidence Spans

- `doc_id`, `page`, `bbox` (x1,y1,x2,y2), `text`, `source_path`
- Stored for text spans and diagram captions/labels.

### 2) Diagram Cards

A **diagram card** is a text representation of a diagram.

Fields:
- `diagram_id`, `doc_id`, `page`, `bbox`
- `caption`
- `labels` (OCR-extracted and normalized)
- `callouts` (if present)
- `related_terms` (from glossary expansion)

### 3) Graph Nodes / Edges

- Nodes: `Entity`, `ProcedureStep`, `Component`, `Signal`, `Threshold`
- Edges: `contains`, `requires`, `measures`, `connects_to`, `depends_on`
- Each edge **must reference evidence spans**.

## Deterministic Graph Build (Offline)

1. **Chunk-level extraction** from PDFs (already in NIC ingestion).
2. **Rule-based entity + relation extraction** (regex + glossary + patterns).
3. **Diagram OCR** for labels + captions (Tesseract or equivalent offline OCR).
4. **Normalize** entities and units (e.g., "115 V" vs "115V").
5. **Attach evidence spans** to every node/edge.

No LLM-generated triples. This avoids non-deterministic graph drift.

## Verification Logic

### A) Claim Parsing (Deterministic)

- Split answer into statements (already done in quality gate).
- Extract structured tuples when possible:
  - `subject`, `predicate`, `object`, `value`, `unit`

### B) Graph Check

For each statement:
- Look for **matching edges** with overlapping entities.
- Validate numeric thresholds and component relationships.
- Require **evidence span** links for any match.

If no graph support:
- Mark statement as **unverified**.

### C) Diagram Check

If statement mentions components or signals that are primarily diagrammatic:
- Search diagram cards by label overlap and page proximity.
- Require **caption/label** match + evidence span.

### D) Decision Policy

- If any **critical** statement is unverified → force extractive or abstain.
- If only **non-critical** statements are unverified → allow if lexical gate passed and confidence is high.

## Configuration Knobs (Proposed)

- `NOVA_GRAPH_VERIFY=1` (enable graph verifier)
- `NOVA_DIAGRAM_VERIFY=1` (enable diagram verifier)
- `NOVA_GRAPH_REQUIRE_EVIDENCE=1` (always require source span)
- `NOVA_GRAPH_STRICT=1` (any unverified critical claim fails)
- `NOVA_DIAGRAM_MIN_LABEL_OVERLAP=0.50`

## Failure Modes and Safeguards

- **Graph sparsity**: if graph lacks coverage, verifier may over-abstain.
  - Safeguard: only enforce for **procedural/safety** queries.
- **OCR errors**: false negatives on diagrams.
  - Safeguard: allow fallback to text spans if available.
- **Ambiguous entities**: same label for different components.
  - Safeguard: require page proximity + caption context.

## Minimal Implementation Plan (All Domains)

### Phase 1: Diagram Cards

- Extract diagram images + captions per PDF page.
- OCR labels and store diagram cards.
- Add diagram cards to retrieval index as a separate doc type.

### Phase 2: Graph Build (Deterministic)

- Add rule-based entity extraction for key domain vocab.
- Build node/edge store with evidence spans.
- Index edges in a simple lookup table for verification.

### Phase 3: Verification Hooks

- Add a post-gate verification step in `core/handlers/query_handler.py`.
- If graph/diagram verification fails, force extractive response.

## Acceptance Criteria

- 100% offline.
- Deterministic runs across identical inputs.
- Every graph/diagram match references page + bbox evidence.
- Failure triggers abstain or extractive fallback only.

## What This Does NOT Do

- It does not generate answers.
- It does not replace retrieval or the lexical grounding gate.
- It does not allow creative synthesis without evidence.

## Rationale

This approach improves **consistency checks** and **multi-hop validation** without weakening NIC's safety posture. It keeps the system conservative, auditable, and offline while allowing diagrams to participate as first-class evidence.
