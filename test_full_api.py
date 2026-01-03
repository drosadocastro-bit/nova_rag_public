#!/usr/bin/env python3
"""Full API test to check actual response"""
import requests
import json
import time

print("Starting Flask server test...")
time.sleep(2)

response = requests.post(
    'http://localhost:5000/api/ask',
    json={'question': 'How do I check brake fluid level?', 'mode': 'Auto'},
        timeout=600
data = response.json()

print(f"\nFull response keys: {list(data.keys())}")
print(f"\nConfidence field: {data.get('confidence')}")
print(f"\nAnswer length: {len(data.get('answer', ''))}")
print(f"\nAnswer preview (first 500 chars):")
print(data.get('answer', '')[:500])
print("\n" + "="*60)

# Check metadata
if 'metadata' in data:
    print(f"\nMetadata keys: {list(data['metadata'].keys())}")
    if 'retrieval_confidence' in data['metadata']:
        print(f"Retrieval confidence: {data['metadata']['retrieval_confidence']}")
