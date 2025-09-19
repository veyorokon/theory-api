FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Install processor dependencies
COPY code/apps/core/processors/replicate_generic/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy shared runtime libraries (provider-agnostic)
COPY code/libs/runtime_common /app/libs/runtime_common

# Copy integrations (provider-specific)
COPY code/apps/core/integrations /app/apps/core/integrations

# Copy processor main
COPY code/apps/core/processors/replicate_generic/main.py /app/main.py

# Contract: Universal thin processor pattern
# --inputs /work/inputs.json --write-prefix /work/out/ --execution-id <id>
ENTRYPOINT ["python", "main.py"]
