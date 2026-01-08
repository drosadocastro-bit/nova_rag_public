# Docker Deployment Guide

**Quick start for containerized NIC deployment**

---

## Prerequisites

- Docker Engine 20.10+ and Docker Compose 2.0+
- 8GB+ RAM, 20GB+ disk space
- Linux, macOS, or Windows with WSL2

---

## Quick Start

### 1. Build and Start Services

```bash
# Clone repository
git clone https://github.com/yourusername/nova_rag_public.git
cd nova_rag_public

# Start all services
docker-compose up -d

# Check service status
docker-compose ps
docker-compose logs -f nic
```

### 2. Pull LLM Models

```bash
# Access Ollama container
docker exec -it nic-ollama ollama pull llama3.2:3b
docker exec -it nic-ollama ollama pull qwen2.5-coder:7b

# Verify models
docker exec -it nic-ollama ollama list
```

### 3. Access Application

Open browser: **http://localhost:5000**

---

## Configuration

### Environment Variables

Edit `docker-compose.yml` to configure:

```yaml
environment:
  # Required: LLM models
  - NOVA_LLM_LLAMA=llama3.2:3b
  - NOVA_LLM_OSS=qwen2.5-coder:7b
  
  # Required: Security key (generate with: openssl rand -hex 32)
  - SECRET_KEY=your-secret-key-here
  
  # Optional: Feature toggles
  - NOVA_HYBRID_SEARCH=1          # Enable BM25 + vector search
  - NOVA_ENABLE_RETRIEVAL_CACHE=1  # Enable caching
  - NOVA_BM25_CACHE=1              # Enable BM25 disk cache
```

### Custom Data

Mount your own corpus data:

```yaml
volumes:
  - ./my-corpus:/app/data:ro
```

Then rebuild the index inside the container:

```bash
docker exec -it nic-app python ingest_vehicle_manual.py
```

---

## Air-Gapped Deployment

For environments without internet access:

### 1. Prepare Offline Bundle

On a machine with internet:

```bash
# Pull all images
docker pull python:3.12-slim
docker pull ollama/ollama:latest

# Build NIC image
docker-compose build

# Save images to tar files
docker save -o nic-app.tar nic-app:latest
docker save -o ollama.tar ollama/ollama:latest

# Download Ollama models
docker run --rm -v $(pwd)/ollama-models:/root/.ollama ollama/ollama:latest \
  ollama pull llama3.2:3b

# Create transfer bundle
tar czf nic-airgap-bundle.tar.gz \
  nic-app.tar \
  ollama.tar \
  ollama-models/ \
  docker-compose.yml \
  .env.example
```

### 2. Transfer Bundle

Copy `nic-airgap-bundle.tar.gz` to air-gapped system via approved media (USB, secure transfer).

### 3. Load on Air-Gapped System

```bash
# Extract bundle
tar xzf nic-airgap-bundle.tar.gz

# Load Docker images
docker load -i nic-app.tar
docker load -i ollama.tar

# Place Ollama models
docker volume create ollama-models
docker run --rm -v ollama-models:/dest -v $(pwd)/ollama-models:/src \
  alpine sh -c "cp -r /src/* /dest/"

# Start services
docker-compose up -d
```

---

## Production Deployment

### Security Hardening

1. **Generate Secure Key**
   ```bash
   openssl rand -hex 32 > .env
   echo "SECRET_KEY=$(cat .env)" > .env
   ```

2. **Use Secrets Management**
   ```yaml
   # docker-compose.yml
   secrets:
     secret_key:
       file: ./secret_key.txt
   
   services:
     nic:
       secrets:
         - secret_key
       environment:
         - SECRET_KEY_FILE=/run/secrets/secret_key
   ```

3. **Enable HTTPS** (use reverse proxy like nginx)
   ```yaml
   services:
     nginx:
       image: nginx:alpine
       ports:
         - "443:443"
       volumes:
         - ./nginx.conf:/etc/nginx/nginx.conf
         - ./ssl:/etc/nginx/ssl
   ```

### Resource Limits

Set memory and CPU limits:

```yaml
services:
  nic:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### Persistent Logging

```yaml
services:
  nic:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Management Commands

### Service Control

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart service
docker-compose restart nic

# View logs
docker-compose logs -f nic
docker-compose logs --tail=100 ollama

# Execute commands in container
docker exec -it nic-app python quick_sanity_check.py
```

### Health Checks

```bash
# Check service health
docker-compose ps

# Test API
curl http://localhost:5000/api/status

# Check Ollama
curl http://localhost:11434/api/tags
```

### Backup & Restore

```bash
# Backup volumes
docker run --rm -v nic_vector_db:/data -v $(pwd):/backup \
  alpine tar czf /backup/vector_db_backup.tar.gz -C /data .

# Restore volumes
docker run --rm -v nic_vector_db:/data -v $(pwd):/backup \
  alpine tar xzf /backup/vector_db_backup.tar.gz -C /data
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs nic

# Verify Ollama connectivity
docker exec -it nic-app curl http://ollama:11434/api/tags
```

### Models Not Found

```bash
# Verify models are pulled
docker exec -it nic-ollama ollama list

# Re-pull if needed
docker exec -it nic-ollama ollama pull llama3.2:3b
```

### Permission Issues

```bash
# Fix volume permissions
docker-compose down
sudo chown -R 1000:1000 vector_db/ data/
docker-compose up -d
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Adjust memory limits in docker-compose.yml
# Reduce model size (use 3b instead of 7b/8b)
```

---

## Performance Tuning

### For Low-Spec Systems

Use smaller models:
```yaml
environment:
  - NOVA_LLM_LLAMA=llama3.2:1b
  - NOVA_DISABLE_CROSS_ENCODER=1
```

### For High-Performance

Use larger models and enable features:
```yaml
environment:
  - NOVA_LLM_LLAMA=llama3.2:8b
  - NOVA_LLM_OSS=qwen2.5-coder:14b
  - NOVA_HYBRID_SEARCH=1
  - NOVA_ENABLE_RETRIEVAL_CACHE=1
```

---

## Monitoring

### Prometheus Metrics

Add Prometheus exporter:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
```

### Health Monitoring

```bash
# Continuous health check
watch -n 5 'curl -s http://localhost:5000/api/status | jq'
```

---

## Updating

### Pull Latest Changes

```bash
# Stop services
docker-compose down

# Update code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d
```

### Update Models

```bash
# Pull new model version
docker exec -it nic-ollama ollama pull llama3.2:latest

# Restart NIC to use new model
docker-compose restart nic
```

---

## Cleanup

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v

# Remove images
docker rmi nic-app:latest
docker rmi ollama/ollama:latest
```

---

## Next Steps

- See [RESOURCE_REQUIREMENTS.md](RESOURCE_REQUIREMENTS.md) for sizing guidance
- See [AIR_GAPPED_DEPLOYMENT.md](AIR_GAPPED_DEPLOYMENT.md) for detailed offline setup
- See [CONFIGURATION.md](CONFIGURATION.md) for all environment variables

---

**Docker deployment tested on:**
- Ubuntu 22.04 LTS
- macOS 13+ (Apple Silicon and Intel)
- Windows 11 with WSL2
