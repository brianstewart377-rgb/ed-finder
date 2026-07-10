# Claude Audit Foundation Next Pass (2026-07-09)

Update (2026-07-10):

- This handoff has now been materially executed on production.
- Final production evidence from the body-contract closeout lane:
  - `flagged_but_zero_count = 3`
  - `unflagged_but_positive_count = 0`
  - `ring_status_drift = 0`
  - the remaining dirty queue oscillates in a small retry/live-churn band after
    rerates and no-body reconciles
  - station-link `total_mismatches = 0`
- `scripts/checks/data_trust_health_snapshot.py` now provides the lightweight
  committed probe for this lane. Latest production snapshot:
  - `flagged_but_zero_count = 0`
  - `unflagged_but_positive_count = 0`
  - `ring_status_drift = 0`
  - station-link drift buckets at `0`
  - dirty tail split: `167` truthful no-body rows, `352` body-backed dirty rows
- Production migration review also closed:
  - `schema_migrations` was already active through
    `035_nullable_population.sql`
  - production did not require a baseline cutover
  - `019_nullable_coords.sql` is now recorded in
    `schema_migration_manual_status`
- The remaining dirty tail is small steady-state retry/live churn, not the
  original audit-scale backlog.

This note packages the next operator-only foundation steps from the adversarial
report lane in the required order:

1. production body-contract closeout evidence
2. remaining pre-ledger migration baseline cutover
3. CI/build honesty follow-through (repo-local and already in progress)

Important boundary:

- Per [`docs/operations/operator-command-contexts.md`](file:///c:/Users/brian/Documents/trae_projects/ED-Finder/docs/operations/operator-command-contexts.md),
  commands that enter `/opt/ed-finder`, query production Postgres containers, or
  invoke production Docker Compose services must run from the Hetzner operator
  shell, not from Codex.

## 1. Production Body-Contract Closeout Evidence

Reference:

- [`docs/operations/stage17n2c-data-trust-runbook.md`](file:///c:/Users/brian/Documents/trae_projects/ED-Finder/docs/operations/stage17n2c-data-trust-runbook.md)

Run from the operator shell or via the trusted `ed-finder-prod` SSH alias.

Preview the repair populations first:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T api python scripts/repair_body_contract.py --json"
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T api python scripts/repair_station_body_links.py --json"
```

If the body-contract preview shows the old dominant drift shape, use the
focused body-only preview:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T api python scripts/repair_body_contract.py --focus missing-bodies-only --json"
```

Recommended first bounded apply:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && PGOPTIONS='-c max_parallel_workers_per_gather=0 -c work_mem=4MB' python3 scripts/repair_body_contract.py --dsn 'postgresql://edfinder:change-me@127.0.0.1:5432/edfinder' --apply --skip-summary --focus missing-bodies-only --batch-size 1000 --limit 5000"
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T api python scripts/repair_station_body_links.py --apply --batch-size 1000 --limit 5000"
```

Why the body-contract command is host-side and uses `--skip-summary`:

- production keeps the repair script in `/opt/ed-finder/scripts`
- DB credentials are easiest to supply explicitly via the host-reachable DSN
- on very large databases, the old summary-first behavior is too expensive for a
  first bounded pass, so `--skip-summary` avoids the full pre-scan

Then run one explicit dirty rebuild pass:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && DIRTY_RATING_THRESHOLD=1 DIRTY_RATING_WORKERS=2 DIRTY_RATING_CHUNK=1000 bash scripts/run_dirty_ratings_if_needed.sh"
```

Finish with invariants and steady-state checks:

```powershell
ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T api python scripts/checks/data_invariants.py --target-rating-version 3.4 --production-safe"
ssh ed-finder-prod "cd /opt/ed-finder && python3 scripts/checks/data_trust_health_snapshot.py --database-url 'postgresql://edfinder:change-me@127.0.0.1:5432/edfinder'"
ssh ed-finder-prod "cd /opt/ed-finder && tail -100 /data/logs/dirty-ratings.log"
```

SQL spot check:

```powershell
$sql = @'
SELECT COUNT(*) AS dirty_systems
FROM systems
WHERE rating_dirty = TRUE;

SELECT association_status, association_confidence, COUNT(*)
FROM station_body_links
GROUP BY association_status, association_confidence
ORDER BY association_status, association_confidence;
'@
$sql | ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T postgres psql -U edfinder -d edfinder -P pager=off"
```

Success criteria:

- `data_invariants.py --production-safe` passes cleanly on production
- body-contract preview returns zero remaining mismatches for the repaired scope
- station-link preview returns zero remaining mismatches for the repaired scope
- the follow-up dirty rebuild drains normally

Observed production closeout result (2026-07-10):

- `data_invariants.py` now has a `--production-safe` mode for very large
  databases, which disables the planner choices that were inflating the live
  production run and skips the heaviest freshness/body-count mismatch scans.
- Before that mode existed, a full live `data_invariants.py` run remained too
  heavyweight on the 120 GB production database, so closeout evidence was
  recorded with targeted production-safe SQL plus the committed repair/preview
  scripts.
- The dominant body-contract drift bucket was drained from `18434` to `3`.
- `repair_body_ring_association_status.py` repaired `428` drifting
  `body_rings.association_status` rows on production and reduced
  `ring_status_drift` to `0`.
- Station-link preview now returns `total_mismatches = 0`.
- The dirty queue now sits in a small retry band rather than an audit-scale
  backlog.

## 2. Remaining Pre-Ledger Migration Baseline Cutover

Local cutover evidence already exists:

- [`artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json`](file:///c:/Users/brian/Documents/trae_projects/ED-Finder/artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json)
- [`artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json`](file:///c:/Users/brian/Documents/trae_projects/ED-Finder/artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json)

The remaining migration-baseline gap is any other pre-ledger database,
including production if it still has no recorded cutover.

Observed production result (2026-07-10):

- Production is not pre-ledger. `schema_migrations` was already present and
  active through `035_nullable_population.sql`.
- The required fix on production was manual bookkeeping for
  `019_nullable_coords.sql`, not a baseline helper run.

Recommended production operator flow:

1. Audit whether `schema_migrations` already exists and how many rows it has.
2. If production is still pre-ledger, inspect schema markers before writing any
   baseline rows.
3. Run the reviewed baseline helper only through the highest schema point that
   is already represented in production.
4. Run the normal applier afterward to pick up only the remaining migrations.
5. Write a receipt outside git or sanitize a summary before committing.

Command skeleton:

```powershell
$sql = @'
SELECT to_regclass('public.schema_migrations');
SELECT to_regclass('public.schema_migration_manual_status');
SELECT COUNT(*) AS public_table_count
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';
'@
$sql | ssh ed-finder-prod "cd /opt/ed-finder && docker compose exec -T postgres psql -U edfinder -d edfinder -P pager=off"
```

If production is still pre-ledger, the reviewed helper is:

```bash
bash scripts/baseline_migration_ledger.sh \
  --baseline-through <reviewed-cutover-file> \
  --manual-019-status applied \
  --receipt-file artifacts/migration-baselines/<production-receipt>.json
```

Then:

```bash
bash scripts/apply_migrations.sh --include-manual
```

Do not guess the `--baseline-through` value from filenames alone. Reuse the
same review discipline used for the local `029_create_source_runs.sql` cutover.

## 3. CI/Build Honesty Follow-Through

Repo-local progress already advanced in this pass:

- stronger frontend CI remained green under `yarn test:ci`
- new disposable-DB runtime coverage is being added for the repair/invariants
  path so CI proves the body-contract and station-link repair scripts actually
  restore invariant cleanliness

Target verification after that lands:

```bash
python -m pytest tests/test_data_trust_runtime.py -q
```
