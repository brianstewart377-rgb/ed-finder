#!/bin/bash
# =============================================================================
# ED Finder — Import Runner  (v2.0)
# =============================================================================
# Always use this script instead of raw 'docker run' commands.
# It uses 'docker compose' which guarantees:
#   - Correct network (ed-finder_default) — no DNS failures
#   - Correct service hostname (postgres) — no IP address guessing
#   - Scripts mounted from latest repo code — no image rebuilds needed
#   - Password from .env — no manual substitution
#
# Usage:
#   ./scripts/run_import.sh                        # show import status
#   ./scripts/run_import.sh --all                  # import all dumps (auto-resumes)
#   ./scripts/run_import.sh --download-only        # download dumps only
#   ./scripts/run_import.sh build_grid.py          # run build_grid
#   ./scripts/run_import.sh build_ratings.py       # run build_ratings
#   ./scripts/run_import.sh build_clusters.py      # run build_clusters
#   ./scripts/run_import.sh scripts/repair_body_contract.py --json
#   ./scripts/run_import.sh scripts/reconcile_no_body_ratings.py --apply --batch-size 5000
#   ./scripts/run_import.sh build_grid.py --reset-cache    # force full rebuild
#   ./scripts/run_import.sh build_ratings.py --rebuild
#   ./scripts/run_import.sh build_clusters.py --rebuild
#
# CHANGES in v2.0:
#   - Removed the two-directory deployment model. The script now always runs
#     from the directory containing docker-compose.yml (the repo root), which
#     is /opt/ed-finder. There is no longer a separate /opt/ed-finder-src.
#   - Removed the file-sync block that copied Python scripts between directories.
#   - Simplified .env detection to look only in the script's parent directory.
#   - Added first-class support for repo-root helper scripts under scripts/.
#   - Forces unbuffered Python output so long-running helper progress reaches
#     the operator without waiting on stdio buffers.
#   - Avoids attached `docker compose run` transport flakiness by starting the
#     one-shot importer container detached, streaming logs explicitly, waiting
#     for exit, and then removing the container.
#
# FIXES in v1.3 (retained):
#   - Orphaned importer containers (ed-importer in Exited state) are removed
#     automatically before every run.
#   - Password sync also restarts pgBouncer when a mismatch is detected.
#   - Password sync tries both 'edfinder' and 'postgres' superuser.
#   - Clear error message if ed-postgres container is not running at all.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The repo root is one level up from scripts/
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Verify docker-compose.yml is present
if [[ ! -f "$INSTALL_DIR/docker-compose.yml" ]]; then
    echo "[ERROR] docker-compose.yml not found at $INSTALL_DIR"
    echo "        This script must be run from within the ed-finder repo."
    echo "        Expected location: /opt/ed-finder/scripts/run_import.sh"
    exit 1
fi

echo "[INFO] Install dir: $INSTALL_DIR"

# ── Locate .env ──────────────────────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[ERROR] .env not found at $ENV_FILE. Create it with:"
    echo "        echo 'POSTGRES_PASSWORD=yourpassword' > $ENV_FILE"
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

cd "$INSTALL_DIR"

# ── Pre-flight 1: Remove orphaned importer containers ────────────────────────
# docker compose run --rm should remove the container on exit, but if the
# container is killed (SIGKILL / OOM / daemon crash) the --rm never fires.
# A leftover ed-importer in Exited state will block the next run with:
#   "Conflict. The container name '/ed-importer' is already in use"
echo "[INFO] Checking for orphaned importer containers ..."
ORPHANS=$(docker ps -a --filter "name=ed-importer" --filter "status=exited" -q 2>/dev/null || true)
if [[ -n "$ORPHANS" ]]; then
    COUNT=$(echo "$ORPHANS" | wc -l)
    echo "[WARN] Found $COUNT orphaned importer container(s) — removing ..."
    echo "$ORPHANS" | xargs docker rm -f
    echo "[OK]   Orphaned containers removed."
else
    echo "[OK]   No orphaned importer containers."
fi

# Also remove any containers stuck in Created state (never started)
CREATED=$(docker ps -a --filter "name=ed-importer" --filter "status=created" -q 2>/dev/null || true)
if [[ -n "$CREATED" ]]; then
    echo "[WARN] Found importer container(s) stuck in Created state — removing ..."
    echo "$CREATED" | xargs docker rm -f
    echo "[OK]   Removed."
fi

# ── Pre-flight 2: Verify DB password and sync if needed ──────────────────────
echo "[INFO] Verifying DB password ..."

if ENV_FILE="$ENV_FILE" bash "$INSTALL_DIR/scripts/sync_password.sh" --verify-only &>/dev/null; then
    echo "[OK]   DB password verified."
else
    echo "[WARN] Password mismatch detected — resyncing ..."
    if ! ENV_FILE="$ENV_FILE" bash "$INSTALL_DIR/scripts/sync_password.sh"; then
        echo "[ERROR] Could not update password in PostgreSQL."
        exit 1
    fi
    echo "[OK]   Password sync successful."
fi

# ── Determine what to run ────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    SCRIPT="/app/import_spansh.py"
    SCRIPT_LABEL="import_spansh.py"
    ARGS=(--status)
elif [[ "$1" == build_*.py ]]; then
    SCRIPT="/app/$1"
    SCRIPT_LABEL="$1"
    shift
    ARGS=("$@")
elif [[ "$1" == scripts/*.py ]]; then
    SCRIPT="/opt/ed-finder/$1"
    SCRIPT_LABEL="$1"
    shift
    ARGS=("$@")
else
    SCRIPT="/app/import_spansh.py"
    SCRIPT_LABEL="import_spansh.py"
    ARGS=("$@")
fi

echo "=============================================="
echo " ED Finder Import Runner v2.0"
echo " Script : $SCRIPT_LABEL ${ARGS[*]:-}"
echo " Dir    : $INSTALL_DIR"
echo " Env    : $ENV_FILE"
echo " Network: ed-finder_default (via docker compose)"
echo "=============================================="

# Use detached docker compose run plus explicit log follow + wait.
# This avoids the flaky attached transport path we've seen with long-running
# helper jobs, while still using compose for the right network, env, and mounts.
JOB_NAME="ed-importer-job-$(date +%Y%m%d%H%M%S)-$$"

cleanup_job() {
    docker rm -f "$JOB_NAME" >/dev/null 2>&1 || true
}

docker compose --profile import run -d --name "$JOB_NAME" \
    --entrypoint python3 \
    -e PYTHONUNBUFFERED=1 \
    -e LOG_FILE="/data/logs/$(basename "${SCRIPT_LABEL%.py}").log" \
    importer \
    -u "$SCRIPT" "${ARGS[@]}"

echo "[INFO] Job container: $JOB_NAME"

docker logs -f "$JOB_NAME" &
LOGS_PID=$!

EXIT_CODE="$(docker wait "$JOB_NAME")"

wait "$LOGS_PID" || true
cleanup_job

exit "$EXIT_CODE"
