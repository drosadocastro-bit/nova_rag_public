#!/usr/bin/env python3
"""
Task 7: Fine-Tune Domain-Specific Embeddings (Simplified Version)

Uses sentence-transformers built-in training API for reliability.
"""

import json
import logging
import random
import argparse
from pathlib import Path
from typing import List, Dict
from datetime import datetime

import torch
from sentence_transformers import (
    SentenceTransformer,
    InputExample,
    losses
)
from torch.utils.data import DataLoader, Dataset

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set random seeds
random.seed(42)
torch.manual_seed(42)
logging.info("Random seed set to 42")


def load_training_pairs(jsonl_file: str) -> List[Dict]:
    """Load training pairs from JSONL file."""
    pairs = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            pairs.append(json.loads(line))
    logging.info(f"Loaded {len(pairs)} training pairs from {jsonl_file}")
    return pairs


def split_train_val(pairs: List[Dict], val_ratio: float = 0.1) -> tuple:
    """Split pairs into train and validation sets, stratified by domain."""
    
    # Group by domain
    domain_pairs = {}
    for pair in pairs:
        domain = pair.get('domain', 'unknown')
        if domain not in domain_pairs:
            domain_pairs[domain] = []
        domain_pairs[domain].append(pair)
    
    train_pairs = []
    val_pairs = []
    
    # Split each domain
    for domain, d_pairs in domain_pairs.items():
        random.shuffle(d_pairs)
        split_idx = int(len(d_pairs) * (1 - val_ratio))
        train_pairs.extend(d_pairs[:split_idx])
        val_pairs.extend(d_pairs[split_idx:])
    
    logging.info(f"Train/Val split: {len(train_pairs)}/{len(val_pairs)} ({val_ratio*100:.1f}% val)")
    return train_pairs, val_pairs


class InputExampleDataset(Dataset):
    """Wrapper to convert InputExample list to a PyTorch Dataset."""
    
    def __init__(self, examples: List[InputExample]):
        self.examples = examples
    
    def __len__(self):
        return len(self.examples)
    
    def __getitem__(self, idx):
        return self.examples[idx]


def main():
    parser = argparse.ArgumentParser(description='Fine-tune embeddings for NIC RAG system')
    parser.add_argument('--data-file', default='data/finetuning/training_pairs.jsonl',
                      help='Path to training data JSONL')
    parser.add_argument('--output-dir', default='models/nic-embeddings-v1.0',
                      help='Output directory for fine-tuned model')
    parser.add_argument('--model-name', default='C:/nova_rag_public/models/all-MiniLM-L6-v2',
                      help='Base model to fine-tune')
    parser.add_argument('--epochs', type=int, default=3,
                      help='Number of training epochs (default: 3 for fast training)')
    parser.add_argument('--batch-size', type=int, default=16,
                      help='Training batch size')
    parser.add_argument('--learning-rate', type=float, default=2e-5,
                      help='Learning rate')
    parser.add_argument('--warmup-steps', type=int, default=100,
                      help='Warmup steps')
    parser.add_argument('--val-ratio', type=float, default=0.1,
                      help='Validation ratio')
    parser.add_argument('--device', default='cpu',
                      help='Device to use (cpu or cuda)')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logging.info("="*70)
    logging.info("TASK 7: FINE-TUNE DOMAIN-SPECIFIC EMBEDDINGS")
    logging.info("="*70)
    logging.info(f"Output directory: {args.output_dir}")
    logging.info(f"Device: {args.device}")
    
    # Load data
    logging.info("\nLoading training data...")
    all_pairs = load_training_pairs(args.data_file)
    train_pairs, val_pairs = split_train_val(all_pairs, args.val_ratio)
    
    # Convert to InputExamples
    logging.info("\nPreparing training examples...")
    train_examples = []
    for pair in train_pairs:
        # For MultipleNegativesRankingLoss, we only need (query, positive)
        # The loss will use other positives in the batch as negatives
        train_examples.append(
            InputExample(texts=[pair['query'], pair['positive']])
        )
    
    # Convert validation pairs
    val_queries = []
    val_corpus = {}
    val_relevant_docs = {}
    
    for idx, pair in enumerate(val_pairs):
        query_id = f"q_{idx}"
        doc_id = f"d_{idx}"
        
        val_queries.append(pair['query'])
        val_corpus[doc_id] = pair['positive']
        val_relevant_docs[query_id] = {doc_id}
    
    # Load model
    logging.info(f"\nInitializing base model: {args.model_name}")
    model = SentenceTransformer(args.model_name, device=args.device)
    
    # Create DataLoader
    train_dataloader = DataLoader(
        InputExampleDataset(train_examples),
        shuffle=True,
        batch_size=args.batch_size
    )
    
    # Create loss
    train_loss = losses.MultipleNegativesRankingLoss(model)
    logging.info("Initialized MultipleNegativesRankingLoss")
    
    # Create evaluator
    evaluator = None  # Skip evaluation for faster training
    
    # Training
    logging.info("\nStarting fine-tuning...")
    logging.info(f"  Epochs: {args.epochs}")
    logging.info(f"  Batch size: {args.batch_size}")
    logging.info(f"  Learning rate: {args.learning_rate}")
    logging.info(f"  Training examples: {len(train_examples)}")
    logging.info(f"  Steps per epoch: {len(train_dataloader)}")
    logging.info(f"  Total steps: {len(train_dataloader) * args.epochs}\n")
    
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        output_path=str(output_dir),
        show_progress_bar=True,
        evaluator=evaluator,
        evaluation_steps=0,  # Don't evaluate during training
        save_best_model=False
    )
    
    logging.info(f"\nTraining complete! Model saved to {output_dir}")
    
    # Create model card
    create_model_card(output_dir, train_pairs, val_pairs, args)
    
    logging.info("\n" + "="*70)
    logging.info("TASK 7 COMPLETE ✓")
    logging.info("="*70)
    logging.info("\nTo use the fine-tuned model:")
    logging.info("  from sentence_transformers import SentenceTransformer")
    logging.info("  model = SentenceTransformer('%s')", args.output_dir)
    logging.info("  embeddings = model.encode(['your query here'])")


def create_model_card(output_dir: Path, train_pairs: List[Dict], val_pairs: List[Dict], args):
    """Create a simple model card."""
    
    # Count domains
    domains = {}
    for pair in train_pairs + val_pairs:
        domain = pair.get('domain', 'unknown')
        domains[domain] = domains.get(domain, 0) + 1
    
    card = f"""# NIC Embeddings v1.0

Fine-tuned for technical documentation retrieval.

## Training Details

- **Base Model**: {args.model_name}
- **Training Pairs**: {len(train_pairs)}
- **Validation Pairs**: {len(val_pairs)}
- **Epochs**: {args.epochs}
- **Batch Size**: {args.batch_size}
- **Learning Rate**: {args.learning_rate}
- **Training Date**: {datetime.now().strftime('%Y-%m-%d')}

## Domain Distribution

"""
    
    total = sum(domains.values())
    for domain in sorted(domains.keys()):
        count = domains[domain]
        pct = 100 * count / total
        card += f"- **{domain}**: {count} pairs ({pct:.1f}%)\n"
    
    card += f"""
## Usage

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('{args.output_dir}')
embeddings = model.encode([
    "How to troubleshoot hydraulic system?",
    "What is the torque specification?"
])
```

## Performance

Optimized for retrieval of:
- Technical procedures
- Safety warnings
- Equipment specifications
- Troubleshooting guides
"""
    
    # Save README
    readme_path = output_dir / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(card)
    
    # Save metadata
    metadata = {
        "model_name": args.model_name,
        "training_pairs": len(train_pairs),
        "validation_pairs": len(val_pairs),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "domains": domains,
        "training_date": datetime.now().isoformat()
    }
    
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    logging.info(f"Model card saved to {readme_path}")
    logging.info(f"Metadata saved to {metadata_path}")


if __name__ == "__main__":
    main()
