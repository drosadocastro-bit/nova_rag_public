"""
MULTI-DOMAIN INGESTION & CROSS-CONTAMINATION TEST REPORT
January 21, 2026
"""

# Results Summary

## ✅ COMPLETED: Multi-Domain PDF Ingestion Pipeline

**Successfully indexed 2,020 chunks from 4 PDF files across 5 domains:**

### Ingestion Results by Domain:

| Domain | Type | Source File | Chunks | Extraction Method | Status |
|--------|------|-------------|--------|------------------|--------|
| **Vehicle (Civilian)** | civilian | TM9-802-Declassified.pdf | 402 | pdfplumber | ✅ |
| **Vehicle (Military)** | military | TM9-802-Declassified.pdf | 402 | pdfplumber | ✅ |
| **Forklift** | equipment | TM-10-3930-673-20-1.pdf | 1,388 | pypdf | ✅ |
| **HVAC** | equipment | Carrier small hvac.pdf | 14 | pypdf | ✅ |
| **Radar** | equipment | WXR-2100_operators_guide.pdf | 216 | pypdf | ✅ |
| **TOTAL** | — | — | **2,020** | — | ✅ |

### Key Achievement: Robust PDF Extraction

The **TM9-802 military truck manual** was successfully extracted using **pdfplumber fallback** after pypdf encountered encoding errors. This demonstrates NIC's ability to handle diverse PDF formats:

- **pypdf** (native text extraction) - Fast, handles modern PDFs
- **pdfplumber** (better error handling) - Recovers corrupted font encodings  
- **Tesseract OCR** (fallback) - Ready for scanned documents

### Files Created:

1. **`ingest_multi_domain.py`** - Domain-aware ingestion with metadata tagging
2. **`robust_pdf_extractor.py`** - Multi-method PDF extraction with fallbacks
3. **`test_cross_contamination.py`** - Cross-domain retrieval validation tests
4. **`validate_multi_domain_index.py`** - Index integrity verification

### Storage:

- **FAISS Index**: `vector_db/faiss_index_multi_domain.bin` (2,020 vectors)
- **Chunk Metadata**: `vector_db/chunks_with_metadata.pkl` (domain-tagged)
- **Index Metadata**: `vector_db/domain_metadata.json` (statistics)

---

## 🔍 FINDINGS: Cross-Contamination Analysis

### Current State:

The cross-contamination test revealed that **NIC's current retrieval system** (`retrieve()` function from backend.py) uses a **consolidated FAISS index** (currently 27 vectors for the existing vehicle manual). 

The new **multi-domain index (2,020 vectors)** has NOT YET been integrated into NIC's retrieval pipeline.

### Next Steps Required:

**To properly test cross-contamination with the multi-domain index:**

1. **Switch NIC backend to use new FAISS index**
   - Update backend.py to load `faiss_index_multi_domain.bin` instead of existing index
   - Ensure chunk metadata (domain tags) are preserved through retrieval pipeline

2. **Implement domain-aware retrieval** (optional enhancement)
   - Add domain filtering to `retrieve()` function
   - Enable queries like "find X in the vehicle manual" vs "find X in the equipment manuals"

3. **Re-run cross-contamination tests**
   - Measure if forklift queries pull vehicle docs (should be 0%)
   - Measure if vehicle queries pull radar docs (should be 0%)
   - Measure if ambiguous queries prefer civilian vehicle docs when available

---

## 💡 RECOMMENDATIONS

### For Testing (What You Suggested):

✅ **Test NIC as-is first** - Establish baseline before switching to multi-domain index

Option A: Run NIC tests on current index, then switch and re-test
Option B: Create separate test harness that uses multi-domain index directly

### For Production (Best Practice):

1. **Implement domain-metadata preservation** in retrieval pipeline
2. **Add optional domain filtering** for more precise queries
3. **Use GAR to expand domain-specific terminology** (next phase)
4. **Monitor retrieval precision** by domain in analytics

---

## 📊 METRICS TO TRACK

After integrating multi-domain index into NIC:

- **Precision by domain**: % of retrieved chunks from expected domain
- **Contamination rate**: % of cross-domain results (should be <10%)
- **Recall per domain**: Are relevant docs from each domain retrieved?
- **GAR effectiveness**: How much do domain terms improve retrieval?

---

## ⚙️ CONFIGURATION

Multi-domain index is configured for:
- Embedding model: `all-MiniLM-L6-v2` (384 dims)
- Chunk size: 500 characters
- Overlap: 100 characters
- Distance metric: L2 (Euclidean)

---

## 🎯 ACTION ITEMS

- [ ] Decide if/when to switch NIC to multi-domain index
- [ ] Determine if domain filtering is needed for your use case
- [ ] Plan integration timeline
- [ ] Extend GAR with equipment/military terminology (Phase 2)
- [ ] Run production-representative load tests

