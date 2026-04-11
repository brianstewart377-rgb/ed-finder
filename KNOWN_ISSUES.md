# ED:Finder - Known Issues & Solutions

## Issue 1: FastAPI Middleware Import Error

**Symptom:**
```
ModuleNotFoundError: No module named 'fastapi.middleware.base'
Container logs show: ImportError when starting uvicorn
```

**Root Cause:**
FastAPI v0.104+ moved `BaseHTTPMiddleware` to Starlette. The old import path no longer works.

**Solution:**
```bash
cd ~/ed-finder-FINAL-COMPLETE/backend
sed -i 's/from fastapi.middleware.base import BaseHTTPMiddleware/from starlette.middleware.base import BaseHTTPMiddleware/g' main.py
docker compose build --no-cache api
docker compose up -d
```

**Prevention:**
Always use Starlette for middleware imports in new code:
```python
from starlette.middleware.base import BaseHTTPMiddleware  # ✅ Correct
from fastapi.middleware.base import BaseHTTPMiddleware    # ❌ Deprecated
```

**Status:** ✅ Fixed in ULTIMATE_FIX.sh (automatic)

---

## Issue 2: Container Name Conflict

**Symptom:**
```
Error: Conflict. The container name "/ed-finder-api" is already in use by container "abc123..."
Error: Conflict. The container name "/ed-finder-web" is already in use
```

**Root Cause:**
Old containers weren't properly stopped/removed before deployment. This happens when:
- Previous deployment didn't complete `docker compose down`
- Container crashed but wasn't removed
- Multiple deployments attempted in quick succession

**Solution:**
```bash
# Remove all ed-finder containers
docker ps -a | grep ed-finder | awk '{print $1}' | xargs -r docker rm -f

# Or more targeted:
docker stop ed-finder-api ed-finder-web 2>/dev/null
docker rm ed-finder-api ed-finder-web 2>/dev/null

# Then redeploy
cd ~/ed-finder-FINAL-COMPLETE
docker compose up -d
```

**Prevention:**
Always run `docker compose down` before redeploying, or use ULTIMATE_FIX.sh which handles this automatically.

**Status:** ✅ Fixed in ULTIMATE_FIX.sh (automatic cleanup)

---

## Issue 3: cgroup v2 Memory Limit Errors

**Symptom:**
```
Error response from daemon: unknown or invalid runtime name: nvidia
failed to create shim task: OCI runtime create failed
Error response from daemon: linux mounts: Path /sys/fs/cgroup/memory does not exist
```

**Root Cause:**
Raspberry Pi OS uses cgroup v2 which doesn't support the `mem_limit` or `cpus` options in the same way as cgroup v1. The old Docker Compose format tries to use cgroup v1 paths that don't exist.

**Solution:**
Remove memory limits from `docker-compose.yml`:
```yaml
# ❌ Remove these lines:
mem_limit: 512m
cpus: "1.0"
memory: 512M

# ✅ For cgroup v2, either omit limits or use:
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '1.0'
```

**For this deployment:**
We've completely removed cgroup limits since the Pi has sufficient resources and they cause more problems than they solve.

**Status:** ✅ Already fixed in this package's docker-compose.yml

---

## Issue 4: Port 80 Already in Use

**Symptom:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:80: bind: address already in use
```

**Root Cause:**
Another service (commonly InfluxDB) is already using port 80.

**Solution:**
```bash
# Find what's using port 80
sudo lsof -i :80
sudo netstat -tulpn | grep :80

# If it's InfluxDB (common on Pi):
sudo systemctl stop influxd
sudo systemctl disable influxd

# Then redeploy
cd ~/ed-finder-FINAL-COMPLETE
docker compose up -d
```

**Alternative:**
Change ED:Finder to use a different port in docker-compose.yml:
```yaml
ports:
  - "8080:80"  # Access via http://192.168.0.115:8080
```

**Status:** ⚠️ Manual fix required (depends on your system)

---

## Issue 5: Yellow "Connecting..." Status

**Symptom:**
- Frontend loads
- Status indicator shows yellow with "Connecting..."
- Never turns green

**Root Cause:**
API container is still starting up, or healthcheck is failing.

**Solution:**
```bash
# Wait 30-60 seconds, then check API status
docker compose ps

# Check API logs
docker compose logs api

# Verify API responds
curl http://localhost:8000/api/health

# If unhealthy, restart API
docker compose restart api
```

**Common sub-causes:**
- **Slow Pi startup:** Wait longer (60-90 seconds)
- **Python dependencies missing:** Run `docker compose build --no-cache api`
- **Database locked:** Check `data/edfinder.db` permissions
- **Spansh API down:** Check `docker compose logs api` for connection errors

**Status:** ⚠️ Usually resolves by waiting; check logs if persists

---

## Issue 6: Blank White Page

**Symptom:**
- Browser shows blank white page
- No content loads
- May or may not show browser tab title

**Root Cause:**
Browser cached old (broken) version of JavaScript.

**Solution:**
```bash
# In browser:
1. Press Ctrl+Shift+Delete
2. Select "Cached images and files"
3. Select "All time"
4. Click "Clear data"
5. Hard refresh: Ctrl+Shift+R

# Or try incognito mode:
Ctrl+Shift+N (Chrome) or Ctrl+Shift+P (Firefox)
```

**Verification:**
```bash
# Check frontend is being served
curl http://localhost/ | grep -c "<script>"
# Should show a number > 0

# Check for key JavaScript functions
curl http://localhost/ | grep -c "async function runSearch"
# Should show 1
```

**Status:** ⚠️ User action required (clear cache)

---

## Issue 7: JavaScript Console Errors

**Symptom:**
Browser console (F12) shows:
```
Uncaught ReferenceError: runSearch is not defined
Uncaught TypeError: Cannot read properties of undefined
Failed to load resource: net::ERR_CACHE_READ_FAILURE
```

**Root Cause:**
Old cached JavaScript or browser extension interference.

**Solution:**
1. **Hard refresh:** Ctrl+Shift+R
2. **Clear cache:** See Issue 6
3. **Disable extensions:** Try incognito mode
4. **Check console:** Look for actual error details

**Verification:**
Open console and run:
```javascript
fetch('/api/status').then(r=>r.json()).then(d=>console.log(d))
```
Should show: `{status: "online", ...}`

**Status:** ⚠️ Usually cache-related; hard refresh fixes most cases

---

## Issue 8: Search Not Showing Suggestions

**Symptom:**
- Type in reference system field
- No autocomplete suggestions appear
- Search button doesn't work

**Root Cause:**
API not reachable from frontend, or CORS issues.

**Solution:**
```bash
# Check API is reachable
curl "http://localhost/api/autocomplete?q=Sol&mode=reference"

# Should return JSON with system suggestions
# If not, check nginx.conf has correct proxy_pass

# Check nginx logs
docker compose logs web | grep -i error

# Restart nginx
docker compose restart web
```

**Check nginx.conf:**
```nginx
location /api/ {
    proxy_pass http://api:8000/api/;  # Must match service name
    ...
}
```

**Status:** ✅ Fixed in provided nginx.conf

---

## Issue 9: Results Don't Display

**Symptom:**
- Search completes
- Loading spinner stops
- No result cards shown

**Root Cause:**
- API returning empty results
- JavaScript error during rendering
- CSS not loading properly

**Solution:**
```bash
# Check API returns data
curl -X POST http://localhost/api/search \
  -H "Content-Type: application/json" \
  -d '{"reference":"Sol","systems":["Colonia"]}'

# Should return JSON with systems array

# Check browser console for errors
# Press F12, look in Console tab

# Verify CSS loaded
# Press F12, Network tab, filter by "CSS"
```

**Status:** ⚠️ Check console for specific errors

---

## Issue 10: Database Locked Error

**Symptom:**
```
sqlite3.OperationalError: database is locked
```

**Root Cause:**
Multiple processes trying to write to SQLite database simultaneously, or improper shutdown left lock.

**Solution:**
```bash
# Stop containers
cd ~/ed-finder-FINAL-COMPLETE
docker compose down

# Check for stale lock files
ls -la data/
rm -f data/edfinder.db-shm data/edfinder.db-wal

# Restart
docker compose up -d
```

**Prevention:**
Always use `docker compose down` to stop services gracefully.

**Status:** ⚠️ Rare; proper shutdown prevents this

---

## Quick Diagnostic Checklist

Run this when something isn't working:

```bash
# 1. Container status
docker compose ps
# Both should show "Up" and "healthy"

# 2. API health
curl http://localhost/api/status
# Should return: {"status":"online",...}

# 3. Frontend accessible
curl -I http://localhost/
# Should return: HTTP/1.1 200 OK

# 4. Check logs for errors
docker compose logs api | grep -i error
docker compose logs web | grep -i error

# 5. Resource usage
docker stats ed-finder-api ed-finder-web --no-stream
# Check memory/CPU aren't maxed out

# 6. Network connectivity
docker network inspect ed-finder-net
# Both containers should be listed
```

---

## Support Resources

- **README.md:** Full documentation
- **QUICK_START.md:** Fast deployment guide
- **DEPLOY_COMMANDS.txt:** Command reference
- **Browser Console (F12):** Real-time JavaScript errors
- **Docker Logs:** `docker compose logs -f`

---

**Remember:** Most issues are fixed by either clearing browser cache or restarting containers!

---

## Issue 11: Docker Build Fails - Snapshot Extraction Error

**Symptom:**
```
failed to solve: failed to prepare extraction snapshot "extract-XXXXXXXX"
parent sha256:... does not exist: not found
```

**Root Cause:**
Corrupted Docker layer cache on the Raspberry Pi. Happens after interrupted builds or Docker updates.

**Solution:**
```bash
docker system prune -af
cd ~/ed-finder-FINAL-COMPLETE
docker compose build --no-cache
docker compose up -d
```

**Warning:** `docker system prune -af` removes ALL Docker images, containers and cache. Only run this if the build is failing.

**Status:** ✅ Fixed in ULTIMATE_FIX.sh (automatic cache clear before build)

---

## Issue 12: Frontend Shows "Backend Offline" After Successful Deploy

**Symptom:**
- Containers are running and healthy
- Browser shows red dot "Backend offline"

**Root Cause:**
Browser is serving old cached version of the page.

**Solution:**
1. `Ctrl+Shift+Delete` → Clear cached images and files → All time → Clear data
2. `Ctrl+Shift+R` hard refresh

**Status:** ✅ Documented — always clear cache after redeployment

---

## Issue 13: Search Always Returns Sol-Area Systems Regardless of Reference System

**Symptom:**
- Set reference system to a deep-space system (e.g. Praea Euq WV-W b2-2)
- Search returns Alpha Centauri, Barnard's Star, Sol-area systems
- Distance slider has no effect — always same 20 systems

**Root Cause:**
The frontend was sending `filters.distance_from_coords` to the backend, which is not a valid Spansh API filter. The Spansh systems/search API requires:
- `reference_coords` at the top level (not inside `filters`)
- `filters.distance` with `{min, max}` (not `distance_from_coords`)

**Solution:**
Fixed in v3.18.1 — both `runSearch` and `appendSearch` in `frontend/index.html` now send the correct format:
```json
{
  "filters": { "distance": { "min": 0, "max": 50 } },
  "reference_coords": { "x": 582.875, "y": 204.78, "z": 280.09 },
  "sort": [{ "distance": { "direction": "asc" } }],
  "size": 50
}
```
Backend prewarm (`_prewarm_one` in `main.py`) also updated to use the same correct format.

**Status:** ✅ Fixed in v3.18.1

---

## Issue 14: Autocomplete Dropdown Does Not Appear

**Symptom:**
- Typing a system name in the Reference System box shows no dropdown suggestions
- Must use the "Recent" button to select a previously searched system
- FIX #15 warning triggers: "System not resolved" even after typing a valid name

**Root Cause:**
The `.panel` CSS class had `overflow: hidden` which clipped the absolutely-positioned autocomplete dropdown, making it invisible even though it was rendering correctly.

**Solution:**
Fixed in v3.18.1 — changed `.panel { overflow: hidden }` to `overflow: visible` and added `border-radius: 6px 6px 0 0` to `.panel-hdr` to preserve the rounded header appearance. Also raised autocomplete `z-index` from 200 to 1000.

**Status:** ✅ Fixed in v3.18.1

---

## Issue 15: Distance Slider Changes the Distances on Existing Result Cards (v3.29 and earlier)

**Symptom:**
- Run a search and get results showing e.g. Sol area systems at 5–50 LY
- Move the Max Distance slider to a different value
- The distances shown on all result cards change, or result cards are replaced

**Root Cause:**
`_attachIncrementalSearch()` was wiring `dist-slider` and `min-dist-slider` to `_debouncedSearch` via the `change` event (fires on slider release). When you released the slider after results were loaded, a full new search ran for the new distance range, silently replacing all result cards with a completely different set of systems from the new range. The user experienced this as "distances changed" because they literally were — new systems were fetched and the old cards destroyed.

**Solution:**
Fixed in v3.30 — distance sliders are **no longer** wired to `_debouncedSearch`. Moving the distance slider only updates the label number and the filter badge counter. You must press the **SCAN** button to apply a new distance range. The slider label now shows `↵ press Search` as a reminder when you move it.

**Status:** ✅ Fixed in v3.30

---

## Issue 16: ELW/Water World/Body-Type Sliders Ignored — All Systems Pass (Phase 1 DB only)

**Symptom:**
- Set the ELW slider to minimum 1
- Search returns many results, none of which have any Earth-like worlds

**Root Cause:**
`passesBodyFilters()` had:
```javascript
const skipBodyFilters = _localDbAvailable && !_localDbHasBodies && bodies.length === 0;
```
When running against a Phase 1 local DB (systems imported but no body data), `_localDbHasBodies` was `false` and `bodies.length` was 0 (no body enrichment from Spansh yet), so `skipBodyFilters` was `true` and ALL body-type slider filters were completely bypassed. Every system passed regardless of ELW/WW/Ammonia settings.

**Solution:**
Fixed in v3.29 — the logic is inverted:
- If body sliders are set AND body data is empty → **reject** the system (can't confirm requirements)
- If body sliders are NOT set AND body data is empty → pass (distance/colony filters still apply)
- An orange warning banner is now shown when body filters are set but Phase 2 hasn't been imported

**Status:** ✅ Fixed in v3.29

---

## Issue 17: Walkable Count Inflated for Tidally Locked Bodies (Phase 2 DB)

**Symptom:**
- A system with tidally locked airless landable planets shows a higher "Walkable" count than expected
- The walkable count in the system card doesn't match the body pills

**Root Cause:**
Python `_count_body_types()` in `local_search.py` counted walkable as `landable + no atmosphere` but did not check `is_tidal_lock`. The JavaScript version (fixed in v3.28) correctly excludes tidally locked bodies: `is_landable && !atmosphere && !is_rotational_period_tidally_locked`. The mismatch meant server-side walkable counts (used for the walkable slider filter) were higher than client-side counts.

**Solution:**
Fixed in v3.30 — added tidal lock check to Python walkable counting:
```python
is_tidal = bool(b.get("is_rotational_period_tidally_locked") or b.get("is_tidal_lock"))
if (not atm or atm.lower() in ("", "no atmosphere", "none")) and not is_tidal:
    counts["walkable"] += 1
```

**Status:** ✅ Fixed in v3.30

---

## Issue 18: Changing Reference System Returns Same Systems (Demo Mode Fallback) (v3.31)

**Symptom:**
- Search from System A, get results (e.g. Proxima Coloniae, Arcturus Deep, Vega Outreach, Deneb Crossing, Sirius Haven)
- Change reference system to a distant location (e.g. Beagle Point ~65,000 LY away)
- Press Search
- **Same five systems appear** with different (but plausible-looking) distances

**Root Cause:**
The `runSearch` `catch(err)` block was rendering `generateDemoSystems()` on **any** API error.
These are five hardcoded fake systems with **random distances** based on `refSystem` coordinates.
When the backend was unreachable (or any error occurred), fake systems appeared as real results.
When you changed the reference system and searched again:
1. The error fired again
2. New random distances were generated for the **same five fake systems**
3. The result appeared to be a real (but suspicious) search result set

Because distances are computed from `refSystem` the distances *changed* when the reference changed — but the same five names always appeared. Users who had their backend misconfigured or temporarily unreachable would see this misleading fallback silently.

**Secondary bug:** `AbortError` (thrown when Search is pressed twice rapidly, aborting the first request) also fell into the catch block, causing a brief error flash.

**Solution:**
Fixed in v3.31:
- Demo rendering **completely removed** from `runSearch` catch block
- On error, only a clear error message is shown (with Docker hint)
- `AbortError` is now caught and silently ignored (lets the new search complete)
- `buildDemoBanner()` still shows at the bottom of the error so the user knows the backend is unreachable

**Status:** ✅ Fixed in v3.31

---

## Issue 19: Enrichment Overwrote Search-Result Distance (v3.31)

**Symptom:**
- Distances shown on cards after enrichment don't match the search range
- After changing reference and re-searching, distances on some cards look like they're from the wrong reference

**Root Cause:**
All three enrichment paths spread or assign the cached single-system record (`rec`) over the search result object (`sys`):
```javascript
{ ...sys, ...rec, _enriched: true }          // spread — rec.distance overwrites sys.distance
Object.assign(s, rec); s._enriched = true;    // assign — same problem
```
The `rec` object fetched from `/api/systems/batch` may contain a stale `distance` field from a prior cached Spansh response (e.g. distance from a different reference). This overwrites `sys.distance` which was correctly computed relative to the current `refSystem` by the search query.

**Solution:**
Fixed in v3.31 — every enrichment now explicitly restores the original `sys.distance`:
```javascript
{ ...sys, ...rec, distance: sys.distance, _enriched: true }
// and for Object.assign:
const _savedDist = s.distance; Object.assign(s, rec); s.distance = _savedDist; s._enriched = true;
```

**Status:** ✅ Fixed in v3.31

---

## Issue 20: Deep Scan Blocked When Reference System is Sol (v3.31)

**Symptom:**
- Deep Scan shows "Please select a reference system first" alert when reference is Sol
- Sol has coordinates (0, 0, 0), so `refSystem.x === 0`

**Root Cause:**
`runDeepScan()` used `!refSystem.x` as a guard — which is `true` when `x === 0` (falsy), blocking deep scan from the galaxy's most common starting system.

**Solution:**
Fixed in v3.31 — guard changed to `refSystem.x === undefined` so Sol (0, 0, 0) is valid:
```javascript
if (!refSystem || refSystem.x === undefined || refSystem.y === undefined || refSystem.z === undefined)
```

**Status:** ✅ Fixed in v3.31
