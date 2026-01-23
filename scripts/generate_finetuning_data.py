#!/usr/bin/env python3
"""
Phase 3.5: Training Data Generator for Fine-Tuned Embeddings

Extracts (question → manual section) pairs from technical procedures for
contrastive learning. Creates high-quality training dataset that respects
domain safety-critical context.

Supports: TXT, PDF, HTML documents

Usage:
    python scripts/generate_finetuning_data.py \
        --corpus-dir data/ \
        --output data/finetuning/training_pairs.jsonl \
        --pairs-per-domain 1000 \
        --include-hard-negatives

Output Format (JSONL):
    {"query": "How do I check tire pressure?", "positive": "Locate valve stem...", "negative": "Engine oil check...", "domain": "vehicle_civilian"}
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

# Optional PDF/HTML support with graceful fallback
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


class DocumentExtractor:
    """Extract text from various document formats (TXT, PDF, HTML)."""
    
    @staticmethod
    def extract_text(file_path: Path) -> Optional[str]:
        """
        Extract text from file, auto-detecting format.
        
        Args:
            file_path: Path to document (TXT, PDF, or HTML)
            
        Returns:
            Extracted text or None if unsupported/failed
        """
        suffix = file_path.suffix.lower()
        
        try:
            if suffix == '.txt':
                return file_path.read_text(encoding='utf-8', errors='ignore')
            elif suffix == '.pdf' and PDF_SUPPORT:
                return DocumentExtractor._extract_pdf(file_path)
            elif suffix == '.html' and HTML_SUPPORT:
                return DocumentExtractor._extract_html(file_path)
            else:
                return None
        except Exception as e:
            logger.warning(f"Error extracting {file_path.name}: {e}")
            return None
    
    @staticmethod
    def _extract_pdf(file_path: Path) -> Optional[str]:
        """Extract text from PDF using pdfplumber."""
        if not PDF_SUPPORT:
            return None
        
        try:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"--- Page {page_num} ---\n{text}")
            
            return '\n\n'.join(text_parts) if text_parts else None
        except Exception as e:
            logger.warning(f"PDF extraction failed for {file_path.name}: {e}")
            return None
    
    @staticmethod
    def _extract_html(file_path: Path) -> Optional[str]:
        """Extract text from HTML using BeautifulSoup."""
        if not HTML_SUPPORT:
            return None
        
        try:
            html_content = file_path.read_text(encoding='utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script/style tags
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            
            # Get text and clean
            text = soup.get_text(separator='\n', strip=True)
            return text if text else None
        except Exception as e:
            logger.warning(f"HTML extraction failed for {file_path.name}: {e}")
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
    """Extract procedures, diagnostics, and parts from technical manuals."""
    
    # Patterns for identifying different content types
    PROCEDURE_HEADERS = re.compile(
        r'^(how to|steps?|procedure|instructions?|process|method|steps for|check|inspect|replace|install|remove|repair)',
        re.IGNORECASE
    )
    
    DIAGNOSTIC_MARKERS = re.compile(
        r'(symptom|cause|diagnosis|troubleshoot|problem|issue|fault|error|warning)',
        re.IGNORECASE
    )
    
    PARTS_MARKERS = re.compile(
        r'(part|component|assembly|module|unit|connector|terminal|bolt|screw|washer)',
        re.IGNORECASE
    )
    
    def __init__(self, min_section_length: int = 100, max_section_length: int = 2000):
        self.min_section_length = min_section_length
        self.max_section_length = max_section_length
    
    def extract_from_text(self, text: str, domain: str) -> List[Tuple[str, str]]:
        """
        Extract (heading, content) pairs from manual text.
        
        Args:
            text: Manual content (markdown or plain text)
            domain: Document domain (e.g., 'vehicle_civilian')
            
        Returns:
            List of (section_heading, section_content) tuples
        """
        sections = []
        
        # Split by common section markers
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            # Detect section headers (lines starting with #, ==, --, or all caps)
            if self._is_header(line):
                # Save previous section
                if current_section and current_content:
                    content_text = '\n'.join(current_content).strip()
                    if self.min_section_length < len(content_text) < self.max_section_length:
                        sections.append((current_section, content_text))
                
                current_section = line.strip().lstrip('#=- ').strip()
                current_content = []
            else:
                if current_section:
                    current_content.append(line)
        
        # Save last section
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
        """Classify section as procedure, diagnostic, or parts."""
        heading_lower = heading.lower()
        content_lower = content.lower()
        
        # Check heading first (more reliable)
        if self.PROCEDURE_HEADERS.search(heading_lower):
            return 'procedure'
        elif self.DIAGNOSTIC_MARKERS.search(heading_lower):
            return 'diagnostic'
        elif self.PARTS_MARKERS.search(heading_lower):
            return 'parts'
        
        # Fallback to content analysis
        if self.PROCEDURE_HEADERS.search(content_lower):
            return 'procedure'
        elif self.DIAGNOSTIC_MARKERS.search(content_lower):
            return 'diagnostic'
        
        return 'general'


class QueryGenerator:
    """Generate synthetic questions from procedures and sections."""
    
    QUESTION_TEMPLATES = {
        'procedure': [
            'How do I {}?',
            'What are the steps to {}?',
            'How to {}?',
            'What is the procedure for {}?',
            'Can you guide me through {}?',
            'What do I need to do to {}?',
        ],
        'diagnostic': [
            'What causes {}?',
            'How do I diagnose {}?',
            'What is the symptom of {}?',
            'How to troubleshoot {}?',
            'What indicates {}?',
        ],
        'parts': [
            'What is a {}?',
            'Where is the {}?',
            'What does the {} do?',
            'How to identify the {}?',
            'What is the function of the {}?',
        ]
    }
    
    def __init__(self):
        self.used_queries = set()
    
    def generate_from_section(self, heading: str, section_type: str) -> List[str]:
        """
        Generate synthetic questions from section heading.
        
        Args:
            heading: Section heading (e.g., "Brake Pad Replacement")
            section_type: Classification (procedure, diagnostic, parts)
            
        Returns:
            List of generated questions
        """
        questions = []
        
        # Extract key terms from heading
        terms = self._extract_key_terms(heading)
        
        if not terms:
            return questions
        
        # Get templates for section type
        templates = self.QUESTION_TEMPLATES.get(section_type, self.QUESTION_TEMPLATES['procedure'])
        
        # Generate questions using templates
        for term in terms:
            for template in templates[:2]:  # Use first 2 templates per term to avoid duplication
                try:
                    question = template.format(term.lower())
                    # Deduplicate
                    if question not in self.used_queries:
                        questions.append(question)
                        self.used_queries.add(question)
                except (IndexError, KeyError):
                    continue
        
        return questions
    
    def _extract_key_terms(self, heading: str) -> List[str]:
        """Extract key terms from heading, removing articles and prepositions."""
        stop_words = {'the', 'a', 'an', 'of', 'in', 'to', 'for', 'and', 'or', 'is', 'are'}
        
        words = heading.lower().split()
        terms = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Also return full heading as term
        if len(terms) >= 2:
            terms.append(heading.lower())
        
        return terms[:5]  # Limit to 5 terms per heading


class TrainingDataGenerator:
    """Main generator for fine-tuning training pairs."""
    
    def __init__(self, corpus_dir: Path, output_dir: Path):
        self.corpus_dir = Path(corpus_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.extractor = ProcedureExtractor()
        self.query_gen = QueryGenerator()
        
        self.training_pairs = []
        self.domain_stats = defaultdict(int)
    
    def generate_dataset(self, pairs_per_domain: int = 1000, include_hard_negatives: bool = True) -> None:
        """
        Generate complete training dataset.
        
        Args:
            pairs_per_domain: Target number of pairs per domain
            include_hard_negatives: Whether to include cross-domain hard negatives
        """
        logger.info(f"🚀 Starting training data generation from {self.corpus_dir}")
        
        # Scan corpus by domain
        domain_sections = self._scan_corpus()
        
        # Generate pairs per domain
        for domain, sections in domain_sections.items():
            logger.info(f"\n📂 Processing domain: {domain} ({len(sections)} sections)")
            
            pairs = self._generate_pairs_for_domain(
                domain, sections, pairs_per_domain, include_hard_negatives
            )
            
            self.training_pairs.extend(pairs)
            self.domain_stats[domain] = len(pairs)
            
            logger.info(f"   ✅ Generated {len(pairs)} pairs for {domain}")
        
        # Save dataset
        output_file = self.output_dir / 'training_pairs.jsonl'
        self._save_jsonl(output_file, self.training_pairs)
        
        logger.info(f"\n📊 Dataset Summary:")
        logger.info(f"   Total pairs: {len(self.training_pairs)}")
        for domain, count in self.domain_stats.items():
            logger.info(f"   - {domain}: {count} pairs")
        
        logger.info(f"\n✅ Saved to {output_file}")
    
    def _scan_corpus(self) -> dict:
        """Scan corpus directory and group sections by domain."""
        domain_sections = defaultdict(list)
        
        # Scan each domain subdirectory
        for domain_dir in self.corpus_dir.iterdir():
            if not domain_dir.is_dir() or domain_dir.name.startswith('.'):
                continue
            
            domain_name = domain_dir.name
            logger.info(f"   Scanning {domain_name}...")
            
            # Read all supported file types from domain
            for file_path in domain_dir.rglob('*'):
                # Skip directories and non-document files
                if file_path.is_dir():
                    continue
                
                if file_path.suffix.lower() not in ['.txt', '.pdf', '.html']:
                    continue
                
                try:
                    text = DocumentExtractor.extract_text(file_path)
                    
                    if not text:
                        logger.debug(f"      Skipped {file_path.name} (empty or unsupported)")
                        continue
                    
                    # Extract sections
                    sections = self.extractor.extract_from_text(text, domain_name)
                    domain_sections[domain_name].extend(sections)
                    
                    logger.debug(f"      Extracted {len(sections)} sections from {file_path.name}")
                    
                except Exception as e:
                    logger.warning(f"      Error processing {file_path.name}: {e}")
        
        return domain_sections
    
    def _generate_pairs_for_domain(
        self,
        domain: str,
        sections: List[Tuple[str, str]],
        target_pairs: int,
        include_hard_negatives: bool
    ) -> List[TrainingPair]:
        """Generate training pairs for a single domain."""
        pairs = []
        
        # Sample sections if too many
        if len(sections) > target_pairs:
            sections = random.sample(sections, target_pairs)
        
        for heading, content in sections:
            # Classify section type
            section_type = self.extractor.identify_section_type(heading, content)
            
            # Generate questions for this section (positive pairs)
            questions = self.query_gen.generate_from_section(heading, section_type)
            
            for question in questions:
                # Create positive pair (query → this content)
                pair = TrainingPair(
                    query=question,
                    positive=content[:512],  # Truncate to first 512 chars
                    negative=self._select_negative(domain, heading, sections),
                    domain=domain,
                    source_section=heading,
                    synthetic=True,
                    hard_negative=include_hard_negatives
                )
                pairs.append(pair)
        
        return pairs[:target_pairs]  # Limit to target
    
    def _select_negative(self, domain: str, heading: str, sections: List[Tuple[str, str]]) -> str:
        """Select a negative example (irrelevant section)."""
        # Pick random section with different heading
        negatives = [s for s in sections if s[0].lower() != heading.lower()]
        
        if negatives:
            _, negative_content = random.choice(negatives)
            return negative_content[:512]
        
        # Fallback: generic negative
        return "Engine oil change procedure. Locate the drain plug beneath the engine..."
    
    def _save_jsonl(self, output_file: Path, pairs: List[TrainingPair]) -> None:
        """Save pairs to JSONL format."""
        with open(output_file, 'w', encoding='utf-8') as f:
            for pair in pairs:
                f.write(json.dumps(pair.to_dict()) + '\n')


def main():
    parser = argparse.ArgumentParser(
        description='Generate fine-tuning training pairs from technical manuals'
    )
    parser.add_argument(
        '--corpus-dir',
        type=Path,
        default=Path('data'),
        help='Path to corpus directory (organized by domain subdirectories)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/finetuning/training_pairs.jsonl'),
        help='Output JSONL file path'
    )
    parser.add_argument(
        '--pairs-per-domain',
        type=int,
        default=1000,
        help='Target number of training pairs per domain'
    )
    parser.add_argument(
        '--include-hard-negatives',
        action='store_true',
        default=True,
        help='Include cross-domain hard negatives for better contrast'
    )
    
    args = parser.parse_args()
    
    # Health check: log supported formats
    logger.info("=" * 60)
    logger.info("Training Data Generator - Health Check")
    logger.info("=" * 60)
    logger.info(f"PDF Support: {'YES (pdfplumber)' if PDF_SUPPORT else 'NO - install: pip install pdfplumber'}")
    logger.info(f"HTML Support: {'YES (BeautifulSoup4)' if HTML_SUPPORT else 'NO - install: pip install beautifulsoup4'}")
    logger.info(f"Corpus Dir: {args.corpus_dir.resolve()}")
    logger.info(f"Output: {args.output.resolve()}")
    logger.info(f"Pairs/Domain: {args.pairs_per_domain}")
    logger.info(f"Hard Negatives: {'ON' if args.include_hard_negatives else 'OFF'}")
    logger.info("=" * 60)
    
    generator = TrainingDataGenerator(args.corpus_dir, args.output.parent)
    generator.generate_dataset(
        pairs_per_domain=args.pairs_per_domain,
        include_hard_negatives=args.include_hard_negatives
    )
    
    logger.info("=" * 60)
    logger.info("Generation Complete")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
