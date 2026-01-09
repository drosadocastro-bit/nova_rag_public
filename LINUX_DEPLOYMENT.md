# Linux/WSL2 Deployment Guide for NIC

Production deployment for Nova Intelligent Copilot with Gunicorn + systemd.

## Quick Start (WSL2/Linux)

### 1. Prerequisites

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python and system dependencies
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential
sudo apt install -y git curl wget openssh-server
sudo apt install -y libssl-dev libffi-dev libopenblas-dev

# For GPU support (optional, if using CUDA/ROCm)
# sudo apt install -y nvidia-cuda-toolkit

# Install Ollama (LLM service)
curl https://ollama.ai/install.sh | sh
ollama serve &  # Start in background
```

### 2. Clone & Setup Repository

```bash
cd /opt
sudo git clone https://github.com/drosadocastro-bit/nova_rag_public.git
cd nova_rag_public
sudo chown -R $USER:$USER .
```

### 3. Create Python Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install gunicorn
```

### 4. Create System User (optional, for production)

```bash
sudo useradd -r -s /bin/bash nic
sudo chown -R nic:nic /opt/nova_rag_public
sudo mkdir -p /var/log/nova_nic /etc/nova_nic
sudo chown nic:nic /var/log/nova_nic /etc/nova_nic
```

### 5. Install systemd Service

```bash
# Copy service file
sudo cp nova_nic.service /etc/systemd/system/

# Create environment file
sudo tee /etc/nova_nic/nova_nic.env > /dev/null <<EOF
NOVA_USE_NATIVE_LLM=1
NOVA_EVAL_FAST=0
NOVA_FORCE_OFFLINE=0
NOVA_CACHE_SECRET=your-secret-key-here-min-32-chars
EOF

# Set permissions
sudo chmod 600 /etc/nova_nic/nova_nic.env

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable nova_nic
sudo systemctl start nova_nic

# Check status
sudo systemctl status nova_nic
```

### 6. Configure Reverse Proxy (Nginx)

```bash
# Install Nginx
sudo apt install -y nginx

# Create Nginx config
sudo tee /etc/nginx/sites-available/nova_nic > /dev/null <<'EOF'
upstream nova_nic {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name _;  # Replace with your domain
    client_max_body_size 50M;

    location / {
        proxy_pass http://nova_nic;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /static/ {
        alias /opt/nova_rag_public/static/;
        expires 30d;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/nova_nic /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Add SSL/HTTPS (with Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal check
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Monitoring & Logs

### View Real-Time Logs
```bash
# Service logs
sudo journalctl -u nova_nic -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
```

### Check Service Health
```bash
# Status
sudo systemctl status nova_nic

# Worker count
ps aux | grep gunicorn

# Port listening
sudo netstat -tlnp | grep 5000
```

### Performance Monitoring
```bash
# CPU & Memory
htop -p $(systemctl show --value -p MainPID nova_nic)

# Disk usage (vector database)
du -sh /opt/nova_rag_public/vector_db/
```

## Configuration Tuning

### Workers (for CPU cores)
```bash
# Edit gunicorn_config.py or set environment variable
export NIC_WORKERS=8  # For 8-core system
```

### LLM Context Window
```bash
# Edit llm_engine.py to match available VRAM
# Default: 8192 tokens (safe)
# Large: 16384 tokens (16GB+ RAM)
```

### Rate Limiting
```bash
# In nova_flask_app.py, adjust RATE_LIMIT_PER_MINUTE
RATE_LIMIT_PER_MINUTE = 20  # Requests per minute per IP
```

## Troubleshooting

### Service Won't Start
```bash
sudo journalctl -u nova_nic -n 50  # Last 50 lines
sudo systemctl status nova_nic
```

### High Memory Usage
```bash
# Reduce LLM context window in llm_engine.py
# Reduce Gunicorn workers
export NIC_WORKERS=2
sudo systemctl restart nova_nic
```

### LLM Timeouts (slow responses)
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check network connectivity
ping 127.0.0.1:11434

# Increase Gunicorn timeout in gunicorn_config.py
timeout = 600  # 10 minutes for heavy inference
```

### Vector DB Issues
```bash
# Rebuild index if corrupted
python3 convert_index.py

# Check permissions
sudo chown nic:nic /opt/nova_rag_public/vector_db/*
```

## Production Checklist

- [ ] SSL/HTTPS enabled
- [ ] Firewall configured (only ports 80, 443 open)
- [ ] Rate limiting enabled
- [ ] Log rotation setup (`logrotate`)
- [ ] Backups of vector_db scheduled
- [ ] Ollama service configured to restart on reboot
- [ ] Resource limits set (memory, CPU)
- [ ] Monitoring alerts configured
- [ ] Security updates scheduled
- [ ] DNS records configured

## Commands Reference

```bash
# Start/stop/restart service
sudo systemctl start nova_nic
sudo systemctl stop nova_nic
sudo systemctl restart nova_nic

# View live logs
sudo journalctl -u nova_nic -f

# Test API
curl -X POST http://localhost:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the tire pressure?"}'

# Graceful reload (0 downtime)
sudo systemctl reload nova_nic

# Check version
grep version /opt/nova_rag_public/pyproject.toml
```

## Docker Alternative

If you prefer containerized deployment:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt gunicorn
CMD ["gunicorn", "-c", "gunicorn_config.py", "nova_flask_app:app"]
```

Build and run:
```bash
docker build -t nova_nic:latest .
docker run -d -p 5000:5000 \
  -e NOVA_USE_NATIVE_LLM=1 \
  -v $(pwd)/vector_db:/app/vector_db \
  nova_nic:latest
```

---

**Support & Issues**: Check [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) or GitHub issues.
