# Multi-stage build for efficient data collector deployment
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r collector && useradd -r -g collector collector

# Copy Python packages from builder
COPY --from=builder /root/.local /home/collector/.local

# Set working directory
WORKDIR /app

# Create directories for mounted volumes
RUN mkdir -p /app/src /app/logs && \
    chown -R collector:collector /app

# Copy only example env file (config.yaml will be mounted at runtime)
COPY .env.example ./.env

# Switch to non-root user
USER collector

# Add local Python packages to PATH
ENV PATH=/home/collector/.local/bin:$PATH
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import asyncio; import sys; sys.path.insert(0, '/app/src'); \
    from applications.data_collection.collector import DataCollector; \
    collector = DataCollector(); \
    status = collector.get_status(); \
    exit(0 if status else 1)" || exit 1

# Expose port (if needed for monitoring)
EXPOSE 8080

# Default command
CMD ["python", "src/applications/data_collection/run.py"]