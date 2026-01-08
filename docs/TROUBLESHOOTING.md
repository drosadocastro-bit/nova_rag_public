# Troubleshooting Guide

Common issues, diagnostics, and solutions for the NIC RAG system. This guide helps you identify and resolve operational problems quickly.

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Ollama Connection Issues](#ollama-connection-issues)
3. [FAISS Index Problems](#faiss-index-problems)
4. [Cache Verification Failures](#cache-verification-failures)
5. [Low Confidence Scores](#low-confidence-scores)
6. [Memory Issues](#memory-issues)
7. [Network Connectivity](#network-connectivity)
8. [Model Loading Failures](#model-loading-failures)
9. [Database/Index Rebuild](#databaseindex-rebuild)
10. [Performance Issues](#performance-issues)
11. [Authentication Problems](#authentication-problems)
12. [Python Environment Issues](#python-environment-issues)

---

## Quick Diagnostics

### System Health Check

Run this quick diagnostic before detailed troubleshooting:

```bash
# Check Ollama status
curl http://127.0.0.1:11434/api/tags

# Check NIC API
curl http://127.0.0.1:5000/api/status

# Verify index files exist
ls -lh vector_db/vehicle_index.faiss
ls -lh vector_db/vehicle_docs.jsonl

# Check Python environment
python -c "import faiss, torch, sentence_transformers; print('OK')"
```

### Common Symptoms and Quick Fixes

| Symptom | Likely Cause | Quick Fix |
|---------|-------------|-----------|
| "Connection refused" on port 5000 | Flask not running | `python nova_flask_app.py` |
| "Ollama connection failed" | Ollama not running | `ollama serve` or start Ollama app |
| "Index not loaded" | FAISS files missing | Run `python ingest_vehicle_manual.py` |
| Very slow responses (>30s) | Large model on CPU | Switch to smaller model (3B or 1B) |
| Out of memory errors | Model too large for RAM | Reduce model size or disable features |
| Empty/wrong answers | Index out of date | Rebuild index with current corpus |

---

## Ollama Connection Issues

### Symptom: "Ollama connection failed"

**Error Messages:**
```
Connection refused
Failed to connect to Ollama at http://127.0.0.1:11434
ollama: false in /api/status response
```

### Diagnosis Steps

1. **Check if Ollama is running:**
   ```bash
   # macOS/Linux
   ps aux | grep ollama
   
   # Windows PowerShell
   Get-Process | Where-Object {$_.ProcessName -like "*ollama*"}
   ```

2. **Test Ollama API directly:**
   ```bash
   curl http://127.0.0.1:11434/api/tags
   # Should return JSON with model list
   ```

3. **Check Ollama port:**
   ```bash
   # macOS/Linux
   netstat -an | grep 11434
   
   # Windows PowerShell
   netstat -an | Select-String 11434
   ```

### Solutions

**Solution 1: Start Ollama**

```bash
# macOS/Linux (background service)
ollama serve

# Windows (start Ollama desktop app)
# Or run: ollama serve in PowerShell
```

**Solution 2: Verify Model is Downloaded**

```bash
# List available models
ollama list

# Download required model if missing
ollama pull llama3.2:8b

# Test model works
ollama run llama3.2:8b "hello"
```

**Solution 3: Check Custom Ollama URL**

If using custom Ollama location:

```bash
# Set environment variable
export OLLAMA_BASE_URL=http://localhost:11434/v1  # macOS/Linux
$env:OLLAMA_BASE_URL="http://localhost:11434/v1"  # Windows PowerShell
```

**Solution 4: Firewall/Port Blocking**

```bash
# Check if port is blocked
telnet 127.0.0.1 11434

# macOS/Linux: Temporarily disable firewall
sudo ufw allow 11434  # Ubuntu/Debian
sudo firewall-cmd --add-port=11434/tcp  # RHEL/CentOS

# Windows: Add firewall exception
# Control Panel → Windows Defender Firewall → Advanced Settings → Inbound Rules
```

**Solution 5: Restart Ollama**

```bash
# macOS/Linux
pkill ollama
ollama serve

# Windows
# Close Ollama app, restart from Start Menu
```

---

## FAISS Index Problems

### Symptom: "Index not loaded" or "vector_index.faiss not found"

**Error Messages:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'vector_db/vehicle_index.faiss'
FAISS index file not found
index_loaded: false in /api/status
```

### Diagnosis Steps

1. **Check if index files exist:**
   ```bash
   ls -lh vector_db/
   # Should contain:
   # - vehicle_index.faiss
   # - vehicle_docs.jsonl
   # - (optional) vehicle_vision_embeddings.pt
   ```

2. **Check index file permissions:**
   ```bash
   # macOS/Linux
   ls -l vector_db/vehicle_index.faiss
   
   # Should be readable (e.g., -rw-r--r--)
   ```

3. **Verify index integrity:**
   ```python
   import faiss
   index = faiss.read_index("vector_db/vehicle_index.faiss")
   print(f"Index loaded: {index.ntotal} vectors")
   # Should print number > 0
   ```

### Solutions

**Solution 1: Build Index from Scratch**

```bash
# Ensure data/ directory has PDF documents
ls data/*.pdf

# Run ingestion script
python ingest_vehicle_manual.py

# Verify index created
ls -lh vector_db/vehicle_index.faiss
```

**Solution 2: Fix File Permissions**

```bash
# macOS/Linux
chmod 644 vector_db/vehicle_index.faiss
chmod 644 vector_db/vehicle_docs.jsonl

# Windows (PowerShell as Administrator)
icacls vector_db\vehicle_index.faiss /grant Everyone:R
```

**Solution 3: Index Corruption Recovery**

If index is corrupted:

```bash
# Backup corrupted index
mv vector_db/vehicle_index.faiss vector_db/vehicle_index.faiss.bak
mv vector_db/vehicle_docs.jsonl vector_db/vehicle_docs.jsonl.bak

# Rebuild from source documents
python ingest_vehicle_manual.py

# Compare new vs old
ls -lh vector_db/
```

**Solution 4: Disk Space Issues**

```bash
# Check available disk space
df -h .  # macOS/Linux
Get-PSDrive C  # Windows PowerShell

# FAISS index typically needs:
# - 400-500 MB for 10k document chunks
# - 2-3 GB for 50k chunks
# Ensure at least 2x required space available
```

**Solution 5: Path Issues**

If running from different directory:

```python
# In nova_flask_app.py or backend.py
# Verify BASE_DIR is correct
print(f"BASE_DIR: {BASE_DIR}")
print(f"INDEX_PATH: {INDEX_PATH}")

# Should point to absolute path where index files exist
```

---

## Cache Verification Failures

### Symptom: Cache errors or inconsistent results

**Error Messages:**
```
Cache verification failed
Hash mismatch in cached retrieval
Secure cache validation error
```

### Diagnosis Steps

1. **Check cache directory permissions:**
   ```bash
   ls -ld vector_db/
   # Should be writable
   ```

2. **Verify cache files:**
   ```bash
   ls -lh vector_db/search_history.pkl
   ls -lh vector_db/favorites.json
   ```

3. **Check secure cache availability:**
   ```python
   import sys
   try:
       from secure_cache import secure_pickle_dump, secure_pickle_load
       print("Secure cache available")
   except ImportError:
       print("Secure cache NOT available - using standard pickle")
   ```

### Solutions

**Solution 1: Clear Cache**

```bash
# Delete cache files
rm vector_db/search_history.pkl
rm vector_db/favorites.json

# Restart application
python nova_flask_app.py
```

**Solution 2: Disable Retrieval Cache**

```bash
# Temporarily disable caching
export NOVA_ENABLE_RETRIEVAL_CACHE=0  # macOS/Linux
$env:NOVA_ENABLE_RETRIEVAL_CACHE="0"  # Windows PowerShell

python nova_flask_app.py
```

**Solution 3: Fix Cache Directory Permissions**

```bash
# macOS/Linux
chmod 755 vector_db/
chmod 644 vector_db/*.pkl vector_db/*.json

# Windows
icacls vector_db /grant Everyone:(OI)(CI)F
```

**Solution 4: Install Secure Cache Module**

If secure_cache.py is missing:

```bash
# Verify file exists
ls -l secure_cache.py

# Check imports
python -c "from secure_cache import secure_pickle_dump; print('OK')"
```

---

## Low Confidence Scores

### Symptom: System frequently abstains or returns "I cannot answer"

**Indicators:**
- Confidence consistently < 60%
- Many abstention responses
- Retrieval scores < 0.5
- System falls back to extractive answers

### Diagnosis Steps

1. **Check retrieval quality:**
   ```bash
   curl -X POST http://127.0.0.1:5000/api/retrieve \
     -H "Content-Type: application/json" \
     -d '{"query": "your test question", "k": 10}'
   # Inspect confidence scores in response
   ```

2. **Test with known good query:**
   ```bash
   curl -X POST http://127.0.0.1:5000/api/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the oil capacity?"}'
   # Should return high confidence for common questions
   ```

3. **Verify corpus coverage:**
   ```bash
   # Check if documents cover query topic
   grep -r "oil capacity" data/*.pdf  # requires pdfgrep
   ```

### Solutions

**Solution 1: Improve Query Phrasing**

```bash
# Instead of vague queries:
"How does it work?"  # Low confidence

# Use specific queries:
"How does the brake system work?"  # Higher confidence
```

**Solution 2: Expand Corpus**

```bash
# Add more relevant documents to data/ directory
cp additional_manual.pdf data/

# Rebuild index
python ingest_vehicle_manual.py
```

**Solution 3: Adjust Confidence Threshold**

**⚠️ Warning:** Only do this if you understand the safety implications.

```python
# In backend.py, locate confidence gating logic
# Default threshold is typically 0.6 (60%)
# Lowering increases risk of hallucinations
```

**Solution 4: Enable Hybrid Search**

```bash
# Ensure hybrid search is enabled
export NOVA_HYBRID_SEARCH=1  # macOS/Linux
$env:NOVA_HYBRID_SEARCH="1"  # Windows PowerShell

# Improves retrieval for exact terms
```

**Solution 5: Check Embedding Model**

```python
# Verify embedding model loaded correctly
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('Model loaded successfully')
"
```

**Solution 6: Enable Query Expansion (GAR)**

```bash
# Enable Glossary Augmented Retrieval
export NOVA_GAR_ENABLED=1  # macOS/Linux
$env:NOVA_GAR_ENABLED="1"  # Windows PowerShell

# Expands queries with domain terminology
```

---

## Memory Issues

### Symptom: Out of memory errors or system slowdown

**Error Messages:**
```
MemoryError: Unable to allocate array
Killed (OOM killer)
System.OutOfMemoryException
```

### Diagnosis Steps

1. **Monitor memory usage:**
   ```bash
   # macOS/Linux
   top -o MEM
   
   # Windows
   Task Manager → Performance → Memory
   
   # Check Python process specifically
   ps aux | grep python | awk '{print $6}'  # macOS/Linux
   ```

2. **Check component memory:**
   ```python
   import psutil
   import os
   process = psutil.Process(os.getpid())
   print(f"Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")
   ```

3. **Identify memory spike:**
   - At startup → Model loading issue
   - During first query → Index loading issue
   - After many queries → Memory leak

### Solutions

**Solution 1: Use Smaller LLM Model**

```bash
# Switch from 8B to 3B model
ollama pull llama3.2:3b

# Update environment or code to use smaller model
# Memory: 8B = ~5-6 GB, 3B = ~2-3 GB, 1B = ~1-2 GB
```

**Solution 2: Disable Optional Features**

```bash
# Disable vision (saves ~520 MB)
export NOVA_DISABLE_VISION=1

# Disable cross-encoder reranking (saves ~420 MB)
export NOVA_DISABLE_CROSS_ENCODER=1

# Disable embeddings (lexical-only retrieval, saves ~400 MB)
export NOVA_DISABLE_EMBED=1
```

**Solution 3: Reduce Batch Sizes**

```bash
# Reduce embedding batch size
export NOVA_EMBED_BATCH_SIZE=16  # Default is 32

# Restart application
python nova_flask_app.py
```

**Solution 4: Limit Numerical Library Threads**

```bash
# Already set in backend.py, but verify:
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
```

**Solution 5: Clear Python Cache**

```bash
# Remove __pycache__ directories
find . -type d -name __pycache__ -exec rm -rf {} +

# Remove .pyc files
find . -type f -name "*.pyc" -delete
```

**Solution 6: Increase System Swap (Last Resort)**

```bash
# macOS: Not recommended, use Activity Monitor to identify leaks
# Linux: Increase swap
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Windows: Settings → System → About → Advanced system settings → Performance → Advanced → Virtual memory
```

---

## Network Connectivity

### Symptom: Download failures or unexpected network calls (air-gapped environments)

**Error Messages:**
```
Failed to download model from HuggingFace
Connection timeout
Network is unreachable
```

### Diagnosis Steps

1. **Check if air-gap mode is enabled:**
   ```bash
   echo $NOVA_FORCE_OFFLINE  # Should be "1" for air-gapped
   echo $HF_HUB_OFFLINE
   ```

2. **Identify network calls:**
   ```bash
   # Monitor network during startup
   # macOS/Linux
   sudo tcpdump -i any -n dst port 80 or dst port 443
   
   # Should show NO outbound connections if properly air-gapped
   ```

### Solutions

**Solution 1: Enable Offline Mode**

```bash
# Force complete offline operation
export NOVA_FORCE_OFFLINE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

python nova_flask_app.py
```

**Solution 2: Pre-download All Models**

```bash
# Before air-gapping, download all required models:

# 1. Ollama models
ollama pull llama3.2:8b

# 2. HuggingFace embedding models
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('Embedding model cached')
"

# 3. Verify cache location
ls ~/.cache/huggingface/
ls ~/.ollama/models/
```

**Solution 3: Transfer Models Offline**

```bash
# On internet-connected machine:
# 1. Download models
ollama pull llama3.2:8b
pip download -r requirements.txt -d ./packages/

# 2. Export Ollama models
# macOS: ~/.ollama/models/
# Linux: /usr/share/ollama/.ollama/models/
# Windows: C:\Users\<user>\.ollama\models\

# 3. Copy to air-gapped machine
# Transfer entire .ollama and .cache/huggingface directories
```

**Solution 4: Verify No Network Calls**

```bash
# Run offline verification script
python verify_offline_requirements.py

# Should confirm all dependencies are local
```

---

## Model Loading Failures

### Symptom: Models fail to load or crash on startup

**Error Messages:**
```
Failed to load model
CUDA error (if GPU mentioned)
Model file corrupt
Unsupported model format
```

### Diagnosis Steps

1. **Verify model files:**
   ```bash
   # Ollama models
   ollama list
   
   # Should show llama3.2:8b or your configured model
   ```

2. **Test model directly:**
   ```bash
   ollama run llama3.2:8b "test"
   # Should generate response
   ```

3. **Check model size vs. RAM:**
   ```bash
   # 8B parameter model needs ~5-6 GB RAM
   free -h  # Linux
   vm_stat  # macOS
   ```

### Solutions

**Solution 1: Re-download Model**

```bash
# Remove potentially corrupted model
ollama rm llama3.2:8b

# Re-download
ollama pull llama3.2:8b

# Verify
ollama list
```

**Solution 2: Check Ollama Version**

```bash
# Check version
ollama --version

# Update if needed (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Windows: Download installer from ollama.com
```

**Solution 3: Use Native Engine**

If Ollama fails, try native llama-cpp-python:

```bash
export NOVA_USE_NATIVE_LLM=1

# Requires llama-cpp-python installed
pip install llama-cpp-python
```

**Solution 4: Model-Specific Issues**

Different model may work better:

```bash
# Try alternative models
ollama pull llama3.2:3b  # Smaller, more stable
ollama pull phi3:mini    # Different architecture
ollama pull mistral:7b   # Alternative 7B model
```

---

## Database/Index Rebuild

### When to Rebuild Index

Rebuild the FAISS index when:
- Adding new documents to corpus
- Changing embedding model
- Index corruption suspected
- Retrieval quality degrades
- After major application updates

### Full Rebuild Procedure

```bash
# 1. Backup existing index
mkdir -p backups/
cp -r vector_db/ backups/vector_db_$(date +%Y%m%d)/

# 2. Clear old index
rm vector_db/vehicle_index.faiss
rm vector_db/vehicle_docs.jsonl
rm vector_db/vehicle_vision_embeddings.pt  # If exists

# 3. Verify source documents
ls -lh data/*.pdf
# Ensure all PDFs are present and readable

# 4. Run ingestion
python ingest_vehicle_manual.py

# 5. Verify new index
ls -lh vector_db/
# Should see new index files with recent timestamps

# 6. Test retrieval
curl -X POST http://127.0.0.1:5000/api/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "k": 5}'
```

### Incremental Update (if supported)

```bash
# Add new document to data/
cp new_manual.pdf data/

# Re-run ingestion (appends to existing index)
python ingest_vehicle_manual.py --incremental  # If supported

# Otherwise, full rebuild required
```

### Verify Index Health

```python
import faiss
import json

# Load index
index = faiss.read_index("vector_db/vehicle_index.faiss")
print(f"Total vectors: {index.ntotal}")

# Load documents
with open("vector_db/vehicle_docs.jsonl", "r") as f:
    docs = [json.loads(line) for line in f]
print(f"Total documents: {len(docs)}")

# Should match
assert index.ntotal == len(docs), "Index/document count mismatch!"
```

---

## Performance Issues

### Symptom: Queries take too long (>15 seconds)

See [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md) for detailed tuning.

**Quick Solutions:**

```bash
# 1. Use smaller model
ollama pull llama3.2:3b  # 40% faster than 8B

# 2. Disable expensive features
export NOVA_CITATION_AUDIT=0       # Save 1-2s per query
export NOVA_DISABLE_CROSS_ENCODER=1  # Save 150ms retrieval time

# 3. Enable caching
export NOVA_ENABLE_RETRIEVAL_CACHE=1  # 6-12x faster for repeated queries

# 4. Reduce retrieval k parameter
# In backend.py, change k=12 to k=6
```

---

## Authentication Problems

### Symptom: "Unauthorized" or 403 errors

**Error Messages:**
```
{"error": "Unauthorized"}
403 Forbidden
```

### Solutions

**Solution 1: Check Token Configuration**

```bash
# Verify environment variables
echo $NOVA_REQUIRE_TOKEN  # Should be "1" if auth enabled
echo $NOVA_API_TOKEN      # Should be set

# Ensure token matches in request header
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "X-API-TOKEN: your_token_here" \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

**Solution 2: Disable Authentication (Development)**

```bash
# Temporarily disable for testing
export NOVA_REQUIRE_TOKEN=0

python nova_flask_app.py
```

**Solution 3: Token Case Sensitivity**

```bash
# Tokens are case-sensitive
# "MyToken123" ≠ "mytoken123"

# Verify exact match
echo $NOVA_API_TOKEN
# Copy exact value to request header
```

---

## Python Environment Issues

### Symptom: Import errors or dependency conflicts

**Error Messages:**
```
ModuleNotFoundError: No module named 'faiss'
ImportError: cannot import name '...'
Version conflict detected
```

### Solutions

**Solution 1: Verify Virtual Environment**

```bash
# Check if venv is activated
which python  # Should point to .venv/bin/python
echo $VIRTUAL_ENV  # Should show .venv path

# Activate if not active
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate  # Windows
```

**Solution 2: Reinstall Dependencies**

```bash
# Upgrade pip first
pip install --upgrade pip

# Reinstall requirements
pip install -r requirements.txt --force-reinstall

# Verify key packages
pip list | grep -E 'faiss|torch|sentence-transformers'
```

**Solution 3: Python Version Check**

```bash
python --version
# Should be 3.12.x or compatible version

# If wrong version, recreate venv
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Solution 4: Clear pip Cache**

```bash
pip cache purge
pip install -r requirements.txt
```

---

## Getting Help

If the above solutions don't resolve your issue:

1. **Check Application Logs:**
   ```bash
   # Run with verbose output
   python nova_flask_app.py 2>&1 | tee debug.log
   ```

2. **Gather System Info:**
   ```bash
   python --version
   pip list > installed_packages.txt
   ollama --version
   ```

3. **Run Diagnostic Script:**
   ```bash
   python quick_sanity_check.py  # If available
   python verify_offline_requirements.py
   ```

4. **Consult Documentation:**
   - [API Reference](api/API_REFERENCE.md)
   - [Configuration Guide](deployment/CONFIGURATION.md)
   - [System Architecture](architecture/SYSTEM_ARCHITECTURE.md)

---

## Preventive Maintenance

### Regular Health Checks

```bash
# Weekly: Verify system health
curl http://127.0.0.1:5000/api/status

# Monthly: Rebuild index
python ingest_vehicle_manual.py

# Quarterly: Update dependencies
pip list --outdated
# Carefully update and test
```

### Backup Critical Files

```bash
# Backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
mkdir -p backups/$DATE/
cp -r vector_db/ backups/$DATE/vector_db/
cp -r data/ backups/$DATE/data/
echo "Backup complete: backups/$DATE/"
```

---

**Last Updated:** 2024-01  
**Version:** 1.0
