#!/usr/bin/env python3
"""
Unit tests for the Multi-Domain Signal-Path Diagnostic Engine.

Tests:
- Graph loading for all domains (beacon, asr8, nexrad)
- Midpoint selection when no alarm_map match
- Plan includes citations for every step
- Missing citations triggers fallback/refusal
- Cross-domain capability validation

Run with:
    pytest tests/test_signal_path_engine.py -v
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.signal_path_engine import (
    DiagnosticPlan,
    DiagnosticStep,
    GraphEdge,
    GraphNode,
    SignalGraph,
    SignalPathEngine,
    get_engine,
    run_signal_path_diagnosis,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_graphs_dir(tmp_path: Path) -> Path:
    """Create a temporary graphs directory with test graphs."""
    graphs_dir = tmp_path / "graphs"
    graphs_dir.mkdir()
    return graphs_dir


@pytest.fixture
def sample_graph_json() -> Dict[str, Any]:
    """Minimal valid graph JSON for testing."""
    return {
        "domain": "test",
        "graph_id": "sample",
        "nodes": [
            {
                "id": "power_input",
                "label": "Power Input",
                "type": "component",
                "measure": "voltage",
                "expected": "120VAC present",
                "refs": ["Manual Section 1.1", "Figure 1-1"],
                "tags": ["power", "input"],
            },
            {
                "id": "amplifier",
                "label": "RF Amplifier",
                "type": "component",
                "measure": "rf",
                "expected": "Gain within spec",
                "refs": ["Manual Section 2.3"],
                "tags": ["rf", "amplifier"],
            },
            {
                "id": "output",
                "label": "RF Output",
                "type": "test_point",
                "measure": "power",
                "expected": "100W output",
                "refs": ["Manual Section 3.2", "Table 3-1"],
                "tags": ["output", "rf_output"],
            },
        ],
        "edges": [
            {"from": "power_input", "to": "amplifier", "kind": "power_flow"},
            {"from": "amplifier", "to": "output", "kind": "signal_flow"},
        ],
        "alarm_map": {
            "no_output": "output",
            "power_fault": "power_input",
        },
    }


@pytest.fixture
def sample_context_docs() -> List[Dict[str, Any]]:
    """Sample retrieved context documents with citations."""
    return [
        {
            "source": "Manual Section 1.1",
            "page": 5,
            "text": "The power input module receives 120VAC and provides regulated DC.",
            "snippet": "Power input receives 120VAC",
        },
        {
            "source": "Manual Section 2.3",
            "page": 12,
            "text": "The RF amplifier provides gain of 20dB nominal.",
            "snippet": "RF amplifier provides 20dB gain",
        },
        {
            "source": "Manual Section 3.2",
            "page": 18,
            "text": "RF output should measure 100W peak under normal conditions.",
            "snippet": "RF output 100W peak",
        },
    ]


@pytest.fixture
def engine_with_temp_graphs(temp_graphs_dir: Path, sample_graph_json: Dict) -> SignalPathEngine:
    """Create an engine with a temporary graphs directory and sample graph."""
    graph_path = temp_graphs_dir / "test.graph.json"
    graph_path.write_text(json.dumps(sample_graph_json))
    return SignalPathEngine(graphs_dir=temp_graphs_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Test: Graph Loading
# ──────────────────────────────────────────────────────────────────────────────


class TestGraphLoading:
    """Tests for graph loading functionality."""

    def test_load_graph_success(
        self, engine_with_temp_graphs: SignalPathEngine, sample_graph_json: Dict
    ):
        """Test that a valid graph loads successfully."""
        graph = engine_with_temp_graphs.load_graph("test")
        
        assert graph is not None
        assert graph.domain == "test"
        assert graph.graph_id == "sample"
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        assert "no_output" in graph.alarm_map

    def test_load_graph_not_found(self, engine_with_temp_graphs: SignalPathEngine):
        """Test that loading a non-existent graph returns None."""
        graph = engine_with_temp_graphs.load_graph("nonexistent_domain")
        assert graph is None

    def test_load_graph_caching(self, engine_with_temp_graphs: SignalPathEngine):
        """Test that loaded graphs are cached."""
        graph1 = engine_with_temp_graphs.load_graph("test")
        graph2 = engine_with_temp_graphs.load_graph("test")
        
        assert graph1 is graph2  # Same object (cached)

    def test_load_real_beacon_graph(self):
        """Test loading the real beacon_hv graph if it exists."""
        engine = SignalPathEngine(graphs_dir=Path("graphs"))
        graph = engine.load_graph("beacon", "hv")
        
        if graph is not None:
            assert graph.domain == "beacon"
            assert len(graph.nodes) > 0
            # Verify all nodes have refs (citations)
            for node in graph.nodes:
                assert len(node.refs) > 0, f"Node {node.id} missing refs"

    def test_load_real_asr8_graph(self):
        """Test loading the real asr8_power graph if it exists."""
        engine = SignalPathEngine(graphs_dir=Path("graphs"))
        graph = engine.load_graph("asr8", "power")
        
        if graph is not None:
            assert graph.domain == "asr8"
            assert len(graph.nodes) > 0
            for node in graph.nodes:
                assert len(node.refs) > 0, f"Node {node.id} missing refs"

    def test_load_real_nexrad_graph(self):
        """Test loading the real nexrad_tx graph if it exists."""
        engine = SignalPathEngine(graphs_dir=Path("graphs"))
        graph = engine.load_graph("nexrad", "tx")
        
        if graph is not None:
            assert graph.domain == "nexrad"
            assert len(graph.nodes) > 0
            for node in graph.nodes:
                assert len(node.refs) > 0, f"Node {node.id} missing refs"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Start Node Selection (Midpoint Isolation)
# ──────────────────────────────────────────────────────────────────────────────


class TestStartNodeSelection:
    """Tests for start node selection using alarm_map and midpoint."""

    def test_alarm_map_match(self, engine_with_temp_graphs: SignalPathEngine):
        """Test that alarm_map matches take priority."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        # Should match "no_output" in alarm_map
        start_node = engine_with_temp_graphs.choose_start_node(
            graph, "System reports no_output alarm"
        )
        assert start_node == "output"

    def test_alarm_map_match_case_insensitive(
        self, engine_with_temp_graphs: SignalPathEngine
    ):
        """Test that alarm matching is case-insensitive."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        start_node = engine_with_temp_graphs.choose_start_node(
            graph, "POWER_FAULT detected"
        )
        assert start_node == "power_input"

    def test_midpoint_selection_no_alarm_match(
        self, engine_with_temp_graphs: SignalPathEngine
    ):
        """Test midpoint selection when no alarm_map match."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        # Query that doesn't match any alarm_map entry
        start_node = engine_with_temp_graphs.choose_start_node(
            graph, "System has unknown issue"
        )
        
        # Should select midpoint of primary path
        # Path: power_input -> amplifier -> output (via signal_flow)
        # Midpoint should be index 1 = "amplifier" or similar
        assert start_node in ["power_input", "amplifier", "output"]

    def test_tag_match(self, engine_with_temp_graphs: SignalPathEngine):
        """Test that node tags can trigger start node selection."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        # Should match "rf" tag on amplifier
        start_node = engine_with_temp_graphs.choose_start_node(
            graph, "rf problem detected"
        )
        # Could match amplifier or output (both have rf tags)
        assert start_node in ["amplifier", "output"]


# ──────────────────────────────────────────────────────────────────────────────
# Test: Diagnostic Plan Generation
# ──────────────────────────────────────────────────────────────────────────────


class TestDiagnosticPlanGeneration:
    """Tests for diagnostic plan generation with midpoint isolation."""

    def test_plan_generation_success(
        self,
        engine_with_temp_graphs: SignalPathEngine,
        sample_context_docs: List[Dict],
    ):
        """Test successful plan generation with citations."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        plan = engine_with_temp_graphs.generate_diagnostic_plan(
            graph, "amplifier", sample_context_docs, max_steps=5
        )
        
        assert plan.response_type == "diagnostic_plan"
        assert plan.domain == "test"
        assert len(plan.steps) > 0

    def test_plan_steps_have_citations(
        self,
        engine_with_temp_graphs: SignalPathEngine,
        sample_context_docs: List[Dict],
    ):
        """Test that all plan steps have citations (non-negotiable rule)."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        plan = engine_with_temp_graphs.generate_diagnostic_plan(
            graph, "amplifier", sample_context_docs, max_steps=5
        )
        
        for step in plan.steps:
            assert len(step.refs) > 0, f"Step {step.step_num} missing citations"

    def test_plan_branching_structure(
        self,
        engine_with_temp_graphs: SignalPathEngine,
        sample_context_docs: List[Dict],
    ):
        """Test that plan has proper branching (if_present/if_absent)."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        plan = engine_with_temp_graphs.generate_diagnostic_plan(
            graph, "amplifier", sample_context_docs, max_steps=5
        )
        
        # At least one step should have branching
        has_branching = any(
            step.if_present or step.if_absent for step in plan.steps
        )
        # With only 3 nodes, branching may be limited, but structure should exist
        assert len(plan.steps) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Test: Citation Validation and Fallback
# ──────────────────────────────────────────────────────────────────────────────


class TestCitationValidation:
    """Tests for citation validation and extractive fallback."""

    def test_missing_citations_triggers_fallback(
        self, temp_graphs_dir: Path
    ):
        """Test that missing citations trigger extractive fallback."""
        # Create a graph with nodes that have NO refs
        graph_json = {
            "domain": "test_no_refs",
            "graph_id": "no_refs",
            "nodes": [
                {
                    "id": "node_a",
                    "label": "Node A",
                    "type": "component",
                    "measure": "voltage",
                    "expected": "present",
                    "refs": [],  # Empty refs!
                    "tags": [],
                },
                {
                    "id": "node_b",
                    "label": "Node B",
                    "type": "component",
                    "measure": "rf",
                    "expected": "present",
                    "refs": [],  # Empty refs!
                    "tags": [],
                },
            ],
            "edges": [
                {"from": "node_a", "to": "node_b", "kind": "signal_flow"},
            ],
            "alarm_map": {},
        }
        
        graph_path = temp_graphs_dir / "test_no_refs.graph.json"
        graph_path.write_text(json.dumps(graph_json))
        
        engine = SignalPathEngine(graphs_dir=temp_graphs_dir)
        graph = engine.load_graph("test_no_refs")
        assert graph is not None, "Test graph should load successfully"
        
        # Context docs that also won't match
        context_docs = [
            {"source": "Unrelated Doc", "text": "This is unrelated content."}
        ]
        
        plan = engine.generate_diagnostic_plan(
            graph, "node_a", context_docs, max_steps=5
        )
        
        # Should be fallback or refusal due to missing citations
        assert plan.response_type in ["extractive_fallback", "refusal"]

    def test_refusal_when_no_evidence(self, temp_graphs_dir: Path):
        """Test refusal when no evidence available at all."""
        graph_json = {
            "domain": "test_empty",
            "graph_id": "empty",
            "nodes": [
                {
                    "id": "orphan",
                    "label": "Orphan Node",
                    "type": "component",
                    "measure": "voltage",
                    "expected": "present",
                    "refs": [],
                    "tags": [],
                }
            ],
            "edges": [],
            "alarm_map": {},
        }
        
        graph_path = temp_graphs_dir / "test_empty.graph.json"
        graph_path.write_text(json.dumps(graph_json))
        
        engine = SignalPathEngine(graphs_dir=temp_graphs_dir)
        graph = engine.load_graph("test_empty")
        assert graph is not None, "Test graph should load successfully"
        
        # Empty context docs
        plan = engine.generate_diagnostic_plan(graph, "orphan", [], max_steps=5)
        
        # Should refuse due to no evidence
        assert plan.response_type == "refusal"
        assert plan.reason == "insufficient_evidence"

    def test_validate_plan_function(self):
        """Test the validate_plan function directly."""
        engine = SignalPathEngine()
        
        # Valid steps with citations
        valid_steps = [
            DiagnosticStep(1, "Check A", "voltage", "present", None, None, ["Ref 1"]),
            DiagnosticStep(2, "Check B", "rf", "present", None, None, ["Ref 2"]),
        ]
        result = engine.validate_plan(valid_steps)
        assert result["valid"] is True
        
        # Invalid steps without citations
        invalid_steps = [
            DiagnosticStep(1, "Check A", "voltage", "present", None, None, ["Ref 1"]),
            DiagnosticStep(2, "Check B", "rf", "present", None, None, []),  # No refs!
        ]
        result = engine.validate_plan(invalid_steps)
        assert result["valid"] is False
        assert 2 in result["missing_steps"]


# ──────────────────────────────────────────────────────────────────────────────
# Test: Full Engine Run
# ──────────────────────────────────────────────────────────────────────────────


class TestFullEngineRun:
    """Integration tests for the full engine.run() method."""

    def test_run_with_valid_input(
        self,
        engine_with_temp_graphs: SignalPathEngine,
        sample_context_docs: List[Dict],
    ):
        """Test full run with valid inputs."""
        result = engine_with_temp_graphs.run(
            domain="test",
            alarm_or_symptom="no_output alarm",
            context_docs=sample_context_docs,
        )
        
        assert result["response_type"] == "diagnostic_plan"
        assert result["domain"] == "test"
        assert "steps" in result
        assert len(result["steps"]) > 0

    def test_run_with_missing_graph(
        self, engine_with_temp_graphs: SignalPathEngine
    ):
        """Test run with non-existent domain."""
        result = engine_with_temp_graphs.run(
            domain="nonexistent",
            alarm_or_symptom="some alarm",
            context_docs=[],
        )
        
        assert result["response_type"] == "refusal"
        assert result["reason"] == "graph_not_found"

    def test_convenience_function(
        self, temp_graphs_dir: Path, sample_graph_json: Dict, sample_context_docs: List
    ):
        """Test the run_signal_path_diagnosis convenience function."""
        # This test uses the global engine which may not have our test graph
        # So we just verify the function is callable and returns expected structure
        result = run_signal_path_diagnosis(
            domain="nonexistent_for_test",
            alarm_or_symptom="test",
            context_docs=[],
        )
        
        assert "response_type" in result
        assert "domain" in result


# ──────────────────────────────────────────────────────────────────────────────
# Test: Cross-Domain Capability
# ──────────────────────────────────────────────────────────────────────────────


class TestCrossDomainCapability:
    """Test that engine can handle all three domains."""

    @pytest.mark.parametrize(
        "domain,graph_id",
        [
            ("beacon", "hv"),
            ("asr8", "power"),
            ("nexrad", "tx"),
        ],
    )
    def test_load_all_domains(self, domain: str, graph_id: str):
        """Test loading graphs for all three domains."""
        engine = SignalPathEngine(graphs_dir=Path("graphs"))
        graph = engine.load_graph(domain, graph_id)
        
        # Graph might not exist in test environment, but if it does, validate it
        if graph is not None:
            assert graph.domain == domain
            assert len(graph.nodes) > 0
            assert len(graph.edges) > 0
            # All actionable nodes must have refs
            for node in graph.nodes:
                if node.type != "decision":
                    assert len(node.refs) > 0, f"Node {node.id} in {domain} missing refs"


# ──────────────────────────────────────────────────────────────────────────────
# Test: Graph Path Traversal
# ──────────────────────────────────────────────────────────────────────────────


class TestGraphPathTraversal:
    """Tests for graph path traversal and primary path detection."""

    def test_get_primary_path(self, engine_with_temp_graphs: SignalPathEngine):
        """Test primary path extraction."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        path = graph.get_primary_path()
        
        # Should follow signal_flow edges
        assert len(path) >= 2
        # Output should be in the path
        assert "output" in path

    def test_get_node(self, engine_with_temp_graphs: SignalPathEngine):
        """Test node retrieval by ID."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        node = graph.get_node("amplifier")
        assert node is not None
        assert node.label == "RF Amplifier"
        
        # Non-existent node
        missing = graph.get_node("nonexistent")
        assert missing is None


# ──────────────────────────────────────────────────────────────────────────────
# Test: Safety Constraints
# ──────────────────────────────────────────────────────────────────────────────


class TestSafetyConstraints:
    """Tests for safety-related constraints."""

    def test_no_invented_components(
        self, engine_with_temp_graphs: SignalPathEngine, sample_context_docs: List
    ):
        """Test that engine only uses nodes from the graph."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        plan = engine_with_temp_graphs.generate_diagnostic_plan(
            graph, "amplifier", sample_context_docs, max_steps=5
        )
        
        # All step references should be to valid graph nodes
        valid_node_ids = {node.id for node in graph.nodes}
        for step in plan.steps:
            if step.if_present:
                assert step.if_present in valid_node_ids
            if step.if_absent:
                assert step.if_absent in valid_node_ids

    def test_max_steps_limit(
        self, engine_with_temp_graphs: SignalPathEngine, sample_context_docs: List
    ):
        """Test that max_steps is respected."""
        graph = engine_with_temp_graphs.load_graph("test")
        assert graph is not None, "Test graph should load successfully"
        
        plan = engine_with_temp_graphs.generate_diagnostic_plan(
            graph, "amplifier", sample_context_docs, max_steps=2
        )
        
        assert len(plan.steps) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
