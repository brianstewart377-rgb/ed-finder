# ── ED:Finder Backend ──────────────────────────────────────────────────────
# Multi-arch: works on linux/amd64 (Hetzner) and linux/arm64 (Pi 5)
# v3.17 — Added local galaxy DB integration (local_search.py, EDDN listener)
# Build context: repo root (so COPY localdb/ works)
FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer)
# Path is relative to build context (repo root)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/main.py .

# Copy local DB modules into the image
COPY localdb/ ./localdb/

# Create data directory (will be overridden by bind mount in compose)
RUN mkdir -p /data

# Expose API port
EXPOSE 8000

# Liveness probe — lightweight /api/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# workers=1 — multiple workers each spawn their own background tasks
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
