# Configuration Management

Complete guide to configuring the NIC RAG system for different environments and use cases.

---

## Table of Contents

1. [Environment Variables](#environment-variables)
2. [Required vs. Optional Configuration](#required-vs-optional-configuration)
3. [Configuration Examples](#configuration-examples)
4. [Configuration Validation](#configuration-validation)
5. [Default Values](#default-values)
6. [Security Configuration](#security-configuration)
7. [Performance Tuning](#performance-tuning)

---

## Environment Variables

### Complete Environment Variable Reference

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| **Core Settings** |
| `FLASK_HOST` | string | `127.0.0.1` | Flask server host address |
| `FLASK_PORT` | integer | `5000` | Flask server port |
| `NOVA_LLM_MODEL` | string | `llama3.2:8b` | LLM model to use (Ollama) |
| `OLLAMA_BASE_URL` | string | `http://127.0.0.1:11434/v1` | Ollama API endpoint |
| **Safety & Quality** |
| `NOVA_CITATION_AUDIT` | boolean | `1` | Enable citation verification |
| `NOVA_CITATION_STRICT` | boolean | `1` | Strict citation validation mode |
| `NOVA_HYBRID_SEARCH` | boolean | `1` | Enable hybrid retrieval (vector+BM25) |
| `NOVA_GAR_ENABLED` | boolean | `1` | Enable Glossary Augmented Retrieval |
| **Performance** |
| `NOVA_ENABLE_RETRIEVAL_CACHE` | boolean | `0` | Enable retrieval result caching |
| `NOVA_USE_NATIVE_LLM` | boolean | `1` | Use native llama-cpp-python engine |
| `NOVA_DISABLE_CROSS_ENCODER` | boolean | `0` | Disable cross-encoder reranking |
| `NOVA_EMBED_BATCH_SIZE` | integer | `32` | Embedding batch size |
| **Feature Toggles** |
| `NOVA_DISABLE_VISION` | boolean | `0` | Disable vision/image processing |
| `NOVA_DISABLE_EMBED` | boolean | `0` | Disable embeddings (lexical-only) |
| `NOVA_FORCE_OFFLINE` | boolean | `0` | Force offline mode (no network) |
| **Security** |
| `NOVA_REQUIRE_TOKEN` | boolean | `0` | Require API token authentication |
| `NOVA_API_TOKEN` | string | (none) | API authentication token |
| **Advanced** |
| `NOVA_WARMUP_ON_START` | boolean | `0` | Pre-warm models on startup |
| `NOVA_ENABLE_SQL_LOG` | boolean | `0` | Enable SQL query logging |
| `NOVA_BM25_K1` | float | `1.5` | BM25 term saturation parameter |
| `NOVA_BM25_B` | float | `0.75` | BM25 length normalization |
| **System** |
| `OMP_NUM_THREADS` | integer | `1` | OpenMP thread count |
| `OPENBLAS_NUM_THREADS` | integer | `1` | OpenBLAS thread count |
| `MKL_NUM_THREADS` | integer | `1` | MKL thread count |
| `TOKENIZERS_PARALLELISM` | string | `false` | HuggingFace tokenizer parallelism |
| `HF_HUB_OFFLINE` | boolean | `0` | Block HuggingFace downloads |
| `TRANSFORMERS_OFFLINE` | boolean | `0` | Block transformer downloads |

---

## Required vs. Optional Configuration

### Required (Minimum Working System)

**None.** NIC works with zero configuration using sensible defaults.

However, these are **strongly recommended** for production:

```bash
# Safety features (recommended for production)
NOVA_CITATION_AUDIT=1
NOVA_CITATION_STRICT=1
NOVA_HYBRID_SEARCH=1
```

### Optional (Recommended for Specific Environments)

**Air-Gapped Deployments:**
```bash
NOVA_FORCE_OFFLINE=1
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

**High-Security Environments:**
```bash
NOVA_REQUIRE_TOKEN=1
NOVA_API_TOKEN=your_secure_random_token_here
NOVA_CITATION_STRICT=1
```

**Low-Memory Systems (<4 GB RAM):**
```bash
NOVA_DISABLE_VISION=1
NOVA_DISABLE_CROSS_ENCODER=1
NOVA_EMBED_BATCH_SIZE=16
# Use smaller model: llama3.2:3b or 1b
```

**Performance-Optimized:**
```bash
NOVA_ENABLE_RETRIEVAL_CACHE=1
NOVA_USE_NATIVE_LLM=1
NOVA_CITATION_AUDIT=0  # Trade safety for speed
```

---

## Configuration Examples

### 1. Development Environment

**Use Case:** Local development, testing, experimentation

```bash
# .env.development
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
NOVA_LLM_MODEL=llama3.2:3b  # Faster for dev
NOVA_CITATION_AUDIT=0        # Speed over safety in dev
NOVA_ENABLE_RETRIEVAL_CACHE=1  # Cache for faster iteration
NOVA_DISABLE_VISION=1        # Not needed for testing
```

**To Use:**
```bash
cp .env.development .env
source .env  # Linux/macOS
# OR
Get-Content .env.development | ForEach-Object {
  if ($_ -match '^([^#][^=]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
  }
}  # Windows PowerShell
python nova_flask_app.py
```

---

### 2. Air-Gapped Production

**Use Case:** Classified networks, no internet access, maximum security

```bash
# .env.airgapped
# Network isolation
NOVA_FORCE_OFFLINE=1
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1

# Safety features
NOVA_CITATION_AUDIT=1
NOVA_CITATION_STRICT=1
NOVA_HYBRID_SEARCH=1
NOVA_GAR_ENABLED=1

# Security
NOVA_REQUIRE_TOKEN=1
NOVA_API_TOKEN=use_a_long_random_secure_token_here_min_32_chars

# Server
FLASK_HOST=0.0.0.0  # Allow network access within air-gap
FLASK_PORT=5000

# Model
NOVA_LLM_MODEL=llama3.2:8b

# Performance (if needed)
NOVA_USE_NATIVE_LLM=1
```

**Deployment Steps:**
1. Pre-download all models on internet-connected machine
2. Transfer models to air-gapped machine (see [Air-Gapped Deployment Guide](AIR_GAPPED_DEPLOYMENT.md))
3. Set environment variables from .env.airgapped
4. Verify offline operation: `python verify_offline_requirements.py`
5. Start server: `waitress-serve --host=0.0.0.0 --port=5000 nova_flask_app:app`

---

### 3. High-Security Mode

**Use Case:** Sensitive data, audit requirements, strict compliance

```bash
# .env.highsec
# Authentication
NOVA_REQUIRE_TOKEN=1
NOVA_API_TOKEN=generate_a_cryptographically_secure_token

# Maximum safety
NOVA_CITATION_AUDIT=1
NOVA_CITATION_STRICT=1
NOVA_HYBRID_SEARCH=1
NOVA_GAR_ENABLED=1

# Disable risky features
NOVA_ENABLE_RETRIEVAL_CACHE=0  # No caching (potential info leak)
NOVA_ENABLE_SQL_LOG=0          # No query logging

# Audit trail (enable session logging in code)
# All queries logged with timestamps, user, answer, citations

# Server
FLASK_HOST=127.0.0.1  # Localhost only, use reverse proxy for network
FLASK_PORT=5000
```

**Additional Security Measures:**
```bash
# Run behind reverse proxy with TLS
# Example nginx config:
server {
    listen 443 ssl;
    server_name nic.internal.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header X-API-TOKEN $http_x_api_token;
    }
}
```

---

### 4. Testing Environment

**Use Case:** Automated testing, CI/CD, quality assurance

```bash
# .env.testing
# Use smallest, fastest model for tests
NOVA_LLM_MODEL=llama3.2:1b

# Disable slow features
NOVA_CITATION_AUDIT=0
NOVA_DISABLE_CROSS_ENCODER=1
NOVA_DISABLE_VISION=1
NOVA_ENABLE_RETRIEVAL_CACHE=0  # Avoid cache-related test flakiness

# Fast retrieval
NOVA_HYBRID_SEARCH=1
NOVA_EMBED_BATCH_SIZE=8

# No authentication for tests
NOVA_REQUIRE_TOKEN=0

# Ports
FLASK_HOST=127.0.0.1
FLASK_PORT=5555  # Non-standard to avoid conflicts
```

**Test Script:**
```bash
#!/bin/bash
export $(cat .env.testing | xargs)
python -m pytest tests/ -v
```

---

### 5. Low-Memory Configuration

**Use Case:** Laptops, edge devices, resource-constrained environments

```bash
# .env.lowmem
# Minimal model
NOVA_LLM_MODEL=llama3.2:1b  # ~1 GB RAM

# Disable memory-heavy features
NOVA_DISABLE_VISION=1          # Save ~520 MB
NOVA_DISABLE_CROSS_ENCODER=1   # Save ~420 MB
NOVA_EMBED_BATCH_SIZE=16       # Reduce batch size

# Still maintain quality
NOVA_HYBRID_SEARCH=1           # Keep hybrid search
NOVA_CITATION_AUDIT=1          # Keep safety

# Performance tuning
NOVA_USE_NATIVE_LLM=1

# Threading limits (already set in code)
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
```

**Expected Memory Footprint:**
- Python + Flask: ~200 MB
- Embeddings: ~380 MB
- FAISS index: ~450 MB
- LLM (1B model): ~1 GB
- **Total: ~2 GB**

---

### 6. High-Performance Configuration

**Use Case:** High query volume, multiple users, production server

```bash
# .env.highperf
# Use native engine for speed
NOVA_USE_NATIVE_LLM=1

# Enable caching
NOVA_ENABLE_RETRIEVAL_CACHE=1

# Disable slow features (trade safety for speed)
NOVA_CITATION_AUDIT=0          # ⚠️ Reduces safety
NOVA_DISABLE_CROSS_ENCODER=0   # Keep for quality

# Keep hybrid search for quality
NOVA_HYBRID_SEARCH=1

# Model selection (balance speed vs quality)
NOVA_LLM_MODEL=llama3.2:3b  # 40% faster than 8b

# Server configuration (use production WSGI server)
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

**Production Deployment:**
```bash
# Use waitress or gunicorn for concurrency
waitress-serve --host=0.0.0.0 --port=5000 --threads=8 nova_flask_app:app

# OR
gunicorn -w 4 -b 0.0.0.0:5000 nova_flask_app:app
```

---

## Configuration Validation

### Validation Checklist

Before deploying, verify your configuration:

**1. Required Files Exist:**
```bash
ls vector_db/vehicle_index.faiss  # FAISS index
ls vector_db/vehicle_docs.jsonl   # Document metadata
ls data/*.pdf                      # Source documents
```

**2. Environment Variables Set:**
```bash
# Check critical variables
echo $NOVA_CITATION_AUDIT    # Should be 1 for production
echo $NOVA_HYBRID_SEARCH     # Should be 1 for quality
echo $NOVA_API_TOKEN         # Should be set if NOVA_REQUIRE_TOKEN=1
```

**3. Ollama Connectivity:**
```bash
curl http://127.0.0.1:11434/api/tags
# Should return JSON with model list
```

**4. Model Downloaded:**
```bash
ollama list
# Should show your configured model (e.g., llama3.2:8b)
```

**5. Python Dependencies:**
```bash
pip check
# Should report no issues
```

**6. Startup Validation:**
```bash
python nova_flask_app.py
# Should pass all startup checks
```

### Automated Validation Script

```bash
#!/bin/bash
# validate_config.sh

echo "=== Configuration Validation ==="

# 1. Check Python environment
python --version || { echo "❌ Python not found"; exit 1; }

# 2. Check dependencies
pip show faiss-cpu torch sentence-transformers flask > /dev/null || {
    echo "❌ Missing dependencies"
    exit 1
}

# 3. Check files
[ -f "vector_db/vehicle_index.faiss" ] || {
    echo "❌ FAISS index not found"
    exit 1
}

# 4. Check Ollama
curl -s http://127.0.0.1:11434/api/tags > /dev/null || {
    echo "⚠ Ollama not accessible"
}

# 5. Check environment
[ -z "$NOVA_API_TOKEN" ] && [ "$NOVA_REQUIRE_TOKEN" = "1" ] && {
    echo "❌ NOVA_API_TOKEN required when NOVA_REQUIRE_TOKEN=1"
    exit 1
}

echo "✓ Configuration valid"
```

---

## Default Values

### System Defaults (if not configured)

```python
# Safety defaults (recommended for production)
NOVA_CITATION_AUDIT = 1           # Citation verification ON
NOVA_CITATION_STRICT = 1          # Strict mode ON
NOVA_HYBRID_SEARCH = 1            # Hybrid retrieval ON
NOVA_GAR_ENABLED = 1              # Query expansion ON

# Performance defaults (balanced)
NOVA_ENABLE_RETRIEVAL_CACHE = 0   # Caching OFF (avoid staleness)
NOVA_USE_NATIVE_LLM = 1           # Native engine ON (if available)
NOVA_DISABLE_CROSS_ENCODER = 0    # Cross-encoder ON (better quality)
NOVA_EMBED_BATCH_SIZE = 32        # Standard batch size

# Feature defaults
NOVA_DISABLE_VISION = 0           # Vision ON (if needed)
NOVA_DISABLE_EMBED = 0            # Embeddings ON
NOVA_FORCE_OFFLINE = 0            # Offline mode OFF

# Security defaults
NOVA_REQUIRE_TOKEN = 0            # Auth OFF (local dev)
NOVA_API_TOKEN = None             # No token

# Server defaults
FLASK_HOST = "127.0.0.1"          # Localhost only
FLASK_PORT = 5000                 # Standard port

# Model defaults
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
# LLM model determined by backend logic
```

---

## Security Configuration

### API Token Generation

**Generate Secure Token:**
```bash
# Linux/macOS
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Windows PowerShell
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Example output:
# kB4zP9xE2mN8cR5tV6hQ1wY7jU3sA0fL2nK9pM4dG8i
```

**Set Token:**
```bash
export NOVA_API_TOKEN="kB4zP9xE2mN8cR5tV6hQ1wY7jU3sA0fL2nK9pM4dG8i"
export NOVA_REQUIRE_TOKEN=1
```

**Secure Token Storage:**
```bash
# Store in .env file (add to .gitignore!)
echo "NOVA_API_TOKEN=your_token_here" >> .env
echo ".env" >> .gitignore

# Or use system keyring/secrets manager
```

### TLS/SSL Configuration

NIC does not provide TLS directly. Use a reverse proxy:

**Nginx Example:**
```nginx
server {
    listen 443 ssl http2;
    server_name nic.example.com;
    
    ssl_certificate /etc/ssl/certs/nic.crt;
    ssl_certificate_key /etc/ssl/private/nic.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Performance Tuning

### Latency Optimization

**Target: Sub-2s queries**
```bash
NOVA_CITATION_AUDIT=0          # Save 1-2s (⚠️ reduces safety)
NOVA_DISABLE_CROSS_ENCODER=1   # Save 150ms
NOVA_HYBRID_SEARCH=0           # Save 200ms (⚠️ reduces recall)
NOVA_LLM_MODEL=llama3.2:3b     # 40% faster generation
```

**Expected latency:** ~1.2s (vs 3.2s default)

### Throughput Optimization

**Target: Maximum QPS**
```bash
# Use production WSGI server
waitress-serve --host=0.0.0.0 --port=5000 --threads=8 nova_flask_app:app

# Enable caching
NOVA_ENABLE_RETRIEVAL_CACHE=1

# Use smaller model for faster throughput
NOVA_LLM_MODEL=llama3.2:3b
```

**Expected throughput:** ~0.8-1.2 QPS (vs 0.3 QPS single-threaded)

### Memory Optimization

**Target: <3 GB total RAM**
```bash
NOVA_LLM_MODEL=llama3.2:1b      # ~1 GB vs 5 GB
NOVA_DISABLE_VISION=1            # Save ~520 MB
NOVA_DISABLE_CROSS_ENCODER=1     # Save ~420 MB
NOVA_EMBED_BATCH_SIZE=16         # Reduce batch memory
```

**Expected memory:** ~2.2 GB total

---

## Environment-Specific Tips

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . /app
WORKDIR /app

# Environment variables (override at runtime)
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000
ENV NOVA_CITATION_AUDIT=1

# Expose port
EXPOSE 5000

# Run
CMD ["python", "nova_flask_app.py"]
```

**Docker Compose:**
```yaml
version: '3.8'
services:
  nic:
    build: .
    ports:
      - "5000:5000"
    environment:
      - NOVA_CITATION_AUDIT=1
      - NOVA_HYBRID_SEARCH=1
      - NOVA_REQUIRE_TOKEN=1
      - NOVA_API_TOKEN=${NOVA_API_TOKEN}
    volumes:
      - ./vector_db:/app/vector_db
      - ./data:/app/data
```

### Kubernetes Deployment

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nic-config
data:
  NOVA_CITATION_AUDIT: "1"
  NOVA_HYBRID_SEARCH: "1"
  FLASK_HOST: "0.0.0.0"
  FLASK_PORT: "5000"

---
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: nic-secrets
type: Opaque
stringData:
  NOVA_API_TOKEN: "your_secure_token_here"
```

---

## Related Documentation

- [API Reference](../api/API_REFERENCE.md) - API endpoint configuration
- [Troubleshooting](../TROUBLESHOOTING.md) - Configuration issues
- [Air-Gapped Deployment](AIR_GAPPED_DEPLOYMENT.md) - Offline configuration
- [Performance Benchmarks](../evaluation/PERFORMANCE_BENCHMARKS.md) - Tuning guidance

---

**Version:** 1.0  
**Last Updated:** 2024-01
