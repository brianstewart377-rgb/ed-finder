# ── ED:Finder Backend ──────────────────────────────────────────────────────
# Multi-arch: works on linux/amd64 (Hetzner) and linux/arm64 (Pi 5)
# v3.15 — workers=1 (prevents duplicate background tasks); added HEALTHCHECK;
#         added .dockerignore (exclude __pycache__, *.pyc, test files)
FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY main.py .

# Create data directory (will be overridden by bind mount in compose)
RUN mkdir -p /data

# Expose API port
EXPOSE 8000

# Liveness probe — lightweight /api/health endpoint (FIX #28)
# curl is not present in slim; use Python's urllib instead
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# FIX: workers=1 — multiple workers each spawn their own background tasks
# (daily refresh, watchlist checker, cache cleanup) which would duplicate
# work and corrupt the shared SQLite state.  One worker is correct here.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
