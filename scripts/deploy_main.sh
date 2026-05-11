#!/usr/bin/env bash
# =============================================================================
# ED Finder - production deploy for main
# =============================================================================
#
# One-command deploy for the single-directory production checkout at
# /opt/ed-finder. It is intentionally boring:
#
#   1. save the current commit for rollback
#   2. pull main with fast-forward only
#   3. apply the known idempotent/additive SQL migrations
#   4. build the frontend bundle served by nginx
#   5. rebuild/restart long-lived app containers
#   6. test and reload nginx
#   7. run local health checks
#
# Usage:
#   bash scripts/deploy_main.sh
#   bash scripts/deploy_main.sh --skip-pull
#   bash scripts/deploy_main.sh --skip-migrations
#   bash scripts/deploy_main.sh --skip-frontend
#
# Environment overrides:
#   REPO_DIR=/opt/ed-finder
#   BRANCH=main
#   PUBLIC_URL=https://ed-finder.app
# =============================================================================
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/ed-finder}"
BRANCH="${BRANCH:-main}"
PUBLIC_URL="${PUBLIC_URL:-https://ed-finder.app}"

SKIP_PULL=0
SKIP_MIGRATIONS=0
SKIP_FRONTEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pull)       SKIP_PULL=1; shift ;;
    --skip-migrations) SKIP_MIGRATIONS=1; shift ;;
    --skip-frontend)   SKIP_FRONTEND=1; shift ;;
    --branch)          BRANCH="$2"; shift 2 ;;
    --repo-dir)        REPO_DIR="$2"; shift 2 ;;
    --public-url)      PUBLIC_URL="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,35p' "$0"
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown flag: $1" >&2
      exit 64
      ;;
  esac
done

PRE_DEPLOY_FILE="/tmp/ed-finder-pre-deploy-commit.txt"

say() { printf "\n[INFO] %s\n" "$*"; }
ok()  { printf "[OK]   %s\n" "$*"; }
die() { printf "[ERROR] %s\n" "$*" >&2; exit 1; }

on_error() {
  local line="$1"
  echo >&2
  echo "[ERROR] Deploy failed near line $line." >&2
  if [[ -f "$PRE_DEPLOY_FILE" ]]; then
    echo "[INFO] Rollback target: $(cat "$PRE_DEPLOY_FILE")" >&2
    echo "[INFO] Rollback commands:" >&2
    echo "  cd $REPO_DIR" >&2
    echo "  git reset --hard \$(awk '{print \$1}' $PRE_DEPLOY_FILE)" >&2
    echo "  ( cd frontend-v2 && yarn build )" >&2
    echo "  docker compose up -d --build api eddn maintenance" >&2
    echo "  docker compose exec nginx nginx -s reload" >&2
  fi
}
trap 'on_error "$LINENO"' ERR

cd "$REPO_DIR"

say "Sanity checks"
[[ -d .git ]] || die "$REPO_DIR is not a git checkout"
[[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_DIR"
[[ -f .env ]] || die ".env not found in $REPO_DIR"
command -v git >/dev/null || die "git not found"
command -v docker >/dev/null || die "docker not found"
command -v curl >/dev/null || die "curl not found"
if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  command -v yarn >/dev/null || die "yarn not found; run corepack enable or install yarn"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  die "tracked files have local edits; commit/stash them before deploy"
fi

git log -1 --oneline > "$PRE_DEPLOY_FILE"
ok "rollback target saved to $PRE_DEPLOY_FILE: $(cat "$PRE_DEPLOY_FILE")"

if [[ "$SKIP_PULL" -eq 0 ]]; then
  say "Pull latest $BRANCH"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
  ok "now on $(git --no-pager log -1 --oneline)"
else
  say "Skipping git pull"
  ok "current commit: $(git --no-pager log -1 --oneline)"
fi

say "Check core services are available"
docker compose ps postgres >/dev/null
docker compose ps redis >/dev/null
ok "compose can see postgres and redis"

if [[ "$SKIP_MIGRATIONS" -eq 0 ]]; then
  say "Apply idempotent/additive SQL migrations"
  migrations=(
    sql/011_autocomplete_index.sql
    sql/012_topology_tables.sql
    sql/013_archetype_scores.sql
    sql/014_archetype_mv.sql
    sql/015_simulation_engine.sql
  )

  for migration in "${migrations[@]}"; do
    [[ -f "$migration" ]] || die "missing migration file: $migration"
    echo "[INFO] applying $migration"
    docker compose exec -T postgres psql \
      -U edfinder \
      -d edfinder \
      -v ON_ERROR_STOP=1 \
      < "$migration"
  done
  ok "migrations applied"
else
  say "Skipping SQL migrations"
fi

if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  say "Build frontend-v2"
  (
    cd frontend-v2
    yarn install --frozen-lockfile
    yarn build
  )
  ok "frontend built"
else
  say "Skipping frontend build"
fi

say "Rebuild/restart application containers"
docker compose up -d --build api eddn maintenance
ok "application containers updated"

say "Wait for API health"
for i in {1..30}; do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/api/health >/tmp/ed-finder-health.json; then
    ok "api health: $(cat /tmp/ed-finder-health.json)"
    break
  fi
  sleep 2
  if [[ "$i" -eq 30 ]]; then
    docker compose logs --tail=120 api || true
    die "api did not become healthy"
  fi
done

say "Verify facility catalogue"
facility_count="$(
  docker compose exec -T postgres psql -U edfinder -d edfinder -At \
    -c "SELECT COUNT(*) FROM facility_templates;"
)"
[[ "$facility_count" -ge 1 ]] || die "facility_templates is empty or missing"
ok "facility_templates rows: $facility_count"

say "Test and reload nginx"
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
ok "nginx reloaded"

say "Check nginx health route"
curl -fsS --max-time 5 http://127.0.0.1/api/health >/tmp/ed-finder-nginx-health.json
ok "nginx health: $(cat /tmp/ed-finder-nginx-health.json)"

say "Check OpenAPI simulation contract"
curl -fsS --max-time 10 http://127.0.0.1:8000/openapi.json \
  | grep -q '"SlotPredictionResponse"'
ok "OpenAPI includes SlotPredictionResponse"

say "Recent API warnings/errors"
docker compose logs --tail=120 api | grep -E "Facility catalogue|ERROR|WARNING" || true

cat <<EOF

===============================================================================
Deploy complete.

Commit:     $(git --no-pager log -1 --oneline)
Health:     http://127.0.0.1/api/health OK
Public URL: $PUBLIC_URL

If Cloudflare caches /v2/index.html, purge it now.
Rollback target is saved at: $PRE_DEPLOY_FILE
===============================================================================
EOF
