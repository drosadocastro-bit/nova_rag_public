# Nova NIC Production Deployment Checklist

Use this checklist before deploying Nova NIC to production.

## Pre-Deployment

### 1. Security Configuration
- [ ] Generate unique `SECRET_KEY` using `openssl rand -hex 32`
- [ ] Generate unique `NOVA_CACHE_SECRET` using `openssl rand -hex 32`
- [ ] Review and set `NOVA_API_TOKEN` if API authentication required
- [ ] Verify `.env` file is in `.gitignore`
- [ ] Confirm no secrets in version control

### 2. Model Preparation
- [ ] Download embedding model to `models/nic-embeddings-v1.0`
- [ ] Pull required Ollama models:
  ```bash
  ollama pull llama3.2:3b
  ollama pull qwen2.5-coder:7b
  ```
- [ ] For offline deployment: verify all models cached locally
- [ ] Test model loading: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('models/nic-embeddings-v1.0')"`

### 3. Index Preparation
- [ ] Build or copy FAISS index to `vector_db/`
- [ ] Build or copy BM25 index
- [ ] Verify index integrity: `python verify_offline_requirements.py`
- [ ] Test retrieval: `python quick_sanity_check.py`

### 4. Configuration Review
- [ ] Copy appropriate template: `cp config/production.env.template .env`
- [ ] Update all `CHANGE_ME` placeholders
- [ ] Set `NOVA_ENV=production`
- [ ] Enable `NOVA_GAR_ENABLED=1`
- [ ] Enable `NOVA_CITATION_AUDIT=1`
- [ ] Configure rate limiting appropriately
- [ ] Run config validation: `python -c "from core.config import validate_startup; validate_startup()"`

### 5. Infrastructure
- [ ] Allocate sufficient RAM (minimum 8GB recommended)
- [ ] Allocate sufficient disk space (check index sizes)
- [ ] Configure log rotation
- [ ] Set up monitoring endpoints
- [ ] Configure backup schedule

## Deployment

### 6. Docker Deployment
```bash
# Build image
docker compose build

# Start services
docker compose up -d

# Check health
docker compose ps
docker logs nic-app --tail 100

# Verify health check
curl http://localhost:5000/api/status
curl http://localhost:5000/health
curl http://localhost:5000/ready
```

### 7. Non-Docker Deployment
```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.\.venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install -r requirements.txt

# Run with production server
python run_waitress.py
# OR
gunicorn -c gunicorn_config.py nova_flask_app:app
```

## Post-Deployment Verification

### 8. Health Checks
- [ ] `/api/status` returns 200
- [ ] `/health` shows all checks passing
- [ ] `/ready` returns ready=true
- [ ] `/metrics` returns Prometheus metrics

### 9. Functional Tests
- [ ] Submit test query to each domain
- [ ] Verify response includes citations
- [ ] Check response times are within SLA (<3s P95)
- [ ] Verify safety filters working (test with known unsafe query)

### 10. Monitoring Setup
- [ ] Prometheus scraping `/metrics`
- [ ] Alerting configured for:
  - [ ] Error rate > 5%
  - [ ] P95 latency > 3s
  - [ ] Disk space < 2GB
  - [ ] Memory usage > 85%
- [ ] Log aggregation configured
- [ ] Dashboard created

### 11. Backup Verification
- [ ] Backup script tested
- [ ] Restore procedure documented and tested
- [ ] Backup schedule confirmed

## Rollback Plan

In case of deployment issues:

1. **Immediate rollback:**
   ```bash
   docker compose down
   docker compose -f docker-compose.previous.yml up -d
   ```

2. **Check logs for issues:**
   ```bash
   docker logs nic-app --tail 500
   cat logs/nova.log | tail -100
   ```

3. **Common issues:**
   - Model not found: Check `models/` directory
   - Index corruption: Restore from backup
   - Memory issues: Reduce `NOVA_EMBED_BATCH_SIZE`
   - Ollama timeout: Increase `NOVA_HEALTH_OLLAMA_TIMEOUT`

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| QA | | | |
| Operations | | | |
| Security | | | |

---

**Version:** 1.0  
**Last Updated:** 2026-01-25  
**Maintained By:** Nova NIC Team
