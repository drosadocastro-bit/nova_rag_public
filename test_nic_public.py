"""
Quick test of NIC Public with vehicle maintenance queries.
Uses nova_text_handler for end-to-end response generation.
"""

import json
import sys
sys.path.insert(0, '.')

from backend import retrieve, nova_text_handler

def test_query(question, description):
    """Test a single query."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"{'='*60}")
    print(f"Query: {question}\n")
    
    try:
        # Test retrieval
        print("1. Testing retrieval...")
        results = retrieve(question, k=5, top_n=3)
        print(f"✅ Retrieved {len(results)} chunks\n")

        for i, chunk in enumerate(results, 1):
            chunk_text = chunk.get('text') if isinstance(chunk, dict) else str(chunk)
            print(f"--- Chunk {i} (Preview) ---")
            print(chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text)
            if isinstance(chunk, dict):
                print(f"Source: {chunk.get('source', 'unknown')} | Page: {chunk.get('page', '?')}")
            print()

        # Test full response
        print("2. Testing full response generation...")
        answer, model_info = nova_text_handler(question, mode="Auto")

        print(f"\n{'─'*60}")
        print("RESPONSE:")
        print(f"{'─'*60}")
        print(json.dumps(answer, indent=2) if isinstance(answer, dict) else answer)
        print(f"\n{'─'*60}")
        print("METADATA:")
        print(f"{'─'*60}")
        print(f"Model Info: {model_info}")

        return True

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run test suite."""
    print("="*60)
    print("NIC PUBLIC - Vehicle Maintenance Test Suite")
    print("="*60)
    
    tests = [
        (
            "What should I check if my engine cranks but won't start?",
            "In-scope diagnostic query"
        ),
        (
            "What's the torque specification for lug nuts?",
            "Specification query (should cite Table 7-1)"
        ),
        (
            "How do I replace the moon?",
            "Out-of-scope query (should refuse)"
        ),
        (
            "My temperature gauge is reading high. What could be wrong?",
            "Multi-cause diagnostic"
        )
    ]
    
    results = []
    for question, description in tests:
        success = test_query(question, description)
        results.append(success)
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {100*passed/total:.1f}%")
    
    if passed == total:
        print("\n✅ All tests passed! NIC Public is working correctly.")
    else:
        print(f"\n⚠ {total-passed} test(s) failed. Review output above.")

if __name__ == "__main__":
    main()
