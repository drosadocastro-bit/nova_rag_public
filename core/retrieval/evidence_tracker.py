"""
Evidence chain tracking for multi-domain retrieval.

Captures full pipeline trace: query → router → GAR → reranking → final selection
Provides audit trail for debugging contamination and explaining results.
"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class RouterEvidence:
    """Evidence from domain router stage."""
    domain_candidates: List[tuple]  # [(domain, score), ...]
    domain_priors: Dict[str, float]  # {domain: prior_weight}
    filter_applied: bool
    filtered_domains: List[str]
    threshold_used: float
    zero_shot_available: bool
    method: str  # "zero-shot+keywords" | "keywords-only" | "none"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GAREvidence:
    """Evidence from GAR expansion stage."""
    initial_candidates: int
    expanded_candidates: int
    expansion_ratio: float
    domains_in_candidates: Dict[str, int]  # {domain: count}
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RerankingEvidence:
    """Evidence from reranking stage."""
    candidates_before: int
    candidates_after: int
    top_5_scores: List[float]
    domain_prior_boost_applied: bool
    domains_in_top_10: Dict[str, int]  # {domain: count}
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinalSelectionEvidence:
    """Evidence from final selection stage."""
    total_results: int
    domain_distribution: Dict[str, int]  # {domain: count}
    domain_cap_applied: bool
    capped_domains: List[str]
    avg_score: float
    score_range: tuple  # (min, max)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceChain:
    """Complete evidence chain for a retrieval request."""
    query: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    execution_time_ms: float = 0.0
    
    router: Optional[RouterEvidence] = None
    gar: Optional[GAREvidence] = None
    reranking: Optional[RerankingEvidence] = None
    final_selection: Optional[FinalSelectionEvidence] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms,
            "router": self.router.to_dict() if self.router else None,
            "gar": self.gar.to_dict() if self.gar else None,
            "reranking": self.reranking.to_dict() if self.reranking else None,
            "final_selection": self.final_selection.to_dict() if self.final_selection else None,
            "metadata": self.metadata,
        }
    
    def summary(self) -> str:
        """Generate human-readable summary of evidence chain."""
        lines = [
            f"Query: {self.query}",
            f"Execution time: {self.execution_time_ms:.2f}ms",
            "",
        ]
        
        if self.router:
            lines.append("ROUTER:")
            lines.append(f"  Method: {self.router.method}")
            lines.append(f"  Candidates: {self.router.domain_candidates[:3]}")
            lines.append(f"  Filter: {self.router.filter_applied} → {self.router.filtered_domains}")
            lines.append("")
        
        if self.gar:
            lines.append("GAR EXPANSION:")
            lines.append(f"  {self.gar.initial_candidates} → {self.gar.expanded_candidates} ({self.gar.expansion_ratio:.2f}x)")
            lines.append(f"  Domains: {self.gar.domains_in_candidates}")
            lines.append("")
        
        if self.reranking:
            lines.append("RERANKING:")
            lines.append(f"  Candidates: {self.reranking.candidates_before} → {self.reranking.candidates_after}")
            lines.append(f"  Top 5 scores: {[f'{s:.3f}' for s in self.reranking.top_5_scores[:5]]}")
            lines.append(f"  Top 10 domains: {self.reranking.domains_in_top_10}")
            lines.append("")
        
        if self.final_selection:
            lines.append("FINAL SELECTION:")
            lines.append(f"  Results: {self.final_selection.total_results}")
            lines.append(f"  Distribution: {self.final_selection.domain_distribution}")
            lines.append(f"  Cap applied: {self.final_selection.domain_cap_applied} → {self.final_selection.capped_domains}")
            lines.append(f"  Score range: {self.final_selection.score_range[0]:.3f} - {self.final_selection.score_range[1]:.3f}")
        
        return "\n".join(lines)


class EvidenceTracker:
    """Context manager for tracking evidence throughout retrieval pipeline."""
    
    def __init__(self, query: str, enabled: bool = True):
        self.query = query
        self.enabled = enabled
        self.chain = EvidenceChain(query=query) if enabled else None
        self.start_time = None
    
    def __enter__(self):
        if self.enabled:
            self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.enabled and self.start_time and self.chain is not None:
            elapsed = (time.time() - self.start_time) * 1000  # ms
            self.chain.execution_time_ms = elapsed
        return False
    
    def record_router(
        self,
        domain_candidates: List[tuple],
        domain_priors: Dict[str, float],
        filter_applied: bool,
        filtered_domains: List[str],
        threshold_used: float,
        zero_shot_available: bool,
        method: str,
    ):
        """Record router stage evidence."""
        if not self.enabled or self.chain is None:
            return
        
        self.chain.router = RouterEvidence(
            domain_candidates=domain_candidates,
            domain_priors=domain_priors,
            filter_applied=filter_applied,
            filtered_domains=filtered_domains,
            threshold_used=threshold_used,
            zero_shot_available=zero_shot_available,
            method=method,
        )
    
    def record_gar(
        self,
        initial_candidates: int,
        expanded_candidates: int,
        domains_in_candidates: Dict[str, int],
    ):
        """Record GAR expansion stage evidence."""
        if not self.enabled or self.chain is None:
            return
        
        expansion_ratio = expanded_candidates / initial_candidates if initial_candidates > 0 else 0
        self.chain.gar = GAREvidence(
            initial_candidates=initial_candidates,
            expanded_candidates=expanded_candidates,
            expansion_ratio=expansion_ratio,
            domains_in_candidates=domains_in_candidates,
        )
    
    def record_reranking(
        self,
        candidates_before: int,
        candidates_after: int,
        top_scores: List[float],
        domain_prior_boost_applied: bool,
        domains_in_top_10: Dict[str, int],
    ):
        """Record reranking stage evidence."""
        if not self.enabled or self.chain is None:
            return
        
        self.chain.reranking = RerankingEvidence(
            candidates_before=candidates_before,
            candidates_after=candidates_after,
            top_5_scores=top_scores[:5],
            domain_prior_boost_applied=domain_prior_boost_applied,
            domains_in_top_10=domains_in_top_10,
        )
    
    def record_final_selection(
        self,
        total_results: int,
        domain_distribution: Dict[str, int],
        domain_cap_applied: bool,
        capped_domains: List[str],
        scores: List[float],
    ):
        """Record final selection stage evidence."""
        if not self.enabled or self.chain is None:
            return
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        score_range = (min(scores), max(scores)) if scores else (0.0, 0.0)
        
        self.chain.final_selection = FinalSelectionEvidence(
            total_results=total_results,
            domain_distribution=domain_distribution,
            domain_cap_applied=domain_cap_applied,
            capped_domains=capped_domains,
            avg_score=avg_score,
            score_range=score_range,
        )
    
    def add_metadata(self, key: str, value: Any):
        """Add custom metadata to evidence chain."""
        if self.enabled and self.chain is not None:
            self.chain.metadata[key] = value
    
    def get_chain(self) -> Optional[EvidenceChain]:
        """Get the complete evidence chain."""
        return self.chain if self.enabled else None
