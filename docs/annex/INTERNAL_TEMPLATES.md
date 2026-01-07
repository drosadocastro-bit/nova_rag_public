# NIC Public - Internal Templates & References

## Overview

This document consolidates internal templates, code review checklists, and validation procedures used during NIC development.

---

## Code Review Checklist

### Security Review
- [ ] No hardcoded credentials or API keys
- [ ] Input validation on all user inputs
- [ ] SQL injection prevention (parameterized queries)
- [ ] Path traversal prevention
- [ ] Rate limiting on public endpoints
- [ ] Secure error handling (no stack traces to users)

### Safety Review
- [ ] Policy guard covers new attack vectors
- [ ] Citation audit handles new response formats
- [ ] Confidence threshold appropriately set
- [ ] Extractive fallback working correctly
- [ ] Audit logging captures all decisions

### Performance Review
- [ ] Response time < 60s for typical queries
- [ ] Memory usage stable over extended runs
- [ ] No blocking operations on main thread
- [ ] Graceful degradation on resource pressure

---

## Test Case Template

```json
{
  "id": "TC001",
  "category": "adversarial|functional|stress",
  "name": "Descriptive test name",
  "query": "The test query",
  "expected_behavior": "What should happen",
  "expected_keywords": ["words", "in", "response"],
  "forbidden_keywords": ["words", "that", "should", "not", "appear"],
  "pass_criteria": "Specific criteria for pass/fail"
}
```

---

## Documentation Standards

### File Naming
- Use SCREAMING_SNAKE_CASE for doc files: `SYSTEM_ARCHITECTURE.md`
- Use descriptive names: `HALLUCINATION_DEFENSE.md` not `HALL_DEF.md`

### Section Structure
```markdown
# Title

## Overview
Brief description of the document's purpose.

---

## Main Content
Detailed information organized logically.

---

## Related Documents
- Links to related documentation
```

### Diagrams
- Use ASCII art for architecture diagrams
- Keep diagrams under 80 characters wide
- Use consistent box characters: `┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼`

---

## Validation Procedure

### Pre-Release Checklist
1. [ ] All adversarial tests pass
2. [ ] Stress tests complete without errors
3. [ ] RAGAS evaluation documented
4. [ ] Documentation updated
5. [ ] No TODO/FIXME in committed code
6. [ ] Dependencies locked in requirements.txt
7. [ ] .env.example updated with new variables

### Post-Deployment Verification
1. [ ] Server starts without errors
2. [ ] Health check endpoint responds
3. [ ] Sample query returns expected response
4. [ ] Logs are being written
5. [ ] No sensitive data in logs

---

## Common Patterns

### Error Handling
```python
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    return fallback_response()
except Exception as e:
    logger.exception("Unexpected error")
    return generic_error_response()
```

### Configuration Loading
```python
import os

CONFIG = {
    "threshold": float(os.getenv("CONFIDENCE_THRESHOLD", "0.60")),
    "strict_mode": os.getenv("STRICT_MODE", "1") == "1",
    "timeout": int(os.getenv("LLM_TIMEOUT", "300")),
}
```

---

## Glossary

| Term | Definition |
|------|------------|
| GAR | Glossary Augmented Retrieval |
| HOTL | Human-on-the-Loop |
| RAGAS | Retrieval Augmented Generation Assessment |
| NIC | Nova Intelligent Copilot |
| RAG | Retrieval Augmented Generation |

---

## Related Documents

- [ENGINEERING_LOG.md](ENGINEERING_LOG.md) - Engineering history
- [MAINTENANCE_LOG.md](MAINTENANCE_LOG.md) - Maintenance notes
- [BUILD_SUMMARY.md](BUILD_SUMMARY.md) - Build process notes
