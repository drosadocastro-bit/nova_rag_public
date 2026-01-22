"""
Robust PDF extraction utility with multiple fallback methods.

Handles diverse PDF formats: native text, corrupted fonts, scanned OCR, old formats.
Methods tried in order: pypdf → pdfplumber → Tesseract OCR
"""

import logging
from pathlib import Path
from typing import Tuple, List, Optional
import warnings

from pypdf import PdfReader
import pdfplumber

try:
    import pytesseract
    from PIL import Image
    import pdf2image  # type: ignore
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None  # type: ignore
    pdf2image = None  # type: ignore
    print("[WARN] pytesseract/pdf2image not available. OCR fallback will be skipped.")

logger = logging.getLogger(__name__)


class RobustPDFExtractor:
    """Extracts text from PDFs using multiple fallback methods."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.extraction_methods_used: dict = {}

    def extract_with_pypdf(self, pdf_path: Path) -> Tuple[str, str]:
        """Try pypdf (fast, native text extraction)."""
        try:
            with open(pdf_path, 'rb') as f:
                reader = PdfReader(f)
                text_parts = []
                for page_num, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    except Exception as e:
                        if self.verbose:
                            logger.warning(f"  pypdf page {page_num}: {e}")
                text = "\n\n".join(text_parts)
                return text, "pypdf"
        except Exception as e:
            if self.verbose:
                logger.debug(f"pypdf failed: {e}")
            return "", ""

    def extract_with_pdfplumber(self, pdf_path: Path) -> Tuple[str, str]:
        """Try pdfplumber (better at handling difficult PDFs)."""
        try:
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    except Exception as e:
                        if self.verbose:
                            logger.warning(f"  pdfplumber page {page_num}: {e}")
            text = "\n\n".join(text_parts)
            return text, "pdfplumber"
        except Exception as e:
            if self.verbose:
                logger.debug(f"pdfplumber failed: {e}")
            return "", ""

    def extract_with_tesseract(self, pdf_path: Path) -> Tuple[str, str]:
        """Fall back to Tesseract OCR for scanned PDFs."""
        if not TESSERACT_AVAILABLE:
            if self.verbose:
                logger.warning("Tesseract not available (install pytesseract and tesseract-ocr)")
            return "", ""

        try:
            # Convert PDF to images
            images = pdf2image.convert_from_path(pdf_path, dpi=200)  # type: ignore
            if not images:
                return "", ""

            text_parts = []
            for page_num, image in enumerate(images):
                try:
                    # Extract text using Tesseract
                    text = pytesseract.image_to_string(image)  # type: ignore
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    if self.verbose:
                        logger.warning(f"  Tesseract page {page_num}: {e}")

            text = "\n\n".join(text_parts)
            return text, "tesseract_ocr"
        except Exception as e:
            if self.verbose:
                logger.debug(f"Tesseract OCR failed: {e}")
            return "", ""

    def extract_text(self, pdf_path: Path) -> Tuple[str, str, List[str]]:
        """
        Extract text from PDF using multiple fallback methods.
        
        Returns (text, method_used, methods_attempted)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return "", "", []

        methods_attempted = []

        # Try method 1: pypdf (fastest, handles native text)
        text, method = self.extract_with_pypdf(pdf_path)
        methods_attempted.append(method if method else "pypdf_failed")
        if text and len(text.strip()) > 100:  # Reasonable amount of text
            if self.verbose:
                logger.info(f"✓ Extracted via {method}")
            return text, method, methods_attempted

        # Try method 2: pdfplumber (better error handling)
        if self.verbose:
            logger.info("  pypdf insufficient text, trying pdfplumber...")
        text, method = self.extract_with_pdfplumber(pdf_path)
        methods_attempted.append(method if method else "pdfplumber_failed")
        if text and len(text.strip()) > 100:
            if self.verbose:
                logger.info(f"✓ Extracted via {method}")
            return text, method, methods_attempted

        # Try method 3: Tesseract OCR (slowest, handles scanned PDFs)
        if self.verbose:
            logger.info("  pdfplumber insufficient text, trying Tesseract OCR...")
        text, method = self.extract_with_tesseract(pdf_path)
        methods_attempted.append(method if method else "tesseract_failed")
        if text and len(text.strip()) > 100:
            if self.verbose:
                logger.info(f"✓ Extracted via {method}")
            return text, method, methods_attempted

        # All methods failed
        if self.verbose:
            logger.error(f"✗ Could not extract text from {pdf_path.name}")
            logger.error(f"  Methods attempted: {', '.join(methods_attempted)}")

        return "", "none", methods_attempted


def test_extraction(pdf_path: Path) -> None:
    """Test extraction on a single PDF."""
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_path.name}")
    print(f"{'='*70}")

    extractor = RobustPDFExtractor(verbose=True)
    text, method, methods = extractor.extract_text(pdf_path)

    print(f"\nMethods attempted: {' → '.join(methods)}")
    print(f"Final method: {method}")
    print(f"Text extracted: {len(text)} characters")
    if text:
        print(f"\nFirst 300 chars:\n{text[:300]}...")


if __name__ == "__main__":
    # Test on all PDFs in data/
    data_dir = Path("data")
    for pdf_file in sorted(data_dir.rglob("*.pdf")):
        test_extraction(pdf_file)
