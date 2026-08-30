# V3 emergency runtime

This is a separate runtime lane for the retained external PostgreSQL 18 database. It never creates PostgreSQL, restores V2 data, applies the V2 migration manifest, changes DNS, or exposes a public listener by default.

## Services and boundaries

The default start boots `redis`, `api`, `eddn`, and `proxy`. Redis uses AOF (`everysec`) plus RDB snapshots on a named volume. `eddn` is the real `apps/eddn/src/eddn_listener.py`; the API also retains its existing gated simulation-ingest task. NATS is absent because no repository process uses it. There is no generic worker or sleeping placeholder. The real maintenance image is available only through the `maintenance` profile and is deliberately excluded from normal start because it performs database writes and requires a separately supplied maintenance role.

Frontier OAuth is disabled by forcing all Frontier credentials and owner IDs empty. Do not enable it until the retained Phase 4C identity contract/schema is verified. Unauthenticated read routes use the externally supplied app/read-only roles.

## Prepare and validate privately

Build `frontend/dist` using the normal pinned frontend build first. Copy `deploy/v3/env.example` to a host-only file such as `/etc/edfinder/v3.env`, replace the sentinels with owner-provided external PG18 role URLs, then `chmod 600 /etc/edfinder/v3.env`. Do not paste the file or resolved Compose output into tickets or logs: URLs contain secrets.

```sh
export V3_ENV_FILE=/etc/edfinder/v3.env
scripts/operator/v3-runtime.sh validate
scripts/operator/v3-runtime.sh start
scripts/operator/v3-runtime.sh status
scripts/operator/v3-runtime.sh smoke
curl -fsS http://127.0.0.1:8080/nginx-healthz
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS 'http://127.0.0.1:8080/api/systems/autocomplete?q=Sol&limit=1'
docker compose --project-name edfinder-v3 --env-file "$V3_ENV_FILE" -f deploy/v3/compose.yml exec -T eddn python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9091/healthz', timeout=3).status)"
```

Stop deterministically with `scripts/operator/v3-runtime.sh stop`. This preserves the Redis volume.

## Owner-controlled cutover

Keep `V3_BIND_ADDRESS=127.0.0.1` during validation and reach it through an SSH tunnel if remote review is needed. A later owner-approved edge/cutover procedure may set a specific non-loopback address together with `V3_ALLOW_PUBLIC_BIND=yes`; that flag only removes the script guard. TLS, firewall, DNS, OAuth redirect URIs, and public smoke checks remain separate owner actions and are intentionally not automated here.

## Blockers

Owner-only external PG18 app, read-only, and EDDN role URLs are required. The maintenance role is optional and must not be enabled until its write permissions and retained-database schedules are reviewed. Phase 4C identity artifacts are required before OAuth can be enabled. This lane intentionally has no schema bootstrap or migration command.
