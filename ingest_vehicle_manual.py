"""
Ingest technical manuals (PDFs) into FAISS vector database for NIC Public.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.retrieval.retrieval_engine import build_index, INDEX_PATH, DOCS_PATH, DOCS_DIR


def main():
    print("="*70)
    print("NIC PUBLIC - Technical Documentation Ingestion")
    print("="*70)
    
    # Scan for PDFs
    print(f"\n📂 Scanning for PDFs in: {DOCS_DIR}")
    print("   (Searching recursively in all subdirectories)")
    
    # List all PDFs found
    pdf_files = sorted(DOCS_DIR.rglob("*.pdf"))
    
    if not pdf_files:
        print(f"\n❌ ERROR: No PDF files found in {DOCS_DIR}")
        print("   Please add PDF manuals to the data/ directory")
        return
    
    print(f"\n✅ Found {len(pdf_files)} PDF files:")
    total_size = 0
    for pdf_path in pdf_files:
        rel_path = pdf_path.relative_to(DOCS_DIR)
        size_mb = pdf_path.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"   - {rel_path} ({size_mb:.1f} MB)")
    
    print(f"\n📊 Total: {len(pdf_files)} files, {total_size:.1f} MB")
    
    # Build index
    print("\n🔨 Building FAISS vector index...")
    print(f"   Index will be saved to: {INDEX_PATH}")
    print(f"   Metadata will be saved to: {DOCS_PATH}")
    
    try:
        index, chunks = build_index()
        
        if index is None:
            print("\n⚠️  WARNING: No embeddings created (fallback mode)")
            print(f"   Created {len(chunks)} text chunks for lexical search only")
        else:
            print("\n✅ Index built successfully!")
            print(f"   Total vectors: {index.ntotal}")
            print(f"   Total chunks: {len(chunks)}")
            print(f"   Vector dimension: {index.d}")
        
        # Show sample documents
        print("\n📄 Sample indexed documents:")
        for i, doc in enumerate(chunks[:3]):
            source = doc.get('source', 'unknown')
            page = doc.get('page', '?')
            snippet = doc.get('snippet', doc.get('text', ''))[:100]
            print(f"\n   [{i+1}] {source} (page {page})")
            print(f"       {snippet}...")
        
        print("\n" + "="*70)
        print("✅ INGESTION COMPLETE")
        print("="*70)
        print(f"📁 Index location: {INDEX_PATH}")
        print(f"📁 Docs location: {DOCS_PATH}")
        print(f"📊 Total chunks: {len(chunks)}")
        print("\n🚀 Next step: Start the FastAPI server:")
        print("   .\\start_fastapi_qwen4b.ps1")
        print("   OR")
        print("   python -m uvicorn nova_fastapi_app:app --host 127.0.0.1 --port 5678")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ ERROR during index building: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
