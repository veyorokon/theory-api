FROM python:3.11-slim

    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        TZ=UTC \
        LC_ALL=C.UTF-8

    RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential gcc g++ \
        && rm -rf /var/lib/apt/lists/*

    WORKDIR /tool

    # Copy runtime_common for imports
    COPY code/libs/runtime_common /tool/libs/runtime_common

    # Copy generic protocol layer
    COPY code/libs/runtime_common/protocol /tool/protocol

    # Copy tool-specific overrides (overwrites generic files)
    COPY tools/llm/litellm/1/protocol/*.py /tool/protocol/

    RUN pip install --no-cache-dir \
        "fastapi>=0.114" \
        "uvicorn[standard]>=0.30" \
        "pydantic>=2.8" \
        "jsonschema>=4.22" \
        "requests>=2.32" \
        "httpx>=0.27" \
        "litellm>=1.43.0"

    # Make arbitrary UID runs safe (writable HOME for pip/model caching)
    RUN mkdir -p /home/app && chmod -R 0777 /home/app
    ENV HOME=/home/app XDG_CACHE_HOME=/home/app/.cache HF_HOME=/home/app/.cache/huggingface

    # Writable /artifacts for local output mode
    RUN mkdir -p /artifacts && chmod -R 0777 /artifacts

    EXPOSE 8000
    CMD ["uvicorn", "protocol.ws:app", "--host", "0.0.0.0", "--port", "8000"]

    HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
      CMD curl -sf http://localhost:8000/healthz || exit 1
