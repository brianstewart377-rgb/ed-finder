FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Build context = repo root so the image can vendor shared_contracts.
COPY apps/eddn/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/eddn/src/ ./
COPY shared_contracts/ ./shared_contracts/

CMD ["python3", "eddn_listener.py"]
