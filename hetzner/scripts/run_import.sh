#!/bin/bash
# =============================================================================
# ED Finder — Import Runner  (v1.2)
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
# FIX in v1.2:
#   INSTALL_DIR is now auto-detected as the hetzner/ subdirectory of the repo
#   (i.e. the directory containing docker-compose.yml), rather than being
#   hard-coded to /opt/ed-finder.  This fixes the "no configuration file
#   provided: not found" error when the repo is cloned directly into
#   /opt/ed-finder/hetzner (or any other path).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# hetzner/ is the parent of scripts/
REPO_HETZNER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Auto-detect install dir ──────────────────────────────────────────────────
# The install dir is the directory that contains docker-compose.yml.
# We look in the following order:
#   1. The hetzner/ directory of the repo itself (most common — repo cloned in place)
#   2. /opt/ed-finder/hetzner  (legacy separate-install layout)
#   3. /opt/ed-finder           (old single-dir layout)
#
# You can override by setting INSTALL_DIR in the environment before calling
# this script:  INSTALL_DIR=/my/path ./scripts/run_import.sh
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
        echo "        and re-run this script."
        exit 1
    fi
fi

echo "[INFO] Install dir : $INSTALL_DIR"
echo "[INFO] Repo hetzner: $REPO_HETZNER_DIR"

# ── Sync latest backend scripts from repo into install dir ──────────────────
# If the install dir IS the repo hetzner dir, this is a no-op (same files).
# If it's a separate install, it copies the latest code across.
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

# Export env vars so docker compose picks them up
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# Always run compose from the install dir so the project name matches the
# running stack (project name = ed-finder, network = ed-finder_default)
cd "$INSTALL_DIR"

# ── Pre-flight: verify DB password is in sync ────────────────────────────────
echo "[INFO] Verifying DB password ..."
if ! docker exec -i ed-postgres psql \
        "postgresql://edfinder:${POSTGRES_PASSWORD}@localhost:5432/edfinder" \
        -c "SELECT 1;" &>/dev/null; then
    echo "[WARN] Password mismatch — resyncing PostgreSQL password from .env ..."
    docker exec -i ed-postgres psql -U edfinder -d edfinder \
        -c "ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';" \
        && echo "[OK]  Password resynced successfully." \
        || { echo "[ERROR] Could not resync password. Is ed-postgres running?"; exit 1; }
else
    echo "[OK]  DB connection verified."
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
echo " ED Finder Import Runner v1.2"
echo " Script : $SCRIPT ${ARGS:-}"
echo " Compose: $INSTALL_DIR"
echo " Env    : $ENV_FILE"
echo " Network: ed-finder_default (via docker compose)"
echo "=============================================="

# Use docker compose run — always gets the right network and DNS
docker compose --profile import run --rm \
    --entrypoint python3 \
    -e LOG_FILE="/data/logs/${SCRIPT%.py}.log" \
    importer \
    "$SCRIPT" ${ARGS:-}
