"""
Gunicorn configuration for NIC (Nova Intelligent Copilot) production deployment.
Optimized for Linux/WSL2 environments with LLM inference workloads.

Usage:
  gunicorn -c gunicorn_config.py nova_flask_app:app
"""

import multiprocessing
import os

# Server socket
bind = os.environ.get("NIC_BIND", "0.0.0.0:5000")
backlog = 2048

# Worker processes
workers = int(os.environ.get("NIC_WORKERS", multiprocessing.cpu_count()))
worker_class = "sync"  # Use sync for LLM (async not suitable for long inference)
worker_connections = 1000
timeout = 300  # 5 min timeout for LLM requests
keepalive = 2

# Logging
accesslog = os.environ.get("NIC_ACCESS_LOG", "logs/access.log")
errorlog = os.environ.get("NIC_ERROR_LOG", "logs/error.log")
loglevel = os.environ.get("NIC_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "nova_nic"

# Server mechanics
daemon = False
pidfile = "/tmp/nova_nic.pid"
umask = 0o022

# SSL (if needed)
# keyfile = "/path/to/key.pem"
# certfile = "/path/to/cert.pem"
# ssl_version = "TLSv1_2"

# Application
preload_app = False  # Don't preload (LLM loading per-worker is safer)
max_requests = 1000  # Restart workers periodically to prevent memory creep
max_requests_jitter = 100

# Hooks for monitoring
def post_worker_init(worker):
    """Called after worker process initialization."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Worker {worker.pid} initialized")

def worker_abort(worker):
    """Called when a worker is aborted (timeout, etc)."""
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Worker {worker.pid} aborted (timeout or crash)")

# Environment
raw_env = [
    f"NOVA_USE_NATIVE_LLM={os.environ.get('NOVA_USE_NATIVE_LLM', '1')}",
    f"NOVA_EVAL_FAST={os.environ.get('NOVA_EVAL_FAST', '0')}",
    f"NOVA_FORCE_OFFLINE={os.environ.get('NOVA_FORCE_OFFLINE', '0')}",
    f"NOVA_DISABLE_VISION={os.environ.get('NOVA_DISABLE_VISION', '0')}",
]
