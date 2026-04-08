# ED:Finder — QUICK START GUIDE

## 🎯 What You Need to Know

**This package contains a WORKING version of ED:Finder!**

The problem with all the previous v3.20 archives was that the frontend `index.html` was **incomplete** - it was missing all the JavaScript code needed to connect to the API and display results.

This package uses the **v3.18 frontend** which is COMPLETE and WORKING.

## 🚀 Quick Deployment (5 Minutes)

### Step 1: Transfer to Your Pi

**From Windows:**
```cmd
scp ed-finder-WORKING.tar.gz mightyraith@192.168.0.115:~/
```

**Or download directly on Pi:**
```bash
# If you have the file hosted somewhere, wget it
# Or use the file transfer method you prefer
```

### Step 2: Deploy

SSH into your Pi:
```bash
ssh mightyraith@192.168.0.115
```

Then run:
```bash
cd ~
tar -xzf ed-finder-WORKING.tar.gz
cd ed-finder-WORKING
./DEPLOY.sh
```

The script will automatically:
- ✅ Stop old containers
- ✅ Backup current installation
- ✅ Deploy new version
- ✅ Build Docker images
- ✅ Start services
- ✅ Run tests

### Step 3: Access the UI

**Open your browser:**
- Primary URL: http://raspberrypi.local
- Alternative: http://192.168.0.115

**IMPORTANT: Clear cache!**
1. Press `Ctrl+Shift+Delete`
2. Select "All time"
3. Check "Cached images and files"
4. Click "Clear data"

**Hard refresh:**
- Press `Ctrl+Shift+R`

### Step 4: Verify It Works

You should see:
- ✅ **Green status light** (not yellow blinking)
- ✅ All tabs clickable
- ✅ Search works
- ✅ Results display

### Quick Test in Browser Console

Press F12 to open console, then paste:
```javascript
fetch('/api/status').then(r=>r.json()).then(d=>console.log('✅ Works!',d))
```

You should see:
```
✅ Works! {status: "online", version: "3.16.0", cache_stats: {...}}
```

## 🔧 If It STILL Doesn't Work

### 1. Check Port 80
InfluxDB might be using it:
```bash
sudo systemctl stop influxd
cd ~/ed-finder-WORKING
docker compose restart web
```

### 2. Try a Different Browser
- Firefox (fresh install has no cache)
- Chrome incognito mode
- Edge private window

### 3. Check Logs
```bash
cd ~/ed-finder-WORKING
docker compose logs --tail 50
```

### 4. Verify Services
```bash
cd ~/ed-finder-WORKING
docker compose ps
curl http://localhost:80/api/status
```

## 📊 Common Commands

**View logs:**
```bash
cd ~/ed-finder-WORKING
docker compose logs -f
```

**Restart services:**
```bash
cd ~/ed-finder-WORKING
docker compose restart
```

**Stop everything:**
```bash
cd ~/ed-finder-WORKING
docker compose down
```

**Start again:**
```bash
cd ~/ed-finder-WORKING
docker compose up -d
```

## ❓ Why This Version Works

1. **Complete Frontend**: v3.18 has ALL the JavaScript functions
2. **Bridge Networking**: Proper Docker networking (not host mode)
3. **Correct Nginx Config**: Proxies to `api:8000` (not `localhost:8000`)
4. **CORS Fixed**: `ALLOWED_ORIGINS=*` and proper headers
5. **Tested Configuration**: This exact setup works

## 📦 What's in the Package

```
ed-finder-WORKING/
├── frontend/           ← COMPLETE v3.18 frontend (6,895 lines)
├── backend/            ← Your FastAPI backend
├── docker-compose.yml  ← Bridge networking
├── nginx.conf          ← Correct API proxy
├── .env                ← Environment variables
├── DEPLOY.sh           ← Automated deployment
├── README.md           ← Full documentation
└── QUICK_START.md      ← This file
```

## 🎉 Success Criteria

Your installation works when you see:

1. **Green status light** in header
2. **"Backend online"** message
3. **Search suggestions** appear when typing
4. **System cards** display when clicking search
5. **No JavaScript errors** in console (F12)

## 💡 Pro Tips

1. **Use `raspberrypi.local`** instead of the IP address
2. **Clear cache** completely when testing changes
3. **Use incognito mode** to bypass cache issues
4. **Check console** (F12) for any error messages
5. **Monitor logs** with `docker compose logs -f`

## 📞 Need Help?

If this STILL doesn't work:

1. **Screenshot** the browser showing the issue
2. **Console output** (F12 → Console tab)
3. **Network tab** showing `/api/status` request
4. **Pi output** from these commands:
   ```bash
   cd ~/ed-finder-WORKING
   docker compose ps
   docker compose logs --tail 100
   curl -v http://localhost:80/api/status
   ```

---

**This is the COMPLETE, WORKING version with the v3.18 frontend that has ALL required JavaScript!**
