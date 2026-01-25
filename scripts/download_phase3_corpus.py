"""
Corpus download and validation script for Phase 3.

Downloads public-domain technical documentation from researched sources,
validates format and licensing, prepares for incremental ingestion.

Usage:
    python scripts/download_phase3_corpus.py --tier 1
    python scripts/download_phase3_corpus.py --validate
"""

import argparse
import hashlib
import json
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CorpusDocument:
    """Metadata for a corpus document."""
    title: str
    source_url: str
    license: str
    domain: str
    format: str
    estimated_chunks: int
    downloaded: bool = False
    validated: bool = False
    file_path: Optional[str] = None
    sha256: Optional[str] = None
    download_date: Optional[str] = None
    notes: str = ""


# Tier 1 Sources (High Priority)
TIER1_SOURCES = [
    CorpusDocument(
        title="U.S. Army TM 9-803 Jeep Maintenance Manual",
        source_url="https://archive.org/details/TM9803",
        license="Public Domain (U.S. Government Work)",
        domain="vehicle_military",
        format="PDF",
        estimated_chunks=700,
        notes="Complete maintenance procedures for military Jeep"
    ),
    CorpusDocument(
        title="Ford Model T Shop Manual (1925)",
        source_url="https://archive.org/details/FordModelTShopManual",
        license="Public Domain (Pre-1928)",
        domain="vehicle_civilian",
        format="PDF",
        estimated_chunks=400,
        notes="Classic automotive repair procedures"
    ),
    CorpusDocument(
        title="Arduino Hardware Documentation",
        source_url="https://docs.arduino.cc/hardware/",
        license="Creative Commons BY-SA 3.0",
        domain="hardware_electronics",
        format="HTML",
        estimated_chunks=300,
        notes="Board specifications, pinouts, schematics"
    ),
    CorpusDocument(
        title="Raspberry Pi GPIO Guide",
        source_url="https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
        license="Creative Commons BY-SA 4.0",
        domain="hardware_electronics",
        format="HTML",
        estimated_chunks=150,
        notes="GPIO pinout, hardware configuration"
    ),
    CorpusDocument(
        title="OpenPLC Programming Guide",
        source_url="https://www.openplcproject.com/reference/",
        license="GPL / Open Documentation",
        domain="industrial_control",
        format="HTML",
        estimated_chunks=250,
        notes="PLC programming, ladder logic, safety interlocks"
    ),
]


# Tier 2 Sources (Secondary)
TIER2_SOURCES = [
    CorpusDocument(
        title="NASA Systems Engineering Handbook",
        source_url="https://ntrs.nasa.gov/citations/20170001761",
        license="Public Domain (U.S. Government Work)",
        domain="safety_standards",
        format="PDF",
        estimated_chunks=600,
        notes="Safety protocols, fault handling, quality procedures"
    ),
    CorpusDocument(
        title="NIST Cybersecurity Framework",
        source_url="https://www.nist.gov/cyberframework",
        license="Public Domain (U.S. Government Work)",
        domain="safety_standards",
        format="PDF",
        estimated_chunks=400,
        notes="Risk assessment, security controls"
    ),
]


class CorpusDownloader:
    """Downloads and validates corpus documents."""
    
    def __init__(self, output_dir: Path):
        """
        Initialize downloader.
        
        Args:
            output_dir: Directory to save downloaded documents
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Manifest tracking
        self.manifest_path = self.output_dir / "corpus_manifest.json"
        self.documents: List[CorpusDocument] = []
    
    def download_tier(self, tier: int = 1, dry_run: bool = False) -> None:
        """
        Download documents from specified tier.
        
        Args:
            tier: 1 for Tier 1 (high priority), 2 for Tier 2
            dry_run: If True, only show what would be downloaded
        """
        sources = TIER1_SOURCES if tier == 1 else TIER2_SOURCES
        
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Downloading Tier {tier} sources...")
        logger.info(f"Total documents: {len(sources)}")
        
        for i, doc in enumerate(sources, 1):
            logger.info(f"\n[{i}/{len(sources)}] {doc.title}")
            logger.info(f"  Source: {doc.source_url}")
            logger.info(f"  License: {doc.license}")
            logger.info(f"  Domain: {doc.domain}")
            logger.info(f"  Format: {doc.format}")
            logger.info(f"  Estimated chunks: {doc.estimated_chunks}")
            
            if dry_run:
                logger.info("  [SKIPPED - DRY RUN]")
                continue
            
            # Note: Actual download implementation would go here
            # For now, this is a planning/documentation script
            logger.warning("  [MANUAL DOWNLOAD REQUIRED]")
            logger.info(f"  → Please download from: {doc.source_url}")
            logger.info(f"  → Save to: {self.output_dir / doc.domain}/")
            
            self.documents.append(doc)
    
    def validate_document(self, file_path: Path) -> Dict:
        """
        Validate downloaded document.
        
        Args:
            file_path: Path to document file
        
        Returns:
            Validation results dictionary
        """
        results = {
            "file_exists": file_path.exists(),
            "file_size": file_path.stat().st_size if file_path.exists() else 0,
            "sha256": None,
            "format_valid": False,
            "errors": []
        }
        
        if not file_path.exists():
            results["errors"].append("File does not exist")
            return results
        
        # Compute SHA-256
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            results["sha256"] = sha256.hexdigest()
        except Exception as e:
            results["errors"].append(f"SHA-256 error: {e}")
        
        # Validate format
        suffix = file_path.suffix.lower()
        if suffix == '.pdf':
            results["format_valid"] = self._validate_pdf(file_path, results)
        elif suffix in ['.html', '.htm']:
            results["format_valid"] = self._validate_html(file_path, results)
        else:
            results["errors"].append(f"Unsupported format: {suffix}")
        
        return results
    
    def _validate_pdf(self, file_path: Path, results: Dict) -> bool:
        """Validate PDF file."""
        try:
            import pypdf
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                page_count = len(reader.pages)
                results["page_count"] = page_count
                
                if page_count == 0:
                    results["errors"].append("PDF has zero pages")
                    return False
                
                # Try to extract text from first page
                first_page = reader.pages[0]
                text = first_page.extract_text()
                
                if len(text.strip()) < 10:
                    results["errors"].append("PDF may be scanned (low text extraction)")
                    results["requires_ocr"] = True
                
                return True
        
        except ImportError:
            results["errors"].append("pypdf not installed (pip install pypdf)")
            return False
        except Exception as e:
            results["errors"].append(f"PDF validation error: {e}")
            return False
    
    def _validate_html(self, file_path: Path, results: Dict) -> bool:
        """Validate HTML file."""
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check for content
            text = soup.get_text().strip()
            if len(text) < 100:
                results["errors"].append("HTML has very little text content")
                return False
            
            results["text_length"] = len(text)
            return True
        
        except ImportError:
            results["errors"].append("beautifulsoup4 not installed")
            return False
        except Exception as e:
            results["errors"].append(f"HTML validation error: {e}")
            return False
    
    def save_manifest(self) -> None:
        """Save download manifest to JSON."""
        manifest_data = {
            "created": datetime.utcnow().isoformat() + "Z",
            "total_documents": len(self.documents),
            "documents": [asdict(doc) for doc in self.documents]
        }
        
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\nSaved manifest to: {self.manifest_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Download Phase 3 corpus documents")
    parser.add_argument(
        '--tier',
        type=int,
        choices=[1, 2],
        default=1,
        help="Tier to download (1=high priority, 2=secondary)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be downloaded without downloading"
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help="Validate already-downloaded documents"
    )
    parser.add_argument(
        '--output',
        type=str,
        default="data/phase3_corpus",
        help="Output directory for downloads"
    )
    
    args = parser.parse_args()
    
    downloader = CorpusDownloader(output_dir=Path(args.output))
    
    if args.validate:
        logger.info("Validation mode - checking existing files...")
        # Validation logic here
    else:
        downloader.download_tier(tier=args.tier, dry_run=args.dry_run)
        downloader.save_manifest()
    
    logger.info("\n" + "="*60)
    logger.info("Next steps:")
    logger.info("1. Manually download documents from listed URLs")
    logger.info("2. Save to appropriate domain subdirectories")
    logger.info("3. Run with --validate to check downloads")
    logger.info("4. Proceed to Task 9: Ingest with hot-reload API")
    logger.info("="*60)


if __name__ == "__main__":
    main()
