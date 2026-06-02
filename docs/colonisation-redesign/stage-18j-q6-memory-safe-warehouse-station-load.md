# Stage 18J-Q6 — Memory-Safe Warehouse Station Load

## Purpose

Stage 18J-Q6 makes the warehouse station staging loader safe for very large
nested EDSM station snapshots while preserving the Stage 18J-Q5 source-shape
support.

The stage is implementation and documentation only. It does not run production
load, production reconciliation, station-type dry-run, canonical apply, or any
Stage 18J-P/18K work.

## Production Failure Summary

After Stage 18J-Q5 merged, an operator attempted a full warehouse staging load
of the server-local station dump:

```text
/data/dumps/galaxy_stations.json.gz
```

The loader process was killed before completion while processing the large
source file. Kernel logs did not show an obvious out-of-memory message, but the
failure mode is consistent with the pre-Q6 write path building a complete
in-memory output plan before database writes.

## Safety Check After Failure

The post-failure safety check found:

- canonical station count: `284763`
- `enrichment_source_runs`: `0`
- `enrichment_source_files`: `0`
- `enrichment_raw_records`: `0`
- `staging_edsm_stations`: `0`
- failed output artifact files were `0` bytes
- no production reconciliation was run
- no station-type dry-run was run
- no canonical apply was run
- Stage 18J-P remained blocked
- Stage 18K remained untouched

## Root Cause Hypothesis

Stage 18J-Q5 correctly extracted station rows from nested EDSM system records,
but write-staging still reused the full dry-run report shape. For a
galaxy-sized nested station snapshot, that meant accumulating every raw system
record and every staged station row in memory, then serializing a very large
final JSON report.

The likely fix is not more host memory. The loader needs to stream source
records, write bounded batches, and keep only counters plus source metadata for
the write-mode summary.

## Loader Changes

Q6 keeps dry-run as the default/no-write path. Small dry-runs still return the
full deterministic `enrichment_snapshot_load_plan/v1` report, including raw
records, staged rows, skipped rows, and warnings.

For `edsm_nightly_stations` with explicit `--write-staging`, Q6 adds a
streaming station write path:

- source run and source file keys remain deterministic,
- top-level source records stream from `.json` or `.json.gz`,
- nested EDSM system station records are extracted using the Q5 logic,
- full parent system records are written to `enrichment_raw_records`,
- extracted stations are written to `staging_edsm_stations`,
- nested body collections remain raw-only unsupported-source-shape warning
  evidence,
- target tables remain limited to warehouse/staging tables,
- `canonical_writes_planned` remains `0`.

## Batching / Streaming Model

The station write path accepts `--batch-size`, defaulting to 500 source
records. Each batch keeps only:

- raw source records for that batch,
- station rows extracted from those source records,
- counters and distributions for the final summary.

After a batch writes successfully, the transaction is committed and the batch
lists are discarded. A final metadata update records source timestamp and
freshness summaries on the source run/file rows.

Body/ring staging keeps its existing report-backed write path. Q6 is scoped to
the station source shape that failed in production.

## Output Summary Model

Write-staging station output remains JSON, but it is compact. It does not
materialize all `raw_records_planned`, `staged_rows`, `planned_rows`,
`skipped_rows`, or warning payloads in the final output.

The compact summary includes the operational counters needed for review:

- `records_seen`
- `source_runs`
- `source_files`
- `raw_records`
- `raw_records_written`
- `staged_edsm_stations`
- `staging_station_rows_written`
- `nested_station_records_extracted`
- `nested_station_records_skipped`
- `batches_written`
- `warnings`
- `errors`
- `canonical_writes_planned`
- `target_tables`
- `staging_writes_enabled`
- `write_mode`

Use dry-run mode with `--limit` for payload-level inspection before a full
warehouse staging load.

## Idempotency / Duplicate Protection

Warehouse writes use deterministic source identity and upsert keys:

- `source_run_key`
- `source_file_key`
- `source_record_key`
- `source_record_hash`

Raw records upsert by source run/file/hash. Station staging rows upsert by
source run/hash. Retrying the same source file with the same source adapter
updates existing warehouse evidence instead of duplicating it.

Because batches commit independently, an interrupted process may leave a
partial staging load if it is killed after at least one batch commit. The safe
recovery expectation is to retry the same staging load and verify the compact
summary plus staged-row counts before running read-only reconciliation. Do not
use a failed or incomplete staging run as reconciliation input.

## Production Retry Criteria

After Q6 merges, the next server action is a controlled retry of the warehouse
station staging load only.

Before retry:

- main must include Q6,
- the warehouse loader role must be scoped to warehouse/staging tables only,
- the source file must be present on the server,
- the output path must be outside git and operator-managed,
- canonical station count must be captured before the run,
- warehouse row counts must be captured before the run,
- `--write-staging`, `--dsn`, `--confirm-staging-db`, and a reviewed
  `--batch-size` must be explicit.

After retry:

- loader summary must report `errors = 0`,
- target tables must be warehouse/staging only,
- `canonical_writes_planned = 0`,
- warehouse row counts must match the summary,
- canonical station count must be unchanged.

If the staging load succeeds, move to read-only reconciliation artifact
generation. Stage 18J-P remains blocked until a valid reconciliation artifact
exists.

## Boundaries

Q6 does not authorize:

- production data committed to git,
- production artifacts committed to git,
- production load during the development stage,
- production reconciliation during the development stage,
- station-type dry-run,
- canonical apply,
- production DB access from development,
- scheduler or cron wiring,
- UI/API apply controls,
- live EDSM/API crawl,
- broad canonical backfill,
- Stage 18J-P,
- Stage 18K.

Unknown values remain unknown. Source-only evidence remains source-only.

## Validation

Required local validation:

```sh
./scripts/run_canonical_safety_tests.sh

.venv/bin/pytest \
  tests/test_enrichment_snapshot_loader.py \
  tests/test_enrichment_staging.py \
  tests/test_enrichment_staging_db_loader.py \
  tests/test_station_type_canonical_pilot.py \
  tests/test_enrichment_warehouse_boundary.py \
  tests/test_enrichment_report_contracts.py \
  tests/test_edsm_station_normalization.py \
  -q

.venv/bin/python -m py_compile \
  apps/importer/src/enrichment_snapshot_loader.py \
  apps/importer/src/enrichment_staging.py \
  apps/importer/src/enrichment_staging_db_loader.py \
  apps/importer/src/station_type_canonical_pilot.py \
  tests/test_enrichment_snapshot_loader.py \
  tests/test_enrichment_staging.py \
  tests/test_enrichment_staging_db_loader.py \
  tests/test_station_type_canonical_pilot.py

git diff --check
```

Disposable Postgres rehearsal remains optional and must use explicit
non-production confirmation only.

## Roadmap Impact

After Q6 merges, the next server action is a controlled retry of the warehouse
station staging load. If that succeeds, move to read-only reconciliation
artifact generation. Stage 18J-P remains blocked until a valid reconciliation
artifact exists.

Stage 19 should expand the warehouse broadly and design freshness/scheduler
support, but no cron/scheduler implementation is allowed in Q6.

## Final Recommendation

Merge Q6 before retrying the full station staging load. Use the compact summary
and staged-row counts to verify the retry. If the retry succeeds cleanly,
generate the read-only reconciliation artifact next. Do not start Stage 18J-P,
Stage 18K, or any canonical apply path until their documented prerequisites are
satisfied.

## Q7 Follow-Up

After Q6 merged, the controlled warehouse station staging load succeeded and
canonical station count remained unchanged. The next read-only reconciliation
attempt failed before artifact generation because the report contained
DB-native datetime values that the CLI JSON printer could not serialize. The
artifact file was 0 bytes, no station-type dry-run was generated, no canonical
apply was run, and Stage 18J-P remained blocked.

Stage 18J-Q7 fixes reconciliation report serialization before retrying the
Stage 18J-Q3 read-only artifact path. Q7 does not authorize station-type
dry-run, canonical apply, Stage 18J-P, Stage 18K, or scheduler work.

## Q8 Follow-Up

After Q7 merged, the controlled read-only reconciliation artifact was generated
successfully and validated outside git. Its size makes direct review
impractical, so Stage 18J-Q8 adds an offline, memory-safe compact summary tool.

Q8 reads an existing `enrichment_staging_reconciliation/v1` artifact from an
operator-managed path and writes a compact deterministic extract with the source
basename, file size, SHA-256, schema, candidate counts, update/insert counts,
blocking reasons, confidence/risk counts, coverage counts, and capped sanitized
candidate samples.

Q8 does not authorize production data commits, production artifact commits,
production reconciliation from development, station-type dry-run, canonical
apply, production DB access from development, Stage 18J-P, Stage 18K, or
scheduler work. Stage 18J-P remains blocked until a compact review output
exists and is explicitly reviewed.
