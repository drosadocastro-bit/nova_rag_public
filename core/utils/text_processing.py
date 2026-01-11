"""
Text processing utilities for chunking and PDF extraction.
"""

from pathlib import Path
import re
from pypdf import PdfReader


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


def load_pdf_text_with_pages(pdf_path: Path) -> list[tuple[str, int]]:
    """Load PDF and return list of (text, page_number) tuples."""
    reader = PdfReader(str(pdf_path))
    pages_data: list[tuple[str, int]] = []

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - broad to keep PDF parsing resilient
            print(f"[!] Error reading page {i} from {pdf_path.name}: {exc}")
            txt = ""
        pages_data.append((txt, i + 1))

    return pages_data


def load_pdf_text(pdf_path: Path) -> str:
    """Legacy function for compatibility."""
    pages_data = load_pdf_text_with_pages(pdf_path)
    return "\n".join(text for text, _ in pages_data)