## Description

<!-- Provide a brief description of your changes -->

Fixes #(issue)

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📝 Documentation update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] 🧪 Tests (adding or updating tests)
- [ ] 🔒 Security fix

## Safety Impact

Does this PR affect safety-critical functionality?

- [ ] Modifies retrieval logic (`core/retrieval/`)
- [ ] Affects hallucination defenses (`core/safety/hallucination_guard.py`)
- [ ] Changes confidence scoring or gating
- [ ] Modifies audit trail/evidence chain
- [ ] Affects domain routing or isolation
- [ ] Changes injection handling (`core/safety/injection_handler.py`)
- [ ] **No safety impact**

## Testing

### Automated Tests
- [ ] Unit tests pass (`pytest tests/unit/ -v`)
- [ ] Integration tests pass (`pytest tests/integration/ -v`)
- [ ] Safety tests pass (`pytest tests/safety/ -v`)
- [ ] Cross-contamination tests pass (`pytest test_cross_contamination.py -v`)

### Manual Testing
- [ ] Manual testing completed
- [ ] Tested in air-gapped/offline mode (if applicable)
- [ ] Load/stress testing performed (if applicable)

### Test Coverage
<!-- Example: Coverage changed from 85% to 87% -->
**Coverage change:** ___ → ___

## Code Quality Checklist

- [ ] Code follows project style guidelines
- [ ] Ran `ruff check` and `ruff format`
- [ ] Self-review of code completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] No new warnings introduced
- [ ] Backward compatible (or breaking change documented)
- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)

## Performance Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Query latency (p95) | | | |
| Retrieval time (avg) | | | |
| Memory usage | | | |
| Index build time | | | |

<!-- Leave blank if no measurable performance impact -->

## Screenshots / Evidence Chain

<!-- If applicable, add screenshots or evidence chain output -->

## Deployment Notes

### Migration Requirements
<!-- Any database migrations, index rebuilds, etc. -->

### New Environment Variables
<!-- List any new environment variables -->

| Variable | Description | Default |
|----------|-------------|---------|
| | | |

## Reviewer Checklist

<!-- For reviewers -->
- [ ] Code logic is correct and follows best practices
- [ ] Safety-critical changes have been thoroughly reviewed
- [ ] Tests adequately cover the changes
- [ ] Documentation is accurate and complete
- [ ] No security vulnerabilities introduced