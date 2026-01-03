"""
LM Studio Manager
Starts LM Studio as a Python subprocess (no GUI) to avoid resource conflicts.
Compatible with LM Studio CLI mode or can use llama-cpp-python as fallback.
"""

import subprocess
import time
import os
import requests
import sys
from pathlib import Path

LM_STUDIO_PORT = 1234
LM_STUDIO_HOST = "127.0.0.1"
LM_STUDIO_URL = f"http://{LM_STUDIO_HOST}:{LM_STUDIO_PORT}/v1"
LM_STUDIO_CHECK_INTERVAL = 2  # seconds
LM_STUDIO_MAX_RETRIES = 30  # 60 seconds total

# Try to find LM Studio installation
COMMON_LM_STUDIO_PATHS = [
    r"C:\Users\{user}\AppData\Local\LM-Studio\bin\lms.exe",
    r"C:\Program Files\LM-Studio\bin\lms.exe",
    r"C:\Program Files (x86)\LM-Studio\bin\lms.exe",
]

def find_lm_studio_executable():
    """Find LM Studio executable on Windows."""
    username = os.getenv("USERNAME", "")
    
    # Try paths with username substitution
    for path_template in COMMON_LM_STUDIO_PATHS:
        path = path_template.format(user=username)
        if os.path.exists(path):
            return path
    
    # Try to find via PATH
    try:
        result = subprocess.run(["where", "lms"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass
    
    return None

def is_lm_studio_running():
    """Check if LM Studio server is responding."""
    try:
        response = requests.get(f"{LM_STUDIO_URL}/models", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def start_lm_studio_server():
    """Start LM Studio as a background server process."""
    if is_lm_studio_running():
        print(f"[LMStudioManager] LM Studio already running on {LM_STUDIO_URL}")
        return True
    
    lm_studio_path = find_lm_studio_executable()
    
    if not lm_studio_path:
        print("[LMStudioManager] ERROR: LM Studio executable not found.")
        print("[LMStudioManager] Please install LM Studio or add its bin directory to PATH")
        print("[LMStudioManager] LM Studio: https://lmstudio.ai/")
        return False
    
    print(f"[LMStudioManager] Starting LM Studio from: {lm_studio_path}")
    
    try:
        # Start LM Studio in server mode (headless)
        # The 'lms serve' command runs LM Studio without GUI
        process = subprocess.Popen(
            [lm_studio_path, "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        
        print(f"[LMStudioManager] LM Studio process started (PID: {process.pid})")
        
        # Wait for server to be ready
        print(f"[LMStudioManager] Waiting for LM Studio to be ready...", end="", flush=True)
        for attempt in range(LM_STUDIO_MAX_RETRIES):
            if is_lm_studio_running():
                print(" ✓ Ready!")
                return True
            print(".", end="", flush=True)
            time.sleep(LM_STUDIO_CHECK_INTERVAL)
        
        print(" FAILED")
        print(f"[LMStudioManager] ERROR: LM Studio did not respond after {LM_STUDIO_MAX_RETRIES * LM_STUDIO_CHECK_INTERVAL} seconds")
        process.terminate()
        return False
        
    except Exception as e:
        print(f"[LMStudioManager] ERROR: Failed to start LM Studio: {e}")
        return False

def verify_lm_studio_models(required_models=None):
    """Verify that required models are loaded in LM Studio."""
    if not is_lm_studio_running():
        print("[LMStudioManager] LM Studio is not running")
        return False
    
    try:
        response = requests.get(f"{LM_STUDIO_URL}/models", timeout=5)
        if response.status_code != 200:
            return False
        
        models = response.json()
        loaded_models = [m.get("id", "") for m in models.get("data", [])]
        
        if not loaded_models:
            print("[LMStudioManager] WARNING: No models loaded in LM Studio!")
            print("[LMStudioManager] Please load models manually in LM Studio")
            return False
        
        print(f"[LMStudioManager] LM Studio has {len(loaded_models)} model(s) loaded:")
        for model in loaded_models[:5]:  # Show first 5
            print(f"  - {model}")
        if len(loaded_models) > 5:
            print(f"  ... and {len(loaded_models) - 5} more")
        
        if required_models:
            for req_model in required_models:
                if not any(req_model in m for m in loaded_models):
                    print(f"[LMStudioManager] WARNING: Required model '{req_model}' not loaded!")
                    return False
        
        return True
        
    except Exception as e:
        print(f"[LMStudioManager] ERROR: Failed to verify models: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("LM Studio Server Manager")
    print("=" * 70)
    
    if start_lm_studio_server():
        print("\n[LMStudioManager] Verifying models...")
        if verify_lm_studio_models([
            "fireball-meta-llama-3.2-8b",
            "qwen2.5-coder-14b",
            "phi-4"
        ]):
            print("\n[LMStudioManager] ✓ LM Studio is ready for use!")
            sys.exit(0)
        else:
            print("\n[LMStudioManager] ✗ Model verification failed")
            sys.exit(1)
    else:
        print("\n[LMStudioManager] ✗ Failed to start LM Studio")
        sys.exit(1)
