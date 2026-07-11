#!/usr/bin/env bash
#
# Run the read-only data invariants check and optionally write a small JSON
# receipt. This is the production-safe wrapper for:
#   - post-deploy verification
#   - weekly host-cron verification
#   - manual operator spot checks
#
# By default it targets the running api container from the repo checkout.
# If DATABASE_URL is supplied, it will run directly on the host instead.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_RATING_VERSION="${TARGET_RATING_VERSION:-3.4}"
PRODUCTION_SAFE=0
RECEIPT_FILE="${RECEIPT_FILE:-}"
DURABLE_RECEIPT_DIR="${DURABLE_RECEIPT_DIR:-}"
DATABASE_URL_OVERRIDE="${DATA_INVARIANTS_DATABASE_URL:-}"
COMPOSE_FILE_OVERRIDE="${EDFINDER_DOCKER_COMPOSE_FILE:-}"
COMPOSE_PROJECT_NAME_OVERRIDE="${EDFINDER_DOCKER_PROJECT_NAME:-}"
compose_args=()

say() { printf '\n[INFO] %s\n' "$*"; }
ok()  { printf '[OK]   %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '1,20p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-rating-version) TARGET_RATING_VERSION="$2"; shift 2 ;;
    --receipt-file) RECEIPT_FILE="$2"; shift 2 ;;
    --durable-receipt-dir) DURABLE_RECEIPT_DIR="$2"; shift 2 ;;
    --database-url) DATABASE_URL_OVERRIDE="$2"; shift 2 ;;
    --compose-file) COMPOSE_FILE_OVERRIDE="$2"; shift 2 ;;
    --project-name) COMPOSE_PROJECT_NAME_OVERRIDE="$2"; shift 2 ;;
    --production-safe) PRODUCTION_SAFE=1; shift ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown flag: $1"
      ;;
  esac
done

cd "$REPO_DIR"

if [[ -n "$COMPOSE_FILE_OVERRIDE" ]]; then
  [[ -f "$COMPOSE_FILE_OVERRIDE" ]] || die "compose file not found: $COMPOSE_FILE_OVERRIDE"
  compose_args+=(-f "$COMPOSE_FILE_OVERRIDE")
elif [[ -z "$DATABASE_URL_OVERRIDE" && -z "${DATABASE_URL:-}" ]]; then
  [[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_DIR"
fi

if [[ -n "$COMPOSE_PROJECT_NAME_OVERRIDE" ]]; then
  compose_args+=(-p "$COMPOSE_PROJECT_NAME_OVERRIDE")
fi

dc() {
  docker compose "${compose_args[@]}" "$@"
}

resolve_host_database_url() {
  local container_url
  container_url="$(dc exec -T api printenv DATABASE_URL | tr -d '\r' | tail -n 1)"
  [[ -n "$container_url" ]] || die "could not read DATABASE_URL from api container"

  case "$container_url" in
    *@postgres:*|*@db:*)
      printf '%s\n' "$container_url" | sed -E 's#@([^:/]+):#@127.0.0.1:#'
      ;;
    *)
      printf '%s\n' "$container_url"
      ;;
  esac
}

command_args=(scripts/checks/data_invariants.py --target-rating-version "$TARGET_RATING_VERSION")
if [[ "$PRODUCTION_SAFE" -eq 1 ]]; then
  command_args+=(--production-safe)
fi

mode="host_database_url"
runner=()
effective_database_url="$DATABASE_URL_OVERRIDE"
if [[ -z "$effective_database_url" && -n "${DATABASE_URL:-}" ]]; then
  effective_database_url="$DATABASE_URL"
fi

if [[ -n "$effective_database_url" ]]; then
  command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || die "python/python3 not found for DATABASE_URL mode"
  mode="database_url"
  python_bin="$(command -v python3 || command -v python)"
  command_args=("$python_bin" "${command_args[@]}" --database-url "$effective_database_url")
  runner=("${command_args[@]}")
else
  command -v docker >/dev/null 2>&1 || die "docker not found"
  command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || die "python/python3 not found for host invariants mode"
  host_database_url="$(resolve_host_database_url)"
  python_bin="$(command -v python3 || command -v python)"
  command_args=("$python_bin" "${command_args[@]}" --database-url "$host_database_url")
  runner=("${command_args[@]}")
fi

started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
completed_at=""
tmp_output="$(mktemp)"

say "Run data invariants ($mode)"
set +e
"${runner[@]}" | tee "$tmp_output"
exit_code=${PIPESTATUS[0]}
set -e

status="failed"
if [[ "$exit_code" -eq 0 ]]; then
  status="passed"
fi
completed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

receipt_json="$(cat <<EOF
{
  "started_at_utc": "$started_at",
  "completed_at_utc": "$completed_at",
  "status": "$status",
  "exit_code": $exit_code,
  "mode": "$mode",
  "target_rating_version": "$TARGET_RATING_VERSION",
  "production_safe": $([[ "$PRODUCTION_SAFE" -eq 1 ]] && echo true || echo false)
}
EOF
)"

if [[ -n "$RECEIPT_FILE" ]]; then
  mkdir -p "$(dirname "$RECEIPT_FILE")"
  printf '%s\n' "$receipt_json" > "$RECEIPT_FILE"
  ok "wrote invariants receipt: $RECEIPT_FILE"
fi

if [[ -n "$DURABLE_RECEIPT_DIR" ]]; then
  durable_stamp="$(printf '%s' "$completed_at" | tr -d ':-' | sed 's/T/_/; s/Z$//')"
  durable_receipt_file="$DURABLE_RECEIPT_DIR/data-invariants-${durable_stamp}.json"
  durable_latest_file="$DURABLE_RECEIPT_DIR/latest.json"
  mkdir -p "$DURABLE_RECEIPT_DIR"
  printf '%s\n' "$receipt_json" > "$durable_receipt_file"
  printf '%s\n' "$receipt_json" > "$durable_latest_file"
  ok "wrote durable invariants receipt: $durable_receipt_file"
  ok "updated durable invariants receipt alias: $durable_latest_file"
fi

if [[ "$exit_code" -ne 0 ]]; then
  echo "[ERROR] data invariants failed; last output lines:" >&2
  tail -n 20 "$tmp_output" >&2 || true
  exit "$exit_code"
fi

ok "data invariants passed"
