#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="ed-finder-prod"
EXPECTED_REPO_DIR="/opt/ed-finder"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  printf 'This command is for the NEW MevSpace ED-Finder operator shell only.\n' >&2
  printf 'Expected host: %s\n' "$EXPECTED_HOSTNAME" >&2
  printf 'Expected repo: %s\n' "$EXPECTED_REPO_DIR" >&2
  exit 1
}

actual_hostname="$(hostname 2>/dev/null || true)"
[[ "$actual_hostname" == "$EXPECTED_HOSTNAME" ]] || stop "wrong host '${actual_hostname:-unknown}'"

current_dir="$(pwd -P)"
[[ "$current_dir" == "$EXPECTED_REPO_DIR" ]] || stop "wrong working directory '$current_dir'"

[[ -f docker-compose.yml || -f compose.yml || -f compose.yaml ]] || \
  stop "no Compose file found in '$current_dir'"

command -v docker >/dev/null 2>&1 || stop "docker CLI is not available"
docker info >/dev/null 2>&1 || stop "docker daemon is not available"

printf 'OK: MevSpace operator environment guard passed for %s on host %s.\n' \
  "$current_dir" "$actual_hostname"
