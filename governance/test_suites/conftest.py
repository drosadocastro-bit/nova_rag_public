"""
Pytest configuration for governance test suites.

Adds project root to sys.path so that module imports work correctly.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
