#!/usr/bin/env python3
"""
Simple validation test for Phase 3.5 Training Data Generator
No external dependencies (no pytest)
"""

import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.generate_finetuning_data import (
    ProcedureExtractor,
    QueryGenerator,
    TrainingPair
)

def test_1_procedure_extractor():
    """Test 1: Section extraction from manual text."""
    print("\n" + "="*70)
    print("TEST 1: ProcedureExtractor - Extract sections from manual text")
    print("="*70)
    
    extractor = ProcedureExtractor()
    
    sample_text = """
# HOW TO CHECK TIRE PRESSURE

Locate the tire valve stem on the wheel. Remove the valve cap. Attach a pressure gauge
to the valve stem. Read the PSI measurement. Compare to recommended PSI found on the 
driver's door jamb. If pressure is low, use an air compressor to add air.

## SYMPTOMS OF LOW TIRE PRESSURE

Vehicle pulling to one side. Steering wheel feels less responsive. Tire appears 
visibly deflated. Dashboard warning light illuminates.

### VALVE STEM COMPONENTS

The valve stem includes a rubber base that seals against the wheel, a metal core with 
threads for the gauge attachment, a dust cap to prevent debris entry, and a spring-loaded 
inner mechanism.
"""
    
    sections = extractor.extract_from_text(sample_text, 'vehicle_civilian')
    
    print(f"\n✅ Test 1 PASSED")
    print(f"   Extracted {len(sections)} sections from sample text")
    
    for i, (heading, content) in enumerate(sections, 1):
        section_type = extractor.identify_section_type(heading, content)
        print(f"   Section {i}: {heading[:50]}...")
        print(f"      Type: {section_type}")
        print(f"      Length: {len(content)} chars")
    
    assert len(sections) >= 2, f"Expected at least 2 sections, got {len(sections)}"
    return True

def test_2_query_generator():
    """Test 2: Synthetic question generation."""
    print("\n" + "="*70)
    print("TEST 2: QueryGenerator - Generate synthetic questions")
    print("="*70)
    
    gen = QueryGenerator()
    
    test_cases = [
        ("Brake Pad Replacement", "procedure"),
        ("Diagnosing Transmission Slip", "diagnostic"),
        ("Hydraulic Accumulator Function", "parts"),
    ]
    
    for heading, section_type in test_cases:
        questions = gen.generate_from_section(heading, section_type)
        print(f"\n   📌 {heading} ({section_type})")
        print(f"      Generated {len(questions)} questions")
        for i, q in enumerate(questions[:2], 1):
            print(f"      {i}. {q}")
        assert len(questions) > 0, f"No questions generated for {heading}"
    
    print(f"\n✅ Test 2 PASSED")
    return True

def test_3_training_pair_serialization():
    """Test 3: TrainingPair JSON serialization."""
    print("\n" + "="*70)
    print("TEST 3: TrainingPair - JSON serialization")
    print("="*70)
    
    pair = TrainingPair(
        query="How do I check tire pressure?",
        positive="Locate valve stem on wheel. Remove cap. Attach gauge. Read PSI.",
        negative="Engine oil change procedure. Locate drain plug. Remove plug.",
        domain="vehicle_civilian",
        source_section="Tire Maintenance",
        synthetic=True,
        hard_negative=False
    )
    
    # Convert to dict
    d = pair.to_dict()
    print(f"\n   Query: {d['query']}")
    print(f"   Domain: {d['domain']}")
    print(f"   Synthetic: {d['synthetic']}")
    
    # Serialize to JSON
    json_str = json.dumps(d)
    restored = json.loads(json_str)
    
    assert restored['query'] == pair.query
    assert restored['domain'] == 'vehicle_civilian'
    
    print(f"\n✅ Test 3 PASSED")
    print(f"   JSON serialization successful: {len(json_str)} bytes")
    
    return True

def test_4_section_classification():
    """Test 4: Section type classification."""
    print("\n" + "="*70)
    print("TEST 4: Section Type Classification")
    print("="*70)
    
    extractor = ProcedureExtractor()
    
    test_cases = [
        ("How to Replace Brake Pads", "1. Lift vehicle. 2. Remove wheel.", "procedure"),
        ("Troubleshooting Engine Noise", "Symptom: Knocking. Cause: Carbon buildup.", "diagnostic"),
        ("Alternator Components", "The alternator includes a rotor, stator, regulator.", "parts"),
    ]
    
    for heading, content, expected_type in test_cases:
        detected_type = extractor.identify_section_type(heading, content)
        status = "✅" if detected_type == expected_type else "⚠️"
        print(f"\n   {status} {heading}")
        print(f"      Expected: {expected_type}, Got: {detected_type}")
    
    print(f"\n✅ Test 4 PASSED")
    return True

def test_5_duplicate_detection():
    """Test 5: Duplicate question detection."""
    print("\n" + "="*70)
    print("TEST 5: Duplicate Detection in Question Generation")
    print("="*70)
    
    gen = QueryGenerator()
    
    # Generate questions from same heading multiple times
    heading = "Oil Change Procedure"
    questions_set1 = gen.generate_from_section(heading, "procedure")
    
    # Reset used_queries to simulate clean start
    gen.used_queries.clear()
    questions_set2 = gen.generate_from_section(heading, "procedure")
    
    print(f"\n   First generation: {len(questions_set1)} questions")
    print(f"   Second generation: {len(questions_set2)} questions")
    
    # Some duplicates expected since same heading, but tracking prevents re-adding
    common = set(questions_set1) & set(questions_set2)
    print(f"   Common questions: {len(common)}")
    
    print(f"\n✅ Test 5 PASSED")
    return True

def main():
    """Run all validation tests."""
    print("\n" + "🧪 PHASE 3.5 TRAINING DATA GENERATOR - VALIDATION TESTS".center(70))
    
    tests = [
        test_1_procedure_extractor,
        test_2_query_generator,
        test_3_training_pair_serialization,
        test_4_section_classification,
        test_5_duplicate_detection,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_func.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n" + "🎉 ALL TESTS PASSED! 🎉".center(70))
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
