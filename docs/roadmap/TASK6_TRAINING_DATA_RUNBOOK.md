# Task 6: Training Data Generation Runbook

**Goal:** Produce 5k–10k high-quality contrastive pairs for fine-tuning domain embeddings without degrading safety.
**Status:** Ready to run (generator implemented and validated).

---

## 1) Prereqs
- Corpus organized under `data/` with domain subdirectories (e.g., `vehicle_civilian`, `vehicle_military`, `forklift`).
- Python env activated with project requirements installed.
- Disk headroom: ~50 MB for output + temp files.

## 2) Recommended Command
```bash
python scripts/generate_finetuning_data.py \
  --corpus-dir data/ \
  --output data/finetuning/training_pairs.jsonl \
  --pairs-per-domain 1200 \
  --include-hard-negatives
```
- `pairs-per-domain 1200` yields ~6k pairs across five domains; adjust to hit 5k–10k.
- Use `--domains vehicle_civilian vehicle_military forklift hvac radar` if you want an explicit include list.

## 3) Quality Guardrails
- Automatic:
  - Duplicate removal and length filtering (<50 chars dropped).
  - Hard negatives sampled cross-domain plus near-miss within domain.
  - Keyword overlap sanity check between query/positive.
- Manual spot check: sample 100 pairs and verify question ↔ positive relevance and negative mismatch.

## 4) Validation Steps
1. Run unit tests: `pytest tests/unit/test_training_data_generator.py`.
2. Quick validator: `python validate_training_generator.py --sample 50 --path data/finetuning/training_pairs.jsonl`.
3. Domain distribution check: ensure pair counts roughly align with corpus (no single domain >40% unless intended).

## 5) Outputs
- Primary dataset: `data/finetuning/training_pairs.jsonl` (JSONL triplets with metadata).
- Logs: stdout INFO detailing per-domain counts and hard-negative usage.

## 6) Acceptance Criteria
- Size: 5k–10k pairs generated without errors.
- Quality: ≤5% bad pairs in manual sample of 100.
- Coverage: Each active domain represented; no dominant domain unless expected by corpus size.

## 7) Next Steps After Generation
- Snapshot hashes of the dataset and record in the model card before fine-tuning.
- Proceed to Task 7 fine-tuning using the generated JSONL.
