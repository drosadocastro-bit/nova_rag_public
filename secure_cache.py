"""
Secure pickle serialization with HMAC verification.
Prevents code execution from tampered cache files.
"""

import pickle
import hmac
import hashlib
import os
from pathlib import Path
import warnings


# Get secret key from environment - REQUIRED for security
SECRET_KEY = os.environ.get('NOVA_CACHE_SECRET')
if not SECRET_KEY:
    # Generate a random secret key for this session
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    warnings.warn(
        "[SECURITY] No NOVA_CACHE_SECRET set! Generated temporary key for this session. "
        "Cache files won't be verifiable across restarts. "
        "Set NOVA_CACHE_SECRET environment variable for persistent cache verification.",
        stacklevel=2
    )


def _compute_hmac(data: bytes) -> bytes:
    """Compute HMAC-SHA256 of data."""
    return hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).digest()


def secure_pickle_dump(obj, filepath: Path):
    """Dump object to pickle with HMAC signature for integrity verification."""
    # Serialize object
    data = pickle.dumps(obj)
    # Compute HMAC
    signature = _compute_hmac(data)
    # Write signature length (4 bytes) + signature + data
    with open(filepath, 'wb') as f:
        f.write(len(signature).to_bytes(4, 'big'))
        f.write(signature)
        f.write(data)


def secure_pickle_load(filepath: Path):
    """Load pickle with HMAC verification to prevent code execution from tampered files."""
    with open(filepath, 'rb') as f:
        # Read signature length
        sig_len_bytes = f.read(4)
        if len(sig_len_bytes) < 4:
            raise ValueError(f"Invalid cache file format: {filepath}")
        sig_len = int.from_bytes(sig_len_bytes, 'big')
        
        # Read signature
        stored_signature = f.read(sig_len)
        if len(stored_signature) < sig_len:
            raise ValueError(f"Invalid cache file format: {filepath}")
        
        # Read data
        data = f.read()
    
    # Verify HMAC
    expected_signature = _compute_hmac(data)
    if not hmac.compare_digest(stored_signature, expected_signature):
        raise ValueError(
            f"HMAC verification failed for {filepath}. "
            "File may be tampered or SECRET_KEY changed. "
            "Delete cache file to regenerate."
        )
    
    # Deserialize
    return pickle.loads(data)
