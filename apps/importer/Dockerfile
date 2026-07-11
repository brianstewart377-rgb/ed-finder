FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc wget && \
    rm -rf /var/lib/apt/lists/*

# Build context = repo root so the image can vendor shared_contracts.
COPY apps/importer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# All importer scripts + the static region_map.json live under src/.
COPY apps/importer/src/ ./
COPY shared_contracts/ ./shared_contracts/

ENTRYPOINT ["python3"]
CMD ["import_spansh.py", "--status"]
