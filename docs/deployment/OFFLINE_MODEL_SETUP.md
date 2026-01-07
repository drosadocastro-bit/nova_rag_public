# Ollama Configuration for NIC Public

# ============================================
# QUICK START - OLLAMA SETUP
# ============================================

## 1. Install Ollama
# - Windows/Mac: https://ollama.com/download
# - Linux: curl -fsSL https://ollama.com/install.sh | sh

## 2. Pull models
# ollama pull llama3.2:8b
# ollama pull qwen2.5-coder:14b
# (Optional for eval): ollama pull phi4:14b

## 3. Start Ollama service
# - Service auto-starts after install; verify with:
#   ollama list
# - Ensure API is up: http://127.0.0.1:11434

## 4. Run the Flask App
python nova_flask_app.py

# Open browser to: http://localhost:5000

# ============================================
# MODEL SELECTION IN WEB UI
# ============================================

# Model selector dropdown:
# - Auto (Smart Selection) - Default, uses best available
# - LLAMA (Fast) - llama3.2:8b
# - GPT-OSS (Deep) - qwen2.5-coder:14b

# All use your local Ollama endpoint.

# ============================================
# TESTING WITHOUT OLLAMA
# ============================================

# The app runs even if Ollama is offline:
# - Retrieval still works (FAISS vector search)
# - You get raw context chunks only (no generation)

# ============================================
# TROUBLESHOOTING
# ============================================

## Ollama not connecting?
# 1. Check service: ollama list
# 2. Verify URL: http://127.0.0.1:11434
# 3. Test: curl http://127.0.0.1:11434/api/tags

## Slow responses?
# - Use the 8B model (llama3.2:8b)
# - Prefer quantized variants (q4_K_M) when available
# - Reduce max_tokens in backend env vars

## Out of memory?
# - Close other GPU-heavy apps
# - Use quantized models
# - Reduce context length via model choice (e.g., 8B)

# ============================================
# MODEL RECOMMENDATIONS
# ============================================

# For Vehicle Maintenance Q&A:
# 
# FAST: llama3.2:8b
#   - Quick responses
#   - Strong instruction following
#   - Good with citations
#
# DEEP: qwen2.5-coder:14b
#   - Better for complex "why" / "explain" questions
#   - Auto-selected for deep reasoning intents

# ============================================
# PERFORMANCE TIPS
# ============================================

# 1. Enable Retrieval Cache (2000x speedup for repeated queries):
$env:NOVA_ENABLE_RETRIEVAL_CACHE="1"

# 2. Use quantized models for speed:
#    Prefer q4_K_M variants when available

# 3. Keep context sizes reasonable:
#    Default outputs are capped via NOVA_MAX_TOKENS_* env vars

# ============================================
# ADVANCED: MODEL OVERRIDE
# ============================================

# You can force explicit model names via env:
#   NOVA_LLM_LLAMA=llama3.2:8b
#   NOVA_LLM_OSS=qwen2.5-coder:14b

# Backend auto-resolves to the first available model if overrides are missing.
