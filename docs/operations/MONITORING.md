# Nova NIC Monitoring Guide

This document describes the Prometheus metrics exposed by Nova NIC for production monitoring and observability.

## Quick Start

### Prerequisites

- Nova NIC server running on port 5000
- Prometheus server (optional, for scraping)
- Grafana (optional, for visualization)

### Accessing Metrics

```bash
# Fetch metrics in Prometheus format
curl http://localhost:5000/metrics

# Example output
# HELP nova_queries_total Total number of queries processed
# TYPE nova_queries_total counter
nova_queries_total{domain="vehicle",safety_check_passed="true"} 42.0
```

---

## Available Metrics

### Query Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_queries_total` | Counter | `domain`, `safety_check_passed` | Total queries processed |
| `nova_query_latency_seconds` | Histogram | `stage` | Query latency by processing stage |

**Labels:**
- `domain`: Query domain (`vehicle`, `medical`, `aerospace`, `nuclear`, `electronics`, `unknown`)
- `safety_check_passed`: Whether query passed safety checks (`true`/`false`)
- `stage`: Processing stage (`retrieval`, `generation`, `safety`, `total`)

**Example Queries (PromQL):**
```promql
# Queries per second by domain
rate(nova_queries_total[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(nova_query_latency_seconds_bucket[5m]))

# Safety rejection rate
sum(rate(nova_queries_total{safety_check_passed="false"}[5m])) 
/ sum(rate(nova_queries_total[5m]))
```

---

### Retrieval Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_retrieval_confidence_score` | Gauge | - | Current retrieval confidence (0-1) |

**Example Queries:**
```promql
# Average confidence over time
avg_over_time(nova_retrieval_confidence_score[1h])

# Alert on low confidence
nova_retrieval_confidence_score < 0.5
```

---

### Safety Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_hallucination_preventions_total` | Counter | `reason` | Hallucination preventions |

**Labels:**
- `reason`: Prevention reason (`low_confidence`, `no_sources`, `conflicting_evidence`, `safety_filter`)

**Example Queries:**
```promql
# Prevention rate by reason
rate(nova_hallucination_preventions_total[5m])

# Top prevention reasons
topk(5, sum by (reason) (nova_hallucination_preventions_total))
```

---

### Session Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_active_sessions` | Gauge | - | Currently active sessions |

**Example Queries:**
```promql
# Active sessions over time
nova_active_sessions

# Peak sessions in last 24h
max_over_time(nova_active_sessions[24h])
```

---

### Cache Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_cache_hits_total` | Counter | - | Total cache hits |
| `nova_cache_misses_total` | Counter | - | Total cache misses |

**Example Queries:**
```promql
# Cache hit ratio
sum(rate(nova_cache_hits_total[5m])) 
/ (sum(rate(nova_cache_hits_total[5m])) + sum(rate(nova_cache_misses_total[5m])))

# Cache efficiency over time
increase(nova_cache_hits_total[1h]) / increase(nova_cache_misses_total[1h])
```

---

### Index Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `nova_index_build_seconds` | Histogram | - | Index build duration |

**Example Queries:**
```promql
# Average index build time
histogram_quantile(0.5, rate(nova_index_build_seconds_bucket[1d]))

# Alert on slow builds
histogram_quantile(0.95, rate(nova_index_build_seconds_bucket[1h])) > 300
```

---

## Prometheus Configuration

Add Nova NIC as a scrape target in your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'nova-nic'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

For Kubernetes environments:

```yaml
scrape_configs:
  - job_name: 'nova-nic'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: nova-nic
        action: keep
```

---

## Grafana Dashboard

### Recommended Panels

1. **Query Rate** - `rate(nova_queries_total[5m])`
2. **Latency P95** - `histogram_quantile(0.95, rate(nova_query_latency_seconds_bucket[5m]))`
3. **Safety Rejection Rate** - Safety check failures as percentage
4. **Cache Hit Ratio** - Cache efficiency gauge
5. **Active Sessions** - Current session count
6. **Hallucination Preventions** - Prevention rate by reason

### Import Dashboard

A pre-built Grafana dashboard JSON is available at:
`docs/operations/grafana-dashboard.json` (if available)

---

## Alerting Rules

### Example Prometheus Alert Rules

```yaml
groups:
  - name: nova-nic-alerts
    rules:
      # High error rate
      - alert: NovaHighErrorRate
        expr: sum(rate(nova_queries_total{safety_check_passed="false"}[5m])) / sum(rate(nova_queries_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High safety rejection rate"
          description: "More than 10% of queries are being rejected by safety checks"

      # High latency
      - alert: NovaHighLatency
        expr: histogram_quantile(0.95, rate(nova_query_latency_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High query latency"
          description: "95th percentile latency exceeds 5 seconds"

      # Low retrieval confidence
      - alert: NovaLowConfidence
        expr: avg_over_time(nova_retrieval_confidence_score[5m]) < 0.3
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low retrieval confidence"
          description: "Average retrieval confidence is below 30%"

      # Cache degradation
      - alert: NovaCacheDegradation
        expr: |
          sum(rate(nova_cache_hits_total[5m])) 
          / (sum(rate(nova_cache_hits_total[5m])) + sum(rate(nova_cache_misses_total[5m]))) < 0.2
        for: 15m
        labels:
          severity: info
        annotations:
          summary: "Low cache hit ratio"
          description: "Cache hit ratio is below 20%"
```

---

## Troubleshooting

### Metrics endpoint returns empty

1. Ensure the server is running: `curl http://localhost:5000/api/status`
2. Check for import errors in logs
3. Verify `prometheus-client` is installed: `pip show prometheus-client`

### Metrics not updating

1. Confirm queries are being processed via `/api/ask`
2. Check that the Flask app is using the instrumented endpoints
3. Verify cache is enabled: `NOVA_ENABLE_RETRIEVAL_CACHE=1`

### High cardinality warnings

If you see high cardinality warnings, check that:
- Domain labels are normalized (not raw source paths)
- Custom labels are limited to expected values

---

## Security Considerations

- The `/metrics` endpoint is rate-limited (120 requests/minute)
- No sensitive data is exposed in metrics
- Consider restricting access in production:
  ```nginx
  location /metrics {
      allow 10.0.0.0/8;  # Internal network only
      deny all;
  }
  ```

---

## Related Documentation

- [API Documentation](../api/README.md)
- [Safety Architecture](../safety/README.md)
- [Deployment Guide](../deployment/README.md)
