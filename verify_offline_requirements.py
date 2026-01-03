#!/usr/bin/env python3
"""
Verify Offline Requirements for NIC RAG System
===============================================
Checks that all required libraries and models are installed
for fully offline operation (no network access needed).
"""

import sys
import os
from pathlib import Path

print("=" * 70)
print("NIC RAG - Offline Requirements Verification")
print("=" * 70)
print()

# Track results
all_ok = True
warnings = []
errors = []

# =============================================================================
# 1. CHECK PYTHON LIBRARIES
# =============================================================================
print("[1/4] Checking Python libraries...")

required_libs = {
    # Core dependencies
    "flask": "Flask web server",
    "requests": "HTTP client",
    
    # RAG/ML libraries
    "faiss": "Vector search (FAISS)",
    "sentence_transformers": "Embeddings (local models)",
    "torch": "PyTorch (ML backend)",
    
    # LLM client
    "openai": "OpenAI-compatible client (LM Studio)",
    
    # PDF/document processing
    "pypdf": "PDF reader",
    "Pillow": "Image processing",
    
    # RAGAS evaluation (optional)
    "datasets": "HuggingFace datasets",
    "ragas": "RAGAS evaluation framework",
    "langchain_openai": "LangChain LM Studio integration",
    "langchain_community": "LangChain community integrations",
}

for lib, desc in required_libs.items():
    try:
        __import__(lib)
        print(f"  ✅ {lib:25s} - {desc}")
    except ImportError:
        print(f"  ❌ {lib:25s} - {desc} (MISSING)")
        errors.append(f"Missing library: {lib} ({desc})")
        all_ok = False

print()

# =============================================================================
# 2. CHECK LOCAL MODEL FILES
# =============================================================================
print("[2/4] Checking local model files...")

base_dir = Path(r"C:\nova_rag_public")
model_checks = {
    "Embedding model": base_dir / "models" / "all-MiniLM-L6-v2" / "config.json",
    "FAISS index": base_dir / "vector_db" / "vehicle_index.faiss",
    "Document store": base_dir / "vector_db" / "vehicle_docs.jsonl",
    "Source data": base_dir / "data" / "vehicle_manual.txt",
}

for name, path in model_checks.items():
    if path.exists():
        size = path.stat().st_size if path.is_file() else sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
        size_mb = size / (1024 * 1024)
        print(f"  ✅ {name:25s} - {path.name} ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ {name:25s} - {path} (MISSING)")
        errors.append(f"Missing file: {name} at {path}")
        all_ok = False

print()

# =============================================================================
# 3. CHECK LM STUDIO MODELS
# =============================================================================
print("[3/4] Checking LM Studio connection (models must be loaded manually)...")

try:
    import requests
    r = requests.get("http://127.0.0.1:1234/v1/models", timeout=3)
    if r.status_code == 200:
        models = r.json().get("data", [])
        print(f"  ✅ LM Studio running with {len(models)} model(s) loaded")
        for model in models:
            model_id = model.get("id", "unknown")
            print(f"     - {model_id}")
        
        # Check for expected models
        model_ids = [m.get("id", "") for m in models]
        expected = [
            "fireball-meta-llama-3.2-8b-instruct-agent-003-128k-code-dpo",
            "qwen/qwen2.5-coder-14b"
        ]
        for exp in expected:
            if not any(exp in mid for mid in model_ids):
                warnings.append(f"Expected model '{exp}' not loaded in LM Studio")
    else:
        print(f"  ⚠️  LM Studio responded with HTTP {r.status_code}")
        warnings.append("LM Studio connection issue")
except Exception as e:
    print(f"  ⚠️  LM Studio not accessible: {e}")
    warnings.append("LM Studio not running - start it manually with required models")

print()

# =============================================================================
# 4. CHECK ENVIRONMENT CONFIGURATION
# =============================================================================
print("[4/4] Checking environment configuration...")

env_checks = {
    "NOVA_FORCE_OFFLINE": ("Offline mode", os.environ.get("NOVA_FORCE_OFFLINE", "0")),
    "HF_HUB_OFFLINE": ("HuggingFace offline", os.environ.get("HF_HUB_OFFLINE", "0")),
    "TRANSFORMERS_OFFLINE": ("Transformers offline", os.environ.get("TRANSFORMERS_OFFLINE", "0")),
}

print("  Environment variables:")
for var, (desc, value) in env_checks.items():
    status = "✅" if value == "1" else "ℹ️ "
    print(f"    {status} {var:25s} = {value:5s} ({desc})")

print()
print("  Recommended settings for offline mode:")
print("    export NOVA_FORCE_OFFLINE=1")
print("    export HF_HUB_OFFLINE=1")
print("    export TRANSFORMERS_OFFLINE=1")

print()

# =============================================================================
# SUMMARY
# =============================================================================
print("=" * 70)
print("VERIFICATION SUMMARY")
print("=" * 70)

if errors:
    print(f"\n❌ ERRORS ({len(errors)}):")
    for err in errors:
        print(f"  - {err}")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for warn in warnings:
        print(f"  - {warn}")

if all_ok and not errors:
    print("\n✅ ALL OFFLINE REQUIREMENTS SATISFIED")
    print("\nYou can enable offline mode with:")
    print("  export NOVA_FORCE_OFFLINE=1")
    print("\nOr in Python:")
    print("  os.environ['NOVA_FORCE_OFFLINE'] = '1'")
    sys.exit(0)
else:
    print(f"\n❌ {len(errors)} critical error(s) found")
    print("\nTo fix:")
    print("  1. Install missing libraries: pip install <library>")
    print("  2. Download missing models to C:\\nova_rag_public\\models\\")
    print("  3. Build FAISS index: python ingest_vehicle_manual.py")
    print("  4. Start LM Studio and load required models")
    sys.exit(1)
