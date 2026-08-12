FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc wget && \
    rm -rf /var/lib/apt/lists/*

# Build context = repo root so the image can vendor cross-service source.
COPY apps/importer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# All importer scripts + the static region_map.json live under src/.
COPY apps/importer/src/ ./
# Importers resolve API modules from /app/apps_api_src. Compose bind-mounts the
# live tree at the same path; vendoring it keeps the standalone image usable.
COPY apps/api/src/ ./apps_api_src/
COPY shared_contracts/ ./shared_contracts/
COPY sql/002_indexes.sql ./sql/002_indexes.sql

ENTRYPOINT ["python3"]
CMD ["import_spansh.py", "--status"]
