# Service Level Agreement (SLA)

## Nova NIC - Technical Advisory System

**Version:** 1.0  
**Effective Date:** January 2026  
**Last Updated:** January 25, 2026

---

## 1. Service Description

Nova NIC (Neural Information Companion) is a retrieval-augmented generation (RAG) system that provides technical advisory responses for multi-domain documentation including:

- Vehicle maintenance and repair
- Aerospace systems
- Nuclear operations
- Medical devices
- Electronics
- Industrial systems

---

## 2. Service Availability

### 2.1 Availability Target

| Metric | Target | Measurement |
|--------|--------|-------------|
| Monthly Uptime | 99.5% | (Total minutes - Downtime) / Total minutes |
| Maximum Planned Downtime | 4 hours/month | During maintenance windows |
| Maximum Unplanned Downtime | 2 hours/month | Outside maintenance windows |

**99.5% uptime = Maximum 3.6 hours downtime per month**

### 2.2 Maintenance Windows

| Window | Time (UTC) | Frequency |
|--------|------------|-----------|
| Standard | Sunday 02:00-06:00 | Weekly |
| Emergency | Any time | As needed with notification |

**Notification Requirements:**
- Planned maintenance: 48 hours notice
- Emergency maintenance: Best effort notification

### 2.3 Availability Exclusions

The following do not count against availability:
- Scheduled maintenance during announced windows
- Force majeure events (natural disasters, etc.)
- Third-party service outages (Ollama, cloud infrastructure)
- Customer-caused issues

---

## 3. Performance Targets

### 3.1 Response Time

| Metric | Target | Percentile |
|--------|--------|------------|
| Query Response Time | < 3 seconds | P95 |
| Query Response Time | < 5 seconds | P99 |
| Health Check Response | < 100ms | P99 |
| Retrieval Latency | < 500ms | P95 |

### 3.2 Throughput

| Metric | Target |
|--------|--------|
| Queries per Second | 10 QPS sustained |
| Concurrent Users | 50 |
| Burst Capacity | 50 QPS (10 seconds) |

### 3.3 Accuracy Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| Retrieval Relevance | > 85% | MRR@5 on test queries |
| Domain Classification | > 95% | Correct domain detection |
| Cross-Domain Contamination | < 1% | Wrong-domain documents in results |
| Citation Accuracy | > 90% | Verifiable source citations |

---

## 4. Safety Guarantees

### 4.1 Safety Targets

| Metric | Target |
|--------|--------|
| Injection Attack Block Rate | > 99% |
| Dangerous Content Filter | > 99.9% |
| Safety Check Latency Overhead | < 100ms |

### 4.2 Safety Response Time

| Severity | Response Time | Resolution Time |
|----------|---------------|-----------------|
| Critical (dangerous output) | 15 minutes | 2 hours |
| High (injection detected) | 1 hour | 4 hours |
| Medium (domain contamination) | 4 hours | 24 hours |
| Low (informational) | 24 hours | 72 hours |

---

## 5. Support

### 5.1 Support Channels

| Channel | Availability | Response Target |
|---------|--------------|-----------------|
| GitHub Issues | 24/7 | 24 hours |
| Email | Business hours | 48 hours |
| Emergency Hotline | 24/7 | 15 minutes |

### 5.2 Support Tiers

| Tier | Description | Availability |
|------|-------------|--------------|
| Tier 1 | Basic troubleshooting | Business hours |
| Tier 2 | Technical investigation | Business hours |
| Tier 3 | Engineering escalation | 24/7 for critical |

### 5.3 Incident Severity Definitions

| Severity | Definition | Examples |
|----------|------------|----------|
| Critical | Service completely unavailable | Server down, all queries failing |
| High | Major feature impaired | LLM not responding, safety bypass |
| Medium | Partial functionality affected | Slow responses, single domain issues |
| Low | Minor issues | UI glitches, log errors |

---

## 6. Incident Management

### 6.1 Incident Response

| Severity | Acknowledge | Update Frequency | Resolution Target |
|----------|-------------|------------------|-------------------|
| Critical | 15 minutes | Every 30 minutes | 2 hours |
| High | 1 hour | Every 2 hours | 8 hours |
| Medium | 4 hours | Daily | 48 hours |
| Low | 24 hours | Weekly | 7 days |

### 6.2 Post-Incident

- **Root Cause Analysis:** Within 5 business days for Critical/High
- **Post-Mortem Report:** Published within 10 business days
- **Preventive Measures:** Implemented within 30 days

---

## 7. Data & Backup

### 7.1 Data Protection

| Metric | Target |
|--------|--------|
| Backup Frequency | Daily |
| Backup Retention | 30 days local, 12 months remote |
| Recovery Point Objective (RPO) | 24 hours |
| Recovery Time Objective (RTO) | 4 hours |

### 7.2 Data Integrity

| Metric | Target |
|--------|--------|
| Index Verification | Daily |
| Checksum Validation | On every backup |
| Recovery Testing | Monthly |

---

## 8. Monitoring & Reporting

### 8.1 Available Metrics

| Endpoint | Metrics |
|----------|---------|
| `/health` | Overall system health |
| `/health/ready` | Readiness for traffic |
| `/health/live` | Liveness status |
| `/metrics` | Prometheus metrics |

### 8.2 Reporting

| Report | Frequency | Contents |
|--------|-----------|----------|
| Availability Report | Monthly | Uptime, downtime events |
| Performance Report | Monthly | Latency percentiles, throughput |
| Safety Report | Monthly | Blocked queries, safety events |
| Incident Summary | Quarterly | All incidents with RCA |

---

## 9. Service Credits

### 9.1 Credit Schedule

If monthly uptime falls below target:

| Uptime | Credit |
|--------|--------|
| 99.0% - 99.5% | 10% |
| 95.0% - 99.0% | 25% |
| 90.0% - 95.0% | 50% |
| < 90.0% | 100% |

### 9.2 Credit Conditions

- Credits apply to monthly service fees
- Maximum credit: 100% of monthly fee
- Must request within 30 days
- Does not apply to beta features

---

## 10. Compliance

### 10.1 Operational Compliance

| Standard | Status |
|----------|--------|
| SOC 2 Type II | Roadmap |
| ISO 27001 | Roadmap |
| GDPR | Compliant |

### 10.2 Audit Rights

- Annual third-party security audit
- Penetration testing: Bi-annual
- Audit reports available upon request (NDA required)

---

## 11. Limitations

### 11.1 Fair Use

- Maximum query length: 2,000 characters
- Maximum response length: 4,000 tokens
- Rate limit: 100 queries/minute per user

### 11.2 Not Covered

This SLA does not apply to:
- Beta or experimental features
- Free tier usage
- Self-hosted deployments
- Custom integrations not supported by vendor

---

## 12. Review & Changes

- **SLA Review:** Quarterly
- **Change Notice:** 30 days for material changes
- **Version History:** Maintained in this document

---

## 13. Contact

| Purpose | Contact |
|---------|---------|
| Support | support@example.com |
| Billing | billing@example.com |
| Security | security@example.com |
| SLA Questions | sla@example.com |

---

## Appendix A: Metric Definitions

### Availability Calculation

```
Monthly Availability % = ((Total Minutes - Downtime Minutes) / Total Minutes) × 100

Where:
- Total Minutes = Days in month × 24 × 60
- Downtime Minutes = Sum of all outage durations
```

### Response Time Calculation

```
Response Time = Time of last byte received - Time of request sent

P95 = 95th percentile of all response times in measurement period
P99 = 99th percentile of all response times in measurement period
```

### Throughput Calculation

```
QPS = Total successful queries / Measurement period in seconds

Sustained = 1-hour measurement period
Burst = 10-second measurement period
```

---

## Appendix B: Prometheus Queries for SLA Metrics

```promql
# Availability (based on health checks)
avg_over_time(up{job="nova-nic"}[30d]) * 100

# P95 Response Time
histogram_quantile(0.95, rate(nova_query_latency_seconds_bucket[24h]))

# P99 Response Time
histogram_quantile(0.99, rate(nova_query_latency_seconds_bucket[24h]))

# Query Throughput
rate(nova_queries_total[1h])

# Safety Block Rate
sum(rate(nova_safety_checks_total{passed="false"}[24h])) / 
sum(rate(nova_safety_checks_total[24h])) * 100

# Error Rate
sum(rate(nova_queries_total{status="error"}[24h])) /
sum(rate(nova_queries_total[24h])) * 100
```

---

## Appendix C: Escalation Matrix

| Severity | Tier 1 | Tier 2 | Tier 3 | Management |
|----------|--------|--------|--------|------------|
| Critical | 0 min | 15 min | 30 min | 1 hour |
| High | 0 min | 1 hour | 4 hours | 8 hours |
| Medium | 0 min | 4 hours | 24 hours | 48 hours |
| Low | 0 min | 24 hours | 72 hours | Weekly |

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-25 | Initial SLA document |
