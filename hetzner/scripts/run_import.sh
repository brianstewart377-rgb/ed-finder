#!/bin/bash
# =============================================================================
# ED Finder — Import Runner  (v1.3)
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
# FIXES in v1.3:
#   - Orphaned importer containers (ed-importer in Exited state) are removed
#     automatically before every run, so they never block the next execution.
#   - Password sync now also restarts pgBouncer when a mismatch is detected,
#     so both Postgres and pgBouncer are always in sync with .env.
#   - Password sync tries both 'edfinder' and 'postgres' superuser if the
#     first attempt fails (handles the case where the password is so wrong
#     that even the ALTER USER connection fails).
#   - Clear error message if ed-postgres container is not running at all.
#
# FIXES in v1.2:
#   - INSTALL_DIR is now auto-detected as the directory containing
#     docker-compose.yml, rather than being hard-coded to /opt/ed-finder.
#     Fixes "no configuration file provided: not found" error.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HETZNER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Auto-detect install dir ──────────────────────────────────────────────────
# The install dir is the directory that contains docker-compose.yml.
# Priority order:
#   1. The hetzner/ directory of the repo itself (repo cloned in place)
#   2. /opt/ed-finder/hetzner  (legacy separate-install layout)
#   3. /opt/ed-finder           (old single-dir layout)
# Override: INSTALL_DIR=/my/path ./scripts/run_import.sh
if [[ -z "${INSTALL_DIR:-}" ]]; then
    if [[ -f "$REPO_HETZNER_DIR/docker-compose.yml" ]]; then
        INSTALL_DIR="$REPO_HETZNER_DIR"
    elif [[ -f "/opt/ed-finder/hetzner/docker-compose.yml" ]]; then
        INSTALL_DIR="/opt/ed-finder/hetzner"
    elif [[ -f "/opt/ed-finder/docker-compose.yml" ]]; then
        INSTALL_DIR="/opt/ed-finder"
    else
        echo "[ERROR] Cannot find docker-compose.yml — tried:"
        echo "        $REPO_HETZNER_DIR/docker-compose.yml"
        echo "        /opt/ed-finder/hetzner/docker-compose.yml"
        echo "        /opt/ed-finder/docker-compose.yml"
        echo ""
        echo "        Set INSTALL_DIR=/path/to/dir/containing/docker-compose.yml"
        exit 1
    fi
fi

echo "[INFO] Install dir : $INSTALL_DIR"
echo "[INFO] Repo hetzner: $REPO_HETZNER_DIR"

# ── Sync latest backend scripts from repo into install dir ──────────────────
if [[ "$INSTALL_DIR" != "$REPO_HETZNER_DIR" ]]; then
    echo "[INFO] Syncing scripts from repo to install dir ..."
    mkdir -p "$INSTALL_DIR/backend"
    cp "$REPO_HETZNER_DIR/backend/import_spansh.py"  "$INSTALL_DIR/backend/import_spansh.py"
    cp "$REPO_HETZNER_DIR/backend/progress.py"       "$INSTALL_DIR/backend/progress.py"
    cp "$REPO_HETZNER_DIR/backend/build_grid.py"     "$INSTALL_DIR/backend/build_grid.py"
    cp "$REPO_HETZNER_DIR/backend/build_ratings.py"  "$INSTALL_DIR/backend/build_ratings.py"
    cp "$REPO_HETZNER_DIR/backend/build_clusters.py" "$INSTALL_DIR/backend/build_clusters.py"
    echo "[INFO] Scripts synced."
else
    echo "[INFO] Install dir is the repo — no sync needed."
fi

# ── Locate .env ──────────────────────────────────────────────────────────────
if [[ -f "$INSTALL_DIR/.env" ]]; then
    ENV_FILE="$INSTALL_DIR/.env"
elif [[ -f "$REPO_HETZNER_DIR/.env" ]]; then
    ENV_FILE="$REPO_HETZNER_DIR/.env"
else
    echo "[ERROR] .env not found. Create it with:"
    echo "        echo 'POSTGRES_PASSWORD=yourpassword' > $INSTALL_DIR/.env"
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
    echo "        Start the stack first: docker compose up -d"
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
        echo "        Run:  bash scripts/sync_password.sh"
        echo "        Or recreate the container:"
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
        echo "        Run:  bash scripts/sync_password.sh"
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
echo " ED Finder Import Runner v1.3"
echo " Script : $SCRIPT ${ARGS:-}"
echo " Compose: $INSTALL_DIR"
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
