"""
LLM Engine - Native Python LLM Integration
===========================================
Direct llama-cpp-python integration for full control over model parameters.
Eliminates LM Studio GUI dependency and provides optimal configuration.

Configuration:
- 30,000 token context (prevents length errors)
- Low temperature (0.15) for consistency
- Optimized batch sizes and threading
- GPU acceleration when available
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Try importing llama-cpp-python
Llama = None  # type: ignore
try:
    from llama_cpp import Llama  # type: ignore
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False
    logger.warning("llama-cpp-python not installed - falling back to HTTP client")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Model paths (adjust to your LM Studio model cache or custom location)
username = os.environ.get("USERNAME", os.environ.get("USER", "user"))
MODEL_DIR = Path(os.environ.get("NOVA_MODEL_DIR", rf"C:\Users\{username}\.lmstudio\models"))

# Model configurations optimized for NIC
MODEL_CONFIGS = {
    "llama-8b": {
        "name": "Fireball-Meta-Llama-3.2-8B",  # Matches QuantFactory model
        "n_ctx": 30000,              # 30k context (up from 10k)
        "n_batch": 256,              # Batch size for prompt processing
        "n_threads": 8,              # CPU threads (adjust for your system)
        "n_gpu_layers": -1,          # Use GPU if available (-1 = all layers)
        "temperature": 0.15,         # Low temp for consistency
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 1024,          # Output limit
        "use_mlock": True,           # Keep model in RAM
        "use_mmap": True,            # Memory-map model file
        "verbose": False,
    },
    "qwen-14b": {
        "name": "Qwen2.5-Coder-14B",  # Matches lmstudio-community model
        "n_ctx": 30000,
        "n_batch": 256,
        "n_threads": 8,
        "n_gpu_layers": -1,
        "temperature": 0.15,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": 512,           # Qwen: lower output for speed
        "use_mlock": True,
        "use_mmap": True,
        "verbose": False,
    },
}

# =============================================================================
# LLM ENGINE
# =============================================================================

class LLMEngine:
    """
    Native Python LLM engine using llama-cpp-python.
    Provides full control over model parameters and eliminates HTTP overhead.
    """
    
    def __init__(self):
        self.models: Dict[str, Any] = {}
        self.model_dir = MODEL_DIR
        
    def find_model_path(self, model_name: str) -> Optional[Path]:
        """Find GGUF model file in LM Studio cache or custom directory."""
        # Common patterns for LM Studio model naming
        patterns = [
            f"**/*{model_name}*.gguf",
            f"**/*{model_name}*.GGUF",
            f"{model_name}*.gguf",
        ]
        
        for pattern in patterns:
            matches = list(self.model_dir.glob(pattern))
            if matches:
                # Prefer Q4_K_M or Q5_K_M quantization for balance
                for match in matches:
                    if "Q4_K_M" in match.name or "Q5_K_M" in match.name:
                        return match
                # Fall back to first match
                return matches[0]
        
        return None
    
    def load_model(self, model_key: str) -> bool:
        """
        Load a model into memory.
        
        Args:
            model_key: "llama-8b" or "qwen-14b"
            
        Returns:
            True if loaded successfully
        """
        if not LLAMA_CPP_AVAILABLE:
            logger.error("llama-cpp-python not available")
            return False
        
        if model_key in self.models:
            logger.info(f"Model {model_key} already loaded")
            return True
        
        config = MODEL_CONFIGS.get(model_key)
        if not config:
            logger.error(f"Unknown model key: {model_key}")
            return False
        
        model_path = self.find_model_path(config["name"])
        if not model_path:
            logger.error(f"Model file not found for {config['name']}")
            logger.info(f"Searched in: {self.model_dir}")
            return False
        
        logger.info(f"Loading {model_key} from {model_path.name}...")
        
        try:
            # Extract generation params (don't pass to constructor)
            gen_params = {
                "temperature", "top_p", "top_k", 
                "repeat_penalty", "max_tokens"
            }
            model_params = {k: v for k, v in config.items() 
                          if k not in gen_params and k != "name"}

            if Llama is None:  # Safety for type checkers
                raise RuntimeError("llama-cpp-python is not available")
            
            model = Llama(
                model_path=str(model_path),
                **model_params
            )
            
            self.models[model_key] = {
                "model": model,
                "config": config,
                "path": model_path
            }
            
            logger.info(f"✓ {model_key} loaded successfully")
            logger.info(f"  Context: {config['n_ctx']:,} tokens")
            logger.info(f"  Batch: {config['n_batch']}")
            logger.info(f"  GPU layers: {config['n_gpu_layers']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load {model_key}: {e}")
            return False
    
    def generate(self, prompt: str, model_key: str = "llama-8b", **override_params) -> str:
        """
        Generate text using loaded model.
        
        Args:
            prompt: Input prompt
            model_key: Which model to use
            **override_params: Override default generation params
            
        Returns:
            Generated text
        """
        # Load model if not already loaded
        if model_key not in self.models:
            if not self.load_model(model_key):
                raise RuntimeError(f"Failed to load model: {model_key}")
        
        model_data = self.models[model_key]
        model = model_data["model"]
        config = model_data["config"]
        
        # Build generation params
        gen_params = {
            "temperature": config.get("temperature", 0.15),
            "top_p": config.get("top_p", 0.9),
            "top_k": config.get("top_k", 40),
            "repeat_penalty": config.get("repeat_penalty", 1.1),
            "max_tokens": config.get("max_tokens", 1024),
        }
        gen_params.update(override_params)
        
        try:
            response = model(
                prompt,
                **gen_params,
                echo=False,  # Don't include prompt in output
            )
            
            # Extract text from response
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    return choices[0].get("text", "").strip()
            
            return str(response).strip()
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
    
    def unload_model(self, model_key: str):
        """Unload model from memory."""
        if model_key in self.models:
            del self.models[model_key]
            logger.info(f"Unloaded {model_key}")
    
    def unload_all(self):
        """Unload all models."""
        self.models.clear()
        logger.info("All models unloaded")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_engine = None

def get_engine() -> LLMEngine:
    """Get or create global LLM engine instance."""
    global _engine
    if _engine is None:
        _engine = LLMEngine()
    return _engine


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def call_llm(prompt: str, model: str = "llama", **kwargs) -> str:
    """
    Convenience function for LLM calls (matches backend.py API).
    
    Args:
        prompt: Input text
        model: "llama" (8B) or "qwen" (14B)
        **kwargs: Override generation params
        
    Returns:
        Generated text
    """
    engine = get_engine()
    
    # Map model aliases
    model_key = "llama-8b" if model.lower() in ["llama", "fast", "8b"] else "qwen-14b"
    
    return engine.generate(prompt, model_key, **kwargs)


def preload_models():
    """Preload both models at startup (optional for faster first response)."""
    engine = get_engine()
    logger.info("Preloading models...")
    engine.load_model("llama-8b")
    engine.load_model("qwen-14b")
    logger.info("Models ready")


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("LLM Engine Test")
    print("=" * 70)
    
    engine = get_engine()
    
    # Test Llama 8B
    print("\n[1/2] Testing Llama 8B...")
    response = call_llm(
        "What are the three most important things to check if a car won't start?",
        model="llama"
    )
    print(f"\nResponse:\n{response}\n")
    
    # Test Qwen 14B
    print("\n[2/2] Testing Qwen 14B...")
    response = call_llm(
        "Explain the diagnostic code P0420 in one sentence.",
        model="qwen"
    )
    print(f"\nResponse:\n{response}\n")
    
    print("=" * 70)
    print("✓ Test complete")
    print("=" * 70)
