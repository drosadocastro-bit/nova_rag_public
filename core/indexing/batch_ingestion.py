"""
Optimized Batch Ingestion with Progress Tracking.

High-performance batch document ingestion with:
- Parallel document processing
- Memory-efficient chunking
- Progress callbacks and tracking
- Resume capability for failed batches
- Validation and error handling
- Resource throttling
"""

import hashlib
import json
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class IngestionStatus(str, Enum):
    """Status of a document in ingestion pipeline."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DocumentResult:
    """Result of processing a single document."""
    
    doc_id: str
    file_path: str
    status: IngestionStatus
    chunks_created: int = 0
    processing_time_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "status": self.status.value,
            "chunks_created": self.chunks_created,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class BatchProgress:
    """Progress tracking for batch ingestion."""
    
    batch_id: str
    total_documents: int
    processed_documents: int = 0
    successful_documents: int = 0
    failed_documents: int = 0
    skipped_documents: int = 0
    total_chunks: int = 0
    
    # Timing
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Current status
    current_document: Optional[str] = None
    current_status: IngestionStatus = IngestionStatus.PENDING
    
    # Results
    results: List[DocumentResult] = field(default_factory=list)
    
    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_documents == 0:
            return 100.0
        return (self.processed_documents / self.total_documents) * 100
    
    @property
    def elapsed_seconds(self) -> float:
        """Calculate elapsed time."""
        if not self.started_at:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at
    
    @property
    def estimated_remaining_seconds(self) -> float:
        """Estimate remaining time."""
        if self.processed_documents == 0:
            return 0.0
        
        avg_time_per_doc = self.elapsed_seconds / self.processed_documents
        remaining_docs = self.total_documents - self.processed_documents
        return avg_time_per_doc * remaining_docs
    
    @property
    def documents_per_second(self) -> float:
        """Calculate throughput."""
        if self.elapsed_seconds == 0:
            return 0.0
        return self.processed_documents / self.elapsed_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "batch_id": self.batch_id,
            "total_documents": self.total_documents,
            "processed_documents": self.processed_documents,
            "successful_documents": self.successful_documents,
            "failed_documents": self.failed_documents,
            "skipped_documents": self.skipped_documents,
            "total_chunks": self.total_chunks,
            "progress_percent": round(self.progress_percent, 1),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds, 2),
            "documents_per_second": round(self.documents_per_second, 2),
            "current_document": self.current_document,
            "current_status": self.current_status.value,
        }


@dataclass
class IngestionConfig:
    """Configuration for batch ingestion."""
    
    # Parallelism
    max_workers: int = 4
    chunk_batch_size: int = 100
    
    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50
    
    # Memory management
    max_memory_mb: int = 1024
    gc_interval: int = 100  # Run GC every N documents
    
    # Error handling
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    fail_fast: bool = False  # Stop on first error
    
    # Resume capability
    checkpoint_interval: int = 50  # Save checkpoint every N documents
    checkpoint_path: Optional[Path] = None
    
    # Validation
    skip_duplicates: bool = True
    validate_content: bool = True
    min_content_length: int = 10
    max_content_length: int = 1_000_000
    
    # Supported file types
    supported_extensions: Set[str] = field(
        default_factory=lambda: {".txt", ".md", ".html", ".json", ".pdf"}
    )
    
    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Create config from environment variables."""
        return cls(
            max_workers=int(os.environ.get("NOVA_INGEST_WORKERS", "4")),
            chunk_batch_size=int(os.environ.get("NOVA_INGEST_BATCH_SIZE", "100")),
            chunk_size=int(os.environ.get("NOVA_CHUNK_SIZE", "512")),
            chunk_overlap=int(os.environ.get("NOVA_CHUNK_OVERLAP", "50")),
            max_memory_mb=int(os.environ.get("NOVA_INGEST_MAX_MEMORY_MB", "1024")),
            max_retries=int(os.environ.get("NOVA_INGEST_MAX_RETRIES", "3")),
            fail_fast=os.environ.get("NOVA_INGEST_FAIL_FAST", "0") == "1",
            skip_duplicates=os.environ.get("NOVA_INGEST_SKIP_DUPLICATES", "1") == "1",
        )


# Type aliases
DocumentProcessor = Callable[[str, Path, Dict[str, Any]], Tuple[List[str], Dict[str, Any]]]
ProgressCallback = Callable[[BatchProgress], None]


class BatchIngestionPipeline:
    """
    High-performance batch document ingestion pipeline.
    
    Features:
    - Parallel processing with configurable workers
    - Progress tracking with callbacks
    - Checkpoint/resume for large batches
    - Memory-efficient streaming
    - Duplicate detection
    - Comprehensive error handling
    """
    
    def __init__(
        self,
        config: Optional[IngestionConfig] = None,
        document_processor: Optional[DocumentProcessor] = None,
    ):
        """
        Initialize batch ingestion pipeline.
        
        Args:
            config: Ingestion configuration
            document_processor: Function to process documents into chunks
        """
        self.config = config or IngestionConfig.from_env()
        self.document_processor = document_processor or self._default_processor
        
        # State
        self._active_batch: Optional[BatchProgress] = None
        self._processed_hashes: Set[str] = set()
        self._lock = threading.Lock()
        self._stop_requested = False
        
        # Callbacks
        self._progress_callbacks: List[ProgressCallback] = []
    
    def add_progress_callback(self, callback: ProgressCallback) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)
    
    def _notify_progress(self, progress: BatchProgress) -> None:
        """Notify all registered callbacks."""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
    
    def _default_processor(
        self,
        content: str,
        file_path: Path,
        metadata: Dict[str, Any]
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Default document processor (simple chunking).
        
        Args:
            content: Document content
            file_path: Path to document
            metadata: Document metadata
            
        Returns:
            Tuple of (chunks, updated_metadata)
        """
        chunks = []
        size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        
        # Simple sliding window chunking
        start = 0
        while start < len(content):
            end = start + size
            chunk = content[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start += size - overlap
        
        return chunks, metadata
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute hash for duplicate detection."""
        return hashlib.md5(content.encode()).hexdigest()
    
    def _validate_document(
        self,
        file_path: Path,
        content: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate document for ingestion.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check extension
        if file_path.suffix.lower() not in self.config.supported_extensions:
            return False, f"Unsupported extension: {file_path.suffix}"
        
        # Check content length
        if len(content) < self.config.min_content_length:
            return False, f"Content too short: {len(content)} chars"
        
        if len(content) > self.config.max_content_length:
            return False, f"Content too long: {len(content)} chars"
        
        # Check for duplicates
        if self.config.skip_duplicates:
            content_hash = self._compute_content_hash(content)
            if content_hash in self._processed_hashes:
                return False, "Duplicate content"
            self._processed_hashes.add(content_hash)
        
        return True, None
    
    def _process_single_document(
        self,
        file_path: Path,
        metadata: Dict[str, Any],
        progress: BatchProgress,
    ) -> DocumentResult:
        """Process a single document with error handling."""
        doc_id = hashlib.md5(str(file_path).encode()).hexdigest()[:16]
        start_time = time.time()
        
        result = DocumentResult(
            doc_id=doc_id,
            file_path=str(file_path),
            status=IngestionStatus.PROCESSING,
        )
        
        try:
            # Read content
            content = file_path.read_text(encoding='utf-8', errors='replace')
            
            # Validate
            if self.config.validate_content:
                is_valid, error_msg = self._validate_document(file_path, content)
                if not is_valid:
                    result.status = IngestionStatus.SKIPPED
                    result.error_message = error_msg
                    return result
            
            # Process with retries
            last_error = None
            for attempt in range(self.config.max_retries):
                try:
                    result.status = IngestionStatus.CHUNKING
                    chunks, updated_meta = self.document_processor(
                        content, file_path, metadata
                    )
                    
                    result.chunks_created = len(chunks)
                    result.metadata = updated_meta
                    result.status = IngestionStatus.COMPLETED
                    break
                    
                except Exception as e:
                    last_error = e
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay_seconds)
            
            if result.status != IngestionStatus.COMPLETED:
                result.status = IngestionStatus.FAILED
                result.error_message = str(last_error)
        
        except Exception as e:
            result.status = IngestionStatus.FAILED
            result.error_message = str(e)
            logger.error(f"Failed to process {file_path}: {e}")
        
        result.processing_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _save_checkpoint(self, progress: BatchProgress) -> None:
        """Save checkpoint for resume capability."""
        if not self.config.checkpoint_path:
            return
        
        try:
            checkpoint = {
                "batch_id": progress.batch_id,
                "processed_documents": progress.processed_documents,
                "results": [r.to_dict() for r in progress.results],
                "processed_hashes": list(self._processed_hashes),
                "timestamp": datetime.now().isoformat(),
            }
            
            self.config.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.checkpoint_path, 'w') as f:
                json.dump(checkpoint, f)
            
            logger.debug(f"Saved checkpoint at {progress.processed_documents} documents")
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def _load_checkpoint(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint if exists."""
        if not self.config.checkpoint_path or not self.config.checkpoint_path.exists():
            return None
        
        try:
            with open(self.config.checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
            
            if checkpoint.get("batch_id") == batch_id:
                logger.info(
                    f"Resuming from checkpoint: {checkpoint['processed_documents']} "
                    f"documents already processed"
                )
                return checkpoint
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
        
        return None
    
    def ingest_batch(
        self,
        documents: List[Tuple[Path, Dict[str, Any]]],
        batch_id: Optional[str] = None,
        resume: bool = True,
    ) -> BatchProgress:
        """
        Ingest a batch of documents.
        
        Args:
            documents: List of (file_path, metadata) tuples
            batch_id: Optional batch identifier (auto-generated if not provided)
            resume: Whether to resume from checkpoint
            
        Returns:
            BatchProgress with results
        """
        # Generate batch ID
        if not batch_id:
            batch_id = hashlib.md5(
                str(time.time()).encode() + str(len(documents)).encode()
            ).hexdigest()[:12]
        
        # Initialize progress
        progress = BatchProgress(
            batch_id=batch_id,
            total_documents=len(documents),
            started_at=time.time(),
        )
        
        self._active_batch = progress
        self._stop_requested = False
        
        # Check for checkpoint
        start_index = 0
        if resume:
            checkpoint = self._load_checkpoint(batch_id)
            if checkpoint:
                start_index = checkpoint["processed_documents"]
                self._processed_hashes = set(checkpoint.get("processed_hashes", []))
                progress.processed_documents = start_index
                # Restore previous results
                for r_dict in checkpoint.get("results", []):
                    progress.results.append(DocumentResult(
                        doc_id=r_dict["doc_id"],
                        file_path=r_dict["file_path"],
                        status=IngestionStatus(r_dict["status"]),
                        chunks_created=r_dict.get("chunks_created", 0),
                        processing_time_ms=r_dict.get("processing_time_ms", 0),
                        error_message=r_dict.get("error_message"),
                    ))
        
        # Process documents
        try:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                # Submit all remaining documents
                future_to_doc = {}
                for i, (file_path, metadata) in enumerate(documents[start_index:], start=start_index):
                    if self._stop_requested:
                        break
                    
                    future = executor.submit(
                        self._process_single_document,
                        file_path,
                        metadata,
                        progress,
                    )
                    future_to_doc[future] = (file_path, i)
                
                # Collect results
                for future in as_completed(future_to_doc):
                    if self._stop_requested:
                        break
                    
                    file_path, idx = future_to_doc[future]
                    
                    try:
                        result = future.result()
                    except Exception as e:
                        result = DocumentResult(
                            doc_id="error",
                            file_path=str(file_path),
                            status=IngestionStatus.FAILED,
                            error_message=str(e),
                        )
                    
                    # Update progress
                    with self._lock:
                        progress.processed_documents += 1
                        progress.results.append(result)
                        progress.total_chunks += result.chunks_created
                        
                        if result.status == IngestionStatus.COMPLETED:
                            progress.successful_documents += 1
                        elif result.status == IngestionStatus.FAILED:
                            progress.failed_documents += 1
                            if self.config.fail_fast:
                                self._stop_requested = True
                        elif result.status == IngestionStatus.SKIPPED:
                            progress.skipped_documents += 1
                        
                        progress.current_document = str(file_path)
                        progress.current_status = result.status
                    
                    # Notify callbacks
                    self._notify_progress(progress)
                    
                    # Save checkpoint periodically
                    if progress.processed_documents % self.config.checkpoint_interval == 0:
                        self._save_checkpoint(progress)
                    
                    # Periodic GC
                    if progress.processed_documents % self.config.gc_interval == 0:
                        import gc
                        gc.collect()
        
        except Exception as e:
            logger.error(f"Batch ingestion failed: {e}")
        
        # Finalize
        progress.completed_at = time.time()
        progress.current_status = IngestionStatus.COMPLETED
        self._active_batch = None
        
        # Final notification
        self._notify_progress(progress)
        
        # Save final checkpoint
        self._save_checkpoint(progress)
        
        logger.info(
            f"Batch {batch_id} completed: {progress.successful_documents}/"
            f"{progress.total_documents} successful, "
            f"{progress.failed_documents} failed, "
            f"{progress.skipped_documents} skipped in {progress.elapsed_seconds:.1f}s"
        )
        
        return progress
    
    def ingest_directory(
        self,
        directory: Path,
        recursive: bool = True,
        metadata_fn: Optional[Callable[[Path], Dict[str, Any]]] = None,
        batch_id: Optional[str] = None,
    ) -> BatchProgress:
        """
        Ingest all documents from a directory.
        
        Args:
            directory: Directory path
            recursive: Whether to search recursively
            metadata_fn: Function to generate metadata from file path
            batch_id: Optional batch identifier
            
        Returns:
            BatchProgress with results
        """
        directory = Path(directory)
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")
        
        # Collect files
        pattern = "**/*" if recursive else "*"
        documents = []
        
        for file_path in directory.glob(pattern):
            if not file_path.is_file():
                continue
            
            if file_path.suffix.lower() not in self.config.supported_extensions:
                continue
            
            metadata = metadata_fn(file_path) if metadata_fn else {}
            documents.append((file_path, metadata))
        
        logger.info(f"Found {len(documents)} documents in {directory}")
        
        return self.ingest_batch(documents, batch_id=batch_id)
    
    def stop(self) -> None:
        """Request stop of current batch processing."""
        self._stop_requested = True
    
    def get_active_progress(self) -> Optional[BatchProgress]:
        """Get progress of active batch."""
        return self._active_batch


def stream_documents(
    file_paths: Iterable[Path],
    chunk_size: int = 100,
) -> Generator[List[Path], None, None]:
    """
    Stream documents in memory-efficient batches.
    
    Args:
        file_paths: Iterable of file paths
        chunk_size: Number of documents per batch
        
    Yields:
        Batches of file paths
    """
    batch = []
    for path in file_paths:
        batch.append(path)
        if len(batch) >= chunk_size:
            yield batch
            batch = []
    
    if batch:
        yield batch
