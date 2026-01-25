"""
Validate Phase 3 corpus downloads.

Checks that downloaded files are:
- Present and readable
- Have valid format (PDF/HTML)
- Contain extractable content
- Have correct domain tags
"""

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results of validating a single file."""
    file_path: str
    domain: str
    exists: bool
    size_bytes: int
    sha256: Optional[str] = None
    format_valid: bool = False
    content_length: int = 0
    page_count: Optional[int] = None
    requires_ocr: bool = False
    errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def is_valid(self) -> bool:
        """Check if file passed validation."""
        return self.exists and self.format_valid and len(self.errors) == 0


class CorpusValidator:
    """Validates corpus documents."""
    
    def __init__(self, corpus_dir: Path):
        """
        Initialize validator.
        
        Args:
            corpus_dir: Root directory of phase3 corpus
        """
        self.corpus_dir = Path(corpus_dir)
        self.results: List[ValidationResult] = []
    
    def validate_all(self) -> None:
        """Validate all files in corpus directory."""
        if not self.corpus_dir.exists():
            logger.error(f"Corpus directory not found: {self.corpus_dir}")
            return
        
        logger.info(f"Validating corpus in: {self.corpus_dir}")
        logger.info("="*60)
        
        # Find all files
        domains = [d for d in self.corpus_dir.iterdir() if d.is_dir()]
        
        for domain_dir in sorted(domains):
            domain = domain_dir.name
            logger.info(f"\nDomain: {domain}")
            logger.info("-"*60)
            
            files = list(domain_dir.glob("*"))
            files = [f for f in files if f.is_file() and f.suffix.lower() in ['.pdf', '.html', '.htm', '.md']]
            
            if not files:
                logger.warning(f"  No files found in {domain}")
                continue
            
            for file_path in sorted(files):
                result = self.validate_file(file_path, domain)
                self.results.append(result)
                self._log_result(result)
    
    def validate_file(self, file_path: Path, domain: str) -> ValidationResult:
        """
        Validate a single file.
        
        Args:
            file_path: Path to file
            domain: Domain tag
        
        Returns:
            ValidationResult object
        """
        result = ValidationResult(
            file_path=str(file_path),
            domain=domain,
            exists=file_path.exists(),
            size_bytes=0
        )
        
        if not file_path.exists():
            result.errors.append("File does not exist")
            return result
        
        # File size
        result.size_bytes = file_path.stat().st_size
        
        # Compute SHA-256
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            result.sha256 = sha256.hexdigest()
        except Exception as e:
            result.errors.append(f"SHA-256 error: {e}")
        
        # Validate based on format
        suffix = file_path.suffix.lower()
        
        if suffix == '.pdf':
            self._validate_pdf(file_path, result)
        elif suffix in ['.html', '.htm']:
            self._validate_html(file_path, result)
        elif suffix == '.md':
            self._validate_markdown(file_path, result)
        else:
            result.errors.append(f"Unsupported format: {suffix}")
        
        return result
    
    def _validate_pdf(self, file_path: Path, result: ValidationResult) -> None:
        """Validate PDF file."""
        try:
            import pypdf
            
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                result.page_count = len(reader.pages)
                
                if result.page_count == 0:
                    result.errors.append("PDF has zero pages")
                    return
                
                # Try to extract text from first page
                first_page = reader.pages[0]
                text = first_page.extract_text()
                result.content_length = len(text.strip())
                
                if result.content_length < 10:
                    result.errors.append("PDF may be scanned (low text extraction)")
                    result.requires_ocr = True
                
                result.format_valid = True
        
        except ImportError:
            result.errors.append("pypdf not installed (pip install pypdf)")
        except Exception as e:
            result.errors.append(f"PDF validation error: {e}")
    
    def _validate_html(self, file_path: Path, result: ValidationResult) -> None:
        """Validate HTML file."""
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract text
            text = soup.get_text().strip()
            result.content_length = len(text)
            
            if result.content_length < 100:
                result.errors.append("HTML has very little text content")
                return
            
            result.format_valid = True
        
        except ImportError:
            result.errors.append("beautifulsoup4 not installed (pip install beautifulsoup4)")
        except Exception as e:
            result.errors.append(f"HTML validation error: {e}")
    
    def _validate_markdown(self, file_path: Path, result: ValidationResult) -> None:
        """Validate Markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result.content_length = len(content.strip())
            
            if result.content_length < 100:
                result.errors.append("Markdown file is very short")
                return
            
            result.format_valid = True
        
        except Exception as e:
            result.errors.append(f"Markdown validation error: {e}")
    
    def _log_result(self, result: ValidationResult) -> None:
        """Log validation result."""
        status = "✓" if result.is_valid else "✗"
        size_mb = result.size_bytes / (1024 * 1024)
        
        logger.info(f"  {status} {Path(result.file_path).name}")
        logger.info(f"      Size: {size_mb:.2f} MB")
        
        if result.page_count:
            logger.info(f"      Pages: {result.page_count}")
        
        if result.content_length:
            logger.info(f"      Content: {result.content_length} chars")
        
        if result.sha256:
            logger.info(f"      SHA-256: {result.sha256[:16]}...")
        
        if result.requires_ocr:
            logger.warning(f"      ⚠ Requires OCR")
        
        if result.errors:
            for error in result.errors:
                logger.error(f"      Error: {error}")
    
    def generate_report(self) -> Dict:
        """Generate validation report."""
        total = len(self.results)
        valid = sum(1 for r in self.results if r.is_valid)
        invalid = total - valid
        
        total_size = sum(r.size_bytes for r in self.results)
        total_size_mb = total_size / (1024 * 1024)
        
        # Group by domain
        domains = {}
        for result in self.results:
            if result.domain not in domains:
                domains[result.domain] = {
                    "files": 0,
                    "valid": 0,
                    "size_bytes": 0
                }
            domains[result.domain]["files"] += 1
            if result.is_valid:
                domains[result.domain]["valid"] += 1
            domains[result.domain]["size_bytes"] += result.size_bytes
        
        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "corpus_directory": str(self.corpus_dir),
            "summary": {
                "total_files": total,
                "valid_files": valid,
                "invalid_files": invalid,
                "total_size_mb": round(total_size_mb, 2),
                "success_rate": round(valid / total * 100, 1) if total > 0 else 0
            },
            "by_domain": domains,
            "files": [asdict(r) for r in self.results]
        }
        
        return report
    
    def save_report(self, output_path: Path) -> None:
        """Save validation report to JSON."""
        report = self.generate_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\nReport saved to: {output_path}")
    
    def print_summary(self) -> None:
        """Print validation summary."""
        report = self.generate_report()
        summary = report["summary"]
        
        logger.info("\n" + "="*60)
        logger.info("VALIDATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Total files: {summary['total_files']}")
        logger.info(f"Valid: {summary['valid_files']}")
        logger.info(f"Invalid: {summary['invalid_files']}")
        logger.info(f"Total size: {summary['total_size_mb']:.2f} MB")
        logger.info(f"Success rate: {summary['success_rate']:.1f}%")
        
        logger.info("\nBy Domain:")
        for domain, stats in report["by_domain"].items():
            size_mb = stats["size_bytes"] / (1024 * 1024)
            logger.info(f"  {domain}:")
            logger.info(f"    Files: {stats['files']} ({stats['valid']} valid)")
            logger.info(f"    Size: {size_mb:.2f} MB")
        
        if summary['invalid_files'] > 0:
            logger.warning("\n⚠ Some files failed validation. See errors above.")
        else:
            logger.info("\n✓ All files passed validation!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate Phase 3 corpus downloads")
    parser.add_argument(
        '--corpus-dir',
        type=str,
        default="data/phase3_corpus",
        help="Path to phase3 corpus directory"
    )
    parser.add_argument(
        '--output',
        type=str,
        default="data/phase3_corpus/validation_report.json",
        help="Path for validation report JSON"
    )
    
    args = parser.parse_args()
    
    # Validate
    validator = CorpusValidator(corpus_dir=Path(args.corpus_dir))
    validator.validate_all()
    
    # Generate report
    validator.print_summary()
    validator.save_report(Path(args.output))
    
    logger.info("\n" + "="*60)
    logger.info("Next steps:")
    logger.info("1. Fix any validation errors")
    logger.info("2. Run hot-reload API: curl -X POST http://localhost:5000/api/reload?dry_run=true")
    logger.info("3. Ingest corpus: curl -X POST http://localhost:5000/api/reload")
    logger.info("="*60)


if __name__ == "__main__":
    main()
