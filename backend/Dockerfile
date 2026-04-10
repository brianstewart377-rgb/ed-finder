# ── ED:Finder Backend ──────────────────────────────────────────────────────
# Multi-arch: works on linux/amd64 (Hetzner) and linux/arm64 (Pi 5)
# v3.17 — Added local galaxy DB integration (local_search.py, EDDN listener)
FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY main.py .

# Copy local DB search module (optional — API works without it via Spansh proxy)
# localdb/ is copied from the project root (build context is set to repo root
# in docker-compose.yml) so it appears at /app/localdb/ inside the container.
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
