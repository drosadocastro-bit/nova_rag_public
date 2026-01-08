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
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_cache_utils.py      # Cache and persistence tests
│   ├── test_session_store.py    # Session management tests
│   └── test_flask_app.py        # Flask API and security tests
├── integration/             # Integration tests (may require services)
│   ├── test_end_to_end.py       # Complete RAG pipeline tests
│   └── test_pipeline.py         # Additional workflow tests
├── load/                    # Load and performance tests
│   └── run_load_test.py         # Concurrent user load testing
├── fixtures/                # Test data and fixtures
│   └── eval_questions.json      # Sample questions for testing
└── README.md                # This file
```

## Test Coverage

Current test coverage by module:

| Module | Coverage | Tests | Notes |
|--------|----------|-------|-------|
| cache_utils.py | ~75% | 15 | Caching, SQL logging, HMAC |
| agents/session_store.py | ~80% | 12 | Session CRUD operations |
| nova_flask_app.py | ~70% | 18 | API routes, rate limiting, security |
| backend.py (integration) | ~60% | 20+ | End-to-end RAG pipeline, retrieval, sessions |

**Total: 65+ tests (45 unit + 20+ integration)**

### Integration Test Coverage

Integration tests (`tests/integration/test_end_to_end.py`) cover:

1. **Full Query Pipeline**: Question → Retrieval → LLM → Answer with citation
2. **Hybrid Retrieval**: Vector + BM25 union with deduplication
3. **Confidence Gating**: Low-confidence queries skip LLM
4. **Session Flow**: Start → Continue → Export session report
5. **Error Code Boosting**: Diagnostic codes get prioritized in results
6. **Fallback Behavior**: Timeout triggers model fallback (Qwen → LLAMA)
7. **Conversation Context**: Multi-turn session context building
8. **Retrieval Edge Cases**: Empty queries, deduplication, index loading
9. **Prompt Building**: Standard and session prompts, model selection

**Test Runtime:** ~10-15 seconds (integration tests use mocking to avoid Ollama dependency)

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
    import backend
    
    # Setup test environment
    os.environ["NOVA_FORCE_OFFLINE"] = "1"
    
    # Test retrieval
    docs = backend.retrieve("test query", k=5, top_n=3)
    assert len(docs) > 0
    
    # Mock LLM for testing
    with patch('backend.call_llm', return_value="Mock answer"):
        answer, info = backend.nova_text_handler("test query", mode="Auto")
        assert "Mock answer" in answer
```

### Load Test Template

```bash
# Run load test with 5 concurrent users for 5 minutes
python tests/load/run_load_test.py --users 5 --duration 300

# Output includes:
# - Average latency
# - p95 latency
# - Throughput (queries/min)
# - Error rate
# - Memory usage

# Results saved to: tests/load/results_{users}users_{timestamp}.json
```

## Known Limitations

- Integration tests require Ollama running for full LLM testing (mocked by default)
- Some tests skip if dependencies missing
- GPU tests not included (CPU only)
- Load tests require Flask app to be running separately

## Performance Testing

### Unit Tests
Test suite runs in ~5-10 seconds (unit tests only).

To speed up:
```bash
pytest -n auto  # Parallel execution (requires pytest-xdist)
```

### Integration Tests  
Integration tests run in ~10-15 seconds with mocking.

To run with real LLM (requires Ollama):
```bash
# Disable mocking in test file, then:
pytest tests/integration/ -v --no-cov
```

### Load Tests
Load tests measure system performance under concurrent load.

```bash
# Quick test (1 user, 1 minute)
python tests/load/run_load_test.py --users 1 --duration 60

# Full test (5 users, 5 minutes)
python tests/load/run_load_test.py --users 5 --duration 300
```

See [Load Test Results](../docs/evaluation/LOAD_TEST_RESULTS.md) for benchmarks.

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
