FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY app/ /work/app/

RUN pip install --no-cache-dir \
    "fastapi>=0.114" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.8" \
    "jsonschema>=4.22" \
    "requests>=2.32"

# Make arbitrary UID runs safe (bind-mounts deletable by host user)
RUN mkdir -p /artifacts /work /home/app && chmod -R 0777 /artifacts /work /home/app
ENV HOME=/home/app XDG_CACHE_HOME=/home/app/.cache HF_HOME=/home/app/.cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "app.ws:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD curl -sf http://localhost:8000/healthz || exit 1
