# Ollama Model Definitions

This folder contains Ollama Modelfiles for registering local GGUF models with Ollama.

## Purpose

When running NIC in an offline/air-gapped environment, you may have GGUF model files downloaded from sources like:
- **LM Studio** — Popular local model manager
- **Hugging Face** — Direct GGUF downloads
- **TheBloke** — Quantized model collections

These Modelfiles let you register those local GGUF files with Ollama so NIC can use them.

## How It Works

A Modelfile tells Ollama:
1. **Where the model weights are** (`FROM /path/to/model.gguf`)
2. **System prompt** (optional safety/behavior instructions)
3. **Parameters** (temperature, context window, etc.)

## Available Modelfiles

| File | Model | Size | Use Case |
|------|-------|------|----------|
| `Modelfile` | Default template | — | Base template |
| `Modelfile.llama3.2-8b` | Llama 3.2 8B | ~5GB | General Q&A, fast |
| `Modelfile.phi-4-14b` | Phi-4 14B | ~8GB | Reasoning, balanced |
| `Modelfile.qwen2.5-coder-14b` | Qwen 2.5 Coder | ~8GB | Technical/code tasks |
| `Modelfile.granite-*` | IBM Granite | Varies | Enterprise use |
| `Modelfile.qwen3-*` | Qwen 3 | Varies | Latest generation |

## Usage

### 1. Edit the Modelfile

Update the `FROM` path to point to your local GGUF file:

```dockerfile
FROM C:/Users/YourName/.lmstudio/models/your-model.gguf
```

### 2. Register with Ollama

```bash
# Register the model
ollama create llama3.2-8b -f ollama/Modelfile.llama3.2-8b

# Verify it's available
ollama list

# Test it
ollama run llama3.2-8b "Hello, how are you?"
```

### 3. Configure NIC to Use It

Set the environment variable or update the config:
```bash
export NOVA_LLM_LLAMA=llama3.2-8b
```

## Creating Your Own Modelfile

```dockerfile
# Modelfile.your-model
FROM /path/to/your-model.gguf

# System prompt for safety-critical use
SYSTEM """You are a technical assistant. Only provide information from the given context. If unsure, say so."""

# Parameters
PARAMETER temperature 0.1
PARAMETER num_ctx 8192
```

## Notes

- Paths must be absolute and use forward slashes or escaped backslashes
- Model names in Ollama should match what NIC expects (see `backend.py`)
- For air-gapped deployments, pre-register all models before disconnecting

## Related

- [Offline Model Setup](../docs/deployment/OFFLINE_MODEL_SETUP.md)
- [Air-Gapped Deployment](../docs/deployment/AIR_GAPPED_DEPLOYMENT.md)
