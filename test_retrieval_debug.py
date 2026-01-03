#!/usr/bin/env python3
"""Test retrieval directly to debug low confidence"""

import sys
sys.path.insert(0, r'C:\nova_rag_public')

from backend import retrieve, get_text_embed_model

# Force load the model
model = get_text_embed_model()
print(f"Model loaded: {model is not None}")

# Test retrieval
print("\n--- Testing retrieval ---")
query = "How do I check brake fluid?"
results = retrieve(query, k=5, top_n=3, use_reranker=True)

print(f"\nQuery: {query}")
print(f"Results: {len(results)}")
for i, doc in enumerate(results):
    print(f"\n[{i+1}] Confidence: {doc.get('confidence', 'N/A')}")
    print(f"Text preview: {doc.get('text', '')[:150]}...")
