"""Direct speed test - bypasses HTTP overhead to test native performance"""
import time
from llm_engine import call_llm

print("Testing native Qwen 4B speed directly (no HTTP)...")
print("=" * 60)

# Set environment to use 128 tokens max
import os  # noqa: E402
os.environ["NOVA_MAX_TOKENS_OSS"] = "128"

# Simple question
question = "How do I check the alternator voltage? Answer briefly."

print(f"\nQuestion: {question}\n")

start = time.time()
response = call_llm(question, model="qwen", max_tokens=128)
elapsed = time.time() - start

print(f"Response:\n{response}\n")
print(f"Response length: {len(response)} chars")
print(f"Time: {elapsed:.1f}s")
print(f"Speed: {len(response)/elapsed:.0f} chars/sec")

if elapsed < 5:
    print("\n[OK] Native engine is fast - HTTP/FastAPI might be the bottleneck")
else:
    print(f"\n[SLOW] Even native engine is slow ({elapsed:.1f}s)")
