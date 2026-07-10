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
elif [[ -z "${DATABASE_URL:-}" ]]; then
  [[ -f docker-compose.yml ]] || die "docker-compose.yml not found in $REPO_DIR"
fi

if [[ -n "$COMPOSE_PROJECT_NAME_OVERRIDE" ]]; then
  compose_args+=(-p "$COMPOSE_PROJECT_NAME_OVERRIDE")
fi

dc() {
  docker compose "${compose_args[@]}" "$@"
}

command_args=(scripts/checks/data_invariants.py --target-rating-version "$TARGET_RATING_VERSION")
if [[ "$PRODUCTION_SAFE" -eq 1 ]]; then
  command_args+=(--production-safe)
fi

mode="docker_compose_api"
runner=()
if [[ -n "${DATABASE_URL:-}" ]]; then
  command -v python >/dev/null 2>&1 || die "python not found for DATABASE_URL mode"
  mode="database_url"
  command_args=(python "${command_args[@]}" --database-url "$DATABASE_URL")
  runner=("${command_args[@]}")
else
  command -v docker >/dev/null 2>&1 || die "docker not found"
  runner=(dc exec -T api python "${command_args[@]}")
fi

started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
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

if [[ -n "$RECEIPT_FILE" ]]; then
  mkdir -p "$(dirname "$RECEIPT_FILE")"
  cat > "$RECEIPT_FILE" <<EOF
{
  "started_at_utc": "$started_at",
  "completed_at_utc": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "status": "$status",
  "exit_code": $exit_code,
  "mode": "$mode",
  "target_rating_version": "$TARGET_RATING_VERSION",
  "production_safe": $([[ "$PRODUCTION_SAFE" -eq 1 ]] && echo true || echo false)
}
EOF
  ok "wrote invariants receipt: $RECEIPT_FILE"
fi

if [[ "$exit_code" -ne 0 ]]; then
  echo "[ERROR] data invariants failed; last output lines:" >&2
  tail -n 20 "$tmp_output" >&2 || true
  exit "$exit_code"
fi

ok "data invariants passed"
