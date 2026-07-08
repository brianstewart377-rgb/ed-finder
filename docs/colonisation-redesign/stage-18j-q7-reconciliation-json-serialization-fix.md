# Stage 18J-Q7 — Reconciliation JSON Serialization Fix

## Purpose

Stage 18J-Q7 fixes the read-only reconciliation artifact path after the first
post-Q6 production attempt failed while printing JSON.

This stage is a serialization fix only. It does not run production
reconciliation, generate or approve a production artifact, run a station-type
dry-run, apply canonical writes, touch the production DB, start Stage 18J-P, or
start Stage 18K.

## Production Finding

After Stage 18J-Q6 merged, the controlled warehouse station staging load
succeeded. Warehouse row counts were populated, canonical station count
remained unchanged, and no reconciliation/apply/station-type dry-run/canonical
write was run during the staging load.

The next read-only reconciliation attempt failed while printing JSON:

```text
TypeError: Object of type datetime is not JSON serializable
```

The failure occurred in the `--report-reconciliation` CLI path while calling
`json.dumps(report, sort_keys=True, indent=2)`.

## Safety State

The failed reconciliation attempt produced a 0-byte artifact and did not alter
canonical data.

- no canonical data changed,
- canonical station count remained `284763`,
- warehouse staging rows remained loaded,
- no station-type dry-run artifact was generated,
- no canonical apply was run,
- Stage 18J-P remained blocked,
- Stage 18K remained untouched.

## Fix

Q7 makes report output JSON-safe before printing. DB-native scalar values are
converted without dropping fields:

- `datetime` and `date` values serialize to ISO-8601 strings,
- `Decimal` values serialize to strings, matching the existing deterministic
  canonical JSON convention,
- mappings, sequences, tuples, and sets are recursively converted to
  JSON-native structures,
- deterministic `sort_keys=True` output is preserved.

The fix is applied to the read-only reconciliation report wrapper and CLI JSON
printing path. It does not introduce a write path.

## Boundaries

Q7 does not authorize:

- production data committed to git,
- production artifacts committed to git,
- production reconciliation from development,
- station-type dry-run,
- canonical apply,
- production DB access from development,
- UI/API apply controls,
- scheduler or cron wiring,
- live EDSM/API crawl,
- broad canonical work,
- Stage 18J-P,
- Stage 18K.

`canonical_writes_planned` remains `0`, and reconciliation remains
read-only/report-only.

## Retry Criteria

After Q7 merges, Stage 18J-Q3 may retry the read-only reconciliation artifact
generation only through the approved operator path.

The retry must confirm:

- output artifact is non-empty valid JSON,
- schema is `enrichment_staging_reconciliation/v1`,
- `canonical_writes_planned = 0`,
- station candidates remain present,
- no production apply or station-type dry-run is run.

Stage 18J-P remains blocked until a valid reconciliation artifact exists and is
explicitly reviewed.

## Validation

Q7 validation must include canonical safety tests, reconciliation tests with
DB-native timestamp/decimal values, report contract tests, `py_compile`,
`git diff --check`, and a changed-doc secret scan.

## Final Recommendation

Merge Q7 before retrying the read-only reconciliation artifact generation.
Treat any JSON serialization failure or 0-byte artifact as a hard stop. Do not
start Stage 18J-P, Stage 18K, station-type dry-run, or canonical apply until
their documented prerequisites are satisfied.

