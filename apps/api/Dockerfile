FROM python:3.12-slim

WORKDIR /app

# Runtime libs: libpq+gcc for asyncpg/psycopg2 wheel fallbacks; freetype+
# zlib+jpeg+dejavu fonts for Pillow's OG share-card renderer.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev gcc \
    libjpeg62-turbo zlib1g libfreetype6 fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# Build context = apps/api/, so requirements.txt sits at context root.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# All API source modules live under src/. Flatten into /app so the
# existing flat-import style (`from config import settings`) keeps
# working without a package rename.
COPY src/ ./

EXPOSE 8000
# workers=1 — backend keeps per-process state (SSE clients, active jobs,
# rate-limit buckets, metrics). Scale horizontally via more containers
# behind nginx if needed, not via uvicorn workers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
