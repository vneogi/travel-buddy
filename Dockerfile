# Travel Buddy - Production Dockerfile
# Target: Google Cloud Run (also works on Railway, Fly.io, AWS ECS)
# Cloud Run injects PORT via env; secrets are set in the console.

# Stage 1: Dependencies
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim

# Security: non-root user
RUN useradd -m -r appuser && mkdir /app && chown appuser:appuser /app
WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages/

# Copy application code (see .dockerignore for exclusions)
COPY --chown=appuser:appuser . .

USER appuser

# Cloud Run injects PORT (default 8080). Do not bake secrets here.
ENV PORT=8080

EXPOSE ${PORT}

# Production uvicorn: read PORT from env, single worker (Cloud Run scales instances).
CMD python -m uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --access-log
