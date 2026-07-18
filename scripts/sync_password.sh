#!/bin/bash
# =============================================================================
# ED Finder — Password Sync Utility  (v1.2)
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
# CHANGES in v1.2:
#   - Passwords no longer appear in process arguments, SQL text, or output.
#   - Connection checks use a short-lived in-container passfile supplied over
#     stdin; password updates use psql's quoting-safe \password command.
#
# CHANGES in v1.1:
#   - Removed the hardcoded /opt/ed-finder/.env fallback. The .env is now
#     always expected in the repo root (one level up from scripts/).
#     This matches the simplified single-directory deployment model.
#
# Usage:
#   bash scripts/sync_password.sh
#   bash scripts/sync_password.sh --verify-only   # just test, don't change anything
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ed-postgres}"
PGBOUNCER_CONTAINER="${PGBOUNCER_CONTAINER:-ed-pgbouncer}"

VERIFY_ONLY=false
if [[ "${1:-}" == "--verify-only" ]]; then
    VERIFY_ONLY=true
fi

# ── Locate .env ──────────────────────────────────────────────────────────────
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[ERROR] .env not found at $ENV_FILE. Create it with:"
    echo "        echo 'POSTGRES_PASSWORD=yourpassword' > $ENV_FILE"
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
echo " Password  : [redacted]"
echo "=============================================="

pgpass_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/:/\\:/g'
}

verify_connection() {
    local escaped_password
    escaped_password="$(pgpass_escape "$POSTGRES_PASSWORD")"
    printf '%s\n' "$escaped_password" |
        docker exec -i "$POSTGRES_CONTAINER" sh -ceu '
            umask 077
            passfile="$(mktemp)"
            trap "rm -f \"$passfile\"" EXIT HUP INT TERM
            IFS= read -r escaped_password
            set -- $(hostname -i)
            database_host="${1:-}"
            [ -n "$database_host" ]
            printf "%s:5432:edfinder:edfinder:%s\n" \
                "$database_host" "$escaped_password" > "$passfile"
            PGPASSFILE="$passfile" psql -X -w \
                -h "$database_host" -p 5432 -U edfinder -d edfinder \
                -v ON_ERROR_STOP=1 -c "SELECT 1;"
        '
}

update_password_as() {
    local admin_user="$1"
    local admin_database="$2"
    printf '%s\n%s\n' "$POSTGRES_PASSWORD" "$POSTGRES_PASSWORD" |
        docker exec -i "$POSTGRES_CONTAINER" psql -X -v ON_ERROR_STOP=1 \
            -U "$admin_user" -d "$admin_database" -c '\password edfinder'
}

# ── Step 1: Check postgres container is running ──────────────────────────────
if ! docker inspect "$POSTGRES_CONTAINER" &>/dev/null; then
    echo "[ERROR] Container $POSTGRES_CONTAINER is not running."
    echo "        Start the stack first: cd $INSTALL_DIR && docker compose up -d"
    exit 1
fi

# ── Step 2: Verify current connection ────────────────────────────────────────
echo ""
echo "[INFO] Testing current connection ..."
if verify_connection &>/dev/null; then
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
    # The official image permits a local socket connection for its configured
    # role. Try that role first, then the conventional postgres superuser.
    if update_password_as edfinder edfinder 2>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (connected as edfinder)."
    elif update_password_as postgres postgres 2>/dev/null; then
        echo "[OK]   Password updated in PostgreSQL (connected as postgres superuser)."
    else
        echo "[ERROR] Could not update password in PostgreSQL."
        echo "        The postgres container may need to be recreated:"
        echo "          cd $INSTALL_DIR"
        echo "          docker compose stop postgres"
        echo "          docker compose up -d postgres"
        exit 1
    fi
fi

# ── Step 4: Restart pgBouncer to reload credentials ──────────────────────────
echo ""
echo "[INFO] Restarting pgBouncer to reload credentials ..."
if docker inspect "$PGBOUNCER_CONTAINER" &>/dev/null; then
    docker restart "$PGBOUNCER_CONTAINER"
    echo "[OK]   pgBouncer restarted."
    sleep 3   # give pgBouncer a moment to reconnect
else
    echo "[WARN] Container $PGBOUNCER_CONTAINER not found — skipping pgBouncer restart."
fi

# ── Step 5: Final verification ────────────────────────────────────────────────
echo ""
echo "[INFO] Verifying connection after sync ..."
if verify_connection 2>/dev/null; then
    echo ""
    echo "[OK]   ✓ Password sync complete — all connections verified."
else
    echo ""
    echo "[ERROR] Connection still failing after sync."
    echo "        Try recreating the postgres container (DATA IS PRESERVED in the volume):"
    echo "          cd $INSTALL_DIR"
    echo "          docker compose stop postgres pgbouncer"
    echo "          docker compose up -d postgres pgbouncer"
    echo "          bash $INSTALL_DIR/scripts/sync_password.sh"
    exit 1
fi
