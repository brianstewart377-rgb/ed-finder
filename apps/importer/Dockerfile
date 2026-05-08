FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc wget && \
    rm -rf /var/lib/apt/lists/*

# Build context = apps/importer/.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# All importer scripts + the static region_map.json live under src/.
COPY src/ ./

ENTRYPOINT ["python3"]
CMD ["import_spansh.py", "--status"]
