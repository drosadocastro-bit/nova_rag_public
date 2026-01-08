# Contributing to NIC

Thank you for your interest in contributing to NIC! This document provides guidelines for contributing to the project.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Review Process](#review-process)

---

## Code of Conduct

This project follows a professional code of conduct. Please be respectful, constructive, and collaborative.

---

## Getting Started

### Prerequisites

- Python 3.12 or 3.13
- Git
- Ollama (for local LLM testing)
- Docker (optional, for containerized development)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your username/nova_rag_public.git
   cd nova_rag_public
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install
   # or manually:
   pip install -r requirements.txt
   ```

4. **Set up development tools**
   ```bash
   pip install ruff bandit pip-audit pytest pytest-cov
   ```

5. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

6. **Verify setup**
   ```bash
   make validate
   ```

---

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-xyz` - New features
- `fix/bug-description` - Bug fixes
- `docs/update-readme` - Documentation
- `refactor/component-name` - Code refactoring
- `test/add-coverage` - Test additions

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(retrieval): add BM25 hybrid search support

Implements hybrid retrieval combining FAISS vector search with 
BM25 lexical search for improved recall on specific terms.

Closes #123
```

```
fix(cache): prevent race condition in retrieval cache

Uses thread lock to prevent concurrent writes to cache dictionary.

Fixes #456
```

---

## Testing

### Running Tests

```bash
# Unit tests only (fast)
make test

# All tests (unit + integration)
make test-all

# With coverage
make coverage
```

### Writing Tests

1. **Location**: Place tests in `tests/unit/` or `tests/integration/`

2. **Naming**: `test_<module>_<function>.py`

3. **Structure**: Follow AAA pattern (Arrange-Act-Assert)

4. **Example**:
   ```python
   def test_cache_key_generation():
       """Test that cache keys are unique per input."""
       # Arrange
       query = "test query"
       k, top_n = 12, 6
       
       # Act
       key = _cache_key(query, k, top_n)
       
       # Assert
       assert isinstance(key, str)
       assert len(key) == 32  # MD5 hex length
   ```

5. **Coverage Target**: Aim for 70%+ on new code

### Test Guidelines

- ✅ Test one thing per test
- ✅ Use descriptive test names
- ✅ Mock external dependencies (Ollama, file I/O)
- ✅ Clean up resources in teardown
- ❌ Don't test implementation details
- ❌ Don't rely on test execution order

---

## Code Style

### Python Style

We follow **PEP 8** with some modifications.

**Formatter**: Ruff
```bash
make format
```

**Linter**: Ruff
```bash
make lint
```

### Key Guidelines

1. **Imports**
   ```python
   # Standard library
   import os
   import sys
   
   # Third-party
   import flask
   import pytest
   
   # Local
   from backend import retrieve
   from cache_utils import cache_retrieval
   ```

2. **Type Hints**
   ```python
   def retrieve(query: str, k: int = 12, top_n: int = 6) -> list[dict]:
       """Retrieve relevant documents."""
       pass
   ```

3. **Docstrings**
   ```python
   def function_name(param1: str, param2: int) -> bool:
       """Brief description.
       
       Args:
           param1: Description of param1
           param2: Description of param2
           
       Returns:
           Description of return value
           
       Raises:
           ValueError: When param1 is empty
       """
       pass
   ```

4. **Line Length**: 100 characters (not strict)

5. **Comments**
   - Use comments sparingly
   - Explain *why*, not *what*
   - Keep comments up-to-date

---

## Security

### Security Guidelines

1. **No Secrets in Code**
   - Use environment variables
   - Never commit API keys or tokens

2. **Input Validation**
   - Validate all user input
   - Sanitize before processing

3. **Dependencies**
   - Keep dependencies up-to-date
   - Run security scans before committing

4. **Security Scans**
   ```bash
   make security
   ```

### Reporting Security Issues

**DO NOT** open public issues for security vulnerabilities.

Email security concerns to: [security contact]

---

## Submitting Changes

### Before Submitting

1. **Run tests**
   ```bash
   make test
   ```

2. **Check code style**
   ```bash
   make lint
   make format
   ```

3. **Run security scans**
   ```bash
   make security
   ```

4. **Update documentation** if needed

5. **Add tests** for new features

### Pull Request Process

1. **Create PR** with descriptive title and description

2. **Link issues** using "Closes #123" or "Fixes #456"

3. **Fill out PR template** completely

4. **Request review** from maintainers

5. **Address feedback** promptly

6. **Keep PR updated** with main branch

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Tests pass locally
```

---

## Review Process

### What We Look For

1. **Correctness**: Code does what it claims
2. **Safety**: No security vulnerabilities
3. **Tests**: Adequate test coverage
4. **Style**: Follows project conventions
5. **Documentation**: Clear and complete
6. **Performance**: No unnecessary inefficiency

### Review Timeline

- Initial review: Within 2-3 business days
- Follow-up reviews: Within 1-2 business days
- Merge: After approval from 1+ maintainers

---

## Development Workflow

### Typical Workflow

```bash
# 1. Create branch
git checkout -b feature/my-feature

# 2. Make changes
# ... edit files ...

# 3. Run tests
make test

# 4. Format code
make format

# 5. Commit changes
git add .
git commit -m "feat: add my feature"

# 6. Push branch
git push origin feature/my-feature

# 7. Create PR on GitHub
```

### Continuous Integration

All PRs run through CI:
- Linting (ruff)
- Unit tests
- Security scans (bandit, pip-audit)
- Documentation checks

CI must pass before merge.

---

## Project Structure

```
.
├── backend.py              # Core RAG logic
├── nova_flask_app.py       # Flask API server
├── cache_utils.py          # Caching utilities
├── agents/                 # Agent implementations
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── fixtures/          # Test data
├── docs/                   # Documentation
│   ├── architecture/      # System design
│   ├── safety/            # Safety validation
│   ├── evaluation/        # Test results
│   └── deployment/        # Deployment guides
└── governance/             # Policies and test suites
```

---

## Getting Help

- **Documentation**: Check [docs/INDEX.md](docs/INDEX.md)
- **FAQ**: See [docs/FAQ.md](docs/FAQ.md)
- **Issues**: Search existing issues first
- **Discussions**: Use GitHub Discussions for questions

---

## Recognition

Contributors will be acknowledged in:
- Release notes
- Contributors section (if added)
- Commit history

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to NIC! Your efforts help make safety-critical AI more accessible and reliable.
