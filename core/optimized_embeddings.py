"""
Optimized Embedding Operations - Phase 4.2 Performance.

Provides memory-efficient embedding operations including:
- Vectorized batch processing
- Optional quantization for reduced memory
- Streaming processing for large datasets
- Smart caching for embeddings
- Fallback mechanisms for potato hardware
"""

import os
import logging
import numpy as np
from typing import List, Optional, Tuple, Union
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class QuantizationConfig:
    """Configuration for model quantization."""
    
    # Quantization types
    INT8 = "int8"           # 8-bit integer quantization (75% memory reduction)
    FLOAT16 = "float16"     # 16-bit float (50% memory reduction)
    DYNAMIC = "dynamic"     # Dynamic quantization (PyTorch)
    NONE = "none"           # No quantization
    
    @staticmethod
    def get_recommended(hardware_tier: str) -> str:
        """Get recommended quantization for hardware tier."""
        tiers = {
            "ultra_lite": QuantizationConfig.INT8,
            "lite": QuantizationConfig.FLOAT16,
            "standard": QuantizationConfig.NONE,
            "full": QuantizationConfig.NONE,
        }
        return tiers.get(hardware_tier, QuantizationConfig.NONE)
    
    @staticmethod
    def apply_to_model(model, quantization_type: str):
        """Apply quantization to a model."""
        if quantization_type == QuantizationConfig.NONE:
            return model
        
        try:
            import torch
        except ImportError:
            logger.warning("torch not available, skipping quantization")
            return model
        
        try:
            if quantization_type == QuantizationConfig.FLOAT16:
                return model.half()
            elif quantization_type == QuantizationConfig.INT8:
                try:
                    return torch.quantization.quantize_dynamic(
                        model,
                        {torch.nn.Linear},
                        dtype=torch.qint8
                    )
                except Exception as e:
                    logger.warning(f"Could not apply INT8 quantization: {e}")
                    return model
            elif quantization_type == QuantizationConfig.DYNAMIC:
                try:
                    return torch.quantization.quantize_dynamic(
                        model,
                        qconfig_spec=torch.quantization.default_dynamic_qconfig,
                        dtype=torch.qint8
                    )
                except Exception as e:
                    logger.warning(f"Could not apply dynamic quantization: {e}")
                    return model
        except Exception as e:
            logger.warning(f"Quantization failed: {e}")
        
        return model


class VectorizedEmbeddingProcessor:
    """
    Efficient batch processing for embeddings with optional quantization.
    
    Features:
    - Smart batching for memory constraints
    - Vectorized operations
    - Optional quantization
    - Streaming support
    """
    
    def __init__(
        self,
        model,
        max_batch_size: int = 32,
        quantization: str = QuantizationConfig.NONE,
        device: str = "cpu",
    ):
        """
        Initialize processor.
        
        Args:
            model: Embedding model (sentence-transformers, transformers, etc.)
            max_batch_size: Max items per batch to control memory
            quantization: Type of quantization to apply
            device: Device to use (cpu, cuda, etc.)
        """
        self.model = model
        self.max_batch_size = max_batch_size
        self.quantization = quantization
        self.device = device
        
        # Apply quantization if requested
        if quantization != QuantizationConfig.NONE:
            logger.info(f"Applying {quantization} quantization to embedding model")
            self.model = QuantizationConfig.apply_to_model(model, quantization)
        
        # Move to device if CUDA available
        try:
            import torch
            if device != "cpu" and torch.cuda.is_available():
                self.model = self.model.to(device)
        except:
            pass
    
    def encode_batch(
        self,
        texts: List[str],
        normalize: bool = True,
        return_numpy: bool = True,
    ) -> Union[np.ndarray, list]:
        """
        Encode texts in optimized batches.
        
        Args:
            texts: List of texts to encode
            normalize: Normalize embeddings to unit length
            return_numpy: Return as numpy array (vs list)
            
        Returns:
            Embeddings array
        """
        if not texts:
            return np.array([]) if return_numpy else []
        
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i:i + self.max_batch_size]
            
            try:
                # Encode batch
                if hasattr(self.model, "encode"):
                    # SentenceTransformers interface
                    batch_embeddings = self.model.encode(
                        batch,
                        convert_to_numpy=True,
                        show_progress_bar=False,
                        normalize_embeddings=normalize,
                    )
                else:
                    # Generic interface
                    batch_embeddings = self.model(batch)
                    if normalize and isinstance(batch_embeddings, np.ndarray):
                        norms = np.linalg.norm(batch_embeddings, axis=1, keepdims=True)
                        batch_embeddings = batch_embeddings / (norms + 1e-10)
                
                all_embeddings.append(batch_embeddings)
                
            except Exception as e:
                logger.error(f"Error encoding batch: {e}")
                raise
        
        # Concatenate all batches
        if not all_embeddings:
            return np.array([]) if return_numpy else []
        
        result = np.vstack(all_embeddings) if return_numpy else all_embeddings
        return result
    
    def encode_stream(
        self,
        text_stream,
        batch_size: int = 32,
        normalize: bool = True,
    ):
        """
        Stream encoding for large datasets (memory-efficient).
        
        Args:
            text_stream: Iterable of texts
            batch_size: Process in batches of this size
            normalize: Normalize embeddings
            
        Yields:
            (text, embedding) tuples
        """
        batch_texts = []
        
        for text in text_stream:
            batch_texts.append(text)
            
            if len(batch_texts) >= batch_size:
                embeddings = self.encode_batch(batch_texts, normalize=normalize)
                for t, emb in zip(batch_texts, embeddings):
                    yield t, emb
                batch_texts = []
        
        # Process remaining
        if batch_texts:
            embeddings = self.encode_batch(batch_texts, normalize=normalize)
            for t, emb in zip(batch_texts, embeddings):
                yield t, emb


class EmbeddingCache:
    """
    Simple LRU cache for embeddings with memory limits.
    """
    
    def __init__(self, max_items: int = 1000, max_memory_mb: int = 100):
        """
        Initialize cache.
        
        Args:
            max_items: Maximum number of cached embeddings
            max_memory_mb: Maximum memory to use (approximate)
        """
        self.max_items = max_items
        self.max_memory_mb = max_memory_mb
        self.cache: dict[str, np.ndarray] = {}
        self.access_counts: dict[str, int] = {}
        self.current_memory_mb = 0
    
    def get(self, key: str) -> Optional[np.ndarray]:
        """Get embedding from cache."""
        if key in self.cache:
            self.access_counts[key] += 1
            return self.cache[key].copy()
        return None
    
    def put(self, key: str, embedding: np.ndarray) -> None:
        """
        Put embedding in cache.
        
        Evicts least-recently-used items if necessary.
        """
        if key in self.cache:
            self.cache[key] = embedding
            self.access_counts[key] += 1
            return
        
        # Estimate memory
        embedding_size_mb = embedding.nbytes / 1024 / 1024
        
        # Evict if needed
        while (
            len(self.cache) >= self.max_items
            or self.current_memory_mb + embedding_size_mb > self.max_memory_mb
        ) and self.cache:
            lru_key = min(self.cache.keys(), key=lambda k: self.access_counts.get(k, 0))
            self.current_memory_mb -= self.cache[lru_key].nbytes / 1024 / 1024
            del self.cache[lru_key]
            del self.access_counts[lru_key]
        
        # Add new embedding
        self.cache[key] = embedding
        self.access_counts[key] = 1
        self.current_memory_mb += embedding_size_mb
    
    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()
        self.access_counts.clear()
        self.current_memory_mb = 0
    
    def stats(self) -> dict:
        """Get cache statistics."""
        return {
            "items": len(self.cache),
            "memory_mb": round(self.current_memory_mb, 2),
            "max_items": self.max_items,
            "max_memory_mb": self.max_memory_mb,
            "utilization": round(len(self.cache) / self.max_items * 100, 1),
        }


class OptimizedRetriever:
    """
    Memory-optimized retriever for potato hardware.
    
    Features:
    - Efficient embedding processing
    - Optional index quantization
    - Streaming search
    - Fallback to lexical search
    """
    
    def __init__(
        self,
        embedding_model,
        index,
        hardware_tier: str = "standard",
        use_quantization: bool = False,
    ):
        """
        Initialize retriever.
        
        Args:
            embedding_model: Embedding model for queries
            index: FAISS index
            hardware_tier: Hardware tier for optimization
            use_quantization: Apply quantization
        """
        self.embedding_model = embedding_model
        self.index = index
        self.hardware_tier = hardware_tier
        
        # Determine batch size based on hardware
        batch_sizes = {
            "ultra_lite": 4,
            "lite": 8,
            "standard": 32,
            "full": 64,
        }
        batch_size = batch_sizes.get(hardware_tier, 32)
        
        # Determine quantization
        quant = QuantizationConfig.NONE
        if use_quantization:
            quant = QuantizationConfig.get_recommended(hardware_tier)
        
        # Create processor
        self.processor = VectorizedEmbeddingProcessor(
            embedding_model,
            max_batch_size=batch_size,
            quantization=quant,
        )
        
        # Cache for query embeddings
        cache_items = {
            "ultra_lite": 100,
            "lite": 500,
            "standard": 1000,
            "full": 5000,
        }
        cache_memory = {
            "ultra_lite": 50,
            "lite": 100,
            "standard": 200,
            "full": 500,
        }
        
        self.query_cache = EmbeddingCache(
            max_items=cache_items.get(hardware_tier, 1000),
            max_memory_mb=cache_memory.get(hardware_tier, 200),
        )
    
    def retrieve(
        self,
        query: str,
        k: int = 10,
        use_cache: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retrieve documents for query.
        
        Args:
            query: Query text
            k: Number of results
            use_cache: Use embedding cache
            
        Returns:
            (distances, indices) from FAISS search
        """
        # Check cache
        cache_key = f"{query}::{k}"
        if use_cache:
            cached = self.query_cache.get(cache_key)
            if cached is not None:
                distances, indices = self.index.search(cached.reshape(1, -1), k)
                return distances[0], indices[0]
        
        # Encode query
        query_embedding = self.processor.encode_batch(
            [query],
            normalize=True,
            return_numpy=True,
        )[0]
        
        # Cache embedding
        if use_cache:
            self.query_cache.put(cache_key, query_embedding)
        
        # Search index
        distances, indices = self.index.search(
            query_embedding.reshape(1, -1),
            min(k, self.index.ntotal)
        )
        
        return distances[0], indices[0]


def create_optimized_retriever(
    embedding_model,
    index,
    hardware_auto_detect: bool = True,
) -> OptimizedRetriever:
    """
    Create optimized retriever with hardware-aware configuration.
    
    Args:
        embedding_model: Embedding model
        index: FAISS index
        hardware_auto_detect: Auto-detect hardware tier
        
    Returns:
        Optimized retriever instance
    """
    if hardware_auto_detect:
        from core.lazy_loading import get_model_registry
        registry = get_model_registry()
        tier = registry.tier.value
        use_quantization = registry.should_quantize("embedding")
    else:
        tier = "standard"
        use_quantization = False
    
    logger.info(
        f"Creating optimized retriever for {tier} hardware "
        f"(quantization={use_quantization})"
    )
    
    return OptimizedRetriever(
        embedding_model=embedding_model,
        index=index,
        hardware_tier=tier,
        use_quantization=use_quantization,
    )
