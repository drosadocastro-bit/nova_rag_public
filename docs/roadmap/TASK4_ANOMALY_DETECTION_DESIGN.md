# Task 4: Anomaly Detection Design & Runbook

**Status:** Draft (design complete, implementation pending)
**Objective:** Flag suspicious query patterns for human review while never blocking requests and keeping deterministic safety rules authoritative.

---

## 1) Scope
- Detect out-of-distribution queries (probing, reconnaissance, nonsense) via advisory anomaly scores.
- Integrate scoring and evidence into the retrieval pipeline without affecting control flow.
- Provide operators with reviewable signals (score, threshold, category) and logs.
- Non-goals: Blocking traffic, modifying existing safety/risk classifiers, online learning.

## 2) Architecture at a Glance
```
Query text
   ↓ embed (sentence-transformer, 384d)
   ↓ QueryAnomalyDetector (autoencoder)
   ↓ reconstruction error → score
   ↓ scorer thresholds → category (low/medium/high)
   ↓ evidence chain logger (advisory only)
   ↓ retrieval & safety pipeline continues unchanged
```
- Model artifact: `models/anomaly_detector_v1.0.pth` + `model_card.json` (sha256, params, data hash).
- Feature space shared with retrieval embeddings to avoid extra model loads.
- Toggle: `NOVA_ENABLE_ANOMALY_DETECTION` (default off); advisory logging only.

## 3) Components
- **Featurizer:** Reuse embedding model (`sentence-transformers/all-MiniLM-L6-v2`) to produce 384-d vectors; no gradient updates.
- **Autoencoder (`core/safety/anomaly_detector.py`):**
  - Encoder: 384 → 128 → 32; Decoder: 32 → 128 → 384.
  - Params ~200K; activation: ReLU; loss: MSE reconstruction.
  - Inference budget: <5 ms CPU per query.
- **Scorer (`core/safety/anomaly_scorer.py`):**
  - Calculates reconstruction error, tracks rolling mean/variance of normal scores for calibration.
  - Categories: low (<p95), medium (p95–p95+2σ), high (≥p95+2σ).
  - Outputs: score, threshold, category, flagged_for_review boolean.
- **Evidence Writer (`core/safety/anomaly_evidence.py`):**
  - Adds advisory fields into evidence chain dataclasses/JSON.
  - Ensures serializable output for logging and compliance reports.
- **Loader (`core/safety/anomaly_loader.py`):**
  - Validates hash, loads frozen weights, handles missing/disabled states gracefully.

## 4) Data Pipeline
- **Source:** Normal queries only (logs + synthetic from manuals). No adversarial examples in training set.
- **Collection script:** `scripts/collect_query_logs.py` → `data/anomaly_detection/normal_queries.jsonl`.
- **Filtering:** dedupe, strip PII, length clamp (5–256 chars), printable ASCII check, domain tag if available.
- **Splits:** 80/10/10 (train/val/test). Shuffle to avoid temporal bias.
- **Telemetry:** Store dataset hash and sampling date in `model_card.json`.

## 5) Training Plan
- Optimizer: Adam (lr 1e-3), batch size 256, epochs 10 with early stop on val loss.
- Regularization: dropout 0.1 on hidden layers; L2 weight decay 1e-5.
- Calibration: compute validation score distribution → set p95 threshold; store threshold + σ in model card.
- Output: `models/anomaly_detector_v1.0.pth`, `model_card.json` (weights_hash, data_hash, threshold, σ, eval metrics).

## 6) Evaluation & Acceptance
- Metrics: AUC on synthetic adversarial holdout; recall@high-score (≥threshold+2σ); false positive rate on normal ≤5%; latency <5 ms CPU.
- Success criteria:
  - Detect ≥80% of synthetic adversarial probes (high category).
  - <5% FP on clean queries; no blocked traffic (advisory only).
  - Evidence chain shows score/threshold/category for every query when enabled.

## 7) Integration Points
- `core/safety/anomaly_loader.py`: init during app startup; honor env toggles; fall back cleanly if missing.
- `core/safety/anomaly_scorer.py`: API `score_query(text, embedding_model, detector, thresholds)` returns score + category.
- `core/safety/anomaly_evidence.py`: attach advisory payload into existing evidence chain dataclasses.
- `backend.py` / `nova_flask_app.py`: optional hook in request flow **after** risk/injection checks and **before** retrieval logging.
- Config: `NOVA_ENABLE_ANOMALY_DETECTION`, `NOVA_ANOMALY_MODEL_PATH`, `NOVA_ANOMALY_THRESHOLD_PCTL` (default 95).

## 8) Observability & Storage
- Log fields: score, threshold, category, flagged_for_review, model_version, model_hash.
- Persist threshold + σ in model card; verify hash on load; emit warning and disable on mismatch.
- Optionally emit histogram stats to analytics DB (frequency of high-category events).

## 9) Testing Plan
- **Unit:** scorer math (percentiles, categories), loader hash validation, evidence serialization, model forward pass shapes.
- **Integration:** end-to-end scoring with sample model; ensure pipeline continues even if model disabled/missing.
- **Safety Regression:** ensure injection/risk blocks still dominate; anomaly remains advisory.
- **Performance:** micro-benchmark <5 ms per query on CPU, no GPU dependency.

## 10) Rollout
- Phase 0: Disabled by default; ship model artifact and loader.
- Phase 1: Shadow mode (log-only) on staging corpus; monitor FP rate and latency.
- Phase 2: Enable in production with periodic report on flagged queries; retrain only with new normal data.

## 11) Open Questions
- What minimum log volume is available for normal queries? Need ≥10k clean samples.
- Do we need per-domain thresholds (vehicle vs radar) or a single global percentile?
- Where to surface operator alerts for high-category flags (dashboard vs log only)?
