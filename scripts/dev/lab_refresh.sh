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
# Only fast-forward when REF is a real remote branch. A genuine non-ff failure
# (diverged local branch) must ABORT rather than silently build/publish a
# different SHA than the requested ref; detached/tag/PR refs have no
# origin/<ref> branch and are used as checked out.
if git show-ref --verify --quiet "refs/remotes/origin/${REF}"; then
  git merge --ff-only "origin/${REF}"
fi

BUILD_SHA="$(git rev-parse HEAD)"
export BUILD_SHA
echo "BUILD_SHA=${BUILD_SHA}" > .lab.env
echo "==> BUILD_SHA=${BUILD_SHA}"

# Reset volumes every refresh so switching refs cannot leave stale state: the
# named Postgres volume otherwise retains a prior ref's schema (forward-only SQL
# can't undo a removed/renamed column), and the Redis cache otherwise keeps
# serving up-to-24h-TTL responses from the previous ref's code/data. A clean
# volume per ref is the intended "refresh to a ref" semantics for a synthetic lab.
echo "==> reset lab volumes (clean schema + cache for this ref)"
"${COMPOSE[@]}" down -v --remove-orphans

echo "==> build + up"
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d

echo "==> wait for Postgres"
pg_deadline=$((SECONDS + 120))
until "${COMPOSE[@]}" exec -T review-postgres pg_isready -U review_user -d edfinder_local_review >/dev/null 2>&1; do
  if (( SECONDS >= pg_deadline )); then
    echo "!! Postgres not ready after 120s (container may have exited — bad volume / out of disk):" >&2
    "${COMPOSE[@]}" ps >&2 || true
    "${COMPOSE[@]}" logs --tail=50 review-postgres >&2 || true
    exit 1
  fi
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

# Schema bootstrap creates the map materialized views (mv_map_regions, the
# heatmap views, mv_map_timeline_month, ...) BEFORE any systems exist, and the
# seed only refreshes mv_archetype_rankings. The map routers fall back to live
# queries only when a view is MISSING, not when it is STALE, so an unrefreshed
# view returns empty/zeroed map data. Refresh every materialized view from the
# now-seeded base tables.
echo "==> refresh materialized views"
"${COMPOSE[@]}" exec -T review-postgres \
  psql -h 127.0.0.1 -U review_user -d edfinder_local_review -v ON_ERROR_STOP=1 -q >/dev/null <<'SQL'
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT schemaname, matviewname FROM pg_matviews ORDER BY schemaname, matviewname LOOP
    EXECUTE format('REFRESH MATERIALIZED VIEW %I.%I', r.schemaname, r.matviewname);
  END LOOP;
END $$;
SQL

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
# A failing `curl -sf … && echo ok` would be exempt from `set -e` (left of &&),
# so the script could report success with a broken web/API. Fail closed, and
# retry readiness briefly before giving up.
smoke() {
  local url="$1" name="$2" deadline=$((SECONDS + 60))
  until curl -sf "$url" >/dev/null; do
    if (( SECONDS >= deadline )); then
      echo "!! smoke check FAILED: ${name} (${url}) not healthy after 60s" >&2
      exit 1
    fi
    sleep 2
  done
  echo "  ${name} ok"
}
smoke http://localhost:4174/ web
smoke http://localhost:4174/api/health api
echo "==> lab is up on http://localhost:4174 (tunnel from your laptop)"
