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
#   3. apply pending ledgered SQL migrations
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
#   bash scripts/deploy_main.sh --external-db
#   bash scripts/deploy_main.sh --frontend-archive /tmp/frontend-dist.tar.gz
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
FRONTEND_DIR="${FRONTEND_DIR:-frontend}"
FRONTEND_ARCHIVE="${FRONTEND_ARCHIVE:-}"

SKIP_PULL=0
SKIP_MIGRATIONS=0
SKIP_FRONTEND=0
SKIP_INVARIANTS=0
EXTERNAL_DB_MODE="${EDFINDER_EXTERNAL_DB_MODE:-false}"
EXTERNAL_DB_FLAG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pull)       SKIP_PULL=1; shift ;;
    --skip-migrations) SKIP_MIGRATIONS=1; shift ;;
    --skip-frontend)   SKIP_FRONTEND=1; shift ;;
    --skip-invariants) SKIP_INVARIANTS=1; shift ;;
    --external-db)     EXTERNAL_DB_MODE=true; EXTERNAL_DB_FLAG=1; shift ;;
    --frontend-archive) FRONTEND_ARCHIVE="$2"; shift 2 ;;
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

say()  { printf "\n[INFO] %s\n" "$*"; }
ok()   { printf "[OK]   %s\n" "$*"; }
warn() { printf "[WARN] %s\n" "$*" >&2; }
die()  { printf "[ERROR] %s\n" "$*" >&2; exit 1; }

on_error() {
  local line="$1"
  echo >&2
  echo "[ERROR] Deploy failed near line $line." >&2
  if [[ -f "$PRE_DEPLOY_FILE" ]]; then
    echo "[INFO] Rollback target: $(cat "$PRE_DEPLOY_FILE")" >&2
    echo "[INFO] Rollback commands:" >&2
    echo "  cd $REPO_DIR" >&2
    echo "  git reset --hard \$(awk '{print \$1}' $PRE_DEPLOY_FILE)" >&2
    echo "  ( cd $FRONTEND_DIR && yarn build )" >&2
    if [[ "$EXTERNAL_DB_MODE" == "true" ]]; then
      echo "  docker compose up -d --build --no-deps api eddn maintenance" >&2
    else
      echo "  docker compose up -d --build api eddn maintenance" >&2
    fi
    echo "  docker compose exec nginx nginx -s reload" >&2
  fi
}
trap 'on_error "$LINENO"' ERR

cd "$REPO_DIR"

say "Sanity checks"
[[ -d .git ]] || die "$REPO_DIR is not a git checkout"
[[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_DIR"
[[ -f .env ]] || die ".env not found in $REPO_DIR"
[[ -d "$FRONTEND_DIR" ]] || die "frontend directory not found: $FRONTEND_DIR"
[[ -f "$FRONTEND_DIR/package.json" ]] || die "frontend manifest not found: $FRONTEND_DIR/package.json"
[[ -f "$FRONTEND_DIR/yarn.lock" ]] || die "frontend lockfile not found: $FRONTEND_DIR/yarn.lock"
command -v git >/dev/null || die "git not found"
command -v docker >/dev/null || die "docker not found"
command -v curl >/dev/null || die "curl not found"

# Compose reads .env automatically; load it here too so the explicit mode and
# its role-separated URLs are validated. Preserve every value explicitly
# exported by the operator: shell overrides have the same precedence here that
# Docker Compose gives them over values from .env.
declare -A OPERATOR_EXPORTED_ENV=()
while IFS= read -r name; do
  OPERATOR_EXPORTED_ENV["$name"]="${!name}"
done < <(compgen -e)
set -a
# shellcheck source=/dev/null
source .env
set +a
for name in "${!OPERATOR_EXPORTED_ENV[@]}"; do
  export "$name=${OPERATOR_EXPORTED_ENV[$name]}"
done
unset OPERATOR_EXPORTED_ENV name
# Child scripts must consume this already-resolved environment. In particular,
# the migration applier must not source .env again and replace operator-exported
# role URLs with file values.
export EDFINDER_ENV_ALREADY_RESOLVED=1
if [[ "$EXTERNAL_DB_FLAG" -eq 0 ]]; then
  EXTERNAL_DB_MODE="${EDFINDER_EXTERNAL_DB_MODE:-false}"
fi

case "$EXTERNAL_DB_MODE" in
  true)
    bash scripts/validate_external_db_config.sh --config-only
    bash scripts/validate_external_db_config.sh
    ;;
  false) ;;
  *) die "EDFINDER_EXTERNAL_DB_MODE must be exactly true or false" ;;
esac
if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  if [[ -n "$FRONTEND_ARCHIVE" ]]; then
    command -v tar >/dev/null || die "tar not found; required to extract --frontend-archive"
  else
    command -v yarn >/dev/null || die "yarn not found; run corepack enable or install yarn"
  fi
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
if [[ "$EXTERNAL_DB_MODE" == "false" ]]; then
  docker compose ps postgres >/dev/null
else
  if [[ -n "$(docker compose ps --status running --services postgres)" ]]; then
    die "bundled postgres is running in external database mode"
  fi
  # Start Redis explicitly because --no-deps below deliberately prevents
  # Compose from starting either Redis or the bundled PostgreSQL dependency.
  docker compose up -d --no-deps redis
  redis_healthy=0
  for i in {1..30}; do
    if [[ "$(docker compose exec -T redis redis-cli ping 2>/dev/null || true)" == "PONG" ]]; then
      redis_healthy=1
      break
    fi
    sleep 2
  done
  [[ "$redis_healthy" -eq 1 ]] || die "redis did not become healthy"
fi
docker compose ps redis >/dev/null
ok "required database and redis services are available"

if [[ "$SKIP_MIGRATIONS" -eq 0 ]]; then
  say "Apply pending ledgered SQL migrations"
  [[ -f scripts/apply_migrations.sh ]] || die "migration applier not found: scripts/apply_migrations.sh"
  bash scripts/apply_migrations.sh
  ok "migrations applied"

  # Emergent adversarial-review recurrence check (2026-08-07), item A4:
  # the call above never passes --include-manual, so every migration
  # marked |manual in sql/migration-manifest.txt is silently skipped —
  # apply_migrations.sh only prints an [INFO] line for each one, and this
  # script still reports "migrations applied" right after. That's
  # intentional (manual migrations are meant to be deployed in their own
  # separate, monitored window per their runbooks, not bundled into every
  # normal deploy) but the silence made it easy to forget one is pending
  # indefinitely. This makes a pending manual migration loud instead.
  #
  # Delegates to apply_migrations.sh --list-pending-manual (Codex Review
  # finding on the first version of this check) rather than querying the
  # DB directly here: that applier already resolves DATABASE_MIGRATION_URL/
  # MIGRATION_LEDGER_TABLE overrides and the docker-vs-direct-psql
  # connection mode, and duplicating that logic here risked silently
  # inspecting the wrong database/ledger if either is ever configured —
  # doubly dangerous since the query result was previously wrapped in
  # `2>/dev/null || true`, which would have shown "nothing pending" for a
  # query that actually errored, not just one that legitimately found
  # nothing.
  pending_manual="$(bash scripts/apply_migrations.sh --list-pending-manual)"
  if [[ -n "$pending_manual" ]]; then
    warn "Manual migration(s) pending — NOT applied by this deploy (see their runbooks for the separate apply procedure): $(printf '%s' "$pending_manual" | tr '\n' ' ')"
  fi
else
  say "Skipping SQL migrations"
fi

if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
if [[ -n "$FRONTEND_ARCHIVE" ]]; then
say "Install prebuilt frontend artifact"
[[ -f "$FRONTEND_ARCHIVE" ]] || die "frontend archive not found: $FRONTEND_ARCHIVE"
tmp_frontend_dir="$(mktemp -d)"
tar -xzf "$FRONTEND_ARCHIVE" -C "$tmp_frontend_dir"
[[ -f "$tmp_frontend_dir/dist/index.html" ]] || die "frontend archive did not contain dist/index.html"
rm -rf "$FRONTEND_DIR/dist"
mv "$tmp_frontend_dir/dist" "$FRONTEND_DIR/dist"
rm -rf "$tmp_frontend_dir"
ok "frontend artifact extracted from $FRONTEND_ARCHIVE"
else
say "Build $FRONTEND_DIR"
(
  cd "$FRONTEND_DIR"
  # --ignore-engines: production Node is currently 20.x, but the test-only jsdom
  # devDependency declares "engines: node >=22". jsdom is not used by the vite
  # build (only by vitest), so the build itself runs fine on Node 20 — without
  # this flag `yarn install` aborts with "engine incompatible" and blocks the
  # whole deploy. Remove this flag once production Node is upgraded to >= 22
  # (or once jsdom is pinned back to a Node-20-compatible major in the frontend).
  yarn install --frozen-lockfile --no-progress --non-interactive --ignore-engines
  yarn build
)
ok "frontend built"
fi
else
  say "Skipping frontend build"
fi

say "Rebuild/restart application containers"
export EDFINDER_BUILD_SHA
EDFINDER_BUILD_SHA="$(git rev-parse HEAD)"
ok "deployment build SHA: $EDFINDER_BUILD_SHA"
if [[ "$EXTERNAL_DB_MODE" == "true" ]]; then
  # --no-deps is the critical isolation boundary: api/eddn/maintenance retain
  # their default bundled-postgres dependency for existing deployments, but an
  # explicit external deployment must never create or start that service.
  docker compose up -d --build --no-deps api eddn maintenance
else
  docker compose up -d --build api eddn maintenance
fi
ok "application containers updated"

say "Recreate nginx to pick up config and volume changes"
if [[ "$EXTERNAL_DB_MODE" == "true" ]]; then
  docker compose up -d --force-recreate --no-deps nginx
else
  docker compose up -d --force-recreate nginx
fi
ok "nginx container recreated"

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
if [[ "$EXTERNAL_DB_MODE" == "true" ]]; then
  facility_count="$(PGCONNECT_TIMEOUT=10 PGOPTIONS='-c default_transaction_read_only=on' \
    psql --no-psqlrc --dbname="$DATABASE_READONLY_URL" -AtX \
      -c "SELECT COUNT(*) FROM facility_templates;")"
else
  facility_count="$(
    docker compose exec -T postgres psql -U edfinder -d edfinder -At \
      -c "SELECT COUNT(*) FROM facility_templates;"
  )"
fi
[[ "$facility_count" -ge 1 ]] || die "facility_templates is empty or missing"
ok "facility_templates rows: $facility_count"

say "Test and reload nginx"
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
ok "nginx reloaded"

say "Check nginx health route"
nginx_health_ok=0
for i in {1..30}; do
  if curl -fsS --max-time 5 http://127.0.0.1/api/health >/tmp/ed-finder-nginx-health.json; then
    nginx_health_ok=1
    ok "nginx health: $(cat /tmp/ed-finder-nginx-health.json)"
    break
  fi
  sleep 2
done

if [[ "$nginx_health_ok" -ne 1 ]]; then
  echo "[WARN] nginx health route did not return 200 after retries" >&2
  curl -sS -D /tmp/ed-finder-nginx-health.headers -o /tmp/ed-finder-nginx-health.body \
    --max-time 5 http://127.0.0.1/api/health || true
  echo "[INFO] nginx health response headers:" >&2
  cat /tmp/ed-finder-nginx-health.headers >&2 || true
  echo "[INFO] nginx health response body:" >&2
  cat /tmp/ed-finder-nginx-health.body >&2 || true

  say "Nginx/API diagnostics"
  docker compose ps api nginx >&2 || true
  echo "[INFO] docker compose logs --tail=120 nginx" >&2
  docker compose logs --tail=120 nginx >&2 || true
  echo "[INFO] docker compose logs --tail=120 api" >&2
  docker compose logs --tail=120 api >&2 || true
  echo "[INFO] Probe API from nginx container (api:8000)" >&2
  docker compose exec -T nginx sh -lc '\
    if command -v curl >/dev/null 2>&1; then \
      curl -sS --max-time 5 http://api:8000/api/health; \
    elif command -v wget >/dev/null 2>&1; then \
      wget -qO- http://api:8000/api/health; \
    else \
      echo "no curl/wget available in nginx container"; \
    fi' >&2 || true

  die "nginx health route remained unavailable (HTTP 502/timeout)"
fi

say "Check OpenAPI simulation contract"
curl -fsS --max-time 10 http://127.0.0.1:8000/openapi.json \
  | grep -q '"SlotPredictionResponse"'
ok "OpenAPI includes SlotPredictionResponse"

if [[ "$SKIP_INVARIANTS" -eq 0 ]]; then
  say "Run post-deploy data invariants"
  [[ -f scripts/run_data_invariants_receipted.sh ]] || die "invariants wrapper not found: scripts/run_data_invariants_receipted.sh"
  # --allow-stale-noneligible: 2026-08-07 incident — this deploy failed
  # twice on dirty_truthful_no_bodies (systems with rating_dirty=TRUE AND
  # has_body_data=FALSE), a count that's expected to be transiently nonzero
  # between runs of scripts/run_dirty_ratings_if_needed.sh's 30-minute
  # reconciliation cycle (see CLAUDE.md's "Dirty ratings maintenance"
  # section — the no-body cleanup half of that job owns clearing this
  # count, not this gate). The app itself was healthy and serving the new
  # code both times; only this post-deploy verification step was failing
  # on a metric documented elsewhere as normal bounded churn. Same
  # rationale as the pre-existing --allow-stale-colonisation-status below.
  bash scripts/run_data_invariants_receipted.sh \
    --target-rating-version 3.4 \
    --production-safe \
    --allow-stale-colonisation-status \
    --allow-stale-noneligible \
    --receipt-file /tmp/ed-finder-data-invariants-post-deploy.json \
    --durable-receipt-dir /data/receipts/data-invariants/post-deploy
  ok "post-deploy data invariants passed"
else
  say "Skipping post-deploy data invariants"
fi

say "Recent API warnings/errors"
docker compose logs --tail=120 api | grep -E "Facility catalogue|ERROR|WARNING" || true

cat <<EOF

===============================================================================
Deploy complete.

Commit:     $(git --no-pager log -1 --oneline)
Health:     http://127.0.0.1/api/health OK
Public URL: $PUBLIC_URL

Smoke-check the promoted root frontend now:
  curl -I "$PUBLIC_URL/"
  curl -I "$PUBLIC_URL/index.html"
Compatibility check for old /v2/ bookmarks:
  curl -I "$PUBLIC_URL/v2/"
Rollback target is saved at: $PRE_DEPLOY_FILE
===============================================================================
EOF
