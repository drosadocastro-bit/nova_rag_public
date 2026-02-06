# RADAR Corpus Expansion Blueprint
# ===================================
# Goal: Expand RADAR corpus from 7.39 MB → 50+ MB
# Timeline: 2-3 weeks
# Status: Planning document (to be implemented)

## 1. RADAR DOCUMENTATION SOURCES

### Tier 1: Existing (7.39 MB)
- wxr-2100_weatherradar_operators_guide.pdf (already in repo)
- Historical military RADAR manuals (if available)

### Tier 2: Synthetic Procedures (Generate ~20 MB)
**What to create:**
- RADAR system diagnostics (50+ procedures)
  - Receiver chain troubleshooting
  - Transmitter power issues
  - Antenna alignment procedures
  - Signal path diagnostics
  
- RADAR operational scenarios (100+ Q&A pairs)
  - "What does a PRF of 1000 Hz mean?"
  - "How do I interpret range ambiguity?"
  - "Steps to calibrate antenna tilt?"
  - "Symptoms of magnetron failure?"

- Maintenance checklists (40+ items)
  - Preventive maintenance for RADAR systems
  - Component replacement procedures
  - Waveguide cleaning protocols
  - Calibration validation procedures

- Safety procedures (30+ scenarios)
  - RF hazard warning placements
  - Emergency power-down procedures
  - Microwave oven syndrome prevention
  - Radiation dose monitoring

**Tools to use:**
- Use GPT or Mistral Nemo to generate realistic procedures based on:
  - Actual RADAR system datasheets
  - FAA technical manuals (public domain)
  - IEEE RADAR standards (can paraphrase)
  
**Quality control:**
- Manual review of first 20% (flag errors)
- Consistency check (cross-reference similar procedures)
- Domain expert review (if available)

### Tier 3: Real Documentation (Acquire ~15 MB)
- FAA RADAR technical standards (public domain)
  - "14 CFR Part 97" (Standard Instrument Approach Procedures)
  - ICAO Annex 10 (Aeronautical Telecommunications)
  - AC 150/5030-4 (Airport Radar Facilities)
  
- Vendor manuals (with permission)
  - Raytheon RADAR operator manuals
  - Thales RADAR system guides
  - Leonardo (formerly Finmeccanica) technical specs
  
- Research papers (public domain)
  - IEEE Transactions on Aerospace and Electronic Systems
  - Defense Technical Information Center (DTIC) docs

### Tier 4: Multimodal Preparation (Diagrams → OCR)
- Extract schematics from RADAR manuals as images
- Use OCR to convert to text descriptions
- Pair OCR output with diagram interpretation queries
  - "What is this circuit diagram showing?"
  - "How are these components connected?"

---

## 2. IMPLEMENTATION PLAN

### Phase 1: Synthetic Content Generation (1 week)
```bash
# Step 1: Create template for procedures
python scripts/generate_radar_procedures.py \
  --templates data/radar/procedure_templates.json \
  --output data/radar/synthetic_procedures/ \
  --count 50

# Step 2: Generate Q&A pairs
python scripts/generate_radar_qa.py \
  --source data/radar/wxr-2100_operators_guide.pdf \
  --output data/radar/synthetic_qa.jsonl \
  --count 100

# Step 3: Add to fine-tuning data
python scripts/add_to_training_pairs.py \
  --input data/radar/synthetic_procedures/ \
  --output data/finetuning/training_pairs.jsonl \
  --append
```

### Phase 2: Source Acquisition (1 week)
```bash
# Step 1: Download public domain RADAR docs
curl https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_150_5030-4.pdf \
  --output data/radar/faa_ac_150_5030_4.pdf

# Step 2: Extract and chunk
python scripts/chunk_pdf.py \
  --input data/radar/faa_ac_150_5030_4.pdf \
  --output data/radar/faa_chunks/ \
  --chunk_size 1000 \
  --overlap 200

# Step 3: Convert to JSONL
python scripts/chunks_to_jsonl.py \
  --input data/radar/faa_chunks/ \
  --output data/radar/faa_training_pairs.jsonl
```

### Phase 3: Index Rebuild (2 days)
```bash
# Step 1: Reindex with expanded corpus
python -c "
from core.retrieval.retrieval_engine import build_index
build_index(force_rebuild=True)
"

# Step 2: Verify index
python verify_offline_requirements.py

# Step 3: Run quick test
python quick_validation.py --domain radar
```

---

## 3. CORPUS EXPANSION TARGETS

| Domain | Current | Target | Type | Priority |
|--------|---------|--------|------|----------|
| RADAR | 7.39 MB | 50 MB | +577% | P0 (Critical) |
| Aerospace | 71.95 MB | 100 MB | +39% | P1 (Nice-to-have) |
| Vehicle | 207.48 MB | 250 MB | +21% | P1 (Nice-to-have) |
| Electronics | 4.98 MB | 20 MB | +301% | P2 (Future) |
| Nuclear | 3.36 MB | 25 MB | +644% | P2 (Future) |

---

## 4. QUALITY METRICS

**Before expansion:**
- RADAR adversarial pass rate: ~70%
- Avg retrieval confidence: 0.68
- Coverage (queries with relevant docs): ~65%

**Target after expansion:**
- RADAR adversarial pass rate: ≥80% (↑10%)
- Avg retrieval confidence: 0.78 (↑0.10)
- Coverage: ≥85% (↑20%)

**Measurement:**
```bash
python nic_multidom_adversarial_test.py --domain radar
```

---

## 5. FILE STRUCTURE (Post-Expansion)

```
data/
├── radar/                           (50 MB)
│   ├── wxr-2100_weatherradar_operators_guide.pdf
│   ├── faa_ac_150_5030_4.pdf
│   ├── synthetic_procedures/        (auto-generated)
│   │   ├── receiver_diagnostics.txt
│   │   ├── antenna_alignment.txt
│   │   └── ...
│   ├── faa_chunks/                  (auto-generated)
│   │   ├── chunk_0001.json
│   │   ├── chunk_0002.json
│   │   └── ...
│   └── README.md                    (source attribution)
├── finetuning/
│   └── training_pairs.jsonl         (+4000 RADAR pairs)
└── [other domains...]
```

---

## 6. CONSIDERATIONS

### Legal/Licensing
- FAA docs: Public domain ✅
- ICAO docs: Paid, but paraphrasing allowed ⚠️
- IEEE papers: Citation required ✅
- Vendor manuals: Requires permission ❌ (skip)

### Technical
- Synthetic data quality: Requires human audit for first 20%
- OCR accuracy: ~85-90% (human review needed)
- Chunk overlap: Use 200 tokens to maintain context
- Deduplication: Remove identical/near-identical chunks

### Maintenance
- Version control training data (git-lfs for large files)
- Document all synthetic data generators
- Create fallback index (in case new index is worse)
- A/B test before deploying

---

## 7. SUCCESS CRITERIA

✅ **Phase 1 Complete When:**
- 50+ synthetic procedures generated and reviewed
- 100+ Q&A pairs added to training data
- Fine-tuning script runs without errors
- Test model trained and evaluated

✅ **Phase 2 Complete When:**
- 15+ MB of real RADAR docs acquired
- PDFs chunked and formatted as JSONL
- No copyright/licensing issues
- Attribution documented

✅ **Phase 3 Complete When:**
- New index built successfully
- Adversarial pass rate improves ≥5%
- Retrieval confidence increases
- No regression on other domains

---

## 8. TIMELINE

| Week | Tasks | Owner |
|------|-------|-------|
| 1 | Generate synthetic procedures, create Q&A pairs | AI/Scripts |
| 1 | Acquire public RADAR documentation | Manual |
| 2 | Chunk PDFs, convert to training format | Scripts |
| 2 | Fine-tune embeddings model | ML Pipeline |
| 2 | Rebuild FAISS index | Pipeline |
| 3 | Run full adversarial test suite | CI/CD |
| 3 | Compare baselines, document improvement | Analysis |
| 3 | Deploy to production (staged) | DevOps |

**Total: 3 weeks → +40% corpus coverage improvement**

---

## 9. ROLLBACK PLAN

If new corpus causes regression:
```bash
# Restore previous index
git checkout HEAD~1 -- vector_db/nic_index.faiss

# Verify old index
python quick_validation.py

# Identify problem
# - Too many false positives?
# - Synthetic data quality issue?
# - Chunk size wrong?
# - Overlap too high?

# Fix and retry
```

---

## NEXT STEPS

1. **Immediate (This week):**
   - [ ] Create `scripts/generate_radar_procedures.py`
   - [ ] Create `scripts/generate_radar_qa.py`
   - [ ] Review synthetic data quality

2. **Short-term (Weeks 1-2):**
   - [ ] Acquire public RADAR documentation
   - [ ] Chunk and convert to JSONL
   - [ ] Fine-tune embeddings

3. **Medium-term (Week 3):**
   - [ ] Rebuild index
   - [ ] Run adversarial tests
   - [ ] Deploy and monitor

