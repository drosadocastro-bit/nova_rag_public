# Runbooks

Operational runbooks for troubleshooting and incident response.

## Available Runbooks

| Runbook | Description |
|---------|-------------|
| [Server Startup Issues](server-startup-issues.md) | Server won't start, port conflicts, missing dependencies |
| [High Latency](high-latency.md) | Slow responses, performance troubleshooting |
| [Ollama Connection](ollama-connection.md) | LLM connectivity issues, timeouts, model problems |
| [Index Corruption](index-corruption.md) | FAISS/BM25 recovery, metadata issues |
| [Memory Issues](memory-issues.md) | OOM errors, memory leaks, high memory usage |
| [Safety Alerts](safety-alerts.md) | Injection detection, safety check failures |

## Quick Reference

### Common Commands

```bash
# Check service status
sudo systemctl status nova-nic

# View recent logs
tail -100 logs/nova.log

# Health check
curl http://localhost:5000/health | jq '.'

# Check metrics
curl http://localhost:5000/metrics | grep nova_

# Restart service
sudo systemctl restart nova-nic
```

### Severity Levels

| Level | Response Time | Examples |
|-------|---------------|----------|
| Critical | 15 min | Service down, safety bypass |
| High | 1 hour | LLM unavailable, high error rate |
| Medium | 4 hours | Slow responses, partial functionality |
| Low | 24 hours | Warnings, non-critical issues |

### Escalation Path

1. **On-call Engineer** - First response
2. **Team Lead** - If unresolved in 30 min (Critical) or 2 hours (High)
3. **Management** - If customer-impacting > 1 hour

## Related Documentation

- [Monitoring Guide](../operations/MONITORING.md)
- [Logging Guide](../operations/LOGGING.md)
- [Backup & Recovery](../operations/BACKUP_RECOVERY.md)
- [SLA](../operations/SLA.md)
