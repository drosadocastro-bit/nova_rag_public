# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| 0.2.x   | :x:                |
| 0.1.x   | :x:                |

## Reporting a Vulnerability

**Do NOT report security vulnerabilities through public GitHub issues.**

### Preferred: GitHub Security Advisories
https://github.com/drosadocastro-bit/nova_rag_public/security/advisories/new

### Alternative: Email
**drosadocastro@gmail.com**

Subject: `[SECURITY] NIC Vulnerability Report`

## What to Include

- **Description**: Clear description of the vulnerability
- **Impact**: What can an attacker do?
- **Steps to Reproduce**: Detailed reproduction steps
- **Affected Components**: Which modules/files?
- **Suggested Fix**: Optional

## Response Timeline

| Action | Timeline |
|--------|----------|
| Initial Response | Within 48 hours |
| Severity Assessment | Within 5 business days |
| Fix Development | Varies by severity |
| Public Disclosure | After fix + 7 days |

## Severity Levels & Response Times

| Severity | Description | Fix Timeline |
|----------|-------------|--------------|
| **Critical** | System compromise, data breach, safety failure | 1-3 days |
| **High** | Security bypass, significant vulnerability | 5-7 days |
| **Medium** | Limited impact, workaround available | 10-14 days |
| **Low** | Minor issue, minimal impact | 21-30 days |

## Security-Critical Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Injection Handler | `core/safety/injection_handler.py` | Prompt injection detection/blocking |
| Risk Assessment | `core/safety/risk_assessment.py` | Safety scoring and gating |
| Retrieval Engine | `core/retrieval/retrieval_engine.py` | Domain isolation, result filtering |
| Session Manager | `core/session/session_manager.py` | Audit trails, session isolation |
| LLM Gateway | `core/generation/llm_gateway.py` | Model interaction, output sanitization |
| Hallucination Guard | `core/safety/hallucination_guard.py` | Citation verification |

## Offline/Air-Gapped Security Considerations

NIC is designed for offline/air-gapped deployments:

- **No external API calls**: All models run locally via Ollama
- **No telemetry**: Zero data leaves the deployment environment
- **Self-contained**: All dependencies bundled for offline installation
- **Network isolation**: Can operate without any network connectivity

### Air-Gap Deployment Security

1. Verify checksums of all downloaded models before transfer
2. Use signed packages when available
3. Audit `requirements.txt` dependencies before offline installation
4. Review `ollama/` model files for integrity

## Prompt Injection Defenses

NIC implements multi-layer prompt injection protection:

### Current Defenses
- **Pattern Detection**: Regex-based detection of known injection patterns
- **Confidence Gating**: Low-confidence responses trigger safety warnings
- **Citation Verification**: Responses must cite indexed sources
- **Domain Isolation**: Cross-domain contamination prevention
- **Input Sanitization**: Special character filtering

### Known Limitations
- Novel injection techniques may bypass pattern detection
- Sophisticated adversarial prompts require manual review
- LLM-level vulnerabilities depend on underlying model

### Adversarial Testing
- 111/111 adversarial test cases passing
- Regular red-team testing recommended
- Run `pytest tests/safety/ -v` to verify defenses

## Security Best Practices for Deployers

### Pre-Deployment
- [ ] Review and customize safety thresholds in `core/safety/`
- [ ] Audit indexed documents for sensitive content
- [ ] Test with domain-specific adversarial inputs
- [ ] Configure appropriate confidence thresholds

### Deployment
- [ ] Run behind reverse proxy with rate limiting
- [ ] Enable audit logging (`NOVA_AUDIT_LOG=true`)
- [ ] Restrict file system access to data directories only
- [ ] Use dedicated service account with minimal privileges

### Post-Deployment
- [ ] Monitor audit logs for anomalies
- [ ] Regular security updates for dependencies
- [ ] Periodic re-run of safety test suite
- [ ] Subscribe to security advisories

## Coordinated Disclosure Policy

We follow responsible disclosure practices:

1. **Reporter submits** vulnerability via private channel
2. **We acknowledge** within 48 hours
3. **We assess severity** within 5 business days
4. **We develop fix** based on severity timeline
5. **We notify reporter** when fix is ready
6. **We release fix** with security advisory
7. **Public disclosure** after 7-day grace period
8. **Reporter credited** in advisory (unless anonymity requested)

We will not pursue legal action against security researchers acting in good faith.

## Contact

drosadocastro@gmail.com