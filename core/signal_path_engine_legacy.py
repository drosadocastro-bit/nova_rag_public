"""
Multi-Domain Signal-Path Diagnostic Engine (MVP)

Domain-agnostic signal path engine that loads per-domain graph JSON and outputs
a branching diagnostic plan using midpoint isolation. Runs post-retrieval only.

Non-negotiable Safety Rules:
1. No invented components - only use nodes defined in graph and retrieved context
2. Every diagnostic step must include citations (refs[]) pointing to manual sections
   If any step lacks citations, return extractive fallback or refusal
3. Does NOT modify retrieval ranking - runs post-retrieval only
4. CoVe and citation audit remain enforced upstream for safety-critical intents

Author: NIC Team
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Graph Schema Types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    """A node in the signal path graph."""
    id: str
    label: str
    type: str  # component, test_point, interlock, decision
    measure: Optional[str]  # voltage, rf, logic, power, pulse, or None
    expected: str  # e.g., "present", "absent", ">=X", "within spec"
    refs: List[str]  # Citation anchors/ids (must be non-empty for actionable nodes)
    tags: List[str] = field(default_factory=list)  # e.g., ["high_voltage", "alarm_123"]


@dataclass
class GraphEdge:
    """An edge connecting two nodes."""
    from_node: str
    to_node: str
    kind: str  # signal_flow, power_flow, control_flow


@dataclass
class SignalGraph:
    """Parsed signal path graph for a domain."""
    domain: str
    graph_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    alarm_map: Dict[str, str] = field(default_factory=dict)  # alarm_code -> start_node_id

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_primary_path(self) -> List[str]:
        """
        Get ordered list of node IDs along the primary signal/power flow path.
        Uses topological traversal following signal_flow and power_flow edges.
        Signal_flow edges are prioritized, but power_flow is included to ensure
        complete path coverage for diagnostic purposes.
        """
        if not self.nodes:
            return []

        # Build adjacency for signal_flow and power_flow edges
        # (control_flow excluded as it doesn't represent data/power path)
        adjacency: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {node.id: 0 for node in self.nodes}

        for edge in self.edges:
            if edge.kind in ("signal_flow", "power_flow"):
                if edge.from_node not in adjacency:
                    adjacency[edge.from_node] = []
                adjacency[edge.from_node].append(edge.to_node)
                if edge.to_node in in_degree:
                    in_degree[edge.to_node] += 1

        # Find start node (in_degree == 0 from signal/power flow)
        start_nodes = [nid for nid, deg in in_degree.items() if deg == 0]
        if not start_nodes:
            # Fallback: use first node
            start_nodes = [self.nodes[0].id]

        # BFS traversal to build path
        path = []
        visited = set()
        queue = [start_nodes[0]]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if self.get_node(current):
                path.append(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        return path


# ──────────────────────────────────────────────────────────────────────────────
# Diagnostic Plan Types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DiagnosticStep:
    """A single step in the diagnostic plan."""
    step_num: int
    action: str
    measure: Optional[str]
    expected: str
    if_present: Optional[str]  # next node_id if condition met
    if_absent: Optional[str]   # next node_id if condition not met
    refs: List[str]  # Citations - must be non-empty


@dataclass
class DiagnosticPlan:
    """Complete diagnostic plan output."""
    response_type: str  # diagnostic_plan, extractive_fallback, refusal
    domain: str
    graph_id: str
    steps: List[DiagnosticStep] = field(default_factory=list)
    reason: Optional[str] = None  # For refusals
    fallback_evidence: Optional[List[Dict[str, Any]]] = None
    # Phase 4 infrastructure: Diagnostic confidence and strategy
    diagnostic_confidence: float = 0.0  # Combined confidence (0.0-1.0)
    confirmation_strategy: str = "multi_node"  # midpoint, branch, multi_node
    required_nodes: int = 3  # Minimum nodes for selected strategy


# ──────────────────────────────────────────────────────────────────────────────
# Signal Path Engine
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_GRAPHS_DIR = Path("graphs")
FALLBACK_GRAPHS_DIR = Path("data") / "signal_paths"


class SignalPathEngine:
    """
    Signal-path diagnostic engine using midpoint isolation.
    
    This engine:
    1. Loads per-domain graph JSON files
    2. Selects start node based on alarm_map or midpoint
    3. Generates branching diagnostic plan with midpoint isolation
    4. Validates all steps have citations; refuses if not
    """

    def __init__(self, graphs_dir: Optional[Path] = None) -> None:
        """
        Initialize the signal path engine.
        
        Args:
            graphs_dir: Directory containing graph JSON files. 
                       Defaults to graphs/, falls back to data/signal_paths/
        """
        if graphs_dir is not None:
            self.graphs_dir = graphs_dir
        elif DEFAULT_GRAPHS_DIR.exists():
            self.graphs_dir = DEFAULT_GRAPHS_DIR
        elif FALLBACK_GRAPHS_DIR.exists():
            self.graphs_dir = FALLBACK_GRAPHS_DIR
        else:
            # Ensure graphs_dir is never None; default to PRIMARY location
            self.graphs_dir = DEFAULT_GRAPHS_DIR
        self._graph_cache: Dict[str, SignalGraph] = {}

    def load_graph(self, domain: str, graph_id: str = "default") -> Optional[SignalGraph]:
        """
        Load a signal path graph for a domain.
        
        Args:
            domain: Domain name (beacon, asr8, nexrad)
            graph_id: Optional specific graph ID
            
        Returns:
            SignalGraph or None if not found
        """
        cache_key = f"{domain}:{graph_id}"
        if cache_key in self._graph_cache:
            return self._graph_cache[cache_key]

        # Try various filename patterns
        candidates = [
            self.graphs_dir / f"{domain}_{graph_id}.graph.json",
            self.graphs_dir / f"{domain}.graph.json",
            self.graphs_dir / f"{domain}_{graph_id}.json",
            self.graphs_dir / f"{domain}.json",
        ]

        for path in candidates:
            if path.exists():
                try:
                    graph = self._parse_graph(path)
                    if graph:
                        self._graph_cache[cache_key] = graph
                        return graph
                except Exception as e:
                    logger.warning(f"Failed to parse graph {path}: {e}")

        logger.warning(f"No graph found for domain={domain}, graph_id={graph_id}")
        return None

    def _parse_graph(self, path: Path) -> Optional[SignalGraph]:
        """Parse a graph JSON file into a SignalGraph."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read graph file {path}: {e}")
            return None

        domain = data.get("domain", "unknown")
        graph_id = data.get("graph_id", path.stem)

        # Parse nodes
        nodes = []
        for node_data in data.get("nodes", []):
            node = GraphNode(
                id=node_data.get("id", ""),
                label=node_data.get("label", node_data.get("id", "")),
                type=node_data.get("type", "component"),
                measure=node_data.get("measure"),
                expected=node_data.get("expected", "within spec"),
                refs=node_data.get("refs", []),
                tags=node_data.get("tags", []),
            )
            nodes.append(node)

        # Parse edges
        edges = []
        for edge_data in data.get("edges", []):
            edge = GraphEdge(
                from_node=edge_data.get("from", ""),
                to_node=edge_data.get("to", ""),
                kind=edge_data.get("kind", "signal_flow"),
            )
            edges.append(edge)

        # Parse alarm_map
        alarm_map = data.get("alarm_map", {})

        return SignalGraph(
            domain=domain,
            graph_id=graph_id,
            nodes=nodes,
            edges=edges,
            alarm_map=alarm_map,
        )

    def choose_start_node(
        self, graph: SignalGraph, alarm_or_symptom_text: str
    ) -> Optional[str]:
        """
        Choose the starting node for diagnosis.
        
        Strategy:
        1. If alarm_map has a match, use that node
        2. Otherwise, choose midpoint node along primary path
        
        Args:
            graph: The signal graph
            alarm_or_symptom_text: User's symptom or alarm description
            
        Returns:
            Node ID to start diagnosis, or None
        """
        text_lower = alarm_or_symptom_text.lower()

        # Strategy 1: Check alarm_map for matches
        for alarm_code, node_id in graph.alarm_map.items():
            if alarm_code.lower() in text_lower:
                if graph.get_node(node_id):
                    logger.debug(f"Alarm match: {alarm_code} -> {node_id}")
                    return node_id

        # Strategy 2: Check node tags for keyword matches
        for node in graph.nodes:
            for tag in node.tags:
                if tag.lower() in text_lower:
                    logger.debug(f"Tag match: {tag} -> {node.id}")
                    return node.id

        # Strategy 3: Midpoint of primary path
        primary_path = graph.get_primary_path()
        if primary_path:
            midpoint_idx = len(primary_path) // 2
            midpoint_node = primary_path[midpoint_idx]
            logger.debug(f"Using midpoint: {midpoint_node}")
            return midpoint_node

        # Fallback: first node
        if graph.nodes:
            return graph.nodes[0].id

        return None

    def generate_diagnostic_plan(
        self,
        graph: SignalGraph,
        start_node_id: str,
        context_docs: List[Dict[str, Any]],
        max_steps: int = 5,
    ) -> DiagnosticPlan:
        """
        Generate a branching diagnostic plan using midpoint isolation.
        
        The plan follows radar-school signal-path troubleshooting:
        - Start at isolation point (midpoint or alarm-mapped node)
        - If signal present -> troubleshoot downstream
        - If signal absent -> troubleshoot upstream
        
        Args:
            graph: The signal graph
            start_node_id: Node ID to start from
            context_docs: Retrieved context documents for citation matching
            max_steps: Maximum steps to generate
            
        Returns:
            DiagnosticPlan with steps or refusal
        """
        primary_path = graph.get_primary_path()
        if not primary_path:
            return DiagnosticPlan(
                response_type="refusal",
                domain=graph.domain,
                graph_id=graph.graph_id,
                reason="signal_path_not_found",
            )

        # Find start position in path
        try:
            start_idx = primary_path.index(start_node_id)
        except ValueError:
            start_idx = len(primary_path) // 2

        # Build midpoint isolation plan
        steps = self._build_midpoint_plan(
            graph, primary_path, start_idx, context_docs, max_steps
        )

        # Validate all steps have citations
        validation_result = self.validate_plan(steps)
        if not validation_result["valid"]:
            # Return extractive fallback
            return self._create_extractive_fallback(
                graph, context_docs, validation_result["reason"]
            )

        return DiagnosticPlan(
            response_type="diagnostic_plan",
            domain=graph.domain,
            graph_id=graph.graph_id,
            steps=steps,
        )

    def _build_midpoint_plan(
        self,
        graph: SignalGraph,
        path: List[str],
        start_idx: int,
        context_docs: List[Dict[str, Any]],
        max_steps: int,
    ) -> List[DiagnosticStep]:
        """
        Build a branching plan using midpoint isolation algorithm.
        
        This implements the "Point C" isolation strategy:
        - Check at midpoint
        - If OK (signal present) -> problem is downstream, isolate downstream half
        - If NOT OK (signal absent) -> problem is upstream, isolate upstream half
        """
        steps: List[DiagnosticStep] = []
        step_num = 1

        # Track segments to process: (start_idx, end_idx, direction)
        # direction: "downstream" or "upstream"
        segments_to_process = [(0, len(path) - 1, start_idx)]

        while segments_to_process and step_num <= max_steps:
            segment_start, segment_end, check_idx = segments_to_process.pop(0)

            if segment_start > segment_end or check_idx < 0 or check_idx >= len(path):
                continue

            node_id = path[check_idx]
            node = graph.get_node(node_id)
            if not node:
                continue

            # Find citations from graph refs + context docs
            refs = self._find_citations(node, context_docs)

            # Calculate next check points for branching
            upstream_mid = None
            downstream_mid = None

            if check_idx > segment_start:
                upstream_mid = path[(segment_start + check_idx) // 2]
            if check_idx < segment_end:
                downstream_mid = path[(check_idx + 1 + segment_end) // 2]

            step = DiagnosticStep(
                step_num=step_num,
                action=f"Check {node.label}: verify {node.expected}",
                measure=node.measure,
                expected=node.expected,
                if_present=downstream_mid,  # Signal OK -> check downstream
                if_absent=upstream_mid,     # Signal not OK -> check upstream
                refs=refs,
            )
            steps.append(step)
            step_num += 1

            # Queue sub-segments for deeper isolation
            if check_idx > segment_start:
                upstream_check = (segment_start + check_idx) // 2
                segments_to_process.append((segment_start, check_idx - 1, upstream_check))
            if check_idx < segment_end:
                downstream_check = (check_idx + 1 + segment_end) // 2
                segments_to_process.append((check_idx + 1, segment_end, downstream_check))

        return steps

    def _find_citations(
        self, node: GraphNode, context_docs: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Find citations for a node from graph refs and retrieved context.
        
        Priority:
        1. Use graph-defined refs if present
        2. Match context docs by keywords in node label/tags
        """
        citations: List[str] = []

        # Use graph-defined refs first
        if node.refs:
            citations.extend(node.refs)

        # Also try to match from context docs
        search_terms = [node.label.lower(), node.id.lower()] + [t.lower() for t in node.tags]

        for doc in context_docs:
            text = (doc.get("text") or doc.get("snippet") or "").lower()
            source = doc.get("source", "unknown")
            page = doc.get("page")

            for term in search_terms:
                if term and term in text:
                    ref = source
                    if page:
                        ref += f" p{page}"
                    if ref not in citations:
                        citations.append(ref)
                    break

            if len(citations) >= 3:
                break

        return citations

    def validate_plan(self, steps: List[DiagnosticStep]) -> Dict[str, Any]:
        """
        Validate that all diagnostic steps have citations.
        
        Returns:
            {"valid": True/False, "reason": str, "missing_steps": list}
        """
        missing_citations = []

        for step in steps:
            if not step.refs:
                missing_citations.append(step.step_num)

        if missing_citations:
            return {
                "valid": False,
                "reason": "insufficient_evidence",
                "missing_steps": missing_citations,
            }

        return {"valid": True, "reason": None, "missing_steps": []}

    def _create_extractive_fallback(
        self,
        graph: SignalGraph,
        context_docs: List[Dict[str, Any]],
        reason: str,
    ) -> DiagnosticPlan:
        """
        Create an extractive fallback when citations are missing.
        """
        fallback_evidence = []

        for doc in context_docs[:3]:
            snippet = (doc.get("snippet") or doc.get("text") or "")[:250]
            fallback_evidence.append({
                "source": doc.get("source", "unknown"),
                "page": doc.get("page"),
                "snippet": snippet,
            })

        if not fallback_evidence:
            return DiagnosticPlan(
                response_type="refusal",
                domain=graph.domain,
                graph_id=graph.graph_id,
                reason="insufficient_evidence",
            )

        return DiagnosticPlan(
            response_type="extractive_fallback",
            domain=graph.domain,
            graph_id=graph.graph_id,
            reason=reason,
            fallback_evidence=fallback_evidence,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 4: Confidence Signal Computation
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_retrieval_confidence(self, context_docs: List[Dict[str, Any]]) -> float:
        """
        Compute retrieval confidence based on document quality and relevance.
        
        Args:
            context_docs: Retrieved context documents
            
        Returns:
            Confidence score (0.0-1.0)
        """
        if not context_docs:
            return 0.0
        
        # Heuristic: More relevant documents (with scores) = higher confidence
        scores = []
        for doc in context_docs[:5]:  # Look at top 5 docs
            score = doc.get("score", doc.get("relevance_score"))
            if isinstance(score, (int, float)):
                scores.append(min(1.0, max(0.0, float(score))))
        
        if not scores:
            # No scores available, use document count heuristic
            return min(0.9, len(context_docs) / 10.0)
        
        # Average of top scores
        return sum(scores) / len(scores)

    def _compute_graph_confidence(self, graph: SignalGraph, alarm_or_symptom: str) -> float:
        """
        Compute graph confidence based on alarm/symptom match quality.
        
        Args:
            graph: The signal graph
            alarm_or_symptom: User's symptom/alarm description
            
        Returns:
            Confidence score (0.0-1.0)
        """
        text_lower = alarm_or_symptom.lower()
        
        # Check for alarm_map matches (highest confidence)
        for alarm_code in graph.alarm_map.keys():
            if alarm_code.lower() in text_lower:
                return 0.95  # Direct alarm match
        
        # Check for node tag matches (high confidence)
        for node in graph.nodes:
            for tag in node.tags:
                if tag.lower() in text_lower:
                    return 0.85
        
        # Check for node label matches (medium confidence)
        for node in graph.nodes:
            if node.label.lower() in text_lower:
                return 0.70
        
        # No specific match, rely on graph existence (low confidence)
        return 0.50

    def _compute_alarm_confidence(self, graph: SignalGraph, alarm_or_symptom: str) -> float:
        """
        Compute alarm confidence based on alarm_map coverage.
        
        Args:
            graph: The signal graph
            alarm_or_symptom: User's symptom/alarm description
            
        Returns:
            Confidence score (0.0-1.0)
        """
        if not graph.alarm_map:
            return 0.5  # No alarm_map = neutral confidence
        
        # Check if alarm_or_symptom matches any alarm_map codes
        text_lower = alarm_or_symptom.lower()
        matches = 0
        
        for alarm_code in graph.alarm_map.keys():
            if alarm_code.lower() in text_lower:
                matches += 1
        
        if matches > 0:
            # Matched alarms = higher confidence
            return min(1.0, 0.8 + (0.2 * (matches / len(graph.alarm_map))))
        
        # No matches, but alarm_map exists = medium confidence
        return 0.65

    def run(
        self,
        domain: str,
        alarm_or_symptom: str,
        context_docs: List[Dict[str, Any]],
        graph_id: str = "default",
        max_steps: int = 5,
    ) -> Dict[str, Any]:
        """
        Main entry point: run the signal path engine.
        
        Args:
            domain: Domain name (beacon, asr8, nexrad)
            alarm_or_symptom: User's symptom or alarm description
            context_docs: Retrieved context documents
            graph_id: Specific graph to load
            max_steps: Maximum diagnostic steps
            
        Returns:
            Dict representation of DiagnosticPlan
        """
        # Import diagnostics after engine loads to avoid circular deps
        from core.diagnostics import (
            compute_diagnostic_confidence,
            determine_confirmation_strategy,
            get_required_nodes_count,
            is_debug_enabled,
            log_debug_info,
        )
        
        # Load graph
        graph = self.load_graph(domain, graph_id)
        if not graph:
            return {
                "response_type": "refusal",
                "domain": domain,
                "graph_id": graph_id,
                "reason": "graph_not_found",
                "message": f"Signal path graph not found for domain '{domain}'.",
            }

        # Choose start node
        start_node_id = self.choose_start_node(graph, alarm_or_symptom)
        if not start_node_id:
            return {
                "response_type": "refusal",
                "domain": domain,
                "graph_id": graph_id,
                "reason": "no_start_node",
                "message": "Could not determine starting point for diagnosis.",
            }

        # Generate plan
        plan = self.generate_diagnostic_plan(
            graph, start_node_id, context_docs, max_steps
        )

        # Compute diagnostic confidence (Phase 4 infrastructure)
        # Confidence signals derived from:
        # - retrieval_conf: Quality of retrieved context (0-1)
        # - graph_conf: Match quality of alarm/symptom to graph (0-1)
        # - alarm_conf: Alarm_map coverage (0-1)
        retrieval_conf = self._compute_retrieval_confidence(context_docs)
        graph_conf = self._compute_graph_confidence(graph, alarm_or_symptom)
        alarm_conf = self._compute_alarm_confidence(graph, alarm_or_symptom)
        
        plan.diagnostic_confidence = compute_diagnostic_confidence(
            retrieval_conf=retrieval_conf,
            graph_conf=graph_conf,
            alarm_conf=alarm_conf,
            rerank_conf=None,  # Not available in signal path context
        )
        
        # Determine confirmation strategy based on confidence
        strategy_str = determine_confirmation_strategy(plan.diagnostic_confidence)
        plan.confirmation_strategy = strategy_str
        
        # Set required node count for strategy
        plan.required_nodes = get_required_nodes_count(strategy_str)
        
        # Optional debug output
        if is_debug_enabled():
            log_debug_info(
                confidence=plan.diagnostic_confidence,
                strategy=plan.confirmation_strategy,
                components={
                    "retrieval": retrieval_conf,
                    "graph": graph_conf,
                    "alarm": alarm_conf,
                },
                metadata={
                    "domain": domain,
                    "graph_id": graph_id,
                    "required_nodes": plan.required_nodes,
                    "start_node": start_node_id,
                },
            )

        # Convert to dict
        result = {
            "response_type": plan.response_type,
            "domain": plan.domain,
            "graph_id": plan.graph_id,
            # Phase 4: Include confidence and strategy
            "diagnostic_confidence": plan.diagnostic_confidence,
            "confirmation_strategy": plan.confirmation_strategy,
            "required_nodes": plan.required_nodes,
        }

        if plan.steps:
            result["steps"] = [
                {
                    "step": step.step_num,
                    "action": step.action,
                    "measure": step.measure,
                    "expected": step.expected,
                    "if_present": step.if_present,
                    "if_absent": step.if_absent,
                    "refs": step.refs,
                }
                for step in plan.steps
            ]

        if plan.reason:
            result["reason"] = plan.reason

        if plan.fallback_evidence:
            result["fallback_evidence"] = plan.fallback_evidence
            result["message"] = (
                "Insufficient citations to support a full diagnostic plan. "
                "Top evidence from retrieved context is provided below."
            )

        return result


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────────────────────────────────────

_default_engine: Optional[SignalPathEngine] = None


def get_engine() -> SignalPathEngine:
    """Get or create the default signal path engine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = SignalPathEngine()
    return _default_engine


def run_signal_path_diagnosis(
    domain: str,
    alarm_or_symptom: str,
    context_docs: List[Dict[str, Any]],
    **kwargs,
) -> Dict[str, Any]:
    """
    Convenience function to run signal path diagnosis.
    
    Example:
        result = run_signal_path_diagnosis(
            domain="nexrad",
            alarm_or_symptom="No RF output from transmitter",
            context_docs=retrieved_chunks,
        )
    """
    engine = get_engine()
    return engine.run(domain, alarm_or_symptom, context_docs, **kwargs)
