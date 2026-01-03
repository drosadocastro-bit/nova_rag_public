"""Quick conversion script to create backend-compatible index files"""
import pickle
import json
import faiss
import shutil
from pathlib import Path

# Load pickled data
with open('vector_db/chunks.pkl', 'rb') as f:
    chunks = pickle.load(f)

# Load FAISS index
index = faiss.read_index('vector_db/faiss_index.bin')

# Convert chunks to JSONL format expected by backend
docs = []
for i, chunk_text in enumerate(chunks):
    doc = {
        'id': i,
        'text': chunk_text,
        'source': 'vehicle_manual.txt',
        'page': i + 1  # Approximate page numbering
    }
    docs.append(doc)

# Save in backend format
with open('vector_db/vehicle_docs.jsonl', 'w', encoding='utf-8') as f:
    for doc in docs:
        f.write(json.dumps(doc) + '\n')

# Copy FAISS index with new name
faiss.write_index(index, 'vector_db/vehicle_index.faiss')

print(f"✅ Converted {len(docs)} chunks to vehicle_docs.jsonl")
print(f"✅ Copied FAISS index to vehicle_index.faiss")
print("✅ Backend-compatible files ready!")
