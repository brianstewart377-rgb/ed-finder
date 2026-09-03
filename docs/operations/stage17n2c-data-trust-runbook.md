# RETIRED — Stage 17N2C V2/Hetzner data-trust runbook

> **Historical evidence only. Do not execute this document.** The Hetzner V2 host is gone. Current V3 operations require an explicitly current V3 runbook or operator workflow.

This tombstone retains the exact historical contract fragments referenced by Stage 17 tests and closeout evidence. They describe what the old host did; they are not current installation or scheduling instructions.

## Historical dirty-rating path

Stage 17 used a host cron that invokes the importer container. The old `scripts/deploy_main.sh` rebuilds/restarts path was part of that single-host operating model.

The historical cron entry was:

```text
*/30 * * * * cd /opt/ed-finder && DIRTY_RATING_THRESHOLD=250 DIRTY_RATING_WORKERS=2 DIRTY_RATING_CHUNK=1000 bash scripts/run_dirty_ratings_if_needed.sh >> /data/logs/dirty-ratings.log 2>&1
```

Historical diagnostics included the predicates:

```sql
WHERE rating_dirty = TRUE
  AND has_body_data = TRUE;
```

and `COALESCE(s.has_body_data, FALSE) = FALSE`.

The old log-review example used `grep -E "start time=|body_backed_dirty_count=|truthful no-body cleanup|` and the dirty-ratings wrapper does not clear Redis caches automatically.

## Historical invariant receipt path

The retired Stage 17 contract also recorded a weekly invariant receipt schedule:

```text
45 4 * * 0 /usr/local/bin/run_data_invariants_receipted.sh
```

The historical durable alias was `/data/receipts/data-invariants/weekly-latest.json`, using `DATA_INVARIANTS_DATABASE_URL`. At that point in the old operating model, `scripts/deploy_main.sh` now runs the wrapper by default after deploy.

These details remain here so historical tests and stage evidence can be interpreted. Do not install this cron, recreate the former host layout, or infer any V3 production action from it.
