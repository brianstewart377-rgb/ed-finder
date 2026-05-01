#!/bin/bash
# =============================================================================
# ED Finder — Hetzner Server Setup Script
# Version: 3.0
#
# Server:  Hetzner AX41-SSD (or equivalent)
#          i7-8700, 128 GB RAM, 3×1 TB NVMe RAID-5, Ubuntu 24.04
# Domain:  ed-finder.app (Cloudflare DNS → Hetzner IP)
# Stack:   PostgreSQL 16, pgBouncer, Redis 7, FastAPI, EDDN, Nginx
#
# Usage:
#   Fresh install:
#     bash setup.sh
#
#   Nuke existing install and reinstall (PRESERVES DATABASE):
#     bash setup.sh --reinstall
#
#   Nuke everything including database (DESTROYS ALL DATA):
#     bash setup.sh --nuke
#
# What --reinstall does:
#   • Stops all Docker containers
#   • Removes Docker images (forces rebuild)
#   • Pulls latest code from GitHub
#   • Restarts all services
#   • KEEPS: PostgreSQL data volume, SSL certs, dump files, logs
#
# What --nuke does:
#   • Everything above PLUS drops the PostgreSQL data volume
#   • Requires explicit confirmation
#   • Use only if you want to re-import everything from scratch
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
            echo "  (no args)     Fresh install"
            echo "  --reinstall   Rebuild containers, preserve DB data"
            echo "  --nuke        Destroy everything including DB (requires confirmation)"
            exit 0 ;;
    esac
done

# ---------------------------------------------------------------------------
# Must run as root
# ---------------------------------------------------------------------------
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup.sh"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_URL="https://github.com/brianstewart377-rgb/ed-finder.git"
REPO_ROOT="/opt/ed-finder-src"
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
mkdir -p "$INSTALL_DIR"
mkdir -p /var/log/nginx
chown -R root:root "$DATA_DIR"
chmod -R 755 "$DATA_DIR"
success "Directories created"

# ---------------------------------------------------------------------------
# Step 5 — Clone / update repository
# ---------------------------------------------------------------------------
step "5. Repository"
if [[ -d "$REPO_ROOT/.git" ]]; then
    info "Updating existing repo ..."
    git -C "$REPO_ROOT" pull origin main
    success "Repo updated to $(git -C $REPO_ROOT rev-parse --short HEAD)"
else
    info "Cloning repository ..."
    git clone "$REPO_URL" "$REPO_ROOT"
    success "Repo cloned"
fi

# ---------------------------------------------------------------------------
# Step 6 — Copy project files
# ---------------------------------------------------------------------------
step "6. Deploy files"
# Copy project files from repo root to install dir
for d in backend config frontend scripts sql tests; do
    [[ -d "$REPO_ROOT/$d" ]] && cp -r "$REPO_ROOT/$d" "$INSTALL_DIR/"
done
for f in docker-compose.yml setup.sh; do
    [[ -f "$REPO_ROOT/$f" ]] && cp "$REPO_ROOT/$f" "$INSTALL_DIR/"
done
# Frontend (served by nginx directly from repo checkout)
if [[ -d "$REPO_ROOT/frontend" ]]; then
    chmod -R 755 "$REPO_ROOT/frontend"
    success "Frontend at $REPO_ROOT/frontend"
fi
success "Files deployed to $INSTALL_DIR"

# ---------------------------------------------------------------------------
# Step 7 — Mask system nginx/apache (would conflict with Docker nginx on :80/:443)
# ---------------------------------------------------------------------------
step "7. Port conflicts"
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
# Step 8 — Environment file
# ---------------------------------------------------------------------------
step "8. Environment"
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
    success ".env created"
else
    success ".env already exists — keeping existing credentials"
fi

# ---------------------------------------------------------------------------
# Step 9 — UFW firewall
# ---------------------------------------------------------------------------
step "9. Firewall"
ufw --force enable
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw status
success "UFW configured"

# ---------------------------------------------------------------------------
# Step 10 — fail2ban
# ---------------------------------------------------------------------------
step "10. fail2ban"
systemctl enable fail2ban
systemctl start fail2ban
success "fail2ban active"

# ---------------------------------------------------------------------------
# Step 11 — SSL Certificate (before starting nginx container)
# ---------------------------------------------------------------------------
step "11. SSL Certificate"
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
# Step 12 — Build and start core services (postgres, redis, pgbouncer)
# ---------------------------------------------------------------------------
step "12. Start core services"
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
# Step 13 — Fix PostgreSQL auth for pgBouncer (md5)
# ---------------------------------------------------------------------------
step "13. PostgreSQL auth fix"
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
# Step 14 — Automated Index Rebuild
# ---------------------------------------------------------------------------
# If this is a fresh install or nuke, we MUST rebuild the indexes that were
# dropped in Step 2. If it's a reinstall, the indexes are likely already there.
step "14. Rebuild indexes"
info "Checking if indexes need to be rebuilt ..."
INDEX_COUNT=$(docker compose exec -T postgres psql -U edfinder -d edfinder -tAc "SELECT count(*) FROM pg_indexes WHERE tablename = 'systems' AND indexname NOT LIKE '%pkey%';")
if [[ "$INDEX_COUNT" -lt 5 ]]; then
    info "Found only $INDEX_COUNT indexes on 'systems'. Rebuilding all indexes from 002_indexes.sql ..."
    docker compose exec -T postgres psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql
    success "Indexes rebuilt successfully"
else
    success "Indexes already exist ($INDEX_COUNT found) — skipping rebuild"
fi

# Step 15 — Start remaining services
# ---------------------------------------------------------------------------
step "15. Start all services"
docker compose up -d
sleep 10
docker compose ps

# ---------------------------------------------------------------------------
# Step 16 — Health checks
# ---------------------------------------------------------------------------
step "16. Health checks"
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
# Step 17 — Nightly update cron
# ---------------------------------------------------------------------------
step "17. Nightly cron"
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
# Step 17 — Done
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
echo "║  REINSTALL (preserves DB):  bash setup.sh --reinstall            ║"
echo "║  FULL RESET (destroys DB):  bash setup.sh --nuke                 ║"
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
