FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy every API-side Python module — previously only main.py was copied,
# which caused `import local_search` to fail silently and forced the API
# into the inline fallback path (missing galaxy_region_id, star_types,
# secondary_economy, display_score, etc.).
COPY main.py local_search.py exploration_value.py inara_api.py ./

EXPOSE 8000
# workers=1 — backend keeps per-process state (SSE clients, active jobs,
# rate-limit buckets, metrics). Scale horizontally via more containers
# behind nginx if needed, not via uvicorn workers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
