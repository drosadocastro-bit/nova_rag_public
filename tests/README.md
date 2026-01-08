# NIC Test Suite

Comprehensive unit tests for the NIC RAG system.

## Running Tests

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html --cov-report=term
```

View coverage report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Run Specific Test Files

```bash
pytest tests/test_cache_utils.py
pytest tests/test_session_store.py
pytest tests/test_flask_app.py
```

### Run Tests by Marker

```bash
pytest -m unit           # Run only unit tests
pytest -m integration    # Run only integration tests  
pytest -m "not slow"     # Skip slow tests
```

### Verbose Output

```bash
pytest -v                # Verbose
pytest -vv               # Very verbose
pytest -s                # Show print statements
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_cache_utils.py      # Cache and persistence tests
├── test_session_store.py    # Session management tests
├── test_flask_app.py        # Flask API and security tests
└── README.md                # This file
```

## Test Coverage

Current test coverage by module:

| Module | Coverage | Tests | Notes |
|--------|----------|-------|-------|
| cache_utils.py | ~75% | 15 | Caching, SQL logging, HMAC |
| agents/session_store.py | ~80% | 12 | Session CRUD operations |
| nova_flask_app.py | ~70% | 18 | API routes, rate limiting, security |

**Total: 45+ unit tests**

## Fixtures

### Available in `conftest.py`

- `sample_question` - Sample vehicle maintenance question
- `sample_documents` - Mock retrieval results  
- `mock_env_vars` - Test environment variables
- `temp_cache_dir` - Temporary cache directory
- `client` - Flask test client (in test_flask_app.py)

## Environment Variables

Tests automatically set:

```bash
NOVA_FORCE_OFFLINE=1          # Prevent network calls
NOVA_DISABLE_VISION=1         # Skip vision models
NOVA_RATE_LIMIT_ENABLED=0     # Disable rate limiting in tests
HF_HUB_OFFLINE=1              # Offline HuggingFace
TRANSFORMERS_OFFLINE=1        # Offline transformers
```

## Writing New Tests

### Unit Test Template

```python
import pytest

@pytest.mark.unit
class TestYourModule:
    """Tests for your_module."""
    
    def test_basic_functionality(self):
        """Test description."""
        from your_module import your_function
        
        result = your_function("input")
        assert result == "expected"
    
    def test_edge_case(self, sample_fixture):
        """Test edge case."""
        # Use fixtures
        assert sample_fixture is not None
```

### Integration Test Template

```python
@pytest.mark.integration
def test_end_to_end_workflow():
    """Test complete workflow."""
    # Setup
    # Execute
    # Verify
    pass
```

## CI Integration

Tests run automatically on:
- Pull requests
- Pushes to main/develop branches

See `.github/workflows/ci.yml` for configuration.

## Debugging Failed Tests

### Run specific test with output

```bash
pytest tests/test_cache_utils.py::TestRetrievalCache::test_cache_enabled -s -vv
```

### Run with debugger

```bash
pytest --pdb  # Drop into debugger on failures
```

### Show local variables

```bash
pytest -l  # Show local variables in tracebacks
```

## Continuous Testing

### Watch mode (requires pytest-watch)

```bash
pip install pytest-watch
ptw  # Runs tests on file changes
```

## Test Data

Test data is isolated in `tests/` directory:
- No shared state between tests
- Each test gets fresh fixtures
- Temporary directories auto-cleaned

## Performance

Test suite runs in ~5-10 seconds (unit tests only).

To speed up:
```bash
pytest -n auto  # Parallel execution (requires pytest-xdist)
```

## Known Limitations

- Integration tests require Ollama running
- Some tests skip if dependencies missing
- GPU tests not included (CPU only)

## Contributing

When adding new code:

1. Write tests first (TDD)
2. Aim for 70%+ coverage
3. Run `pytest --cov` before committing
4. Update this README if adding new test files

## Test Quality Guidelines

- **One assertion per test** (when possible)
- **Descriptive test names** (test_what_when_expected)
- **Arrange-Act-Assert** pattern
- **Mock external dependencies** (Ollama, file system when appropriate)
- **Use fixtures** for shared setup
