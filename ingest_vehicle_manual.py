"""
Ingest vehicle maintenance manual into FAISS vector database for NIC Public.
"""

import os
import re
import pickle
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Configuration
DATA_FILE = "data/vehicle_manual.txt"
VECTOR_DB_DIR = "vector_db"
CHUNK_SIZE = 500  # Characters per chunk
OVERLAP = 100     # Character overlap between chunks

def load_manual():
    """Load the vehicle manual text."""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def split_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    """
    Split text into overlapping chunks for better retrieval.
    Tries to break on paragraph boundaries when possible.
    """
    chunks = []
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Start new chunk with overlap from previous
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + " " + para
        else:
            current_chunk += " " + para if current_chunk else para
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def create_vector_db(chunks):
    """Create FAISS vector database from text chunks."""
    print(f"Loading embedding model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    print(f"Generating embeddings for {len(chunks)} chunks...")
    embeddings = model.encode(chunks, show_progress_bar=True, convert_to_numpy=True)
    
    # Create FAISS index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings.astype('float32'))
    
    print(f"✅ FAISS index created with {index.ntotal} vectors (dimension: {dimension})")
    
    return index, chunks

def save_database(index, chunks):
    """Save FAISS index and chunks to disk."""
    os.makedirs(VECTOR_DB_DIR, exist_ok=True)
    
    # Save FAISS index
    faiss.write_index(index, f"{VECTOR_DB_DIR}/faiss_index.bin")
    print(f"✅ Saved FAISS index to {VECTOR_DB_DIR}/faiss_index.bin")
    
    # Save chunks
    with open(f"{VECTOR_DB_DIR}/chunks.pkl", 'wb') as f:
        pickle.dump(chunks, f)
    print(f"✅ Saved {len(chunks)} chunks to {VECTOR_DB_DIR}/chunks.pkl")

def main():
    print("="*60)
    print("NIC PUBLIC - Vehicle Manual Ingestion")
    print("="*60)
    
    # Load manual
    print(f"\n1. Loading manual from {DATA_FILE}...")
    text = load_manual()
    print(f"✅ Loaded {len(text):,} characters")
    
    # Split into chunks
    print(f"\n2. Splitting into chunks (size={CHUNK_SIZE}, overlap={OVERLAP})...")
    chunks = split_into_chunks(text)
    print(f"✅ Created {len(chunks)} chunks")
    
    # Sample chunks
    print(f"\n3. Sample chunks:")
    for i in [0, len(chunks)//2, -1]:
        print(f"\n--- Chunk {i} (length: {len(chunks[i])}) ---")
        print(chunks[i][:200] + "..." if len(chunks[i]) > 200 else chunks[i])
    
    # Create vector database
    print(f"\n4. Creating FAISS vector database...")
    index, chunks = create_vector_db(chunks)
    
    # Save to disk
    print(f"\n5. Saving database...")
    save_database(index, chunks)
    
    print("\n" + "="*60)
    print("✅ INGESTION COMPLETE")
    print("="*60)
    print(f"Vector DB location: {VECTOR_DB_DIR}/")
    print(f"Total chunks: {len(chunks)}")
    print(f"Index size: {index.ntotal} vectors")
    print("\nNext step: Run 'python nova_flask_app.py' to start NIC Public")

if __name__ == "__main__":
    main()
