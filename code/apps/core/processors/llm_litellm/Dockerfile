FROM python:3.11-slim

# Minimal OS deps with build tools for Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# 1) Install Python deps for this processor only
COPY apps/core/processors/llm_litellm/requirements.txt /work/requirements.txt
RUN pip install --no-cache-dir -r /work/requirements.txt

# 2) Copy shared runtime libs (no Django)
COPY libs/runtime_common /work/libs/runtime_common

# 3) Copy JUST the processor package
COPY apps/core/processors/llm_litellm /work/apps/core/processors/llm_litellm

# 4) For module import resolution
ENV PYTHONPATH=/work

# 5) Standard entrypoint: module form (fixes relative import issues)
ENTRYPOINT ["python", "-m", "apps.core.processors.llm_litellm.main"]
