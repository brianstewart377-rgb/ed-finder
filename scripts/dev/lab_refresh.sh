#!/usr/bin/env bash
# Refresh the always-on Review Lab to a git ref: checkout, build, up, schema, seed.
#
# The base lab needs ONLY Docker on the host: the legacy schema bootstrap and the
# synthetic seed run inside the containers, mirroring the Review Lab orchestrator
# (scripts/dev/review_lab/lifecycle.py :: bootstrap_schema + seed_review_database),
# which stays the source of truth for those two steps.
#
# The optional V3 Finder generation (only present on refs that include PR #777)
# additionally needs the apps/api test venv, because seed_cypress_v3_generation.py
# imports scripts/* and uses psycopg, neither of which the production api image
# carries. Create it once with:
#   uv sync --project apps/api --frozen --group test --no-install-project
#
# Usage: scripts/dev/lab_refresh.sh [git-ref]   (default: main)
set -euo pipefail

REF="${1:-main}"
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.review.yml -f docker-compose.lab.yml)
LAB_DB_HOST="postgresql://review_user:review_password@localhost:55435/edfinder_local_review"

echo "==> fetch + checkout ${REF}"
git fetch --prune origin
git checkout "${REF}"
git pull --ff-only origin "${REF}" 2>/dev/null || true  # no-op for detached PR refs

BUILD_SHA="$(git rev-parse HEAD)"
export BUILD_SHA
echo "BUILD_SHA=${BUILD_SHA}" > .lab.env
echo "==> BUILD_SHA=${BUILD_SHA}"

echo "==> build + up"
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d

echo "==> wait for Postgres"
until "${COMPOSE[@]}" exec -T review-postgres pg_isready -U review_user -d edfinder_local_review >/dev/null 2>&1; do
  sleep 2
done

# Legacy schema bootstrap — every sql/*.sql except seed_preview.sql, in order.
# Mirrors scripts/dev/review_lab/lifecycle.py::bootstrap_schema (keep in sync).
echo "==> bootstrap schema"
"${COMPOSE[@]}" exec -T review-postgres sh -lc \
  'set -eu; for f in $(ls -1 /workspace/sql/*.sql | sort); do case "$f" in */seed_preview.sql) continue ;; esac; psql -h 127.0.0.1 -U review_user -d edfinder_local_review -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null; done'

# Synthetic review data. Mirrors lifecycle.py::seed_review_database (mounted path).
echo "==> seed synthetic review data"
"${COMPOSE[@]}" run --rm review-api python /workspace/scripts/dev/review_environment_seed.py

# Optional V3 Finder generation (refs with PR #777 only); host test venv required.
if [ -f scripts/dev/seed_cypress_v3_generation.py ]; then
  if [ -x apps/api/.venv/bin/python ]; then
    echo "==> publish V3 derived generation (F3 Finder)"
    DATABASE_URL="${LAB_DB_HOST}" apps/api/.venv/bin/python scripts/dev/seed_cypress_v3_generation.py
  else
    echo "!! V3 seed present but apps/api/.venv missing — Finder will 404 until you run:"
    echo "   uv sync --project apps/api --frozen --group test --no-install-project && scripts/dev/lab_refresh.sh ${REF}"
  fi
else
  echo "==> V3 seed absent on ${REF} (pre-#777); Finder uses the legacy path"
fi

echo "==> smoke check"
curl -sf http://localhost:4174/ >/dev/null && echo "  web ok"
curl -sf http://localhost:4174/api/health >/dev/null && echo "  api ok"
echo "==> lab is up on http://localhost:4174 (tunnel from your laptop)"
