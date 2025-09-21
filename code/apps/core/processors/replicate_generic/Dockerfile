FROM python:3.11-slim

# Minimal OS deps
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# 1) Install Python deps for this processor only
COPY apps/core/processors/replicate_generic/requirements.txt /work/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /work/requirements.txt

# 2) Copy shared runtime libs (no Django)
COPY libs/runtime_common /work/libs/runtime_common

# 3) Copy JUST the processor package
COPY apps/core/processors/replicate_generic /work/apps/core/processors/replicate_generic

# 4) For module import resolution
ENV PYTHONPATH=/work

# 5) Standard entrypoint: module form (fixes relative import issues)
ENTRYPOINT ["python", "-m", "apps.core.processors.replicate_generic.main"]
