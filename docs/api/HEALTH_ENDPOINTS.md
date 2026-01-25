# Health Check Endpoints

Nova NIC provides comprehensive health check endpoints for production monitoring, Kubernetes integration, and load balancer health probes.

## Quick Reference

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /health` | Full system health report | 60/min |
| `GET /health/ready` | Kubernetes readiness probe | 120/min |
| `GET /health/live` | Kubernetes liveness probe | 300/min |

---

## `/health` - Full Health Report

Returns detailed status of all system components.

### Request

```bash
curl http://localhost:5000/health
```

### Response

```json
{
  "status": "healthy",
  "timestamp": "2026-01-25T10:30:00Z",
  "version": "0.3.5",
  "checks": {
    "database": {
      "status": "pass",
      "latency_ms": 12.5,
      "tables": 3
    },
    "faiss_index": {
      "status": "pass",
      "latency_ms": 1.2,
      "vectors": 6610,
      "chunks": 6610
    },
    "bm25_cache": {
      "status": "pass",
      "latency_ms": 0.8,
      "message": "BM25 index loaded in memory",
      "cache_enabled": true
    },
    "ollama": {
      "status": "pass",
      "latency_ms": 45.3,
      "models": ["llama3.2:8b", "nomic-embed-text"],
      "model_count": 2
    },
    "disk_space": {
      "status": "pass",
      "latency_ms": 0.5,
      "available_gb": 15.3,
      "used_percent": 68.2
    },
    "memory": {
      "status": "warn",
      "latency_ms": 0.3,
      "message": "Memory usage elevated: 82.5%",
      "usage_percent": 82.5,
      "available_gb": 4.2
    }
  }
}
```

### Status Values

| Status | HTTP Code | Description |
|--------|-----------|-------------|
| `healthy` | 200 | All checks pass |
| `degraded` | 200 | Some warnings but operational |
| `unhealthy` | 503 | Critical failures detected |

### Check Status Values

| Check Status | Meaning |
|--------------|---------|
| `pass` | Check successful |
| `warn` | Non-critical issue detected |
| `fail` | Critical failure |

---

## `/health/ready` - Readiness Probe

Kubernetes readiness probe. Indicates whether the service can accept traffic.

### Request

```bash
curl http://localhost:5000/health/ready
```

### Response (Ready)

```json
{
  "ready": true,
  "timestamp": "2026-01-25T10:30:00Z",
  "checks": {
    "database": {"status": "pass", "latency_ms": 12.5},
    "faiss_index": {"status": "pass", "vectors": 6610},
    "ollama": {"status": "pass", "models": ["llama3.2:8b"]}
  }
}
```

### Response (Not Ready)

```json
{
  "ready": false,
  "timestamp": "2026-01-25T10:30:00Z",
  "checks": {
    "database": {"status": "pass"},
    "faiss_index": {"status": "pass"},
    "ollama": {"status": "fail", "message": "Cannot connect to Ollama at http://127.0.0.1:11434"}
  }
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Ready to serve traffic |
| 503 | Not ready (startup in progress or dependency failure) |

### Kubernetes Configuration

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 5000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 3
```

---

## `/health/live` - Liveness Probe

Kubernetes liveness probe. Indicates whether the process is alive and responsive.

### Request

```bash
curl http://localhost:5000/health/live
```

### Response (Alive)

```json
{
  "alive": true,
  "timestamp": "2026-01-25T10:30:00Z",
  "latency_ms": 0.15,
  "process_memory_mb": 512.3
}
```

### Response (Dead/Deadlocked)

```json
{
  "alive": false,
  "timestamp": "2026-01-25T10:30:00Z",
  "error": "Process unresponsive"
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Process is alive |
| 503 | Process may be deadlocked (consider restart) |

### Kubernetes Configuration

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 5000
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3
```

---

## Individual Check Details

### Database Check

Verifies SQLite analytics database connectivity.

- **Pass**: Database accessible, can query tables
- **Warn**: Database file not found (will create on first request)
- **Fail**: Connection error or corruption

### FAISS Index Check

Verifies vector search index is loaded.

- **Pass**: Index loaded with vectors
- **Warn**: Index not loaded (using fallback retrieval)
- **Fail**: Index corruption or load error

### BM25 Cache Check

Verifies lexical search cache status.

- **Pass**: BM25 index in memory or cache file available
- **Warn**: Cache not built (will build on first query)
- **Fail**: Cache access error

### Ollama Check

Verifies LLM service connectivity.

- **Pass**: Ollama responding with loaded models
- **Warn**: Ollama running but no models loaded
- **Fail**: Connection refused, timeout, or error

### Disk Space Check

Monitors available storage.

- **Pass**: >5GB available
- **Warn**: 1-5GB available
- **Fail**: <1GB available (configurable via `NOVA_HEALTH_DISK_MIN_GB`)

### Memory Check

Monitors system memory usage.

- **Pass**: <80% usage
- **Warn**: 80-90% usage
- **Fail**: >90% usage (configurable via `NOVA_HEALTH_MEMORY_MAX_PERCENT`)

---

## Configuration

Environment variables for health check thresholds:

| Variable | Default | Description |
|----------|---------|-------------|
| `NOVA_HEALTH_DISK_MIN_GB` | `1.0` | Minimum disk space (GB) before failure |
| `NOVA_HEALTH_MEMORY_MAX_PERCENT` | `90.0` | Maximum memory usage before failure |
| `NOVA_HEALTH_OLLAMA_TIMEOUT` | `5.0` | Ollama connectivity timeout (seconds) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama service URL |

---

## Load Balancer Integration

### AWS ALB/NLB

```yaml
HealthCheckPath: /health/ready
HealthCheckIntervalSeconds: 30
HealthyThresholdCount: 2
UnhealthyThresholdCount: 3
```

### NGINX

```nginx
upstream nova_backend {
    server 127.0.0.1:5000;
    health_check uri=/health/ready interval=10s fails=3 passes=2;
}
```

### HAProxy

```haproxy
backend nova
    option httpchk GET /health/ready
    http-check expect status 200
    server nova1 127.0.0.1:5000 check
```

---

## Monitoring Integration

### Prometheus Alert Rules

```yaml
groups:
  - name: nova-health
    rules:
      - alert: NovaUnhealthy
        expr: probe_success{job="nova-health"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Nova NIC health check failing"
```

### Grafana Dashboard

Monitor health status with:
- Panel: Health check latency over time
- Alert: Trigger on 503 responses
- Gauge: Memory/disk usage from `/health` response

---

## Related Documentation

- [Monitoring Guide](../operations/MONITORING.md)
- [API Overview](README.md)
- [Deployment Guide](../deployment/README.md)
