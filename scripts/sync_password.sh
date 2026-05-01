#!/bin/bash
# =============================================================================
# ED Finder — Password Sync Utility  (v1.0)
# =============================================================================
# Fixes the "password authentication failed for user edfinder" error.
#
# The problem:
#   PostgreSQL stores the password hash in its pg_authid table.
#   pgBouncer caches the hash in memory.
#   The .env file holds the plaintext password.
#
#   If ANY of these three get out of sync — e.g. after:
#     - Recreating the postgres container
#     - Changing POSTGRES_PASSWORD in .env
#     - Restoring from a pg_dump that had a different password hash
#     - pgBouncer container restart with stale cached credentials
#
#   ...you get "password authentication failed" even though the containers
#   are running and healthy.
#
# This script fixes all three in the correct order:
#   1. Reads the password from .env (the single source of truth)
#   2. Updates PostgreSQL's pg_authid hash via ALTER USER
#   3. Restarts pgBouncer so it reloads the new hash from postgres
#   4. Verifies the connection works end-to-end
#
# Usage:
#   bash scripts/sync_password.sh
#   bash scripts/sync_password.sh --verify-only   # just test, don't change anything
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VERIFY_ONLY=false
if [[ "${1:-}" == "--verify-only" ]]; then
    VERIFY_ONLY=true
fi

# ── Locate .env ──────────────────────────────────────────────────────────────
if [[ -f "$REPO_ROOT/.env" ]]; then
    ENV_FILE="$REPO_ROOT/.env"
elif [[ -f "/opt/ed-finder/.env" ]]; then
    ENV_FILE="/opt/ed-finder/.env"
else
    echo "[ERROR] .env not found. Create it with:"
    echo "        echo 'POSTGRES_PASSWORD=yourpassword' > $REPO_ROOT/.env"
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    echo "[ERROR] POSTGRES_PASSWORD is not set in $ENV_FILE"
    exit 1
fi

echo "=============================================="
echo " ED Finder — Password Sync"
echo " .env file : $ENV_FILE"
echo " Password  : ${POSTGRES_PASSWORD:0:3}****** (first 3 chars shown)"
echo "=============================================="

# ── Step 1: Check postgres container is running ──────────────────────────────
if ! docker inspect ed-postgres &>/dev/null; then
    echo "[ERROR] Container ed-postgres is not running."
    echo "        Start the stack first: cd /opt/ed-finder && docker compose up -d"
    exit 1
fi

# ── Step 2: Verify current connection ────────────────────────────────────────
echo ""
echo "[INFO] Testing current connection ..."
if docker exec -i ed-postgres psql \
        "postgresql://edfinder:${POSTGRES_PASSWORD}@localhost:5432/edfinder" \
        -c "SELECT 1;" &>/dev/null; then
    echo "[OK]   Connection works — password is already in sync."
    if [[ "$VERIFY_ONLY" == true ]]; then
        echo "[INFO] --verify-only: nothing changed."
        exit 0
    fi
    echo "[INFO] Proceeding to also restart pgBouncer to clear any cached stale state ..."
    NEEDS_PG_FIX=false
else
    echo "[WARN] Connection FAILED with current .env password."
    if [[ "$VERIFY_ONLY" == true ]]; then
        echo "[ERROR] --verify-only: password is out of sync. Run without --verify-only to fix."
        exit 1
    fi
    NEEDS_PG_FIX=true
fi

# ── Step 3: Update PostgreSQL password hash ───────────────────────────────────
if [[ "$NEEDS_PG_FIX" == true ]]; then
    echo ""
    echo "[INFO] Updating PostgreSQL password hash via ALTER USER ..."
    # Connect as the superuser (postgres) to change the edfinder user's password.
    # We use the POSTGRES_USER=edfinder from compose, so we try both users.
    if docker exec -i ed-postgres psql -U edfinder -d edfinder \
            -c "ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';" 2>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (connected as edfinder)."
    elif docker exec -i ed-postgres psql -U postgres -d postgres \
            -c "ALTER USER edfinder WITH PASSWORD '${POSTGRES_PASSWORD}';" 2>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (connected as postgres superuser)."
    else
        echo "[ERROR] Could not update password in PostgreSQL."
        echo "        The postgres container may need to be recreated:"
        echo "          docker compose stop postgres"
        echo "          docker compose up -d postgres"
        exit 1
    fi
fi

# ── Step 4: Restart pgBouncer to reload credentials ──────────────────────────
echo ""
echo "[INFO] Restarting pgBouncer to reload credentials ..."
if docker inspect ed-pgbouncer &>/dev/null; then
    docker restart ed-pgbouncer
    echo "[OK]   pgBouncer restarted."
    sleep 3   # give pgBouncer a moment to reconnect
else
    echo "[WARN] Container ed-pgbouncer not found — skipping pgBouncer restart."
fi

# ── Step 5: Final verification ────────────────────────────────────────────────
echo ""
echo "[INFO] Verifying connection after sync ..."
if docker exec -i ed-postgres psql \
        "postgresql://edfinder:${POSTGRES_PASSWORD}@localhost:5432/edfinder" \
        -c "SELECT 'password sync OK' AS result;" 2>/dev/null; then
    echo ""
    echo "[OK]   ✓ Password sync complete — all connections verified."
else
    echo ""
    echo "[ERROR] Connection still failing after sync."
    echo "        Try recreating the postgres container (DATA IS PRESERVED in the volume):"
    echo "          cd /opt/ed-finder"
    echo "          docker compose stop postgres pgbouncer"
    echo "          docker compose up -d postgres pgbouncer"
    echo "          bash scripts/sync_password.sh"
    exit 1
fi
