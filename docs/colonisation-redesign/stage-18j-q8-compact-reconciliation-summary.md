# Stage 18J-Q8 - Compact Reconciliation Summary

## Purpose

Stage 18J-Q8 adds an offline, memory-safe compact summary tool for large
read-only reconciliation artifacts.

The current valid reconciliation artifact exists outside git in an
operator-managed location. It has schema
`enrichment_staging_reconciliation/v1`, `canonical_writes_planned = 0`,
zero-byte stderr, clean JSON termination, and no canonical station count
change. The artifact is too large for normal review, so the next safe step is a
bounded compact extract.

## Tool

CLI:

```sh
python3 apps/importer/src/reconciliation_artifact_summary.py \
    --artifact /operator/artifacts/enrichment_staging_reconciliation_YYYYMMDDTHHMMSSZ.json \
    --output /operator/artifacts/enrichment_staging_reconciliation_summary_YYYYMMDDTHHMMSSZ.json \
    --max-candidate-samples 50
```

The tool:

- reads only the supplied local JSON artifact,
- computes source file size and SHA-256 by streaming bytes,
- parses the JSON with `ijson`,
- streams candidate arrays one candidate at a time,
- keeps only counters, top distributions, and capped sanitized samples,
- writes deterministic JSON with `sort_keys=True`,
- does not import warehouse DB modules or connect to Postgres.

## Compact Output

The compact summary includes:

- summary schema `enrichment_reconciliation_artifact_summary/v1`,
- `safe_for_git = false`,
- source artifact basename only,
- source artifact SHA-256,
- source artifact size in bytes,
- artifact schema version,
- `canonical_writes_planned`,
- station candidate count,
- candidate counts by section,
- candidate action counts,
- candidate update and missing-canonical insert counts,
- top blocking reasons,
- top confidence/risk/reconciliation-state counts,
- available confidence/risk summary distributions,
- available source coverage summary counts,
- available warehouse coverage summary counts,
- capped sanitized candidate samples.

Samples deliberately exclude raw payloads, full canonical payloads, difference
values, full private paths, DSNs, passwords, tokens, and secrets. Production
summary output still defaults to `safe_for_git = false` because sampled
candidate identities can be production evidence even after sanitization.

## Boundaries

Q8 does not authorize:

- production data committed to git,
- production artifact committed to git,
- production summary committed unless separately synthetic or sanitized,
- production reconciliation from development,
- station-type dry-run,
- canonical apply,
- production DB access from development,
- scheduler or cron wiring,
- Stage 18J-P,
- Stage 18K.

The tool is an extract/review aid only. It does not change the reconciliation
artifact and does not turn report candidates into a write plan.

## Review Gate

Stage 18J-P remains blocked until:

- the compact summary is generated from the valid read-only artifact by an
  operator-approved offline command,
- the compact summary confirms `schema_version =
  enrichment_staging_reconciliation/v1`,
- `canonical_writes_planned = 0`,
- station candidate counts and update/insert counts are understood,
- blocking reasons and confidence/risk distributions are reviewed,
- source and warehouse coverage counts are reviewed,
- no production artifact or production summary is committed to git.

Only after that review may a separate prompt decide whether Stage 18J-P should
generate a station-type production dry-run. Q8 itself does not start Stage
18J-P.

## Validation

Local validation uses synthetic fixtures only:

```sh
./scripts/run_canonical_safety_tests.sh

.venv/bin/pytest \
  tests/test_enrichment_staging_reconciliation.py \
  tests/test_enrichment_staging_db_loader.py \
  tests/test_enrichment_report_contracts.py \
  tests/test_station_type_canonical_pilot.py \
  tests/test_enrichment_warehouse_boundary.py \
  tests/test_edsm_station_normalization.py \
  tests/test_reconciliation_artifact_summary.py \
  -q

.venv/bin/python -m py_compile \
  apps/importer/src/enrichment_staging_db_loader.py \
  apps/importer/src/enrichment_reconciliation.py \
  apps/importer/src/enrichment_warehouse_repository.py \
  apps/importer/src/station_type_canonical_pilot.py \
  apps/importer/src/reconciliation_artifact_summary.py \
  tests/test_reconciliation_artifact_summary.py

git diff --check
```

Changed docs and code should also be scanned for DSNs/secrets before opening
the PR.

## Final Recommendation

Merge Q8 before any Stage 18J-P decision. Generate and review a compact
operator-managed summary from the existing valid reconciliation artifact, keep
production outputs out of git, and do not run station-type dry-run, canonical
apply, Stage 18J-P, or Stage 18K from this stage.

## Stage 19A Follow-Up

Stage 19A defines the artifact taxonomy and chunked roadmap that should govern
any broader warehouse expansion after Q8. The station compact summary remains a
station-domain artifact and should use the domain-qualified naming direction
from Stage 19A, such as
`reconciliation_compact_summary_stations_<timestamp>.json`, for future operator
outputs.

Do not use Stage 19A to skip the Stage 18J continuation gates. The next station
steps remain Q9 compact summary review / station-type dry-run readiness, then
18J-P production dry-run retry only if explicitly approved, followed by review
and tiny manual apply approval packets if the dry-run is boring. Stage 19A does
not start Stage 18J-P, Stage 18K, scheduler wiring, or any canonical apply.

## Q9 Follow-Up

Stage 18J-Q9 reviews the generated compact summary and records the readiness
verdict for Stage 18J-P:

```text
Ready only with strict filter
```

The compact summary is valid and useful, but it is not a dry-run approval. It
shows that the full station reconciliation scope is too broad for Stage 18J-P.
Any station-type dry-run retry must be limited to externally identified,
non-ambiguous, non-volatile, permanent station-type candidates with an explicit
max-row bound and compact reviewable output. Station/body association work
remains blocked separately.

Q9 does not run station-type dry-run, approve an artifact, create an approval
record, run canonical apply, start Stage 18J-P, or start Stage 18K.
