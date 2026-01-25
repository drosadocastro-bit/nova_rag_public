# Runbook: Safety Alerts / Injection Detection

## Symptoms
- Safety check failures logged
- Injection attempts detected
- Cross-domain contamination alerts
- Suspicious query patterns
- Prometheus `nova_safety_checks_total{passed="false"}` increasing

---

## Quick Diagnosis

```bash
# Check recent safety events
grep -i "safety\|injection\|blocked" logs/nova.log | tail -50

# Check Prometheus metrics
curl -s http://localhost:5000/metrics | grep nova_safety

# Review blocked queries
grep '"passed": false' logs/nova.log | tail -20
```

---

## Issue: Prompt Injection Detected

### Symptoms
```
Safety check injection_detection failed
Injection pattern detected: ignore previous instructions
nova_safety_checks_total{check="injection",passed="false"}
```

### Diagnosis

**Review the query:**
```bash
# Find the blocked query
grep -B5 "injection_detection.*failed" logs/nova.log | tail -20

# Check injection patterns matched
grep -i "injection.*pattern" logs/nova.log | tail -10
```

### Response Protocol

**1. Assess severity:**
- **Low:** Common patterns (e.g., "ignore instructions") - likely automated/testing
- **Medium:** Targeted patterns with domain knowledge
- **High:** Sophisticated attempts with encoded payloads

**2. Determine if legitimate:**
```python
# Example: User asking about injection molding (automotive)
query = "What is the injection timing for the diesel engine?"
# This is LEGITIMATE - contains "injection" but automotive context
```

**3. Actions by severity:**

| Severity | Actions |
|----------|---------|
| Low | Log and monitor, no immediate action |
| Medium | Review source IP, check for patterns |
| High | Block IP temporarily, investigate further |

### False Positive Handling

If query is legitimate:
```python
# Add to allowlist in core/safety/injection_handler.py
ALLOWED_TERMS = [
    "fuel injection",
    "injection molding", 
    "injection timing",
]
```

---

## Issue: Cross-Domain Contamination

### Symptoms
```
Cross-domain contamination detected
Domain mismatch: query=vehicle, retrieved=aerospace
nova_safety_checks_total{check="domain_isolation",passed="false"}
```

### Diagnosis

```bash
# Check contamination rate
curl -s http://localhost:5000/metrics | grep contamination

# Review recent contamination events
grep -i "contamination\|domain.*mismatch" logs/nova.log | tail -20
```

### Response Protocol

**1. Verify the issue:**
```python
# Test query manually
from core.retrieval.retrieval_engine import retrieve

results = retrieve("How do I check brake pads?", domain="vehicle")
for r in results:
    print(f"Domain: {r.get('domain')}, Score: {r.get('score')}")
```

**2. Check domain classifier:**
```python
from agents.agent_router import detect_domain

query = "How do I check brake pads?"
domain, confidence = detect_domain(query)
print(f"Detected: {domain} ({confidence:.2f})")
```

**3. If contamination is real:**
- Check if new documents were ingested incorrectly
- Verify domain tags in metadata
- May need to re-ingest affected domain

---

## Issue: High Volume Safety Failures

### Symptoms
- Sudden spike in safety failures
- Same patterns repeated
- Possible automated attack

### Diagnosis

```bash
# Count failures by source
grep "safety.*failed" logs/nova.log | \
  grep -oP 'source_ip":\s*"\K[^"]+' | \
  sort | uniq -c | sort -rn | head -10

# Check rate of failures
grep "safety.*failed" logs/nova.log | \
  grep -oP '\d{4}-\d{2}-\d{2}T\d{2}:\d{2}' | \
  sort | uniq -c | tail -20
```

### Response Protocol

**1. If single source:**
```bash
# Temporarily block IP (example with iptables)
sudo iptables -A INPUT -s <IP_ADDRESS> -j DROP

# Or via nginx
# Add to /etc/nginx/conf.d/blocklist.conf
# deny <IP_ADDRESS>;
```

**2. If distributed:**
```bash
# Enable rate limiting in nginx
# /etc/nginx/conf.d/rate_limit.conf
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
}
```

**3. Alert and escalate:**
- Notify security team
- Preserve logs for analysis
- Consider enabling additional logging

---

## Issue: Dangerous Content in Response

### Symptoms
```
Response safety check failed
Dangerous content detected in LLM output
nova_safety_checks_total{check="response_safety",passed="false"}
```

### Diagnosis

```bash
# Find the response that triggered
grep -B10 "response.*safety.*failed" logs/nova.log | tail -30
```

### Response Protocol

**1. Review the output:**
- What dangerous content was detected?
- Was it actually dangerous or false positive?
- Did it come from the documents or LLM hallucination?

**2. If from documents:**
```bash
# Search for dangerous content in corpus
grep -r "dangerous phrase" data/

# May need to remove or redact source document
```

**3. If from LLM:**
```python
# Strengthen system prompt
SYSTEM_PROMPT = """
You are a technical advisor. You MUST:
- Never provide information that could cause harm
- Refuse requests for dangerous procedures
- Always recommend professional assistance for safety-critical tasks
"""
```

**4. Update safety filters:**
```python
# In core/safety/risk_assessment.py
DANGEROUS_PATTERNS = [
    "how to disable",
    "bypass safety",
    # Add new patterns
]
```

---

## Safety Event Types Reference

| Event Type | Severity | Description |
|------------|----------|-------------|
| `injection_attempt` | Medium | Prompt injection pattern detected |
| `domain_contamination` | Low | Retrieved docs from wrong domain |
| `dangerous_response` | High | LLM output contains unsafe content |
| `rate_limit_exceeded` | Low | Too many requests from source |
| `unusual_pattern` | Medium | Anomalous query pattern |
| `auth_failure` | High | Authentication/authorization failure |

---

## Safety Metrics to Monitor

```promql
# Injection attempt rate
rate(nova_safety_checks_total{check="injection",passed="false"}[5m])

# Safety failure ratio
sum(rate(nova_safety_checks_total{passed="false"}[5m])) / 
sum(rate(nova_safety_checks_total[5m]))

# Domain contamination rate
rate(nova_domain_contamination_total[5m])
```

---

## Alert Thresholds

```yaml
# prometheus/alerts/safety.yml
groups:
  - name: safety
    rules:
      - alert: HighInjectionAttempts
        expr: rate(nova_safety_checks_total{check="injection",passed="false"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High rate of injection attempts"
          
      - alert: DangerousContentDetected
        expr: increase(nova_safety_checks_total{check="response_safety",passed="false"}[1h]) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Dangerous content detected in response"
          
      - alert: DomainContamination
        expr: rate(nova_domain_contamination_total[5m]) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Cross-domain contamination detected"
```

---

## Safety Investigation Script

Save as `investigate_safety.py`:

```python
#!/usr/bin/env python3
"""Investigate safety events."""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

def parse_log_line(line):
    """Parse JSON log line."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def analyze_safety_events(log_path, hours=24):
    """Analyze safety events from logs."""
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    events = []
    
    with open(log_path) as f:
        for line in f:
            entry = parse_log_line(line)
            if not entry:
                continue
            
            # Check if safety-related
            if 'safety' in entry.get('message', '').lower() or \
               'injection' in entry.get('message', '').lower() or \
               entry.get('event_type', '').startswith('safety'):
                events.append(entry)
    
    print(f"=== Safety Event Analysis ({hours}h) ===\n")
    print(f"Total events: {len(events)}")
    
    # Count by type
    types = Counter(e.get('event_type', 'unknown') for e in events)
    print("\nBy type:")
    for t, count in types.most_common(10):
        print(f"  {t}: {count}")
    
    # Count by check
    checks = Counter(e.get('check_name', 'unknown') for e in events)
    print("\nBy check:")
    for c, count in checks.most_common(10):
        print(f"  {c}: {count}")
    
    # Failed checks
    failed = [e for e in events if e.get('passed') == False]
    print(f"\nFailed checks: {len(failed)}")
    
    if failed:
        print("\nRecent failures:")
        for e in failed[-5:]:
            print(f"  - {e.get('timestamp')}: {e.get('check_name')} - {e.get('message')}")
    
    return events

if __name__ == "__main__":
    log_path = sys.argv[1] if len(sys.argv) > 1 else "logs/nova.log"
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    
    analyze_safety_events(log_path, hours)
```

---

## Escalation

For critical safety events:

1. **Immediate actions:**
   - Preserve logs: `cp logs/nova.log logs/nova.log.incident.$(date +%s)`
   - Screenshot Prometheus dashboards
   - Note timeline of events

2. **Collect evidence:**
   ```bash
   python investigate_safety.py logs/nova.log > safety_report.txt
   grep -C10 "safety.*failed" logs/nova.log >> safety_report.txt
   ```

3. **Escalation contacts:**
   - Security team: security@example.com
   - On-call engineer: See PagerDuty
   - Management: For high-severity incidents

4. **Post-incident:**
   - Update safety filters if needed
   - Document lessons learned
   - Update this runbook

---

## Related Runbooks

- [Server Startup Issues](server-startup-issues.md)
- [High Latency](high-latency.md) (safety checks add latency)
- [Backup & Recovery](../operations/BACKUP_RECOVERY.md)
