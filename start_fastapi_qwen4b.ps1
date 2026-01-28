# Start FastAPI with Qwen 4B model
# This forces NIC to use the 4B model for potato hardware testing

Write-Host "Starting FastAPI with Qwen 3:4B model..." -ForegroundColor Green

# Activate venv
. .venv\Scripts\Activate.ps1

# Set model to Qwen 4B
$env:NOVA_LLM_OSS = "qwen3:4b"
$env:NOVA_LLM_LLAMA = "qwen3:4b"

# CRITICAL: Limit max tokens to prevent verbose reasoning
$env:NOVA_MAX_TOKENS_OSS = "128"     # Max 128 tokens for Qwen 4B
$env:NOVA_MAX_TOKENS_LLAMA = "128"   # Same for fallback

# DISABLE slow native engine - use Ollama API (GPU accelerated)
$env:NOVA_USE_NATIVE_LLM = "0"

Write-Host "Model configuration:" -ForegroundColor Cyan
Write-Host "  NOVA_LLM_OSS: $env:NOVA_LLM_OSS"
Write-Host "  NOVA_LLM_LLAMA: $env:NOVA_LLM_LLAMA"
Write-Host "  MAX_TOKENS_OSS: $env:NOVA_MAX_TOKENS_OSS (prevents verbose reasoning)"
Write-Host "  MAX_TOKENS_LLAMA: $env:NOVA_MAX_TOKENS_LLAMA"
Write-Host "  USE_NATIVE_LLM: $env:NOVA_USE_NATIVE_LLM (using Ollama API - GPU accelerated)"
Write-Host ""

# Start server
Write-Host "Starting FastAPI on http://127.0.0.1:5678" -ForegroundColor Green
Write-Host "Keep this terminal open while benchmarking!" -ForegroundColor Yellow
python -m uvicorn nova_fastapi_app:app --host 127.0.0.1 --port 5678
