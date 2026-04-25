#!/bin/bash
# =============================================================================
# ED Finder — Orphan Cleanup Utility  (v1.0)
# =============================================================================
# Removes leftover containers, stopped importer containers, and detached
# screen sessions that accumulate after interrupted import/build runs.
#
# The problem:
#   docker compose run --rm is supposed to remove the container when it exits.
#   But if the container is killed (SIGKILL), OOM-killed, or the Docker daemon
#   crashes, the --rm flag never fires and the container is left in "Exited"
#   state.  These orphans:
#     - Block the next run if they share a container_name (ed-importer)
#     - Consume disk space (container layers + logs)
#     - Clutter `docker ps -a` output
#
#   Similarly, if you ran imports inside `screen` sessions and they crashed,
#   dead screen sessions accumulate.
#
# Usage:
#   bash scripts/cleanup.sh           # interactive — asks before removing
#   bash scripts/cleanup.sh --force   # non-interactive — removes without asking
#   bash scripts/cleanup.sh --dry-run # show what would be removed, do nothing
# =============================================================================
set -euo pipefail

FORCE=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --force)   FORCE=true ;;
        --dry-run) DRY_RUN=true ;;
    esac
done

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
dry()  { echo -e "${YELLOW}[DRY-RUN]${NC} Would remove: $*"; }

confirm() {
    # $1 = prompt text
    if [[ "$FORCE" == true ]]; then return 0; fi
    if [[ "$DRY_RUN" == true ]]; then return 1; fi
    read -rp "$1 [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

echo ""
echo "════════════════════════════════════════════════"
echo "  ED Finder — Orphan Cleanup"
if [[ "$DRY_RUN" == true ]]; then
    echo "  Mode: DRY RUN (nothing will be removed)"
elif [[ "$FORCE" == true ]]; then
    echo "  Mode: FORCE (no confirmation prompts)"
fi
echo "════════════════════════════════════════════════"
echo ""

REMOVED=0

# ── 1. Stopped / exited importer containers ──────────────────────────────────
log "Checking for stopped importer containers ..."
STOPPED_IMPORTERS=$(docker ps -a --filter "name=ed-importer" --filter "status=exited" \
    --format "{{.ID}} {{.Names}} (exited {{.Status}})" 2>/dev/null || true)

if [[ -z "$STOPPED_IMPORTERS" ]]; then
    ok "No stopped importer containers found."
else
    echo "$STOPPED_IMPORTERS" | while read -r line; do
        warn "Stopped importer: $line"
    done
    if [[ "$DRY_RUN" == true ]]; then
        echo "$STOPPED_IMPORTERS" | while read -r id rest; do dry "container $id ($rest)"; done
    elif confirm "Remove all stopped importer containers?"; then
        docker ps -a --filter "name=ed-importer" --filter "status=exited" -q \
            | xargs -r docker rm -f
        ok "Stopped importer containers removed."
        REMOVED=$((REMOVED + 1))
    fi
fi

# ── 2. Any other exited ed-finder containers (not the core stack) ─────────────
log "Checking for other exited ed-* containers ..."
OTHER_EXITED=$(docker ps -a \
    --filter "name=ed-" \
    --filter "status=exited" \
    --format "{{.ID}} {{.Names}} ({{.Status}})" 2>/dev/null \
    | grep -v "ed-postgres\|ed-pgbouncer\|ed-redis\|ed-api\|ed-eddn\|ed-nginx" \
    || true)

if [[ -z "$OTHER_EXITED" ]]; then
    ok "No other exited ed-* containers found."
else
    echo "$OTHER_EXITED" | while read -r line; do warn "Exited container: $line"; done
    if [[ "$DRY_RUN" == true ]]; then
        echo "$OTHER_EXITED" | while read -r id rest; do dry "container $id ($rest)"; done
    elif confirm "Remove these exited containers?"; then
        echo "$OTHER_EXITED" | awk '{print $1}' | xargs -r docker rm -f
        ok "Exited containers removed."
        REMOVED=$((REMOVED + 1))
    fi
fi

# ── 3. Dangling docker volumes from old importer runs ────────────────────────
log "Checking for dangling (unused) Docker volumes ..."
DANGLING_VOLS=$(docker volume ls -qf dangling=true 2>/dev/null || true)
if [[ -z "$DANGLING_VOLS" ]]; then
    ok "No dangling volumes found."
else
    COUNT=$(echo "$DANGLING_VOLS" | wc -l)
    warn "$COUNT dangling volume(s) found."
    if [[ "$DRY_RUN" == true ]]; then
        dry "$COUNT dangling volumes"
    elif confirm "Remove $COUNT dangling volume(s)? (These are NOT the postgres_data or redis_data volumes)"; then
        echo "$DANGLING_VOLS" | xargs -r docker volume rm
        ok "Dangling volumes removed."
        REMOVED=$((REMOVED + 1))
    fi
fi

# ── 4. Dead / detached screen sessions ───────────────────────────────────────
log "Checking for dead or detached screen sessions ..."
if ! command -v screen &>/dev/null; then
    log "screen not installed — skipping."
else
    # Wipe dead sessions first (screen -wipe is non-destructive for live ones)
    screen -wipe &>/dev/null || true

    SCREEN_SESSIONS=$(screen -ls 2>/dev/null | grep -E "Detached|Dead" || true)
    if [[ -z "$SCREEN_SESSIONS" ]]; then
        ok "No dead or detached screen sessions found."
    else
        echo "$SCREEN_SESSIONS" | while read -r line; do warn "Screen session: $line"; done
        if [[ "$DRY_RUN" == true ]]; then
            dry "screen sessions listed above"
        elif confirm "Quit all detached/dead screen sessions?"; then
            # Extract session names (format: NNN.name (Detached))
            echo "$SCREEN_SESSIONS" | awk '{print $1}' | while read -r sess; do
                screen -S "$sess" -X quit 2>/dev/null || true
            done
            screen -wipe &>/dev/null || true
            ok "Screen sessions cleaned up."
            REMOVED=$((REMOVED + 1))
        fi
    fi
fi

# ── 5. Docker build cache (optional, large savings) ──────────────────────────
log "Checking Docker build cache size ..."
CACHE_SIZE=$(docker system df --format "{{.Size}}" 2>/dev/null | tail -1 || echo "unknown")
warn "Docker build cache: $CACHE_SIZE"
if [[ "$DRY_RUN" == true ]]; then
    dry "docker build cache ($CACHE_SIZE)"
elif confirm "Prune Docker build cache? (Frees disk space — images/containers are NOT affected)"; then
    docker builder prune -f
    ok "Docker build cache pruned."
    REMOVED=$((REMOVED + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
if [[ "$DRY_RUN" == true ]]; then
    echo "  DRY RUN complete — nothing was removed."
    echo "  Re-run without --dry-run to apply changes."
elif [[ "$REMOVED" -gt 0 ]]; then
    echo -e "  ${GREEN}✓ Cleanup complete — $REMOVED category(ies) cleaned.${NC}"
else
    echo -e "  ${GREEN}✓ Nothing to clean — stack is already tidy.${NC}"
fi
echo "════════════════════════════════════════════════"
echo ""
