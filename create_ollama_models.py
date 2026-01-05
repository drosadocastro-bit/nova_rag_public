import requests
import json
import glob

# Find the actual GGUF files in the new locations
llama_path = r"C:\Users\draku\.ollama\models\Fireball-Meta-Llama-3.2-8B-Instruct-agent-003-128k-code-DPO-GGUF"
qwen_path = r"C:\Users\draku\.ollama\models\Qwen2.5-Coder-14B-Instruct-GGUF"
phi_path = r"C:\Users\draku\.ollama\models\EasierAI\Phi-4-14B"

# Find GGUF files
llama_files = glob.glob(llama_path + r"\*.gguf")
qwen_files = glob.glob(qwen_path + r"\*.gguf")
phi_files = glob.glob(phi_path + r"\*.gguf")

print(f"Found llama files: {llama_files}")
print(f"Found qwen files: {qwen_files}")
print(f"Found phi files: {phi_files}")

if llama_files:
    llama_file = llama_files[0]
    modelfile_llama = f"FROM {llama_file}\nPARAMETER temperature 0.15\nPARAMETER top_p 0.9\nPARAMETER top_k 40\nPARAMETER repeat_penalty 1.1"
    print(f"\nCreating llama8b from {llama_file}...")
    try:
        resp = requests.post('http://localhost:11434/api/create', json={'name': 'llama8b', 'modelfile': modelfile_llama}, timeout=120)
        print(f"llama8b: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Error creating llama8b: {e}")

if qwen_files:
    qwen_file = qwen_files[0]
    modelfile_qwen = f"FROM {qwen_file}\nPARAMETER temperature 0.15\nPARAMETER top_p 0.9\nPARAMETER top_k 40\nPARAMETER repeat_penalty 1.1"
    print(f"\nCreating qwen14b from {qwen_file}...")
    try:
        resp = requests.post('http://localhost:11434/api/create', json={'name': 'qwen14b', 'modelfile': modelfile_qwen}, timeout=120)
        print(f"qwen14b: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Error creating qwen14b: {e}")

if phi_files:
    phi_file = phi_files[0]
    modelfile_phi = f"FROM {phi_file}\nPARAMETER temperature 0.15\nPARAMETER top_p 0.9\nPARAMETER top_k 40\nPARAMETER repeat_penalty 1.1"
    print(f"\nCreating phi4 from {phi_file}...")
    try:
        resp = requests.post('http://localhost:11434/api/create', json={'name': 'phi4', 'modelfile': modelfile_phi}, timeout=120)
        print(f"phi4: {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"Error creating phi4: {e}")

print("\nDone!")
