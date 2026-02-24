"""
Domain-agnostic signal path engine.

Loads per-domain signal path graphs and generates a branching diagnostic plan
using midpoint isolation. This runs post-retrieval and requires citations for
EVERY step. If citations are missing, it returns an extractive fallback.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.retrieval.retrieval_engine import detect_domain_intent


DEFAULT_GRAPH_DIR = Path("data") / "signal_paths"
GRAPH_EXTENSIONS = [".json"]


@dataclass
class Citation:
    source: str
    page: Optional[int]
    snippet: str


@dataclass
class PlanStep:
    step_id: int
    title: str
    instruction: str
    citations: List[Citation]
    pass_next: Optional[int] = None
    fail_next: Optional[int] = None


class SignalPathEngine:
    def __init__(self, graph_dir: Optional[Path] = None) -> None:
        self.graph_dir = graph_dir or DEFAULT_GRAPH_DIR

    def build_plan(
        self,
        question: str,
        context_docs: List[Dict[str, Any]],
        domain_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        domain = domain_hint or self._infer_domain(question, context_docs)
        graph = self._load_graph(domain)
        if not graph:
            return {
                "status": "refusal",
                "reason": "signal_path_graph_missing",
                "message": (
                    "Signal-path graph not available for this domain. "
                    "Add a per-domain graph JSON under data/signal_paths." 
                ),
            }

        path = self._select_path(graph, question)
        if not path:
            return {
                "status": "refusal",
                "reason": "signal_path_not_found",
                "message": "No matching signal path found in the domain graph.",
            }

        nodes = path.get("nodes", [])
        if len(nodes) < 2:
            return {
                "status": "refusal",
                "reason": "signal_path_invalid",
                "message": "Signal path graph is missing node details.",
            }

        steps = self._build_midpoint_plan(nodes, context_docs)
        if steps is None:
            return self._extractive_fallback(context_docs)

        return {
            "status": "success",
            "domain": domain,
            "path_id": path.get("id"),
            "path_name": path.get("name"),
            "plan": self._format_plan(steps),
        }

    def _infer_domain(self, question: str, context_docs: List[Dict[str, Any]]) -> str:
        domain_counts = Counter(
            d.get("domain") for d in context_docs if isinstance(d.get("domain"), str)
        )
        if domain_counts:
            most_common = domain_counts.most_common(1)
            if most_common and len(most_common) > 0:
                domain = most_common[0][0]
                if isinstance(domain, str):
                    return domain
        detected, _ = detect_domain_intent(question)
        return detected or "unknown"

    def _load_graph(self, domain: str) -> Optional[Dict[str, Any]]:
        if not self.graph_dir.exists():
            return None

        candidates = [
            self.graph_dir / f"{domain}.json",
            self.graph_dir / f"{domain}_graph.json",
            self.graph_dir / "default.json",
        ]
        for path in candidates:
            if path.exists() and path.suffix in GRAPH_EXTENSIONS:
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return None
        return None

    def _select_path(self, graph: Dict[str, Any], question: str) -> Optional[Dict[str, Any]]:
        paths = graph.get("signal_paths") or []
        if not paths:
            return None

        q_lower = question.lower()
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for path in paths:
            keywords = path.get("keywords", [])
            score = sum(1 for kw in keywords if kw.lower() in q_lower)
            scored.append((score, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]

        return paths[0]

    def _build_midpoint_plan(
        self,
        nodes: List[Dict[str, Any]],
        context_docs: List[Dict[str, Any]],
    ) -> Optional[List[PlanStep]]:
        steps: List[PlanStep] = []

        def add_step(node_index: int, pass_next: Optional[int], fail_next: Optional[int]) -> None:
            node = nodes[node_index]
            title = node.get("name") or node.get("id") or f"node_{node_index}"
            instruction = (node.get("check") or node.get("instruction") or "Verify operation per manual.").strip()
            citations = self._find_citations(node, context_docs)
            if not citations:
                raise ValueError("missing_citations")
            steps.append(
                PlanStep(
                    step_id=len(steps) + 1,
                    title=title,
                    instruction=instruction,
                    citations=citations,
                    pass_next=pass_next,
                    fail_next=fail_next,
                )
            )

        def build_segment(start: int, end: int) -> int:
            mid = (start + end) // 2
            current_step_id = len(steps) + 1

            left_id = None
            right_id = None
            if start <= mid - 1:
                left_id = current_step_id + 1
                build_segment(start, mid - 1)
            if mid + 1 <= end:
                right_id = len(steps) + 1
                build_segment(mid + 1, end)

            try:
                add_step(mid, pass_next=right_id, fail_next=left_id)
            except ValueError:
                raise
            return current_step_id

        try:
            build_segment(0, len(nodes) - 1)
        except ValueError:
            return None

        # Ensure deterministic order by step_id
        steps.sort(key=lambda s: s.step_id)
        return steps

    def _find_citations(self, node: Dict[str, Any], context_docs: List[Dict[str, Any]]) -> List[Citation]:
        keywords = [kw.lower() for kw in node.get("keywords", []) if isinstance(kw, str)]
        if not keywords:
            keywords = [str(node.get("name", "")).lower()]

        citations: List[Citation] = []
        for doc in context_docs:
            text = (doc.get("text") or doc.get("snippet") or "").lower()
            if any(kw and kw in text for kw in keywords):
                citations.append(
                    Citation(
                        source=str(doc.get("source", "unknown")),
                        page=doc.get("page"),
                        snippet=(doc.get("snippet") or doc.get("text") or "")[:180],
                    )
                )
            if len(citations) >= 3:
                break
        return citations

    def _format_plan(self, steps: List[PlanStep]) -> str:
        lines = ["Branching diagnostic plan (midpoint isolation):"]
        for step in steps:
            lines.append(f"{step.step_id}. Check {step.title}: {step.instruction}")
            for cite in step.citations:
                page = f" p{cite.page}" if cite.page is not None else ""
                lines.append(f"   - Source: {cite.source}{page} — {cite.snippet}")
            if step.pass_next or step.fail_next:
                if step.pass_next:
                    lines.append(f"   - If normal -> go to step {step.pass_next}")
                if step.fail_next:
                    lines.append(f"   - If abnormal -> go to step {step.fail_next}")
        return "\n".join(lines)

    def _extractive_fallback(self, context_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not context_docs:
            return {
                "status": "refusal",
                "reason": "missing_citations",
                "message": "Insufficient citations available to build a diagnostic plan.",
            }
        lines = [
            "Refusal: insufficient citations to support a full diagnostic plan.",
            "Extractive fallback (top evidence):",
        ]
        for doc in context_docs[:3]:
            snippet = (doc.get("snippet") or doc.get("text") or "")[:220]
            page = f" p{doc.get('page')}" if doc.get("page") is not None else ""
            lines.append(f"- {doc.get('source','unknown')}{page}: {snippet}")
        return {
            "status": "refusal",
            "reason": "missing_citations",
            "message": "\n".join(lines),
        }
