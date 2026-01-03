# LM Studio Configuration for NIC Public

# ============================================
# QUICK START - LM STUDIO SETUP
# ============================================

## 1. Start LM Studio Server
# - Open LM Studio
# - Go to "Local Server" tab
# - Load one of your models:
#   * fireball-meta-llama-3.2-8b-instruct-agent-003-128k-code-dpo (TIER 1: fast)
#   * qwen/qwen2.5-coder-14b (TIER 2: deep reasoning)
#   * phi-4-14b (TIER 3: evaluation only)
# - Click "Start Server"
# - Verify it's running on http://127.0.0.1:1234

## 2. Set Environment Variable (Optional)
# Windows PowerShell:
$env:OPENAI_API_KEY="lm-studio"

# Linux/Mac:
export OPENAI_API_KEY="lm-studio"

## 3. Run the Flask App
python nova_flask_app.py

# Open browser to: http://localhost:5000

# ============================================
# MODEL SELECTION IN WEB UI
# ============================================

# The web UI has a model selector dropdown:
# - Auto (Smart Selection) - Default, uses best available
# - LLAMA (Fast) - Good for quick responses
# - GPT-OSS (Deep) - Better for complex analysis

# Both models will use your LM Studio endpoint!

# ============================================
# TESTING WITHOUT LM STUDIO
# ============================================

# The app works even WITHOUT LM Studio running!
# - Retrieval still works (FAISS vector search)
# - You'll get raw context chunks
# - No AI-generated responses (only extracted snippets)

# ============================================
# TROUBLESHOOTING
# ============================================

## LM Studio not connecting?
# 1. Check LM Studio server is running
# 2. Verify URL is http://127.0.0.1:1234
# 3. Test with: curl http://127.0.0.1:1234/v1/models

## Slow responses?
# - Use smaller model (8B instead of 20B)
# - Reduce context window in LM Studio
# - Enable "GPU acceleration" in LM Studio settings

## Out of memory?
# - Close other applications
# - Use quantized models (Q4 or Q5)
# - Reduce max_tokens in LM Studio

# ============================================
# MODEL RECOMMENDATIONS
# ============================================

# For Vehicle Maintenance Q&A:
# 
# BEST: fireball-meta-llama-3.2-8b-instruct-agent-003-128k-code-dpo
#   - Fast
#   - Good at following instructions
#   - 128k context window
#   - Works well with citations
#
# ALTERNATIVE: qwen/qwen2.5-coder-14b (TIER 2: Deep Reasoning)
#   - Better for complex "why" / "explain" questions
#   - ~5-10s inference (vs ~2-5s for Llama)
#   - Auto-selected when query matches deep keywords
#   - Falls back to Llama if timeout (>1200s)

# ============================================
# PERFORMANCE TIPS
# ============================================

# 1. Enable Retrieval Cache (2000x speedup for repeated queries):
$env:NOVA_ENABLE_RETRIEVAL_CACHE="1"

# 2. Use GPU acceleration in LM Studio:
#    Settings > GPU Offload > Max (or adjust based on VRAM)

# 3. Adjust context window:
#    In LM Studio: Context Length = 4096 (faster) or 8192 (better quality)

# 4. Use quantized models:
#    Q4_K_M or Q5_K_M versions are 3-4x faster with minimal quality loss

# ============================================
# ADVANCED: MODEL OVERRIDE
# ============================================

# If you want to force a specific model name:
# (Only needed if LM Studio returns unexpected model name)

# In backend.py, find the call_llm() function and check:
# - It auto-detects models from LM Studio
# - Default fallback is "llama-3.2-8b-instruct"

# No changes needed for your models - they'll work automatically!
