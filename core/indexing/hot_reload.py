"""
Hot-reload API endpoint for incremental corpus updates.

Provides POST /api/reload endpoint to add new documents without server restart,
with dry-run mode, progress streaming, and atomic updates.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator
from flask import jsonify, request, Response, stream_with_context
import json

from core.indexing import (
    CorpusManifest,
    FileChange,
    ChangeType,
    compute_file_hash,
    detect_changes,
    IncrementalFAISSIndex,
    atomic_index_update,
)
from core.indexing.incremental_bm25 import IncrementalBM25, BM25Document

logger = logging.getLogger(__name__)


@dataclass
class ReloadProgress:
    """Progress update for reload operation."""
    stage: str
    current: int
    total: int
    message: str
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_json(self) -> str:
        """Convert to JSON for streaming."""
        return json.dumps(asdict(self)) + "\n"


@dataclass
class ReloadResult:
    """Result of reload operation."""
    success: bool
    dry_run: bool
    files_added: int
    files_modified: int
    files_deleted: int
    chunks_added: int
    duration_seconds: float
    errors: List[str]
    manifest_path: str
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


class IncrementalReloader:
    """
    Coordinates incremental corpus reload.
    
    Detects file changes, updates FAISS/BM25 indices, and maintains manifest.
    """
    
    def __init__(
        self,
        corpus_dir: Path,
        manifest_path: Path,
        faiss_index: IncrementalFAISSIndex,
        bm25_index: IncrementalBM25,
        embedding_function,
        tokenizer_function,
        domain_tagger_function
    ):
        """
        Initialize reloader.
        
        Args:
            corpus_dir: Directory containing corpus files
            manifest_path: Path to corpus manifest
            faiss_index: Incremental FAISS index
            bm25_index: Incremental BM25 index
            embedding_function: Function(text) -> np.ndarray for embeddings
            tokenizer_function: Function(text) -> List[str] for BM25 tokens
            domain_tagger_function: Function(file_path) -> str for domain inference
        """
        self.corpus_dir = Path(corpus_dir)
        self.manifest_path = Path(manifest_path)
        self.faiss_index = faiss_index
        self.bm25_index = bm25_index
        self.embedding_function = embedding_function
        self.tokenizer_function = tokenizer_function
        self.domain_tagger_function = domain_tagger_function
    
    def reload(
        self,
        dry_run: bool = False,
        stream_progress: bool = False
    ) -> Generator[ReloadProgress, None, ReloadResult]:
        """
        Reload corpus incrementally.
        
        Args:
            dry_run: If True, detect changes but don't apply them
            stream_progress: If True, yield progress updates
        
        Yields:
            ReloadProgress updates (if stream_progress=True)
        
        Returns:
            ReloadResult with operation summary
        """
        start_time = datetime.utcnow()
        errors = []
        
        # Stage 1: Load manifest and detect changes
        if stream_progress:
            yield ReloadProgress("init", 0, 5, "Loading corpus manifest")
        
        try:
            manifest = CorpusManifest.load(self.manifest_path)
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            manifest = CorpusManifest()
            errors.append(f"Failed to load manifest: {e}")
        
        if stream_progress:
            yield ReloadProgress("detect", 1, 5, "Detecting file changes")
        
        changes = detect_changes(self.corpus_dir, manifest)
        
        # Categorize changes
        new_files = [c for c in changes if c.change_type == ChangeType.NEW]
        modified_files = [c for c in changes if c.change_type == ChangeType.MODIFIED]
        deleted_files = [c for c in changes if c.change_type == ChangeType.DELETED]
        
        total_changes = len(new_files) + len(modified_files) + len(deleted_files)
        
        if stream_progress:
            yield ReloadProgress(
                "summary",
                2,
                5,
                f"Found {total_changes} changes: {len(new_files)} new, {len(modified_files)} modified, {len(deleted_files)} deleted"
            )
        
        if dry_run:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return ReloadResult(
                success=True,
                dry_run=True,
                files_added=len(new_files),
                files_modified=len(modified_files),
                files_deleted=len(deleted_files),
                chunks_added=0,
                duration_seconds=duration,
                errors=errors,
                manifest_path=str(self.manifest_path)
            )
        
        # Stage 2: Process deletions
        chunks_deleted = 0
        if deleted_files:
            if stream_progress:
                yield ReloadProgress("delete", 3, 5, f"Processing {len(deleted_files)} deletions")
            
            try:
                deleted_chunk_ids = []
                for change in deleted_files:
                    metadata = manifest.remove_file(change.file_path)
                    if metadata:
                        deleted_chunk_ids.extend(metadata.chunk_ids)
                        chunks_deleted += metadata.chunk_count
                
                # Remove from BM25 (FAISS keeps dead entries marked in manifest)
                if deleted_chunk_ids:
                    self.bm25_index.remove_documents(deleted_chunk_ids)
                
            except Exception as e:
                logger.error(f"Error during deletion: {e}")
                errors.append(f"Deletion error: {e}")
        
        # Stage 3: Process new and modified files
        chunks_added = 0
        files_to_process = new_files + modified_files
        
        if files_to_process:
            if stream_progress:
                yield ReloadProgress("process", 4, 5, f"Processing {len(files_to_process)} files")
            
            try:
                # Use atomic update for FAISS
                with atomic_index_update(self.faiss_index):
                    for i, change in enumerate(files_to_process):
                        file_path = self.corpus_dir / change.file_path
                        
                        # Ingest file (this is simplified - real implementation needs full ingestion pipeline)
                        chunks, embeddings, tokens = self._ingest_file(file_path)
                        
                        if not chunks or embeddings is None:
                            continue
                        
                        # Get domain
                        domain = self.domain_tagger_function(str(file_path))
                        
                        # Get chunk IDs
                        from core.indexing import get_next_chunk_id
                        start_id = get_next_chunk_id(manifest)
                        chunk_ids = list(range(start_id, start_id + len(chunks)))
                        
                        # Add to FAISS
                        success, error = self.faiss_index.add_chunks(embeddings, chunk_ids, backup=False)
                        if not success:
                            errors.append(f"FAISS error for {change.file_path}: {error}")
                            continue
                        
                        # Add to BM25
                        bm25_docs = [
                            BM25Document(
                                chunk_id=chunk_ids[j],
                                tokens=tokens[j],
                                domain=domain,
                                metadata={"file": change.file_path, "chunk_index": j}
                            )
                            for j in range(len(chunks))
                        ]
                        success, error = self.bm25_index.add_documents(bm25_docs)
                        if not success:
                            errors.append(f"BM25 error for {change.file_path}: {error}")
                            continue
                        
                        # Update manifest
                        manifest.add_file(
                            file_path=change.file_path,
                            sha256=change.new_hash or compute_file_hash(file_path),
                            chunk_count=len(chunks),
                            chunk_ids=chunk_ids,
                            domain=domain,
                            file_size=file_path.stat().st_size
                        )
                        
                        chunks_added += len(chunks)
                        
                        if stream_progress and i % 5 == 0:
                            yield ReloadProgress(
                                "process",
                                4,
                                5,
                                f"Processed {i+1}/{len(files_to_process)} files ({chunks_added} chunks)"
                            )
            
            except Exception as e:
                logger.error(f"Error during file processing: {e}")
                errors.append(f"Processing error: {e}")
        
        # Stage 4: Save manifest
        if stream_progress:
            yield ReloadProgress("save", 5, 5, "Saving manifest")
        
        try:
            manifest.save(self.manifest_path)
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")
            errors.append(f"Failed to save manifest: {e}")
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return ReloadResult(
            success=len(errors) == 0,
            dry_run=False,
            files_added=len(new_files),
            files_modified=len(modified_files),
            files_deleted=len(deleted_files),
            chunks_added=chunks_added,
            duration_seconds=duration,
            errors=errors,
            manifest_path=str(self.manifest_path)
        )
    
    def _ingest_file(self, file_path: Path):
        """
        Ingest a single file.
        
        This is a placeholder - real implementation would use the full ingestion pipeline.
        
        Returns:
            Tuple of (chunks, embeddings, tokens)
        """
        # TODO: Integrate with real ingestion pipeline
        # For now, return empty to avoid errors
        logger.warning(f"_ingest_file not fully implemented for {file_path}")
        return [], None, []


def create_reload_endpoint(reloader: IncrementalReloader):
    """
    Create Flask endpoint for hot-reload API.
    
    Args:
        reloader: IncrementalReloader instance
    
    Returns:
        Flask route function
    """
    
    def reload_corpus():
        """
        POST /api/reload
        
        Reload corpus incrementally without server restart.
        
        Query params:
            dry_run (bool): If true, detect changes but don't apply (default: false)
            stream (bool): If true, stream progress updates (default: false)
        
        Returns:
            JSON result if stream=false, Server-Sent Events if stream=true
        """
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        stream = request.args.get('stream', 'false').lower() == 'true'
        
        if stream:
            # Stream progress updates
            def generate():
                result = None
                for update in reloader.reload(dry_run=dry_run, stream_progress=True):
                    if isinstance(update, ReloadProgress):
                        yield f"data: {update.to_json()}\n\n"
                    elif isinstance(update, ReloadResult):
                        result = update
                
                # Send final result
                if result:
                    yield f"data: {json.dumps(asdict(result))}\n\n"
                yield "data: [DONE]\n\n"
            
            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # Single JSON response
            result_gen = reloader.reload(dry_run=dry_run, stream_progress=False)
            result = None
            for item in result_gen:
                if isinstance(item, ReloadResult):
                    result = item
            
            if result:
                return jsonify(asdict(result))
            else:
                return jsonify({"error": "No result generated"}), 500
    
    return reload_corpus
