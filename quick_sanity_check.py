"""Quick sanity check for NIC"""
import requests
import time

tests = [
    ("How do I check brake fluid?", "should_answer", 60),
    ("What's the capital of France?", "should_refuse", 20),
    ("How tight should the drive belt be?", "should_answer", 30),
]

print("="*80)
print("QUICK SANITY CHECK")
print("="*80)

for question, expect, timeout in tests:
    print(f"\n[TEST] {question}")
    print(f"  Expected: {expect}, timeout: {timeout}s")
    try:
        start = time.time()
        response = requests.post(
            'http://localhost:5000/api/ask',
            json={'question': question, 'mode': 'Auto'},
            timeout=timeout
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            conf = data.get('confidence', 'N/A')
            answer_preview = str(data.get('answer', ''))[:100]
            
            print(f"  [OK] Response in {elapsed:.1f}s, Confidence: {conf}")
            print(f"  Answer preview: {answer_preview}")
        else:
            print(f"  [FAIL] HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT] No response within {timeout}s")
    except Exception as e:
        print(f"  [ERROR] {e}")

print("\n" + "="*80)
