# NIC - Offline RAG for Safety-Critical Systems
# Multi-stage build for optimized image size

FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/vector_db /app/data /app/models /app/ragas_results && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Set environment variables for offline mode
ENV NOVA_FORCE_OFFLINE=0
ENV HF_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models
ENV PYTHONUNBUFFERED=1
ENV NOVA_LOG_FORMAT=json
ENV NOVA_ENV=production

# Expose Flask port
EXPOSE 5000

# Health check using Python script for comprehensive validation
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/scripts/docker_healthcheck.py || exit 1

# Run with waitress for production
CMD ["python", "nova_flask_app.py"]
