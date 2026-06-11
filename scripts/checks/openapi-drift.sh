#!/usr/bin/env bash
#
# Local OpenAPI drift check.
#
# Mirrors the CI OpenAPI job as closely as practical:
#   1. require a local/disposable Postgres + Redis;
#   2. apply schema/seed with scripts/seed_check.sh;
#   3. boot the API locally;
#   4. regenerate frontend-v2/src/types/api.gen.ts from /openapi.json;
#   5. fail if git sees drift.
#
# This script deliberately refuses production-looking DATABASE_URL values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_PORT="${OPENAPI_API_PORT:-8000}"
API_HOST="${OPENAPI_API_HOST:-127.0.0.1}"
API_URL="http://${API_HOST}:${API_PORT}"
OPENAPI_URL="${OPENAPI_URL:-${API_URL}/openapi.json}"
DATABASE_URL="${DATABASE_URL:-postgresql://edfinder:edfinder@127.0.0.1:55432/edfinder}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
ADMIN_TOKEN="${ADMIN_TOKEN:-test-admin-token}"
LOG_LEVEL="${LOG_LEVEL:-WARNING}"
API_PID=""

section() {
  printf '\n==> %s\n' "$1"
}

die() {
  printf 'openapi-drift: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command '$1'. $2"
}

pick_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
  elif [ -x "$ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
  elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
    printf '%s\n' "$ROOT/.venv/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die "missing Python. Install backend deps or set PYTHON=/path/to/python."
  fi
}

pick_yarn() {
  if [ -n "${YARN:-}" ]; then
    printf '%s\n' "$YARN"
  elif command -v yarn >/dev/null 2>&1; then
    command -v yarn
  elif command -v yarn.cmd >/dev/null 2>&1; then
    command -v yarn.cmd
  else
    die "missing yarn. Install frontend dependencies before running this check."
  fi
}

assert_safe_db_url() {
  case "$DATABASE_URL" in
    *prod*|*production*|*live*|*hetzner*|*ed-finder.app*|*edfinder.app*)
      die "DATABASE_URL must not look like a production target for this check."
      ;;
  esac
  case "$DATABASE_URL" in
    *localhost*|*127.0.0.1*|*::1*|*postgres:5432*|*postgres:55432*)
      return 0
      ;;
  esac
  die "DATABASE_URL must point at a local/disposable DB for this check."
}

cleanup() {
  if [ -n "$API_PID" ] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

PYTHON_BIN="$(pick_python)"
YARN_BIN="$(pick_yarn)"

need_cmd git "Git is required to detect generated type drift."
need_cmd curl "curl is required to wait for the local API."
need_cmd psql "psql is required because this check mirrors CI schema seeding."
assert_safe_db_url

section "Apply disposable/local schema seed"
(
  cd "$ROOT"
  DATABASE_URL="$DATABASE_URL" bash scripts/seed_check.sh
)

section "Boot local API"
(
  cd "$ROOT/apps/api/src"
  DATABASE_URL="$DATABASE_URL" \
  REDIS_URL="$REDIS_URL" \
  CORS_ORIGINS="http://test" \
  ADMIN_TOKEN="$ADMIN_TOKEN" \
  LOG_LEVEL="$LOG_LEVEL" \
  "$PYTHON_BIN" -m uvicorn main:app --host "$API_HOST" --port "$API_PORT" \
    > "${TMPDIR:-/tmp}/edfinder-openapi-uvicorn.log" 2>&1 &
  API_PID=$!
  printf '%s\n' "$API_PID" > "${TMPDIR:-/tmp}/edfinder-openapi-uvicorn.pid"
)
API_PID="$(cat "${TMPDIR:-/tmp}/edfinder-openapi-uvicorn.pid")"

for _ in $(seq 1 30); do
  if curl -sf "${API_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf "${API_URL}/api/health" >/dev/null 2>&1; then
  cat "${TMPDIR:-/tmp}/edfinder-openapi-uvicorn.log" >&2 || true
  die "API did not become healthy at ${API_URL}/api/health"
fi

section "Regenerate frontend OpenAPI types"
(
  cd "$ROOT/frontend-v2"
  VITE_OPENAPI_URL="$OPENAPI_URL" "$YARN_BIN" types:gen
)

section "Check generated type drift"
(
  cd "$ROOT"
  if ! git diff --exit-code frontend-v2/src/types/api.gen.ts; then
    die "OpenAPI type drift detected. Commit the regenerated frontend-v2/src/types/api.gen.ts."
  fi
)

section "OpenAPI drift check passed"
