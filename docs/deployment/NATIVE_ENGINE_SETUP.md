# Native LLM Engine Setup Complete! ✅

> Note: This document describes the legacy LM Studio → native-engine migration. The current stack runs on Ollama (http://127.0.0.1:11434) for local inference. Keep this for archival reference.

## What Changed

### Before
- HTTP client connecting to LM Studio GUI on port 1234
- 10k context length (too small)
- Model contention between Flask and RAGAS
- GUI dependency

### After  
- **Native llama-cpp-python** integration
- **30,000 token context** (3x increase)
- Direct model loading (no HTTP overhead)
- No GUI conflicts
- Full parameter control

## Configuration

**Model Parameters (Optimized):**
```python
{
    "n_ctx": 30000,          # 30k context length
    "n_batch": 256,          # Batch size
    "n_threads": 8,          # CPU threads
    "n_gpu_layers": -1,      # All layers on GPU (if available)
    "temperature": 0.15,     # Low for consistency
    "top_p": 0.9,
    "top_k": 40,
    "repeat_penalty": 1.1,
    "max_tokens": 1024,      # 8B output limit
    # Qwen uses 512 for speed
}
```

**Models Loaded:**
- **Llama 8B**: `Fireball-Meta-Llama-3.2-8B-Instruct` (Q4_K_S quantization)
- **Qwen 14B**: `Qwen2.5-Coder-14B-Instruct` (GGUF)

**Model Location:**
`C:\Users\draku\.lmstudio\models`

## Usage

**Enable native engine** (default):
```python
# In backend.py - automatically used when available
USE_NATIVE_ENGINE = True
```

**Fallback to HTTP** (if needed):
```bash
set NOVA_USE_NATIVE_LLM=0
python nova_flask_app.py
```

**Test the engine:**
```bash
python llm_engine.py
```

## Benefits

### 1. **3x Context Length**
- Before: 10k tokens → length errors
- After: 30k tokens → handles complex queries

### 2. **No Model Contention**
- Before: Flask + RAGAS fight for LM Studio
- After: Each loads models independently

### 3. **Direct Control**
- Full parameter tuning
- No HTTP overhead
- Better error handling
- GPU acceleration control

### 4. **Consistent Performance**
- Optimized batch sizes (256)
- mlock/mmap for RAM efficiency
- Reproducible temperature (0.15)

## Files Modified

1. **`llm_engine.py`** (NEW)
   - Native llama-cpp-python wrapper
   - 30k context configuration
   - Auto model discovery
   - Optimized parameters

2. **`backend.py`**
   - Added native engine import
   - Updated `call_llm()` to use native engine
   - HTTP fallback for compatibility

3. **Updated dependencies:**
   - `llama-cpp-python==0.3.2`

## Next Steps

1. ✅ **Test with Flask**: `python nova_flask_app.py`
2. ✅ **Run RAGAS**: `python nic_ragas_eval.py 5` (should handle 30k context)
3. ✅ **Verify no length errors**: Complex queries should work now
4. 📊 **Compare scores**: Expect 70%+ with proper context

## Troubleshooting

**If models don't load:**
```bash
# Check model path
python -c "from llm_engine import get_engine; print(get_engine().model_dir)"

# Force HTTP fallback
set NOVA_USE_NATIVE_LLM=0
```

**To use custom model directory:**
```bash
set NOVA_MODEL_DIR=C:\path\to\your\models
```

**GPU vs CPU:**
- Current: `-1` (all GPU layers if CUDA available)
- CPU only: Set `n_gpu_layers=0` in MODEL_CONFIGS

---

**Status**: ✅ Ready for testing!

**Expected Improvement**: 30k context should eliminate all length errors and allow RAGAS to run full evaluations without crashes.
