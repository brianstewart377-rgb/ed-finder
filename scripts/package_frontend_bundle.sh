#!/usr/bin/env bash
#
# Package an already-built frontend/dist into a reproducible archive for deploy.
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/artifacts/frontend-bundles}"
COMMIT_SHA="${COMMIT_SHA:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"
ARCHIVE_PATH=""

say() { printf '\n[INFO] %s\n' "$*"; }
ok()  { printf '[OK]   %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      ARCHIVE_PATH="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,18p' "$0"
      exit 0
      ;;
    *)
      die "Unknown flag: $1"
      ;;
  esac
done

command -v tar >/dev/null 2>&1 || die "tar not found"

[[ -d "$FRONTEND_DIR/dist" ]] || die "frontend build output missing: $FRONTEND_DIR/dist"
[[ -f "$FRONTEND_DIR/yarn.lock" ]] || die "frontend lockfile missing: $FRONTEND_DIR/yarn.lock"

mkdir -p "$OUTPUT_DIR"

if [[ -z "$ARCHIVE_PATH" ]]; then
  ARCHIVE_PATH="$OUTPUT_DIR/frontend-dist-${COMMIT_SHA}.tar.gz"
fi

CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

say "Create frontend bundle"
tar --force-local -C "$FRONTEND_DIR" -czf "$ARCHIVE_PATH" dist
ok "archive written: $ARCHIVE_PATH"

say "Write bundle checksum"
if command -v sha256sum >/dev/null 2>&1; then
  CHECKSUM_OUTPUT="$(sha256sum "$ARCHIVE_PATH")"
elif command -v shasum >/dev/null 2>&1; then
  CHECKSUM_OUTPUT="$(shasum -a 256 "$ARCHIVE_PATH")"
else
  die "missing sha256sum/shasum"
fi
CHECKSUM="${CHECKSUM_OUTPUT%% *}"
CHECKSUM="${CHECKSUM#\\}"
printf '%s  %s\n' "$CHECKSUM" "$ARCHIVE_PATH" > "$CHECKSUM_PATH"
ok "checksum written: $CHECKSUM_PATH"

printf '%s\n' "$ARCHIVE_PATH"
