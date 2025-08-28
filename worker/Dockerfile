FROM nvidia/cuda:11.8-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV CUDA_VISIBLE_DEVICES=all

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    ffmpeg \
    git \
    wget \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY worker/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r /app/requirements.txt

# Install Demucs for audio separation (GPU task)
RUN pip3 install --no-cache-dir demucs

# Copy shared modules
COPY shared /app/shared

# Copy worker code
COPY worker /app/worker

# Copy scripts
COPY scripts /app/scripts

# Create non-root user for security
RUN useradd -m -u 1000 worker && \
    chown -R worker:worker /app && \
    chmod +x /app/scripts/*.py

USER worker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default entry point
ENTRYPOINT ["python", "/app/scripts/run-worker.py"]

# Default command 
CMD ["start"]