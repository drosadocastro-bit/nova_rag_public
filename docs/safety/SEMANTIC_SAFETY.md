# Semantic Safety Detection

## Overview
Semantic safety detects paraphrased attacks by comparing query meaning to known unsafe intents rather than exact keywords. It catches phrasing like "make the anti-lock brake system not work" that would bypass simple string matching.

## How It Works
1. Embed the query with sentence-transformers (all-MiniLM-L6-v2).
2. Compare against 23 unsafe intent templates.
3. Compare against 13 safe intent templates.
4. Block when unsafe_similarity > threshold and unsafe_similarity > safe_similarity.
5. Confidence is |unsafe - safe| (clamped to 1.0).

## Examples
### Paraphrased Attacks (Blocked)
- "make the anti-lock brake system not work"
- "how can I stop the airbag from deploying"
- "remove the brake safety mechanism"

### Legitimate Queries (Allowed)
- "How do anti-lock brakes work?"
- "What does the ABS warning light mean?"

## Threshold Settings
| Threshold | Behavior | Use Case |
| --- | --- | --- |
| 0.50 | Strict | High-security environments |
| 0.65 | Balanced | Recommended default |
| 0.80 | Lenient | Minimize false positives |

### Tuning Guidance
- Use a held-out dataset of known unsafe vs. legitimate queries to select thresholds empirically
- Evaluate precision/recall/F1 across several thresholds (e.g., 0.50/0.65/0.80) to pick the best trade-off
- Consider operational requirements: minimize false positives for customer support vs. maximize recall for safety-critical contexts

## Setup
### Installation
```bash
pip install sentence-transformers torch
python scripts/download_semantic_models.py
```

### Offline Deployment
```bash
export SEMANTIC_MODEL_PATH=/path/to/models/semantic-safety
```

## Performance
- Speed: ~1000 queries/sec on CPU
- Latency: <100 ms per query
- Model size: ~80 MB
- Fully offline after initial download

## Testing
```bash
pytest tests/safety/test_semantic_safety.py -v
```
