"""
Quick test of NIC Public with vehicle maintenance queries.
Tests only the retrieval layer (no LLM required).
"""

import sys
sys.path.insert(0, '.')

from backend import retrieve

def test_retrieval(question, description):
    """Test retrieval for a query."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"{'='*60}")
    print(f"Query: {question}\n")
    
    try:
        # Test retrieval
        results = retrieve(question, k=5, top_n=3, use_sklearn_reranker=False)
        print(f"✅ Retrieved {len(results)} chunks\n")
        
        for i, result in enumerate(results, 1):
            chunk = result['text'] if isinstance(result, dict) else result
            print(f"--- Chunk {i} ---")
            print(chunk[:300] + "..." if len(chunk) > 300 else chunk)
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run test suite."""
    print("="*60)
    print("NIC PUBLIC - Vehicle Maintenance Retrieval Test")
    print("="*60)
    print("Testing FAISS retrieval with vehicle manual...")
    
    tests = [
        (
            "What should I check if my engine cranks but won't start?",
            "In-scope diagnostic query"
        ),
        (
            "What's the torque specification for lug nuts?",
            "Specification query (should retrieve Table 7-1)"
        ),
        (
            "How do I replace the moon?",
            "Out-of-scope query (should retrieve nothing relevant)"
        ),
        (
            "My temperature gauge is reading high. What could be wrong?",
            "Multi-cause diagnostic (cooling system)"
        ),
        (
            "Battery warning light is on",
            "Electrical system diagnostic"
        )
    ]
    
    results = []
    for question, description in tests:
        success = test_retrieval(question, description)
        results.append(success)
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"Completed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All retrieval tests completed successfully!")
        print("✅ FAISS index is working with vehicle maintenance manual")
        print("\nNext step: Start Flask server with:")
        print("  python nova_flask_app.py")
    else:
        print(f"\n⚠ {total-passed} test(s) failed. Review output above.")

if __name__ == "__main__":
    main()
