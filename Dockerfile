# Multi-stage Dockerfile optimized for ARM64 (OCI Free Tier)
# Stage 1: Frontend build
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system deps for ARM64
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend modules
COPY main.py .
COPY config/ ./config/
COPY core/ ./core/
COPY api/ ./api/
COPY brokers/ ./brokers/
COPY data/ ./data/
COPY strategies/ ./strategies/
COPY risk/ ./risk/
COPY evolution/ ./evolution/
COPY agents/ ./agents/

# Copy built frontend static files
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["python", "main.py"]
