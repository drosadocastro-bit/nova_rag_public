"""
Tantivy BM25 Backend for NOVA NIC.

Scalable disk-based full-text search using Tantivy (Rust-based search engine).
Replaces in-memory BM25 for handling millions of documents.

Features:
- Disk-based index (survives restarts)
- Real-time indexing
- Incremental updates
- Multi-field search
- Domain filtering
- Concurrent reads
"""

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Try to import tantivy
try:
    import tantivy  # type: ignore
    TANTIVY_AVAILABLE = True
except ImportError:
    TANTIVY_AVAILABLE = False
    logger.warning(
        "tantivy-py not installed. Install with: pip install tantivy\n"
        "Falling back to in-memory BM25."
    )


@dataclass
class TantivyDocument:
    """Document for Tantivy indexing."""
    
    doc_id: str
    content: str
    title: str = ""
    domain: str = ""
    source: str = ""
    chunk_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to indexable dict."""
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "title": self.title,
            "domain": self.domain,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "metadata_json": json.dumps(self.metadata),
        }


@dataclass
class TantivySearchResult:
    """Search result from Tantivy."""
    
    doc_id: str
    score: float
    content: str
    title: str = ""
    domain: str = ""
    source: str = ""
    chunk_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    highlights: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doc_id": self.doc_id,
            "score": round(self.score, 4),
            "content": self.content,
            "title": self.title,
            "domain": self.domain,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
            "highlights": self.highlights,
        }


class TantivyBM25Index:
    """
    Tantivy-based BM25 index for scalable full-text search.
    
    Scales to millions of documents with:
    - Disk-based storage
    - Real-time indexing
    - Concurrent reads
    - Domain filtering
    """
    
    # Schema field names
    FIELD_DOC_ID = "doc_id"
    FIELD_CONTENT = "content"
    FIELD_TITLE = "title"
    FIELD_DOMAIN = "domain"
    FIELD_SOURCE = "source"
    FIELD_CHUNK_INDEX = "chunk_index"
    FIELD_METADATA = "metadata_json"
    
    def __init__(
        self,
        index_path: str,
        heap_size_mb: int = 128,
        auto_commit: bool = True,
        commit_interval_seconds: float = 5.0,
    ):
        """
        Initialize Tantivy index.
        
        Args:
            index_path: Path to store index
            heap_size_mb: Memory for indexing (MB)
            auto_commit: Auto-commit after indexing
            commit_interval_seconds: Interval for background commit
        """
        if not TANTIVY_AVAILABLE:
            raise ImportError(
                "tantivy-py is required for TantivyBM25Index. "
                "Install with: pip install tantivy"
            )
        
        self.index_path = Path(index_path)
        self.heap_size_mb = heap_size_mb
        self.auto_commit = auto_commit
        self.commit_interval = commit_interval_seconds
        
        # Ensure directory exists
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        # Build schema
        self._schema = self._build_schema()
        
        # Open or create index
        self._index = self._open_or_create_index()
        
        # Writer (single writer at a time)
        self._writer = self._index.writer(heap_size_mb * 1024 * 1024)
        self._writer_lock = threading.Lock()
        
        # Background commit thread
        self._commit_thread: Optional[threading.Thread] = None
        self._stop_commit = threading.Event()
        self._pending_docs = 0
        
        # Stats
        self._total_indexed = 0
        self._total_deleted = 0
        self._total_searches = 0
        
        if auto_commit:
            self._start_commit_thread()
        
        logger.info(
            f"TantivyBM25Index initialized: path={index_path}, "
            f"heap={heap_size_mb}MB, docs={self.doc_count()}"
        )
    
    def _build_schema(self) -> "tantivy.Schema":
        """Build Tantivy schema."""
        schema_builder = tantivy.SchemaBuilder()  # type: ignore
        
        # Stored and indexed fields
        schema_builder.add_text_field(self.FIELD_DOC_ID, stored=True)
        schema_builder.add_text_field(self.FIELD_CONTENT, stored=True)
        schema_builder.add_text_field(self.FIELD_TITLE, stored=True)
        schema_builder.add_text_field(self.FIELD_DOMAIN, stored=True)
        schema_builder.add_text_field(self.FIELD_SOURCE, stored=True)
        schema_builder.add_integer_field(self.FIELD_CHUNK_INDEX, stored=True)
        schema_builder.add_text_field(self.FIELD_METADATA, stored=True)
        
        return schema_builder.build()
    
    def _open_or_create_index(self) -> "tantivy.Index":
        """Open existing index or create new one."""
        try:
            # Try to open existing
            return tantivy.Index(self._schema, str(self.index_path))  # type: ignore
        except Exception:
            # Create new
            return tantivy.Index(self._schema, str(self.index_path), reuse=False)  # type: ignore
    
    def _start_commit_thread(self) -> None:
        """Start background commit thread."""
        def commit_loop():
            while not self._stop_commit.wait(self.commit_interval):
                if self._pending_docs > 0:
                    try:
                        with self._writer_lock:
                            self._writer.commit()
                            self._pending_docs = 0
                    except Exception as e:
                        logger.error(f"Auto-commit failed: {e}")
        
        self._commit_thread = threading.Thread(
            target=commit_loop,
            daemon=True,
            name="TantivyCommit"
        )
        self._commit_thread.start()
    
    def index_document(self, doc: TantivyDocument) -> bool:
        """
        Index a single document.
        
        Args:
            doc: Document to index
            
        Returns:
            True if successful
        """
        try:
            with self._writer_lock:
                self._writer.add_document(tantivy.Document(  # type: ignore
                    doc_id=doc.doc_id,
                    content=doc.content,
                    title=doc.title,
                    domain=doc.domain,
                    source=doc.source,
                    chunk_index=doc.chunk_index,
                    metadata_json=json.dumps(doc.metadata),
                ))
                self._pending_docs += 1
                self._total_indexed += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to index document {doc.doc_id}: {e}")
            return False
    
    def index_batch(
        self,
        docs: List[TantivyDocument],
        commit: bool = True,
    ) -> Tuple[int, int]:
        """
        Index a batch of documents.
        
        Args:
            docs: Documents to index
            commit: Commit after batch
            
        Returns:
            Tuple of (successful, failed) counts
        """
        success = 0
        failed = 0
        
        with self._writer_lock:
            for doc in docs:
                try:
                    self._writer.add_document(tantivy.Document(  # type: ignore
                        doc_id=doc.doc_id,
                        content=doc.content,
                        title=doc.title,
                        domain=doc.domain,
                        source=doc.source,
                        chunk_index=doc.chunk_index,
                        metadata_json=json.dumps(doc.metadata),
                    ))
                    success += 1
                    self._total_indexed += 1
                except Exception as e:
                    logger.error(f"Failed to index document {doc.doc_id}: {e}")
                    failed += 1
            
            if commit and success > 0:
                self._writer.commit()
                self._pending_docs = 0
            else:
                self._pending_docs += success
        
        logger.info(f"Indexed batch: {success} successful, {failed} failed")
        return success, failed
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document by ID.
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if deleted
        """
        try:
            with self._writer_lock:
                self._writer.delete_documents(self.FIELD_DOC_ID, doc_id)
                self._pending_docs += 1
                self._total_deleted += 1
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
    
    def delete_by_domain(self, domain: str) -> int:
        """
        Delete all documents in a domain.
        
        Args:
            domain: Domain to delete
            
        Returns:
            Number of documents deleted
        """
        # First, find all doc_ids in domain
        results = self.search(
            query="*",
            domain=domain,
            top_k=10000,
        )
        
        deleted = 0
        for result in results:
            if self.delete_document(result.doc_id):
                deleted += 1
        
        if deleted > 0:
            self.commit()
        
        logger.info(f"Deleted {deleted} documents from domain: {domain}")
        return deleted
    
    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        top_k: int = 10,
        fields: Optional[List[str]] = None,
    ) -> List[TantivySearchResult]:
        """
        Search the index.
        
        Args:
            query: Search query
            domain: Filter by domain
            top_k: Number of results
            fields: Fields to search (default: content, title)
            
        Returns:
            List of search results
        """
        self._total_searches += 1
        
        try:
            searcher = self._index.searcher()
            
            # Build query
            search_fields = fields or [self.FIELD_CONTENT, self.FIELD_TITLE]
            
            if domain:
                # Add domain filter
                full_query = f"({query}) AND {self.FIELD_DOMAIN}:{domain}"
            else:
                full_query = query
            
            # Parse and execute query
            query_parser = tantivy.QueryParser.for_index(  # type: ignore
                self._index,
                search_fields
            )
            parsed_query = query_parser.parse_query(full_query)
            
            # Search
            search_results = searcher.search(parsed_query, top_k).hits
            
            # Convert to results
            results = []
            for score, doc_address in search_results:
                doc = searcher.doc(doc_address)
                
                # Parse metadata
                try:
                    metadata = json.loads(
                        doc.get_first(self.FIELD_METADATA) or "{}"
                    )
                except json.JSONDecodeError:
                    metadata = {}
                
                results.append(TantivySearchResult(
                    doc_id=doc.get_first(self.FIELD_DOC_ID) or "",
                    score=score,
                    content=doc.get_first(self.FIELD_CONTENT) or "",
                    title=doc.get_first(self.FIELD_TITLE) or "",
                    domain=doc.get_first(self.FIELD_DOMAIN) or "",
                    source=doc.get_first(self.FIELD_SOURCE) or "",
                    chunk_index=doc.get_first(self.FIELD_CHUNK_INDEX) or 0,
                    metadata=metadata,
                ))
            
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def commit(self) -> None:
        """Commit pending changes."""
        with self._writer_lock:
            self._writer.commit()
            self._pending_docs = 0
    
    def optimize(self) -> None:
        """Optimize index (merge segments)."""
        logger.info("Optimizing index...")
        start = time.time()
        
        with self._writer_lock:
            self._writer.wait_merging_threads()
        
        elapsed = time.time() - start
        logger.info(f"Index optimized in {elapsed:.2f}s")
    
    def doc_count(self) -> int:
        """Get total document count."""
        try:
            searcher = self._index.searcher()
            return searcher.num_docs
        except Exception:
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "index_path": str(self.index_path),
            "doc_count": self.doc_count(),
            "total_indexed": self._total_indexed,
            "total_deleted": self._total_deleted,
            "total_searches": self._total_searches,
            "pending_docs": self._pending_docs,
            "heap_size_mb": self.heap_size_mb,
        }
    
    def close(self) -> None:
        """Close the index."""
        # Stop commit thread
        self._stop_commit.set()
        if self._commit_thread:
            self._commit_thread.join(timeout=5)
        
        # Final commit
        try:
            self.commit()
        except Exception as e:
            logger.error(f"Final commit failed: {e}")
        
        logger.info("TantivyBM25Index closed")
    
    def clear(self) -> None:
        """Clear all documents from index."""
        logger.warning("Clearing entire index...")
        
        self.close()
        
        # Remove index directory
        if self.index_path.exists():
            shutil.rmtree(self.index_path)
        
        # Recreate
        self.index_path.mkdir(parents=True, exist_ok=True)
        self._index = self._open_or_create_index()
        self._writer = self._index.writer(self.heap_size_mb * 1024 * 1024)
        self._pending_docs = 0
        
        if self.auto_commit:
            self._start_commit_thread()
        
        logger.info("Index cleared")


class TantivyBM25Fallback:
    """
    Fallback BM25 implementation when Tantivy is not available.
    
    Uses simple in-memory TF-IDF scoring.
    """
    
    def __init__(self, index_path: str, **kwargs):
        """Initialize fallback index."""
        self.index_path = Path(index_path)
        self._documents: Dict[str, TantivyDocument] = {}
        self._domains: Dict[str, Set[str]] = {}  # domain -> doc_ids
        
        # Try to load from disk
        self._load()
        
        logger.warning(
            "Using in-memory BM25 fallback. For production, install tantivy-py."
        )
    
    def _load(self) -> None:
        """Load documents from disk."""
        docs_file = self.index_path / "documents.jsonl"
        if docs_file.exists():
            with open(docs_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        doc = TantivyDocument(
                            doc_id=data["doc_id"],
                            content=data["content"],
                            title=data.get("title", ""),
                            domain=data.get("domain", ""),
                            source=data.get("source", ""),
                            chunk_index=data.get("chunk_index", 0),
                            metadata=data.get("metadata", {}),
                        )
                        self._documents[doc.doc_id] = doc
                        
                        if doc.domain:
                            if doc.domain not in self._domains:
                                self._domains[doc.domain] = set()
                            self._domains[doc.domain].add(doc.doc_id)
                    except Exception:
                        continue
    
    def _save(self) -> None:
        """Save documents to disk."""
        self.index_path.mkdir(parents=True, exist_ok=True)
        docs_file = self.index_path / "documents.jsonl"
        
        with open(docs_file, "w") as f:
            for doc in self._documents.values():
                data = {
                    "doc_id": doc.doc_id,
                    "content": doc.content,
                    "title": doc.title,
                    "domain": doc.domain,
                    "source": doc.source,
                    "chunk_index": doc.chunk_index,
                    "metadata": doc.metadata,
                }
                f.write(json.dumps(data) + "\n")
    
    def index_document(self, doc: TantivyDocument) -> bool:
        """Index a document."""
        self._documents[doc.doc_id] = doc
        
        if doc.domain:
            if doc.domain not in self._domains:
                self._domains[doc.domain] = set()
            self._domains[doc.domain].add(doc.doc_id)
        
        return True
    
    def index_batch(
        self,
        docs: List[TantivyDocument],
        commit: bool = True,
    ) -> Tuple[int, int]:
        """Index a batch."""
        for doc in docs:
            self.index_document(doc)
        
        if commit:
            self.commit()
        
        return len(docs), 0
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        if doc_id in self._documents:
            doc = self._documents[doc_id]
            if doc.domain and doc.domain in self._domains:
                self._domains[doc.domain].discard(doc_id)
            del self._documents[doc_id]
            return True
        return False
    
    def delete_by_domain(self, domain: str) -> int:
        """Delete all documents in domain."""
        if domain not in self._domains:
            return 0
        
        doc_ids = list(self._domains[domain])
        for doc_id in doc_ids:
            self.delete_document(doc_id)
        
        return len(doc_ids)
    
    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        top_k: int = 10,
        fields: Optional[List[str]] = None,
    ) -> List[TantivySearchResult]:
        """Simple keyword search."""
        query_terms = set(query.lower().split())
        
        # Filter by domain
        if domain and domain in self._domains:
            doc_ids = self._domains[domain]
        else:
            doc_ids = set(self._documents.keys())
        
        # Score documents
        scored = []
        for doc_id in doc_ids:
            doc = self._documents[doc_id]
            
            # Simple term frequency scoring
            text = f"{doc.title} {doc.content}".lower()
            score = sum(1 for term in query_terms if term in text)
            
            if score > 0:
                scored.append((score, doc))
        
        # Sort by score
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top_k
        return [
            TantivySearchResult(
                doc_id=doc.doc_id,
                score=float(score),
                content=doc.content,
                title=doc.title,
                domain=doc.domain,
                source=doc.source,
                chunk_index=doc.chunk_index,
                metadata=doc.metadata,
            )
            for score, doc in scored[:top_k]
        ]
    
    def commit(self) -> None:
        """Save to disk."""
        self._save()
    
    def optimize(self) -> None:
        """No-op for fallback."""
        pass
    
    def doc_count(self) -> int:
        """Get document count."""
        return len(self._documents)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "index_path": str(self.index_path),
            "doc_count": self.doc_count(),
            "domains": list(self._domains.keys()),
            "is_fallback": True,
        }
    
    def close(self) -> None:
        """Save and close."""
        self._save()
    
    def clear(self) -> None:
        """Clear all documents."""
        self._documents.clear()
        self._domains.clear()
        self._save()


def create_bm25_index(
    index_path: str,
    heap_size_mb: int = 128,
    **kwargs,
) -> TantivyBM25Index:
    """
    Create a BM25 index (Tantivy or fallback).
    
    Args:
        index_path: Path to store index
        heap_size_mb: Memory for indexing
        **kwargs: Additional arguments
        
    Returns:
        TantivyBM25Index or TantivyBM25Fallback
    """
    if TANTIVY_AVAILABLE:
        return TantivyBM25Index(index_path, heap_size_mb=heap_size_mb, **kwargs)
    else:
        return TantivyBM25Fallback(index_path, **kwargs)  # type: ignore
