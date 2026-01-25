"""
Neural Advisory Layer helpers for Phase 3.5 integration.

Responsibilities:
- Centralize feature flags for finetuned embeddings, anomaly detection, and compliance reports.
- Build evidence chains from API responses for compliance reporting.
- Generate tamper-evident compliance reports (JSON/PDF) with graceful degradation.

All features are advisory-only: failures fall back to baseline behavior without blocking requests.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from core.compliance.report_generator import ComplianceReporter

logger = logging.getLogger(__name__)


@dataclass
class AdvisoryConfig:
    use_finetuned_embeddings: bool
    anomaly_detection_enabled: bool
    auto_compliance_reports: bool
    report_formats: List[str]
    report_dir: str
    system_version: str
    operator: Optional[str]


class NeuralAdvisoryLayer:
    """Phase 3.5 orchestration for advisory-only neural components."""

    def __init__(self) -> None:
        report_formats_env = os.environ.get("NOVA_COMPLIANCE_REPORT_FORMAT", "json")
        report_formats = [f.strip().lower() for f in report_formats_env.split(",") if f.strip()]
        if not report_formats:
            report_formats = ["json"]

        self.config = AdvisoryConfig(
            use_finetuned_embeddings=os.environ.get("NOVA_USE_FINETUNED_EMBEDDINGS", "0") == "1",
            anomaly_detection_enabled=(
                os.environ.get("NOVA_ANOMALY_DETECTOR", "0") == "1"
                or os.environ.get("NOVA_ENABLE_ANOMALY_DETECTION", "0") == "1"
            ),
            auto_compliance_reports=os.environ.get("NOVA_AUTO_COMPLIANCE_REPORTS", "0") == "1",
            report_formats=report_formats,
            report_dir=os.environ.get("NOVA_COMPLIANCE_REPORT_DIR", "compliance_reports"),
            system_version=os.environ.get("NOVA_SYSTEM_VERSION", "0.3.5"),
            operator=os.environ.get("NOVA_OPERATOR_ID"),
        )

        self.reporter: Optional[ComplianceReporter] = None
        if self.config.auto_compliance_reports:
            try:
                self.reporter = ComplianceReporter(output_dir=self.config.report_dir)
                logger.info(
                    "Phase 3.5 compliance reporter enabled",
                    extra={"dir": self.config.report_dir, "formats": self.config.report_formats},
                )
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning("Compliance reporter unavailable; auto reports disabled", extra={"error": str(exc)})
                self.reporter = None

    @staticmethod
    def _safe_answer_text(answer: Any) -> str:
        if isinstance(answer, str):
            return answer
        try:
            return json.dumps(answer, ensure_ascii=True, default=str)
        except Exception:
            return str(answer)

    @staticmethod
    def _collect_anomaly_stats(documents: Iterable[Dict[str, Any]]) -> tuple[float, bool]:
        scores: List[float] = []
        flagged = False
        for doc in documents:
            if "anomaly_score" in doc and isinstance(doc.get("anomaly_score"), (int, float)):
                scores.append(float(doc["anomaly_score"]))
            flagged = flagged or bool(doc.get("anomaly_flag") or doc.get("anomaly_flagged"))
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return avg_score, flagged

    def build_evidence_chain(
        self,
        *,
        query: str,
        domain: str,
        intent: Optional[str],
        retrieved_documents: List[Dict[str, Any]],
        safety_meta: Dict[str, Any],
        model_used: str,
        decision_tag: Optional[str],
        traced_sources: List[Dict[str, Any]],
        retrieval_time_ms: float,
        total_time_ms: float,
        session_id: Optional[str],
    ) -> Dict[str, Any]:
        """Assemble a compliance-ready evidence chain."""
        anomaly_score, anomaly_flagged = self._collect_anomaly_stats(retrieved_documents)
        citations = []
        for src in traced_sources:
            source = src.get("source", "unknown")
            page = src.get("page")
            citations.append(f"{source}#page:{page}" if page is not None else str(source))

        safe_docs = []
        for doc in retrieved_documents:
            safe_docs.append(
                {
                    "source": doc.get("source", "unknown"),
                    "page": doc.get("page"),
                    "score": float(doc.get("confidence") or doc.get("score") or 0.0),
                    "anomaly_score": doc.get("anomaly_score"),
                    "anomaly_flag": doc.get("anomaly_flag") or doc.get("anomaly_flagged"),
                    "domain": doc.get("domain"),
                    "snippet": (doc.get("snippet") or doc.get("text") or "")[:280],
                }
            )

        return {
            "session_id": session_id or "session-unknown",
            "system_version": self.config.system_version,
            "query": query,
            "domain": domain or "unknown",
            "intent": intent or "",
            "decision_tag": decision_tag,
            "retrieved_documents": safe_docs,
            "reranking": {},
            "safety_checks": {
                "heuristic_triggers": safety_meta.get("heuristic_triggers") or [],
                "passed": not bool(safety_meta.get("heuristic_triggers")),
            },
            "anomaly_score": anomaly_score,
            "anomaly_flagged": anomaly_flagged,
            "citations": citations,
            "extractive_fallback": False,
            "retrieval_time_ms": retrieval_time_ms,
            "generation_time_ms": max(0.0, total_time_ms - retrieval_time_ms),
            "total_time_ms": total_time_ms,
            "model_used": model_used,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def maybe_generate_report(
        self,
        *,
        evidence_chain: Dict[str, Any],
        query: str,
        answer: Any,
    ) -> List[str]:
        """Generate compliance reports when auto-reporting is enabled.

        Returns a list of saved report paths (may be empty).
        """
        if not self.config.auto_compliance_reports or not self.reporter:
            return []

        answer_text = self._safe_answer_text(answer)
        report = self.reporter.generate_report(
            session_id=evidence_chain.get("session_id", "session-unknown"),
            query=query,
            answer=answer_text,
            evidence_chain=evidence_chain,
            operator=self.config.operator,
        )

        saved: List[str] = []
        for fmt in self.config.report_formats:
            try:
                if fmt == "json":
                    path = self.reporter.save_json(report)
                elif fmt == "pdf":
                    path = self.reporter.save_pdf(report)
                else:
                    continue
                saved.append(str(path))
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.warning("Compliance report generation skipped", extra={"format": fmt, "error": str(exc)})
        return saved


def get_neural_advisory_layer() -> Optional[NeuralAdvisoryLayer]:
    try:
        layer = NeuralAdvisoryLayer()
        return layer
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("NeuralAdvisoryLayer unavailable", extra={"error": str(exc)})
        return None
