"""
Comprehensive health check for NIC RAG system.
"""

import sys
from pathlib import Path
import json

print("="*70)
print("NIC RAG HEALTH CHECK")
print("="*70)

# 1. Check vector database
print("\n📊 1. VECTOR DATABASE STATUS")
print("-" * 70)

vector_db_dir = Path("vector_db")
index_path = vector_db_dir / "nic_index.faiss"
docs_path = vector_db_dir / "nic_docs.jsonl"

if index_path.exists():
    import faiss
    index = faiss.read_index(str(index_path))
    print(f"✅ FAISS Index: {index_path}")
    print(f"   Vectors: {index.ntotal}")
    print(f"   Dimension: {index.d}")
else:
    print(f"❌ FAISS Index NOT FOUND: {index_path}")

if docs_path.exists():
    with open(docs_path, 'r', encoding='utf-8') as f:
        doc_count = sum(1 for _ in f)
    print(f"✅ Docs Metadata: {docs_path}")
    print(f"   Document chunks: {doc_count}")
    
    # Sample first doc
    with open(docs_path, 'r', encoding='utf-8') as f:
        first_doc = json.loads(f.readline())
    print(f"   Sample doc source: {first_doc.get('source', 'unknown')}")
    print(f"   Sample doc fields: {list(first_doc.keys())}")
else:
    print(f"❌ Docs Metadata NOT FOUND: {docs_path}")

# 2. Check PDF files
print("\n📁 2. PDF FILES IN DATA DIRECTORY")
print("-" * 70)

data_dir = Path("data")
pdf_files = sorted(data_dir.rglob("*.pdf"))
print(f"Total PDFs found: {len(pdf_files)}")
total_size = 0
domain_counts = {}
for pdf_path in pdf_files:
    rel_path = pdf_path.relative_to(data_dir)
    domain = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
    domain_counts[domain] = domain_counts.get(domain, 0) + 1
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    total_size += size_mb
    print(f"  - {rel_path} ({size_mb:.1f} MB)")

print(f"\n📊 Domain distribution:")
for domain, count in sorted(domain_counts.items()):
    print(f"  - {domain}: {count} PDFs")
print(f"\n💾 Total size: {total_size:.1f} MB")

# 3. Check PDF processing libraries
print("\n🔧 3. PDF PROCESSING LIBRARIES")
print("-" * 70)

try:
    import pypdf
    print(f"✅ pypdf: {pypdf.__version__}")
except ImportError as e:
    print(f"❌ pypdf: NOT INSTALLED")

try:
    import pdfplumber
    print(f"✅ pdfplumber: {pdfplumber.__version__}")
except ImportError:
    print(f"❌ pdfplumber: NOT INSTALLED")

try:
    import pytesseract
    print(f"✅ pytesseract: {pytesseract.__version__}")
    try:
        version = pytesseract.get_tesseract_version()
        print(f"   Tesseract OCR: v{version}")
    except:
        print(f"   ⚠️  Tesseract binary NOT FOUND in PATH")
except ImportError:
    print(f"❌ pytesseract: NOT INSTALLED")

try:
    from pdf2image import convert_from_path
    print(f"✅ pdf2image: installed")
    # Check poppler
    try:
        from pdf2image.exceptions import PDFInfoNotInstalledError
        # Try to use it
        print(f"   ⚠️  Poppler status unknown (need to test conversion)")
    except:
        pass
except ImportError:
    print(f"❌ pdf2image: NOT INSTALLED")

# 4. Check embedding model
print("\n🤖 4. EMBEDDING MODEL")
print("-" * 70)

try:
    from sentence_transformers import SentenceTransformer
    import torch
    
    models_dir = Path("models")
    local_model = models_dir / "all-MiniLM-L6-v2"
    
    if local_model.exists():
        print(f"✅ Local embedding model: {local_model}")
        print(f"   CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   CUDA device: {torch.cuda.get_device_name(0)}")
    else:
        print(f"⚠️  Local model not found, will download from HuggingFace")
        
except ImportError as e:
    print(f"❌ sentence-transformers: NOT INSTALLED")

# 5. Check Flask vs FastAPI
print("\n🌐 5. WEB SERVER STATUS")
print("-" * 70)

flask_app = Path("nova_flask_app.py")
fastapi_app = Path("nova_fastapi_app.py")

if flask_app.exists():
    print(f"✅ Flask app exists: {flask_app}")
    # Count Flask references
    with open(flask_app, 'r', encoding='utf-8') as f:
        content = f.read()
        import_count = content.count('from flask')
        print(f"   Flask imports: {import_count}")
else:
    print(f"❌ Flask app NOT FOUND")

if fastapi_app.exists():
    print(f"✅ FastAPI app exists: {fastapi_app}")
    with open(fastapi_app, 'r', encoding='utf-8') as f:
        content = f.read()
        import_count = content.count('from fastapi')
        print(f"   FastAPI imports: {import_count}")
else:
    print(f"❌ FastAPI app NOT FOUND")

# 6. Check which apps reference Flask
print("\n🔍 6. FLASK REFERENCES IN CODEBASE")
print("-" * 70)

flask_refs = []
for py_file in Path(".").rglob("*.py"):
    if "venv" in str(py_file) or ".venv" in str(py_file):
        continue
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if 'nova_flask_app.py' in content and py_file.name != 'nova_flask_app.py':
            count = content.count('nova_flask_app')
            flask_refs.append((py_file, count))

if flask_refs:
    print(f"⚠️  Found {len(flask_refs)} files still referencing nova_flask_app.py:")
    for filepath, count in sorted(flask_refs, key=lambda x: x[1], reverse=True)[:10]:
        print(f"   - {filepath} ({count} references)")
else:
    print(f"✅ No files referencing nova_flask_app.py")

# 7. Check retrieval engine config
print("\n⚙️  7. RETRIEVAL ENGINE CONFIGURATION")
print("-" * 70)

try:
    from core.retrieval.retrieval_engine import INDEX_PATH, DOCS_PATH, DOCS_DIR
    print(f"✅ Retrieval engine loaded")
    print(f"   DOCS_DIR: {DOCS_DIR}")
    print(f"   INDEX_PATH: {INDEX_PATH}")
    print(f"   DOCS_PATH: {DOCS_PATH}")
    print(f"   Index exists: {INDEX_PATH.exists()}")
    print(f"   Docs exist: {DOCS_PATH.exists()}")
except Exception as e:
    print(f"❌ Failed to load retrieval engine: {e}")

# 8. Check environment variables
print("\n🔐 8. ENVIRONMENT VARIABLES")
print("-" * 70)

import os
key_vars = [
    "NOVA_LLM_OSS",
    "NOVA_LLM_LLAMA",
    "NOVA_MAX_TOKENS_OSS",
    "NOVA_USE_NATIVE_LLM",
    "NOVA_FORCE_OFFLINE",
]

for var in key_vars:
    value = os.environ.get(var, "NOT SET")
    print(f"   {var}: {value}")

# 9. Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

issues = []
if not index_path.exists():
    issues.append("FAISS index missing - run ingest script")
if not docs_path.exists():
    issues.append("Docs metadata missing - run ingest script")
if len(pdf_files) == 0:
    issues.append("No PDFs found in data/ directory")
if flask_refs:
    issues.append(f"{len(flask_refs)} files still reference Flask app")

if issues:
    print("⚠️  ISSUES FOUND:")
    for issue in issues:
        print(f"   - {issue}")
else:
    print("✅ ALL CHECKS PASSED")

print("\n📋 RECOMMENDED ACTIONS:")
if not index_path.exists() or not docs_path.exists():
    print("   1. Run: python ingest_vehicle_manual.py")
if flask_refs:
    print("   2. Update benchmark and test scripts to use FastAPI (port 5678)")
print("   3. Start server: .\\start_fastapi_qwen4b.ps1")
print("="*70)
