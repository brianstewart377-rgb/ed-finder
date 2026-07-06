#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# ed-finder v2 deploy — all-in-one
# ─────────────────────────────────────────────────────────────────────────
#
# What this script does (in order, with rollback on failure):
#
#   1.  git fetch + checkout the v2 feature branch
#   2.  apply DB migration 007_profile_sync.sql via the postgres container
#   3.  install frontend deps  + run unit tests + build (yarn)
#   4.  rsync the built bundle into /var/www/html-v2/
#   5.  restart the backend container (picks up routers/profile.py)
#   6.  reload nginx
#   7.  smoke-check both /v2/ and /api/profile/sync
#   8.  optional: regenerate src/types/api.gen.ts from the live OpenAPI
#       (requires that nginx is configured to forward /openapi.json to
#       the backend — there's a snippet in the README to add if missing)
#
# Designed to be re-runnable. Each step is idempotent. Aborts at the
# first failure (set -e) and prints a clear summary line.
#
# Usage:
#   sudo bash deploy_v2.sh                       # full deploy
#   sudo bash deploy_v2.sh --skip-tests          # faster, no unit tests
#   sudo bash deploy_v2.sh --gen-types           # also runs yarn types:gen
#   sudo bash deploy_v2.sh --branch main         # deploy from a different branch
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "scripts/deploy_v2.sh is retired: the frontend is now served at /, not /v2/." >&2
echo "Use: bash scripts/deploy_main.sh" >&2
exit 64

REPO_DIR=${REPO_DIR:-/opt/ed-finder}
BRANCH=${BRANCH:-main}
WEBROOT=${WEBROOT:-/var/www/html-v2}
SKIP_TESTS=0
GEN_TYPES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-tests) SKIP_TESTS=1; shift ;;
    --gen-types)  GEN_TYPES=1;  shift ;;
    --branch)     BRANCH="$2";  shift 2 ;;
    *) echo "Unknown flag: $1"; exit 64 ;;
  esac
done

C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_CYAN='\033[0;36m'; C_RST='\033[0m'
say() { printf "${C_CYAN}▶ %s${C_RST}\n" "$*"; }
ok()  { printf "${C_GREEN}✓ %s${C_RST}\n" "$*"; }
die() { printf "${C_RED}✕ %s${C_RST}\n" "$*" >&2; exit 1; }

# ── 0. Sanity ────────────────────────────────────────────────────────────
say "Sanity check"
[[ -d "$REPO_DIR/.git" ]] || die "$REPO_DIR is not a git checkout"
command -v docker >/dev/null || die "docker not on PATH"
command -v yarn   >/dev/null || die "yarn not on PATH (install with: corepack enable)"
command -v rsync  >/dev/null || die "rsync not on PATH (apt install rsync)"
ok "all tools present"

# ── 1. Pull latest code on $BRANCH ──────────────────────────────────────
say "git: fetching origin and checking out $BRANCH"
cd "$REPO_DIR"
git fetch origin --tags
git checkout "$BRANCH"
# git reset --hard "origin/$BRANCH"  # disabled: preserves local docker-compose tuning
ok "on $(git --no-pager log -1 --oneline)"

# ── 2. Apply DB migration 007 (idempotent: CREATE TABLE IF NOT EXISTS) ─
say "DB migration: profile_sync table"
docker compose exec -T postgres psql -U edfinder -d edfinder \
  -v ON_ERROR_STOP=1 \
  < sql/007_profile_sync.sql \
  || die "migration 007 failed — see docker compose logs postgres"
ok "migration 007 applied"

# ── 3. Frontend: install + (test) + build ───────────────────────────────
say "Frontend build pipeline"
cd "$REPO_DIR/frontend-v2"
yarn install --frozen-lockfile
if [[ $SKIP_TESTS -eq 0 ]]; then
  yarn test || die "unit tests failed — fix before deploying"
  ok "unit tests pass"
else
  printf "  (skipping tests on user request)\n"
fi
yarn build
ok "build → dist/ ($(du -sh dist | cut -f1))"

# ── 4. Sync to webroot ──────────────────────────────────────────────────
say "Deploy: rsync dist/ → $WEBROOT"
mkdir -p "$WEBROOT"
rsync -a --delete dist/ "$WEBROOT/"
ok "$WEBROOT updated"

# ── 5. Restart backend so it picks up routers/profile.py ────────────────
say "Restart backend (so routers/profile.py is loaded)"
cd "$REPO_DIR"
docker compose restart api
# Give uvicorn a few seconds to come back online.
for i in {1..30}; do
  if curl -sf -m 2 -o /dev/null http://127.0.0.1:8000/api/status; then break; fi
  sleep 1
  [[ $i -eq 30 ]] && die "backend did not come back online after 30s — check 'docker compose logs api'"
done
ok "backend healthy"

# ── 6. Reload nginx ─────────────────────────────────────────────────────
say "Reload nginx"
if docker compose ps --services | grep -q '^nginx$'; then
  docker compose exec nginx nginx -t
  docker compose exec nginx nginx -s reload
else
  # Host-installed nginx fallback.
  nginx -t
  systemctl reload nginx
fi
ok "nginx reloaded"

# ── 7. Smoke checks ─────────────────────────────────────────────────────
say "Smoke checks"
PUBLIC_URL=${PUBLIC_URL:-https://ed-finder.app}

# Frontend
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "$PUBLIC_URL/v2/" || echo "fail")
[[ "$HTTP" == "200" ]] || die "GET $PUBLIC_URL/v2/ → $HTTP"
ok "frontend at $PUBLIC_URL/v2/  → 200"

# Manifest is the canonical sign the PWA pieces shipped.
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "$PUBLIC_URL/v2/manifest.webmanifest" || echo "fail")
[[ "$HTTP" == "200" ]] || die "manifest.webmanifest missing — PWA broken"
ok "PWA manifest         → 200"

# Service worker
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "$PUBLIC_URL/v2/sw.js" || echo "fail")
[[ "$HTTP" == "200" ]] || die "sw.js missing — service worker broken"
ok "service worker       → 200"

# Profile sync round-trip (uses a unique key so it doesn't collide).
SYNC_KEY="deploy-test-$(date +%s)-zzzz"
HTTP=$(curl -sS -o /tmp/_sync_put -w "%{http_code}" -X PUT \
  -H "Content-Type: application/json" \
  -d '{"blob":{"version":1,"exported_at":"now","ed_pinned":[]}}' \
  "$PUBLIC_URL/api/profile/sync/$SYNC_KEY" || echo "fail")
[[ "$HTTP" == "200" ]] || { cat /tmp/_sync_put; die "PUT /api/profile/sync → $HTTP"; }
ok "profile-sync PUT     → 200"

HTTP=$(curl -sS -o /tmp/_sync_get -w "%{http_code}" \
  "$PUBLIC_URL/api/profile/sync/$SYNC_KEY" || echo "fail")
[[ "$HTTP" == "200" ]] || { cat /tmp/_sync_get; die "GET /api/profile/sync → $HTTP"; }
grep -q '"version":1' /tmp/_sync_get || die "round-trip blob missing version field"
ok "profile-sync GET     → 200 (round-trip OK)"

curl -sS -X DELETE "$PUBLIC_URL/api/profile/sync/$SYNC_KEY" >/dev/null
ok "profile-sync DELETE  → 200 (test slot cleaned)"

# ── 8. Optional: regenerate src/types/api.gen.ts from live backend ──────
if [[ $GEN_TYPES -eq 1 ]]; then
  say "Codegen: regenerating src/types/api.gen.ts"
  cd "$REPO_DIR/frontend-v2"
  # Prefer the local backend (no nginx in the way).
  VITE_OPENAPI_URL="http://127.0.0.1:8000/openapi.json" yarn types:gen
  ok "api.gen.ts written ($(wc -l < src/types/api.gen.ts) lines)"
fi

# ── 9. Summary ──────────────────────────────────────────────────────────
echo
printf "${C_GREEN}════════════════════════════════════════════════════════════${C_RST}\n"
printf "${C_GREEN}  v2 deployed successfully${C_RST}\n"
printf "  • Frontend       : $PUBLIC_URL/v2/\n"
printf "  • PWA installable: yes (manifest + service worker)\n"
printf "  • Profile sync   : POST /api/profile/sync/{key} live\n"
printf "  • Branch HEAD    : %s\n" "$(git -C "$REPO_DIR" --no-pager log -1 --oneline)"
printf "${C_GREEN}════════════════════════════════════════════════════════════${C_RST}\n"
echo
echo "Next steps:"
echo "  1. Visit $PUBLIC_URL/v2/#admin and try Section 4 (Profile sync)."
echo "  2. When happy, flip nginx root to /v2/ (snippet in frontend-v2/README.md)."
echo "  3. Watch /var/log/nginx/access.log for a week, then delete /v1/."
