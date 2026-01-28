"""
Text processing utilities for chunking and PDF extraction.
"""

from pathlib import Path
import re
from pypdf import PdfReader

# Optional OCR support
OCR_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_path
    import shutil
    
    # Set Tesseract path for Windows if not in PATH
    if shutil.which("tesseract") is None:
        tesseract_paths = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
        for tess_path in tesseract_paths:
            if tess_path.exists():
                pytesseract.pytesseract.tesseract_cmd = str(tess_path)
                OCR_AVAILABLE = True
                break
        else:
            print("[NovaRAG] Tesseract not found in PATH or standard locations")
    else:
        OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    convert_from_path = None


def split_text_semantic(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text with semantic awareness, keeping paragraph and sentence boundaries when possible."""
    paragraphs = re.split(r"\n\s*\n", text)

    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk)

            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                temp_chunk = ""
                for sent in sentences:
                    if len(temp_chunk) + len(sent) + 1 <= chunk_size:
                        temp_chunk += (" " if temp_chunk else "") + sent
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk)
                        temp_chunk = sent
                current_chunk = temp_chunk
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]
            overlap_text = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
            overlapped_chunks.append(overlap_text + "\n" + curr_chunk)
        return overlapped_chunks

    return chunks


def split_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Fallback to semantic chunking."""
    return split_text_semantic(text, chunk_size, overlap)


def _try_ocr_on_page(pdf_path: Path, page_num: int) -> str:
    """Try to extract text from a scanned PDF page using OCR."""
    if not OCR_AVAILABLE or convert_from_path is None or pytesseract is None:
        return ""
    
    try:
        # Convert just this page to image
        images = convert_from_path(
            pdf_path,
            dpi=200,  # Higher DPI for better OCR accuracy
            first_page=page_num,
            last_page=page_num
        )
        if images:
            text = pytesseract.image_to_string(images[0], lang='eng')
            return text.strip()
    except Exception as e:
        print(f"[!] OCR failed for page {page_num} of {pdf_path.name}: {e}")
    return ""


def load_pdf_text_with_pages(pdf_path: Path) -> list[tuple[str, int]]:
    """
    Load PDF and return list of (text, page_number) tuples.
    Attempts OCR on pages with little/no text if OCR is available.
    """
    reader = PdfReader(str(pdf_path))
    pages_data: list[tuple[str, int]] = []
    ocr_pages = []

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - broad to keep PDF parsing resilient
            print(f"[!] Error reading page {i} from {pdf_path.name}: {exc}")
            txt = ""
        
        # If page has very little text (likely scanned/image), try OCR
        if len(txt.strip()) < 50 and OCR_AVAILABLE:
            ocr_text = _try_ocr_on_page(pdf_path, i + 1)
            if len(ocr_text) > len(txt):
                txt = ocr_text
                ocr_pages.append(i + 1)
        
        pages_data.append((txt, i + 1))
    
    if ocr_pages:
        print(f"   [OCR] Extracted {len(ocr_pages)} scanned pages from {pdf_path.name}")

    return pages_data


def load_pdf_text(pdf_path: Path) -> str:
    """Legacy function for compatibility."""
    pages_data = load_pdf_text_with_pages(pdf_path)
    return "\n".join(text for text, _ in pages_data)