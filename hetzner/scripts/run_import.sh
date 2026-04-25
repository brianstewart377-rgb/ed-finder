#!/bin/bash
# =============================================================================
# ED Finder — Import Runner
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
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HETZNER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# The stack always runs from /opt/ed-finder (the install dir created by setup.sh).
# Running docker compose from a different directory creates a different project name
# which causes network conflicts. Always use the install dir.
INSTALL_DIR="/opt/ed-finder"

if [[ ! -d "$INSTALL_DIR" ]]; then
    echo "[ERROR] Install dir $INSTALL_DIR not found — has setup.sh been run?"
    exit 1
fi

# Sync latest scripts from repo into install dir so compose picks them up
echo "[INFO] Syncing scripts from repo to install dir ..."
cp "$REPO_HETZNER_DIR/backend/import_spansh.py" "$INSTALL_DIR/backend/import_spansh.py"
cp "$REPO_HETZNER_DIR/backend/progress.py"      "$INSTALL_DIR/backend/progress.py"
cp "$REPO_HETZNER_DIR/backend/build_grid.py"    "$INSTALL_DIR/backend/build_grid.py"
cp "$REPO_HETZNER_DIR/backend/build_ratings.py" "$INSTALL_DIR/backend/build_ratings.py"
cp "$REPO_HETZNER_DIR/backend/build_clusters.py" "$INSTALL_DIR/backend/build_clusters.py"

# Determine .env location
if [[ -f "$INSTALL_DIR/.env" ]]; then
    ENV_FILE="$INSTALL_DIR/.env"
elif [[ -f "$REPO_HETZNER_DIR/.env" ]]; then
    ENV_FILE="$REPO_HETZNER_DIR/.env"
else
    echo "[ERROR] .env not found at $INSTALL_DIR/.env"
    echo "        Create it with: echo 'POSTGRES_PASSWORD=yourpassword' > $INSTALL_DIR/.env"
    exit 1
fi

# Export env vars so docker compose picks them up
set -a
source "$ENV_FILE"
set +a

# Always run compose from the install dir so the project name matches the
# running stack (project name = ed-finder, network = ed-finder_default)
cd "$INSTALL_DIR"

# Determine what to run
if [[ $# -eq 0 ]]; then
    # No args — show status
    SCRIPT="import_spansh.py"
    ARGS="--status"
elif [[ "$1" == build_*.py ]]; then
    # Running a build script (grid/ratings/clusters)
    SCRIPT="$1"
    shift
    ARGS="${*:-}"
else
    # Passing args to import_spansh.py
    SCRIPT="import_spansh.py"
    ARGS="$*"
fi

echo "=============================================="
echo " ED Finder Import Runner"
echo " Script : $SCRIPT $ARGS"
echo " Compose: $INSTALL_DIR"
echo " Env    : $ENV_FILE"
echo " Network: ed-finder_default (via docker compose)"
echo "=============================================="

# Use docker compose run — always gets the right network and DNS
docker compose --profile import run --rm \
    -e LOG_FILE="/data/logs/${SCRIPT%.py}.log" \
    importer \
    python3 "$SCRIPT" $ARGS
