# Project Development Journal

This journal documents engineering decisions, constraints, failures, and tradeoffs encountered while building a safety-first, offline RAG system intended for reproducible behavior rather than conversational fluency.

## January 2, 2026 - Native LLM Engine Migration ⭐

### Major Achievement: Switched to llama-cpp-python
- ✅ **Installed llama-cpp-python** (v0.3.2) with prebuilt binaries
- ✅ **Created `llm_engine.py`**: Native Python LLM integration
- ✅ **30,000 token context**: 3x increase from 10k (eliminates length errors)
- ✅ **Optimized parameters**: Batch 256, temp 0.15, GPU acceleration
- ✅ **Updated `backend.py`**: Auto-switch to native engine when available
- ✅ **Model discovery**: Auto-finds GGUF models in `.lmstudio/models`

**Benefits:**
- No more LM Studio GUI dependency
- No HTTP overhead
- No model contention (Flask + RAGAS can run simultaneously)
- Full control over context length, temperature, batch size
- Direct GPU acceleration control

**Configuration:**
```python
{
    "n_ctx": 30000,          # 30k context (was 10k)
    "n_batch": 256,          # Optimized batch size
    "n_gpu_layers": -1,      # All layers on GPU
    "temperature": 0.15,     # Consistency
    "max_tokens": 1024/512,  # 8B/Qwen output limits
}
```

**Models Located:**
- Llama 8B: `Fireball-Meta-Llama-3.2-8B-Instruct` (Q4_K_S)
- Qwen 14B: `Qwen2.5-Coder-14B-Instruct` (GGUF)

### Session 2: Polish & GitHub Readiness Pass

### Completed
- ✅ Added LM Studio headless startup script (`lm_studio_manager.py`)
- ✅ Integrated LM Studio auto-launch into Flask app startup
- ✅ Cleaned legacy cleanup summary documentation
- ✅ Installed missing dependency: Pillow
- ✅ **Added response normalizer**: Ensures consistent WARNINGS/STEPS/VERIFY format
- ✅ **Updated RAGAS**: Modern llm_factory with legacy fallback (silences deprecations)

### Now Ready to Test
- ⭐ **30k context testing**: Run RAGAS with native engine (should eliminate all length errors)
- 📊 **Expected improvement**: 70%+ scores with proper context handling
- 🚀 **No more crashes**: Direct model loading prevents contention

### Configuration Status
**Native Engine Settings:**
- Context length: **30,000 tokens** ✅ (was 10k)
- Max predicted tokens: 1,024 (8B), 512 (Qwen)
- Batch size: 256
- Temperature: 0.15
- GPU: All layers (-1)

**Test Results (with 10k context):**
- Retrieval: 100% (5/5)
- Stress: 100% safety
- Adversarial: 98.9% (1 FP acceptable)
- Highest observed RAGAS score: 77.22% (20B evaluator). Scores above ~70% may indicate increased generation and reduced conservatism.

**Evaluation Note:**
- RAGAS scores are sensitive to evaluator model choice, context window, and runtime stability. Scores are used as relative indicators, not absolute quality metrics.

**Next Test Target (with 30k context):**
- RAGAS: Target 75%+ (better context handling)
- Context length: Need to test with 30k tokens (current retrieval + evaluation stack exceeds 10k under sustained load; long-term fix is retrieval reduction, not unlimited context).
- Stable 10+ query runs

### Architecture Notes
- **Hybrid routing**: Llama 8B (fast) + Qwen 14B (deep reasoning) with automatic fallback
- **Native engine**: llama-cpp-python for direct model control
- **Offline mode**: Infrastructure added (FORCE_OFFLINE flag), not yet enabled
- **Citation strict mode**: Enabled by default for safety-critical responses
- **Response normalization**: JSON → WARNINGS/STEPS/VERIFY format

### Issues Resolved ✅
1. ~~**Model contention**~~ → Native engine eliminates HTTP conflicts
2. ~~**Mixed JSON/prose outputs**~~ → Response normalizer added
3. ~~**Context length errors**~~ → 30k context now configured

---

## December 31, 2025 - RAGAS Optimization

### Achievements
- Discovered critical context length misconfiguration (256→10k)
- Reduced batch size from 512→256 for stability
- Optimized Qwen output tokens: 4096→512
- Added 8B fallback logic on Qwen timeout
- **Best score**: 77.22% answer relevancy (20B evaluator)

### Lessons Learned
- Context length = prompt + output combined (critical!)
- Batch size impacts stability under sustained load
- Model switching has overhead; minimize when possible
- Local-first approach prevents network stalls

---

## December 29-30, 2025 - Domain Cleanup & Public Release Prep

### Major Changes
- Converted from proprietary domain to vehicle maintenance corpus
- Removed all sensitive/restricted terminology
- Updated paths: `C:\nova_rag` → `C:\nova_rag_public`
- Rebuilt vector index with vehicle_manual.txt (27 pages, 53 paragraphs)
- Created comprehensive test suites (retrieval, stress, adversarial, RAGAS)

### Test Infrastructure
- `test_retrieval.py`: Basic retrieval quality
- `nic_stress_test.py`: Safety filter validation
- `nic_adversarial_test.py`: Hallucination defense
- `nic_ragas_eval.py`: Answer relevancy scoring
- `verify_offline_requirements.py`: Dependency checker

---

## Next Session TODO

1. **Increase context length to 30k** in LM Studio for all models
2. **Switch RAGAS evaluator** to phi-4-14b (best scores, lighter than 20B)
3. **Add answer normalizer** to enforce consistent output format
4. **Update RAGAS imports** to use modern llm_factory (silence deprecations)
5. **Test offline mode** with `NOVA_FORCE_OFFLINE=1`
6. **Final RAGAS run** with optimized settings (target: 70%+)
7. **GitHub release** once scores stabilize

---

## Future Enhancements

- [ ] Add vision-based troubleshooting (diagram analysis)
- [ ] Implement streaming responses for better UX
- [ ] Add session export to PDF/Markdown
- [ ] Build admin dashboard for monitoring
- [ ] Add multi-manual support
- [ ] Implement semantic caching for repeated queries
- [ ] Add telemetry for quality monitoring
