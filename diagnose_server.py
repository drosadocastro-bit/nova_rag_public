#!/usr/bin/env python3
"""Diagnose server startup issues by testing components individually."""

import sys
import traceback
from pathlib import Path

print("\n" + "=" * 80)
print("DIAGNOSTIC: Testing NIC components for startup issues")
print("=" * 80 + "\n")

# Test 1: Import Flask
print("[1/5] Testing Flask import...")
try:
    from flask import Flask
    print("  ✅ Flask imported successfully")
except Exception as e:
    print(f"  ❌ Flask import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 2: Import backend module
print("[2/5] Testing backend module...")
try:
    import backend
    print("  ✅ Backend module imported successfully")
except Exception as e:
    print(f"  ❌ Backend import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 3: Import Flask app
print("[3/5] Testing nova_flask_app...")
try:
    from nova_flask_app import app
    print("  ✅ Flask app created successfully")
except Exception as e:
    print(f"  ❌ Flask app creation failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 4: Create test client
print("[4/5] Testing Flask test client...")
try:
    client = app.test_client()
    print("  ✅ Test client created successfully")
except Exception as e:
    print(f"  ❌ Test client creation failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test basic route
print("[5/5] Testing basic GET request...")
try:
    response = client.get("/")
    print(f"  ✅ GET / returned status {response.status_code}")
except Exception as e:
    print(f"  ❌ GET request failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL DIAGNOSTICS PASSED - Flask app is functional")
print("=" * 80)
print("\nRecommendations:")
print("  - Try running with: python nova_flask_app.py")
print("  - Or with Waitress: python run_waitress.py --port 5000")
print("  - Check if Ollama is running at http://127.0.0.1:11434")
print("=" * 80 + "\n")
