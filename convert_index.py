"""
Quick conversion script to create backend-compatible index files.
Converts multi-domain ingestion output to backend format.
"""
import pickle
import json
import faiss
from pathlib import Path

VECTOR_DB = Path('vector_db')

# Try multi-domain format first, fall back to legacy
multi_domain_chunks = VECTOR_DB / 'chunks_with_metadata.pkl'
multi_domain_index = VECTOR_DB / 'faiss_index_multi_domain.bin'
legacy_chunks = VECTOR_DB / 'chunks.pkl'
legacy_index = VECTOR_DB / 'faiss_index.bin'

if multi_domain_chunks.exists() and multi_domain_index.exists():
    print("[INFO] Using multi-domain format...")
    with open(multi_domain_chunks, 'rb') as f:
        chunks_data = pickle.load(f)
    index = faiss.read_index(str(multi_domain_index))
    
    # chunks_data is list of dicts with text, source, page, domain, category
    docs = []
    for i, chunk in enumerate(chunks_data):
        doc = {
            'id': i,
            'text': chunk.get('text', ''),
            'source': chunk.get('source', 'unknown'),
            'page': chunk.get('page', 0),
            'domain': chunk.get('domain', 'vehicle'),
            'category': chunk.get('category', 'unknown')
        }
        docs.append(doc)
    
elif legacy_chunks.exists() and legacy_index.exists():
    print("[INFO] Using legacy format...")
    with open(legacy_chunks, 'rb') as f:
        chunks = pickle.load(f)
    index = faiss.read_index(str(legacy_index))
    
    # Legacy format - just text strings
    docs = []
    for i, chunk_text in enumerate(chunks):
        doc = {
            'id': i,
            'text': chunk_text,
            'source': 'vehicle_manual.txt',
            'page': i + 1,
            'domain': 'vehicle',
            'category': 'civilian'
        }
        docs.append(doc)
else:
    print("[ERROR] No index files found! Run ingestion first.")
    exit(1)

# Save in backend format
output_docs = VECTOR_DB / 'vehicle_docs.jsonl'
with open(output_docs, 'w', encoding='utf-8') as f:
    for doc in docs:
        f.write(json.dumps(doc) + '\n')

# Copy FAISS index with backend name
output_index = VECTOR_DB / 'vehicle_index.faiss'
faiss.write_index(index, str(output_index))

# Domain statistics
domain_counts = {}
for doc in docs:
    domain = doc.get('domain', 'unknown')
    domain_counts[domain] = domain_counts.get(domain, 0) + 1

print(f"\n✅ Converted {len(docs)} chunks to vehicle_docs.jsonl")
print(f"✅ Copied FAISS index to vehicle_index.faiss")
print("\nDomain distribution:")
for domain, count in sorted(domain_counts.items()):
    print(f"  {domain}: {count} chunks")
print("\n✅ Backend-compatible files ready!")
