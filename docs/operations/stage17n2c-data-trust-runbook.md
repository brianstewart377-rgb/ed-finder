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

## Rating Generation Names

- **Ratings v3.4 Best-Build Potential** is the canonical current scorer.
  `build_ratings.py` writes `rating_version = '3.4'` for rows rebuilt by the
  current engine.
- **Pre-v3.4 Unversioned Ratings** means any row where
  `rating_version IS NULL`. This is the correct operational name for the legacy
  bucket.
- The unversioned bucket may contain more than one historical scorer
  generation. Production data can reliably distinguish `3.4` rows from
  unversioned rows, but it cannot safely identify which exact pre-`3.4`
  generation produced a given unversioned row.
- If production still shows both `rating_version = '3.4'` and
  `rating_version IS NULL`, treat that as an incomplete ratings rebaseline, not
  as an acceptable steady state.

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

10. Verify `rating_version` distribution and capped-score behavior.
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

Station-only imports and station/body association backfills do not affect v3.4
rating math directly, but they can affect planner role/occupied-slot
presentation. Stage 17N.2d-P therefore makes dirty marking an explicit
operator choice in the coordinated backfill CLI: use `--mark-dirty` when
trusted station facts or confirmed links are applied and downstream planner
payloads should be rebuilt/cleared. The script still never runs rating
calculation inline.

## Scheduled Dirty Ratings Maintenance

Stage 17N.2d-R keeps EDDN ingestion and rating recalculation separate:

- EDDN marks affected rows with `systems.rating_dirty = TRUE`.
- Host cron periodically runs `scripts/run_dirty_ratings_if_needed.sh`.
- The script runs `build_ratings.py --dirty` only when the dirty queue is at or
  above `DIRTY_RATING_THRESHOLD`.
- The script uses `flock` on `/tmp/ed-finder-dirty-ratings.lock` by default, so
  two scheduled invocations of this script cannot overlap.

This scheduled job only maintains the deferred dirty queue. It does not
complete a backlog of **Pre-v3.4 Unversioned Ratings** by itself unless those
systems have also been marked dirty or a broader rebuild/rebaseline run is
performed intentionally.

The existing maintenance sidecar is not the production path for this job. It is
a small `postgres:16-alpine` cron container for `psql` maintenance tasks. It
does not mount importer source, does not include importer Python dependencies,
and does not have Docker Compose access to start the importer service. Keep this
as a host cron that invokes the importer container from the repo checkout.

`scripts/deploy_main.sh` rebuilds/restarts the long-lived `api`, `eddn`, and
`maintenance` services. It does not install or modify host crontabs. Install the
dirty-ratings cron once on the production host after deploying code:

```cron
*/30 * * * * cd /opt/ed-finder && DIRTY_RATING_THRESHOLD=250 DIRTY_RATING_WORKERS=2 DIRTY_RATING_CHUNK=1000 bash scripts/run_dirty_ratings_if_needed.sh >> /data/logs/dirty-ratings.log 2>&1
```

Scheduled-equivalent manual run:

```bash
cd /opt/ed-finder
DIRTY_RATING_THRESHOLD=250 DIRTY_RATING_WORKERS=2 DIRTY_RATING_CHUNK=1000 \
  bash scripts/run_dirty_ratings_if_needed.sh
```

Safe smoke test that should only count and skip unless the queue is enormous:

```bash
cd /opt/ed-finder
DIRTY_RATING_THRESHOLD=999999999 bash scripts/run_dirty_ratings_if_needed.sh
```

Validation SQL:

```sql
SELECT COUNT(*) FROM systems WHERE rating_dirty = TRUE;

SELECT rating_version, COUNT(*)
FROM ratings
GROUP BY rating_version
ORDER BY COUNT(*) DESC;
```

Interpretation:

- `rating_version = '3.4'` rows are **Ratings v3.4 Best-Build Potential**.
- `rating_version IS NULL` rows are **Pre-v3.4 Unversioned Ratings**.
- A mixed result set means the ratings rebaseline is still incomplete even if
  the dirty queue is currently small.

Log checks:

```bash
tail -100 /data/logs/dirty-ratings.log
grep -E "start time=|dirty_count=|below threshold|dirty ratings rebuild command|exit_status=|another dirty ratings maintenance run" /data/logs/dirty-ratings.log | tail -100
```

The script does not clear Redis caches automatically. Cache clears remain a
separate operator action after a verified successful rebuild when freshness is
needed before TTL expiry.

## Body Order And Ring Facts

Stage 17N.2d-M changes body display order to natural Elite hierarchy order.
Distance can still be displayed, but it must not be used as the primary planner
body order. Nested names such as `Exioce 4 a a` are valid child bodies and must
sort under `Exioce 4 a`, before sibling `Exioce 4 b`.

Stage 17N.2d-N adds `body_rings` for provenance-backed ring facts. Ring facts
are tri-state operationally:

- One or more trusted `body_rings` rows for a body means ringed.
- `body_scan_facts` row from `eddn_scan` with `is_ringed = true` is source
  evidence only; consumers treat a body as ringed only when a trusted
  `body_rings` row is joined to the local `bodies.id`.
- `body_scan_facts` row from `eddn_scan` with `is_ringed = false` means scanned
  and not ringed.
- Missing scan facts, or partial non-scan facts, mean unknown. Do not count
  unknown as no-rings evidence.
- Ring type/class must come from source payload fields. Do not infer it from
  body subtype text, rating summaries, or archetype/topology booleans.
- `body_rings.body_id` is always the ED-Finder local `bodies.id` BIGINT, or
  `NULL` while unresolved. EDDN Journal `BodyID` is source identity and belongs
  in `body_rings.source_body_id`; it must not be written into `body_rings.body_id`
  unless it has been resolved to an actual local `bodies.id` row.

The production Stage 17N.2d-M investigation observed `scan_fact_rows = 0`,
`ringed_bodies = 0`, `non_ringed_bodies = 0`, and `unknown_ring_state = 0`.
That means ring coverage is absent, not that all bodies are unringed. Spansh
imports now populate `body_rings` only from explicit Spansh ring arrays.
EDDN `Journal/Scan` ingestion writes ring rows from explicit `Rings` payloads
only when exact `(SystemAddress, BodyName)` resolution finds exactly one local
body. Unresolved EDDN ring payloads are skipped from `body_rings` so they cannot
inflate API ring state, ratings `ring_count`, or planner ringed-body traits.
Scan-derived `is_ringed=false` is written only when a trusted full scan
explicitly carries an empty `Rings` array. Historical coverage still requires a
separate safe population/backfill plan; do not treat empty production
`body_scan_facts` or `body_rings` as no-rings evidence.

Stage 17N.2d-P found legacy EDDN rows where Journal `BodyID` had been stored in
`body_rings.body_id`. Before any wider dirty ratings rebuild, run the identity
repair dry-run and review the summary:

```bash
python scripts/repair_eddn_ring_identity.py
```

Apply only after the dry-run counts are reviewed:

```bash
python scripts/repair_eddn_ring_identity.py --apply
```

The repair updates `eddn_scan` rows whose same-system `body_name` matches
exactly one local body, preserving the legacy source integer in
`source_body_id`, and marks affected systems dirty for a later controlled
ratings rebuild. Rows with no exact local body match are not deleted; current
API/rating/planner joins ignore them because ring presence is counted through
the local `body_rings.body_id = bodies.id` relationship.

Stage 17N.2d-Q adds `body_rings.association_status` and the
`body_rings_eddn_identity_report` view. Consumers count only
`association_status = 'local_matched'`. Future EDDN ring payloads are resolved
by exact `(SystemAddress, BodyName)` to one local body; unmatched, ambiguous,
or belt-source payloads are skipped from trusted `body_rings` writes and
summarised in listener counters instead of logging one row at a time.

## Stage 17N.2d-P Coordinated Enrichment CLI

Script:

```bash
python apps/importer/src/enrich_system_data.py --help
```

The coordinator is dry-run by default and has no broad apply mode. Writes are
split by explicit flags:

- `--apply-station-metadata` updates only trusted station type, station arrival
  distance, and station body-name provenance from exact EDSM station identity.
- `--apply-confirmed-links` writes only exact EDSM body-name
  `station_body_links`; it does not write inferred distance links and it
  preserves existing confirmed/manual links.
- `--apply-rings` writes trusted `body_rings` rows and sets
  `body_scan_facts.is_ringed = true` for bodies with trusted ring rows.
- `--mark-dirty` is a separate write and is required with apply flags so changed
  ring or station facts queue deferred rebuild/cache work.

Useful options:

- `--system-id64` or `--system-name` for one targeted system.
- `--limit` for bounded batch work.
- `--source edsm` for EDSM station metadata and targeted EDSM body/ring reads.
- `--source spansh --spansh-file /path/to/galaxy.json.gz` for controlled
  Spansh ring backfill.
- `--source local --rings` for ring coverage audit only.
- `--checkpoint-file /path/to/checkpoint.json` to skip systems already handled
  by a previous run.
- `--json` for machine-readable counts, skipped rows, conflicts, and applied
  rows.

Safe station dry-run for one system:

```bash
PYTHONPATH=apps/api/src:apps/importer/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/enrich_system_data.py \
    --stations --source edsm \
    --system-id64 2008132031194 \
    --json
```

Safe station apply after reviewing conflicts:

```bash
PYTHONPATH=apps/api/src:apps/importer/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/enrich_system_data.py \
    --stations --source edsm \
    --system-id64 2008132031194 \
    --apply-station-metadata \
    --apply-confirmed-links \
    --mark-dirty \
    --json
```

Safe Spansh ring dry-run for a tiny batch:

```bash
PYTHONPATH=apps/api/src:apps/importer/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/enrich_system_data.py \
    --rings --source spansh \
    --spansh-file /data/dumps/galaxy.json.gz \
    --limit 10 \
    --json
```

Safe Spansh ring apply after reviewing the dry-run:

```bash
PYTHONPATH=apps/api/src:apps/importer/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/enrich_system_data.py \
    --rings --source spansh \
    --spansh-file /data/dumps/galaxy.json.gz \
    --limit 10 \
    --apply-rings \
    --mark-dirty \
    --checkpoint-file /data/checkpoints/stage17n2d-p-rings.json \
    --json
```

Conservative batch sizes:

- EDSM station enrichment: start with one system, then `--limit 10`; keep the
  default inter-system rate limit unless the EDSM request volume has been
  reviewed.
- Spansh ring enrichment: start with `--limit 10`, then `--limit 100` after
  conflict counts and row counts look sane. Avoid a full-galaxy apply until a
  sampled run has been verified.
- Dirty rebuild: run separately and gently with `build_ratings.py --dirty`;
  never run it from the enrichment script. For Stage 17N.2d-P, wait until the
  EDDN ring identity repair dry-run/apply and coverage validation are complete.

Post-backfill sequence:

1. Apply a small enrichment batch.
2. Verify applied/skipped/conflict counts and sample SQL.
3. Run `build_ratings.py --dirty` gently only after EDDN ring identity repair
   validation is clean enough for the intended scope.
4. Clear system/detail/planner/search caches.
5. Inspect UI/API for the sampled systems.

Additional verification SQL:

```sql
SELECT distance_source, distance_confidence, count(*)
FROM stations
GROUP BY distance_source, distance_confidence
ORDER BY count(*) DESC;

SELECT station_type_source, station_type_confidence, count(*)
FROM stations
GROUP BY station_type_source, station_type_confidence
ORDER BY count(*) DESC;

SELECT association_source, association_status, association_confidence, count(*)
FROM station_body_links
GROUP BY association_source, association_status, association_confidence
ORDER BY count(*) DESC;

SELECT source, confidence, count(*)
FROM body_rings
GROUP BY source, confidence
ORDER BY count(*) DESC;

SELECT system_address, body_id, body_name, is_ringed, data_sources, confidence
FROM body_scan_facts
WHERE system_address = :system_id64
ORDER BY body_id;

SELECT id64, name, rating_dirty
FROM systems
WHERE id64 = :system_id64;
```

Stage 17N.2d-Q validation SQL:

```sql
-- Recent EDDN ring identity coverage.
WITH recent AS (
  SELECT *
  FROM body_rings
  WHERE source = 'eddn_scan'
    AND updated_at >= NOW() - INTERVAL '24 hours'
)
SELECT
  COUNT(*) AS recent_rows,
  COUNT(*) FILTER (
    WHERE local_body.id IS NOT NULL
      AND recent.association_status = 'local_matched'
  ) AS matched_by_local_body_id,
  COUNT(*) FILTER (
    WHERE local_body.id IS NULL
       OR recent.association_status <> 'local_matched'
  ) AS unmatched_by_local_body_id
FROM recent
LEFT JOIN bodies local_body
  ON local_body.system_id64 = recent.system_id64
 AND local_body.id = recent.body_id;

-- Safe cleanup/report buckets: no deletion implied.
SELECT report_bucket, COUNT(*) AS rows
FROM body_rings_eddn_identity_report
GROUP BY report_bucket
ORDER BY report_bucket;

-- Source-level coverage.
WITH name_matches AS (
  SELECT br.id AS ring_id,
         COUNT(b.id) AS name_match_count
  FROM body_rings br
  LEFT JOIN bodies b
    ON b.system_id64 = br.system_id64
   AND b.name = br.body_name
  GROUP BY br.id
)
SELECT br.source,
       COUNT(*) AS rows,
       COUNT(*) FILTER (
         WHERE local_body.id IS NOT NULL
           AND br.association_status = 'local_matched'
       ) AS matches_by_bigint_id,
       COUNT(*) FILTER (WHERE name_matches.name_match_count = 1) AS matches_by_body_name,
       COUNT(*) FILTER (
         WHERE local_body.id IS NULL
            OR br.association_status <> 'local_matched'
       ) AS unmatched_rows,
       COUNT(*) FILTER (WHERE br.association_status = 'ambiguous_body_identity') AS ambiguous_rows,
       COUNT(*) FILTER (WHERE br.association_status = 'belt_source_evidence') AS belt_rows,
       COUNT(*) FILTER (WHERE br.association_status = 'conflict') AS conflict_rows
FROM body_rings br
LEFT JOIN bodies local_body
  ON local_body.system_id64 = br.system_id64
 AND local_body.id = br.body_id
JOIN name_matches ON name_matches.ring_id = br.id
GROUP BY br.source
ORDER BY br.source;

-- Dirty queue.
SELECT COUNT(*) AS dirty_ratings_waiting
FROM systems
WHERE rating_dirty IS TRUE;

-- Ring consumer validation after the dirty ratings rebuild completes.
WITH valid_ring_systems AS (
  SELECT DISTINCT br.system_id64
  FROM body_rings br
  JOIN bodies b
    ON b.system_id64 = br.system_id64
   AND b.id = br.body_id
  WHERE br.association_status = 'local_matched'
)
SELECT
  COUNT(*) AS valid_ring_systems,
  COUNT(r.system_id64) AS with_rating_row,
  COUNT(*) FILTER (WHERE r.rating_version = '3.4') AS with_v34_rating,
  COUNT(*) FILTER (WHERE COALESCE(r.ring_count, 0) > 0) AS with_positive_ring_count,
  COUNT(*) FILTER (WHERE COALESCE(r.ring_count, 0) = 0) AS zero_or_null_ring_count
FROM valid_ring_systems v
LEFT JOIN ratings r ON r.system_id64 = v.system_id64;
```

Recent EDDN log checks after deploy:

```bash
grep -E "rings_written|rings_skipped_unmatched_body|rings_skipped_ambiguous_body|ring_write_errors|Dirty mark flush" /data/logs/eddn.log | tail -100
grep -F "Dirty recalc job error" /data/logs/eddn.log | tail -20
```

The second command should return no new lines after the Stage 17N.2d-Q deploy.

Useful verification SQL:

```sql
-- Start with cheap existence checks on production before running any
-- full-table aggregates over ratings.
SELECT system_id64, ring_count, walkable_count, other_star_count
FROM ratings
WHERE ring_count > 0
LIMIT 5;

SELECT system_id64, ring_count, walkable_count, other_star_count
FROM ratings
WHERE walkable_count > 0
LIMIT 5;

SELECT system_id64, ring_count, walkable_count, other_star_count
FROM ratings
WHERE other_star_count > 0
LIMIT 5;

-- If you need exact counts from ratings on the live galaxy, disable
-- statement_timeout for the session first.
-- Example:
--   SET statement_timeout = 0;
--   SELECT
--     count(*) FILTER (WHERE ring_count > 0)       AS w_rings,
--     count(*) FILTER (WHERE walkable_count > 0)   AS w_walkable,
--     count(*) FILTER (WHERE other_star_count > 0) AS w_otherstar
--   FROM ratings;

SELECT count(*) AS ring_rows
FROM body_rings;

SELECT source, confidence, association_status, count(*) AS rows
FROM body_rings
GROUP BY source, confidence, association_status
ORDER BY rows DESC;

WITH name_matches AS (
  SELECT br.id AS ring_id,
         COUNT(b.id) AS name_match_count
  FROM body_rings br
  LEFT JOIN bodies b
    ON b.system_id64 = br.system_id64
   AND b.name = br.body_name
  GROUP BY br.id
)
SELECT br.source,
       COUNT(*) AS rows,
       COUNT(*) FILTER (WHERE local_body.id IS NOT NULL) AS matches_by_bigint_id,
       COUNT(*) FILTER (WHERE name_matches.name_match_count = 1) AS matches_by_body_name,
       COUNT(*) FILTER (
         WHERE local_body.id IS NULL
           AND name_matches.name_match_count = 0
       ) AS unmatched_rows
FROM body_rings br
LEFT JOIN bodies local_body
  ON local_body.system_id64 = br.system_id64
 AND local_body.id = br.body_id
JOIN name_matches ON name_matches.ring_id = br.id
GROUP BY br.source
ORDER BY br.source;

WITH name_matches AS (
  SELECT br.id AS ring_id,
         COUNT(b.id) AS name_match_count
  FROM body_rings br
  LEFT JOIN bodies b
    ON b.system_id64 = br.system_id64
   AND b.name = br.body_name
  WHERE br.source = 'eddn_scan'
  GROUP BY br.id
)
SELECT br.system_id64, br.body_id, br.source_body_id, br.body_name,
       br.ring_name, br.confidence, br.updated_at
FROM body_rings br
LEFT JOIN bodies local_body
  ON local_body.system_id64 = br.system_id64
 AND local_body.id = br.body_id
JOIN name_matches ON name_matches.ring_id = br.id
WHERE br.source = 'eddn_scan'
  AND local_body.id IS NULL
  AND name_matches.name_match_count = 0
ORDER BY br.updated_at DESC
LIMIT 100;

SELECT br.system_id64, b.name AS matched_body_name,
       br.body_id, br.body_name, br.ring_name, br.ring_type, br.ring_class,
       br.mass_mt, br.inner_radius, br.outer_radius,
       br.source, br.confidence, br.updated_at
FROM body_rings br
LEFT JOIN bodies b ON b.id = br.body_id
WHERE br.system_id64 = :system_id64
ORDER BY COALESCE(b.name, br.body_name), br.ring_name;

SELECT id64, rating_dirty, cluster_dirty, updated_at
FROM systems
WHERE id64 = :system_id64;

SELECT COUNT(*) AS dirty_ratings_waiting
FROM systems
WHERE rating_dirty IS TRUE;

SELECT
  count(*) FILTER (WHERE is_ringed IS TRUE)  AS trusted_ringed_scan_facts,
  count(*) FILTER (WHERE is_ringed IS FALSE) AS trusted_not_ringed_scan_facts,
  count(*) FILTER (WHERE is_ringed IS NULL)  AS unknown_scan_facts
FROM body_scan_facts;
```

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

Do not purge `ratings` rows first as the normal production path. The intended
rebaseline path is to overwrite existing rows with a full
`build_ratings.py --rebuild` run so every eligible row is rewritten by
**Ratings v3.4 Best-Build Potential** and receives `rating_version = '3.4'`.
Deleting all rows up front removes the fallback state before the rebuild path
has proved stable.

## Full Production Rebaseline Sequence

Use this when the goal is to eliminate all **Pre-v3.4 Unversioned Ratings** and
leave production serving only **Ratings v3.4 Best-Build Potential** rows for
eligible systems.

1. Pause the scheduled dirty-ratings cron or otherwise ensure no overlapping
   `build_ratings.py --dirty` job can run while the full rebuild is active.
2. Capture a baseline before the run:

   ```sql
   SELECT rating_version, COUNT(*)
   FROM ratings
   GROUP BY rating_version
   ORDER BY COUNT(*) DESC;

   SELECT COUNT(*) AS dirty_count
   FROM systems
   WHERE rating_dirty = TRUE;
   ```

3. Start with the smallest practical full rebuild:

   ```bash
   cd /opt/ed-finder
   BATCH_SIZE=1000 RATING_DIRTY_CLEANUP_CHUNK=1000 \
     ./scripts/run_import.sh build_ratings.py --rebuild --workers 1 --chunk 1000
   ```

4. Only if the conservative run proves stable, increase carefully:

   ```bash
   cd /opt/ed-finder
   BATCH_SIZE=2000 RATING_DIRTY_CLEANUP_CHUNK=5000 \
     ./scripts/run_import.sh build_ratings.py --rebuild --workers 2 --chunk 5000
   ```

5. Monitor the run with repeated checks:
   - `rating_version = '3.4'` count should keep increasing.
   - `rating_version IS NULL` count should trend toward zero.
   - `systems.rating_dirty = TRUE` may fluctuate during live ingestion, but the
     rebuild must continue making forward progress on rating writes.
6. Do not treat a small dirty queue as proof that the legacy rebaseline is
   complete. Dirty maintenance and full historical rebaseline are separate
   concerns.
7. After the rebuild finishes, rerun the verification queries in the next
   section.
8. Clear caches only after verification is clean enough for cutover.
9. Re-enable the scheduled dirty-ratings cron after the full rebuild is
   complete and verified.

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
  active `frontend/` application surface; findings there were not patched.
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
- Trusted EDSM-provenance `body_name` is confirmed when it matches one known
  body; legacy local `body_name` is inferred.
- A unique non-zero `distance_from_star` match is allowed only as `inferred`;
  legacy local distance is weak evidence.
- Ambiguous or missing association renders as unresolved existing
  infrastructure.
- Coriolis, Orbis, Ocellus, Outpost, and AsteroidBase occupy orbital capacity.
- PlanetaryPort, PlanetaryOutpost, and surface/settlement-like types occupy
  surface capacity.
- MegaShip, FleetCarrier, and Unknown station types are shown as unresolved
  rather than forced into a colony slot.
- planner canvas shows existing slots with established/solid styling, planned
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

Stage 17N.2d-J/K/L EDSM targeted probe:

```bash
PYTHONPATH=apps/api/src DATABASE_URL="$DATABASE_URL" \
  python apps/importer/src/edsm_station_enrichment_probe.py \
    --system-name Exioce --system-id64 2008132031194 --dry-run --json
```

Container dry-run form:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --dry-run --json
```

This command fetches EDSM station/body evidence for one named system only. It
does not run on a normal user path and does not import a bulk dump. Default
mode is dry-run. `--apply` hard-fails as not implemented. Stage 17N.2d-L adds
station metadata provenance columns through `sql/023_station_data_provenance.sql`;
existing station rows remain `NULL` provenance and legacy local station
distance stays weak evidence.

Station metadata apply form, after reviewing dry-run output:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --apply-metadata --json
```

Confirmed link apply form, after reviewing dry-run output:

```bash
docker compose --profile import run --rm \
  --entrypoint python3 \
  -v /opt/ed-finder/apps/importer/src:/workspace/apps/importer/src:ro \
  -v /opt/ed-finder/apps/api/src:/workspace/apps/api/src:ro \
  importer \
  /workspace/apps/importer/src/edsm_station_enrichment_probe.py \
  --system-name Exioce \
  --system-id64 2008132031194 \
  --apply-confirmed-links --json
```

Guarded all-record automation from the repo checkout on the host:

```bash
scripts/run_station_enrichment_guarded.sh --all-records
```

This runs dry-run, safe metadata apply passes, confirmed-link apply, and final
verification for every eligible station system in batches. It writes a
checkpoint JSON under `/tmp/edfinder-station-enrichment/...` by default, so a
failed run can resume with `--checkpoint-file <path>`. Safety gates still abort
the run if risky station writes or trusted EDSM precision churn appear.

`--apply-metadata` is intentionally narrow. It can update only trusted station
metadata/provenance for exact EDSM id/marketId plus exact station name matches:
`station_type` from `Unknown` to a known permanent type, EDSM
`distanceToArrival` into `stations.distance_from_star`, and EDSM `bodyName`
into `stations.body_name` when that body name matches exactly one local
same-system body. It sets source `edsm_system_api` and confidence
`exact_station_identity`.

`--apply-confirmed-links` writes only confirmed/exact EDSM bodyName
`station_body_links` for permanent station types, using source
`edsm_body_name`. It does not write inferred distance-only links and does not
overwrite existing confirmed links. Neither apply mode writes economies,
service flags, bulk data, or transient/mobile infrastructure links. Fleet
carriers, raw carriers, and megaships stay under `ignored_transient_non_slot`
and are ignored for colony planning occupancy.

Expected Exioce shape:

- dry-run: Macmillan Depot and Fort Lawrence `Unknown -> Orbis`; Miller
  Terminal `Unknown -> Coriolis`
- metadata apply: Macmillan Depot distance `592` bodyName `Exioce 3 d`; Fort
  Lawrence distance `1627` bodyName `Exioce 4`; Miller Terminal distance
  `2219` bodyName `Exioce 5 b`, all with EDSM provenance
- confirmed-link apply: three confirmed/exact `edsm_body_name` links, but only
  if each EDSM bodyName matches exactly one local body
- fleet carriers WFK-N6Z, K2W-77Q, WFW-4TZ, T9J-B2N, and XFK-T4M remain
  ignored transient/non-slot rows

Before apply, capture reviewed rows for rollback; after apply, inspect the
station metadata and links:

```sql
CREATE TEMP TABLE exioce_station_metadata_before AS
SELECT id, station_type::text AS station_type,
       distance_from_star, distance_source, distance_confidence, distance_updated_at,
       body_name, body_name_source, body_name_confidence, body_name_updated_at,
       station_type_source, station_type_confidence, station_type_updated_at
FROM stations
WHERE system_id64 = 2008132031194
  AND name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal');

SELECT id, name, station_type::text,
       distance_from_star, distance_source, distance_confidence,
       body_name, body_name_source, body_name_confidence
FROM stations
WHERE system_id64 = 2008132031194
  AND name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal')
ORDER BY name;

SELECT s.name AS station_name, l.body_id, l.body_name, l.lane,
       l.association_status, l.association_confidence, l.association_source
FROM station_body_links l
JOIN stations s ON s.id = l.station_id
WHERE l.system_id64 = 2008132031194
  AND s.name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal')
ORDER BY s.name;

UPDATE stations s
SET station_type = b.station_type::station_type,
    distance_from_star = b.distance_from_star,
    distance_source = b.distance_source,
    distance_confidence = b.distance_confidence,
    distance_updated_at = b.distance_updated_at,
    body_name = b.body_name,
    body_name_source = b.body_name_source,
    body_name_confidence = b.body_name_confidence,
    body_name_updated_at = b.body_name_updated_at,
    station_type_source = b.station_type_source,
    station_type_confidence = b.station_type_confidence,
    station_type_updated_at = b.station_type_updated_at
FROM exioce_station_metadata_before b
WHERE s.id = b.id;

DELETE FROM station_body_links
WHERE system_id64 = 2008132031194
  AND association_source = 'edsm_body_name'
  AND station_id IN (
      SELECT id FROM stations
      WHERE system_id64 = 2008132031194
        AND name IN ('Macmillan Depot', 'Fort Lawrence', 'Miller Terminal')
  );
```

Treat `association_changes.confirmed` rows as proposed evidence until
`--apply-confirmed-links` is run for that one system. Treat `inferred` rows as
reviewable distance matches, `unresolved` rows as still-visible infrastructure,
and `conflicts` as stop/review items.

Association diagnostics:

```sql
SELECT distance_source, distance_confidence, count(*)
FROM stations
GROUP BY distance_source, distance_confidence
ORDER BY distance_source NULLS FIRST, distance_confidence NULLS FIRST;

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

