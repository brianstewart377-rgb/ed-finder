#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="ed-finder"
EXPECTED_REPO_DIR="/opt/ed-finder"
STAGE18J_ARTIFACT_DIR="${ART_DIR:-/var/lib/ed-finder/operator-artifacts/stage-18j}"
ALLOW_NON_HETZNER="${EDFINDER_ALLOW_NON_HETZNER_OPERATOR_ENV:-no}"
REQUIRE_STAGE18J_ARTIFACT_DIR="${REQUIRE_STAGE18J_ARTIFACT_DIR:-no}"

stop() {
  printf 'STOP: %s\n' "$*" >&2
  printf 'This command is for the Hetzner production operator shell only.\n' >&2
  printf 'Run repo/code/docs/PR work in Codex or local dev, and run operator artifact commands from %s on host %s.\n' \
    "$EXPECTED_REPO_DIR" "$EXPECTED_HOSTNAME" >&2
  exit 1
}

actual_hostname="$(hostname 2>/dev/null || true)"
if [[ "$actual_hostname" != "$EXPECTED_HOSTNAME" && "$ALLOW_NON_HETZNER" != "yes" ]]; then
  stop "wrong host '${actual_hostname:-unknown}'. Expected '$EXPECTED_HOSTNAME'. Set EDFINDER_ALLOW_NON_HETZNER_OPERATOR_ENV=yes only for an explicitly approved operator exception."
fi

current_dir="$(pwd -P)"
if [[ "$current_dir" != "$EXPECTED_REPO_DIR" ]]; then
  stop "wrong working directory '$current_dir'. Expected '$EXPECTED_REPO_DIR'."
fi

if [[ ! -f docker-compose.yml ]]; then
  stop "docker-compose.yml was not found in '$current_dir'."
fi

if [[ "$REQUIRE_STAGE18J_ARTIFACT_DIR" == "yes" && ! -d "$STAGE18J_ARTIFACT_DIR" ]]; then
  stop "required Stage 18J artifact directory is missing: $STAGE18J_ARTIFACT_DIR"
fi

if ! command -v docker >/dev/null 2>&1; then
  stop "docker CLI is not available in this shell."
fi

if ! docker compose ps >/dev/null 2>&1; then
  stop "docker compose ps failed. Confirm this is the production operator shell and Docker Compose services are available."
fi

printf 'OK: Hetzner operator environment guard passed for %s on host %s.\n' "$current_dir" "$actual_hostname"
