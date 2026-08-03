# Travel Buddy MVP - Production Dockerfile
# Multi-stage build for minimal image size
# Deploy to: Railway, Fly.io, Google Cloud Run, AWS ECS

# Stage 1: Dependencies
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements-prod.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements-prod.txt

# Stage 2: Production image
FROM python:3.11-slim

# Security: non-root user
RUN useradd -m -r appuser && mkdir /app && chown appuser:appuser /app
WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /deps /usr/local/lib/python3.11/site-packages/

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/api/v1/health'); assert r.status_code==200"

# Expose port
EXPOSE 8000

# Run with uvicorn (production settings)
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
