# nginx snippet — optional codegen note

The old `/v2/` deployment flow is retired now that the frontend is served at `/`.
This file remains only for the optional OpenAPI forwarding tweak: by default
the SPA fallback can catch `/openapi.json` before it can reach the backend. Add this snippet
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

Then re-run `yarn types:gen` from `frontend` to refresh `src/types/api.gen.ts`
from the live schema.
