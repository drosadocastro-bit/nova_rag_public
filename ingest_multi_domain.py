"""
Multi-domain PDF ingestion script with cross-contamination tracking.

Extracts PDFs from data/ subdirectories, tags by domain, chunks text,
and stores in FAISS with metadata for measuring retrieval accuracy by domain.
"""

import os
import re
import pickle
import json
import faiss
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from sentence_transformers import SentenceTransformer
import pdfplumber

# Optional HTML support
try:
    from bs4 import BeautifulSoup
    HTML_SUPPORT_AVAILABLE = True
except ImportError:
    HTML_SUPPORT_AVAILABLE = False

# Configuration
DATA_DIR = Path("data")
VECTOR_DB_DIR = Path("vector_db")
CHUNK_SIZE = 500  # Characters per chunk
OVERLAP = 100     # Character overlap between chunks
METADATA_FILE = "vector_db/domain_metadata.json"
CHUNKS_FILE = "vector_db/chunks_with_metadata.pkl"
FAISS_INDEX_FILE = "vector_db/faiss_index_multi_domain.bin"

# Domain definitions
DOMAIN_CONFIG = {
    "vehicle": {
        "type": "civilian",
        "keywords": ["vehicle", "car", "engine", "maintenance", "diagnostic"],
        "priority": 1,
    },
    "vehicle_military": {
        "type": "military",
        "keywords": ["amphibian", "ford", "TM9-802", "gmc", "truck"],
        "priority": 2,
    },
    "forklift": {
        "type": "equipment",
        "keywords": ["forklift", "lift", "cargo", "mechanical", "operation"],
        "priority": 3,
    },
    "hvac": {
        "type": "equipment",
        "keywords": ["hvac", "heating", "cooling", "air", "temperature"],
        "priority": 4,
    },
    "radar": {
        "type": "equipment",
        "keywords": ["radar", "weather", "detection", "signal", "operator"],
        "priority": 5,
    },
}

# Domain folder mapping
DOMAIN_FOLDERS = {
    "vehicle_military": "vehicle",  # Military vehicle manuals
    "vehicle": "vehicle_civilian",  # Civilian vehicle manuals
    "forklift": "forklift",
    "hvac": "hvac",
    "radar": "radar",
}


@dataclass
class Chunk:
    """Represents a text chunk with domain metadata."""
    text: str
    domain: str
    domain_type: str
    source_file: str
    chunk_index: int
    source_keywords: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


class MultiDomainIngester:
    """Ingests multi-domain PDFs and text files with domain tagging."""

    def __init__(self, embedding_model: str = 'all-MiniLM-L6-v2'):
        """Initialize with embedding model."""
        self.embedding_model = SentenceTransformer(embedding_model)
        self.chunks: List[Chunk] = []
        self.domain_stats: Dict[str, int] = {}

    def extract_text_from_pdf(self, pdf_path: Path) -> Tuple[str, str, List[str]]:
        """
        Extract text from PDF using pdfplumber.
        Returns (text, extraction_method, methods_attempted)
        """
        text = ""
        method = "pdfplumber"
        methods = ["pdfplumber"]
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        except Exception:
            text = ""
        return text, method, methods

    def extract_text_from_html(self, html_path: Path) -> Tuple[str, bool]:
        """
        Extract text from HTML file using BeautifulSoup.
        Returns (text, success)
        """
        if not HTML_SUPPORT_AVAILABLE:
            return "", False
        
        try:
            from bs4 import BeautifulSoup
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style tags
            for tag in soup(['script', 'style', 'meta', 'link']):
                tag.decompose()
            
            # Extract text
            text = soup.get_text(separator='\n', strip=True)
            
            return text, True
        except Exception as e:
            print(f"(HTML extraction failed: {e})", end="")
            return "", False

    def detect_domain(self, text: str, filename: str) -> Tuple[str, str]:
        """
        Detect domain from content and filename.
        Returns (domain_id, domain_type).
        """
        text_lower = text.lower()
        filename_lower = filename.lower()

        # Special case: Distinguish between civilian and military vehicle docs
        if "vehicle" in filename_lower:
            military_indicators = ["tm9-802", "amphibian", "gmc 353", "6x6", "ford"]
            if any(ind in text_lower for ind in military_indicators):
                return "vehicle_military", "military"
            else:
                return "vehicle", "civilian"

        # Match other domains
        for domain_id, config in DOMAIN_CONFIG.items():
            if domain_id in ["vehicle", "vehicle_military"]:
                continue  # Already handled
            keywords = config["keywords"]
            if any(kw in text_lower or kw in filename_lower for kw in keywords):
                return domain_id, config["type"]

        # Default to generic if no match
        return "unknown", "general"

    def split_into_chunks(
        self, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
    ) -> List[str]:
        """Split text into overlapping chunks, preferring paragraph boundaries."""
        chunks = []
        paragraphs = text.split('\n\n')

        current_chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph would exceed chunk size
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap from previous
                overlap_text = (
                    current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                )
                current_chunk = overlap_text + " " + para
            else:
                current_chunk += " " + para if current_chunk else para

        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def ingest_directory(self) -> int:
        """Ingest all documents from data/ subdirectories."""
        print("="*70)
        print("MULTI-DOMAIN INGESTION")
        print("="*70)

        total_chunks = 0

        # Process each domain folder
        for domain_id, folder_name in DOMAIN_FOLDERS.items():
            folder_path = DATA_DIR / folder_name
            if not folder_path.exists():
                print(f"⚠ Skipping {domain_id}: folder not found at {folder_path}")
                continue

            print(f"\n[{domain_id.upper()}] Processing {folder_path}")
            print("-" * 70)

            domain_chunks = 0

            # Process PDFs
            for pdf_file in folder_path.glob("*.pdf"):
                print(f"  [PDF] {pdf_file.name}...", end=" ", flush=True)

                text, method, methods = self.extract_text_from_pdf(pdf_file)
                if not text:
                    print(f"(extraction failed: {' → '.join(methods)})")
                    continue

                detected_domain, domain_type = self.detect_domain(text, pdf_file.name)
                if detected_domain != domain_id and domain_id != "vehicle_military":
                    # Override detection if folder suggests otherwise
                    detected_domain = domain_id
                    domain_type = DOMAIN_CONFIG[domain_id]["type"]

                chunks = self.split_into_chunks(text)
                print(f"{len(chunks)} chunks [{method}]")

                for chunk_idx, chunk_text in enumerate(chunks):
                    chunk_obj = Chunk(
                        text=chunk_text,
                        domain=detected_domain,
                        domain_type=domain_type,
                        source_file=pdf_file.name,
                        chunk_index=chunk_idx,
                        source_keywords=DOMAIN_CONFIG.get(detected_domain, {}).get(
                            "keywords", []
                        ),
                    )
                    self.chunks.append(chunk_obj)
                    domain_chunks += 1

            # Process text files (e.g., vehicle_manual.txt)
            for txt_file in folder_path.glob("*.txt"):
                print(f"  [TEXT] {txt_file.name}...", end=" ", flush=True)

                with open(txt_file, 'r', encoding='utf-8') as f:
                    text = f.read()

                if not text:
                    print("(empty)")
                    continue

                detected_domain, domain_type = self.detect_domain(text, txt_file.name)
                if detected_domain != domain_id:
                    detected_domain = domain_id
                    domain_type = DOMAIN_CONFIG[domain_id]["type"]

                chunks = self.split_into_chunks(text)
                print(f"{len(chunks)} chunks")

                for chunk_idx, chunk_text in enumerate(chunks):
                    chunk_obj = Chunk(
                        text=chunk_text,
                        domain=detected_domain,
                        domain_type=domain_type,
                        source_file=txt_file.name,
                        chunk_index=chunk_idx,
                        source_keywords=DOMAIN_CONFIG.get(detected_domain, {}).get(
                            "keywords", []
                        ),
                    )
                    self.chunks.append(chunk_obj)
                    domain_chunks += 1

            # Process HTML files (e.g., vehicle manual websites)
            for html_file in folder_path.glob("*.html"):
                print(f"  [HTML] {html_file.name}...", end=" ", flush=True)

                text, success = self.extract_text_from_html(html_file)
                if not success or not text:
                    print(" (skipped)")
                    continue

                detected_domain, domain_type = self.detect_domain(text, html_file.name)
                if detected_domain != domain_id:
                    detected_domain = domain_id
                    domain_type = DOMAIN_CONFIG[domain_id]["type"]

                chunks = self.split_into_chunks(text)
                print(f" {len(chunks)} chunks")

                for chunk_idx, chunk_text in enumerate(chunks):
                    chunk_obj = Chunk(
                        text=chunk_text,
                        domain=detected_domain,
                        domain_type=domain_type,
                        source_file=html_file.name,
                        chunk_index=chunk_idx,
                        source_keywords=DOMAIN_CONFIG.get(detected_domain, {}).get(
                            "keywords", []
                        ),
                    )
                    self.chunks.append(chunk_obj)
                    domain_chunks += 1

            # Process HTML files in subdirectories (e.g., Volkswagen GTI folder)
            for html_dir in folder_path.iterdir():
                if not html_dir.is_dir():
                    continue
                
                for html_file in html_dir.glob("*.html"):
                    print(f"  [HTML] {html_dir.name}/{html_file.name}...", end=" ", flush=True)

                    text, success = self.extract_text_from_html(html_file)
                    if not success or not text:
                        print(" (skipped)")
                        continue

                    detected_domain, domain_type = self.detect_domain(text, html_file.name)
                    if detected_domain != domain_id:
                        detected_domain = domain_id
                        domain_type = DOMAIN_CONFIG[domain_id]["type"]

                    chunks = self.split_into_chunks(text)
                    print(f" {len(chunks)} chunks")

                    for chunk_idx, chunk_text in enumerate(chunks):
                        chunk_obj = Chunk(
                            text=chunk_text,
                            domain=detected_domain,
                            domain_type=domain_type,
                            source_file=f"{html_dir.name}/{html_file.name}",
                            chunk_index=chunk_idx,
                            source_keywords=DOMAIN_CONFIG.get(detected_domain, {}).get(
                                "keywords", []
                            ),
                        )
                        self.chunks.append(chunk_obj)
                        domain_chunks += 1

            self.domain_stats[domain_id] = domain_chunks
            total_chunks += domain_chunks
            print(f"  Total for {domain_id}: {domain_chunks} chunks")

        print(f"\n{'='*70}")
        print(f"[OK] Ingestion complete: {total_chunks} total chunks")
        print(f"{'='*70}")
        return total_chunks

    def create_vector_index(self) -> faiss.IndexFlatL2:
        """Create FAISS index from chunks."""
        print(f"\n[PROGRESS] Creating vector embeddings...")
        print(f"   Encoding {len(self.chunks)} chunks...")

        chunk_texts = [chunk.text for chunk in self.chunks]
        embeddings = self.embedding_model.encode(
            chunk_texts, show_progress_bar=True, convert_to_numpy=True
        )

        # Create FAISS index
        dimension = embeddings.shape[1] if len(embeddings.shape) > 1 else 1
        index = faiss.IndexFlatL2(dimension)
        embeddings = np.asarray(embeddings, dtype='float32')
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        index.add(embeddings)  # type: ignore

        print(f"[OK] FAISS index created: {index.ntotal} vectors (dim: {dimension})")
        return index

    def save_database(self, index: faiss.IndexFlatL2) -> None:
        """Save FAISS index and chunks with metadata."""
        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

        # Save FAISS index
        faiss.write_index(index, str(FAISS_INDEX_FILE))
        print(f"[OK] Saved FAISS index to {FAISS_INDEX_FILE}")

        # Save chunks with metadata (as plain dicts for easier unpickling)
        chunks_as_dicts = [
            {
                'text': chunk.text,
                'domain': chunk.domain,
                'domain_type': chunk.domain_type,
                'source_file': chunk.source_file,
                'chunk_index': chunk.chunk_index,
                'source_keywords': chunk.source_keywords,
            }
            for chunk in self.chunks
        ]
        with open(CHUNKS_FILE, 'wb') as f:
            pickle.dump(chunks_as_dicts, f)
        print(f"[OK] Saved {len(self.chunks)} chunks to {CHUNKS_FILE}")

        # Save metadata summary
        metadata = {
            "total_chunks": len(self.chunks),
            "domain_stats": self.domain_stats,
            "chunk_size": CHUNK_SIZE,
            "overlap": OVERLAP,
            "embedding_model": self.embedding_model.get_sentence_embedding_dimension(),
            "domains": list(self.domain_stats.keys()),  # Only include domains with chunks
        }
        with open(METADATA_FILE, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"[OK] Saved metadata to {METADATA_FILE}")

    def print_domain_statistics(self) -> None:
        """Print detailed domain statistics."""
        print(f"\n{'='*70}")
        print("DOMAIN STATISTICS")
        print(f"{'='*70}")

        for domain_id, count in sorted(self.domain_stats.items()):
            domain_type = DOMAIN_CONFIG.get(domain_id, {}).get("type", "unknown")
            pct = (count / len(self.chunks)) * 100
            print(f"  {domain_id:20s} ({domain_type:10s}): {count:5d} chunks ({pct:5.1f}%)")

        print(f"  {'-'*60}")
        print(f"  {'TOTAL':20s} {'':12s}: {len(self.chunks):5d} chunks (100.0%)")


def main():
    """Run multi-domain ingestion."""
    try:
        ingester = MultiDomainIngester()

        # Ingest documents
        ingester.ingest_directory()

        # Create vector index
        index = ingester.create_vector_index()

        # Save database
        ingester.save_database(index)

        # Print statistics
        ingester.print_domain_statistics()

        print(f"\n[OK] Multi-domain ingestion pipeline complete!")
        print(f"   Ready for cross-contamination testing")

    except Exception as e:
        print(f"\n[ERROR] Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
