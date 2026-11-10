# Local real-data Galaxy map acceptance

The normal Product E2E seed is small and deterministic. This optional Product
browser run exercises the **same release web image, normal V3 API entrypoint,
PostgreSQL 18 and Redis** with a separate, populated local database. It is for
camera, density and star rendering before a release. Review Lab keeps its own
synthetic failure scenarios and is not used here.

## Data requirement

Provide an already prepared, sanitized PostgreSQL 18 custom-format snapshot for
this isolated database. It must contain a coherent V3 schema, a published real
catalogue generation, the matching published spatial density pyramid and the
Finder data needed for an ordinary Explore search. Include Achenar and enough
nearby systems for the exact-star view. Preserve the generation and source
metadata. Do not include account, journal, auth, token or personal tables.

The snapshot is **not** checked into Git. Follow the [refresh and coverage
contract](map-snapshot-refresh.md) to capture and review a new one. A bounded
camera-path catalogue is valid only for those paths; it is not evidence for
arbitrary navigation elsewhere in the galaxy. The local Compose file never
contacts or imports from production by itself.

The snapshot producer must validate that this selected export restores with
the published pointers intact. A table-only dump lacking dependent V3 schema
and metadata will fail the API even if `pg_restore` exits successfully.

## Windows run

From the repository root, with Docker Desktop running and a current checkout:

```powershell
$env:MAP_TEST_BUILD_SHA = (git rev-parse HEAD).Trim()
docker compose -f docker-compose.map-test.yml up -d map-postgres map-redis
$mapPg = (docker compose -f docker-compose.map-test.yml ps -q map-postgres).Trim()
docker cp 'C:\path\to\sanitized-map-snapshot.dump' "${mapPg}:/tmp/map-snapshot.dump"
python scripts/dev/map_snapshot_check.py archive --manifest 'C:\path\to\map-snapshot.json' --dump 'C:\path\to\sanitized-map-snapshot.dump'
docker compose -f docker-compose.map-test.yml exec -T map-postgres pg_restore --no-owner --no-acl --exit-on-error -U map_test_user -d edfinder_map_test /tmp/map-snapshot.dump
python scripts/dev/map_snapshot_check.py local --manifest 'C:\path\to\map-snapshot.json'
docker compose -f docker-compose.map-test.yml up -d --build map-api map-web
Invoke-RestMethod http://127.0.0.1:4175/api/health
```

Open `http://127.0.0.1:4175/explore` to inspect the actual release bundle. Then
run the non-fixtured Product map check:

```powershell
Set-Location apps/web
corepack pnpm install --frozen-lockfile
corepack pnpm exec cypress run --browser chrome --config-file cypress.map-real-data.config.ts
```

It requires more than 1,000 real density cells at galaxy scale and more than
100 exact stars near Achenar, then checks six wheel zoom steps, pan, tilt,
retained canvas, JavaScript failures and compositor captures. Screenshot/video
evidence is under `apps/web/cypress/artifacts/map-real-data/`. Compare those
captures with the owner's six map recordings at the same viewport and backend;
pixel presence alone is not a visual match or a frame-time measurement.

To stop the stack while retaining the local data, run
`docker compose -f docker-compose.map-test.yml down` from the repository root.
The separate `edfinder-map-test` volume is deliberately retained for the next
run. **Restore into a fresh empty volume** when replacing the archive: the
existing database has published rows and `pg_restore` cannot safely overlay
them. Keep the previous accepted archive until the new one passes. Remove the
disposable volume only as an intentional local reset after checking the exact
Compose project and volume name.

## Boundaries

- The API is `edfinder_api.main:app`; no review-only controls or fixtures are
  present. The web image uses the same `apps/web/Dockerfile` and F4 flag as the
  Product browser lane.
- Only the web and database maintenance port bind to loopback. There are no
  production URLs, credentials, database mounts or background EDDN ingest.
- This run is opt-in because a representative snapshot is large and may change.
  The normal seeded Chrome/Firefox E2E and Review Lab remain mandatory CI gates.
- A restored snapshot tests the captured data generation. It does not prove a
  later live generation, an unsampled edge of the galaxy or hardware GPU frame
  pacing. The saved build SHA and snapshot manifest identify what was tested.
- The archive checker fails on an unreviewed `TABLE DATA` inventory, an
  unexpected schema, an archive hash mismatch or a mismatched published
  pointer. It does not replace the operator's column-level privacy review.

