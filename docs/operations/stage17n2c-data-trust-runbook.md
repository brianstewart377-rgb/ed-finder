# Stage 17N.2c/17N.2d Data Trust Runbook

This runbook is for the next production continuation after the nullable-coordinate
and rating-version deployment. It is intentionally conservative: prefer small
dirty rebuilds, verify after each step, and do not run a high-worker full rebuild
until production has proven the new settings under load.

Stage 17N.2d extended this with a repo-wide reliability audit. The code now also
preserves nullable population in API/search contracts, bumps Redis cache key
versions for data-trust payloads, rejects partial EDDN `StarPos` triples, avoids
treating missing EDDN `Population` as real zero, and reports dirty rebuild
progress with an unknown total instead of a fake percentage.

## Safe Order

1. Apply `sql/020_rating_version.sql`.
2. Apply `sql/022_rating_dirty_triggers.sql`.
3. Deploy code. If production already has partially applied migrations, deploy with `--skip-migrations` and apply SQL manually.
4. Apply `sql/019_nullable_coords.sql`.
5. If the coordinate cleanup times out, rerun only the cleanup with timeout-disabled session settings:

   ```sql
   SET statement_timeout = 0;
   SET lock_timeout = 0;

   UPDATE systems
      SET x = NULL, y = NULL, z = NULL
    WHERE x = 0 AND y = 0 AND z = 0
      AND id64 != 10477373803;
   ```

6. Analyze systems:

   ```sql
   ANALYZE systems;
   ```

7. Clear Redis cache patterns for search, autocomplete, system detail, body,
   galaxy, cluster, map, status, and OpenGraph payloads.
8. Run a small ratings smoke rebuild:

   ```bash
   BATCH_SIZE=1000 RATING_DIRTY_CLEANUP_CHUNK=1000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 1 --chunk 1000 --limit 10
   ```

9. Run a gentle dirty rebuild:

   ```bash
   BATCH_SIZE=1000 RATING_DIRTY_CLEANUP_CHUNK=1000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 1 --chunk 1000
   ```

   If stable, a slightly larger pass is acceptable:

   ```bash
   BATCH_SIZE=2000 RATING_DIRTY_CLEANUP_CHUNK=5000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 2 --chunk 5000
   ```

10. Verify `rating_version` and capped-score behavior.
11. Run nightly maintenance:

    ```bash
    docker compose run --rm maintenance run_maintenance.sh nightly
    ```

12. Clear Redis caches again.

## Rating Dirty Triggers

Stage 17N.2c-R makes dirty marking explicit and deferred. Import/EDDN writes
must never recalculate ratings inline; they only set `systems.rating_dirty =
TRUE`, then `build_ratings.py --dirty` performs the recalculation.

These changes mark the affected system dirty:

- System fields in the current or conservative rating contract:
  `main_star_type`, `main_star_subtype`, `main_star_is_scoopable`,
  `updated_at`, economy/population/colonisation status, body-data flags, and
  body count/quality flags.
- Body insert/delete.
- Body rating fields on real change: `body_type`, `subtype`, `is_main_star`,
  `distance_from_star`, `is_tidal_lock`, landable/terraformable/special-world
  flags, signal counts, `spectral_class`, and `is_scoopable`.
- EDDN main-star scans now update `systems.main_star_type`; EDDN body upserts
  preserve conflict updates for rating fields such as `distance_from_star`.

These changes do not mark `rating_dirty` today:

- Station-only imports and station/body association backfills. The v3.4 rating
  builder does not read `stations` or `station_body_links`. These paths can make
  system-detail and planner/occupied-slot cache payloads stale until TTL expiry
  or an explicit cache clear, but they do not change rating math.
- Body scan facts in `body_scan_facts`; the current rating builder reads the
  canonical `bodies` table.

## Rebuild Warnings

Avoid this in production unless a prior gentle run has proven connection and DB
headroom:

```bash
./scripts/run_import.sh build_ratings.py --rebuild --workers 12
```

The safer defaults for continuation are:

- `--dirty`
- `--workers 1` or `--workers 2`
- `--chunk 1000` or `--chunk 5000`
- `BATCH_SIZE=1000` or `BATCH_SIZE=2000`
- `RATING_DIRTY_CLEANUP_CHUNK=1000` or `5000`

## Verification Queries

Fake non-Sol origin rows:

```sql
SELECT COUNT(*) AS fake_non_sol_origin_count
FROM systems
WHERE id64 != 10477373803
  AND x = 0 AND y = 0 AND z = 0;
```

Exioce coordinates:

```sql
SELECT id64, name, x, y, z
FROM systems
WHERE id64 = 2008132031194;
```

Expected:

```text
x = 78.5
y = -100.25
z = 16.78125
```

Rating version distribution:

```sql
SELECT rating_version, COUNT(*)
FROM ratings
GROUP BY rating_version
ORDER BY COUNT(*) DESC;
```

Exioce rating version and score caps:

```sql
SELECT
  system_id64,
  rating_version,
  score_agriculture,
  score_refinery,
  score_industrial,
  score_hightech,
  score_military,
  score_tourism,
  score_extraction
FROM ratings
WHERE system_id64 = 2008132031194;
```

Dirty count:

```sql
SELECT COUNT(*) AS dirty_count
FROM systems
WHERE rating_dirty = TRUE;
```

Specific dirty check:

```sql
SELECT id64, name, rating_dirty, updated_at
FROM systems
WHERE id64 = ...;
```

Verify a recalculated rating row:

```sql
SELECT rating_version, updated_at
FROM ratings
WHERE system_id64 = ...;
```

v3.4 count:

```sql
SELECT COUNT(*) AS v34_count
FROM ratings
WHERE rating_version = '3.4';
```

Multiple capped core economies:

```sql
SELECT COUNT(*) AS capped_core_economies
FROM ratings
WHERE rating_version = '3.4'
  AND (
    (score_agriculture = 100)::int +
    (score_refinery = 100)::int +
    (score_industrial = 100)::int +
    (score_hightech = 100)::int +
    (score_military = 100)::int +
    (score_tourism = 100)::int +
    (score_extraction = 100)::int
  ) >= 3;
```

Galaxy-wide distance should be null, not `0.0`:

```bash
curl -sS https://ed-finder.app/api/local/search \
  -H 'content-type: application/json' \
  --data '{"galaxy_wide":true,"filters":{"population":{"value":0,"comparison":"equal"}},"size":1,"from":0}' \
  | jq '.results[0].distance'
```

API health:

```bash
curl -fsS https://ed-finder.app/api/health
```

## Dirty-Flag Recovery

If ratings have been written successfully but dirty cleanup timed out, clear only
systems that have a current v3.4 rating. Repeat the chunk until it updates zero
rows:

```sql
SET statement_timeout = 0;
SET lock_timeout = 0;

WITH clean AS (
  SELECT s.id64
  FROM systems s
  JOIN ratings r ON r.system_id64 = s.id64
  WHERE s.rating_dirty = TRUE
    AND r.rating_version = '3.4'
  LIMIT 1000
)
UPDATE systems s
   SET rating_dirty = FALSE
  FROM clean
 WHERE s.id64 = clean.id64;
```

Do not clear dirty flags for systems without a successful current rating row.

## Redis Cache Clear

Use the production Redis service from the app host:

```bash
docker compose exec redis redis-cli --scan --pattern 'search:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'ac:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'sys:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'body:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'galaxy:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'cluster:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'map:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'status:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'og:*' \
  | xargs -r docker compose exec -T redis redis-cli del
```

Current code also version-bumps fresh payloads:

| Payload | Prefix |
|---|---|
| Local search | `search:v4:*` |
| Autocomplete/reference systems | `ac:v3:*` |
| System detail/batch detail | `sys:v3:*` |
| Body detail | `body:v2:*` |
| Galaxy search | `galaxy:v4:*` |
| Cluster search | `cluster:v4:*` |

The admin cache-clear endpoint scans broad prefixes (`search:*`, `ac:*`, etc.)
so it removes both old and new versions.

Small EDDN/import updates do not run Redis scans. Search, autocomplete, system,
body, map, cluster, archetype, and simulation payloads may remain stale until
their TTL expires. For operator-verified data refreshes, clear only the relevant
prefixes above after a dirty ratings pass succeeds.

## Stage 17N.2d Reliability Audit Findings

Classified findings:

- **Unsafe and fixed**: EDDN `Location`/`FSDJump` and `FSSDiscoveryScan`
  accepted partial `StarPos` triples. They now write coordinates only when all
  three axes parse as numbers.
- **Unsafe and fixed**: EDDN treated missing `Population` as `0`, which could
  overwrite a known population. Missing population now means no population
  update; brand-new inserts use `COALESCE($7, 0)` only to satisfy the current
  `systems.population NOT NULL DEFAULT 0` schema.
- **Unsafe and fixed**: API/search serializers and frontend list types forced
  unknown population to `0`. Pydantic search/detail/autocomplete models and
  frontend table/watchlist/pinned types now allow `null`.
- **Unsafe and fixed**: dirty rebuild progress used a fake total of `1` in
  `--dirty` mode, producing misleading huge percentages. Unknown dirty totals
  now render as `done / unknown`; `--limit` runs still show a bounded total.
- **Unsafe and fixed**: system-detail station rows did not expose `body_name`
  even though the DB stores it. The API now includes nullable `body_name`, which
  is needed for occupied-slot modelling.
- **Safe / intended**: Sol at `(0,0,0)`, same-reference frontend
  `formatDistance(0, { allowZero: true })`, score/progress count fallbacks, CSS
  color values, and fixture origin triples used in tests.
- **Dead / legacy path**: `_redesign/` mock/discover components are not the
  active v2 application surface; findings there were not patched.
- **Needs follow-up**: `systems.population` remains `NOT NULL DEFAULT 0`, so DB
  storage still cannot distinguish unknown population from true zero for the
  main systems table. UI and API contracts are now conservative, but a future
  migration is required for full population nullability.

## Existing Infrastructure / Occupied-Slot Awareness

Current DB/API state:

- `systems` exists and exposes nullable `x/y/z` after `019_nullable_coords.sql`.
- `bodies` exists with `id`, `system_id64`, `name`, `body_type`, `subtype`,
  `distance_from_star`, landability/terraforming flags, signals, mass/radius,
  gravity, and scan/mapping values.
- `stations` exists with `id`, `system_id64`, `name`, `station_type`,
  `distance_from_star`, nullable `body_name`, landing pad, service booleans,
  primary/secondary economy, faction/allegiance/government, and `updated_at`.
- `/api/system/{id64}` exposes `bodies` and `stations`. Stage 17N.2d now
  includes station `body_name`, `market_id` (alias of current station `id`),
  primary/secondary economy, and the core refuel/repair/rearm service flags.

Frontend planner behaviour:

- Existing station rows are converted into an internal `existing` structure
  model. They are not inserted into the user Build Plan.
- Exact body id/local body id is used first when present.
- Exact `body_name` is used when it matches one known body.
- A unique non-zero `distance_from_star` match is allowed only as `inferred`.
- Ambiguous or missing association renders as unresolved existing
  infrastructure.
- Coriolis, Orbis, Ocellus, Outpost, and AsteroidBase occupy orbital capacity.
- PlanetaryPort, PlanetaryOutpost, and surface/settlement-like types occupy
  surface capacity.
- MegaShip, FleetCarrier, and Unknown station types are shown as unresolved
  rather than forced into a colony slot.
- Raven canvas shows existing slots with established/solid styling, planned
  slots with user-plan styling, projected slots with ghost/dashed styling, and
  unresolved stations in a compact area below the map.
- Add Orbit/Add Surface uses remaining capacity after existing + planned
  occupancy. A lane with no remaining capacity disables Add with
  "No empty orbital slots" or "All surface slots occupied".

Stage 17N.2d-H normalized source of truth:

- apply `sql/021_station_body_links.sql` before relying on persisted occupied
  slot association
- `/api/system/{id64}` now emits `body_id`, `lane`, `association_status`,
  `association_confidence`, `association_source`, and `resolver_notes` for
  stations
- confirmed associations can occupy slots normally
- inferred associations are displayed in lane but marked for verification
- unresolved or unknown-lane infrastructure remains visible outside body lanes

Manual dry-run:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --dry-run --limit 10
```

Apply one known system:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --apply --system-id64 2008132031194
```

Gentle batch:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/backfill_station_body_links.py --apply --limit 1000
```

Default backfill behaviour does not overwrite existing confirmed links.

Association diagnostics:

```sql
SELECT association_status, association_confidence, count(*)
FROM station_body_links
GROUP BY association_status, association_confidence
ORDER BY association_status, association_confidence;

SELECT s.station_type, count(*)
FROM station_body_links l
JOIN stations s ON s.id = l.station_id
WHERE l.association_status = 'unresolved'
GROUP BY s.station_type
ORDER BY count(*) DESC;

SELECT lane, association_status, association_confidence, count(*)
FROM station_body_links
WHERE lane IN ('orbital', 'surface')
GROUP BY lane, association_status, association_confidence
ORDER BY lane, association_status, association_confidence;
```

What is missing for occupied slots:

- no native `stations.body_id`
- no separate `market_id` column; current `stations.id` is populated from
  Spansh `id`/`marketId`/`market_id` and should be verified before treating it
  as canonical market identity
- no exact station/body source for many historical station rows
- no manual correction/Architect-observed truth workflow yet
- no permanent-colony-infrastructure model for fleet carriers or megaships

Concrete follow-up plan:

1. Backfill `station_body_links` in small batches and monitor unresolved counts.
2. Backfill exact `body_id` values where source data provides them.
3. Verify whether `stations.id` is always market id or split a true
   `market_id` column.
4. Move the resolver to backend diagnostics once enough body ids are available.
5. Add production monitoring for unresolved station counts by station type.

## Stop Conditions

Pause the rebuild and inspect logs if any of these occur:

- repeated worker connection closures
- repeated dirty cleanup failures after retries
- rising `rating_dirty` count while rating writes are not increasing
- `rating_version = '3.4'` count stops increasing during a dirty rebuild
- fake non-Sol origin count is non-zero after coordinate cleanup
