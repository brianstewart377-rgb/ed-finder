#!/bin/bash
# =============================================================================
# ED Finder — Hetzner One-Shot Setup Script
# Run this once on a fresh Ubuntu 24.04 Hetzner server.
#
# Usage:
#   git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder-src
#   cd /opt/ed-finder-src/hetzner
#   chmod +x setup.sh
#   sudo ./setup.sh
#
# What it does:
#   1.  System updates + essential packages
#   2.  Docker + Docker Compose
#   3.  Directory structure
#   4.  Clone/verify repo at /opt/ed-finder-src
#   5.  Copy hetzner/ stack to /opt/ed-finder (working directory)
#   6.  .env file from prompts
#   7.  Kill system nginx (conflicts with Docker on port 80)
#   8.  Firewall (ufw)
#   9.  Fail2ban
#  10.  SSL certificate (Let's Encrypt, standalone — before Docker starts)
#  11.  Build Docker images
#  12.  Start core services (postgres, redis, pgbouncer)
#  13.  Apply schema + fix pg_hba auth for pgbouncer (md5)
#  14.  Start API + nginx
#  15.  Nightly update cron
#  16.  Print next steps
#
# Lessons learned from first deployment (documented here for future runs):
#   - Ubuntu 24.04 ships with nginx pre-installed and enabled — it grabs port 80
#     before Docker starts and causes containers to fail.  We mask it permanently.
#   - PostgreSQL 16 defaults to scram-sha-256 auth.  edoburu/pgbouncer sends md5.
#     Fix: SET password_encryption=md5, patch pg_hba.conf, pg_reload_conf().
#   - nginx upstream { server api:8000 } is resolved ONCE at startup — if the api
#     container isn't up yet nginx crashes.  Use resolver 127.0.0.11 + variable.
#   - ../frontend volume mount in docker-compose.yml resolves to /opt/frontend
#     (doesn't exist).  We use the absolute path /opt/ed-finder-src/frontend.
#   - Spansh no longer provides bodies.json.gz or attractions.json.gz.  All data
#     (systems, bodies, stations) is now in galaxy.json.gz (~102 GB compressed).
#     Total downloads: ~110 GB across 3 files (not 5).
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Must run as root
[[ $EUID -ne 0 ]] && error "Run as root: sudo ./setup.sh"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ED Finder — Hetzner Setup                                   ║"
echo "║  Target: Ubuntu 24.04, i7-8700, 128GB RAM, 2×1TB SSD        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------------------
# 1. RAID-1 check / recommendation
# ---------------------------------------------------------------------------
info "Checking storage ..."
if lsblk | grep -q 'md\|raid'; then
    success "RAID array detected"
else
    warn "No RAID detected. Consider setting up RAID-1 for redundancy:"
    warn "  mdadm --create /dev/md0 --level=1 --raid-devices=2 /dev/sda /dev/sdb"
    warn "Continuing with single-disk setup ..."
fi

# ---------------------------------------------------------------------------
# 2. System update
# ---------------------------------------------------------------------------
info "Updating system packages ..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip htop iotop ncdu \
    ufw fail2ban \
    python3 python3-pip python3-venv \
    certbot
success "System packages installed"

# ---------------------------------------------------------------------------
# 3. Docker
# ---------------------------------------------------------------------------
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
# 4. Directory structure
# ---------------------------------------------------------------------------
info "Creating directory structure ..."
mkdir -p /data/{dumps,logs,backups}
mkdir -p /opt/ed-finder/config
chown -R 1000:1000 /data
success "Directories created: /data/dumps  /data/logs  /data/backups  /opt/ed-finder"

# ---------------------------------------------------------------------------
# 5. Verify repo + copy working stack to /opt/ed-finder
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure we have a proper git clone at /opt/ed-finder-src
if [[ "$REPO_ROOT" != "/opt/ed-finder-src" ]]; then
    info "Cloning repo to /opt/ed-finder-src ..."
    if [[ -d /opt/ed-finder-src ]]; then
        git -C /opt/ed-finder-src pull origin main
    else
        git clone https://github.com/brianstewart377-rgb/ed-finder.git /opt/ed-finder-src
    fi
    REPO_ROOT=/opt/ed-finder-src
fi
success "Repo at $REPO_ROOT"

info "Copying hetzner stack to /opt/ed-finder ..."
cp -r "$REPO_ROOT/hetzner/"* /opt/ed-finder/
# Set correct permissions on frontend files (nginx needs world-readable)
chmod -R 755 "$REPO_ROOT/frontend/"
success "Stack copied to /opt/ed-finder"

# ---------------------------------------------------------------------------
# 6. .env file
# ---------------------------------------------------------------------------
ENV_FILE=/opt/ed-finder/.env
if [[ ! -f "$ENV_FILE" ]]; then
    info "Creating .env configuration file ..."
    echo ""
    read -r -p "  PostgreSQL password (strong, no special chars): " PG_PASS
    echo ""

    # Generate a random password if empty
    if [[ -z "$PG_PASS" ]]; then
        PG_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
        warn "No password entered — generated: $PG_PASS"
        warn "Save this password somewhere safe!"
    fi

    cat > "$ENV_FILE" << EOF
# ED Finder — Hetzner Environment Variables
# Generated: $(date)

POSTGRES_PASSWORD=${PG_PASS}
LOG_LEVEL=INFO

# Optional: adjust cache TTLs (seconds)
TTL_SEARCH=3600
TTL_SYSTEM=86400
TTL_CLUSTER=3600
EOF
    chmod 600 "$ENV_FILE"
    success ".env file created at $ENV_FILE"
else
    # Read existing password for use in pg_hba fix later
    PG_PASS=$(grep POSTGRES_PASSWORD "$ENV_FILE" | cut -d= -f2)
    success ".env already exists — skipping"
fi

# ---------------------------------------------------------------------------
# 7. Kill system nginx — it grabs port 80 and blocks Docker nginx
# ---------------------------------------------------------------------------
info "Disabling system nginx (conflicts with Docker on port 80/443) ..."
systemctl stop nginx   2>/dev/null || true
systemctl disable nginx 2>/dev/null || true
systemctl mask nginx   2>/dev/null || true   # prevent restart on boot
systemctl stop apache2  2>/dev/null || true
systemctl disable apache2 2>/dev/null || true
# Give the OS a moment to release ports
sleep 2
if ss -tlnp | grep -qE ':80\b|:443\b'; then
    warn "Something is still on port 80/443:"
    ss -tlnp | grep -E ':80\b|:443\b'
    warn "You may need to kill it manually before nginx starts."
else
    success "Ports 80 and 443 are free"
fi

# ---------------------------------------------------------------------------
# 8. Firewall
# ---------------------------------------------------------------------------
info "Configuring firewall ..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment 'SSH'
ufw allow 80/tcp    comment 'HTTP'
ufw allow 443/tcp   comment 'HTTPS'
ufw --force enable
success "Firewall configured (22, 80, 443 open)"

# ---------------------------------------------------------------------------
# 9. Fail2ban
# ---------------------------------------------------------------------------
info "Enabling fail2ban ..."
systemctl enable fail2ban
systemctl start fail2ban
success "fail2ban enabled"

# ---------------------------------------------------------------------------
# 10. SSL certificate (standalone — runs before Docker nginx starts)
# ---------------------------------------------------------------------------
info "Requesting Let's Encrypt SSL certificate ..."
echo ""
read -r -p "  Your email for SSL cert renewal notices: " SSL_EMAIL
echo ""

if [[ -z "$SSL_EMAIL" ]]; then
    warn "No email provided — skipping SSL setup. Run manually later:"
    warn "  certbot certonly --standalone -d ed-finder.app -d www.ed-finder.app \\"
    warn "    --email you@example.com --agree-tos --non-interactive"
else
    certbot certonly --standalone \
        -d ed-finder.app \
        -d www.ed-finder.app \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        && success "SSL certificate obtained for ed-finder.app" \
        || warn "SSL failed — check DNS points to this server and try manually"

    # Auto-renewal: certbot renews, then reload nginx (no restart needed)
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f /opt/ed-finder/docker-compose.yml exec nginx nginx -s reload") | crontab -
    success "SSL auto-renewal configured (daily at 03:00)"
fi

# ---------------------------------------------------------------------------
# 11. Build Docker images
# ---------------------------------------------------------------------------
info "Building Docker images ..."
cd /opt/ed-finder
docker compose build
success "Docker images built"

# ---------------------------------------------------------------------------
# 12. Start core services (PostgreSQL, Redis, pgBouncer — not API or nginx yet)
# ---------------------------------------------------------------------------
info "Starting database services ..."
docker compose up -d postgres redis pgbouncer

info "Waiting for PostgreSQL to be ready ..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U edfinder -q 2>/dev/null; then
        success "PostgreSQL ready"
        break
    fi
    sleep 2
    echo -n "."
done
echo ""

# ---------------------------------------------------------------------------
# 13. Apply schema + fix pg_hba auth for pgbouncer compatibility
# ---------------------------------------------------------------------------
info "Applying database schema ..."
# 001_schema.sql is auto-run by postgres on first start via initdb.d mount.
# Run it explicitly in case the volume already existed without schema.
docker compose exec -T postgres psql -U edfinder -d edfinder \
    -f /docker-entrypoint-initdb.d/001_schema.sql 2>/dev/null || true
docker compose exec -T postgres psql -U edfinder -d edfinder \
    -f /docker-entrypoint-initdb.d/003_functions.sql 2>/dev/null || true
success "Schema applied"

info "Switching postgres auth to md5 for pgbouncer compatibility ..."
# PostgreSQL 16 defaults to scram-sha-256.
# edoburu/pgbouncer AUTH_TYPE=md5 cannot relay scram-sha-256 to postgres.
# Fix: store the password as md5 hash and update pg_hba.conf.
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "SET password_encryption = md5; ALTER USER edfinder WITH PASSWORD '${PG_PASS}';"
docker compose exec -T postgres sed -i 's/scram-sha-256/md5/g' \
    /var/lib/postgresql/data/pg_hba.conf
docker compose exec -T postgres psql -U edfinder -d edfinder -c \
    "SELECT pg_reload_conf();"
success "Auth method set to md5 — pgbouncer can now connect"

# ---------------------------------------------------------------------------
# 14. Start API + nginx
# ---------------------------------------------------------------------------
info "Starting API and nginx ..."
docker compose up -d api nginx

info "Waiting for API to become healthy ..."
for i in {1..20}; do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        success "API is healthy"
        break
    fi
    sleep 5
    echo -n "."
done
echo ""

# Quick smoke test
HTTP_STATUS=$(curl -so /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [[ "$HTTP_STATUS" == "200" ]]; then
    success "Frontend serving on port 80 (HTTP $HTTP_STATUS)"
else
    warn "Frontend returned HTTP $HTTP_STATUS — check: docker compose logs nginx"
fi

# ---------------------------------------------------------------------------
# 15. Nightly update cron
# ---------------------------------------------------------------------------
info "Installing nightly update cron job ..."
NIGHTLY_SCRIPT=/opt/ed-finder/import/nightly_update.sh
if [[ -f "$NIGHTLY_SCRIPT" ]]; then
    chmod +x "$NIGHTLY_SCRIPT"
    (crontab -l 2>/dev/null; echo "0 2 * * * $NIGHTLY_SCRIPT >> /data/logs/nightly.log 2>&1") | crontab -
    success "Nightly update scheduled at 02:00 daily"
else
    warn "nightly_update.sh not found at $NIGHTLY_SCRIPT — skipping cron"
fi

# ---------------------------------------------------------------------------
# 16. Done — print next steps
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
echo "║  1. START SPANSH IMPORT (~3-5 days, fully resumable):            ║"
echo "║                                                                   ║"
echo "║     screen -S import                                             ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       import_spansh.py --all                                     ║"
echo "║     # Ctrl+A D to detach                                         ║"
echo "║                                                                   ║"
echo "║     Downloads + imports 3 files (~110 GB total):                 ║"
echo "║       galaxy.json.gz          ~102 GB  (systems+bodies+stations) ║"
echo "║       galaxy_populated.json.gz  ~3.6 GB  (faction/economy data)  ║"
echo "║       galaxy_stations.json.gz   ~3.6 GB  (station refresh)       ║"
echo "║                                                                   ║"
echo "║  2. MONITOR IMPORT:                                              ║"
echo "║     screen -r import                  (re-attach)                ║"
echo "║     docker compose exec postgres psql -U edfinder -d edfinder \\ ║"
echo "║       -c 'SELECT dump_file,status,rows_processed FROM import_meta;'║"
echo "║                                                                   ║"
echo "║  3. AFTER IMPORT — build ratings + grid + clusters:              ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_ratings.py --rebuild --workers 12            ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_grid.py                                      ║"
echo "║     screen -S clusters                                           ║"
echo "║     docker compose --profile import run --rm importer \\          ║"
echo "║       python3 build_clusters.py --workers 12                     ║"
echo "║                                                                   ║"
echo "║  4. BUILD INDEXES (run after all data is loaded):                ║"
echo "║     docker compose exec postgres psql -U edfinder -d edfinder \\ ║"
echo "║       -f /docker-entrypoint-initdb.d/002_indexes.sql             ║"
echo "║                                                                   ║"
echo "║  5. START EDDN LISTENER (live game data):                        ║"
echo "║     docker compose up -d eddn                                    ║"
echo "║                                                                   ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Useful commands:                                                 ║"
echo "║    docker compose logs -f api         — API logs                 ║"
echo "║    docker compose logs -f nginx       — nginx logs               ║"
echo "║    docker compose logs -f eddn        — EDDN listener logs       ║"
echo "║    docker compose logs -f postgres    — DB logs                  ║"
echo "║    docker compose restart api         — Restart API              ║"
echo "║    tail -f /data/logs/import.log      — Import progress          ║"
echo "║    df -h /data                        — Disk usage               ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
success "ED Finder Hetzner setup complete!"
