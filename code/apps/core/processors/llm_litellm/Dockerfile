FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Install only what this processor needs
COPY apps/core/processors/llm_litellm/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy shared providers library (Django-free)
COPY libs/runtime_common /app/libs/runtime_common

# Copy foundation and processor code
COPY apps/core/processors/llm_litellm/foundation /app/foundation
COPY apps/core/processors/llm_litellm/main.py /app/main.py

# Contract: read /work/inputs.json; write outputs under /work/out/**
# No ENTRYPOINT; caller provides command to run main
