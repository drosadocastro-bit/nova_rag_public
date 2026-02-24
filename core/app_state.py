"""
NICAppState: Central application state singleton.

This module provides a single source of truth for all mutable application state:
- FAISS vector index and document metadata
- Loaded models (embeddings, cross-encoder, reranker)
- Session state (turn history, findings, etc.)
- Error states (for troubleshooting)

Pattern: Thread-safe via Python's GIL (no explicit locks needed for read/write of references).
All initialization is idempotent: calling ensure_initialized() multiple times is safe.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict


@dataclass
class NICAppState:
    """
    Central application state container.
    
    Thread-safe via Python's GIL for reference assignment.
    All fields default to None/empty; populated by ensure_initialized().
    """
    
    # FAISS vector index and document metadata
    index: Optional[Any] = None
    docs: Optional[list] = None
    
    # Loaded models (lazy-loaded)
    text_embed_model: Optional[Any] = None
    cross_encoder: Optional[Any] = None
    vision_model: Optional[Any] = None
    tfidf_vectorizer: Optional[Any] = None
    anomaly_detector: Optional[Any] = None
    bm25_model: Optional[Any] = None
    
    # Error states (for diagnostics)
    index_error: Optional[str] = None
    embed_error: Optional[str] = None
    vision_error: Optional[str] = None
    anomaly_error: Optional[str] = None
    bm25_error: Optional[str] = None
    
    # Initialization tracking
    initialized: bool = False
    index_initialized: bool = False
    models_initialized: bool = False
    
    # Session state (maps session_id -> session_dict)
    sessions: Dict[str, Any] = field(default_factory=dict)
    
    # Error code index (for troubleshooting)
    error_codes: Optional[Dict[int, list]] = None
    
    def ensure_initialized(self) -> None:
        """
        Idempotent initialization: loads index and models exactly once.
        
        Safe to call multiple times; only first call does work.
        Any errors are stored in *_error fields (not raised).
        """
        if self.initialized:
            return
        
        self.initialized = True  # Mark attempted, even if fails
        
        # Initialize FAISS index and docs
        if not self.index_initialized:
            try:
                from core.retrieval.retrieval_engine import load_index
                self.index, self.docs = load_index()
                self.index_initialized = True
                
                # Also update module-level globals in retrieval_engine for backward compatibility
                import core.retrieval.retrieval_engine as engine
                engine.index = self.index
                engine.docs = self.docs
                
            except Exception as e:
                self.index_error = str(e)
        
        # Initialize models (lazy load in background if needed)
        if not self.models_initialized:
            try:
                # Models load on-demand in retrieval_engine
                # This just ensures no startup errors
                self.models_initialized = True
            except Exception as e:
                self.embed_error = str(e)
    
    def ensure_index_loaded(self) -> bool:
        """
        Ensure index is loaded; return True if successful, False if error.
        """
        self.ensure_initialized()
        return self.index is not None and self.index_error is None
    
    def get_stats(self) -> dict:
        """Return diagnostics dict for health checks."""
        return {
            "initialized": self.initialized,
            "index_loaded": self.index is not None,
            "index_vectors": self.index.ntotal if self.index else 0,
            "docs_count": len(self.docs) if self.docs else 0,
            "index_error": self.index_error,
            "embed_error": self.embed_error,
            "sessions_active": len(self.sessions),
        }


# Global singleton instance
_app_state: Optional[NICAppState] = None


def get_app_state() -> NICAppState:
    """
    Get or create the global NICAppState singleton.
    
    Returns:
        NICAppState: Thread-safe singleton instance
        
    Example:
        >>> state = get_app_state()
        >>> state.ensure_initialized()
        >>> if state.index_error:
        ...     raise RuntimeError(f"Index failed: {state.index_error}")
        >>> vectors = state.index.ntotal
    """
    global _app_state
    if _app_state is None:
        _app_state = NICAppState()
    return _app_state


def reset_app_state() -> None:
    """
    Reset global singleton (useful for testing).
    
    WARNING: Only use in tests; production should never reset state!
    """
    global _app_state
    _app_state = None
