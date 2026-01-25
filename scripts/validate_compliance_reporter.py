"""
Validation script for Phase 3.5 Task 9: Compliance Reporter.

Tests:
1. JSON report generation
2. PDF report generation
3. Tamper detection
4. Batch reporting
5. Performance benchmarks
"""

import json
import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.compliance.report_generator import ComplianceReport, ComplianceReporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def create_sample_evidence_chain(session_id: str) -> dict:
    """Create a sample evidence chain for testing."""
    return {
        'session_id': session_id,
        'system_version': '1.0.0',
        'query': 'How to replace brake pads on a forklift?',
        'domain': 'forklift',
        'intent': 'procedure',
        'retrieved_documents': [
            {
                'source': 'forklift_maintenance_manual.pdf',
                'score': 0.92,
                'chunk_id': 'chunk_123',
            },
            {
                'source': 'brake_system_guide.pdf',
                'score': 0.87,
                'chunk_id': 'chunk_456',
            },
        ],
        'reranking': {
            'method': 'semantic',
            'scores_improved': True,
        },
        'safety_checks': {
            'passed': True,
            'injection_detected': False,
            'toxic_content': False,
        },
        'anomaly_score': 0.000003,
        'anomaly_flagged': False,
        'answer': (
            "To replace brake pads on a forklift:\n\n"
            "1. Park on level ground and engage parking brake\n"
            "2. Remove wheel and tire assembly\n"
            "3. Clean brake assembly\n"
            "4. Remove retaining clips and old brake pads\n"
            "5. Install new brake pads with anti-squeal compound\n"
            "6. Reinstall components and test brake function\n\n"
            "Always refer to the manufacturer's service manual for specific torque specifications."
        ),
        'citations': [
            'forklift_maintenance_manual.pdf (Section 5.2)',
            'brake_system_guide.pdf (Page 42)',
        ],
        'extractive_fallback': False,
        'retrieval_time_ms': 45.3,
        'generation_time_ms': 123.7,
        'total_time_ms': 169.0,
        'operator': 'test_operator',
    }


def test_json_generation(reporter: ComplianceReporter) -> None:
    """Test JSON report generation."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 1: JSON Report Generation")
    logger.info("=" * 70)
    
    evidence = create_sample_evidence_chain("test_session_001")
    
    # Generate report
    start_time = time.time()
    report = reporter.generate_report(
        session_id=evidence['session_id'],
        query=evidence['query'],
        answer=evidence['answer'],
        evidence_chain=evidence,
        operator=evidence['operator'],
    )
    
    # Save JSON
    json_path = reporter.save_json(report, "test_report_001.json")
    elapsed = time.time() - start_time
    
    logger.info(f"✓ Report generated in {elapsed:.3f}s")
    logger.info(f"✓ Session ID: {report.session_id}")
    logger.info(f"✓ Hash: {report.report_hash}")
    logger.info(f"✓ Saved to: {json_path}")
    
    # Verify file exists
    assert json_path.exists(), "JSON file not created"
    
    # Verify content
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    assert data['session_id'] == 'test_session_001'
    assert data['query'] == evidence['query']
    assert len(data['report_hash']) == 64  # SHA-256 hex length
    
    logger.info("✓ JSON generation test PASSED")


def test_pdf_generation(reporter: ComplianceReporter) -> None:
    """Test PDF report generation."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 2: PDF Report Generation")
    logger.info("=" * 70)
    
    evidence = create_sample_evidence_chain("test_session_002")
    
    try:
        # Generate report
        start_time = time.time()
        report = reporter.generate_report(
            session_id=evidence['session_id'],
            query=evidence['query'],
            answer=evidence['answer'],
            evidence_chain=evidence,
        )
        
        # Save PDF
        pdf_path = reporter.save_pdf(report, "test_report_002.pdf")
        elapsed = time.time() - start_time
        
        logger.info(f"✓ PDF generated in {elapsed:.3f}s")
        logger.info(f"✓ Saved to: {pdf_path}")
        
        # Verify file exists and has content
        assert pdf_path.exists(), "PDF file not created"
        file_size = pdf_path.stat().st_size
        assert file_size > 1000, "PDF file too small"
        
        logger.info(f"✓ File size: {file_size / 1024:.1f} KB")
        logger.info("✓ PDF generation test PASSED")
        
        # Performance check
        if elapsed > 2.0:
            logger.warning(f"⚠ PDF generation took {elapsed:.3f}s (target: < 2s)")
        
    except ImportError as e:
        logger.warning(f"⚠ PDF generation skipped: {e}")
        logger.info("  Install reportlab: pip install reportlab")


def test_tamper_detection(reporter: ComplianceReporter) -> None:
    """Test tamper detection via hash verification."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 3: Tamper Detection")
    logger.info("=" * 70)
    
    evidence = create_sample_evidence_chain("test_session_003")
    
    # Generate and save report
    report = reporter.generate_report(
        session_id=evidence['session_id'],
        query=evidence['query'],
        answer=evidence['answer'],
        evidence_chain=evidence,
    )
    
    json_path = reporter.save_json(report, "test_report_003.json")
    
    # Verify original (should pass)
    is_valid = reporter.verify_json(json_path)
    assert is_valid, "Original report should be valid"
    logger.info("✓ Original report verification PASSED")
    
    # Tamper with report
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    original_query = data['query']
    data['query'] = "TAMPERED QUERY"
    
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Verify tampered (should fail)
    is_valid_after_tamper = reporter.verify_json(json_path)
    assert not is_valid_after_tamper, "Tampered report should be invalid"
    logger.info("✓ Tamper detection PASSED (tampered report detected)")
    
    # Restore original
    data['query'] = original_query
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Verify restored (should pass)
    is_valid_restored = reporter.verify_json(json_path)
    assert is_valid_restored, "Restored report should be valid"
    logger.info("✓ Restored report verification PASSED")


def test_batch_generation(reporter: ComplianceReporter) -> None:
    """Test batch report generation."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 4: Batch Report Generation")
    logger.info("=" * 70)
    
    # Create multiple evidence chains
    evidence_chains = []
    for i in range(10):
        evidence = create_sample_evidence_chain(f"batch_session_{i:03d}")
        evidence['query'] = f"Test query {i + 1}"
        evidence['anomaly_score'] = 0.000001 * (i + 1)
        evidence_chains.append(evidence)
    
    # Generate batch
    start_time = time.time()
    paths = reporter.batch_generate(evidence_chains, output_format="json")
    elapsed = time.time() - start_time
    
    logger.info(f"✓ Generated {len(paths)} reports in {elapsed:.3f}s")
    logger.info(f"✓ Average: {elapsed / len(paths) * 1000:.1f} ms per report")
    
    assert len(paths) == 10, "Should generate 10 reports"
    
    # Verify all exist
    for path in paths:
        assert path.exists(), f"Report {path} not found"
    
    logger.info("✓ Batch generation test PASSED")


def test_aggregate_stats(reporter: ComplianceReporter) -> None:
    """Test aggregate statistics generation."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 5: Aggregate Statistics")
    logger.info("=" * 70)
    
    # Create reports with varying data
    reports = []
    domains = ['forklift', 'vehicle', 'radar', 'hvac']
    
    for i in range(20):
        evidence = create_sample_evidence_chain(f"stats_session_{i:03d}")
        evidence['domain'] = domains[i % len(domains)]
        evidence['anomaly_score'] = 0.000001 * (i + 1)
        evidence['anomaly_flagged'] = (i % 5 == 0)  # 20% flagged
        
        report = reporter.generate_report(
            session_id=evidence['session_id'],
            query=evidence['query'],
            answer=evidence['answer'],
            evidence_chain=evidence,
        )
        reports.append(report)
    
    # Generate stats
    stats = reporter.generate_aggregate_stats(reports)
    
    logger.info(f"\nAggregate Statistics:")
    logger.info(f"  Total queries: {stats['total_queries']}")
    logger.info(f"  Domain distribution: {stats['domains']}")
    logger.info(f"  Anomalies flagged: {stats['anomaly_detection']['total_flagged']} " +
                f"({stats['anomaly_detection']['flagged_percentage']:.1f}%)")
    logger.info(f"  Avg anomaly score: {stats['anomaly_detection']['avg_score']:.6f}")
    logger.info(f"  Avg confidence: {stats['confidence']['avg']:.3f}")
    logger.info(f"  Avg retrieval time: {stats['performance']['avg_retrieval_ms']:.1f} ms")
    
    # Verify stats
    assert stats['total_queries'] == 20
    assert stats['anomaly_detection']['total_flagged'] == 4  # 20% of 20
    assert len(stats['domains']) == 4
    
    logger.info("\n✓ Aggregate statistics test PASSED")


def test_performance_benchmark(reporter: ComplianceReporter) -> None:
    """Performance benchmark for report generation."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 6: Performance Benchmark")
    logger.info("=" * 70)
    
    num_reports = 100
    evidence_chains = []
    
    for i in range(num_reports):
        evidence = create_sample_evidence_chain(f"perf_session_{i:04d}")
        evidence_chains.append(evidence)
    
    # Benchmark JSON generation
    start_time = time.time()
    for evidence in evidence_chains:
        report = reporter.generate_report(
            session_id=evidence['session_id'],
            query=evidence['query'],
            answer=evidence['answer'],
            evidence_chain=evidence,
        )
    elapsed = time.time() - start_time
    
    avg_time_ms = (elapsed / num_reports) * 1000
    
    logger.info(f"\nJSON Generation Benchmark:")
    logger.info(f"  Total reports: {num_reports}")
    logger.info(f"  Total time: {elapsed:.2f}s")
    logger.info(f"  Average: {avg_time_ms:.2f} ms per report")
    logger.info(f"  Throughput: {num_reports / elapsed:.1f} reports/second")
    
    # Performance targets
    if avg_time_ms < 50:
        logger.info(f"✓ EXCELLENT performance (< 50ms)")
    elif avg_time_ms < 100:
        logger.info(f"✓ GOOD performance (< 100ms)")
    elif avg_time_ms < 200:
        logger.info(f"✓ ACCEPTABLE performance (< 200ms)")
    else:
        logger.warning(f"⚠ SLOW performance (> 200ms)")
    
    logger.info("✓ Performance benchmark complete")


def main():
    """Run all validation tests."""
    logger.info("=" * 70)
    logger.info("Phase 3.5 Task 9: Compliance Reporter Validation")
    logger.info("=" * 70)
    
    # Create reporter
    reporter = ComplianceReporter(output_dir="compliance_reports/test")
    
    try:
        # Run tests
        test_json_generation(reporter)
        test_pdf_generation(reporter)
        test_tamper_detection(reporter)
        test_batch_generation(reporter)
        test_aggregate_stats(reporter)
        test_performance_benchmark(reporter)
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("✓ VALIDATION PASSED")
        logger.info("=" * 70)
        logger.info("\nAll tests completed successfully!")
        logger.info(f"Reports saved to: {reporter.output_dir}")
        logger.info("\nKey Results:")
        logger.info("  ✓ JSON generation working")
        logger.info("  ✓ PDF generation working (if reportlab installed)")
        logger.info("  ✓ Tamper detection working")
        logger.info("  ✓ Batch generation working")
        logger.info("  ✓ Aggregate statistics working")
        logger.info("  ✓ Performance benchmarks complete")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"\n✗ VALIDATION FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
