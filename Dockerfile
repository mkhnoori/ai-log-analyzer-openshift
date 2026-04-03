# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed for some Python packages (e.g. tiktoken)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY config.py .
COPY main.py .
COPY models/ ./models/
COPY services/ ./services/
COPY dashboard/ ./dashboard/
COPY .env .

# Create data directories (ChromaDB persists here via PersistentVolumeClaim)
RUN mkdir -p data/chroma data/knowledge data/sample_logs

# OpenShift runs containers as a random non-root UID — make dirs world-writable
RUN chmod -R g+rwX /app

# Non-root user (OpenShift may override this with a random UID anyway)
RUN useradd -u 1001 -r -g 0 -s /sbin/nologin appuser
USER 1001

EXPOSE 8000

# Healthcheck — OpenShift uses this for readiness probing
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
