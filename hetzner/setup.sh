#!/bin/bash
# =============================================================================
# ED Finder — Hetzner One-Shot Setup Script
# Run this once on a fresh Ubuntu 24.04 Hetzner server.
#
# Usage:
#   chmod +x setup.sh
#   sudo ./setup.sh
#
# What it does:
#   1. System updates + essential packages
#   2. Docker + Docker Compose
#   3. Directory structure
#   4. .env file from prompts
#   5. SSL certificate (Let's Encrypt)
#   6. Start all services
#   7. Print next steps
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
mkdir -p /opt/ed-finder
chown -R 1000:1000 /data
success "Directories created: /data/dumps  /data/logs  /data/backups"

# ---------------------------------------------------------------------------
# 5. Copy project files
# ---------------------------------------------------------------------------
info "Copying ED Finder files to /opt/ed-finder ..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR"/* /opt/ed-finder/
# Copy frontend if present
if [[ -d "$SCRIPT_DIR/../frontend" ]]; then
    cp -r "$SCRIPT_DIR/../frontend" /opt/ed-finder/frontend
    success "Frontend files copied"
fi
success "Project files copied to /opt/ed-finder"

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
    success ".env already exists — skipping"
fi

# ---------------------------------------------------------------------------
# 7. Firewall
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
# 8. Fail2ban
# ---------------------------------------------------------------------------
info "Enabling fail2ban ..."
systemctl enable fail2ban
systemctl start fail2ban
success "fail2ban enabled"

# ---------------------------------------------------------------------------
# 9. SSL certificate
# ---------------------------------------------------------------------------
info "Requesting Let's Encrypt SSL certificate ..."
echo ""
read -r -p "  Your email for SSL cert renewal notices: " SSL_EMAIL
echo ""

if [[ -z "$SSL_EMAIL" ]]; then
    warn "No email provided — skipping SSL setup. Run manually later:"
    warn "  certbot certonly --standalone -d ed-finder.app -d www.ed-finder.app --email you@example.com --agree-tos"
else
    # Stop anything on port 80 first
    docker compose -f /opt/ed-finder/docker-compose.yml down 2>/dev/null || true

    certbot certonly --standalone \
        -d ed-finder.app \
        -d www.ed-finder.app \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        && success "SSL certificate obtained for ed-finder.app" \
        || warn "SSL failed — check DNS and try manually"

    # Auto-renewal cron
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f /opt/ed-finder/docker-compose.yml restart nginx") | crontab -
    success "SSL auto-renewal configured"
fi

# ---------------------------------------------------------------------------
# 10. Build Docker images
# ---------------------------------------------------------------------------
info "Building Docker images ..."
cd /opt/ed-finder
docker compose build
success "Docker images built"

# ---------------------------------------------------------------------------
# 11. Start core services (PostgreSQL, Redis, pgBouncer only — not API yet)
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
# 12. Apply schema
# ---------------------------------------------------------------------------
info "Applying database schema ..."
docker compose exec -T postgres psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/001_schema.sql
docker compose exec -T postgres psql -U edfinder -d edfinder -f /docker-entrypoint-initdb.d/003_functions.sql
success "Schema applied"

# ---------------------------------------------------------------------------
# 13. Nightly update cron
# ---------------------------------------------------------------------------
info "Installing nightly update cron job ..."
NIGHTLY_SCRIPT=/opt/ed-finder/import/nightly_update.sh
chmod +x "$NIGHTLY_SCRIPT"
(crontab -l 2>/dev/null; echo "0 2 * * * $NIGHTLY_SCRIPT >> /data/logs/nightly.log 2>&1") | crontab -
success "Nightly update scheduled at 02:00 daily"

# ---------------------------------------------------------------------------
# 14. Done — print next steps
# ---------------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Setup complete! Next steps:                                  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                               ║"
echo "║  1. DOWNLOAD SPANSH DUMPS (run in screen/tmux):              ║"
echo "║     cd /opt/ed-finder                                        ║"
echo "║     docker compose --profile import run importer             ║"
echo "║       python3 import_spansh.py --download                    ║"
echo "║                                                               ║"
echo "║  2. START IMPORT (takes 1-3 days, fully resumable):          ║"
echo "║     docker compose --profile import up importer              ║"
echo "║     # Monitor:                                                ║"
echo "║     docker logs ed-importer -f                               ║"
echo "║                                                               ║"
echo "║  3. AFTER IMPORT — build ratings + grid + clusters:          ║"
echo "║     docker compose exec importer python3 build_ratings.py    ║"
echo "║     docker compose exec importer python3 build_grid.py       ║"
echo "║     docker compose exec importer python3 build_clusters.py   ║"
echo "║                                                               ║"
echo "║  4. BUILD INDEXES (run after all data is loaded):            ║"
echo "║     docker compose exec postgres psql -U edfinder -d         ║"
echo "║       edfinder -f /docker-entrypoint-initdb.d/002_indexes.sql ║"
echo "║                                                               ║"
echo "║  5. START FULL STACK:                                        ║"
echo "║     docker compose up -d                                     ║"
echo "║                                                               ║"
echo "║  6. CHECK EVERYTHING IS RUNNING:                             ║"
echo "║     docker compose ps                                        ║"
echo "║     curl https://ed-finder.app/api/health                    ║"
echo "║     curl https://ed-finder.app/api/status                    ║"
echo "║                                                               ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Useful commands:                                             ║"
echo "║    docker compose logs -f api         — API logs             ║"
echo "║    docker compose logs -f eddn        — EDDN listener logs   ║"
echo "║    docker compose logs -f postgres    — DB logs              ║"
echo "║    docker compose restart api         — Restart API          ║"
echo "║    cat /data/logs/import.log          — Import progress      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
success "ED Finder Hetzner setup complete!"
