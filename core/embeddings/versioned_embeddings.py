"""
Phase 3.5: Versioned Embeddings with Model Artifacts

Manages fine-tuned embedding models as immutable, versioned artifacts with
SHA-256 integrity checking. Each model version is frozen and tracked with
complete metadata for reproducibility and audit.

Models stored in: models/nic-embeddings-v{version}/
  - pytorch_model.bin (fine-tuned weights)
  - config.json (sentence-transformers config)
  - model_card.json (metadata, training info, benchmarks)
"""

import json
import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class ModelCard:
    """Metadata for versioned embedding model."""
    name: str
    version: str
    base_model: str
    training_corpus_hash: str
    training_date: str
    training_commit: Optional[str]
    
    # Benchmark metrics
    recall_at_5_baseline: float
    recall_at_5_finetuned: float
    mean_reciprocal_rank: float
    
    # Technical details
    embedding_dimension: int
    total_params: int
    trainable_params: int
    
    # Model weights SHA-256 for tamper detection
    weights_hash: str
    config_hash: str
    
    # Performance on adversarial tests
    adversarial_tests_passed: int
    adversarial_tests_total: int
    
    # Safety notes
    notes: str = ""
    
    def is_safety_validated(self) -> bool:
        """Check if model passed all safety tests."""
        return self.adversarial_tests_passed == self.adversarial_tests_total
    
    def improvement_pct(self) -> float:
        """Calculate recall improvement as percentage."""
        if self.recall_at_5_baseline == 0:
            return 0
        return (
            (self.recall_at_5_finetuned - self.recall_at_5_baseline) /
            self.recall_at_5_baseline * 100
        )


class VersionedEmbeddings:
    """Load and manage versioned embedding models with validation."""
    
    MODELS_DIR = Path('models')
    BASELINE_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
    
    def __init__(self, version: Optional[str] = None, fallback_to_baseline: bool = True):
        """
        Initialize embeddings with optional version.
        
        Args:
            version: Model version (e.g., 'v1.0'). If None, use baseline.
            fallback_to_baseline: If specified version unavailable, use baseline.
        """
        self.version = version
        self.fallback_to_baseline = fallback_to_baseline
        self.model = None
        self.model_card = None
        self.model_path = None
        
        self._load_model()
    
    def _load_model(self) -> None:
        """Load model with fallback strategy."""
        if self.version:
            success = self._load_versioned_model()
            if not success and self.fallback_to_baseline:
                logger.warning(f"Failed to load version {self.version}, falling back to baseline")
                self._load_baseline_model()
        else:
            self._load_baseline_model()
    
    def _load_versioned_model(self) -> bool:
        """Load fine-tuned model from versioned directory."""
        try:
            model_dir = self.MODELS_DIR / f'nic-embeddings-{self.version}'
            
            if not model_dir.exists():
                logger.warning(f"Model directory not found: {model_dir}")
                return False
            
            # Load model card
            card_path = model_dir / 'model_card.json'
            if card_path.exists():
                with open(card_path, 'r') as f:
                    card_dict = json.load(f)
                    self.model_card = ModelCard(**card_dict)
            
            # Verify integrity
            if not self._verify_integrity(model_dir):
                logger.error(f"Model integrity check failed for {model_dir}")
                return False
            
            # Load model
            self.model = SentenceTransformer(str(model_dir))
            self.model_path = model_dir
            
            logger.info(f"✅ Loaded fine-tuned model: {model_dir}")
            if self.model_card:
                logger.info(f"   Recall improvement: {self.model_card.improvement_pct():.1f}%")
                logger.info(f"   Safety: {self.model_card.adversarial_tests_passed}/{self.model_card.adversarial_tests_total} tests passed")
            
            return True
        
        except Exception as e:
            logger.error(f"Error loading versioned model: {e}")
            return False
    
    def _load_baseline_model(self) -> None:
        """Load baseline sentence-transformers model."""
        try:
            self.model = SentenceTransformer(self.BASELINE_MODEL)
            self.version = 'baseline'
            logger.info(f"✅ Loaded baseline model: {self.BASELINE_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load baseline model: {e}")
            raise
    
    def _verify_integrity(self, model_dir: Path) -> bool:
        """Verify model integrity via SHA-256 hashes."""
        try:
            card_path = model_dir / 'model_card.json'
            weights_path = model_dir / 'pytorch_model.bin'
            config_path = model_dir / 'config.json'
            
            if not card_path.exists() or not weights_path.exists():
                logger.error(f"Missing required files in {model_dir}")
                return False
            
            # Compute hashes
            weights_hash = self._compute_file_hash(weights_path)
            config_hash = self._compute_file_hash(config_path) if config_path.exists() else ""
            
            # Load card and verify
            with open(card_path, 'r') as f:
                card_dict = json.load(f)
            
            if card_dict.get('weights_hash') != weights_hash:
                logger.error(f"Weights hash mismatch for {model_dir}")
                return False
            
            if config_path.exists() and card_dict.get('config_hash') != config_hash:
                logger.error(f"Config hash mismatch for {model_dir}")
                return False
            
            logger.info(f"✅ Model integrity verified: {model_dir}")
            return True
        
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            return False
    
    def _compute_file_hash(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Compute SHA-256 hash of file (streaming for large files)."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def encode(self, sentences, *args, **kwargs):
        """
        Encode sentences to embeddings.
        
        Args:
            sentences: Text or list of texts to encode
            
        Returns:
            Embeddings as numpy array
        """
        if self.model is None:
            raise RuntimeError("No model loaded")
        
        return self.model.encode(sentences, *args, **kwargs)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get current model information."""
        info = {
            'version': self.version,
            'model': self.model_path or self.BASELINE_MODEL,
            'has_card': self.model_card is not None,
        }
        
        if self.model_card:
            info.update({
                'recall_improvement_pct': self.model_card.improvement_pct(),
                'adversarial_tests': f"{self.model_card.adversarial_tests_passed}/{self.model_card.adversarial_tests_total}",
                'safety_validated': self.model_card.is_safety_validated(),
            })
        
        return info


class ModelArtifactCreator:
    """Create versioned model artifacts with metadata."""
    
    def __init__(self, models_dir: Path = Path('models')):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    def save_finetuned_model(
        self,
        model: SentenceTransformer,
        version: str,
        training_corpus_hash: str,
        benchmark_scores: Dict[str, float],
        adversarial_results: Tuple[int, int],
        training_commit: Optional[str] = None
    ) -> Path:
        """
        Save fine-tuned model as versioned artifact.
        
        Args:
            model: Trained SentenceTransformer model
            version: Version string (e.g., 'v1.0')
            training_corpus_hash: SHA-256 of training dataset
            benchmark_scores: Dict with 'recall_at_5_baseline', 'recall_at_5_finetuned', 'mrr'
            adversarial_results: Tuple of (passed, total) test count
            training_commit: Git commit hash of training code (optional)
            
        Returns:
            Path to saved model directory
        """
        model_dir = self.models_dir / f'nic-embeddings-{version}'
        model_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"💾 Saving model artifact: {model_dir}")
        
        # Save model
        model.save(str(model_dir))
        logger.info(f"   ✅ Model weights saved")
        
        # Compute hashes
        weights_path = model_dir / 'pytorch_model.bin'
        config_path = model_dir / 'config.json'
        
        weights_hash = self._compute_hash(weights_path)
        config_hash = self._compute_hash(config_path) if config_path.exists() else ""
        
        logger.info(f"   ✅ SHA-256 hashes computed")
        
        # Create model card
        embedding_dim = model.get_sentence_embedding_dimension()
        if embedding_dim is None:
            embedding_dim = 0

        card = ModelCard(
            name=f'nic-embeddings-{version}',
            version=version,
            base_model='sentence-transformers/all-MiniLM-L6-v2',
            training_corpus_hash=training_corpus_hash,
            training_date=datetime.now().isoformat(),
            training_commit=training_commit,
            
            recall_at_5_baseline=benchmark_scores.get('recall_at_5_baseline', 0),
            recall_at_5_finetuned=benchmark_scores.get('recall_at_5_finetuned', 0),
            mean_reciprocal_rank=benchmark_scores.get('mrr', 0),
            
            embedding_dimension=embedding_dim,
            total_params=sum(p.numel() for p in model.parameters()),
            trainable_params=sum(p.numel() for p in model.parameters() if p.requires_grad),
            
            weights_hash=weights_hash,
            config_hash=config_hash,
            
            adversarial_tests_passed=adversarial_results[0],
            adversarial_tests_total=adversarial_results[1],
            
            notes="Fine-tuned for safety-critical technical documentation retrieval"
        )
        
        # Save card
        card_path = model_dir / 'model_card.json'
        with open(card_path, 'w') as f:
            json.dump(asdict(card), f, indent=2)
        
        logger.info(f"   ✅ Model card saved")
        logger.info(f"\n📊 Model Summary:")
        logger.info(f"   Version: {version}")
        logger.info(f"   Recall improvement: {card.improvement_pct():.1f}%")
        logger.info(f"   MRR: {card.mean_reciprocal_rank:.3f}")
        logger.info(f"   Params: {card.total_params:,} total, {card.trainable_params:,} trainable")
        logger.info(f"   Safety: {card.adversarial_tests_passed}/{card.adversarial_tests_total} adversarial tests passed")
        
        return model_dir
    
    def _compute_hash(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Compute SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()


# Example usage
if __name__ == '__main__':
    # Load baseline embeddings
    embeddings = VersionedEmbeddings()
    
    # Encode sample text
    text = ["How do I check the tire pressure?", "Engine maintenance procedures"]
    embeddings_result = embeddings.encode(text)
    print(f"Baseline embeddings shape: {embeddings_result.shape}")
    
    # Try to load fine-tuned model (will fallback to baseline if not available)
    embeddings_v1 = VersionedEmbeddings(version='v1.0', fallback_to_baseline=True)
    print(f"\nModel info: {embeddings_v1.get_model_info()}")
