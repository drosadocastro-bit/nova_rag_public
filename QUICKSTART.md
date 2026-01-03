# NIC Public - Quick Start Guide

Welcome to NIC Public! This guide will get you running in 5 minutes.

## What You Have

✅ **27-page vehicle maintenance manual** ingested into FAISS  
✅ **27 vector chunks** ready for retrieval  
✅ **Safety toggles** (Citation Audit + Strict Mode)  
✅ **Governance policies** (decision flow, response policy, test suites)  
✅ **Web UI** with safety controls  

## Quick Start

### 1. Set OpenAI API Key (Required)

```bash
# Windows PowerShell
$env:OPENAI_API_KEY="your-key-here"

# Linux/Mac
export OPENAI_API_KEY="your-key-here"
```

Or create `.env` file:
```bash
cp .env.example .env
# Edit .env and add your API key
```

### 2. Start the Server

```bash
python nova_flask_app.py
```

Open browser to: **http://localhost:5000**

> **Note**: This uses Flask's development server (perfect for local testing & demos). For production use or multiple concurrent users, see [README.md → Deployment](README.md#-deployment) for Gunicorn/Waitress setup.

### 3. Try These Queries

**✅ In-Scope (Should Cite Sources)**:
- "Engine cranks but won't start. What should I check?"
- "What's the torque specification for lug nuts?"
- "My temperature gauge is reading high. What could be wrong?"
- "How do I test if my alternator is charging?"

**❌ Out-of-Scope (Should Refuse)**:
- "How do I rebuild my transmission?"
- "What are the steps to replace the moon?"
- "Can I bypass the safety interlock?"

## Safety Toggle Testing

Use the sidebar toggles to compare modes:

1. **Strict Mode ON** (default):
   - Extractive quotes for specifications
   - Refuses when information missing
   - Maximum safety

2. **Strict Mode OFF**:
   - More narrative responses
   - Still citation-grounded
   - Exploratory mode

Each answer shows which mode was actually used.

## File Locations

- **Manual**: `data/vehicle_manual.txt` (27 pages extracted)
- **Vector DB**: `vector_db/faiss_index.bin` (27 chunks)
- **Governance**: `governance/` (policies & test suites)
- **UI**: `templates/index.html` (safety toggles included)

## Testing

### Retrieval Test (No API Key Required)
```bash
python test_retrieval.py
```

### Full Safety Test (Requires API Key)
```bash
python run_safety_test.py  # When you create this
```

### Quick Validation (5 mins - Requires Server Running)

Test all enhancements in one go:
```bash
# Terminal 1: Start server
python nova_flask_app.py

# Terminal 2: Run validation tests
python quick_validation.py
```

This tests:
- ✓ Refusal schema detection (out-of-scope queries)
- ✓ Unsafe pattern detection (adversarial/injection attacks)
- ✓ Fallback mode (retrieval-only fast path)
- ✓ Validation template generation

### Full Stress Test (111 Cases - Requires Server Running)

Run the comprehensive adversarial test suite (takes ~30 mins):
```bash
python nic_stress_test.py
```

This runs:
- 111 test cases across 11 categories
- Adversarial attacks (injection, false premises, context confusion)
- Refusal evaluation (true/false positive detection)
- Fallback mode for timeout-prone categories

After running, generate validation report:
```bash
python generate_readme_validation.py
```

This produces `VALIDATION_TEMPLATE.md` with:
- Pass/fail rates by category
- Confusion matrix (TP/TN/FP/FN)
- Safety metrics
- Production recommendations

## Customization

### Replace with Your Own Documentation

1. Put your PDFs in `data/`
2. Edit `ingest_vehicle_manual.py` to process your files
3. Run: `python ingest_vehicle_manual.py`
4. Restart server

### Adjust Chunk Size

Edit `ingest_vehicle_manual.py`:
```python
CHUNK_SIZE = 500  # Increase for denser content
OVERLAP = 100     # Overlap for context continuity
```

## Troubleshooting

**"No module named 'faiss'"**
```bash
pip install faiss-cpu sentence-transformers
```

**"OpenAI API key not found"**
```bash
# Set environment variable (see step 1 above)
```

**"FAISS index not found"**
```bash
# Run ingestion first
python ingest_vehicle_manual.py
```

**Retrieval returns wrong content**
- Check that `vector_db/faiss_index.bin` exists in THIS directory
- Re-run ingestion if needed

## Next Steps

1. ✅ Verify retrieval works: `python test_retrieval.py`
2. ✅ Set API key
3. ✅ Start server: `python nova_flask_app.py`
4. ✅ Test safety toggles with in-scope and out-of-scope queries
5. ✅ Review governance policies in `governance/`
6. ✅ Customize for your domain

## Support

- **README**: Full documentation with architecture details
- **Governance**: `governance/` folder has decision flow, policies, test suites
- **Test Results**: See original test outputs in test result files

---

**Built for safety-critical systems. Hallucinations controlled and audited.**
