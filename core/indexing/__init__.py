"""
Incremental indexing components for Phase 3.

This package provides:
- File-hash tracking and change detection
- Incremental FAISS index updates
- Incremental BM25 corpus expansion
- Hot-reload coordination
"""

from .corpus_manifest import (
    CorpusManifest,
    FileMetadata,
    FileChange,
    ChangeType,
    compute_file_hash,
    detect_changes,
    get_next_chunk_id,
)
from .incremental_faiss import (
    IncrementalFAISSIndex,
    atomic_index_update,
)
from .incremental_bm25 import (
    IncrementalBM25,
    BM25Document,
)
from .hot_reload import (
    IncrementalReloader,
    ReloadProgress,
    ReloadResult,
    create_reload_endpoint,
)
from .batch_ingestion import (
    BatchIngestionPipeline,
    IngestionConfig,
    IngestionStatus,
    BatchProgress,
    DocumentResult,
    stream_documents,
)

__all__ = [
    "CorpusManifest",
    "FileMetadata",
    "FileChange",
    "ChangeType",
    "compute_file_hash",
    "detect_changes",
    "get_next_chunk_id",
    "IncrementalFAISSIndex",
    "atomic_index_update",
    "IncrementalBM25",
    "BM25Document",
    "IncrementalReloader",
    "ReloadProgress",
    "ReloadResult",
    "create_reload_endpoint",
    # Batch ingestion
    "BatchIngestionPipeline",
    "IngestionConfig",
    "IngestionStatus",
    "BatchProgress",
    "DocumentResult",
    "stream_documents",
]
