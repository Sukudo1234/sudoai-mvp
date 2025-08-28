# Use a PyTorch runtime with CUDA; will still work on CPU if no GPU is present
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg sox && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Demucs (includes torchaudio dependency already present in base image)
RUN pip install --no-cache-dir demucs==4.0.1

COPY . /app

CMD ["celery", "-A", "tasks.celery", "worker", "--loglevel=INFO", "--concurrency=1"]
