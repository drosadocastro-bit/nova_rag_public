"""Quick FastAPI test - assumes server is running on localhost:5678"""
import requests
import time

BASE_URL = "http://localhost:5678"

print("Testing FastAPI server...")

# Test 1: Health check
try:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    print(f"\n[1/3] Health check: {response.status_code}")
    print(f"  Response: {response.json()}")
except Exception as e:
    print(f"\n[1/3] Health check FAILED: {e}")
    print("\nMake sure FastAPI is running in another terminal:")
    print("  python -m uvicorn nova_fastapi_app:app --host 127.0.0.1 --port 5678")
    exit(1)

# Test 2: Simple query
try:
    print("\n[2/3] Testing simple query...")
    start = time.time()
    response = requests.post(
        f"{BASE_URL}/query",
        params={"q": "How to reset the battery?"},
        timeout=30
    )
    elapsed = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        print(f"  Status: {response.status_code} OK")
        print(f"  Latency: {elapsed:.0f}ms")
        print(f"  Answer length: {len(data.get('answer', ''))} chars")
        print(f"  Answer preview: {data.get('answer', '')[:100]}...")
    else:
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text}")
except Exception as e:
    print(f"  Query FAILED: {e}")

# Test 3: Root endpoint
try:
    print("\n[3/3] Testing root endpoint (API docs)...")
    response = requests.get(f"{BASE_URL}/", timeout=5)
    if response.status_code == 200:
        data = response.json()
        print(f"  Status: {response.status_code} OK")
        print(f"  App: {data.get('app')}")
        print(f"  Mode: {data.get('mode')}")
        print(f"  Endpoints: {list(data.get('endpoints', {}).keys())}")
    else:
        print(f"  Status: {response.status_code}")
except Exception as e:
    print(f"  Root endpoint FAILED: {e}")

print("\n[COMPLETE] FastAPI test finished!")
print(f"\nAPI Documentation: {BASE_URL}/docs")
print(f"Alternative docs: {BASE_URL}/redoc")
