#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
#  ED:Finder — COMPLETE FIX Deployment Script
#  This script will deploy the WORKING v3.18 frontend with proper configuration
# ══════════════════════════════════════════════════════════════════════════════

set -e

echo "🚀 ED:Finder COMPLETE FIX Deployment Script"
echo "============================================="
echo ""

# Timestamp for backups
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="backup-${TIMESTAMP}"

# Step 1: Stop any existing containers
echo "⏹️  Step 1: Stopping existing containers..."
cd ~/ed-finder-v3.20 2>/dev/null && docker compose down 2>/dev/null || true
echo "✅ Existing containers stopped"
echo ""

# Step 2: Backup current installation
echo "💾 Step 2: Backing up current installation..."
if [ -d ~/ed-finder-v3.20 ]; then
    mkdir -p ~/"${BACKUP_DIR}"
    cp -r ~/ed-finder-v3.20 ~/"${BACKUP_DIR}/" 2>/dev/null || true
    echo "✅ Backup created at ~/${BACKUP_DIR}"
else
    echo "⚠️  No existing installation found to backup"
fi
echo ""

# Step 3: Extract the WORKING version
echo "📦 Step 3: Deploying WORKING version..."
cd ~
tar -xzf ed-finder-WORKING.tar.gz
echo "✅ Files extracted"
echo ""

# Step 4: Build and start containers
echo "🔨 Step 4: Building Docker containers (this may take 2-3 minutes)..."
cd ~/ed-finder-WORKING
docker compose build --no-cache
echo "✅ Containers built"
echo ""

echo "▶️  Step 5: Starting services..."
docker compose up -d
echo "✅ Services started"
echo ""

# Step 6: Wait for services to be healthy
echo "⏳ Step 6: Waiting for services to be healthy (30 seconds)..."
sleep 30

# Step 7: Verify deployment
echo ""
echo "🧪 Step 7: Running verification tests..."
echo ""

echo "Test 1: Check container status..."
docker compose ps
echo ""

echo "Test 2: Test API health endpoint..."
curl -s http://localhost:80/api/health | head -5
echo ""

echo "Test 3: Test API status endpoint..."
curl -s http://localhost:80/api/status | head -5
echo ""

echo "Test 4: Check CORS configuration..."
docker compose exec api env | grep ALLOWED_ORIGINS
echo ""

echo "Test 5: Verify port 80 is listening..."
sudo ss -tlnp | grep :80
echo ""

# Final instructions
echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ DEPLOYMENT COMPLETE!                                 ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Next steps:"
echo ""
echo "1️⃣  Open your browser and go to: http://raspberrypi.local"
echo "    (If you're on Windows, you might need to use: http://192.168.0.115)"
echo ""
echo "2️⃣  CLEAR YOUR BROWSER CACHE (very important!):"
echo "    • Press Ctrl+Shift+Delete"
echo "    • Select 'All time' and 'Cached images and files'"
echo "    • Click 'Clear data'"
echo ""
echo "3️⃣  Hard refresh the page:"
echo "    • Press Ctrl+Shift+R (or Cmd+Shift+R on Mac)"
echo ""
echo "4️⃣  You should see:"
echo "    • Green status light in the header"
echo "    • All tabs clickable (Search, Route, Watchlist, Colonise, Commodities)"
echo "    • Search functionality working"
echo ""
echo "📊 Monitor logs with:"
echo "    cd ~/ed-finder-WORKING"
echo "    docker compose logs -f"
echo ""
echo "🛑 Stop services with:"
echo "    cd ~/ed-finder-WORKING"
echo "    docker compose down"
echo ""
echo "♻️  Restart services with:"
echo "    cd ~/ed-finder-WORKING"
echo "    docker compose restart"
echo ""
echo "💡 If you still see issues:"
echo "    1. Try a different browser (Firefox, Chrome, Edge)"
echo "    2. Try incognito/private mode"
echo "    3. Check browser console (F12) for errors"
echo ""
echo "🎉 Your ED:Finder installation should now be working!"
echo ""
