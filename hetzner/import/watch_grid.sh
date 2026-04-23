#!/bin/bash
# =============================================================================
# ED Finder — Grid Build Progress Monitor
# Run this in a second terminal while build_grid.py is running.
#
# Usage:
#   chmod +x watch_grid.sh
#   ./watch_grid.sh            # auto-detects docker container
#   ./watch_grid.sh 5          # poll every 5 seconds (default: 10)
#
# What it shows:
#   • Phase and row progress from pg_stat_progress_update (during active UPDATE)
#   • Assigned / unassigned counts from the systems table
#   • Estimated time remaining
#   • Log tail from /data/logs/build_grid.log
# =============================================================================
set -euo pipefail

INTERVAL="${1:-10}"   # seconds between polls
LOG_FILE="/data/logs/build_grid.log"
CONTAINER="ed-postgres"
DB_USER="edfinder"
DB_NAME="edfinder"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'  # No Colour

psql_q() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "$1" 2>/dev/null || echo "ERROR"
}

header() {
    printf "\n${CYAN}══════════════════════════════════════════════════════════════${NC}\n"
    printf "${CYAN}  ED Finder — Grid Build Monitor   (refresh every ${INTERVAL}s)${NC}\n"
    printf "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S')${NC}\n"
    printf "${CYAN}══════════════════════════════════════════════════════════════${NC}\n\n"
}

show_update_progress() {
    local result
    result=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc "
        SELECT
            phase,
            tuples_done,
            tuples_total,
            CASE WHEN tuples_total > 0
                 THEN ROUND(tuples_done * 100.0 / tuples_total, 2)
                 ELSE 0
            END AS pct_done,
            heap_blks_scanned,
            heap_blks_total
        FROM pg_stat_progress_update
        WHERE relid = 'systems'::regclass
        LIMIT 1
    " 2>/dev/null)

    if [[ -z "$result" || "$result" == "" ]]; then
        printf "${YELLOW}  pg_stat_progress_update: no active UPDATE on systems table${NC}\n"
        printf "  (UPDATE may be done, or script hasn't reached Stage 3 yet)\n"
    else
        IFS='|' read -r phase done total pct blks_scanned blks_total <<< "$result"
        printf "${GREEN}  pg_stat_progress_update:${NC}\n"
        printf "    Phase        : %s\n" "$phase"
        printf "    Tuples done  : %s / %s  (%s%%)\n" \
            "$(printf '%d' "${done:-0}" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta')" \
            "$(printf '%d' "${total:-0}" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta')" \
            "${pct:-0}"
        if [[ -n "$blks_total" && "$blks_total" -gt 0 ]]; then
            local blk_pct
            blk_pct=$(echo "scale=1; ${blks_scanned:-0} * 100 / $blks_total" | bc 2>/dev/null || echo "?")
            printf "    Heap blocks  : %s / %s  (%s%%)\n" \
                "${blks_scanned:-0}" "${blks_total:-0}" "$blk_pct"
        fi
    fi
}

show_system_counts() {
    local assigned unassigned total
    assigned=$(psql_q "SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NOT NULL")
    unassigned=$(psql_q "SELECT COUNT(*) FROM systems WHERE grid_cell_id IS NULL")
    total=$(psql_q "SELECT COUNT(*) FROM systems")

    printf "\n${GREEN}  systems table (live counts):${NC}\n"
    printf "    Total systems   : %s\n" \
        "$(echo "$total" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta' 2>/dev/null || echo "$total")"
    printf "    Assigned        : %s\n" \
        "$(echo "$assigned" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta' 2>/dev/null || echo "$assigned")"
    printf "    ${RED}Unassigned (NULL)${NC}: %s  ← this should reach 0\n" \
        "$(echo "$unassigned" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta' 2>/dev/null || echo "$unassigned")"

    if [[ "$unassigned" == "0" ]]; then
        printf "\n    ${GREEN}✓ All systems assigned! Stage 3 complete.${NC}\n"
    fi
}

show_spatial_grid() {
    local cells
    cells=$(psql_q "SELECT COUNT(*) FROM spatial_grid")
    printf "\n${GREEN}  spatial_grid:${NC}\n"
    printf "    Cells           : %s\n" \
        "$(echo "$cells" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta' 2>/dev/null || echo "$cells")"
}

show_log_tail() {
    if [[ -f "$LOG_FILE" ]]; then
        printf "\n${CYAN}  Last 10 lines from %s:${NC}\n" "$LOG_FILE"
        printf "  %s\n" "$(tail -10 "$LOG_FILE" | sed 's/^/  /')"
    else
        printf "\n${YELLOW}  Log file not found: %s${NC}\n" "$LOG_FILE"
        printf "  (Check build_grid.py is running and LOG_FILE env var is set)\n"
    fi
}

# Main loop
echo ""
echo "  Watching grid build progress (Ctrl+C to stop)"
echo "  Container : $CONTAINER"
echo "  Interval  : ${INTERVAL}s"
echo ""

while true; do
    clear
    header
    show_update_progress
    show_system_counts
    show_spatial_grid
    show_log_tail

    printf "\n  Next refresh in ${INTERVAL}s ... (Ctrl+C to stop)\n"
    sleep "$INTERVAL"
done
