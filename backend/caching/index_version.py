from dataclasses import dataclass, asdict
from typing import Optional
import json
import hashlib
from datetime import datetime


@dataclass
class IndexVersion: 
    """Metadata for tracking index versions and triggering rebuilds."""
    schema_version: str = "1.0.0"
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 512
    chunk_overlap: int = 50
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    corpus_hash: str = ""
    created_at: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'IndexVersion':
        """Load from dictionary."""
        return cls(**data)
    
    def compute_fingerprint(self) -> str:
        """Generate unique fingerprint based on all parameters."""
        config_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(config_str. encode()).hexdigest()[:16]
    
    def is_compatible_with(self, other: 'IndexVersion') -> bool:
        """
        Check if a cached index with 'other' version can be reused.
        Returns False if any critical parameter differs.
        """
        return (
            self.embedding_model == other.embedding_model and
            self.chunk_size == other.chunk_size and
            self.chunk_overlap == other. chunk_overlap and
            self. bm25_k1 == other.bm25_k1 and
            self.bm25_b == other.bm25_b and
            self. corpus_hash == other.corpus_hash
        )