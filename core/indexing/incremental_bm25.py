"""
Incremental BM25 index for append-only corpus expansion.

Enables adding new documents to BM25 without full rebuild,
leveraging the fact that BM25 rebuild is fast in-memory (~1s for 10k docs).
"""

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast
import numpy as np

try:
    from rank_bm25 import BM25Okapi  # type: ignore[import]
except ImportError:
    BM25Okapi = None

BM25Okapi = cast(Any, BM25Okapi)
BM25Okapi: Any

logger = logging.getLogger(__name__)


@dataclass
class BM25Document:
    """Document for BM25 indexing."""
    chunk_id: int
    tokens: List[str]
    domain: str
    metadata: dict


class IncrementalBM25:
    """
    BM25 index supporting incremental document addition.
    
    Strategy: Maintain corpus in memory, rebuild BM25 on additions.
    This is acceptable because BM25 rebuild is fast (~1s for 10k docs).
    
    Features:
    - Append documents without full corpus reload
    - Persistent corpus storage
    - Fast in-memory rebuild
    - Domain-aware document tracking
    """
    
    def __init__(
        self,
        corpus_path: Path,
        k1: float = 1.5,
        b: float = 0.75
    ):
        """
        Initialize incremental BM25 index.
        
        Args:
            corpus_path: Path to save/load corpus
            k1: BM25 term saturation parameter
            b: BM25 length normalization parameter
        """
        if BM25Okapi is None:
            raise ImportError("rank-bm25 required for BM25 indexing")
        # Narrow type for static analyzers
        assert BM25Okapi is not None
        
        self.corpus_path = Path(corpus_path)
        self.k1 = k1
        self.b = b
        
        # Document storage
        self.documents: List[BM25Document] = []
        self.chunk_id_to_idx: dict = {}  # chunk_id -> document index
        
        # BM25 index
        self.bm25: Optional[Any] = None
        
        # Load existing corpus
        self._load_corpus()
        self._rebuild_index()
    
    def _load_corpus(self) -> None:
        """Load corpus from disk if exists."""
        if not self.corpus_path.exists():
            logger.info(f"No existing corpus at {self.corpus_path}, starting fresh")
            return
        
        try:
            with open(self.corpus_path, 'rb') as f:
                data = pickle.load(f)
            
            self.documents = data.get('documents', [])
            self.chunk_id_to_idx = data.get('chunk_id_to_idx', {})
            
            logger.info(f"Loaded BM25 corpus: {len(self.documents)} documents from {self.corpus_path}")
        
        except Exception as e:
            logger.error(f"Failed to load corpus from {self.corpus_path}: {e}")
            self.documents = []
            self.chunk_id_to_idx = {}
    
    def _save_corpus(self) -> bool:
        """Save corpus to disk."""
        try:
            self.corpus_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'documents': self.documents,
                'chunk_id_to_idx': self.chunk_id_to_idx,
                'params': {'k1': self.k1, 'b': self.b}
            }
            
            with open(self.corpus_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            logger.info(f"Saved BM25 corpus: {len(self.documents)} documents to {self.corpus_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save corpus to {self.corpus_path}: {e}")
            return False
    
    def _rebuild_index(self) -> None:
        """Rebuild BM25 index from corpus (fast in-memory operation)."""
        if not self.documents:
            logger.info("No documents to index")
            self.bm25 = None
            return
        
        # Extract tokenized corpus
        tokenized_corpus = [doc.tokens for doc in self.documents]
        
        # Rebuild BM25 (fast: ~1s for 10k documents)
        self.bm25 = BM25Okapi(tokenized_corpus, k1=self.k1, b=self.b)  # type: ignore[operator]
        
        logger.info(f"Rebuilt BM25 index: {len(self.documents)} documents")
    
    def add_documents(
        self,
        documents: List[BM25Document],
        rebuild: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Add new documents to BM25 index.
        
        Args:
            documents: List of BM25Document to add
            rebuild: Whether to rebuild index after adding (default True)
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not documents:
            return True, None
        
        try:
            # Validate no duplicate chunk IDs
            new_chunk_ids = {doc.chunk_id for doc in documents}
            existing_chunk_ids = set(self.chunk_id_to_idx.keys())
            
            duplicates = new_chunk_ids & existing_chunk_ids
            if duplicates:
                return False, f"Duplicate chunk IDs: {duplicates}"
            
            # Add documents
            start_idx = len(self.documents)
            for i, doc in enumerate(documents):
                self.documents.append(doc)
                self.chunk_id_to_idx[doc.chunk_id] = start_idx + i
            
            logger.info(f"Added {len(documents)} documents (total: {len(self.documents)})")
            
            # Rebuild index if requested
            if rebuild:
                self._rebuild_index()
            
            # Save corpus
            self._save_corpus()
            
            return True, None
        
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            return False, str(e)
    
    def remove_documents(
        self,
        chunk_ids: List[int],
        rebuild: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Remove documents from index by chunk ID.
        
        Note: This requires full rebuild due to index reordering.
        
        Args:
            chunk_ids: List of chunk IDs to remove
            rebuild: Whether to rebuild index after removing (default True)
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not chunk_ids:
            return True, None
        
        try:
            # Remove documents
            chunk_id_set = set(chunk_ids)
            self.documents = [doc for doc in self.documents if doc.chunk_id not in chunk_id_set]
            
            # Rebuild chunk_id -> idx mapping
            self.chunk_id_to_idx = {
                doc.chunk_id: idx 
                for idx, doc in enumerate(self.documents)
            }
            
            logger.info(f"Removed {len(chunk_ids)} documents (remaining: {len(self.documents)})")
            
            # Rebuild index
            if rebuild:
                self._rebuild_index()
            
            # Save corpus
            self._save_corpus()
            
            return True, None
        
        except Exception as e:
            logger.error(f"Failed to remove documents: {e}")
            return False, str(e)
    
    def search(
        self,
        query_tokens: List[str],
        k: int = 10,
        domain_filter: Optional[str] = None
    ) -> List[Tuple[int, float]]:
        """
        Search BM25 index for relevant documents.
        
        Args:
            query_tokens: Tokenized query
            k: Number of results to return
            domain_filter: Optional domain to filter results
        
        Returns:
            List of (chunk_id, score) tuples, sorted by score descending
        """
        if not self.bm25 or not self.documents:
            logger.warning("BM25 index empty or not built")
            return []
        
        scores = self.bm25.get_scores(query_tokens)

        # Build candidate list with optional domain filter
        candidates: List[Tuple[int, float]] = []
        for idx, doc in enumerate(self.documents):
            if domain_filter and doc.domain != domain_filter:
                continue
            score = scores[idx]
            if np.isfinite(score):
                candidates.append((doc.chunk_id, float(score)))

        # Sort by score descending and take top-k
        candidates.sort(key=lambda x: x[1], reverse=True)
        results = [(cid, score) for cid, score in candidates[:k]]
        
        return results
    
    def get_document(self, chunk_id: int) -> Optional[BM25Document]:
        """Get document by chunk ID."""
        idx = self.chunk_id_to_idx.get(chunk_id)
        if idx is None:
            return None
        return self.documents[idx]
    
    @property
    def total_documents(self) -> int:
        """Get total number of documents."""
        return len(self.documents)
    
    def get_stats(self) -> dict:
        """Get BM25 index statistics."""
        domain_counts = {}
        for doc in self.documents:
            domain_counts[doc.domain] = domain_counts.get(doc.domain, 0) + 1
        
        return {
            "total_documents": self.total_documents,
            "index_built": self.bm25 is not None,
            "corpus_path": str(self.corpus_path),
            "params": {"k1": self.k1, "b": self.b},
            "domain_distribution": domain_counts
        }
    
    def clear(self) -> None:
        """Clear all documents and index."""
        self.documents = []
        self.chunk_id_to_idx = {}
        self.bm25 = None
        logger.info("Cleared BM25 index")
