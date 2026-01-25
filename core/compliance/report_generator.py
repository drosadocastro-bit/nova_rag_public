"""
Compliance Reporting Module for NOVA NIC.

Generates tamper-evident audit reports for regulatory compliance:
- Session-level compliance reports (JSON + PDF)
- Batch reporting with aggregate statistics
- SHA-256 tamper detection
- Evidence chain traceability

Compliant with:
- ISO 31000 (Risk Management)
- NIST SP 800-53 SI-4 (Information System Monitoring)
- GDPR Article 32 (Security of Processing)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ComplianceReport:
    """
    Compliance report for a single query session.
    
    Contains complete audit trail for regulatory review.
    """
    
    # Session metadata
    session_id: str
    timestamp: str
    operator: Optional[str] = None
    system_version: str = "1.0.0"
    
    # Query details
    query: str = ""
    domain: str = ""
    intent_classification: str = ""
    
    # Retrieval details
    retrieval_sources: List[str] = field(default_factory=list)
    confidence_scores: List[float] = field(default_factory=list)
    reranking_decisions: Dict[str, Any] = field(default_factory=dict)
    
    # Safety and anomaly detection
    safety_checks: Dict[str, Any] = field(default_factory=dict)
    anomaly_score: float = 0.0
    anomaly_flagged: bool = False
    
    # Response details
    answer: str = ""
    citations: List[str] = field(default_factory=list)
    extractive_fallback_used: bool = False
    
    # Evidence chain
    evidence_chain: Dict[str, Any] = field(default_factory=dict)
    
    # Performance metrics
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Tamper detection
    report_hash: str = ""
    
    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of report content.
        
        Hash excludes the report_hash field itself to enable verification.
        
        Returns:
            SHA-256 hash (hex string)
        """
        # Create copy without hash field
        report_dict = asdict(self)
        report_dict.pop('report_hash', None)
        
        # Sort keys for deterministic hashing
        report_json = json.dumps(report_dict, sort_keys=True, default=str)
        
        # Compute SHA-256
        hash_obj = hashlib.sha256(report_json.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ComplianceReport':
        """Create report from dictionary."""
        return cls(**data)


class ComplianceReporter:
    """
    Generate compliance reports from evidence chains.
    
    Features:
    - JSON report generation
    - PDF report generation (optional)
    - Batch reporting
    - Tamper detection via SHA-256
    """
    
    def __init__(self, output_dir: str = "compliance_reports"):
        """
        Initialize compliance reporter.
        
        Args:
            output_dir: Directory for report output
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ComplianceReporter initialized: output_dir={output_dir}")
    
    def generate_report(
        self,
        session_id: str,
        query: str,
        answer: str,
        evidence_chain: Dict[str, Any],
        operator: Optional[str] = None,
    ) -> ComplianceReport:
        """
        Generate compliance report for a query session.
        
        Args:
            session_id: Unique session identifier
            query: User query
            answer: System response
            evidence_chain: Complete evidence chain dictionary
            operator: Optional operator identifier
            
        Returns:
            ComplianceReport with computed hash
        """
        # Extract data from evidence chain
        report = ComplianceReport(
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            operator=operator,
            system_version=evidence_chain.get('system_version', '1.0.0'),
            
            # Query
            query=query,
            domain=evidence_chain.get('domain', 'unknown'),
            intent_classification=evidence_chain.get('intent', ''),
            
            # Retrieval
            retrieval_sources=[
                doc.get('source', '') for doc in evidence_chain.get('retrieved_documents', [])
            ],
            confidence_scores=[
                doc.get('score', 0.0) for doc in evidence_chain.get('retrieved_documents', [])
            ],
            reranking_decisions=evidence_chain.get('reranking', {}),
            
            # Safety
            safety_checks=evidence_chain.get('safety_checks', {}),
            anomaly_score=evidence_chain.get('anomaly_score', 0.0),
            anomaly_flagged=evidence_chain.get('anomaly_flagged', False),
            
            # Response
            answer=answer,
            citations=evidence_chain.get('citations', []),
            extractive_fallback_used=evidence_chain.get('extractive_fallback', False),
            
            # Full evidence chain
            evidence_chain=evidence_chain,
            
            # Performance
            retrieval_time_ms=evidence_chain.get('retrieval_time_ms', 0.0),
            generation_time_ms=evidence_chain.get('generation_time_ms', 0.0),
            total_time_ms=evidence_chain.get('total_time_ms', 0.0),
        )
        
        # Compute tamper-evident hash
        report.report_hash = report.compute_hash()
        
        return report
    
    def save_json(self, report: ComplianceReport, filename: Optional[str] = None) -> Path:
        """
        Save report as JSON.
        
        Args:
            report: ComplianceReport to save
            filename: Optional custom filename
            
        Returns:
            Path to saved JSON file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{report.session_id}_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Saved JSON report: {output_path}")
        return output_path
    
    def save_pdf(self, report: ComplianceReport, filename: Optional[str] = None) -> Path:
        """
        Save report as PDF.
        
        Args:
            report: ComplianceReport to save
            filename: Optional custom filename
            
        Returns:
            Path to saved PDF file
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from reportlab.lib import colors
        except ImportError:
            logger.warning("reportlab not installed, PDF generation disabled")
            raise ImportError("reportlab required for PDF generation: pip install reportlab")
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{report.session_id}_{timestamp}.pdf"
        
        output_path = self.output_dir / filename
        
        # Create PDF document
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=12,
        )
        
        # Cover page
        story.append(Paragraph("NOVA NIC Compliance Report", title_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Session metadata table
        metadata = [
            ['Session ID:', report.session_id],
            ['Timestamp:', report.timestamp],
            ['Operator:', report.operator or 'N/A'],
            ['System Version:', report.system_version],
            ['Domain:', report.domain],
        ]
        
        meta_table = Table(metadata, colWidths=[2*inch, 4*inch])
        meta_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONT', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#34495e')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Query section
        story.append(Paragraph("Query Details", heading_style))
        story.append(Paragraph(f"<b>Question:</b> {report.query}", styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"<b>Intent:</b> {report.intent_classification or 'N/A'}", styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Safety checks section
        story.append(Paragraph("Safety and Anomaly Detection", heading_style))
        
        safety_data = [
            ['Anomaly Score:', f"{report.anomaly_score:.6f}"],
            ['Anomaly Flagged:', 'Yes' if report.anomaly_flagged else 'No'],
            ['Safety Checks:', 'Passed' if report.safety_checks.get('passed', True) else 'Failed'],
        ]
        
        safety_table = Table(safety_data, colWidths=[2*inch, 4*inch])
        safety_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONT', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(safety_table)
        story.append(Spacer(1, 0.2 * inch))
        
        # Retrieval section
        story.append(Paragraph("Retrieval Evidence", heading_style))
        story.append(Paragraph(f"<b>Sources Retrieved:</b> {len(report.retrieval_sources)}", styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))
        
        if report.confidence_scores:
            avg_confidence = sum(report.confidence_scores) / len(report.confidence_scores)
            story.append(Paragraph(f"<b>Average Confidence:</b> {avg_confidence:.3f}", styles['Normal']))
            story.append(Spacer(1, 0.2 * inch))
        
        # Response section
        story.append(Paragraph("System Response", heading_style))
        story.append(Paragraph(f"<b>Answer:</b>", styles['Normal']))
        story.append(Spacer(1, 0.05 * inch))
        
        # Wrap long answer text
        answer_text = report.answer[:500] + "..." if len(report.answer) > 500 else report.answer
        story.append(Paragraph(answer_text, styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))
        
        story.append(Paragraph(f"<b>Citations:</b> {len(report.citations)}", styles['Normal']))
        story.append(Paragraph(f"<b>Extractive Fallback:</b> {'Yes' if report.extractive_fallback_used else 'No'}", styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
        
        # Performance metrics
        story.append(Paragraph("Performance Metrics", heading_style))
        
        perf_data = [
            ['Retrieval Time:', f"{report.retrieval_time_ms:.1f} ms"],
            ['Generation Time:', f"{report.generation_time_ms:.1f} ms"],
            ['Total Time:', f"{report.total_time_ms:.1f} ms"],
        ]
        
        perf_table = Table(perf_data, colWidths=[2*inch, 4*inch])
        perf_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONT', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(perf_table)
        
        # Page break before hash
        story.append(PageBreak())
        
        # Tamper-evident footer
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("Tamper-Evident Signature", heading_style))
        story.append(Paragraph(
            "<font face='Courier' size='8'>" +
            f"SHA-256: {report.report_hash}" +
            "</font>",
            styles['Code']
        ))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(
            "<i>This hash is computed from the report content. "
            "Any modification to the report will invalidate the hash.</i>",
            styles['Normal']
        ))
        
        # Build PDF
        doc.build(story)
        
        logger.info(f"Saved PDF report: {output_path}")
        return output_path
    
    def verify_json(self, json_path: Path) -> bool:
        """
        Verify tamper detection for JSON report.
        
        Args:
            json_path: Path to JSON report
            
        Returns:
            True if hash matches (report not tampered), False otherwise
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        report = ComplianceReport.from_dict(data)
        stored_hash = report.report_hash
        
        # Recompute hash
        computed_hash = report.compute_hash()
        
        is_valid = stored_hash == computed_hash
        
        if is_valid:
            logger.info(f"Report verification PASSED: {json_path.name}")
        else:
            logger.warning(f"Report verification FAILED: {json_path.name}")
        
        return is_valid
    
    def batch_generate(
        self,
        evidence_chains: List[Dict[str, Any]],
        output_format: str = "json",
    ) -> List[Path]:
        """
        Generate batch compliance reports.
        
        Args:
            evidence_chains: List of evidence chain dictionaries
            output_format: 'json' or 'pdf'
            
        Returns:
            List of paths to generated reports
        """
        output_paths = []
        
        for evidence in evidence_chains:
            try:
                report = self.generate_report(
                    session_id=evidence.get('session_id', 'unknown'),
                    query=evidence.get('query', ''),
                    answer=evidence.get('answer', ''),
                    evidence_chain=evidence,
                    operator=evidence.get('operator'),
                )
                
                if output_format == "json":
                    path = self.save_json(report)
                elif output_format == "pdf":
                    path = self.save_pdf(report)
                else:
                    raise ValueError(f"Unknown format: {output_format}")
                
                output_paths.append(path)
                
            except Exception as e:
                logger.error(f"Failed to generate report for session {evidence.get('session_id')}: {e}")
        
        logger.info(f"Generated {len(output_paths)}/{len(evidence_chains)} batch reports")
        return output_paths
    
    def generate_aggregate_stats(
        self,
        reports: List[ComplianceReport],
    ) -> Dict[str, Any]:
        """
        Generate aggregate statistics from multiple reports.
        
        Args:
            reports: List of ComplianceReport objects
            
        Returns:
            Dictionary with aggregate statistics
        """
        if not reports:
            return {}
        
        total_queries = len(reports)
        
        # Domain distribution
        domain_counts = {}
        for report in reports:
            domain_counts[report.domain] = domain_counts.get(report.domain, 0) + 1
        
        # Anomaly statistics
        anomaly_scores = [r.anomaly_score for r in reports]
        anomalies_flagged = sum(1 for r in reports if r.anomaly_flagged)
        
        # Confidence statistics
        all_confidence_scores = []
        for report in reports:
            all_confidence_scores.extend(report.confidence_scores)
        
        # Performance statistics
        retrieval_times = [r.retrieval_time_ms for r in reports if r.retrieval_time_ms > 0]
        generation_times = [r.generation_time_ms for r in reports if r.generation_time_ms > 0]
        
        stats = {
            "total_queries": total_queries,
            "date_range": {
                "start": min(r.timestamp for r in reports),
                "end": max(r.timestamp for r in reports),
            },
            "domains": domain_counts,
            "anomaly_detection": {
                "total_flagged": anomalies_flagged,
                "flagged_percentage": (anomalies_flagged / total_queries * 100) if total_queries > 0 else 0,
                "avg_score": sum(anomaly_scores) / len(anomaly_scores) if anomaly_scores else 0,
                "max_score": max(anomaly_scores) if anomaly_scores else 0,
            },
            "confidence": {
                "avg": sum(all_confidence_scores) / len(all_confidence_scores) if all_confidence_scores else 0,
                "min": min(all_confidence_scores) if all_confidence_scores else 0,
                "max": max(all_confidence_scores) if all_confidence_scores else 0,
            },
            "performance": {
                "avg_retrieval_ms": sum(retrieval_times) / len(retrieval_times) if retrieval_times else 0,
                "avg_generation_ms": sum(generation_times) / len(generation_times) if generation_times else 0,
            },
        }
        
        return stats
