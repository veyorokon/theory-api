FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY app/ /work/app/

RUN pip install --no-cache-dir \
    "fastapi>=0.114" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.8" \
    "jsonschema>=4.22" \
    "litellm>=1.43.0"


EXPOSE 8000
# NOTE: We do NOT run uvicorn when used with Modal @asgi_app(); but for local docker run, this CMD is handy.
CMD ["uvicorn", "app.ws:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -sf http://localhost:8000/healthz || exit 1
