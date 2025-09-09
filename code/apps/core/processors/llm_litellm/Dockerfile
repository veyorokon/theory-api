# LLM LiteLLM processor container
FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy processor code
COPY processor.py .

# Set entrypoint
ENTRYPOINT ["python", "-m", "processor"]