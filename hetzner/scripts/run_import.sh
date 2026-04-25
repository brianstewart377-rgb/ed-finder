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
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Determine the install dir (.env location) — setup.sh puts it in /opt/ed-finder
# If running from the repo directly, fall back to the compose dir
if [[ -f "/opt/ed-finder/.env" ]]; then
    ENV_FILE="/opt/ed-finder/.env"
elif [[ -f "$COMPOSE_DIR/.env" ]]; then
    ENV_FILE="$COMPOSE_DIR/.env"
else
    echo "[ERROR] .env not found at /opt/ed-finder/.env or $COMPOSE_DIR/.env"
    echo "        Create it with: echo 'POSTGRES_PASSWORD=yourpassword' > /opt/ed-finder/.env"
    exit 1
fi

# Export env vars so docker compose picks them up
set -a
source "$ENV_FILE"
set +a

cd "$COMPOSE_DIR"

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
echo " Compose: $COMPOSE_DIR"
echo " Env    : $ENV_FILE"
echo " Network: ed-finder_default (via docker compose)"
echo "=============================================="

# Use docker compose run — always gets the right network and DNS
docker compose --profile import run --rm \
    -e LOG_FILE="/data/logs/${SCRIPT%.py}.log" \
    importer \
    python3 "$SCRIPT" $ARGS
