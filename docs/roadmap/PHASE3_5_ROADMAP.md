# Phase 3.5: Neural Advisory Layer - Implementation Roadmap

**Status:** 🚀 IN PROGRESS  
**Start Date:** January 22, 2026  
**Goal:** Introduce neural networks as **advisors** to enhance quality while maintaining deterministic safety guarantees

---

## Mission Statement

Phase 3.5 explores how neural networks can improve retrieval quality, detect anomalies, and streamline compliance—**without ever overriding safety rules**. NNs suggest, log, and enhance. Deterministic rules decide.

**Core Principle:** Advisory, not arbitral. If the NN fails, NIC continues to work perfectly.

---

## Architecture Philosophy

```
Query → NN Anomaly Score (logged, advisory)
     ↓
     Rule-Based Safety Check (deterministic, BLOCKING)
     ↓
     NN Fine-Tuned Embeddings (with BM25 fallback)
     ↓
     Deterministic Retrieval + Evidence Logging
     ↓
     Response with NN-Enhanced Quality + Audit Trail
```

**Key Constraints:**
- NNs are **frozen artifacts** (versioned weights, immutable)
- NNs **never block** queries (log scores only)
- System **degrades gracefully** if NN unavailable (falls back to rules + BM25)
- All NN predictions **logged** with confidence scores for audit

---

## Task Breakdown (10 Tasks)

### Task 1: Update README - Mark Phase 3 Complete ✅ DONE
**Deliverable:** Update Evolution Timeline and Phase 3 section to reflect completion  
**Status:** COMPLETE  
**Files Modified:**
- `README.md` - Updated timeline, Phase 3 section shows completion, Phase 3.5 marked IN PROGRESS
- Linked to `docs/roadmap/PHASE3_COMPLETE.md`

---

### Task 2: Create Phase 3.5 Roadmap ⚡ CURRENT
**Deliverable:** This document (`PHASE3_5_ROADMAP.md`)  
**Status:** IN PROGRESS  
**Purpose:** Comprehensive implementation plan for all 3 neural advisory features

---

### Task 3: Design Fine-Tuning Pipeline
**Goal:** Improve retrieval recall on technical terminology by 15-25%

**Components:**
1. **Training Data Generator** (`scripts/generate_finetuning_data.py`)
   - Extract (question → manual section) pairs from procedures
   - Parse technical manuals to identify:
     - Safety procedures (step-by-step instructions)
     - Diagnostic flowcharts (symptom → action)
     - Parts catalogs (terminology definitions)
   - Generate synthetic questions from procedure headings
   - Create positive/negative pairs for contrastive learning
   - Output: `data/finetuning/training_pairs.jsonl`

2. **Sentence-Transformer Fine-Tuning** (`scripts/finetune_embeddings.py`)
   - Base model: `sentence-transformers/all-MiniLM-L6-v2` (22M params, fast inference)
   - Training approach: Contrastive learning with hard negatives
   - Dataset size: 5,000-10,000 pairs (quality > quantity for safety domains)
   - Validation split: 20% holdout for evaluation
   - Training config:
     - Epochs: 3-5 (prevent overfitting)
     - Learning rate: 2e-5
     - Batch size: 16
     - Loss: MultipleNegativesRankingLoss
   - Output: Versioned model artifact (e.g., `models/nic-embeddings-v1.0/`)

3. **Model Versioning & Deployment** (`core/embeddings/versioned_embeddings.py`)
   - SHA-256 hash of model weights (tamper detection)
   - Version metadata: `models/nic-embeddings-v1.0/model_card.json`
     - Base model name
     - Training corpus hash
     - Training date/commit
     - Benchmark scores (recall@k on validation set)
   - Immutable once deployed (new versions = new directory)

**Evaluation Metrics:**
- Recall@5 improvement (baseline vs fine-tuned)
- Mean Reciprocal Rank (MRR)
- Domain-specific term matching accuracy
- Benchmark on adversarial edge cases (maintain 111/111 pass rate)

**Safety Guarantees:**
- BM25 fallback if fine-tuned model unavailable
- Frozen weights (no online learning)
- Model versioning for reproducibility
- Performance regression alerts (automated tests)

**Success Criteria:**
- 15-25% improvement in recall on technical terminology
- Zero degradation on adversarial tests
- <10ms inference latency overhead
- Full backward compatibility with baseline embeddings

---

### Task 4: Design Anomaly Detection
**Goal:** Flag suspicious query patterns for human review (never auto-block)

**Components:**
1. **Autoencoder Architecture** (`core/safety/anomaly_detector.py`)
   - Lightweight autoencoder (200K params, <5ms inference)
   - Input: Query embedding (384 dims from sentence-transformer)
   - Encoder: 384 → 128 → 32 (bottleneck)
   - Decoder: 32 → 128 → 384 (reconstruction)
   - Loss: Mean Squared Error (MSE) between input and reconstruction
   - Anomaly score: Reconstruction error (higher = more anomalous)

2. **Training Data Collection** (`scripts/collect_query_logs.py`)
   - Extract normal queries from production logs (if available)
   - Synthetic normal queries from manual procedures:
     - "How do I check tire pressure?"
     - "What is the torque spec for head bolts?"
     - "Where is the coolant reservoir?"
   - **No adversarial examples in training** (learn normal distribution only)
   - Dataset size: 10,000-50,000 normal queries
   - Output: `data/anomaly_detection/normal_queries.jsonl`

3. **Anomaly Scoring** (`core/safety/anomaly_scorer.py`)
   - Score incoming queries with autoencoder
   - Threshold calibration: 95th percentile of normal queries
   - Anomaly categories:
     - **Low (score < threshold):** Normal query
     - **Medium (score < threshold + 2σ):** Unusual but valid
     - **High (score ≥ threshold + 2σ):** Suspicious, flag for review
   - **NEVER BLOCK** - log score in evidence chain only

4. **Evidence Chain Integration** (`core/safety/anomaly_evidence.py`)
   - Add `anomaly_score` to evidence chain JSON
   - Include reconstruction error, threshold, category
   - Example:
     ```json
     {
       "anomaly_detection": {
         "score": 0.042,
         "threshold": 0.035,
         "category": "medium",
         "reconstruction_error": 0.042,
         "flagged_for_review": true
       }
     }
     ```

**Detection Patterns (Examples):**
- **Probing:** "List all security vulnerabilities" (out-of-distribution)
- **Reconnaissance:** "What files are in the system?" (not safety-related)
- **Injection Attempts:** Already caught by Phase 2 rules, but anomaly detection provides defense-in-depth
- **Nonsense Queries:** Random characters or extremely long inputs

**Safety Guarantees:**
- Advisory only - **NEVER blocks queries**
- Logged for offline analysis
- Human security team reviews flagged queries
- Deterministic safety rules still enforce blocking

**Success Criteria:**
- Detect 80%+ of synthetic adversarial queries (high anomaly score)
- False positive rate <5% on normal queries
- <5ms inference latency
- Zero impact on query success rate

**Design Doc:** [docs/roadmap/TASK4_ANOMALY_DETECTION_DESIGN.md](docs/roadmap/TASK4_ANOMALY_DETECTION_DESIGN.md)

---

### Task 5: Design Compliance Reporting
**Goal:** Auto-generate audit trails for regulatory review (reduce prep time from days to minutes)

**Components:**
1. **Report Generator** (`core/compliance/report_generator.py`)
   - Input: Evidence chain from retrieval pipeline
   - Output formats: JSON and PDF
   - Report structure:
     - **Session Metadata:** ID, timestamp, operator (if authenticated), system version
     - **Query Details:** Question text, domain, intent classification
     - **Retrieval Evidence:** Sources retrieved, confidence scores, reranking decisions
     - **Safety Checks:** Injection detection results, risk assessment, anomaly score
     - **Response Details:** Answer text, citations, extractive fallback used?
     - **Audit Trail:** Full evidence chain (router → GAR → rerank → selection)
     - **Tamper Detection:** SHA-256 hash of report content

2. **PDF Generation** (`core/compliance/pdf_exporter.py`)
   - Use ReportLab library for professional PDF output
   - Include:
     - Cover page with session summary
     - Detailed audit trail (one page per query)
     - Appendix with configuration settings
     - Digital signature (SHA-256 hash) on final page
   - Output: `compliance_reports/session_<id>_<timestamp>.pdf`

3. **Tamper-Evident Signatures** (`core/compliance/signature.py`)
   - SHA-256 hash of report JSON (before PDF conversion)
   - Include in PDF footer: "Report Hash: sha256:abc123..."
   - Verification tool: `python scripts/verify_report.py <report.pdf>`
   - Detects any modification to report content post-generation

4. **Batch Reporting** (`scripts/generate_batch_reports.py`)
   - Generate reports for date range (e.g., last 30 days)
   - Filter by domain, confidence threshold, anomaly score
   - Aggregate statistics:
     - Total queries processed
     - Average confidence scores
     - Safety check trigger rates
     - Top domains queried
     - Anomaly score distribution

**Report Use Cases:**
- **Regulatory Audit:** Demonstrate due diligence in safety-critical deployment
- **Security Review:** Identify attack patterns from anomaly scores
- **Quality Assurance:** Track confidence trends, identify low-scoring queries
- **Operator Training:** Review sessions for compliance with procedures

**Success Criteria:**
- Generate PDF report in <2 seconds
- Tamper detection works (modified PDFs fail verification)
- Reports include all required audit fields
- Batch reporting handles 10,000+ queries efficiently

---

## Task 6: Implement Training Data Generator
**Deliverable:** `scripts/generate_finetuning_data.py` (~300 lines)

**Implementation Steps:**

1. **Parse Technical Manuals**
   - Load corpus from `data/` directory
   - Extract structured content:
     - Section headings (e.g., "Brake System Inspection")
     - Step-by-step procedures (numbered/bulleted lists)
     - Diagnostic tables (symptom → cause → action)
     - Parts lists (term → definition)

2. **Generate Question-Answer Pairs**
   - **From Headings:** "How do I perform brake system inspection?" → section content
   - **From Procedures:** "What are the steps to replace brake pads?" → procedure text
   - **From Tables:** "What causes brake fade?" → table row (cause + action)
   - **Synthetic Variations:**
     - Paraphrase questions (e.g., "inspect brakes" → "check brake system")
     - Add domain terms (e.g., "hydraulic" instead of "fluid")

3. **Create Negative Examples**
   - Hard negatives: Similar but incorrect sections (e.g., "Engine Oil Change" for "Brake Inspection")
   - Cross-domain negatives: Vehicle procedure for forklift query
   - Purpose: Contrastive learning (push apart irrelevant content)

4. **Quality Filtering**
   - Remove duplicates (exact or near-duplicate pairs)
   - Filter short answers (<50 chars)
   - Validate question-answer relevance (basic keyword overlap)

5. **Output Format** (JSONL)
   ```jsonl
   {"query": "How do I check tire pressure?", "positive": "Locate valve stem...", "negative": "Engine oil check procedure...", "domain": "vehicle_civilian"}
   {"query": "What is torque spec for head bolts?", "positive": "Torque: 85 ft-lbs...", "negative": "Brake pad replacement...", "domain": "vehicle_military"}
   ```

**Validation:**
- Generate 5,000-10,000 pairs from existing corpus
- Manual review of 100 random pairs (quality check)
- Domain distribution matches corpus (no bias)

**Runbook:** [docs/roadmap/TASK6_TRAINING_DATA_RUNBOOK.md](docs/roadmap/TASK6_TRAINING_DATA_RUNBOOK.md)

---

## Task 7: Implement Fine-Tuning Script ⚡ IN PROGRESS
**Status:** STARTED - Script created, ready for training  
**Deliverable:** `scripts/finetune_embeddings.py` (420 lines) + execution runbook  
**Execution Guide:** [docs/roadmap/TASK7_FINETUNING_RUNBOOK.md](docs/roadmap/TASK7_FINETUNING_RUNBOOK.md)

**Implementation Complete:**

1. ✅ **Data Pipeline**
   - TripletsDataset class: Loads (query, positive, negative) triplets
   - DataLoader with automatic shuffling, batch_size=32
   - Train/Val split: 90/10 stratified by domain
   - Handles 4,010 pairs from Task 6 output

2. ✅ **Model Setup**
   - Load base: `sentence-transformers/all-MiniLM-L6-v2` (384 dims, 22M params)
   - Layer freezing: Bottom 10/12 transformer blocks frozen
   - Trainable params: ~1.2M (5.5% of total)
   - Reduces overfitting on domain-specific data

3. ✅ **Training Configuration**
   - Loss: MultipleNegativesRankingLoss (contrastive learning)
   - Optimizer: AdamW with weight decay
   - LR Schedule: Cosine Annealing with warm restarts
   - Training: 5 epochs, 32 batch size, 2e-5 learning rate
   - Validation: Every 100 steps with domain breakdown

4. ✅ **Evaluation Metrics**
   - Per-domain Recall@5 (% top-5 contains positive)
   - Per-domain MRR (mean reciprocal rank)
   - Early stopping on best validation metric
   - Model checkpointing: saves epoch + best checkpoints

5. ✅ **Output Artifacts**
   - Model: `models/nic-embeddings-v1.0/pytorch_model.bin`
   - Metadata: `models/nic-embeddings-v1.0/metadata.json`
   - Model Card: `models/nic-embeddings-v1.0/README.md` (human-readable)
   - Training Log: `models/nic-embeddings-v1.0/training.log`
   - Checkpoints: `checkpoint-epoch-*/`, `checkpoint-best/`

**Running the Training:**
```bash
python scripts/finetune_embeddings.py \
  --data-file data/finetuning/training_pairs.jsonl \
  --output-dir models/nic-embeddings-v1.0 \
  --epochs 5 \
  --batch-size 32 \
  --learning-rate 2e-5 \
  --freeze-layers 10 \
  --seed 42
```

Expected runtime:
- GPU: 40-60 minutes
- CPU: 2-4 hours

**Validation Success Criteria:**
- Fine-tuning completes in <30 minutes (on CPU)
- Recall@5 improves by 15-25%
- Inference latency <10ms per query
- Model artifact saved with version hash

---

## Task 8: Implement Anomaly Detector
**Deliverable:** `core/safety/anomaly_detector.py` (~250 lines)

**Implementation Steps:**

1. **Define Autoencoder**
   ```python
   import torch
   import torch.nn as nn
   
   class QueryAnomalyDetector(nn.Module):
       def __init__(self, input_dim=384):
           super().__init__()
           self.encoder = nn.Sequential(
               nn.Linear(input_dim, 128),
               nn.ReLU(),
               nn.Linear(128, 32),
               nn.ReLU()
           )
           self.decoder = nn.Sequential(
               nn.Linear(32, 128),
               nn.ReLU(),
               nn.Linear(128, input_dim)
           )
       
       def forward(self, x):
           encoded = self.encoder(x)
           decoded = self.decoder(encoded)
           return decoded
       
       def anomaly_score(self, x):
           reconstructed = self.forward(x)
           mse = torch.mean((x - reconstructed) ** 2, dim=1)
           return mse.item()
   ```

2. **Train on Normal Queries**
   - Load normal query embeddings
   - Train autoencoder to minimize reconstruction error
   - Save model: `models/anomaly_detector_v1.0.pth`
   - Save threshold: 95th percentile of training errors

3. **Score Incoming Queries**
   ```python
   def score_query(query_text, embedding_model, anomaly_model, threshold):
       # Embed query
       embedding = embedding_model.encode(query_text)
       
       # Score with autoencoder
       score = anomaly_model.anomaly_score(embedding)
       
       # Categorize
       if score < threshold:
           category = "low"
       elif score < threshold + 2 * sigma:
           category = "medium"
       else:
           category = "high"
       
       return {
           "score": score,
           "threshold": threshold,
           "category": category,
           "flagged_for_review": category in ["medium", "high"]
       }
   ```

4. **Integrate with Evidence Chain**
   - Add anomaly score to `EvidenceChain` dataclass
   - Log in evidence JSON for every query
   - Never block - advisory only

**Validation:**
- Train on 10,000 normal queries
- Test on 100 synthetic adversarial queries (expect high scores)
- Test on 1,000 normal queries (expect low scores, <5% false positives)
- Inference <5ms per query

---

## Task 9: Implement Compliance Reporter
**Deliverable:** `core/compliance/report_generator.py` (~350 lines)

**Implementation Steps:**

1. **Define Report Schema**
   ```python
   from dataclasses import dataclass
   from typing import List, Optional
   
   @dataclass
   class ComplianceReport:
       session_id: str
       timestamp: str
       operator: Optional[str]
       system_version: str
       
       query: str
       domain: str
       intent_classification: str
       
       retrieval_sources: List[str]
       confidence_scores: List[float]
       reranking_decisions: dict
       
       safety_checks: dict
       anomaly_score: float
       
       answer: str
       citations: List[str]
       extractive_fallback_used: bool
       
       evidence_chain: dict
       report_hash: str  # SHA-256 of JSON content
   ```

2. **Generate JSON Report**
   ```python
   def generate_json_report(evidence_chain, response):
       report = ComplianceReport(
           session_id=evidence_chain.session_id,
           timestamp=datetime.now().isoformat(),
           # ... populate all fields from evidence_chain
       )
       
       # Compute hash
       report_json = dataclasses.asdict(report)
       report_hash = hashlib.sha256(
           json.dumps(report_json, sort_keys=True).encode()
       ).hexdigest()
       
       report.report_hash = report_hash
       return report
   ```

3. **Generate PDF Report**
   ```python
   from reportlab.lib.pagesizes import letter
   from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
   from reportlab.lib.styles import getSampleStyleSheet
   
   def generate_pdf_report(report, output_path):
       doc = SimpleDocTemplate(output_path, pagesize=letter)
       story = []
       styles = getSampleStyleSheet()
       
       # Cover page
       story.append(Paragraph("NIC Compliance Report", styles['Title']))
       story.append(Spacer(1, 12))
       story.append(Paragraph(f"Session: {report.session_id}", styles['Normal']))
       story.append(Paragraph(f"Date: {report.timestamp}", styles['Normal']))
       
       # Query details
       story.append(Spacer(1, 24))
       story.append(Paragraph("Query Details", styles['Heading2']))
       story.append(Paragraph(f"Question: {report.query}", styles['Normal']))
       story.append(Paragraph(f"Domain: {report.domain}", styles['Normal']))
       
       # Evidence trail
       # ... add retrieval sources, safety checks, anomaly score
       
       # Footer with hash
       story.append(Spacer(1, 24))
       story.append(Paragraph(
           f"Report Hash (SHA-256): {report.report_hash}",
           styles['Code']
       ))
       
       doc.build(story)
   ```

4. **Verification Tool**
   ```python
   def verify_report(pdf_path):
       # Extract hash from PDF footer
       # Recompute hash from report content
       # Compare
       return hash_matches
   ```

**Validation:**
- Generate 10 sample reports
- Verify tamper detection (modify PDF → verification fails)
- PDF generation <2 seconds
- Batch report 1,000 queries in <10 seconds

---

## Task 10: Integration & Validation
**Deliverable:** End-to-end Phase 3.5 integration with comprehensive testing

**Components:**

1. **Integrated Pipeline** (`core/phase3_5/neural_advisory.py`)
   ```python
   class NeuralAdvisoryLayer:
       def __init__(self):
           # Load versioned models (with fallback)
           self.finetuned_embeddings = load_finetuned_embeddings()
           self.anomaly_detector = load_anomaly_detector()
           self.compliance_reporter = ComplianceReporter()
       
       def enhance_query(self, query, evidence_chain):
           # Score query (advisory - never blocks)
           anomaly_score = self.anomaly_detector.score(query)
           evidence_chain.anomaly_score = anomaly_score
           
           # Use fine-tuned embeddings (with BM25 fallback)
           try:
               embeddings = self.finetuned_embeddings.encode(query)
           except Exception as e:
               logger.warning("Fine-tuned embeddings failed, using baseline")
               embeddings = baseline_embeddings.encode(query)
           
           return embeddings, evidence_chain
       
       def generate_compliance_report(self, evidence_chain, response):
           return self.compliance_reporter.generate(evidence_chain, response)
   ```

2. **Flask Integration** (update `nova_flask_app.py`)
   ```python
   # Initialize Phase 3.5 (optional - graceful degradation)
   try:
       neural_advisory = NeuralAdvisoryLayer()
       logger.info("Phase 3.5 Neural Advisory Layer: ENABLED")
   except Exception as e:
       neural_advisory = None
       logger.warning(f"Phase 3.5 unavailable: {e}")
   
   @app.route("/api/ask", methods=["POST"])
   def ask():
       query = request.json.get("question")
       
       # Phase 3.5: Anomaly scoring (advisory)
       if neural_advisory:
           embeddings, evidence = neural_advisory.enhance_query(query, evidence)
       else:
           embeddings = baseline_embeddings.encode(query)
       
       # Continue with normal pipeline...
       # ...
       
       # Phase 3.5: Generate compliance report
       if neural_advisory:
           report = neural_advisory.generate_compliance_report(evidence, response)
   ```

3. **Configuration Flags**
   ```bash
   # Enable/disable Phase 3.5 features
   export NOVA_USE_FINETUNED_EMBEDDINGS=1   # Default: 0
   export NOVA_ENABLE_ANOMALY_DETECTION=1   # Default: 0
   export NOVA_AUTO_COMPLIANCE_REPORTS=1    # Default: 0
   
   # Model paths
   export NOVA_FINETUNED_MODEL_PATH="models/nic-embeddings-v1.0"
   export NOVA_ANOMALY_MODEL_PATH="models/anomaly_detector_v1.0.pth"
   ```

4. **Comprehensive Testing**
   - **Unit Tests:** 30+ tests for each component
     - Fine-tuned embeddings: recall improvements, fallback behavior
     - Anomaly detector: normal vs adversarial queries, <5% false positives
     - Compliance reporter: JSON/PDF generation, tamper detection
   
   - **Integration Tests:**
     - End-to-end pipeline with Phase 3.5 enabled
     - Graceful degradation when Phase 3.5 unavailable
     - Verify advisory-only behavior (NNs never block)
   
   - **Adversarial Validation:**
     - Maintain 111/111 pass rate on existing tests
     - No regressions in retrieval quality
     - Anomaly detector flags synthetic attacks
   
   - **Performance Benchmarks:**
     - Latency overhead <15ms with all Phase 3.5 features
     - Memory footprint <200MB for all models
     - Compliance report generation <2s

5. **Documentation**
   - Update `docs/architecture/PHASE3_5_ARCHITECTURE.md`
   - Create `docs/deployment/NEURAL_ADVISORY_GUIDE.md`
   - Add examples to `examples/phase3_5_usage.py`
   - Update main README with Phase 3.5 summary

**Success Criteria:**
- All 3 neural advisory features operational
- Zero impact on safety guarantees (rules still decide)
- Graceful degradation validated
- Performance targets met
- Full documentation complete

---

## Development Timeline

**Week 1: Architecture & Data Prep**
- Tasks 1-2: README updates, roadmap creation ✅
- Task 3: Fine-tuning pipeline design
- Task 6: Training data generator (5,000+ pairs)

**Week 2: Model Training**
- Task 7: Fine-tune embeddings (15-25% recall improvement)
- Task 8: Train anomaly detector (on normal query distribution)

**Week 3: Compliance & Integration**
- Task 9: Compliance reporter (JSON/PDF with tamper detection)
- Task 10: End-to-end integration, testing, documentation

**Estimated Effort:** 3 weeks, ~3,000 lines of code + docs

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Fine-tuning overfits on small dataset** | Poor generalization | Freeze early layers, use hard negatives, validate on holdout |
| **Anomaly detector has high false positives** | User frustration | Calibrate threshold at 95th percentile, tune sigma, human review |
| **Fine-tuned embeddings degrade safety tests** | Safety regression | Benchmark on 111 adversarial tests before deployment, fallback to baseline |
| **Compliance reports are too slow** | User experience | Async generation, background worker, cache common queries |
| **Models increase memory footprint** | Deployment constraints | Use lightweight models (<200MB total), lazy loading, offload to disk |

---

## Success Metrics

| Metric | Target | Validation Method |
|--------|--------|-------------------|
| **Recall@5 Improvement** | +15-25% | Benchmark on validation set |
| **Anomaly Detection Accuracy** | 80%+ on adversarial | Synthetic attack dataset |
| **False Positive Rate** | <5% | Test on 1,000 normal queries |
| **Inference Latency** | <15ms total overhead | Performance profiling |
| **Compliance Report Generation** | <2s per report | Timed benchmarks |
| **Adversarial Test Pass Rate** | 111/111 maintained | Run existing test suite |
| **Graceful Degradation** | System works without Phase 3.5 | Disable models, verify functionality |

---

## Lessons Learned (To Be Updated)

This section will capture design decisions and trade-offs discovered during implementation:

1. **[To be filled during Task 6]** - Training data quality vs. quantity
2. **[To be filled during Task 7]** - Fine-tuning hyperparameter choices
3. **[To be filled during Task 8]** - Anomaly threshold calibration
4. **[To be filled during Task 9]** - Compliance report format decisions
5. **[To be filled during Task 10]** - Integration challenges and solutions

---

## Next Steps After Phase 3.5

**Phase 4 (Future):**
- Multi-modal retrieval (vision + text for diagram-heavy manuals)
- Federated learning for multi-site deployments (preserve air-gap)
- Continuous validation framework (automated regression testing)

**Production Hardening:**
- A/B testing framework for embedding models
- Model performance monitoring (drift detection)
- Automated retraining pipeline (when corpus scales)

---

## References

- [Phase 3 Completion Documentation](PHASE3_COMPLETE.md)
- [Safety Model](../safety/SAFETY_MODEL.md)
- [System Architecture](../architecture/SYSTEM_ARCHITECTURE.md)
- [Evidence Chain Specification](../architecture/EVIDENCE_CHAIN.md)

---

**Phase 3.5: Proving that neural networks can enhance safety-critical systems when used as advisors, not arbiters.**
