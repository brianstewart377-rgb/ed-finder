#!/bin/bash
# =============================================================================
# ED Finder — Hetzner Server Setup Script
# Version: 4.0
#
# Server:  Hetzner AX41-SSD (or equivalent)
#          i7-8700, 128 GB RAM, 3×1 TB NVMe RAID-5, Ubuntu 24.04
# Domain:  ed-finder.app (Cloudflare DNS → Hetzner IP)
# Stack:   PostgreSQL 16, pgBouncer, Redis 7, FastAPI, EDDN, Nginx
#
# Usage:
#   Fresh install:
#     git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder
#     cd /opt/ed-finder
#     sudo bash setup.sh
#
#   Update code and rebuild containers (PRESERVES DATABASE):
#     cd /opt/ed-finder
#     git pull origin main
#     sudo bash setup.sh --reinstall
#
#   Nuke everything including database (DESTROYS ALL DATA):
#     sudo bash setup.sh --nuke
#
# What --reinstall does:
#   • Pulls latest code from GitHub
#   • Removes Docker images (forces rebuild)
#   • Restarts all services
#   • KEEPS: PostgreSQL data volume, SSL certs, dump files, logs
#
# What --nuke does:
#   • Everything above PLUS drops the PostgreSQL data volume
#   • Requires explicit confirmation
#   • Use only if you want to re-import everything from scratch
#
# NOTE: v4.0 removes the old two-directory deployment model.
#       The repo is cloned directly to /opt/ed-finder and all
#       services run from there. /opt/ed-finder-src no longer exists.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Colours & helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}══ $* ══${NC}"; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
MODE="fresh"
for arg in "$@"; do
    case "$arg" in
        --reinstall) MODE="reinstall" ;;
        --nuke)      MODE="nuke" ;;
        --help|-h)
            echo "Usage: bash setup.sh [--reinstall|--nuke]"
            echo "  (no args)     Fresh install (run from /opt/ed-finder after cloning)"
            echo "  --reinstall   Pull latest code, rebuild containers, preserve DB data"
            echo "  --nuke        Destroy everything including DB (requires confirmation)"
            exit 0 ;;
    esac
done

# ---------------------------------------------------------------------------
# Must run as root
# ---------------------------------------------------------------------------
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup.sh"

# ---------------------------------------------------------------------------
# Config — single directory, no split between src and install
# ---------------------------------------------------------------------------
REPO_URL="https://github.com/brianstewart377-rgb/ed-finder.git"
INSTALL_DIR="/opt/ed-finder"
DATA_DIR="/data"
DOMAIN="ed-finder.app"

# ---------------------------------------------------------------------------
# Step 0 — Nuke / Reinstall handling
# ---------------------------------------------------------------------------
if [[ "$MODE" == "nuke" ]]; then
    step "NUKE MODE — destroys ALL data including database"
    echo -e "${RED}${BOLD}WARNING: This will permanently destroy the PostgreSQL database."
    echo -e "All imported data (186M systems, bodies, stations) will be deleted."
    echo -e "You will need to re-import everything from scratch (3-5 days).${NC}"
    echo ""
    read -r -p "Type 'NUKE IT' to confirm: " confirm
    [[ "$confirm" != "NUKE IT" ]] && error "Aborted."

    info "Stopping and removing all containers and volumes ..."
    cd "$INSTALL_DIR" 2>/dev/null && docker compose down -v --remove-orphans 2>/dev/null || true
    docker volume rm ed-finder_postgres_data ed-finder_redis_data 2>/dev/null || true
    docker volume rm $(docker volume ls -q | grep edfinder) 2>/dev/null || true
    docker image prune -f 2>/dev/null || true
    success "All containers and volumes removed"

elif [[ "$MODE" == "reinstall" ]]; then
    step "REINSTALL MODE — preserving database"
    info "Stopping containers (keeping postgres_data volume) ..."
    cd "$INSTALL_DIR" 2>/dev/null && docker compose down --remove-orphans 2>/dev/null || true
    info "Removing old images to force rebuild ..."
    docker images | grep 'ed-finder' | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || true
    success "Containers stopped, images removed. Database preserved."
fi

# ---------------------------------------------------------------------------
# Step 1 — System packages
# ---------------------------------------------------------------------------
step "1. System packages"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip htop iotop ncdu screen \
    ufw fail2ban \
    python3 python3-pip python3-venv \
    certbot aria2 \
    mdadm smartmontools
success "System packages installed"

# ---------------------------------------------------------------------------
# Step 2 — RAID-5 check
# ---------------------------------------------------------------------------
step "2. Storage check"
if command -v mdadm &>/dev/null; then
    if mdadm --detail /dev/md0 &>/dev/null 2>&1; then
        RAID_STATE=$(mdadm --detail /dev/md0 | grep 'State :' | awk '{print $3}')
        success "RAID-5 /dev/md0 state: $RAID_STATE"
        if [[ "$RAID_STATE" != "clean" ]]; then
            warn "RAID not clean — check: mdadm --detail /dev/md0"
        fi
    else
        warn "No /dev/md0 found — check RAID status manually: mdadm --detail --scan"
    fi
fi

DISK_FREE=$(df -BG /data 2>/dev/null | awk 'NR==2{print $4}' || echo "unknown")
info "Free space on /data: $DISK_FREE"

# ---------------------------------------------------------------------------
# Step 3 — Docker
# ---------------------------------------------------------------------------
step "3. Docker"
if ! command -v docker &>/dev/null; then
    info "Installing Docker ..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    success "Docker installed"
else
    success "Docker already installed: $(docker --version)"
fi

# ---------------------------------------------------------------------------
# Step 4 — Directory structure
# ---------------------------------------------------------------------------
step "4. Directories"
mkdir -p "$DATA_DIR"/{dumps,logs,backups}
mkdir -p /var/log/nginx
chown -R root:root "$DATA_DIR"
chmod -R 755 "$DATA_DIR"
success "Directories created"

# ---------------------------------------------------------------------------
# Step 5 — Clone / update repository (single directory)
# ---------------------------------------------------------------------------
step "5. Repository"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing repo at $INSTALL_DIR ..."
    git -C "$INSTALL_DIR" pull origin main
    success "Repo updated to $(git -C $INSTALL_DIR rev-parse --short HEAD)"
else
    if [[ -d "$INSTALL_DIR" ]] && [[ "$(ls -A $INSTALL_DIR 2>/dev/null)" ]]; then
        # Directory exists and is not empty but has no .git — likely a manual copy.
        # Back it up and do a clean clone.
        warn "$INSTALL_DIR exists but is not a git repo — backing up to ${INSTALL_DIR}.bak"
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak"
    fi
    info "Cloning repository to $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    success "Repo cloned to $INSTALL_DIR"
fi

# ---------------------------------------------------------------------------
# Step 6 — Mask system nginx/apache (would conflict with Docker nginx on :80/:443)
# ---------------------------------------------------------------------------
step "6. Port conflicts"
for svc in nginx apache2; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc"
        warn "Stopped system $svc"
    fi
    systemctl disable "$svc" 2>/dev/null || true
    systemctl mask "$svc" 2>/dev/null || true
done
ss -tlnp | grep -E ':80|:443' && warn "Something still on port 80/443 — check above" || success "Ports 80/443 are free"

# ---------------------------------------------------------------------------
# Step 7 — Environment file
# ---------------------------------------------------------------------------
step "7. Environment"
ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]] || [[ "$MODE" == "nuke" ]]; then
    if [[ -n "${POSTGRES_PASSWORD:-}" ]]; then
        PG_PASS="$POSTGRES_PASSWORD"
    else
        read -r -p "PostgreSQL password (leave blank to generate): " PG_PASS
        if [[ -z "$PG_PASS" ]]; then
            PG_PASS=$(openssl rand -base64 32 | tr -d '/+=\n' | cut -c1-32)
            info "Generated password: $PG_PASS"
            info "Save this — it won't be shown again."
        fi
    fi
    cat > "$ENV_FILE" <<EOF
POSTGRES_PASSWORD=${PG_PASS}
LOG_LEVEL=INFO
TTL_SEARCH=3600
TTL_SYSTEM=86400
TTL_CLUSTER=3600
EOF
    chmod 600 "$ENV_FILE"
    success ".env created at $ENV_FILE"
else
    success ".env already exists — keeping existing credentials"
fi

# ---------------------------------------------------------------------------
# Step 8 — UFW firewall
# ---------------------------------------------------------------------------
step "8. Firewall"
ufw --force enable
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw status
success "UFW configured"

# ---------------------------------------------------------------------------
# Step 9 — fail2ban
# ---------------------------------------------------------------------------
step "9. fail2ban"
systemctl enable fail2ban
systemctl start fail2ban
success "fail2ban active"

# ---------------------------------------------------------------------------
# Step 10 — SSL Certificate (before starting nginx container)
# ---------------------------------------------------------------------------
step "10. SSL Certificate"
if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    success "SSL certificate already exists — skipping"
else
    warn "No SSL certificate found."
    warn "Run certbot manually after DNS is pointed to this server:"
    warn "  certbot certonly --standalone -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m your@email.com"
    warn "Then: docker compose up -d nginx"
    warn "Continuing setup without SSL (nginx will start in HTTP-only mode) ..."
fi

# ---------------------------------------------------------------------------
# Step 11 — Build and start core services (postgres, redis, pgbouncer)
# ---------------------------------------------------------------------------
step "11. Start core services"
cd "$INSTALL_DIR"
docker compose build --no-cache 2>&1 | tail -5
docker compose up -d postgres redis
info "Waiting for PostgreSQL to be healthy ..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U edfinder -d edfinder &>/dev/null; then
        success "PostgreSQL is ready"
        break
    fi
    sleep 3
    [[ $i -eq 30 ]] && error "PostgreSQL did not become healthy after 90s"
done

# ---------------------------------------------------------------------------
# Step 12 — Fix PostgreSQL auth for pgBouncer (md5)
# ---------------------------------------------------------------------------
step "12. PostgreSQL auth fix"
# pgBouncer uses md5, PostgreSQL 16 defaults to scram-sha-256.
# We need to store the password as md5 and set hba to md5.
docker compose exec -T postgres psql -U edfinder -d edfinder -c "
    SET password_encryption = md5;
    ALTER USER edfinder WITH PASSWORD '$(grep POSTGRES_PASSWORD $ENV_FILE | cut -d= -f2)';
" || warn "md5 password set may have failed — check manually"

# Patch pg_hba.conf inside the container
PGDATA=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc "SHOW data_directory;" | tr -d '[:space:]')
docker compose exec -T postgres sed -i 's/scram-sha-256/md5/g' "${PGDATA}/pg_hba.conf" 2>/dev/null || true
docker compose exec -T postgres psql -U edfinder -d edfinder -c "SELECT pg_reload_conf();" &>/dev/null || true
success "PostgreSQL auth set to md5"

# ---------------------------------------------------------------------------
# Step 13 — Automated Index Rebuild
# ---------------------------------------------------------------------------
step "13. Rebuild indexes"
info "Checking if indexes need to be rebuilt ..."
INDEX_COUNT=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc "SELECT count(*) FROM pg_indexes WHERE tablename = 'systems' AND indexname NOT LIKE '%pkey%';")
if [[ "$INDEX_COUNT" -lt 5 ]]; then
    info "Found only $INDEX_COUNT indexes on 'systems'. Rebuilding all indexes from 002_indexes.sql ..."
    docker compose exec -T postgres psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql
    success "Indexes rebuilt successfully"
else
    success "Indexes already exist ($INDEX_COUNT found) — skipping rebuild"
fi

# ---------------------------------------------------------------------------
# Step 14 — Start remaining services
# ---------------------------------------------------------------------------
step "14. Start all services"
docker compose up -d
sleep 10
docker compose ps

# ---------------------------------------------------------------------------
# Step 15 — Health checks
# ---------------------------------------------------------------------------
step "15. Health checks"
sleep 15
API_HEALTH=$(curl -sf http://localhost:8000/api/health 2>/dev/null || echo '{"status":"unreachable"}')
info "API: $API_HEALTH"
HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "301" ]]; then
    success "nginx serving frontend (HTTP $HTTP_CODE)"
else
    warn "nginx returned HTTP $HTTP_CODE — may need SSL cert or container restart"
fi

# ---------------------------------------------------------------------------
# Step 16 — Nightly update cron
# ---------------------------------------------------------------------------
step "16. Nightly cron"
NIGHTLY_SCRIPT="$INSTALL_DIR/scripts/nightly_update.sh"
if [[ -f "$NIGHTLY_SCRIPT" ]]; then
    chmod +x "$NIGHTLY_SCRIPT"
    CRON_LINE="0 2 * * * $NIGHTLY_SCRIPT >> /data/logs/nightly.log 2>&1"
    (crontab -l 2>/dev/null | grep -v "nightly_update"; echo "$CRON_LINE") | crontab -
    success "Nightly cron set: $CRON_LINE"
else
    warn "nightly_update.sh not found — skipping cron"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Setup complete! Next steps:                                      ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║                                                                   ║"
echo "║  0. VERIFY SERVICES:                                             ║"
echo "║     docker compose ps                                            ║"
echo "║     curl http://localhost/api/health                             ║"
echo "║                                                                   ║"
echo "║  1. DOWNLOAD SPANSH DUMPS (~15-30 min on 1 Gbps):               ║"
echo "║                                                                   ║"
echo "║     screen -S import                                             ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       import_spansh.py --download-only                          ║"
echo "║     # Ctrl+A D to detach                                         ║"
echo "║                                                                   ║"
echo "║     Files (~110 GB total):                                       ║"
echo "║       galaxy.json.gz          ~102 GB  (all systems+bodies+sta)  ║"
echo "║       galaxy_populated.json.gz  ~3.6 GB (faction/economy)        ║"
echo "║       galaxy_stations.json.gz   ~3.6 GB (station refresh)        ║"
echo "║                                                                   ║"
echo "║  2. DROP INDEXES BEFORE IMPORTING (critical for speed):          ║"
echo "║                                                                   ║"
echo "║     docker compose exec postgres psql -U edfinder -d edfinder \\ ║"
echo "║       -c \"DO \\\$\\\$ DECLARE r RECORD; BEGIN FOR r IN              ║"
echo "║         SELECT indexname FROM pg_indexes WHERE tablename IN      ║"
echo "║         ('systems','bodies','stations','factions')               ║"
echo "║         AND indexname NOT LIKE '%pkey%'                          ║"
echo "║         LOOP EXECUTE 'DROP INDEX IF EXISTS '||r.indexname;       ║"
echo "║         END LOOP; END\\\$\\\$;\"                                      ║"
echo "║                                                                   ║"
echo "║  3. IMPORT (~8-24 hrs with COPY method, fully resumable):        ║"
echo "║                                                                   ║"
echo "║     screen -r import                                             ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       import_spansh.py --all                                     ║"
echo "║     # Ctrl+A D to detach                                         ║"
echo "║                                                                   ║"
echo "║  4. REBUILD INDEXES (after import):                              ║"
echo "║     docker compose exec postgres psql -U edfinder -d edfinder \\ ║"
echo "║       -f /docker-entrypoint-initdb.d/002_indexes.sql            ║"
echo "║                                                                   ║"
echo "║  5. BUILD RATINGS + GRID + CLUSTERS:                             ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_ratings.py --rebuild --workers 12           ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_grid.py                                      ║"
echo "║     screen -S clusters                                           ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_clusters.py --workers 12                    ║"
echo "║                                                                   ║"
echo "║  6. START EDDN LISTENER:                                         ║"
echo "║     docker compose up -d eddn                                    ║"
echo "║                                                                   ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  UPDATE (preserves DB):  git pull && sudo bash setup.sh --reinstall ║"
echo "║  FULL RESET (destroys DB):  sudo bash setup.sh --nuke            ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Useful commands:                                                 ║"
echo "║    docker compose logs -f api         — API logs                 ║"
echo "║    docker compose logs -f nginx       — nginx logs               ║"
echo "║    docker compose logs -f eddn        — EDDN listener logs       ║"
echo "║    docker compose restart api         — Restart API              ║"
echo "║    docker compose --profile import logs importer --tail=5       ║"
echo "║    df -h /data                        — Disk usage               ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
success "ED Finder setup complete!"
