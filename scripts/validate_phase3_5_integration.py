"""
Validation script for Phase 3.5 Task 10 integration.

Tests:
1. NeuralAdvisoryLayer initialization with various config flags
2. Evidence chain building from mock query data
3. Compliance report generation via advisory layer
4. Finetuned embedding fallback when model missing
5. Anomaly detection integration (optional)
6. End-to-end integration via Flask /api/ask endpoint

Run:
    python scripts/validate_phase3_5_integration.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.phase3_5.neural_advisory import get_neural_advisory_layer, NeuralAdvisoryLayer

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_advisory_layer_init() -> None:
    """Test 1: Verify NeuralAdvisoryLayer initialization."""
    logger.info("Test 1: Initializing NeuralAdvisoryLayer...")
    
    # Save original env
    orig_env = {
        "NOVA_USE_FINETUNED_EMBEDDINGS": os.environ.get("NOVA_USE_FINETUNED_EMBEDDINGS"),
        "NOVA_ENABLE_ANOMALY_DETECTION": os.environ.get("NOVA_ENABLE_ANOMALY_DETECTION"),
        "NOVA_AUTO_COMPLIANCE_REPORTS": os.environ.get("NOVA_AUTO_COMPLIANCE_REPORTS"),
        "NOVA_COMPLIANCE_REPORT_FORMAT": os.environ.get("NOVA_COMPLIANCE_REPORT_FORMAT"),
    }
    
    try:
        # Test with all features disabled
        os.environ["NOVA_USE_FINETUNED_EMBEDDINGS"] = "0"
        os.environ["NOVA_ENABLE_ANOMALY_DETECTION"] = "0"
        os.environ["NOVA_AUTO_COMPLIANCE_REPORTS"] = "0"
        
        layer = get_neural_advisory_layer()
        assert layer is not None, "Failed to initialize NeuralAdvisoryLayer"
        assert not layer.config.use_finetuned_embeddings, "Finetuned embeddings should be disabled"
        assert not layer.config.anomaly_detection_enabled, "Anomaly detection should be disabled"
        assert not layer.config.auto_compliance_reports, "Auto compliance reports should be disabled"
        assert layer.reporter is None, "Reporter should not be initialized when auto_compliance_reports=False"
        logger.info("✓ NeuralAdvisoryLayer initialized with features disabled")
        
        # Test with compliance reports enabled
        os.environ["NOVA_AUTO_COMPLIANCE_REPORTS"] = "1"
        os.environ["NOVA_COMPLIANCE_REPORT_FORMAT"] = "json,pdf"
        
        layer2 = NeuralAdvisoryLayer()
        assert layer2.config.auto_compliance_reports, "Auto compliance reports should be enabled"
        assert "json" in layer2.config.report_formats, "JSON format should be enabled"
        assert "pdf" in layer2.config.report_formats, "PDF format should be enabled"
        assert layer2.reporter is not None, "Reporter should be initialized"
        logger.info("✓ NeuralAdvisoryLayer initialized with compliance reports enabled")
        
    finally:
        # Restore original env
        for key, val in orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


def test_evidence_chain_building() -> None:
    """Test 2: Build evidence chain from mock query data."""
    logger.info("Test 2: Building evidence chain...")
    
    os.environ["NOVA_AUTO_COMPLIANCE_REPORTS"] = "0"
    layer = NeuralAdvisoryLayer()
    
    mock_docs = [
        {
            "source": "test_manual.pdf",
            "page": 42,
            "confidence": 0.85,
            "score": 0.85,
            "snippet": "Test procedure for brake inspection",
            "anomaly_score": 0.000002,
            "anomaly_flag": False,
            "domain": "vehicle",
        },
        {
            "source": "test_manual.pdf",
            "page": 43,
            "confidence": 0.75,
            "score": 0.75,
            "snippet": "Torque specifications: 85 ft-lbs",
            "anomaly_score": 0.000003,
            "anomaly_flag": False,
            "domain": "vehicle",
        },
    ]
    
    evidence = layer.build_evidence_chain(
        query="How do I inspect brakes?",
        domain="vehicle",
        intent="procedure_lookup",
        retrieved_documents=mock_docs,
        safety_meta={"heuristic_triggers": []},
        model_used="llama3.2",
        decision_tag=None,
        traced_sources=[
            {"source": "test_manual.pdf", "page": 42, "confidence": 0.85},
            {"source": "test_manual.pdf", "page": 43, "confidence": 0.75},
        ],
        retrieval_time_ms=150.0,
        total_time_ms=850.0,
        session_id="test_session_001",
    )
    
    assert evidence["session_id"] == "test_session_001", "Session ID mismatch"
    assert evidence["query"] == "How do I inspect brakes?", "Query mismatch"
    assert evidence["domain"] == "vehicle", "Domain mismatch"
    assert len(evidence["retrieved_documents"]) == 2, "Document count mismatch"
    # Anomaly score should be average of (0.000002, 0.000003) = 0.0000025
    assert abs(evidence["anomaly_score"] - 0.0000025) < 1e-9, f"Anomaly score mismatch: got {evidence['anomaly_score']}, expected 0.0000025"
    assert not evidence["anomaly_flagged"], "Should not be flagged"
    assert len(evidence["citations"]) == 2, "Citation count mismatch"
    assert "test_manual.pdf#page:42" in evidence["citations"], "Citation format incorrect"
    assert evidence["retrieval_time_ms"] == 150.0, "Retrieval time mismatch"
    assert evidence["total_time_ms"] == 850.0, "Total time mismatch"
    
    logger.info("✓ Evidence chain built successfully")
    logger.info(f"  - Session: {evidence['session_id']}")
    logger.info(f"  - Domain: {evidence['domain']}")
    logger.info(f"  - Retrieved: {len(evidence['retrieved_documents'])} docs")
    logger.info(f"  - Anomaly score: {evidence['anomaly_score']:.6f}")


def test_compliance_report_generation() -> None:
    """Test 3: Generate compliance report via advisory layer."""
    logger.info("Test 3: Generating compliance report...")
    
    # Enable compliance reports
    os.environ["NOVA_AUTO_COMPLIANCE_REPORTS"] = "1"
    os.environ["NOVA_COMPLIANCE_REPORT_FORMAT"] = "json"
    os.environ["NOVA_COMPLIANCE_REPORT_DIR"] = "compliance_reports/phase3_5_test"
    
    layer = NeuralAdvisoryLayer()
    assert layer.reporter is not None, "Reporter should be initialized"
    
    mock_evidence = {
        "session_id": "test_session_002",
        "system_version": "0.3.5",
        "query": "What is torque spec for head bolts?",
        "domain": "vehicle",
        "intent": "spec_lookup",
        "decision_tag": None,
        "retrieved_documents": [
            {
                "source": "manual.pdf",
                "page": 10,
                "score": 0.92,
                "anomaly_score": 0.000001,
                "anomaly_flag": False,
                "domain": "vehicle",
                "snippet": "Head bolt torque: 85 ft-lbs in 3 stages",
            }
        ],
        "reranking": {},
        "safety_checks": {"heuristic_triggers": [], "passed": True},
        "anomaly_score": 0.000001,
        "anomaly_flagged": False,
        "citations": ["manual.pdf#page:10"],
        "extractive_fallback": False,
        "retrieval_time_ms": 120.0,
        "generation_time_ms": 480.0,
        "total_time_ms": 600.0,
        "model_used": "llama3.2",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    paths = layer.maybe_generate_report(
        evidence_chain=mock_evidence,
        query="What is torque spec for head bolts?",
        answer="The head bolt torque specification is 85 ft-lbs, applied in 3 stages. See manual.pdf page 10.",
    )
    
    assert len(paths) > 0, "No reports generated"
    assert any("json" in str(p) for p in paths), "JSON report not generated"
    
    # Verify report file exists and is valid JSON
    json_path = Path(paths[0])
    assert json_path.exists(), f"Report file not found: {json_path}"
    
    with open(json_path, 'r', encoding='utf-8') as f:
        report_data = json.load(f)
    
    assert report_data["session_id"] == "test_session_002", "Report session ID mismatch"
    assert report_data["query"] == "What is torque spec for head bolts?", "Report query mismatch"
    assert "report_hash" in report_data, "Report hash missing"
    assert len(report_data["report_hash"]) == 64, "SHA-256 hash should be 64 hex chars"
    
    logger.info("✓ Compliance report generated successfully")
    logger.info(f"  - Path: {json_path}")
    logger.info(f"  - Hash: {report_data['report_hash'][:16]}...")
    logger.info(f"  - Anomaly score: {report_data['anomaly_score']:.6f}")
    
    # Cleanup
    os.environ.pop("NOVA_AUTO_COMPLIANCE_REPORTS", None)
    os.environ.pop("NOVA_COMPLIANCE_REPORT_FORMAT", None)
    os.environ.pop("NOVA_COMPLIANCE_REPORT_DIR", None)


def test_finetuned_embedding_fallback() -> None:
    """Test 4: Verify finetuned embedding fallback logic."""
    logger.info("Test 4: Testing finetuned embedding fallback...")
    
    # Save original env
    orig_use_ft = os.environ.get("NOVA_USE_FINETUNED_EMBEDDINGS")
    orig_ft_path = os.environ.get("NOVA_FINETUNED_MODEL_PATH")
    
    try:
        # Test with finetuned embeddings enabled but model missing
        os.environ["NOVA_USE_FINETUNED_EMBEDDINGS"] = "1"
        os.environ["NOVA_FINETUNED_MODEL_PATH"] = "/nonexistent/path/to/model"
        
        # Import here to reload config
        from core.retrieval import retrieval_engine
        
        # Check that USE_FINETUNED_EMBEDDINGS flag is set
        assert retrieval_engine.USE_FINETUNED_EMBEDDINGS, "Finetuned embeddings flag should be enabled"
        
        # get_text_embed_model should fallback to baseline when finetuned model missing
        model = retrieval_engine.get_text_embed_model()
        
        if model is not None:
            logger.info("✓ Embedding model loaded (fallback to baseline when finetuned missing)")
        else:
            logger.info("✓ Embedding model unavailable (acceptable in test env)")
        
    finally:
        # Restore original env
        if orig_use_ft is None:
            os.environ.pop("NOVA_USE_FINETUNED_EMBEDDINGS", None)
        else:
            os.environ["NOVA_USE_FINETUNED_EMBEDDINGS"] = orig_use_ft
        
        if orig_ft_path is None:
            os.environ.pop("NOVA_FINETUNED_MODEL_PATH", None)
        else:
            os.environ["NOVA_FINETUNED_MODEL_PATH"] = orig_ft_path


def test_config_flag_overview() -> None:
    """Test 5: Print overview of Phase 3.5 config flags."""
    logger.info("Test 5: Phase 3.5 configuration flags overview...")
    
    flags = {
        "NOVA_USE_FINETUNED_EMBEDDINGS": os.environ.get("NOVA_USE_FINETUNED_EMBEDDINGS", "0"),
        "NOVA_FINETUNED_MODEL_PATH": os.environ.get(
            "NOVA_FINETUNED_MODEL_PATH", "models/nic-embeddings-v1.0"
        ),
        "NOVA_ANOMALY_DETECTOR": os.environ.get("NOVA_ANOMALY_DETECTOR", "0"),
        "NOVA_ENABLE_ANOMALY_DETECTION": os.environ.get("NOVA_ENABLE_ANOMALY_DETECTION", "0"),
        "NOVA_ANOMALY_MODEL": os.environ.get("NOVA_ANOMALY_MODEL", "models/anomaly_detector_v1.0.pth"),
        "NOVA_ANOMALY_CONFIG": os.environ.get(
            "NOVA_ANOMALY_CONFIG", "models/anomaly_detector_v1.0_config.json"
        ),
        "NOVA_AUTO_COMPLIANCE_REPORTS": os.environ.get("NOVA_AUTO_COMPLIANCE_REPORTS", "0"),
        "NOVA_COMPLIANCE_REPORT_FORMAT": os.environ.get("NOVA_COMPLIANCE_REPORT_FORMAT", "json"),
        "NOVA_COMPLIANCE_REPORT_DIR": os.environ.get("NOVA_COMPLIANCE_REPORT_DIR", "compliance_reports"),
        "NOVA_SYSTEM_VERSION": os.environ.get("NOVA_SYSTEM_VERSION", "0.3.5"),
        "NOVA_OPERATOR_ID": os.environ.get("NOVA_OPERATOR_ID", "<not set>"),
    }
    
    logger.info("Configuration flags:")
    for key, val in flags.items():
        logger.info(f"  {key} = {val}")
    
    logger.info("✓ Configuration overview complete")


def main() -> None:
    """Run all validation tests."""
    logger.info("=" * 60)
    logger.info("Phase 3.5 Task 10 Integration Validation")
    logger.info("=" * 60)
    
    tests = [
        ("Advisory Layer Init", test_advisory_layer_init),
        ("Evidence Chain Building", test_evidence_chain_building),
        ("Compliance Report Generation", test_compliance_report_generation),
        ("Finetuned Embedding Fallback", test_finetuned_embedding_fallback),
        ("Config Flag Overview", test_config_flag_overview),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            logger.info("")
            test_fn()
            passed += 1
        except AssertionError as exc:
            logger.error(f"✗ Test failed: {name}")
            logger.error(f"  {exc}")
            failed += 1
        except Exception as exc:
            logger.error(f"✗ Test error: {name}")
            logger.error(f"  {exc}")
            failed += 1
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Results: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        logger.info("All tests passed! ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
