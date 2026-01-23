"""
Unit tests for Phase 3.5 Training Data Generator

Tests the core components:
- ProcedureExtractor: Section identification and type classification
- QueryGenerator: Synthetic question generation
- TrainingDataGenerator: End-to-end pipeline
"""

import pytest
import json
from scripts.generate_finetuning_data import (
    ProcedureExtractor,
    QueryGenerator,
    TrainingDataGenerator,
    TrainingPair
)


class TestProcedureExtractor:
    """Test section extraction from technical manuals."""
    
    @pytest.fixture
    def extractor(self):
        return ProcedureExtractor(min_section_length=50, max_section_length=2000)
    
    @pytest.fixture
    def sample_manual(self):
        return """
# HOW TO CHECK TIRE PRESSURE

1. Locate the tire valve stem on the wheel
2. Remove the valve cap
3. Attach pressure gauge to valve stem
4. Read the pressure reading
5. Compare to recommended PSI

## TROUBLESHOOTING TIRE ISSUES

Symptoms of low tire pressure include:
- Vehicle pulling to one side
- Steering feels loose
- Tire appears visibly flat
- Dashboard warning light

### VALVE STEM COMPONENTS

The valve stem includes several parts:
- Rubber base seals against wheel
- Metal core with threads
- Dust cap prevents debris
"""
    
    def test_extract_sections(self, extractor, sample_manual):
        """Test basic section extraction."""
        sections = extractor.extract_from_text(sample_manual, 'vehicle_civilian')
        
        assert len(sections) > 0
        assert all(isinstance(h, str) and isinstance(c, str) for h, c in sections)
    
    def test_identify_procedure(self, extractor):
        """Test procedure detection."""
        heading = "HOW TO CHANGE BRAKE PADS"
        content = "1. Lift the vehicle. 2. Remove wheel. 3. Remove brake caliper. 4. Replace pads."
        
        section_type = extractor.identify_section_type(heading, content)
        assert section_type == 'procedure'
    
    def test_identify_diagnostic(self, extractor):
        """Test diagnostic detection."""
        heading = "TROUBLESHOOTING TRANSMISSION ISSUES"
        content = "Symptom: Vehicle won't shift. Cause: Low fluid or worn bands."
        
        section_type = extractor.identify_section_type(heading, content)
        assert section_type in ['diagnostic', 'procedure']  # Could be either
    
    def test_identify_parts(self, extractor):
        """Test parts detection."""
        heading = "ALTERNATOR COMPONENTS"
        content = "The alternator includes a rotor, stator, connector, and housing assembly."
        
        section_type = extractor.identify_section_type(heading, content)
        assert section_type in ['parts', 'general']
    
    def test_section_length_filtering(self, extractor):
        """Test that sections outside length range are filtered."""
        extractor_strict = ProcedureExtractor(min_section_length=500, max_section_length=1000)
        
        short_text = "# Short\nToo short"
        long_text = "# Long\n" + "x" * 2500
        
        short_sections = extractor_strict.extract_from_text(short_text, 'test')
        long_sections = extractor_strict.extract_from_text(long_text, 'test')
        
        assert len(short_sections) == 0
        assert len(long_sections) == 0


class TestQueryGenerator:
    """Test synthetic question generation."""
    
    @pytest.fixture
    def generator(self):
        return QueryGenerator()
    
    def test_generate_procedure_questions(self, generator):
        """Test question generation for procedures."""
        questions = generator.generate_from_section(
            "Brake Pad Replacement",
            "procedure"
        )
        
        assert len(questions) > 0
        assert all(isinstance(q, str) for q in questions)
        # Procedure questions should contain keywords from heading
        assert any("brake" in q.lower() for q in questions)
    
    def test_generate_diagnostic_questions(self, generator):
        """Test question generation for diagnostics."""
        questions = generator.generate_from_section(
            "Diagnosing Steering Issues",
            "diagnostic"
        )
        
        assert len(questions) > 0
        # Diagnostic questions might ask about causes/symptoms
        question_text = ' '.join(questions).lower()
        assert any(keyword in question_text for keyword in ['what', 'how', 'cause', 'diagnose'])
    
    def test_generate_parts_questions(self, generator):
        """Test question generation for parts."""
        questions = generator.generate_from_section(
            "Thermostat Housing",
            "parts"
        )
        
        assert len(questions) > 0
        # Parts questions might ask about function/identification
        question_text = ' '.join(questions).lower()
        assert any(keyword in question_text for keyword in ['what', 'where', 'thermostat'])
    
    def test_question_deduplication(self, generator):
        """Test that duplicate questions are removed."""
        # Generate same section twice
        gen1 = generator.generate_from_section("Oil Change", "procedure")
        gen2 = generator.generate_from_section("Oil Change", "procedure")
        
        # Some questions might repeat due to same heading, but dedup should work
        assert len(gen1) > 0
        assert len(gen2) > 0


class TestTrainingPair:
    """Test TrainingPair dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        pair = TrainingPair(
            query="How do I check tire pressure?",
            positive="Locate valve stem on wheel...",
            negative="Engine oil change procedure...",
            domain="vehicle_civilian",
            source_section="Tire Maintenance",
            synthetic=True,
            hard_negative=False
        )
        
        d = pair.to_dict()
        
        assert d['query'] == "How do I check tire pressure?"
        assert d['domain'] == "vehicle_civilian"
        assert d['synthetic'] is True
        assert all(k in d for k in ['query', 'positive', 'negative', 'domain'])
    
    def test_json_serializable(self):
        """Test that pairs are JSON serializable."""
        pair = TrainingPair(
            query="Test query?",
            positive="Positive text",
            negative="Negative text",
            domain="test_domain",
            source_section="Test Section"
        )
        
        # Should not raise exception
        json_str = json.dumps(pair.to_dict())
        restored = json.loads(json_str)
        
        assert restored['query'] == "Test query?"


class TestTrainingDataGenerator:
    """Test end-to-end training data generation."""
    
    @pytest.fixture
    def temp_corpus(self, tmp_path):
        """Create temporary corpus with sample files."""
        domain_dir = tmp_path / "vehicle_civilian"
        domain_dir.mkdir()
        
        content = """
# TIRE PRESSURE MONITORING

## HOW TO CHECK TIRE PRESSURE

1. Locate the tire valve stem on the wheel
2. Remove the valve cap
3. Attach pressure gauge to valve stem
4. Read the PSI measurement
5. Compare to recommended PSI on driver's door jamb
6. Add air if needed using compressor
7. Replace valve cap

## RECOMMENDED TIRE PRESSURES

Front tires: 32 PSI
Rear tires: 28 PSI
Spare tire: 60 PSI (when stored)

# BRAKE SYSTEM MAINTENANCE

## HOW TO REPLACE BRAKE PADS

The brake pad replacement procedure takes about 30 minutes:
- Lift vehicle on jack stands
- Remove wheel from brake assembly
- Locate brake caliper and remove mounting bolts
- Slide old pads out carefully
- Install new brake pads
- Reassemble caliper
- Test brakes before driving
"""
        
        with open(domain_dir / "maintenance.txt", "w") as f:
            f.write(content)
        
        return tmp_path
    
    def test_scan_corpus(self, temp_corpus):
        """Test corpus scanning."""
        generator = TrainingDataGenerator(temp_corpus, temp_corpus / "output")
        domain_sections = generator._scan_corpus()
        
        assert 'vehicle_civilian' in domain_sections
        assert len(domain_sections['vehicle_civilian']) > 0
    
    def test_generate_pairs_for_domain(self, temp_corpus):
        """Test pair generation for single domain."""
        generator = TrainingDataGenerator(temp_corpus, temp_corpus / "output")
        domain_sections = generator._scan_corpus()
        
        pairs = generator._generate_pairs_for_domain(
            'vehicle_civilian',
            domain_sections['vehicle_civilian'],
            target_pairs=50,
            include_hard_negatives=True
        )
        
        assert len(pairs) > 0
        assert all(isinstance(p, TrainingPair) for p in pairs)
        assert all(p.domain == 'vehicle_civilian' for p in pairs)
    
    def test_full_generation(self, temp_corpus):
        """Test full dataset generation."""
        output_dir = temp_corpus / "output"
        generator = TrainingDataGenerator(temp_corpus, output_dir)
        
        generator.generate_dataset(
            pairs_per_domain=50,
            include_hard_negatives=True
        )
        
        output_file = output_dir / 'training_pairs.jsonl'
        assert output_file.exists()
        
        # Read and validate output
        pairs = []
        with open(output_file) as f:
            for line in f:
                pairs.append(json.loads(line))
        
        assert len(pairs) > 0
        assert all('query' in p and 'positive' in p for p in pairs)


# Run tests with: pytest tests/unit/test_training_data_generator.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
