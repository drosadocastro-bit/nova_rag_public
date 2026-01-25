# Runbook: Ollama Connection Issues

## Symptoms
- "Connection refused" errors
- Timeouts when generating responses
- Empty or truncated responses
- Health check shows Ollama as unhealthy

---

## Quick Diagnosis

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check Ollama process
ps aux | grep ollama  # Linux
Get-Process | Where-Object Name -like "*ollama*"  # Windows

# Check Ollama logs
journalctl -u ollama -n 50  # systemd
tail -50 ~/.ollama/logs/server.log  # Manual
```

---

## Issue: Ollama Not Running

### Symptoms
```
ConnectionRefusedError: [Errno 111] Connection refused
requests.exceptions.ConnectionError
```

### Resolution

**Start Ollama manually:**
```bash
# Linux/Mac
ollama serve &

# Windows (PowerShell)
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
```

**Start via systemd (Linux):**
```bash
sudo systemctl start ollama
sudo systemctl enable ollama  # Start on boot
```

**Verify it's running:**
```bash
curl http://localhost:11434/api/tags
# Should return: {"models":[...]}
```

### Prevention
- Configure Ollama as a systemd service
- Add Ollama health check to NIC startup script

---

## Issue: Model Not Found

### Symptoms
```
Error: model 'llama2' not found
{"error":"model 'custom-model' not found"}
```

### Resolution

**List available models:**
```bash
ollama list
```

**Pull missing model:**
```bash
ollama pull llama2
ollama pull nomic-embed-text  # For embeddings
```

**Create custom model if needed:**
```bash
# Check if Modelfile exists
cat models/Modelfile.nic

# Create model
ollama create nic-advisor -f models/Modelfile.nic
```

### Prevention
- Document required models in README
- Add model verification to startup script

---

## Issue: Ollama Timeout

### Symptoms
```
TimeoutError: Request timed out after 30 seconds
requests.exceptions.ReadTimeout
```

### Diagnosis
```bash
# Check Ollama resource usage
top -bn1 | grep ollama

# Check GPU memory (if using GPU)
nvidia-smi

# Test model directly
time ollama run llama2 "Hello" --verbose
```

### Resolution

**Increase timeout in NIC:**
```python
# In llm_engine.py
OLLAMA_TIMEOUT = 120  # seconds
```

**Use smaller model:**
```bash
ollama pull llama3.2:1b  # 1B parameter model
export NOVA_LLM_MODEL="llama3.2:1b"
```

**Free up resources:**
```bash
# Stop other processes using GPU
nvidia-smi --query-compute-apps=pid --format=csv
kill <PID>

# Reduce Ollama context size
export OLLAMA_NUM_CTX=2048
```

### Prevention
- Monitor Ollama response times
- Set appropriate timeouts based on model size

---

## Issue: Wrong Ollama Host

### Symptoms
- Works locally but not in Docker/production
- "Connection refused" with correct Ollama running

### Diagnosis
```bash
# Check configured host
echo $OLLAMA_HOST
grep -r "localhost:11434" *.py

# Test connectivity
curl http://$OLLAMA_HOST/api/tags
```

### Resolution

**Configure correct host:**
```bash
# For Docker networking
export OLLAMA_HOST="http://host.docker.internal:11434"

# For remote Ollama
export OLLAMA_HOST="http://ollama-server:11434"
```

**Update docker-compose.yml:**
```yaml
services:
  nova-nic:
    environment:
      - OLLAMA_HOST=http://ollama:11434
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
```

### Prevention
- Document host configuration
- Use environment variables consistently

---

## Issue: Ollama Out of Memory

### Symptoms
```
Error: OOM (Out of Memory)
CUDA error: out of memory
```

### Diagnosis
```bash
# Check GPU memory
nvidia-smi

# Check system memory
free -h
```

### Resolution

**Unload unused models:**
```bash
# List loaded models
curl http://localhost:11434/api/ps

# Unload specific model
curl -X DELETE http://localhost:11434/api/delete -d '{"name":"unused-model"}'
```

**Use quantized model:**
```bash
# Use Q4 quantized version (smaller)
ollama pull llama2:7b-q4_0
export NOVA_LLM_MODEL="llama2:7b-q4_0"
```

**Reduce context length:**
```bash
export OLLAMA_NUM_CTX=2048  # Default is 4096
```

### Prevention
- Monitor GPU/CPU memory
- Use appropriately sized models for hardware

---

## Issue: SSL/TLS Errors

### Symptoms
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
requests.exceptions.SSLError
```

### Resolution

**Disable SSL verification (development only):**
```python
# In llm_engine.py (NOT for production)
import urllib3
urllib3.disable_warnings()
requests.get(url, verify=False)
```

**Use correct certificate:**
```bash
export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
```

### Prevention
- Use proper certificates in production
- Document SSL configuration

---

## Issue: Rate Limiting

### Symptoms
- 429 Too Many Requests
- Intermittent failures under load

### Diagnosis
```bash
# Check Ollama logs for rate limiting
journalctl -u ollama | grep -i "rate\|limit"
```

### Resolution

**Add request queuing:**
```python
# In llm_engine.py
from queue import Queue
import threading

request_queue = Queue(maxsize=10)
```

**Scale Ollama instances:**
```bash
# Run multiple Ollama instances behind load balancer
# Instance 1
OLLAMA_HOST=0.0.0.0:11434 ollama serve
# Instance 2
OLLAMA_HOST=0.0.0.0:11435 ollama serve
```

### Prevention
- Implement request queuing
- Monitor request rate vs capacity

---

## Connection Test Script

Save as `test_ollama.py`:

```python
#!/usr/bin/env python3
"""Test Ollama connectivity and model availability."""

import os
import sys
import time
import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def test_connection():
    """Test basic connectivity."""
    print(f"Testing connection to {OLLAMA_HOST}...")
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        print("✓ Connection successful")
        return resp.json()
    except requests.exceptions.ConnectionError:
        print("✗ Connection refused - is Ollama running?")
        return None
    except requests.exceptions.Timeout:
        print("✗ Connection timed out")
        return None

def test_model(model_name):
    """Test model inference."""
    print(f"\nTesting model '{model_name}'...")
    try:
        start = time.time()
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": model_name, "prompt": "Say hello", "stream": False},
            timeout=60
        )
        resp.raise_for_status()
        elapsed = time.time() - start
        print(f"✓ Model responded in {elapsed:.2f}s")
        return True
    except Exception as e:
        print(f"✗ Model test failed: {e}")
        return False

if __name__ == "__main__":
    result = test_connection()
    if result:
        models = [m["name"] for m in result.get("models", [])]
        print(f"\nAvailable models: {models}")
        
        if models:
            test_model(models[0])
        else:
            print("\n⚠ No models installed. Run: ollama pull llama2")
    
    sys.exit(0 if result else 1)
```

---

## Escalation

If connection issues persist:

1. Collect Ollama diagnostics:
   ```bash
   ollama --version
   curl http://localhost:11434/api/tags > ollama_models.json
   journalctl -u ollama -n 200 > ollama_logs.txt
   ```

2. Check system resources:
   ```bash
   free -h > memory.txt
   nvidia-smi > gpu.txt  # If using GPU
   df -h > disk.txt
   ```

3. Open issue with:
   - Error messages
   - Ollama version
   - System specs (CPU, RAM, GPU)
   - Model being used

---

## Related Runbooks

- [Server Startup Issues](server-startup-issues.md)
- [High Latency](high-latency.md)
- [Memory Issues](memory-issues.md)
