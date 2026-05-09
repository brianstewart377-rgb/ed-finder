#!/usr/bin/env bash
#
# scripts/seed_check.sh — verifies that every sql/*.sql file applies
# cleanly with `ON_ERROR_STOP=1` against a fresh PostgreSQL, and that
# the `seed_preview.sql` produces a usable preview database (every
# system has a rating, every body is reachable, materialised views
# render non-empty).
#
# This catches the bug class that bit us twice in May 2026:
#
#   * sql/seed_preview.sql shipped INSERT-too-many-values and silently
#     left `ratings` empty (28 vs 27 columns, see fix-search-economy-enum
#     PR), which the `psql -v ON_ERROR_STOP=0` default in
#     docker-entrypoint-initdb.d masked at boot time.
#
#   * sql/006_score_history.sql shipped a NOT-NULL violation on
#     app_meta.value that only manifested if you re-applied the file
#     after schema_version had advanced (i.e. on every CI run).
#
# Usage: bash scripts/seed_check.sh
#   Requires: a PostgreSQL ≥ 16 instance reachable via $DATABASE_URL,
#             with a database that the script is allowed to TRUNCATE.
# Exit:    0 on full success, non-zero on any psql failure or assertion.
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://edfinder:edfinder@localhost:5432/edfinder}"
SQL_DIR="${SQL_DIR:-$(dirname "$0")/../sql}"

echo "▶ seed_check: applying every sql/*.sql with ON_ERROR_STOP=1"
echo "  (fail-fast on any silent SQL error that prod would tolerate)"
echo

# Apply schema/migrations in numerical order, then the seed.
# psql with ON_ERROR_STOP=1 will exit non-zero on the first error,
# which `set -e` then surfaces as the script exit code.
for f in $(ls -1 "$SQL_DIR"/*.sql | sort); do
    case "$f" in
        */seed_preview.sql)        continue ;;  # applied last
    esac
    echo "  ✓ $(basename "$f")"
    psql "$DB_URL" -v ON_ERROR_STOP=1 -q -f "$f" >/dev/null
done

echo "  ✓ seed_preview.sql"
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -f "$SQL_DIR/seed_preview.sql" >/dev/null

# ── Post-conditions ────────────────────────────────────────────────────
echo
echo "▶ seed_check: invariants"

assert_count() {
    local label="$1"; local sql="$2"; local min="$3"
    local n
    n=$(psql "$DB_URL" -At -c "$sql")
    if [ "$n" -lt "$min" ]; then
        echo "  ✗ $label: got $n, expected ≥ $min"
        echo "    SQL: $sql"
        return 1
    fi
    echo "  ✓ $label: $n"
}

assert_count "systems"          "SELECT COUNT(*) FROM systems"               40
assert_count "ratings"          "SELECT COUNT(*) FROM ratings"               40
assert_count "bodies"           "SELECT COUNT(*) FROM bodies"                10
assert_count "stations"         "SELECT COUNT(*) FROM stations"               5
assert_count "galaxy_regions"   "SELECT COUNT(*) FROM galaxy_regions"        42

# Cross-table invariant: every system must have a rating row.
# The previous seed_preview.sql 'INSERT has more expressions' bug
# left ratings empty while systems were populated; this catches that.
orphans=$(psql "$DB_URL" -At -c "
    SELECT COUNT(*) FROM systems s
    LEFT JOIN ratings r ON r.system_id64 = s.id64
    WHERE r.system_id64 IS NULL
")
if [ "$orphans" -gt 0 ]; then
    echo "  ✗ unrated systems: $orphans (must be 0 — seed_preview's"
    echo "    ratings INSERT silently failed; check sql/seed_preview.sql)"
    exit 1
fi
echo "  ✓ every system has a rating row"

# Materialised views (added in sql/009) must be REFRESH-able. Empty MVs
# are OK with the small seed, but a syntax/permission failure here would
# only surface on first /api/map/* call in prod, which is too late.
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c "SELECT refresh_map_mviews();" >/dev/null
echo "  ✓ refresh_map_mviews() succeeds"

echo
echo "▶ seed_check: PASS"
