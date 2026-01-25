# Phase 4.1: Quick Reference Guide

## 5-Minute Setup

### 1. Start Flask App with Observability

```python
from flask import Flask
from core.observability_flask import configure_observability

app = Flask(__name__)
obs_manager, notif_manager = configure_observability(app)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
```

### 2. Access Dashboard

```bash
# Open in browser
http://localhost:5000/dashboard/
```

### 3. Configure Alerts

```python
from core.observability import AlertRule, AlertSeverity

rule = AlertRule(
    name="high_latency",
    description="Query > 200ms",
    metric_name="query_latency_ms",
    operator=">",
    threshold=200.0,
    severity=AlertSeverity.WARNING,
)

obs_manager.alert_manager.add_rule(rule)
```

### 4. Log Queries

```python
from core.observability import QueryLog

query_log = QueryLog(
    query_id="abc123",
    timestamp=time.time(),
    query_text="What is NIC?",
    duration_ms=75.5,
)

obs_manager.record_query(query_log)
```

## API Quick Reference

### Metrics Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/observability/metrics` | GET | Prometheus format metrics |
| `/api/observability/metrics/json` | GET | JSON metrics |
| `/api/observability/dashboard` | GET | Dashboard data |

### Alert Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/observability/alerts` | GET | Active alerts |
| `/api/observability/alerts/rules` | GET | Alert rules |
| `/api/observability/alerts/rules` | POST | Create rule |
| `/api/observability/test/alert` | POST | Test alert |

### Log Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/observability/queries` | GET | Query logs |
| `/api/observability/events` | GET | Event logs |
| `/api/observability/notifications` | GET | Notifications |

### Status Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/observability/health` | GET | Health check |
| `/api/observability/status` | GET | System status |

## Common Tasks

### Monitor Query Performance

```bash
# Get recent queries
curl http://localhost:5000/api/observability/queries?limit=20 | jq '.'

# Filter slow queries
curl http://localhost:5000/api/observability/queries | jq '.[] | select(.duration_ms > 200)'

# Get statistics
curl http://localhost:5000/api/observability/metrics/json | jq '.metric_stats.query_latency_ms'
```

### Set Up Slack Webhook

```python
from core.notifications import NotificationConfig, configure_notifications

config = NotificationConfig(
    webhook_enabled=True,
    webhook_url="https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
)

notif = configure_notifications(config)
```

### Create Custom Alert

```python
from core.observability import AlertRule, AlertSeverity

rule = AlertRule(
    name="low_cache_hit",
    description="Cache hit rate < 50%",
    metric_name="cache_hit_rate",
    operator="<",
    threshold=0.5,
    severity=AlertSeverity.WARNING,
    cooldown_seconds=600,
)

obs_manager.alert_manager.add_rule(rule)
```

### Export Metrics to Prometheus

```bash
# Prometheus config (prometheus.yml)
scrape_configs:
  - job_name: 'nova-nic'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/api/observability/metrics'
    scrape_interval: 15s
```

## Environment Variables

```bash
# Enable/disable components
NOVA_METRICS_ENABLED=true
NOVA_ALERTS_ENABLED=true
NOVA_AUDIT_ENABLED=true
NOVA_DASHBOARD_ENABLED=true

# Configure storage
NOVA_METRICS_MAX_POINTS=10000
NOVA_AUDIT_LOG_DIR=logs
NOVA_AUDIT_RETENTION_DAYS=30

# Alert defaults
NOVA_ALERTS_COOLDOWN_SECONDS=300

# Notifications
NOVA_WEBHOOK_ENABLED=false
NOVA_WEBHOOK_URL=
NOVA_WEBHOOK_SECRET=
```

## Dashboard Features

| Feature | Description |
|---------|-------------|
| **Status Indicator** | Live system health pulse |
| **Uptime Counter** | Total running time |
| **Performance Metrics** | P95 latency, memory, cache hit % |
| **Query Statistics** | Total, failed, error rate |
| **Hardware Info** | Active tier, models loaded, batch size |
| **Latency Chart** | Last 50 queries trend |
| **Alert Panel** | Active alerts with severity |
| **Query Log** | Recent 20 queries |
| **Auto-Refresh** | Every 5 seconds |

## Troubleshooting

### Dashboard Not Loading

```bash
# Check if API is responding
curl http://localhost:5000/api/observability/health

# Check Flask logs
# Look for "Observability configured successfully"
```

### Alerts Not Triggering

```bash
# Verify rule exists
curl http://localhost:5000/api/observability/alerts/rules

# Check metric values
curl http://localhost:5000/api/observability/metrics/json

# Verify threshold is correct
# (Metric value must exceed threshold)
```

### High Disk Usage

```bash
# Configure retention
NOVA_AUDIT_RETENTION_DAYS=7

# Or manually clean logs
find logs/ -type f -mtime +30 -delete
```

## Metrics Reference

### Recording a Metric

```python
# Simple metric
obs_manager.metrics.record("latency_ms", 50.0)

# With labels
obs_manager.metrics.record("latency_ms", 50.0, {
    "tier": "lite",
    "model": "embedding",
})
```

### Getting Statistics

```python
stats = obs_manager.metrics.get_stats("latency_ms")

# Returns:
# {
#   "count": 1000,
#   "sum": 50000,
#   "mean": 50.0,
#   "min": 10.0,
#   "max": 200.0,
#   "p50": 45.0,
#   "p95": 150.0,
#   "p99": 190.0,
# }
```

## Alert Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `>` | Greater than | Latency > 200ms |
| `<` | Less than | Cache hit < 50% |
| `==` | Equal to | Error count == 10 |
| `!=` | Not equal to | Status != "healthy" |

## Severity Levels

| Severity | Color | Use Case |
|----------|-------|----------|
| CRITICAL | Red | System failures, OOM |
| WARNING | Orange | Performance degradation |
| INFO | Blue | Informational events |

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Record metric | <0.1ms | Async, non-blocking |
| Calculate p95 | <5ms | For 10K points |
| Alert evaluation | <1ms | For 10 rules |
| Log query | <1ms | Buffered write |
| Dashboard refresh | <100ms | From API |

## Testing

```bash
# Run all tests
pytest tests/test_observability.py -v

# Run specific test class
pytest tests/test_observability.py::TestMetricsCollector -v

# Trigger test alert
curl -X POST http://localhost:5000/api/observability/test/alert
```

## Next Steps

1. **Deploy**: Integrate into Flask app
2. **Configure**: Set notification channels
3. **Monitor**: Open dashboard, set alerts
4. **Analyze**: Track performance trends
5. **Optimize**: Use insights for Phase 4.3

---

For detailed documentation, see [PHASE4_1_OBSERVABILITY.md](../governance/PHASE4_1_OBSERVABILITY.md)
