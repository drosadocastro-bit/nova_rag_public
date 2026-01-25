"""
Lazy Loading Module for NIC - Phase 4.2 Performance Optimization.

Provides lazy-loaded model wrappers and hardware tier detection
to enable running NIC on resource-constrained ("potato") hardware.

Features:
- Deferred model loading until first use
- Hardware tier auto-detection (ultra-lite, lite, standard, full)
- Model quantization options for memory savings
- Fallback chain when models unavailable
- Startup time optimization for potato hardware
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Any, Callable, Type
from dataclasses import dataclass
from enum import Enum
import psutil

logger = logging.getLogger(__name__)


class HardwareTier(str, Enum):
    """Hardware capability tiers."""
    
    # Potato hardware: <2GB RAM, single core, slow storage
    ULTRA_LITE = "ultra_lite"
    
    # Low-resource: 2-4GB RAM, 2 cores, SSDs
    LITE = "lite"
    
    # Standard: 4-8GB RAM, 4+ cores
    STANDARD = "standard"
    
    # High-end: 8GB+ RAM, many cores, GPU possible
    FULL = "full"


@dataclass
class HardwareProfile:
    """System hardware capabilities."""
    
    total_memory_gb: float
    available_memory_gb: float
    cpu_count: int
    has_gpu: bool
    estimated_tier: HardwareTier
    
    @classmethod
    def detect(cls) -> "HardwareProfile":
        """Auto-detect hardware profile."""
        total_gb = psutil.virtual_memory().total / 1024 / 1024 / 1024
        available_gb = psutil.virtual_memory().available / 1024 / 1024 / 1024
        cpu_count = psutil.cpu_count(logical=False) or 1
        
        # Detect GPU (simplified - checks for CUDA or MPS)
        has_gpu = False
        try:
            import torch
            has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
        except:
            pass
        
        # Determine tier
        if total_gb < 2:
            tier = HardwareTier.ULTRA_LITE
        elif total_gb < 4:
            tier = HardwareTier.LITE
        elif total_gb < 8:
            tier = HardwareTier.STANDARD
        else:
            tier = HardwareTier.FULL
        
        return cls(
            total_memory_gb=total_gb,
            available_memory_gb=available_gb,
            cpu_count=cpu_count,
            has_gpu=has_gpu,
            estimated_tier=tier,
        )


class LazyModelLoader:
    """
    Lazy-load wrapper for heavyweight models.
    
    Defers loading until first access, enables quantization,
    and provides fallback mechanisms.
    """
    
    def __init__(
        self,
        name: str,
        loader_func: Callable[[], Any],
        quantize: bool = False,
        fallback_loader: Optional[Callable[[], Any]] = None,
        required: bool = False,
    ):
        """
        Initialize lazy loader.
        
        Args:
            name: Model name for logging
            loader_func: Function that loads the model
            quantize: Apply quantization to reduce memory
            fallback_loader: Alternative loader if primary fails
            required: Raise error if loading fails
        """
        self.name = name
        self.loader_func = loader_func
        self.fallback_loader = fallback_loader
        self.quantize = quantize
        self.required = required
        
        self._model: Optional[Any] = None
        self._loading = False
        self._load_error: Optional[str] = None
    
    def load(self) -> Optional[Any]:
        """Load model (idempotent)."""
        if self._model is not None:
            return self._model
        
        if self._loading:
            logger.warning(f"Circular load attempted for {self.name}")
            return None
        
        if self._load_error and self.required:
            raise RuntimeError(f"Failed to load required model {self.name}: {self._load_error}")
        
        self._loading = True
        try:
            logger.info(f"Lazy loading model: {self.name}")
            self._model = self.loader_func()
            
            if self._model is None and self.fallback_loader:
                logger.info(f"Primary loader failed, trying fallback for {self.name}")
                self._model = self.fallback_loader()
            
            if self._model is None:
                if self.required:
                    raise RuntimeError(f"Could not load required model {self.name}")
                logger.warning(f"Failed to load optional model {self.name}")
            
            logger.info(f"Successfully loaded {self.name}")
            return self._model
            
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Error loading {self.name}: {e}")
            if self.required:
                raise
            return None
        finally:
            self._loading = False
    
    def __call__(self, *args, **kwargs):
        """Proxy calls to loaded model."""
        model = self.load()
        if model is None:
            raise RuntimeError(f"Model {self.name} not available")
        return model(*args, **kwargs)
    
    def __getattr__(self, name):
        """Proxy attribute access to loaded model."""
        model = self.load()
        if model is None:
            raise RuntimeError(f"Model {self.name} not available")
        return getattr(model, name)


class ModelRegistry:
    """
    Registry of lazy-loaded models with hardware-aware configuration.
    
    Provides central control point for all model loading across NIC,
    with per-hardware-tier customization.
    """
    
    _instance: Optional["ModelRegistry"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.hardware = HardwareProfile.detect()
        self._models: dict[str, LazyModelLoader] = {}
        
        logger.info(
            f"ModelRegistry initialized for {self.hardware.estimated_tier.value} hardware "
            f"({self.hardware.total_memory_gb:.1f}GB RAM, {self.hardware.cpu_count} CPUs)"
        )
        
        self._configured = False
        self._initialized = True
    
    @property
    def tier(self) -> HardwareTier:
        """Get detected hardware tier."""
        return self.hardware.estimated_tier
    
    def should_quantize(self, model_type: str = "embedding") -> bool:
        """Check if model should be quantized for this hardware."""
        if os.environ.get("NOVA_QUANTIZE_MODELS", "").lower() in ("1", "true", "yes"):
            return True
        
        if self.tier in (HardwareTier.ULTRA_LITE, HardwareTier.LITE):
            return model_type in ("embedding", "cross_encoder")
        
        return False
    
    def should_enable_feature(self, feature: str) -> bool:
        """Check if feature should be enabled for this hardware."""
        disabled = os.environ.get(f"NOVA_DISABLE_{feature.upper()}", "").lower()
        if disabled in ("1", "true", "yes"):
            return False
        
        tier_features = {
            HardwareTier.ULTRA_LITE: {"embeddings", "cache"},
            HardwareTier.LITE: {"embeddings", "cache", "cross_encoder"},
            HardwareTier.STANDARD: {"embeddings", "cache", "cross_encoder", "anomaly"},
            HardwareTier.FULL: {"all"},
        }
        
        enabled = tier_features.get(self.tier, set())
        return feature in enabled or "all" in enabled
    
    def register(
        self,
        name: str,
        loader_func: Callable[[], Any],
        quantize: bool = False,
        fallback_loader: Optional[Callable[[], Any]] = None,
        required: bool = False,
    ) -> LazyModelLoader:
        """Register a lazy-loaded model."""
        model = LazyModelLoader(
            name=name,
            loader_func=loader_func,
            quantize=quantize,
            fallback_loader=fallback_loader,
            required=required,
        )
        self._models[name] = model
        return model
    
    def get(self, name: str) -> Optional[Any]:
        """Get loaded model by name."""
        if name not in self._models:
            logger.warning(f"Model '{name}' not registered")
            return None
        
        return self._models[name].load()
    
    def load_all(self) -> dict[str, Any]:
        """Load all registered models (useful for warmup)."""
        results = {}
        for name, loader in self._models.items():
            try:
                results[name] = loader.load()
            except Exception as e:
                logger.warning(f"Failed to load {name}: {e}")
        return results
    
    def get_stats(self) -> dict[str, Any]:
        """Get statistics about registered models."""
        return {
            "hardware_tier": self.hardware.estimated_tier.value,
            "total_memory_gb": self.hardware.total_memory_gb,
            "available_memory_gb": self.hardware.available_memory_gb,
            "cpu_count": self.hardware.cpu_count,
            "registered_models": len(self._models),
            "loaded_models": sum(1 for m in self._models.values() if m._model is not None),
            "models": {
                name: {
                    "loaded": loader._model is not None,
                    "quantized": loader.quantize,
                    "required": loader.required,
                }
                for name, loader in self._models.items()
            },
        }


def get_model_registry() -> ModelRegistry:
    """Get singleton model registry."""
    return ModelRegistry()


def estimate_memory_for_tier(tier: HardwareTier) -> dict[str, int]:
    """
    Estimate safe memory allocations per component for each tier.
    
    Returns:
        Dict of component -> max_memory_mb
    """
    allocations = {
        HardwareTier.ULTRA_LITE: {
            "embeddings_mb": 100,
            "index_mb": 200,
            "cross_encoder_mb": 50,
            "llm_context_mb": 50,
            "cache_mb": 50,
            "total_mb": 450,
        },
        HardwareTier.LITE: {
            "embeddings_mb": 250,
            "index_mb": 400,
            "cross_encoder_mb": 150,
            "llm_context_mb": 100,
            "cache_mb": 100,
            "total_mb": 1000,
        },
        HardwareTier.STANDARD: {
            "embeddings_mb": 500,
            "index_mb": 800,
            "cross_encoder_mb": 300,
            "llm_context_mb": 200,
            "cache_mb": 200,
            "total_mb": 2000,
        },
        HardwareTier.FULL: {
            "embeddings_mb": 1000,
            "index_mb": 2000,
            "cross_encoder_mb": 500,
            "llm_context_mb": 500,
            "cache_mb": 500,
            "total_mb": 5000,
        },
    }
    
    return allocations.get(tier, allocations[HardwareTier.STANDARD])


# Module initialization
def configure_for_potato_hardware():
    """
    Configure environment for potato hardware operation.
    
    Sets sensible defaults for resource-constrained systems.
    """
    registry = get_model_registry()
    tier = registry.tier
    
    logger.info(f"Configuring for {tier.value} hardware...")
    
    # Set environment variables based on tier
    if tier == HardwareTier.ULTRA_LITE:
        os.environ.setdefault("NOVA_DISABLE_VISION", "1")
        os.environ.setdefault("NOVA_DISABLE_CROSS_ENCODER", "1")
        os.environ.setdefault("NOVA_ANOMALY_DETECTOR", "0")
        os.environ.setdefault("NOVA_EMBED_BATCH_SIZE", "1")
        os.environ.setdefault("NOVA_CACHE_ENABLED", "0")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    
    elif tier == HardwareTier.LITE:
        os.environ.setdefault("NOVA_DISABLE_VISION", "1")
        os.environ.setdefault("NOVA_EMBED_BATCH_SIZE", "8")
        os.environ.setdefault("NOVA_CACHE_ENABLED", "1")
        os.environ.setdefault("NOVA_CACHE_MAX_SIZE", "100")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
    
    elif tier == HardwareTier.STANDARD:
        os.environ.setdefault("NOVA_EMBED_BATCH_SIZE", "32")
        os.environ.setdefault("NOVA_CACHE_ENABLED", "1")
        os.environ.setdefault("NOVA_CACHE_MAX_SIZE", "500")
        os.environ.setdefault("OMP_NUM_THREADS", "2")
    
    logger.info(f"Potato hardware configuration complete for {tier.value}")
