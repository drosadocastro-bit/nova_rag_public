"""
File-hash tracking system for incremental indexing.

Maintains a manifest of all corpus files with SHA-256 hashes to detect changes
efficiently without re-processing the entire corpus.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Types of file changes detected."""
    NEW = "new"           # File not in manifest
    MODIFIED = "modified" # Hash mismatch
    DELETED = "deleted"   # File in manifest but missing
    UNCHANGED = "unchanged"


@dataclass
class FileMetadata:
    """Metadata for a single corpus file."""
    sha256: str
    chunk_count: int
    domain: str
    last_modified: str  # ISO 8601 timestamp
    ingested_at: str    # ISO 8601 timestamp
    chunk_ids: List[int] = field(default_factory=list)
    file_size: int = 0  # bytes
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "FileMetadata":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class FileChange:
    """Represents a detected file change."""
    file_path: str
    change_type: ChangeType
    old_metadata: Optional[FileMetadata] = None
    new_hash: Optional[str] = None
    
    def __str__(self) -> str:
        return f"{self.change_type.value}: {self.file_path}"


@dataclass
class CorpusManifest:
    """
    Manifest tracking all corpus files and their hashes.
    
    Enables incremental indexing by detecting which files have changed
    since the last ingestion.
    """
    version: str = "3.0"
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    total_chunks: int = 0
    files: Dict[str, FileMetadata] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "last_updated": self.last_updated,
            "total_chunks": self.total_chunks,
            "files": {path: metadata.to_dict() for path, metadata in self.files.items()}
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CorpusManifest":
        """Create from dictionary."""
        files = {
            path: FileMetadata.from_dict(metadata) 
            for path, metadata in data.get("files", {}).items()
        }
        return cls(
            version=data.get("version", "3.0"),
            last_updated=data.get("last_updated", datetime.utcnow().isoformat() + "Z"),
            total_chunks=data.get("total_chunks", 0),
            files=files
        )
    
    def save(self, manifest_path: Path) -> None:
        """Save manifest to disk."""
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved manifest to {manifest_path} ({len(self.files)} files, {self.total_chunks} chunks)")
    
    @classmethod
    def load(cls, manifest_path: Path) -> "CorpusManifest":
        """Load manifest from disk."""
        if not manifest_path.exists():
            logger.warning(f"Manifest not found at {manifest_path}, creating new manifest")
            return cls()
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        manifest = cls.from_dict(data)
        logger.info(f"Loaded manifest from {manifest_path} ({len(manifest.files)} files, {manifest.total_chunks} chunks)")
        return manifest
    
    def add_file(
        self, 
        file_path: str, 
        sha256: str, 
        chunk_count: int, 
        chunk_ids: List[int],
        domain: str,
        file_size: int = 0
    ) -> None:
        """Add or update file metadata in manifest."""
        now = datetime.utcnow().isoformat() + "Z"
        
        # Get last_modified timestamp from file system
        path = Path(file_path)
        last_modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat() + "Z" if path.exists() else now
        
        self.files[file_path] = FileMetadata(
            sha256=sha256,
            chunk_count=chunk_count,
            domain=domain,
            last_modified=last_modified,
            ingested_at=now,
            chunk_ids=chunk_ids,
            file_size=file_size
        )
        self.total_chunks = sum(f.chunk_count for f in self.files.values())
        self.last_updated = now
        logger.info(f"Added {file_path} to manifest: {chunk_count} chunks, domain={domain}")
    
    def remove_file(self, file_path: str) -> Optional[FileMetadata]:
        """Remove file from manifest, returning its metadata if it existed."""
        metadata = self.files.pop(file_path, None)
        if metadata:
            self.total_chunks = sum(f.chunk_count for f in self.files.values())
            self.last_updated = datetime.utcnow().isoformat() + "Z"
            logger.info(f"Removed {file_path} from manifest ({metadata.chunk_count} chunks)")
        return metadata
    
    def get_file(self, file_path: str) -> Optional[FileMetadata]:
        """Get metadata for a specific file."""
        return self.files.get(file_path)
    
    def validate_integrity(self, corpus_dir: Path) -> List[str]:
        """
        Validate manifest integrity against actual corpus.
        
        Returns list of validation errors (empty if valid).
        """
        errors = []
        
        # Check manifest files exist
        for file_path in self.files.keys():
            full_path = corpus_dir / file_path
            if not full_path.exists():
                errors.append(f"Manifest references missing file: {file_path}")
        
        # Check chunk_ids are unique and sequential
        all_chunk_ids = []
        for file_path, metadata in self.files.items():
            all_chunk_ids.extend(metadata.chunk_ids)
        
        if len(all_chunk_ids) != len(set(all_chunk_ids)):
            errors.append("Duplicate chunk IDs detected in manifest")
        
        # Check total_chunks matches sum of file chunk_counts
        expected_total = sum(f.chunk_count for f in self.files.values())
        if self.total_chunks != expected_total:
            errors.append(f"total_chunks mismatch: {self.total_chunks} != {expected_total}")
        
        if errors:
            logger.warning(f"Manifest validation found {len(errors)} errors")
        else:
            logger.info("Manifest validation passed")
        
        return errors


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """
    Compute SHA-256 hash of file content.
    
    Args:
        file_path: Path to file
        chunk_size: Size of chunks to read (default 8KB)
    
    Returns:
        Hexadecimal SHA-256 hash string
    """
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def detect_changes(
    corpus_dir: Path, 
    manifest: CorpusManifest,
    file_extensions: Optional[Set[str]] = None
) -> List[FileChange]:
    """
    Detect changes between current corpus and manifest.
    
    Args:
        corpus_dir: Directory containing corpus files
        manifest: Current corpus manifest
        file_extensions: Set of file extensions to scan (e.g., {'.pdf', '.html'})
                        If None, scans common document types
    
    Returns:
        List of detected file changes
    """
    if file_extensions is None:
        file_extensions = {'.pdf', '.html', '.htm', '.txt', '.md'}
    
    changes = []
    
    # Scan current corpus directory
    current_files = {}
    for ext in file_extensions:
        for file_path in corpus_dir.rglob(f"*{ext}"):
            # Convert to relative path for consistency
            rel_path = str(file_path.relative_to(corpus_dir))
            current_files[rel_path] = file_path
    
    manifest_files = set(manifest.files.keys())
    current_file_paths = set(current_files.keys())
    
    # Detect new and modified files
    for rel_path, full_path in current_files.items():
        current_hash = compute_file_hash(full_path)
        
        if rel_path not in manifest_files:
            # New file
            changes.append(FileChange(
                file_path=rel_path,
                change_type=ChangeType.NEW,
                new_hash=current_hash
            ))
            logger.info(f"Detected NEW file: {rel_path}")
        else:
            # Check if modified
            old_metadata = manifest.files[rel_path]
            if old_metadata.sha256 != current_hash:
                changes.append(FileChange(
                    file_path=rel_path,
                    change_type=ChangeType.MODIFIED,
                    old_metadata=old_metadata,
                    new_hash=current_hash
                ))
                logger.info(f"Detected MODIFIED file: {rel_path}")
            else:
                changes.append(FileChange(
                    file_path=rel_path,
                    change_type=ChangeType.UNCHANGED,
                    old_metadata=old_metadata
                ))
    
    # Detect deleted files
    for rel_path in manifest_files - current_file_paths:
        changes.append(FileChange(
            file_path=rel_path,
            change_type=ChangeType.DELETED,
            old_metadata=manifest.files[rel_path]
        ))
        logger.warning(f"Detected DELETED file: {rel_path}")
    
    # Summary
    summary = {ct: sum(1 for c in changes if c.change_type == ct) for ct in ChangeType}
    logger.info(f"Change detection complete: {summary}")
    
    return changes


def get_next_chunk_id(manifest: CorpusManifest) -> int:
    """
    Get the next available chunk ID (monotonic, no reuse).
    
    Args:
        manifest: Current corpus manifest
    
    Returns:
        Next available chunk ID
    """
    if not manifest.files:
        return 0
    
    # Find max chunk ID across all files
    max_id = max(
        max(metadata.chunk_ids) if metadata.chunk_ids else -1
        for metadata in manifest.files.values()
    )
    
    return max_id + 1
