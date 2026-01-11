"""
Pytest configuration and shared fixtures for NIC tests.
"""
import os
import sys
import warnings
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set test environment variables
os.environ["NOVA_FORCE_OFFLINE"] = "1"
os.environ["NOVA_DISABLE_VISION"] = "1"
os.environ["NOVA_RATE_LIMIT_ENABLED"] = "0"  # Disable rate limiting in tests
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# Provide deterministic cache secret to avoid security warnings during tests
os.environ.setdefault("NOVA_CACHE_SECRET", "test-cache-secret")
os.environ.setdefault("NOVA_SUPPRESS_CACHE_UTILS_DEPRECATION", "1")

# Silence the legacy cache_utils deprecation warning during tests
warnings.filterwarnings(
    "ignore",
    message="cache_utils is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="cache_utils",
)


@pytest.fixture
def sample_question():
    """Sample vehicle maintenance question for testing."""
    return "What should I check if my engine won't start?"


@pytest.fixture
def sample_documents():
    """Sample documents for retrieval testing."""
    return [
        {
            "text": "Check the battery connections and ensure they are tight and clean.",
            "source": "vehicle_manual.txt",
            "page": 42,
            "confidence": 0.95
        },
        {
            "text": "Verify that the fuel pump is working properly.",
            "source": "vehicle_manual.txt",
            "page": 43,
            "confidence": 0.88
        },
        {
            "text": "Inspect the starter motor for any signs of damage.",
            "source": "vehicle_manual.txt",
            "page": 44,
            "confidence": 0.82
        }
    ]


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up test environment variables."""
    test_vars = {
        "NOVA_HYBRID_SEARCH": "1",
        "NOVA_BM25_CACHE": "0",  # Disable caching in tests
        "NOVA_ENABLE_RETRIEVAL_CACHE": "0",
        "NOVA_ENABLE_SQL_LOG": "0",
        "SECRET_KEY": "test-secret-key-for-testing-only",
        "NOVA_CACHE_SECRET": os.environ["NOVA_CACHE_SECRET"],
        "NOVA_SUPPRESS_CACHE_UTILS_DEPRECATION": os.environ["NOVA_SUPPRESS_CACHE_UTILS_DEPRECATION"],
    }
    for key, value in test_vars.items():
        monkeypatch.setenv(key, value)
    return test_vars


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for tests."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir
