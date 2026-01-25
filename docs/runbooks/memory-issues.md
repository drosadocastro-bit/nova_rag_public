# Runbook: Memory Issues

## Symptoms
- Out of Memory (OOM) errors
- Process killed by OS
- Gradual memory growth (leak)
- Swap usage increasing
- Slow performance due to swapping

---

## Quick Diagnosis

```bash
# Check system memory
free -h  # Linux
systeminfo | findstr Memory  # Windows

# Check process memory
ps aux --sort=-%mem | head -10  # Linux
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10  # Windows

# Check NIC health endpoint
curl -s http://localhost:5000/health | jq '.checks.memory'

# Check for OOM in logs
dmesg | grep -i "oom\|killed"  # Linux
```

---

## Issue: Out of Memory (OOM) Crash

### Symptoms
```
MemoryError: Unable to allocate X GiB
Killed (signal 9)
Process exited with code 137
```

### Diagnosis
```bash
# Check what was killed
dmesg | tail -50 | grep -i oom

# Check memory at crash time
journalctl -u nova-nic | grep -i memory
```

### Resolution

**Immediate: Restart with lower memory settings**
```bash
# Reduce embedding batch size
export NOVA_BATCH_SIZE=8  # Default is 32

# Use smaller embedding model
export EMBEDDING_MODEL="all-MiniLM-L6-v2"  # 80MB vs 400MB

# Limit workers
export NOVA_MAX_WORKERS=2

# Restart
sudo systemctl restart nova-nic
```

**Long-term: Add memory limits**
```bash
# Systemd service limit
# In /etc/systemd/system/nova-nic.service
[Service]
MemoryMax=4G
MemoryHigh=3G
```

**Docker memory limit:**
```yaml
# docker-compose.yml
services:
  nova-nic:
    deploy:
      resources:
        limits:
          memory: 4G
```

### Prevention
- Set memory limits in deployment
- Monitor memory usage via Prometheus
- Alert at 80% memory usage

---

## Issue: Memory Leak (Gradual Growth)

### Symptoms
- Memory increases over hours/days
- No OOM but performance degrades
- Swap usage increases

### Diagnosis

**Monitor over time:**
```bash
# Watch memory usage
watch -n 60 'ps -o rss,vsz,pid -p $(pgrep -f nova_flask) | numfmt --header --field 1-2 --from-unit=1024 --to=iec'

# Log memory every minute
while true; do
    echo "$(date): $(ps -o rss= -p $(pgrep -f nova_flask) | numfmt --from-unit=1024 --to=iec)"
    sleep 60
done >> memory_log.txt
```

**Profile memory:**
```bash
# Install memory profiler
pip install memory_profiler

# Profile specific function
python -m memory_profiler your_script.py
```

### Resolution

**Schedule periodic restarts:**
```bash
# Cron job to restart during low-traffic hours
0 4 * * * systemctl restart nova-nic
```

**Identify leak source:**
```python
# Add to nova_flask_app.py for debugging
import tracemalloc
tracemalloc.start()

@app.route('/debug/memory')
def debug_memory():
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')[:10]
    return jsonify([str(stat) for stat in top_stats])
```

**Common leak sources:**
1. **Session store growing** - Implement session expiry
2. **Cache not bounded** - Set max cache size
3. **Embeddings cached** - Clear embedding cache periodically

### Prevention
- Set max cache sizes
- Implement session cleanup
- Regular restarts in production

---

## Issue: High Memory at Startup

### Symptoms
- OOM during initialization
- Never reaches ready state
- "Cannot allocate memory" on startup

### Diagnosis
```bash
# Monitor startup
watch -n 1 'ps -o rss= -p $(pgrep -f nova_flask) | numfmt --from-unit=1024 --to=iec'
```

### Resolution

**Lazy-load models:**
```python
# Don't load all models at startup
# Load on first request instead
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)
    return _embedding_model
```

**Use smaller index:**
```bash
# Use memory-mapped FAISS
python -c "
import faiss
index = faiss.read_index('vector_db/faiss_index.bin')
# Convert to memory-mapped
faiss.write_index(index, 'vector_db/faiss_index.bin', faiss.IO_FLAG_MMAP)
"
```

### Prevention
- Lazy-load heavy components
- Use memory-mapped files for large indices

---

## Issue: Embedding Model Memory

### Symptoms
- 400MB+ memory for embeddings alone
- Memory spike when processing queries

### Resolution

**Use smaller model:**
```bash
# MiniLM is much smaller
export EMBEDDING_MODEL="all-MiniLM-L6-v2"  # ~80MB
# Instead of
# export EMBEDDING_MODEL="all-mpnet-base-v2"  # ~400MB
```

**Reduce batch size:**
```python
# In embedding code
embeddings = model.encode(texts, batch_size=8)  # Lower = less memory
```

---

## Issue: FAISS Index Memory

### Symptoms
- Large FAISS index consuming GB of RAM
- OOM when loading index

### Diagnosis
```bash
# Check index size
ls -lh vector_db/faiss_index.bin

# Check loaded size
python -c "
import faiss
import sys
index = faiss.read_index('vector_db/faiss_index.bin')
print(f'Vectors: {index.ntotal}')
print(f'Dimension: {index.d}')
print(f'Estimated RAM: {index.ntotal * index.d * 4 / 1e9:.2f} GB')
"
```

### Resolution

**Use IVF index (less memory):**
```python
import faiss
import numpy as np

# Load current index
index = faiss.read_index('vector_db/faiss_index.bin')
vectors = index.reconstruct_n(0, index.ntotal)

# Create IVF index
nlist = 100  # Number of clusters
quantizer = faiss.IndexFlatL2(index.d)
ivf_index = faiss.IndexIVFFlat(quantizer, index.d, nlist)
ivf_index.train(vectors)
ivf_index.add(vectors)

# Save
faiss.write_index(ivf_index, 'vector_db/faiss_index_ivf.bin')
```

**Use memory-mapped index:**
```python
# Read with memory mapping
index = faiss.read_index('vector_db/faiss_index.bin', faiss.IO_FLAG_MMAP)
```

---

## Memory Configuration Reference

| Component | Default | Min | Recommended |
|-----------|---------|-----|-------------|
| Embedding Model | 400MB | 80MB | 80-200MB |
| FAISS Index (10K docs) | 150MB | 50MB | 150MB |
| FAISS Index (100K docs) | 1.5GB | 500MB | 1.5GB |
| BM25 Index | 50MB | 20MB | 50MB |
| LLM (Ollama) | 4GB | 1GB | 4-8GB |
| Cache | Unbounded | 100MB | 500MB |
| Session Store | Unbounded | 50MB | 200MB |

**Total recommended:** 4-8 GB RAM minimum

---

## Memory Monitoring Script

Save as `monitor_memory.py`:

```python
#!/usr/bin/env python3
"""Monitor NIC memory usage."""

import psutil
import time
import sys
from datetime import datetime

def find_nic_process():
    """Find NIC Flask process."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'nova_flask' in cmdline or 'waitress' in cmdline:
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def format_bytes(b):
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"

def main():
    print("=== NIC Memory Monitor ===")
    print("Time, RSS, VMS, Shared, %Mem")
    
    try:
        while True:
            proc = find_nic_process()
            if proc:
                mem = proc.memory_info()
                pct = proc.memory_percent()
                print(f"{datetime.now().strftime('%H:%M:%S')}, "
                      f"{format_bytes(mem.rss)}, "
                      f"{format_bytes(mem.vms)}, "
                      f"{format_bytes(getattr(mem, 'shared', 0))}, "
                      f"{pct:.1f}%")
            else:
                print(f"{datetime.now().strftime('%H:%M:%S')}, NIC not running")
            
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopped")

if __name__ == "__main__":
    main()
```

---

## Prometheus Alerts for Memory

```yaml
# prometheus/alerts/memory.yml
groups:
  - name: memory
    rules:
      - alert: HighMemoryUsage
        expr: nova_memory_usage_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on NIC"
          
      - alert: MemoryLeakSuspected
        expr: increase(nova_memory_usage_bytes[1h]) > 500000000
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Memory increased by 500MB in 1 hour"
          
      - alert: OOMRisk
        expr: nova_memory_usage_percent > 95
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "OOM imminent - memory at 95%"
```

---

## Escalation

If memory issues persist:

1. Collect memory diagnostics:
   ```bash
   # System memory
   free -h > memory_state.txt
   vmstat 1 10 >> memory_state.txt
   
   # Process memory
   ps aux --sort=-%mem | head -20 >> memory_state.txt
   
   # Memory map
   pmap $(pgrep -f nova_flask) >> memory_state.txt
   ```

2. Enable memory profiling:
   ```bash
   pip install memory_profiler
   mprof run python nova_flask_app.py
   mprof plot  # Generates memory graph
   ```

3. Open issue with:
   - Memory state at crash
   - Load pattern before crash
   - Configuration (batch size, model, etc.)
   - Memory profile if available

---

## Related Runbooks

- [High Latency](high-latency.md)
- [Server Startup Issues](server-startup-issues.md)
- [Ollama Connection Issues](ollama-connection.md)
