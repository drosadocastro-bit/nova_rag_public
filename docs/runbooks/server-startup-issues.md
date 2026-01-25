# Runbook: Server Won't Start

## Symptoms
- Flask app fails to start
- Gunicorn/Waitress exits immediately
- "Address already in use" errors
- Import errors on startup

---

## Quick Diagnosis

```bash
# Check if port is in use
netstat -ano | findstr :5000   # Windows
lsof -i :5000                  # Linux

# Check Python environment
python --version
pip list | grep -E "flask|gunicorn|waitress"

# Verify required files exist
ls -la vector_db/  # FAISS index
ls -la cache/      # Cache directories
```

---

## Issue: Port Already in Use

### Symptoms
```
OSError: [Errno 98] Address already in use
```

### Resolution

**Windows:**
```powershell
# Find process using port 5000
netstat -ano | findstr :5000
# Kill process (replace <PID>)
taskkill /PID <PID> /F
```

**Linux:**
```bash
# Find and kill process
sudo fuser -k 5000/tcp
# Or use
kill $(lsof -t -i:5000)
```

### Prevention
- Use `run_waitress.py` which handles graceful shutdown
- Configure unique port via `NOVA_PORT` environment variable

---

## Issue: Missing Dependencies

### Symptoms
```
ModuleNotFoundError: No module named 'flask'
ImportError: cannot import name 'X' from 'Y'
```

### Resolution

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux
.venv\Scripts\Activate.ps1  # Windows

# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
python -c "import flask; import faiss; print('OK')"
```

### Prevention
- Always use virtual environment
- Pin dependency versions in requirements.txt

---

## Issue: FAISS Index Not Found

### Symptoms
```
FileNotFoundError: vector_db/faiss_index.bin not found
RuntimeError: Could not load FAISS index
```

### Resolution

```bash
# Check if index exists
ls -la vector_db/

# If missing, rebuild from documents
python ingest_vehicle_manual.py

# Verify index loads
python -c "
import faiss
index = faiss.read_index('vector_db/faiss_index.bin')
print(f'Index has {index.ntotal} vectors')
"
```

### Prevention
- Include vector_db/ in backups
- Monitor disk space (index can be large)

---

## Issue: Ollama Not Running

### Symptoms
```
ConnectionRefusedError: [Errno 111] Connection refused
requests.exceptions.ConnectionError: HTTPConnectionPool
```

### Resolution

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve &

# Verify models are available
ollama list
```

### Prevention
- Add Ollama health check to startup script
- Use systemd service for automatic restart

---

## Issue: Permission Errors

### Symptoms
```
PermissionError: [Errno 13] Permission denied: 'logs/nova.log'
OSError: [Errno 30] Read-only file system
```

### Resolution

```bash
# Fix ownership
chown -R $USER:$USER logs/ cache/ vector_db/

# Fix permissions
chmod 755 logs/ cache/ vector_db/
chmod 644 logs/*.log
```

### Prevention
- Run as non-root user
- Ensure log directory exists before starting

---

## Issue: Memory Allocation Failure

### Symptoms
```
MemoryError: Unable to allocate X GiB
RuntimeError: CUDA out of memory
```

### Resolution

```bash
# Check available memory
free -h  # Linux
systeminfo | findstr Memory  # Windows

# Reduce batch size in config
export NOVA_BATCH_SIZE=8

# Use smaller embedding model
export EMBEDDING_MODEL="all-MiniLM-L6-v2"
```

### Prevention
- Monitor memory usage with health endpoints
- Set memory limits in Docker/systemd

---

## Startup Checklist

Before starting the server, verify:

- [ ] Virtual environment activated
- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] FAISS index exists (`vector_db/faiss_index.bin`)
- [ ] Ollama is running (`curl localhost:11434/api/tags`)
- [ ] Required directories exist (`logs/`, `cache/`, `vector_db/`)
- [ ] Port 5000 is available
- [ ] Sufficient memory (>2GB free)
- [ ] Sufficient disk space (>1GB free)

---

## Escalation

If none of the above resolves the issue:

1. Collect diagnostic information:
   ```bash
   python diagnose_server.py > diagnostics.txt 2>&1
   ```

2. Check logs:
   ```bash
   tail -100 logs/nova.log
   tail -100 server.err
   ```

3. Open issue with:
   - Error message
   - Steps to reproduce
   - Diagnostics output
   - Environment details (OS, Python version)

---

## Related Runbooks

- [High Latency](high-latency.md)
- [Ollama Connection Issues](ollama-connection.md)
- [Memory Issues](memory-issues.md)
