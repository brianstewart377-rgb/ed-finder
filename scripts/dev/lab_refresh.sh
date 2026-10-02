#!/usr/bin/env bash
# Refresh the always-on Review Lab to a git ref: checkout, build, up, seed.
# Usage: scripts/dev/lab_refresh.sh [git-ref]   (default: main)
set -euo pipefail

REF="${1:-main}"
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.review.yml -f docker-compose.lab.yml)
IN_DB="postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review"

echo "==> fetch + checkout ${REF}"
git fetch --prune origin
git checkout "${REF}"
git pull --ff-only origin "${REF}" 2>/dev/null || true  # no-op for detached PR refs

BUILD_SHA="$(git rev-parse HEAD)"
export BUILD_SHA
echo "BUILD_SHA=${BUILD_SHA}" > .lab.env
echo "==> BUILD_SHA=${BUILD_SHA}"

echo "==> build"
"${COMPOSE[@]}" build

echo "==> up"
"${COMPOSE[@]}" up -d

echo "==> wait for Postgres"
until "${COMPOSE[@]}" exec -T review-postgres pg_isready -U review_user -d edfinder_local_review >/dev/null 2>&1; do
  sleep 2
done

echo "==> seed synthetic review data"
"${COMPOSE[@]}" exec -T -e DATABASE_URL="${IN_DB}" review-api python scripts/dev/review_environment_seed.py

if [ -f scripts/dev/seed_cypress_v3_generation.py ]; then
  echo "==> publish V3 derived generation (F3 Finder)"
  "${COMPOSE[@]}" exec -T -e DATABASE_URL="${IN_DB}" review-api python scripts/dev/seed_cypress_v3_generation.py
else
  echo "==> V3 seed absent on ${REF} (pre-#777); Finder uses the legacy path"
fi

echo "==> smoke check"
curl -sf http://localhost:4174/ >/dev/null && echo "  web ok"
curl -sf http://localhost:4174/api/health >/dev/null && echo "  api ok"
echo "==> lab is up on http://localhost:4174 (tunnel from your laptop)"
