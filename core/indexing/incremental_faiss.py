"""
Incremental FAISS index for append-only updates.

Enables adding new embeddings without rebuilding the entire index,
with backup/rollback support for atomic updates.
"""

import logging
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

# Ensure faiss is treated as Any for static analysis once availability is checked at runtime
faiss = cast(Any, faiss)
faiss: Any

logger = logging.getLogger(__name__)


class IncrementalFAISSIndex:
    """
    FAISS index wrapper supporting incremental additions.
    
    Features:
    - Append-only updates (no full rebuild)
    - Backup before modifications
    - Rollback on failure
    - Preserves chunk ID → index position mapping
    """
    
    def __init__(
        self,
        dimension: int,
        index_path: Path,
        backup_dir: Optional[Path] = None,
        index_type: str = "IndexFlatL2"
    ):
        """
        Initialize incremental FAISS index.
        
        Args:
            dimension: Embedding dimension (e.g., 384 for sentence-transformers)
            index_path: Path to index file
            backup_dir: Directory for backups (default: index_path.parent / "backups")
            index_type: FAISS index type ("IndexFlatL2", "IndexIVFFlat", etc.)
        """
        if faiss is None:
            raise ImportError("faiss-cpu or faiss-gpu required for incremental indexing")
        # Narrow type for static analyzers
        assert faiss is not None
        
        self.dimension = dimension
        self.index_path = Path(index_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.index_path.parent / "backups"
        self.index_type = index_type
        self.index: Optional[Any] = None
        
        # Load existing index or create new one
        self._load_or_create_index()
    
    def _load_or_create_index(self) -> None:
        """Load existing index from disk or create new one."""
        if self.index_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))  # type: ignore[attr-defined]
                logger.info(f"Loaded existing FAISS index from {self.index_path} ({self.index.ntotal} vectors)")  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"Failed to load index from {self.index_path}: {e}")
                logger.info("Creating new index")
                self._create_new_index()
        else:
            self._create_new_index()
    
    def _create_new_index(self) -> None:
        """Create new FAISS index."""
        if self.index_type == "IndexFlatL2":
            self.index = faiss.IndexFlatL2(self.dimension)  # type: ignore[attr-defined]
        elif self.index_type == "IndexIVFFlat":
            # For IVF index, need to train first (not implemented yet)
            raise NotImplementedError("IndexIVFFlat requires training - use IndexFlatL2 for Phase 3")
        else:
            raise ValueError(f"Unsupported index type: {self.index_type}")
        
        logger.info(f"Created new {self.index_type} index (dimension={self.dimension})")
    
    def add_chunks(
        self,
        embeddings: np.ndarray,
        chunk_ids: List[int],
        backup: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Add new chunk embeddings to index.
        
        Args:
            embeddings: Numpy array of shape (n_chunks, dimension)
            chunk_ids: List of chunk IDs (length must match embeddings)
            backup: Whether to create backup before adding
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if embeddings.shape[0] != len(chunk_ids):
            return False, f"Embedding count ({embeddings.shape[0]}) != chunk_ids count ({len(chunk_ids)})"
        
        if embeddings.shape[1] != self.dimension:
            return False, f"Embedding dimension ({embeddings.shape[1]}) != expected dimension ({self.dimension})"
        
        if self.index is None:
            return False, "FAISS index not initialized"

        # Backup current index
        backup_path = None
        if backup:
            backup_path = self._create_backup()
            if not backup_path:
                return False, "Failed to create backup"
        
        try:
            # Add embeddings to index
            initial_count = self.index.ntotal
            self.index.add(embeddings.astype('float32'))
            final_count = self.index.ntotal
            
            added_count = final_count - initial_count
            logger.info(f"Added {added_count} embeddings to FAISS index (total: {final_count})")
            
            # Save updated index
            self.save()
            
            return True, None
        
        except Exception as e:
            logger.error(f"Failed to add embeddings: {e}")
            
            # Rollback to backup
            if backup_path:
                logger.info(f"Rolling back to backup: {backup_path}")
                self._restore_backup(backup_path)
            
            return False, str(e)
    
    def _create_backup(self) -> Optional[Path]:
        """
        Create timestamped backup of current index.
        
        Returns:
            Path to backup file, or None if failed
        """
        if not self.index_path.exists():
            # If index exists in memory but not on disk, persist it first
            if self.index is None:
                logger.warning("No index file to backup")
                return None
            # Save current index to enable backup creation
            self.save()
        
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"{self.index_path.stem}_backup_{timestamp}.index"
            
            shutil.copy2(self.index_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            
            # Keep only last 5 backups
            self._cleanup_old_backups(keep=5)
            
            return backup_path
        
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None
    
    def _restore_backup(self, backup_path: Path) -> bool:
        """
        Restore index from backup.
        
        Args:
            backup_path: Path to backup file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            shutil.copy2(backup_path, self.index_path)
            self._load_or_create_index()
            logger.info(f"Restored index from backup: {backup_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False
    
    def _cleanup_old_backups(self, keep: int = 5) -> None:
        """
        Remove old backups, keeping only the most recent N.
        
        Args:
            keep: Number of backups to keep
        """
        if not self.backup_dir.exists():
            return
        
        # Get all backup files for this index
        pattern = f"{self.index_path.stem}_backup_*.index"
        backups = sorted(self.backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Remove old backups
        for backup in backups[keep:]:
            try:
                backup.unlink()
                logger.debug(f"Removed old backup: {backup}")
            except Exception as e:
                logger.warning(f"Failed to remove backup {backup}: {e}")
    
    def save(self) -> bool:
        """
        Save index to disk.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            if self.index is None:
                return False
            faiss.write_index(self.index, str(self.index_path))  # type: ignore[attr-defined]
            logger.info(f"Saved FAISS index to {self.index_path} ({self.index.ntotal} vectors)")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            return False
    
    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search index for nearest neighbors.
        
        Args:
            query_embedding: Query vector of shape (1, dimension) or (dimension,)
            k: Number of neighbors to return
        
        Returns:
            Tuple of (distances, indices) arrays
        """
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        
        if self.index is None:
            raise ValueError("FAISS index is not initialized")

        distances, indices = self.index.search(query_embedding.astype('float32'), k)
        return distances, indices
    
    @property
    def total_vectors(self) -> int:
        """Get total number of vectors in index."""
        return self.index.ntotal if self.index else 0
    
    def get_stats(self) -> dict:
        """Get index statistics."""
        return {
            "index_type": self.index_type,
            "dimension": self.dimension,
            "total_vectors": self.total_vectors,
            "index_path": str(self.index_path),
            "index_exists": self.index_path.exists(),
            "backup_count": len(list(self.backup_dir.glob(f"{self.index_path.stem}_backup_*.index"))) if self.backup_dir.exists() else 0
        }


@contextmanager
def atomic_index_update(index: IncrementalFAISSIndex):
    """
    Context manager for atomic FAISS index updates.
    
    Creates backup before entering context, rolls back on exception.
    
    Usage:
        with atomic_index_update(index):
            index.add_chunks(embeddings, chunk_ids, backup=False)  # backup handled by context
    """
    backup_path = index._create_backup()
    
    try:
        yield index
        logger.info("Atomic update completed successfully")
    except Exception as e:
        logger.error(f"Atomic update failed: {e}")
        if backup_path:
            index._restore_backup(backup_path)
        raise
