# nginx snippet — required for v2 deploy + optional codegen

The `deploy_v2.sh` script handles everything except one upstream nginx
config tweak: by default the legacy frontend's `try_files ... /index.html;`
catches `/openapi.json` before it can reach the backend. Add this snippet
inside your `server { listen 443 ssl; server_name ed-finder.app; }`
block, **before** the SPA fallback location:

```nginx
# Forward FastAPI doc / schema endpoints to the backend.
# Required for `yarn types:gen` and for human inspection at /docs.
location = /openapi.json { proxy_pass http://api:8000/openapi.json; }
location = /docs          { proxy_pass http://api:8000/docs;          }
location = /redoc         { proxy_pass http://api:8000/redoc;         }
```

After adding it:
```
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

Then re-run `deploy_v2.sh --gen-types` to refresh `src/types/api.gen.ts`
from the live schema.

# Optional: parity flip (root → v2)

When v2 has soaked enough that you trust it (a day or three of dual-running),
flip the default by editing the same nginx server block:

```nginx
# OLD:
# location / { root /var/www/html; try_files $uri $uri/ /index.html; }

# NEW:
location = /        { return 302 /v2/; }
location  /v1/      { alias /var/www/html/; try_files $uri $uri/ /v1/index.html; }
location  /v2/      { alias /var/www/html-v2/; try_files $uri $uri/ /v2/index.html; }
```

Reload nginx. The legacy app stays reachable at `/v1/` for one week as
rollback insurance, then you can `rm -rf /var/www/html`.
