# ED:Finder Quick Start Guide

## One-Command Deployment (Fastest)

### On your Raspberry Pi, run:

```bash
cd ~ && tar -xzf ed-finder-FINAL-COMPLETE.tar.gz && cd ed-finder-FINAL-COMPLETE && ./ULTIMATE_FIX.sh
```

**That's it!** The script will:
1. Stop old containers
2. Backup existing installation
3. Fix the FastAPI import issue
4. Build containers
5. Start services
6. Verify deployment

## Step-by-Step (If you prefer manual control)

### 1. Transfer to Pi (from Windows)

```cmd
scp "%USERPROFILE%\Downloads\ed-finder-FINAL-COMPLETE.tar.gz" mightyraith@192.168.0.115:~/
```

### 2. Extract

```bash
cd ~
tar -xzf ed-finder-FINAL-COMPLETE.tar.gz
cd ed-finder-FINAL-COMPLETE
```

### 3. Deploy

```bash
./ULTIMATE_FIX.sh
```

**OR** manually:

```bash
# Fix import
sed -i 's/from fastapi.middleware.base/from starlette.middleware.base/g' backend/main.py

# Clean old containers
docker ps -a | grep ed-finder | awk '{print $1}' | xargs -r docker rm -f

# Deploy
docker compose build --no-cache
docker compose up -d
```

### 4. Verify

```bash
docker compose ps           # Check status
curl http://localhost/api/status  # Test API
```

### 5. Access

- http://raspberrypi.local
- http://192.168.0.115

**Clear cache** (Ctrl+Shift+Delete) and **hard refresh** (Ctrl+Shift+R)

## Expected Outcome

✅ Green status light  
✅ "Backend online" message  
✅ All tabs clickable  
✅ Search shows suggestions  
✅ Results display as cards  

## If Something Goes Wrong

```bash
# View logs
docker compose logs api
docker compose logs web

# Restart
docker compose restart

# Nuclear option (clean restart)
docker compose down
docker compose up -d --build
```

## Common Issues

| Symptom | Fix |
|---------|-----|
| Yellow "Connecting..." | Wait 30s, refresh |
| Blank page | Clear cache, hard refresh |
| Port 80 in use | `sudo systemctl stop influxd` |
| Container conflict | `docker ps -a \| grep ed-finder \| awk '{print $1}' \| xargs -r docker rm -f` |

## Support

Need help? Check:
- `README.md` - Full documentation
- `KNOWN_ISSUES.md` - Detailed troubleshooting
- Browser console (F12) for errors

---

**Happy exploring, Commander! o7** 🚀
