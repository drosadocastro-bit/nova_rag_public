# Task 7: Fine-Tune Domain-Specific Embeddings - Execution Runbook

**Status**: In Progress  
**Phase**: 3.5 (Neural Advisory Layer)  
**Objective**: Fine-tune sentence-transformer embeddings on 4,010 domain-specific training pairs  

---

## Quick Start

### Prerequisites
Ensure dependencies are installed:
```bash
pip install sentence-transformers torch scikit-learn
```

### Run Training
```bash
cd C:/nova_rag_public

# Standard configuration (5 epochs, 32 batch size)
python scripts/finetune_embeddings.py \
  --data-file data/finetuning/training_pairs.jsonl \
  --output-dir models/nic-embeddings-v1.0 \
  --epochs 5 \
  --batch-size 32 \
  --learning-rate 2e-5 \
  --freeze-layers 10 \
  --seed 42

# Or use defaults (equivalent to above)
python scripts/finetune_embeddings.py
```

### Expected Output
```
Fine-tuning will:
1. Load 4,010 training pairs from JSONL file
2. Split into 90% train (3,609 pairs) / 10% val (401 pairs)
3. Initialize all-MiniLM-L6-v2 base model
4. Freeze bottom 10 transformer layers (12 total)
5. Train for 5 epochs with validation every 100 steps
6. Save checkpoints and best model to models/nic-embeddings-v1.0/
7. Generate model card with metadata

Total time: ~30-60 minutes (GPU) or ~2-4 hours (CPU)
```

---

## Configuration Guide

### Training Parameters

| Parameter | Default | Range | Notes |
|-----------|---------|-------|-------|
| `--epochs` | 5 | 3-10 | More epochs = better fit, risk of overfit |
| `--batch-size` | 32 | 8-128 | Larger = more memory, faster convergence |
| `--learning-rate` | 2e-5 | 1e-6 to 1e-4 | Lower = slower, more stable; higher = faster, risky |
| `--freeze-layers` | 10 | 0-12 | More frozen = preserve general knowledge |
| `--val-ratio` | 0.1 | 0.05-0.2 | Validation set size |

### Recommended Configurations

**Fast Training (GPU)**
```bash
python scripts/finetune_embeddings.py \
  --epochs 3 \
  --batch-size 64 \
  --learning-rate 5e-5
```
Runs in ~20 minutes, good for testing.

**Production (GPU)**
```bash
python scripts/finetune_embeddings.py \
  --epochs 5 \
  --batch-size 32 \
  --learning-rate 2e-5 \
  --freeze-layers 10
```
Recommended: ~40-60 minutes, best quality.

**CPU Mode**
```bash
python scripts/finetune_embeddings.py \
  --device cpu \
  --batch-size 16 \
  --epochs 3
```
Slower but works on CPU: ~3-4 hours for 3 epochs.

---

## Architecture Details

### Model Setup
- **Base Model**: sentence-transformers/all-MiniLM-L6-v2
  - Dimensions: 384
  - Parameters: ~22M
  - Pooling: Mean pooling over token embeddings

- **Layer Freezing**: Bottom 10 / 12 transformer blocks frozen
  - Preserves general linguistic knowledge
  - Only fine-tunes 2 top layers + pooling layer
  - Reduces overfitting risk on small dataset

### Loss Function
- **MultipleNegativesRankingLoss**
  - Treats batch negatives as hard negatives
  - Maximizes similarity(query, positive) - similarity(query, negatives)
  - In-batch negatives: 31 additional negatives per triplet (batch_size=32)

### Data Processing
1. **Load**: Read 4,010 pairs from JSONL
2. **Split**: 90/10 train/val stratified by domain
3. **Dataset**: TripletsDataset yields (query, positive, negative, domain)
4. **Loader**: DataLoader with shuffling, batch_size=32, drop_last=True

### Optimization
- **Optimizer**: AdamW (weight_decay=0.01)
- **Learning Rate Schedule**: Cosine Annealing with warm restarts
  - Starts at 2e-5
  - Decays to ~1e-6 by end
  - Helps escape local minima

### Evaluation
Runs every 100 steps (every ~3 batches):
- **Recall@5**: % queries where top-5 contains positive
- **MRR**: Mean reciprocal rank of first correct match
- **Per-domain metrics**: Breakdown by electronics, forklift, hvac, radar, vehicle, vehicle_civilian

---

## Output Structure

After training, check `models/nic-embeddings-v1.0/`:

```
models/nic-embeddings-v1.0/
├── pytorch_model.bin          # Final model weights
├── config.json                # Model config
├── tokenizer.json             # Tokenizer
├── tokenizer_config.json      # Tokenizer config
├── sentence_bert_config.json  # Sentence-BERT pooling config
├── README.md                  # Model card (human-readable)
├── metadata.json              # Training metadata (JSON)
├── training.log               # Training logs
├── checkpoint-epoch-1/        # Checkpoint after epoch 1
├── checkpoint-epoch-2/        # ...
├── checkpoint-epoch-3/        # ...
├── checkpoint-epoch-4/        # ...
├── checkpoint-epoch-5/        # Final checkpoint
└── checkpoint-best/           # Best validation metric checkpoint
```

### Verify Model Was Saved
```bash
# Check file exists and has content
ls -lh models/nic-embeddings-v1.0/pytorch_model.bin

# Load model to test
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('models/nic-embeddings-v1.0')
test_embedding = model.encode('How do I reset the engine?')
print(f'Embedding shape: {test_embedding.shape}')
print(f'Sample values: {test_embedding[:5]}')
"
```

---

## Validation & Testing

### Check Training Metrics
```bash
# View training log
tail -50 models/nic-embeddings-v1.0/training.log

# Or live monitoring
tail -f models/nic-embeddings-v1.0/training.log
```

### Test Model Performance
```python
from sentence_transformers import SentenceTransformer, util

# Load fine-tuned model
model = SentenceTransformer('models/nic-embeddings-v1.0')

# Test query
query = "How do I reset the engine fault code?"
documents = [
    "Engine Fault Code Reset: Turn ignition OFF, wait 30 seconds, turn ON.",
    "Weather radar maintenance requires periodic calibration checks.",
]

# Encode
query_emb = model.encode(query)
doc_embs = model.encode(documents)

# Compute similarities
scores = util.cos_sim(query_emb, doc_embs)
print(scores)
# Expected: [high_score, low_score] since first doc is relevant
```

### Measure Latency
```python
import time
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('models/nic-embeddings-v1.0')

# Warm up
_ = model.encode("Test query")

# Measure single inference
start = time.time()
for _ in range(100):
    _ = model.encode("How do I page?")
elapsed = (time.time() - start) / 100 * 1000
print(f"Latency per query: {elapsed:.2f}ms")
# Expected: <10ms on modern CPU
```

---

## Troubleshooting

### Issue: Out of Memory (OOM)
**Symptom**: `RuntimeError: CUDA out of memory`

**Solutions**:
1. Reduce batch size: `--batch-size 16`
2. Use CPU: `--device cpu`
3. Reduce frozen layers: `--freeze-layers 8` (trains more params, needs less batch)

### Issue: Training Too Slow
**Symptom**: Each epoch takes >30 minutes

**Solutions**:
1. Use GPU: Ensure `torch.cuda.is_available()` returns True
2. Reduce epochs: `--epochs 3`
3. Increase batch size: `--batch-size 64` (if memory allows)

### Issue: Model Not Improving
**Symptom**: Validation metrics not increasing after epoch 1

**Possible Causes**:
1. Learning rate too high: try `--learning-rate 1e-5`
2. Learning rate too low: try `--learning-rate 5e-5`
3. Frozen layers wrong: try `--freeze-layers 8` or `--freeze-layers 12`

### Issue: File Not Found
**Symptom**: `FileNotFoundError: data/finetuning/training_pairs.jsonl`

**Solution**: Ensure Task 6 (data generation) completed successfully:
```bash
ls -lh data/finetuning/training_pairs.jsonl
```

---

## Integration with Pipeline

### Use in Retrieval (Task 9)
```python
from sentence_transformers import SentenceTransformer

# Load fine-tuned model (replaces base model)
model = SentenceTransformer('models/nic-embeddings-v1.0')

# Use in retrieval pipeline
query = "How do I page?"
query_embedding = model.encode(query)

# Query vector database with embedding
# (Embed document corpus similarly during indexing)
```

### Expected Improvements
- **Baseline**: all-MiniLM-L6-v2 (general domain)
- **Fine-tuned**: nic-embeddings-v1.0 (domain-specific)

Improvements expected:
- +10-20% Recall@5 on domain-specific queries
- +15-25% improvement on technical terminology
- Latency increase: <2ms (from 5ms to 7ms)

---

## Monitoring & Logging

### Real-Time Monitoring
```bash
# Watch training logs as they're written
tail -f models/nic-embeddings-v1.0/training.log

# Extract key metrics
grep "Loss\|Recall@5\|MRR" models/nic-embeddings-v1.0/training.log
```

### Log Entries to Expect
```
[INFO] Random seed set to 42
[INFO] Loaded 4010 training pairs from data/finetuning/training_pairs.jsonl
[INFO] Train/Val split: 3609/401 (10.0% val)
[INFO] Froze bottom 10/12 transformer layers
[INFO] Trainable params: 1,234,567 / 22,000,000
[INFO] Initialized MultipleNegativesRankingLoss
[INFO] Starting training:
[INFO]   Epochs: 5
[INFO]   Batch size: 32
[INFO]   Learning rate: 2e-05
[INFO] Epoch 1/5, Batch 10, Loss: 4.2345, LR: 2.00e-05
[INFO] ============================================================
[INFO] Validation (Epoch 1, Steps 100)
[INFO]   electronics         : Recall@5=0.7234, MRR=0.7456 (16 pairs)
[INFO]   forklift            : Recall@5=0.7912, MRR=0.8123 (109 pairs)
...
[INFO] Saved best model to models/nic-embeddings-v1.0/checkpoint-best
```

---

## Success Criteria

Task 7 is complete when:

✅ Script runs without errors  
✅ Model saves to `models/nic-embeddings-v1.0/`  
✅ README.md and metadata.json created  
✅ Training curves show improvement over epochs  
✅ Recall@5 > 0.70 on validation set  
✅ MRR > 0.65 on validation set  
✅ Inference latency < 10ms per query (on CPU)  
✅ Model can be loaded via `SentenceTransformer()`  

---

## Next Steps

**Task 8**: Train Anomaly Detection Module
- Use fine-tuned embeddings from Task 7
- Train autoencoder on normal query embeddings
- Detect adversarial/out-of-distribution queries

**Task 9**: Integrate Fine-Tuned Model
- Replace base embeddings in retrieval pipeline
- Update vector database with fine-tuned embeddings
- Benchmark end-to-end improvements

**Task 10**: End-to-End Testing & Validation
- Test on safety-critical scenarios
- Measure retrieval quality improvements
- Compare vs baseline embeddings

---

## References

- SentenceTransformers: https://www.sbert.net/
- MultipleNegativesRankingLoss: https://www.sbert.net/docs/package_reference/losses.html
- Fine-tuning guide: https://www.sbert.net/examples/training/sts/training_stsbenchmark_python.html
- Model card template: https://huggingface.co/model_card_template.md
