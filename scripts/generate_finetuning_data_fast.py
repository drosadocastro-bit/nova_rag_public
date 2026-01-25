#!/usr/bin/env python3
"""
Phase 3.5: Training Data Generator (Optimized for Large Corpora)

Fast variant that:
- Samples large HTML/PDF documents (max 100 pages per file)
- Skips diagrams folder
- Targets 10k+ pairs with smart domain distribution
- Adds health checks and progress tracking

Usage:
    python scripts/generate_finetuning_data_fast.py --corpus-dir data --output data/finetuning/training_pairs.jsonl
"""

import argparse
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from collections import defaultdict
import random

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
    HTML_SUPPORT = True
except ImportError:
    HTML_SUPPORT = False
    BeautifulSoup = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DocumentExtractorFast:
    """Extract text from documents with sampling for large files."""
    
    MAX_PAGES_PDF = 100  # Sample max 100 pages per PDF
    MAX_LINES_TXT = 50000  # Sample max 50k lines from TXT
    
    @staticmethod
    def extract_text(file_path: Path) -> Optional[str]:
        """Extract text, sampling large documents."""
        suffix = file_path.suffix.lower()
        
        try:
            if suffix == '.txt':
                return DocumentExtractorFast._extract_txt(file_path)
            elif suffix == '.pdf' and PDF_SUPPORT:
                return DocumentExtractorFast._extract_pdf(file_path)
            elif suffix == '.html' and HTML_SUPPORT:
                return DocumentExtractorFast._extract_html(file_path)
            else:
                return None
        except Exception as e:
            logger.warning(f"Error extracting {file_path.name}: {e}")
            return None
    
    @staticmethod
    def _extract_txt(file_path: Path) -> Optional[str]:
        """Extract from TXT with line sampling."""
        try:
            lines = file_path.read_text(encoding='utf-8', errors='ignore').split('\n')
            if len(lines) > DocumentExtractorFast.MAX_LINES_TXT:
                sampled = random.sample(range(len(lines)), DocumentExtractorFast.MAX_LINES_TXT)
                lines = [lines[i] for i in sorted(sampled)]
            return '\n'.join(lines) if lines else None
        except Exception as e:
            logger.warning(f"TXT extraction failed: {e}")
            return None
    
    @staticmethod
    def _extract_pdf(file_path: Path) -> Optional[str]:
        """Extract from PDF with page sampling and robust error handling."""
        if not PDF_SUPPORT or pdfplumber is None:
            return None
        
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                
                # Sample pages if too many
                if total_pages > DocumentExtractorFast.MAX_PAGES_PDF:
                    page_indices = sorted(random.sample(range(total_pages), DocumentExtractorFast.MAX_PAGES_PDF))
                else:
                    page_indices = list(range(total_pages))
                
                text_parts = []
                failed_pages = 0
                
                for page_num in page_indices:
                    try:
                        page = pdf.pages[page_num]
                        text = page.extract_text()
                        if text and len(text.strip()) > 50:
                            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
                    except Exception:
                        # Skip problematic pages gracefully
                        failed_pages += 1
                        if failed_pages > 10:
                            break  # Stop trying if too many failures
                        continue
                
                if not text_parts and failed_pages > 0:
                    logger.warning(f"PDF {file_path.name}: could not extract text from {failed_pages} pages")
                
                return '\n\n'.join(text_parts) if text_parts else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {file_path.name}: {type(e).__name__}")
            return None
    
    @staticmethod
    def _extract_html(file_path: Path) -> Optional[str]:
        """Extract from HTML with smart sampling."""
        if not HTML_SUPPORT or BeautifulSoup is None:
            return None
        
        try:
            html_content = file_path.read_text(encoding='utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove bloat
            for tag in soup(['script', 'style', 'nav', 'footer', 'noscript']):
                tag.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            
            # Sample if too large
            lines = text.split('\n')
            if len(lines) > DocumentExtractorFast.MAX_LINES_TXT:
                sampled = random.sample(range(len(lines)), DocumentExtractorFast.MAX_LINES_TXT)
                lines = [lines[i] for i in sorted(sampled)]
            
            return '\n'.join(lines) if lines else None
        except Exception as e:
            logger.warning(f"HTML extraction failed: {e}")
            return None


@dataclass
class TrainingPair:
    """Single training example for contrastive learning."""
    query: str
    positive: str
    negative: str
    domain: str
    source_section: str
    synthetic: bool = False
    hard_negative: bool = False
    
    def to_dict(self) -> dict:
        return {
            'query': self.query,
            'positive': self.positive,
            'negative': self.negative,
            'domain': self.domain,
            'source_section': self.source_section,
            'synthetic': self.synthetic,
            'hard_negative': self.hard_negative
        }


class ProcedureExtractor:
    """Extract procedures from text."""
    
    PROCEDURE_HEADERS = re.compile(
        r'^(how to|steps?|procedure|instructions?|process|method|check|inspect|replace|install)',
        re.IGNORECASE
    )
    
    def __init__(self, min_section_length: int = 100, max_section_length: int = 2000):
        self.min_section_length = min_section_length
        self.max_section_length = max_section_length
    
    def extract_from_text(self, text: str, domain: str) -> List[Tuple[str, str]]:
        """Extract sections from text."""
        sections = []
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            if self._is_header(line):
                if current_section and current_content:
                    content_text = '\n'.join(current_content).strip()
                    if self.min_section_length < len(content_text) < self.max_section_length:
                        sections.append((current_section, content_text))
                
                current_section = line.strip().lstrip('#=- ').strip()
                current_content = []
            else:
                if current_section:
                    current_content.append(line)
        
        if current_section and current_content:
            content_text = '\n'.join(current_content).strip()
            if self.min_section_length < len(content_text) < self.max_section_length:
                sections.append((current_section, content_text))
        
        return sections
    
    def _is_header(self, line: str) -> bool:
        """Check if line is a section header."""
        stripped = line.strip()
        return (
            stripped.startswith('#') or
            stripped.startswith('==') or
            stripped.startswith('--') or
            (len(stripped) > 3 and stripped.isupper() and len(stripped.split()) < 10)
        )
    
    def identify_section_type(self, heading: str, content: str) -> str:
        """Classify section type."""
        heading_lower = heading.lower()
        if self.PROCEDURE_HEADERS.search(heading_lower):
            return 'procedure'
        return 'general'


class QueryGenerator:
    """Generate synthetic questions."""
    
    TEMPLATES = [
        'How do I {}?',
        'What are the steps to {}?',
        'How to {}?',
        'Can you guide me through {}?',
    ]
    
    def __init__(self):
        self.used_queries = set()
    
    def generate_from_section(self, heading: str) -> List[str]:
        """Generate questions from heading."""
        questions = []
        terms = self._extract_key_terms(heading)
        
        for term in terms:
            for template in self.TEMPLATES[:2]:
                try:
                    q = template.format(term.lower())
                    if q not in self.used_queries:
                        questions.append(q)
                        self.used_queries.add(q)
                except Exception:
                    continue
        
        return questions
    
    def _extract_key_terms(self, heading: str) -> List[str]:
        """Extract key terms from heading."""
        stop_words = {'the', 'a', 'an', 'of', 'in', 'to', 'for', 'and', 'or', 'is'}
        words = heading.lower().split()
        terms = [w for w in words if w not in stop_words and len(w) > 2]
        if len(terms) >= 2:
            terms.append(heading.lower())
        return terms[:5]


class TrainingDataGenerator:
    """Main generator for training pairs."""
    
    # Skip these domains (diagrams, etc)
    SKIP_DIRS = {'diagrams', 'finetuning', '__pycache__'}
    
    def __init__(self, corpus_dir: Path, output_dir: Path):
        self.corpus_dir = Path(corpus_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.extractor = ProcedureExtractor()
        self.query_gen = QueryGenerator()
        
        self.training_pairs = []
        self.domain_stats = defaultdict(int)
    
    def generate_dataset(self, pairs_per_domain: int = 1500, include_hard_negatives: bool = True) -> None:
        """Generate complete dataset with smart targeting."""
        logger.info(f"Starting training data generation (targeting {pairs_per_domain} pairs/domain)...")
        
        domain_sections = self._scan_corpus()
        
        for domain, sections in domain_sections.items():
            logger.info(f"\nProcessing {domain}: {len(sections)} sections")
            
            pairs = self._generate_pairs_for_domain(
                domain, sections, pairs_per_domain, include_hard_negatives
            )
            
            self.training_pairs.extend(pairs)
            self.domain_stats[domain] = len(pairs)
            logger.info(f"  -> Generated {len(pairs)} pairs")
        
        # Save
        output_file = self.output_dir / 'training_pairs.jsonl'
        self._save_jsonl(output_file, self.training_pairs)
        
        logger.info("\n%s", "=" * 60)
        logger.info("DATASET SUMMARY")
        logger.info("%s", "=" * 60)
        logger.info(f"Total pairs: {len(self.training_pairs)}")
        for domain, count in sorted(self.domain_stats.items()):
            pct = 100 * count / len(self.training_pairs) if self.training_pairs else 0
            logger.info(f"  {domain}: {count} ({pct:.1f}%)")
        logger.info(f"Output: {output_file}")
        logger.info(f"{'=' * 60}")
    
    def _scan_corpus(self) -> dict:
        """Scan and extract from all documents with skip on error."""
        domain_sections = defaultdict(list)
        
        for domain_dir in self.corpus_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name in self.SKIP_DIRS:
                continue
            
            domain_name = domain_dir.name
            logger.info(f"  Scanning {domain_name}...")
            
            files_processed = 0
            files_failed = 0
            
            for file_path in domain_dir.rglob('*'):
                if file_path.is_dir() or file_path.suffix.lower() not in ['.txt', '.pdf', '.html']:
                    continue
                
                try:
                    text = DocumentExtractorFast.extract_text(file_path)
                    if text and len(text) > 500:
                        sections = self.extractor.extract_from_text(text, domain_name)
                        domain_sections[domain_name].extend(sections)
                        files_processed += 1
                    else:
                        files_failed += 1
                except Exception as e:
                    files_failed += 1
                    logger.debug(f"    Skipped {file_path.name}: {type(e).__name__}")
            
            if files_processed > 0:
                logger.info(f"    -> Processed {files_processed} files, {len(domain_sections[domain_name])} sections")
        
        return domain_sections
    
    def _generate_pairs_for_domain(
        self, domain: str, sections: List[Tuple[str, str]], target: int, hard_neg: bool
    ) -> List[TrainingPair]:
        """Generate pairs for domain."""
        pairs = []
        
        if len(sections) > target:
            sections = random.sample(sections, target)
        
        for heading, content in sections:
            questions = self.query_gen.generate_from_section(heading)
            
            for question in questions:
                pair = TrainingPair(
                    query=question,
                    positive=content[:512],
                    negative=self._select_negative(domain, sections),
                    domain=domain,
                    source_section=heading,
                    synthetic=True,
                    hard_negative=hard_neg
                )
                pairs.append(pair)
        
        return pairs[:target]
    
    def _select_negative(self, domain: str, sections: List[Tuple[str, str]]) -> str:
        """Select a negative example."""
        negatives = [s[1] for s in sections]
        if negatives:
            return random.choice(negatives)[:512]
        return "Engine maintenance procedure"
    
    def _save_jsonl(self, output_file: Path, pairs: List[TrainingPair]) -> None:
        """Save to JSONL."""
        with open(output_file, 'w', encoding='utf-8') as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + '\n')


def main():
    parser = argparse.ArgumentParser(description='Fast training data generator')
    parser.add_argument('--corpus-dir', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('data/finetuning/training_pairs.jsonl'))
    parser.add_argument('--pairs-per-domain', type=int, default=1500)
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Training Data Generator (Fast) - Health Check")
    logger.info("=" * 60)
    logger.info(f"PDF Support: {'YES' if PDF_SUPPORT else 'NO'}")
    logger.info(f"HTML Support: {'YES' if HTML_SUPPORT else 'NO'}")
    logger.info(f"Corpus: {args.corpus_dir}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Target/Domain: {args.pairs_per_domain}")
    logger.info("=" * 60 + "\n")
    
    generator = TrainingDataGenerator(args.corpus_dir, args.output.parent)
    generator.generate_dataset(pairs_per_domain=args.pairs_per_domain, include_hard_negatives=True)


if __name__ == '__main__':
    main()
