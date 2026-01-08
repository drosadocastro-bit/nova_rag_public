# Resource Requirements

**Hardware and software requirements for NIC deployment**

---

## Quick Reference

| Deployment | CPU | RAM | Disk | Model Size |
|------------|-----|-----|------|------------|
| **Minimum** | 4 cores | 8GB | 10GB | 1-3B params |
| **Recommended** | 8 cores | 16GB | 20GB | 3-7B params |
| **High Performance** | 16+ cores | 32GB+ | 50GB+ | 7-14B params |

---

## Minimum Requirements

**For development, testing, and low-volume deployments**

### Hardware
- **CPU**: 4 cores (x86_64 or ARM64)
- **RAM**: 8GB
- **Disk**: 10GB free space
  - 2GB: Application and dependencies
  - 2-4GB: LLM models (llama3.2:1b or 3b)
  - 500MB: Embedding model (all-MiniLM-L6-v2)
  - 100-500MB: Vector indexes
  - 3GB: Working space

### Software
- **OS**: Linux (Ubuntu 20.04+), macOS (12+), Windows 10/11 with WSL2
- **Python**: 3.12 or 3.13
- **Ollama**: Latest version (or Docker)
- **Available Tools**: curl, git

### Network
- **Internet**: Required for initial setup (model downloads)
- **Runtime**: Air-gapped OK after setup
- **Bandwidth**: None (offline operation)

### Expected Performance
- **Query Latency**: 5-15 seconds
- **Throughput**: 1-2 queries/minute
- **Concurrent Users**: 1-2

---

## Recommended Requirements

**For production deployments in safety-critical environments**

### Hardware
- **CPU**: 8 cores (x86_64), 3.0+ GHz
- **RAM**: 16GB
- **Disk**: 20GB free space (SSD recommended)
  - 2GB: Application and dependencies
  - 6-8GB: LLM models (llama3.2:3b + qwen2.5-coder:7b)
  - 500MB: Embedding model
  - 500MB-1GB: Vector indexes
  - 8GB: Cache, logs, working space

### Software
- **OS**: Ubuntu 22.04 LTS (recommended), RHEL 8+, or equivalent
- **Python**: 3.12 (tested and validated)
- **Docker**: 20.10+ and Docker Compose 2.0+ (if containerized)
- **Ollama**: Latest stable version

### Network
- **Internet**: Required for initial setup only
- **Runtime**: Fully air-gapped capable
- **Internal**: 1Gbps LAN (if multi-server)

### Expected Performance
- **Query Latency**: 2-8 seconds
- **Throughput**: 5-10 queries/minute
- **Concurrent Users**: 5-10
- **Uptime**: 99.5%+

---

## High-Performance Configuration

**For high-volume or research deployments**

### Hardware
- **CPU**: 16+ cores (x86_64), 3.5+ GHz, or Apple M1/M2
- **RAM**: 32GB+
- **Disk**: 50GB+ free space (NVMe SSD)
  - 2GB: Application
  - 15-20GB: Multiple LLM models (8b-14b params)
  - 1GB: Embedding models (if using large models)
  - 5GB: Vector indexes (10k+ documents)
  - 27GB: Cache, logs, working space

### Optional: GPU
- **CUDA-capable GPU**: 8GB+ VRAM (for faster inference)
- **Drivers**: CUDA 12.0+
- **Note**: Not required; CPU inference is production-validated

### Software
- **OS**: Ubuntu 22.04 LTS or RHEL 9
- **Python**: 3.12
- **Docker**: Latest stable
- **Monitoring**: Prometheus + Grafana

### Expected Performance
- **Query Latency**: 1-4 seconds
- **Throughput**: 15-30 queries/minute
- **Concurrent Users**: 20-50
- **Uptime**: 99.9%+

---

## Component Breakdown

### Application Components

| Component | Disk | RAM (Idle) | RAM (Active) | CPU (Idle) | CPU (Active) |
|-----------|------|------------|--------------|------------|--------------|
| Flask App | 100MB | 200MB | 500MB | <5% | 10-20% |
| FAISS Index | 50-500MB | 200-500MB | 500MB-1GB | <1% | 20-40% |
| Embedding Model | 80MB | 500MB | 1GB | <1% | 30-50% |
| BM25 Cache | 10-100MB | 100-500MB | 500MB | <1% | 10-20% |
| Session Store | 1-10MB | 50MB | 100MB | <1% | <5% |

### LLM Model Sizes

| Model | Disk Size | RAM Usage | Inference Time | Quality |
|-------|-----------|-----------|----------------|---------|
| llama3.2:1b | 1.3GB | 2-3GB | Fast (2-4s) | Basic |
| llama3.2:3b | 2GB | 4-5GB | Good (3-6s) | Good |
| llama3.2:8b | 4.7GB | 8-10GB | Moderate (5-10s) | Excellent |
| qwen2.5-coder:7b | 4.2GB | 7-9GB | Moderate (4-8s) | Excellent |
| qwen2.5-coder:14b | 8.3GB | 14-16GB | Slow (8-15s) | Best |

### Document Corpus Scaling

| Corpus Size | Index Size | Build Time | RAM Usage | Query Time |
|-------------|------------|------------|-----------|------------|
| 100 docs | 10MB | 10s | 500MB | <1s |
| 1,000 docs | 50MB | 2min | 1GB | 1-2s |
| 10,000 docs | 500MB | 20min | 3GB | 2-3s |
| 100,000 docs | 5GB | 3hr | 10GB+ | 3-5s |

**Note**: BM25 disk caching (enabled by default) eliminates rebuild overhead for subsequent starts.

---

## Scaling Recommendations

### Vertical Scaling (Single Server)

**When to scale up:**
- Query latency > 10 seconds consistently
- Memory usage > 90%
- CPU usage > 80% sustained

**Upgrade path:**
1. Add RAM (8GB → 16GB → 32GB)
2. Upgrade to SSD (if HDD)
3. Add CPU cores (4 → 8 → 16)
4. Consider smaller models if latency is acceptable

### Horizontal Scaling (Multiple Servers)

**Architecture:**
```
                 ┌─────────────┐
                 │ Load Balancer│
                 └──────┬───────┘
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ NIC-1   │    │ NIC-2   │    │ NIC-3   │
    │ + Ollama│    │ + Ollama│    │ + Ollama│
    └─────────┘    └─────────┘    └─────────┘
         │              │              │
         └──────────────┼──────────────┘
                  ┌─────▼─────┐
                  │   Shared  │
                  │   Storage │
                  └───────────┘
```

**Shared components:**
- Vector indexes (read-only, NFS mount)
- Document corpus (read-only)
- Session store (Redis or shared DB)

**Per-server resources:**
- 8 cores, 16GB RAM, 20GB disk
- Dedicated Ollama instance
- Local model cache

---

## Environment-Specific Guidance

### Laptop / Development

**Typical Setup:**
- MacBook Pro M1/M2: 16GB RAM, 8 cores
- Dell XPS 15: 16GB RAM, 8 cores
- **Recommendation**: Use 1b-3b models, disable cross-encoder

```bash
export NOVA_LLM_LLAMA=llama3.2:3b
export NOVA_DISABLE_CROSS_ENCODER=1
```

### On-Premises Server

**Typical Setup:**
- Dell PowerEdge R450: 32GB RAM, 16 cores
- HP ProLiant DL380: 64GB RAM, 24 cores
- **Recommendation**: Use 7b-8b models, full features

```bash
export NOVA_LLM_LLAMA=llama3.2:8b
export NOVA_LLM_OSS=qwen2.5-coder:7b
export NOVA_HYBRID_SEARCH=1
```

### Edge Device / Remote Site

**Typical Setup:**
- Intel NUC: 8GB RAM, 4 cores
- Raspberry Pi 4 (8GB): 4 cores ARM64
- **Recommendation**: Use 1b models, minimal features

```bash
export NOVA_LLM_LLAMA=llama3.2:1b
export NOVA_DISABLE_CROSS_ENCODER=1
export NOVA_DISABLE_VISION=1
```

### Cloud VM (for testing, not air-gapped)

**Typical Setup:**
- AWS EC2 t3.xlarge: 4 vCPU, 16GB RAM
- Azure D4s_v3: 4 vCPU, 16GB RAM
- **Recommendation**: Use 3b-7b models

---

## Storage Breakdown

### Detailed Disk Usage

```
/app/                          (2.0 GB)
├── requirements.txt           (1 KB)
├── *.py                       (500 KB)
├── data/                      (40 KB - sample corpus)
├── models/                    (932 MB - embedding model)
│   └── all-MiniLM-L6-v2/
├── vector_db/                 (50-500 MB)
│   ├── *.faiss               (50-500 MB - FAISS index)
│   ├── *.pkl                 (10-100 MB - BM25 cache)
│   └── *.jsonl               (1-10 MB - document metadata)
├── ragas_results/             (1-10 MB - evaluation outputs)
└── docs/                      (500 KB - documentation)

/root/.ollama/                 (4-10 GB - Ollama models)
├── models/
│   ├── llama3.2-3b/          (2 GB)
│   └── qwen2.5-coder-7b/     (4.2 GB)
└── cache/                     (100-500 MB)
```

---

## Network Requirements

### Initial Setup (with internet)
- **Bandwidth**: 10GB+ download
  - 5-10GB: Ollama models
  - 1GB: Python dependencies
  - 100MB: Embedding models (if not included)
- **Ports**:
  - 5000: NIC Flask API
  - 11434: Ollama API

### Air-Gapped Operation
- **Bandwidth**: None required
- **Latency**: N/A (no external calls)
- **Ports**: Internal only (5000, 11434)

---

## Performance Benchmarks

### Query Latency (by model)

**Environment**: 8-core CPU, 16GB RAM, SSD

| Model | Retrieval | LLM Inference | Citation Audit | Total |
|-------|-----------|---------------|----------------|-------|
| llama3.2:1b | 0.5s | 2-3s | 0.2s | **2.7-3.7s** |
| llama3.2:3b | 0.5s | 3-5s | 0.2s | **3.7-5.7s** |
| llama3.2:8b | 0.6s | 6-10s | 0.3s | **6.9-10.9s** |

### Throughput (concurrent queries)

| Hardware | Model | Queries/Min | Max Concurrent |
|----------|-------|-------------|----------------|
| 4 cores, 8GB | 1b | 10-15 | 2 |
| 8 cores, 16GB | 3b | 8-12 | 5 |
| 16 cores, 32GB | 8b | 5-8 | 10 |

---

## Tuning Recommendations

### Low Memory (<8GB)
```bash
export NOVA_LLM_LLAMA=llama3.2:1b
export NOVA_DISABLE_CROSS_ENCODER=1
export NOVA_EMBED_BATCH_SIZE=8
export OMP_NUM_THREADS=2
```

### Optimize for Speed
```bash
export NOVA_LLM_LLAMA=llama3.2:3b
export NOVA_ENABLE_RETRIEVAL_CACHE=1
export NOVA_BM25_CACHE=1
```

### Optimize for Quality
```bash
export NOVA_LLM_LLAMA=llama3.2:8b
export NOVA_LLM_OSS=qwen2.5-coder:14b
export NOVA_HYBRID_SEARCH=1
```

---

## Monitoring

### Key Metrics to Track

1. **Memory**: Should stay < 80% of available
2. **CPU**: Spikes OK, sustained >80% indicates undersizing
3. **Disk I/O**: Should be < 100MB/s (SSD), < 20MB/s (HDD)
4. **Query Latency**: Target < 10s for safety-critical use

### Tools
- `docker stats` (if containerized)
- `htop` / `top` (Linux)
- Activity Monitor (macOS)
- Task Manager (Windows)

---

## Deployment Checklist

- [ ] CPU: 4+ cores (8+ recommended)
- [ ] RAM: 8GB+ (16GB+ recommended)
- [ ] Disk: 10GB+ free, SSD preferred
- [ ] OS: Linux/macOS/Windows with WSL2
- [ ] Python: 3.12 installed
- [ ] Ollama: Installed and running
- [ ] Models: Downloaded (llama3.2:3b minimum)
- [ ] Network: Internet for setup, air-gap OK after

---

**For detailed deployment steps, see:**
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Containerized deployment
- [AIR_GAPPED_DEPLOYMENT.md](AIR_GAPPED_DEPLOYMENT.md) - Offline setup
- [CONFIGURATION.md](CONFIGURATION.md) - Environment variables
