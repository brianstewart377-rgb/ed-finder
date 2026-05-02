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

if ! docker inspect ed-postgres &>/dev/null; then
    echo "[ERROR] Container ed-postgres is not running."
    echo "        Start the stack first: cd $INSTALL_DIR && docker compose up -d"
    exit 1
fi

if docker exec -i ed-postgres psql \
        "postgresql://edfinder:${POSTGRES_PASSWORD}@localhost:5432/edfinder" \
        -c "SELECT 1;" &>/dev/null; then
    echo "[OK]   DB password verified."
else
    echo "[WARN] Password mismatch detected — resyncing ..."

    # Try ALTER USER as edfinder first, then fall back to postgres superuser
    SYNCED=false
    if docker exec -i ed-postgres psql -U edfinder -d edfinder \
            -c "ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';" &>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (as edfinder)."
        SYNCED=true
    elif docker exec -i ed-postgres psql -U postgres -d postgres \
            -c "ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';" &>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (as postgres superuser)."
        SYNCED=true
    fi

    if [[ "$SYNCED" == false ]]; then
        echo "[ERROR] Could not update password in PostgreSQL."
        echo "        Run:  bash $INSTALL_DIR/scripts/sync_password.sh"
        echo "        Or recreate the container:"
        echo "          cd $INSTALL_DIR"
        echo "          docker compose stop postgres pgbouncer"
        echo "          docker compose up -d postgres pgbouncer"
        exit 1
    fi

    # Restart pgBouncer so it reloads the new hash — without this pgBouncer
    # keeps its cached (wrong) password and connections still fail.
    if docker inspect ed-pgbouncer &>/dev/null; then
        echo "[INFO] Restarting pgBouncer to reload credentials ..."
        docker restart ed-pgbouncer
        sleep 3
        echo "[OK]   pgBouncer restarted."
    fi

    # Final verification
    if docker exec -i ed-postgres psql \
            "postgresql://edfinder:${POSTGRES_PASSWORD}@localhost:5432/edfinder" \
            -c "SELECT 1;" &>/dev/null; then
        echo "[OK]   Password sync successful."
    else
        echo "[ERROR] Connection still failing after password sync."
        echo "        Run:  bash $INSTALL_DIR/scripts/sync_password.sh"
        exit 1
    fi
fi

# ── Determine what to run ────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
    SCRIPT="import_spansh.py"
    ARGS="--status"
elif [[ "$1" == build_*.py ]]; then
    SCRIPT="$1"
    shift
    ARGS="${*:-}"
else
    SCRIPT="import_spansh.py"
    ARGS="$*"
fi

echo "=============================================="
echo " ED Finder Import Runner v2.0"
echo " Script : $SCRIPT ${ARGS:-}"
echo " Dir    : $INSTALL_DIR"
echo " Env    : $ENV_FILE"
echo " Network: ed-finder_default (via docker compose)"
echo "=============================================="

# Use docker compose run — always gets the right network and DNS.
# --rm ensures the container is removed on clean exit.
# The orphan cleanup above handles the case where --rm didn't fire.
docker compose --profile import run --rm \
    --entrypoint python3 \
    -e LOG_FILE="/data/logs/${SCRIPT%.py}.log" \
    importer \
    "$SCRIPT" ${ARGS:-}
