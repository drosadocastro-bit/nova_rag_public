# Runbook: High Latency / Slow Responses

## Symptoms
- Query response times >5 seconds
- Timeouts on `/api/ask` endpoint
- Prometheus `nova_query_latency_seconds` showing high values
- Users reporting slow responses

---

## Quick Diagnosis

```bash
# Check current latency metrics
curl -s http://localhost:5000/metrics | grep nova_query_latency

# Check system resources
top -bn1 | head -20  # Linux
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10  # Windows

# Check Ollama response time
time curl -s http://localhost:11434/api/tags
```

---

## Issue: Slow LLM Inference

### Symptoms
- Latency increases with query complexity
- CPU usage at 100% during queries
- `nova_query_latency_seconds{phase="llm"}` is high

### Diagnosis
```bash
# Test LLM directly
time curl -X POST http://localhost:11434/api/generate \
  -d '{"model":"llama2","prompt":"Hello","stream":false}'
```

### Resolution

**Use smaller/faster model:**
```bash
# Switch to faster model
ollama pull llama3.2:1b
export NOVA_LLM_MODEL="llama3.2:1b"
```

**Enable GPU acceleration:**
```bash
# Verify GPU is available
nvidia-smi

# Ensure Ollama uses GPU
ollama run llama2 --verbose
```

**Reduce max tokens:**
```python
# In config, reduce response length
MAX_TOKENS = 256  # Instead of 512
```

### Prevention
- Monitor `nova_query_latency_seconds{phase="llm"}`
- Set up alerts for p95 latency > 3s

---

## Issue: Slow Retrieval

### Symptoms
- Latency even for cached queries
- `nova_query_latency_seconds{phase="retrieval"}` is high
- High disk I/O during queries

### Diagnosis
```bash
# Test retrieval speed
python -c "
import time
from core.retrieval.retrieval_engine import retrieve
start = time.time()
results = retrieve('test query', domain='vehicle')
print(f'Retrieval took {time.time()-start:.2f}s')
"
```

### Resolution

**Optimize FAISS index:**
```python
# Convert to IVF index for faster search
import faiss
index = faiss.read_index('vector_db/faiss_index.bin')
# Create IVF index with 100 centroids
nlist = 100
quantizer = faiss.IndexFlatL2(index.d)
ivf_index = faiss.IndexIVFFlat(quantizer, index.d, nlist)
ivf_index.train(vectors)
ivf_index.add(vectors)
faiss.write_index(ivf_index, 'vector_db/faiss_index_ivf.bin')
```

**Reduce top_k:**
```python
# Fetch fewer documents
TOP_K = 3  # Instead of 5
```

**Enable caching:**
```bash
# Ensure cache is enabled
export NOVA_CACHE_ENABLED=true
export NOVA_CACHE_TTL=3600
```

### Prevention
- Pre-warm cache with common queries
- Monitor cache hit rate via metrics

---

## Issue: Memory Pressure

### Symptoms
- Swapping to disk
- Gradual latency increase over time
- High memory usage in health check

### Diagnosis
```bash
# Check memory usage
curl -s http://localhost:5000/health | jq '.checks.memory'

# Check for memory leaks
ps aux | grep python
watch -n 5 'ps -o rss,vsz,pid,command -p $(pgrep -f nova_flask)'
```

### Resolution

**Restart service:**
```bash
# Graceful restart
sudo systemctl restart nova-nic
```

**Reduce memory footprint:**
```bash
# Use smaller embedding model
export EMBEDDING_MODEL="all-MiniLM-L6-v2"

# Limit concurrent requests
export NOVA_MAX_WORKERS=2
```

### Prevention
- Set memory limits in systemd/Docker
- Schedule periodic restarts during low-traffic periods

---

## Issue: Cache Miss Storm

### Symptoms
- Sudden latency spike after restart
- Low cache hit rate
- High Ollama CPU usage

### Diagnosis
```bash
# Check cache hit rate
curl -s http://localhost:5000/metrics | grep nova_cache

# Check cache directory
ls -la cache/retrieval/
```

### Resolution

**Pre-warm cache:**
```bash
# Run common queries to warm cache
python scripts/warm_cache.py
```

**Increase cache TTL:**
```bash
export NOVA_CACHE_TTL=86400  # 24 hours
```

### Prevention
- Implement cache warming on startup
- Use persistent cache across restarts

---

## Issue: Network Latency to Ollama

### Symptoms
- Latency higher when Ollama is remote
- Intermittent slow responses
- Network timeouts

### Diagnosis
```bash
# Ping Ollama host
ping ollama-host

# Check network latency
time curl -s http://ollama-host:11434/api/tags
```

### Resolution

**Run Ollama locally:**
```bash
# If possible, run Ollama on same machine
ollama serve
```

**Increase timeouts:**
```python
# In llm_engine.py
OLLAMA_TIMEOUT = 60  # seconds
```

### Prevention
- Deploy Ollama on same network segment
- Use connection pooling

---

## Performance Tuning Checklist

| Setting | Current | Recommended |
|---------|---------|-------------|
| LLM Model | llama2:7b | llama3.2:1b (if speed critical) |
| Embedding Model | all-mpnet-base-v2 | all-MiniLM-L6-v2 (faster) |
| Top-K Results | 5 | 3 (faster retrieval) |
| Max Tokens | 512 | 256 (faster generation) |
| Cache TTL | 3600 | 86400 (fewer cache misses) |
| Workers | 4 | 2 (less memory pressure) |

---

## Latency Budget

Target: **< 3 seconds** for 95th percentile

| Phase | Budget | Description |
|-------|--------|-------------|
| Retrieval | 200ms | FAISS + BM25 hybrid search |
| Reranking | 100ms | Domain scoring, safety checks |
| LLM | 2500ms | Response generation |
| Post-processing | 200ms | Safety validation, formatting |

---

## Monitoring Queries

**Prometheus queries for latency analysis:**

```promql
# P95 latency
histogram_quantile(0.95, rate(nova_query_latency_seconds_bucket[5m]))

# Latency by phase
rate(nova_query_latency_seconds_sum[5m]) / rate(nova_query_latency_seconds_count[5m])

# Slow query rate (>5s)
rate(nova_query_latency_seconds_bucket{le="5"}[5m])
```

---

## Escalation

If latency remains high after optimization:

1. Enable debug logging:
   ```bash
   export NOVA_LOG_LEVEL=DEBUG
   ```

2. Profile a query:
   ```bash
   python -m cProfile -o profile.out -c "
   from core.retrieval.retrieval_engine import retrieve
   retrieve('How do I check brake pads?', domain='vehicle')
   "
   python -c "import pstats; pstats.Stats('profile.out').sort_stats('cumtime').print_stats(20)"
   ```

3. Open issue with:
   - Latency metrics (p50, p95, p99)
   - System resources (CPU, memory, disk)
   - Query examples
   - Profile output

---

## Related Runbooks

- [Memory Issues](memory-issues.md)
- [Ollama Connection Issues](ollama-connection.md)
- [Server Startup Issues](server-startup-issues.md)
