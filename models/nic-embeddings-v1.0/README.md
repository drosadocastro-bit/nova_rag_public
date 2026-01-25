# NIC Embeddings v1.0

Fine-tuned for technical documentation retrieval.

## Training Details

- **Base Model**: C:/nova_rag_public/models/all-MiniLM-L6-v2
- **Training Pairs**: 3607
- **Validation Pairs**: 403
- **Epochs**: 2
- **Batch Size**: 16
- **Learning Rate**: 2e-05
- **Training Date**: 2026-01-23

## Domain Distribution

- **electronics**: 160 pairs (4.0%)
- **forklift**: 1082 pairs (27.0%)
- **hvac**: 140 pairs (3.5%)
- **radar**: 674 pairs (16.8%)
- **vehicle**: 1500 pairs (37.4%)
- **vehicle_civilian**: 454 pairs (11.3%)

## Usage

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('models/nic-embeddings-v1.0')
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
