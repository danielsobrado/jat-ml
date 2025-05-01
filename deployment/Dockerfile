FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY rag/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy config file
COPY rag/config-chroma.yaml /app/config.yaml

# Copy the nested rag directory
COPY rag/rag /app/rag

# Create empty __init__.py files to ensure Python recognizes directories as packages
RUN mkdir -p /app/rag && touch /app/rag/__init__.py

# Add health check endpoint
COPY rag/deployment/health_check.py /app/rag/health_check.py

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config.yaml \
    PYTHONPATH=/app

# Command to run the application
CMD ["python", "-m", "rag.main"]