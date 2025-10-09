FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY code/ /app/

# Copy only registry.yaml files from tools directory, preserving structure
RUN mkdir -p /app/tools/
COPY tools/ /tmp/tools/
RUN find /tmp/tools/ -type f -name "registry.yaml" -exec sh -c 'cp --parents "$1" /app/tools/' sh {} \; && rm -rf /tmp/tools/

# Copy entrypoint script
COPY code/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user for security
RUN groupadd -r django && useradd -r -g django django && \
    chown -R django:django /app
USER django

# Expose port
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
