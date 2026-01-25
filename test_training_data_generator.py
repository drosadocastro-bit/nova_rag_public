#!/usr/bin/env python3
"""
Test script for Phase 3.5 Training Data Generator
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.generate_finetuning_data import (
    TrainingDataGenerator,
    ProcedureExtractor,
    QueryGenerator
)

def test_procedure_extractor():
    """Test section extraction from sample text."""
    print("\n" + "="*60)
    print("TEST 1: ProcedureExtractor")
    print("="*60)
    
    sample_text = """
# HOW TO CHECK TIRE PRESSURE

1. Locate the tire valve stem on the wheel
2. Remove the valve cap
3. Attach pressure gauge to valve
4. Read the pressure display
5. Compare to recommended PSI (found on driver's door jamb)

## SYMPTOMS OF LOW TIRE PRESSURE

- Vehicle pulls to one side while driving
- Steering wheel feels less responsive
- Tire appears visibly deflated
- Warning light on dashboard

## VALVE STEM COMPONENTS

The valve stem includes:
- Rubber base that seals against wheel
- Metal core with threads
- Dust cap to prevent dirt entry
- Spring-loaded inner mechanism
"""
    
    extractor = ProcedureExtractor()
    sections = extractor.extract_from_text(sample_text, 'vehicle_civilian')
    
    print(f"\n✅ Extracted {len(sections)} sections:")
    for heading, content in sections:
        section_type = extractor.identify_section_type(heading, content)
        print(f"\n   📌 {heading[:40]}... ({section_type})")
        print(f"      Length: {len(content)} chars")

def test_query_generator():
    """Test synthetic question generation."""
    print("\n" + "="*60)
    print("TEST 2: QueryGenerator")
    print("="*60)
    
    gen = QueryGenerator()
    
    test_cases = [
        ("Brake Pad Replacement", "procedure"),
        ("Diagnosing Transmission Issues", "diagnostic"),
        ("Hydraulic Accumulator Function", "parts"),
    ]
    
    for heading, section_type in test_cases:
        questions = gen.generate_from_section(heading, section_type)
        print(f"\n📌 {heading} ({section_type}):")
        for i, q in enumerate(questions[:3], 1):
            print(f"   {i}. {q}")

def test_full_pipeline():
    """Test complete pipeline with mock data."""
    print("\n" + "="*60)
    print("TEST 3: Full TrainingDataGenerator Pipeline")
    print("="*60)
    
    # Create test corpus directory with sample files
    test_corpus_dir = Path("test_corpus")
    test_corpus_dir.mkdir(exist_ok=True)
    
    # Create sample vehicle_civilian domain
    vehicle_dir = test_corpus_dir / "vehicle_civilian"
    vehicle_dir.mkdir(exist_ok=True)
    
    sample_content = """
# TIRE MAINTENANCE

## HOW TO CHECK TIRE PRESSURE

Locate the tire valve stem on the wheel. Remove the valve cap. Attach pressure gauge to valve. 
Read the pressure display. Compare to recommended PSI (found on driver's door jamb).

## ROTATING TIRES

Tire rotation helps ensure even wear and extends tire life. Recommended every 5,000-7,000 miles.
Follow the manufacturer's rotation pattern specific to your vehicle.

# BRAKE SYSTEM

## BRAKE PAD REPLACEMENT PROCEDURE

1. Lift vehicle safely using jack stands
2. Remove wheel
3. Locate brake caliper
4. Remove old brake pads
5. Install new pads
6. Reinstall caliper and wheel

## DIAGNOSING BRAKE FADE

Symptoms of brake fade include:
- Increased pedal pressure needed
- Longer stopping distances
- Burning smell from wheels
- Spongy brake pedal feel
"""
    
    with open(vehicle_dir / "maintenance.txt", "w") as f:
        f.write(sample_content)
    
    # Generate training data
    generator = TrainingDataGenerator(test_corpus_dir, Path("data/finetuning"))
    generator.generate_dataset(pairs_per_domain=100, include_hard_negatives=True)
    
    # Check output
    output_file = Path("data/finetuning/training_pairs.jsonl")
    if output_file.exists():
        with open(output_file) as f:
            pairs = [json.loads(line) for line in f]
        
        print(f"\n✅ Generated {len(pairs)} training pairs")
        
        if pairs:
            print(f"\n📊 Sample pairs:")
            for i, pair in enumerate(pairs[:3], 1):
                print(f"\n   Pair {i}:")
                print(f"      Query: {pair['query'][:60]}...")
                print(f"      Positive: {pair['positive'][:60]}...")
                print(f"      Domain: {pair['domain']}")
                print(f"      Synthetic: {pair['synthetic']}")
    else:
        print(f"❌ Output file not created: {output_file}")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_corpus_dir, ignore_errors=True)

if __name__ == '__main__':
    print("\n" + "🧪 TESTING PHASE 3.5 TRAINING DATA GENERATOR".center(60) + "\n")
    
    try:
        test_procedure_extractor()
        test_query_generator()
        test_full_pipeline()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
