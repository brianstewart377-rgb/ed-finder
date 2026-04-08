# ED:Finder — COMPLETE WORKING VERSION

## What's Different in This Version?

This is **v3.18-clean** with a **complete, working frontend** that actually connects to your backend.

### The Problem
All the v3.20 archives had an **incomplete frontend** - the `index.html` file was missing all the JavaScript functions needed to:
- Connect to the API
- Search for systems
- Display results
- Handle user interactions

### The Solution
This package uses the **v3.18 frontend** which has ALL the required JavaScript code, combined with:
- Proper **bridge networking** (not host mode)
- Correct **nginx configuration** pointing to `api:8000`
- Permissive **CORS settings** for testing
- All necessary **environment variables**

## What's Included

```
ed-finder-WORKING/
├── frontend/           # COMPLETE v3.18 frontend with all JavaScript
│   ├── index.html      # 6,895 lines - fully functional!
│   └── 50x.html
├── backend/            # Your FastAPI backend
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── data/               # SQLite database directory
├── docker-compose.yml  # Bridge networking configuration
├── nginx.conf          # Proper API proxy to api:8000
├── .env                # Environment variables
├── DEPLOY.sh           # Automated deployment script
└── README.md           # This file
```

## Deployment Instructions

### Option 1: Automated Deployment (Recommended)

On your Raspberry Pi:

```bash
# 1. Download the archive to your Pi
cd ~
# (Transfer ed-finder-WORKING.tar.gz to the Pi via SCP or download)

# 2. Extract it
tar -xzf ed-finder-WORKING.tar.gz

# 3. Run the deployment script
cd ed-finder-WORKING
./DEPLOY.sh
```

The script will:
- Stop any existing containers
- Backup your current installation
- Deploy the working version
- Build and start containers
- Run verification tests
- Show you the status

### Option 2: Manual Deployment

```bash
# 1. Stop existing containers
cd ~/ed-finder-v3.20
docker compose down

# 2. Extract the working version
cd ~
tar -xzf ed-finder-WORKING.tar.gz
cd ed-finder-WORKING

# 3. Build and start
docker compose build --no-cache
docker compose up -d

# 4. Wait 30 seconds for services to be healthy
sleep 30

# 5. Verify
docker compose ps
curl http://localhost:80/api/status
```

## Access the Application

### From Your Desktop
1. Open your browser and go to: **http://raspberrypi.local**
   - If that doesn't work, try: **http://192.168.0.115**

2. **CRITICAL**: Clear your browser cache:
   - Press `Ctrl+Shift+Delete`
   - Select "All time" and check "Cached images and files"
   - Click "Clear data"

3. Hard refresh the page:
   - Press `Ctrl+Shift+R` (Windows/Linux)
   - Press `Cmd+Shift+R` (Mac)

### What You Should See
- ✅ **Green status light** in the header (not yellow blinking)
- ✅ **All tabs clickable**: Search, Route, Watchlist, Colonise, Commodities
- ✅ **Search works**: Type a system name, see suggestions, click search
- ✅ **Results display**: System cards with details

### If You Still See "Connecting to ED:Finder backend..."

1. **Try a different browser**: Firefox, Chrome, Edge
2. **Try incognito/private mode**: This guarantees no cache
3. **Check browser console** (press F12):
   - Look for any red errors
   - Run this test:
     ```javascript
     fetch('/api/status').then(r=>r.json()).then(d=>console.log('✅ Works!',d))
     ```
   - You should see: `✅ Works! {status: "online", version: "3.16.0", ...}`

## Managing the Application

### View Logs
```bash
cd ~/ed-finder-WORKING
docker compose logs -f
```

### Stop Services
```bash
cd ~/ed-finder-WORKING
docker compose down
```

### Restart Services
```bash
cd ~/ed-finder-WORKING
docker compose restart
```

### Rebuild (if you change code)
```bash
cd ~/ed-finder-WORKING
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Troubleshooting

### Problem: Port 80 Already in Use
If InfluxDB is using port 80:

```bash
# Stop InfluxDB
sudo systemctl stop influxd

# Restart ED:Finder
cd ~/ed-finder-WORKING
docker compose restart web

# Verify
sudo ss -tlnp | grep :80
```

### Problem: Containers Won't Start
```bash
# Check logs
docker compose logs

# Check container status
docker compose ps

# Try rebuilding
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Problem: API Returns Empty Response
This was a network routing issue - solved by:
1. Using bridge networking (not host mode)
2. Accessing via hostname: `http://raspberrypi.local`
3. Nginx proxying to `api:8000` (not `localhost:8000`)

## Technical Details

### Why This Version Works

1. **Complete Frontend**: v3.18 has ALL JavaScript functions:
   - `checkApiConnection()` - tests API connectivity
   - `runSearch()` - performs system searches
   - `buildSystemCard()` - renders results
   - All UI interaction handlers

2. **Correct Networking**:
   - Bridge mode with internal network
   - Nginx and API can communicate via service names
   - Port 80 exposed to host

3. **Proper Nginx Config**:
   - Proxies `/api/` to `http://api:8000/api/`
   - Permissive CORS headers
   - Permissive CSP for testing

4. **Environment Variables**:
   - `ALLOWED_ORIGINS=*` for development
   - All TTL and system check settings

### Configuration Files

**docker-compose.yml**:
- Bridge networking with `internal` network
- API service with healthcheck
- Web service depends on healthy API
- Proper volume mounts

**nginx.conf**:
- Proxy to `api:8000` (not `localhost`)
- CORS headers
- CSP allowing necessary external APIs
- Static file serving

**.env**:
- All necessary environment variables
- CORS set to wildcard for testing
- Sensible cache TTLs

## Version History

- **v3.18-clean**: Complete, working frontend
- **v3.20**: Attempted fixes but frontend incomplete
- **THIS VERSION**: v3.18 frontend + v3.20 configuration

## Support

If this STILL doesn't work after:
1. Clearing browser cache completely
2. Hard refreshing (Ctrl+Shift+R)
3. Trying incognito mode
4. Trying a different browser

Then provide:
1. Browser console output (F12 → Console tab)
2. Network tab showing `/api/status` request/response
3. Output of:
   ```bash
   cd ~/ed-finder-WORKING
   docker compose ps
   docker compose logs --tail 100
   curl http://localhost:80/api/status
   ```

## Credits

- Backend: FastAPI caching proxy for Spansh/EDSM/Inara APIs
- Frontend: Elite Dangerous system finder with colonization planning
- Deployment: Docker Compose with Nginx reverse proxy
