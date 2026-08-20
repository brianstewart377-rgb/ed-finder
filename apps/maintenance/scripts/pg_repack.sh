#!/usr/bin/env bash
# Weekly pg_repack maintenance: compact tables and reclaim dead space
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_FILE="/data/logs/pg_repack.log"

{
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting pg_repack maintenance..."

  if ! docker compose -f "$REPO_DIR/docker-compose.yml" ps postgres > /dev/null 2>&1; then
    echo "[ERROR] postgres container not running"
    exit 1
  fi

  # Run pg_repack on all tables in public schema
  docker compose -f "$REPO_DIR/docker-compose.yml" exec -T postgres psql -U edfinder -d edfinder << 'EOF'
SET statement_timeout = 0;
SELECT pg_repack(t.oid)
FROM pg_class t
INNER JOIN pg_namespace n ON (n.oid = t.relnamespace)
WHERE n.nspname = 'public'
  AND t.relkind = 'r'
  AND t.reltuples > 0
ORDER BY t.relpages DESC;
EOF

  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] pg_repack completed successfully"

} >> "$LOG_FILE" 2>&1

exit 0
