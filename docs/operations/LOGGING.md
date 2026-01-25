# Nova NIC Structured Logging Guide

This document describes the structured logging system for production monitoring and troubleshooting.

## Quick Start

### Configuration

Set environment variables to configure logging:

```bash
# Log format: "json" (production) or "text" (development)
export NOVA_LOG_FORMAT=json

# Log level: DEBUG, INFO, WARNING, ERROR
export NOVA_LOG_LEVEL=INFO

# Log file path
export NOVA_LOG_FILE=logs/nova.log

# Log rotation settings
export NOVA_LOG_MAX_SIZE=100    # Max size in MB
export NOVA_LOG_BACKUP_COUNT=10 # Number of backup files to keep
```

### Default Behavior

- **Format**: JSON (machine-readable)
- **Level**: INFO
- **File**: `logs/nova.log`
- **Rotation**: 100MB max, 10 backup files
- **Output**: Both console and file

---

## Log Formats

### JSON Format (Production)

```json
{
  "timestamp": "2026-01-25T10:30:15.123456Z",
  "level": "INFO",
  "query_id": "a3f8b2c1-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "module": "nova_flask_app",
  "message": "Query completed",
  "domain": "vehicle_civilian",
  "query": "How do I check tire pressure?",
  "confidence_score": 0.82,
  "latency_ms": 345,
  "safety_checks": ["input_validation", "injection_detection"]
}
```

**Benefits:**
- Machine-parseable for log aggregators (ELK, Splunk, Loki)
- Structured fields for filtering and analysis
- Consistent field names across all log entries

### Text Format (Development)

```
2026-01-25 10:30:15 INFO  [nova_flask_app] Query completed | query_id=a3f8b2c1 domain=vehicle latency_ms=345
```

**Benefits:**
- Human-readable
- Color-coded by level
- Compact single-line format

---

## Standard Log Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | UTC timestamp with microseconds |
| `level` | string | DEBUG, INFO, WARNING, ERROR |
| `module` | string | Source module name |
| `message` | string | Log message |

### Query Fields

| Field | Type | Description |
|-------|------|-------------|
| `query_id` | UUID | Unique identifier for tracing |
| `query` | string | User's query text (truncated) |
| `domain` | string | Detected domain |
| `confidence_score` | float | Retrieval confidence (0-1) |
| `latency_ms` | float | Processing time in milliseconds |
| `safety_checks` | array | Safety checks performed |

### Safety Fields

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Type of safety event |
| `check_name` | string | Specific check name |
| `passed` | bool | Whether check passed |
| `details` | object | Additional check details |

---

## Usage in Code

### Basic Logging

```python
from core.monitoring.logger_config import get_logger

logger = get_logger(__name__)

# Simple log
logger.info("Processing started")

# With extra fields
logger.info("Query received", extra={
    "query": "How do I check tire pressure?",
    "mode": "Auto",
})

# Warning with details
logger.warning("Low confidence result", extra={
    "confidence_score": 0.35,
    "domain": "vehicle",
})

# Error with exception
try:
    process_query()
except Exception as e:
    logger.error("Query processing failed", extra={"error": str(e)})
```

### Query Context

Track query_id across the entire request lifecycle:

```python
from core.monitoring.logger_config import get_logger, QueryContext

logger = get_logger(__name__)

# All logs within context include query_id
with QueryContext(query="How do I check tire pressure?", domain="vehicle") as ctx:
    logger.info("Starting retrieval")  # Includes query_id
    
    # Access query_id if needed
    print(f"Processing query {ctx.query_id}")
    
    logger.info("Retrieval complete", extra={"latency_ms": 150})
```

### Specialized Log Functions

```python
from core.monitoring.logger_config import (
    get_logger,
    log_query,
    log_safety_event,
    log_retrieval_event,
)

logger = get_logger(__name__)

# Log query with standard fields
log_query(
    logger,
    "Query completed",
    query="How do I check tire pressure?",
    domain="vehicle",
    confidence_score=0.82,
    latency_ms=345,
    safety_checks=["injection_detection", "risk_assessment"],
)

# Log safety check
log_safety_event(
    logger,
    "injection_check",
    check_name="prompt_injection",
    passed=True,
    details={"patterns_checked": 15},
)

# Log retrieval event
log_retrieval_event(
    logger,
    "faiss_search",
    chunks_retrieved=12,
    confidence=0.85,
    latency_ms=45,
)
```

---

## Log Rotation

Logs are automatically rotated to prevent disk exhaustion:

| Setting | Default | Description |
|---------|---------|-------------|
| Max file size | 100 MB | Rotate when file exceeds this size |
| Backup count | 10 | Number of old files to keep |
| Compression | None | Files are not compressed |

**Rotated file names:**
```
logs/nova.log      # Current log
logs/nova.log.1    # Previous rotation
logs/nova.log.2    # Older rotation
...
logs/nova.log.10   # Oldest (deleted when new rotation occurs)
```

---

## Log Aggregation

### Elasticsearch / Logstash

```conf
# logstash.conf
input {
  file {
    path => "/app/logs/nova.log"
    codec => json
    type => "nova"
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "nova-logs-%{+YYYY.MM.dd}"
  }
}
```

### Promtail / Loki

```yaml
# promtail.yaml
scrape_configs:
  - job_name: nova
    static_configs:
      - targets:
          - localhost
        labels:
          job: nova
          __path__: /app/logs/nova.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            module: module
            query_id: query_id
      - labels:
          level:
          module:
```

### Fluentd

```conf
<source>
  @type tail
  path /app/logs/nova.log
  pos_file /var/log/fluentd/nova.log.pos
  tag nova.app
  <parse>
    @type json
  </parse>
</source>
```

---

## Troubleshooting

### Common Issues

#### Logs not appearing

1. Check log level: `NOVA_LOG_LEVEL=DEBUG`
2. Verify log directory exists and is writable
3. Check for import errors in logger_config.py

#### JSON parse errors

1. Ensure `NOVA_LOG_FORMAT=json` is set
2. Check for print() statements bypassing logger
3. Verify log file is not corrupted

#### High disk usage

1. Reduce `NOVA_LOG_MAX_SIZE`
2. Reduce `NOVA_LOG_BACKUP_COUNT`
3. Increase log level to reduce volume

#### Missing query_id

1. Ensure QueryContext is used in request handlers
2. Check that extra fields include query_id
3. Verify context propagation in async code

---

## Log Analysis Examples

### Find slow queries

```bash
# JSON logs with jq
cat logs/nova.log | jq 'select(.latency_ms > 2000)'
```

### Count by domain

```bash
cat logs/nova.log | jq -r '.domain // "unknown"' | sort | uniq -c
```

### Find safety failures

```bash
cat logs/nova.log | jq 'select(.event_type == "safety_check" and .passed == false)'
```

### Trace specific query

```bash
cat logs/nova.log | jq 'select(.query_id == "a3f8b2c1-...")'
```

---

## Security Considerations

### Sensitive Data

- **Query text**: Truncated to 200 characters in logs
- **User IPs**: Logged only in analytics, not in structured logs
- **Answers**: Not logged (only metadata)
- **Credentials**: Never logged (redacted in config summary)

### Log Access

- Logs should be stored securely
- Restrict file permissions: `chmod 640 logs/nova.log`
- Consider encryption for sensitive environments

---

## Related Documentation

- [Monitoring Guide](MONITORING.md)
- [Health Endpoints](../api/HEALTH_ENDPOINTS.md)
- [Deployment Guide](../deployment/README.md)
