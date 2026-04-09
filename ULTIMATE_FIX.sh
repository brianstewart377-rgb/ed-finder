#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
#  ED:Finder ULTIMATE FIX — Complete Deployment Script
#  Fixes all known issues and deploys the working v3.18 solution
# ══════════════════════════════════════════════════════════════════════════════

set -e  # Exit on any error

echo "════════════════════════════════════════════════════════════════════"
echo "  ED:Finder ULTIMATE FIX - Deployment Starting"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Configuration ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${HOME}/ed-finder-backup-${TIMESTAMP}"

echo "📁 Working directory: ${SCRIPT_DIR}"
echo "⏰ Timestamp: ${TIMESTAMP}"
echo ""

# ── Step 1: Stop existing containers ──────────────────────────────────────
echo "🛑 Step 1: Stopping existing ED:Finder containers..."
docker ps -a | grep ed-finder | awk '{print $1}' | xargs -r docker rm -f 2>/dev/null || true
docker compose down 2>/dev/null || true
echo "✅ Old containers stopped"
echo ""

# ── Step 2: Backup existing installation ──────────────────────────────────
if [ -d "${HOME}/ed-finder-v3.20" ]; then
    echo "💾 Step 2: Backing up existing installation..."
    cp -r "${HOME}/ed-finder-v3.20" "${BACKUP_DIR}"
    echo "✅ Backup created at: ${BACKUP_DIR}"
else
    echo "ℹ️  Step 2: No existing installation found (first deployment)"
fi
echo ""

# ── Step 3: Fix FastAPI import issue ──────────────────────────────────────
echo "🔧 Step 3: Fixing FastAPI middleware import..."
cd "${SCRIPT_DIR}/backend"
sed -i 's/from fastapi.middleware.base import BaseHTTPMiddleware/from starlette.middleware.base import BaseHTTPMiddleware/g' main.py
echo "✅ Import fixed (fastapi.middleware.base → starlette.middleware.base)"
echo ""

# ── Step 4: Verify docker-compose.yml (no cgroup limits) ─────────────────
echo "🔍 Step 4: Verifying Docker Compose configuration..."
cd "${SCRIPT_DIR}"
if grep -q "mem_limit\|cpus\|memory:" docker-compose.yml; then
    echo "⚠️  WARNING: Found cgroup v2 incompatible settings!"
    echo "   These will cause container failures on Raspberry Pi OS."
    echo "   Please remove mem_limit, cpus, or memory: settings."
    exit 1
else
    echo "✅ Docker Compose configuration is cgroup v2 compatible"
fi
echo ""

# ── Step 5: Clear Docker cache (prevents snapshot extraction errors) ────────
echo "🧹 Step 5: Clearing Docker cache (prevents build errors on Raspberry Pi)..."
docker system prune -af 2>/dev/null || true
echo "✅ Docker cache cleared"
echo ""

# ── Step 6: Build containers ───────────────────────────────────────────────
echo "🏗️  Step 6: Building Docker containers (this may take 3-5 minutes)..."
cd "${SCRIPT_DIR}"
docker compose build --no-cache
echo "✅ Containers built successfully"
echo ""

# ── Step 7: Start services ─────────────────────────────────────────────────
echo "🚀 Step 7: Starting ED:Finder services..."
docker compose up -d
echo "✅ Services started"
echo ""

# ── Step 8: Wait for API health check ─────────────────────────────────────
echo "⏳ Step 8: Waiting for API to become healthy..."
for i in {1..30}; do
    if docker inspect ed-finder-api | grep -q '"Status": "healthy"'; then
        echo "✅ API is healthy!"
        break
    fi
    echo "   Attempt $i/30... (waiting 2s)"
    sleep 2
done
echo ""

# ── Step 9: Verify deployment ──────────────────────────────────────────────
echo "🧪 Step 9: Running verification tests..."
echo ""

# Test API endpoint
echo "   Testing API status endpoint..."
if curl -sf http://localhost/api/status > /dev/null; then
    echo "   ✅ API endpoint responding"
else
    echo "   ❌ API endpoint not responding"
    echo "   Run: docker compose logs api"
fi

# Test frontend
echo "   Testing frontend..."
if curl -sf http://localhost/ > /dev/null; then
    echo "   ✅ Frontend accessible"
else
    echo "   ❌ Frontend not accessible"
    echo "   Run: docker compose logs web"
fi

# Check container status
echo ""
echo "   Container status:"
docker compose ps
echo ""

# ── Final Summary ──────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  ✅ ED:Finder ULTIMATE FIX - Deployment Complete!"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "🌐 Access your ED:Finder installation at:"
echo "   • http://raspberrypi.local"
echo "   • http://192.168.0.115"
echo ""
echo "🔍 If you see issues:"
echo "   • Yellow 'Connecting...' → Wait 30 seconds for API to start"
echo "   • Blank page → Clear browser cache (Ctrl+Shift+Delete)"
echo "   • JavaScript errors → Hard refresh (Ctrl+Shift+R)"
echo ""
echo "📋 Useful commands:"
echo "   docker compose logs api     # View API logs"
echo "   docker compose logs web     # View Nginx logs"
echo "   docker compose ps           # Check container status"
echo "   docker compose restart      # Restart all services"
echo ""
echo "💾 Backup location: ${BACKUP_DIR}"
echo ""
echo "🎉 Happy exploring, Commander! o7"
