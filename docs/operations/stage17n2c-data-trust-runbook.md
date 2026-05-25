# Stage 17N.2c Data Trust Runbook

This runbook is for the next production continuation after the nullable-coordinate
and rating-version deployment. It is intentionally conservative: prefer small
dirty rebuilds, verify after each step, and do not run a high-worker full rebuild
until production has proven the new settings under load.

## Safe Order

1. Apply `sql/020_rating_version.sql`.
2. Deploy code. If production already has partially applied migrations, deploy with `--skip-migrations` and apply SQL manually.
3. Apply `sql/019_nullable_coords.sql`.
4. If the coordinate cleanup times out, rerun only the cleanup with timeout-disabled session settings:

   ```sql
   SET statement_timeout = 0;
   SET lock_timeout = 0;

   UPDATE systems
      SET x = NULL, y = NULL, z = NULL
    WHERE x = 0 AND y = 0 AND z = 0
      AND id64 != 10477373803;
   ```

5. Analyze systems:

   ```sql
   ANALYZE systems;
   ```

6. Clear Redis cache patterns for search, autocomplete, and system detail.
7. Run a small ratings smoke rebuild:

   ```bash
   BATCH_SIZE=1000 RATING_DIRTY_CLEANUP_CHUNK=1000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 1 --chunk 1000 --limit 10
   ```

8. Run a gentle dirty rebuild:

   ```bash
   BATCH_SIZE=1000 RATING_DIRTY_CLEANUP_CHUNK=1000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 1 --chunk 1000
   ```

   If stable, a slightly larger pass is acceptable:

   ```bash
   BATCH_SIZE=2000 RATING_DIRTY_CLEANUP_CHUNK=5000 \
     ./scripts/run_import.sh build_ratings.py --dirty --workers 2 --chunk 5000
   ```

9. Verify `rating_version` and capped-score behavior.
10. Run nightly maintenance:

    ```bash
    docker compose run --rm maintenance run_maintenance.sh nightly
    ```

11. Clear Redis caches again.

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

docker compose exec redis redis-cli --scan --pattern 'autocomplete:*' \
  | xargs -r docker compose exec -T redis redis-cli del

docker compose exec redis redis-cli --scan --pattern 'sys:*' \
  | xargs -r docker compose exec -T redis redis-cli del
```

## Stop Conditions

Pause the rebuild and inspect logs if any of these occur:

- repeated worker connection closures
- repeated dirty cleanup failures after retries
- rising `rating_dirty` count while rating writes are not increasing
- `rating_version = '3.4'` count stops increasing during a dirty rebuild
- fake non-Sol origin count is non-zero after coordinate cleanup
