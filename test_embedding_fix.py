#!/usr/bin/env python3
"""Quick test to verify embedding model loads correctly after huggingface_hub fix"""

import requests
import time

print("Testing embedding model fix...")
print("Waiting 2 seconds for server to be ready...")
time.sleep(2)

try:
    response = requests.post(
        'http://localhost:5000/api/ask',
        json={'question': 'What is brake fluid?', 'mode': 'Auto'},
        timeout=60
    )
    
    if response.status_code == 200:
        data = response.json()
        confidence = data.get('confidence', 'N/A')
        answer = data.get('answer', '')[:300]
        
        print(f"\n[OK] Request successful!")
        print(f"Confidence: {confidence}")
        print(f"Answer preview: {answer}...")
        
        # Check if confidence is reasonable (should be > 50% for simple vehicle question)
        if isinstance(confidence, str) and '%' in confidence:
            conf_val = float(confidence.replace('%', ''))
            if conf_val > 50:
                print(f"\n✓ Embedding model is working! Confidence {conf_val}% > 50%")
                exit(0)
            elif conf_val > 1:
                print(f"\n⚠ Embedding model loaded but confidence is low ({conf_val}%)")
                exit(0)
            else:
                print(f"\n✗ Embedding model may still be broken (confidence {conf_val}% ≈ 1%)")
                exit(1)
        else:
            print(f"\n⚠ Response received but confidence format unexpected: {confidence}")
            exit(0)
    else:
        print(f"\n✗ Request failed with status {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)
        
except requests.exceptions.Timeout:
    print("\n✗ Request timed out (LLM may be slow)")
    exit(1)
except Exception as e:
    print(f"\n✗ Error: {e}")
    exit(1)
