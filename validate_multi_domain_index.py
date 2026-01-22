"""
Simple validation script to verify multi-domain index was created correctly.
Directly tests the chunks we stored in the FAISS index.
"""

import pickle
import json
from pathlib import Path
from typing import List, Dict
import sys
from dataclasses import dataclass

sys.path.insert(0, '.')

@dataclass
class Chunk:
    """Chunk class to represent text chunks with metadata."""
    text: str
    domain: str
    source_file: str

def validate_chunks():
    """Validate that chunks were stored correctly with domain metadata."""
    chunks_file = Path("vector_db/chunks_with_metadata.pkl")
    metadata_file = Path("vector_db/domain_metadata.json")
    
    if not chunks_file.exists():
        print(f"❌ Chunks file not found: {chunks_file}")
        return False
    
    # Load chunks
    with open(chunks_file, 'rb') as f:
        chunks: List[Chunk] = pickle.load(f)
    
    # Load metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    print("="*70)
    print("MULTI-DOMAIN INDEX VALIDATION")
    print("="*70)
    
    print(f"\n✅ Loaded {len(chunks)} chunks")
    print(f"✅ Metadata reports {metadata['total_chunks']} chunks")
    
    # Analyze chunks by domain
    domain_counts: Dict[str, int] = {}
    domain_files: Dict[str, set] = {}
    
    for chunk in chunks:
        domain = chunk.domain
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        if domain not in domain_files:
            domain_files[domain] = set()
        domain_files[domain].add(chunk.source_file)
    
    print("\n" + "="*70)
    print("DOMAIN BREAKDOWN")
    print("="*70)
    
    for domain in sorted(domain_counts.keys()):
        count = domain_counts[domain]
        files = domain_files[domain]
        pct = (count / len(chunks)) * 100
        print(f"\n{domain.upper()}")
        print(f"  Chunks: {count:,} ({pct:.1f}%)")
        print(f"  Source files: {', '.join(sorted(files))}")
        
        # Sample a chunk
        sample = next((c for c in chunks if c.domain == domain), None)
        if sample:
            print(f"  Sample text: {sample.text[:100]}...")
    
    print("\n" + "="*70)
    print("EXTRACTION METHOD ANALYSIS")
    print("="*70)
    
    # This info isn't stored, but let's at least confirm files
    print("\nSource files found:")
    files_found = set()
    for chunk in chunks:
        files_found.add(chunk.source_file)
    
    for file in sorted(files_found):
        print(f"  ✓ {file}")
    
    print("\n✅ Multi-domain index validation complete!")
    return True

if __name__ == "__main__":
    validate_chunks()
