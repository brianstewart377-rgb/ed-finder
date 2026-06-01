# Stage 18J-R — Station Type Non-Production Rehearsal

## Purpose

Stage 18J-R rehearses the Stage 18J station type canonical pilot without touching production data, creating production artifacts, starting broad backfill, or advancing beyond the station-type-only scope. The rehearsal exists to prove that the current pilot tooling can build a deterministic dry-run artifact, exercise the guarded apply path against disposable fixture data, emit audit and rollback evidence, verify the post-apply state, and keep every non-approved canonical table and downstream planner surface untouched.

This document is a rehearsal report, not production approval. It keeps the Stage 18J production blocks from the canonical write design review and the warehouse database boundary review in force. The only canonical field in scope is `stations.station_type`; every other canonical field, derived product state, scheduler path, live crawler, and Docker invocation remains out of scope.

## Preconditions

The Stage 18J implementation is present on `main` through merge commit `acf7b88222ac1f0d20136815aa741f48dd426ec6`. This rehearsal branch was created from `origin/main` so that the local-only `main` caveat cannot influence the Stage 18J-R evidence. In this checkout, the local `main` branch was already equal to `origin/main`, and `backup/local-main-ee6f546-map-refactor` was still created before the rehearsal branch was made.

Before any real apply command is considered, the operator must confirm the DSN points only to a disposable or staging database. This rehearsal did not pass any DSN to the apply CLI and did not connect to Postgres. The guarded apply behavior was exercised only by `tests/test_station_type_canonical_pilot.py` through an in-memory `FakeApplyConn`, which is disposable fixture data and cannot reach production.

| Precondition | Rehearsal state |
|---|---|
| Stage 18J code present | Confirmed by branch history including merge commit `acf7b88`. |
| Production apply forbidden | Confirmed; no production apply command was run. |
| Production artifact forbidden | Confirmed; no artifact was produced from production data. |
| Disposable or non-production data only | Confirmed; guarded apply used `FakeApplyConn` fixture rows only. |
| Narrow scope | Confirmed; the pilot code and tests target only `stations.station_type`. |
| Warehouse loaders remain non-canonical | Confirmed by boundary and loader tests in the validation set. |

## Rehearsal Environment

The rehearsal environment is the repository checkout on branch `stage-18j-r-station-type-nonprod-rehearsal`. The rehearsal data is fixture-backed and local-only. It uses the helper builders `report_with(...)` and `station_candidate(...)` from `tests/test_station_type_canonical_pilot.py` to construct deterministic read-only reconciliation input, then uses `FakeApplyConn` and `FakeApplyCursor` to simulate row selection, station-type update, transaction commit, transaction rollback, and SQL inspection.

No live EDSM/API crawl was started. No Docker command was invoked. No production scheduler wiring was added. No migration was added. No production DSN was inspected, stored, logged, or used.

| Environment item | Value |
|---|---|
| Branch | `stage-18j-r-station-type-nonprod-rehearsal` |
| Base | `origin/main` at Stage 18J merge commit `acf7b88` |
| Data source | Local pytest fixtures and in-memory fake connection |
| Apply target | `FakeApplyConn`, not a real database |
| Production DB | Not touched |
| Production artifact | Not created |

## Commands Run

The branch preparation commands were:

```sh
git switch main
git branch backup/local-main-ee6f546-map-refactor || true
git status --short --branch
git fetch origin main
git switch -c stage-18j-r-station-type-nonprod-rehearsal origin/main
git log --oneline -12
```

The Stage 18J-R validation commands are:

```sh
.venv/bin/pytest tests/test_station_type_canonical_pilot.py -q
```

```sh
.venv/bin/pytest \
    tests/test_station_type_canonical_pilot.py \
    tests/test_enrichment_warehouse_boundary.py \
    tests/test_enrichment_staging_db_loader.py \
    tests/test_enrichment_report_contracts.py \
    tests/test_edsm_station_normalization.py \
    -q
```

```sh
.venv/bin/python -m py_compile \
    apps/importer/src/station_type_canonical_pilot.py \
    tests/test_station_type_canonical_pilot.py
```

```sh
git diff --check
```

The exact command results are recorded after validation below.

| Command | Result |
|---|---|
| Stage 18J focused pytest | **Passed**: 26 passed in 0.10s. |
| Stage 18J plus warehouse boundary pytest set | **Passed**: 81 passed in 0.27s. |
| `py_compile` | **Passed**: no output (success). |
| `git diff --check` | **Passed**: no output (success). |

## Dry-Run Artifact Result

The rehearsal dry-run path is exercised by `test_dry_run_builds_deterministic_station_type_artifact` and `test_cli_writes_dry_run_json_artifact`. The dry-run builder produces `station_type_canonical_pilot_dry_run/v1`, marks the artifact as `dry_run = true`, records the canonical table as `stations`, records the canonical field as `station_type`, and embeds a canonical JSON SHA-256 checksum that is recomputed in the test.

The eligible fixture row promotes an old canonical value of `Unknown` to the normalized permanent type `Orbis` using matching `market_id`, matching `system_id64`, matching station name, source run/file keys, and a source record hash. Unsafe candidates are blocked rather than silently omitted.

| Dry-run check | Rehearsed result |
|---|---|
| Versioned artifact | `station_type_canonical_pilot_dry_run/v1` |
| Default dry-run behavior | Confirmed through builder and CLI tests. |
| Approved table | `stations` only. |
| Approved field | `station_type` only. |
| Artifact checksum | Recomputed and matched through `pilot.artifact_sha256(...)`. |
| Row limit behavior | Explicit limit is accepted and first-pilot maximum is enforced by code. |
| Unsafe evidence handling | Blocked rows include explicit `blocking_reasons`. |

## Guarded Apply Result

The guarded apply path is exercised only against `FakeApplyConn` fixture data. The successful rehearsal case constructs a dry-run artifact, approves its exact checksum, candidate count, table, field, source run, source file, approval ID, confirmation flag, and `max_rows = 1`, then calls `apply_station_type_pilot(...)`. The fake database row begins as `station_type = 'Unknown'` and ends as `station_type = 'Orbis'`.

The apply rehearsal confirms that the SQL path selects by canonical primary key plus `system_id64`, verifies station name and station type pre-image, then updates only `stations.station_type`. The test inspects recorded SQL and confirms that `distance_from_star` and `station_body_links` do not appear in the apply SQL.

| Apply guard | Rehearsed result |
|---|---|
| Explicit confirmation required | Confirmed by parser and apply validation tests. |
| Approval ID required | Confirmed by validation contract. |
| Artifact checksum required | Confirmed; mismatched checksum fails closed. |
| Candidate count approval required | Confirmed; count mismatch fails closed. |
| Table and field approval required | Confirmed; non-`station_type` field fails closed. |
| Explicit max row approval required | Confirmed; missing `max_rows` fails closed. |
| Pre-image validation | Confirmed; changed station type rolls back. |
| Identity pre-image validation | Confirmed; renamed station rolls back. |

## Audit / Rollback / Verification Artifacts

The successful guarded apply rehearsal emits an apply audit artifact with schema `station_type_canonical_pilot_apply/v1`. The audit includes the apply run ID, dry-run artifact checksum, approval metadata, row-level old and new values, and summary counts. It also contains a rollback pre-image artifact with schema `station_type_canonical_pilot_rollback_preimage/v1` and a post-apply verification artifact with schema `station_type_canonical_pilot_verification/v1`.

The rollback pre-image row records `pre_image_value = 'Unknown'` and `applied_value = 'Orbis'`. The verification artifact confirms that the row now has the expected approved station type and that the verification summary is `ok = true`.

| Artifact | Rehearsed evidence |
|---|---|
| Dry-run artifact | Versioned, checksumed, deterministic station-type-only artifact. |
| Apply audit | `station_type_canonical_pilot_apply/v1`, summary `applied = 1`. |
| Rollback pre-image | `station_type_canonical_pilot_rollback_preimage/v1`, old value captured before apply. |
| Post-apply verification | `station_type_canonical_pilot_verification/v1`, summary `ok = true`. |
| Secrets hygiene | No DSN, API key, or private path is emitted by fixture artifacts. |

## Tables Confirmed Untouched

The rehearsal proves that the successful guarded apply updates only the approved field on the approved table. The Stage 18J unit test inspects the SQL emitted by the fake apply path and confirms that non-scope objects such as `distance_from_star` and `station_body_links` do not appear. The broader validation set also keeps ordinary warehouse loaders constrained to warehouse staging tables and report-only reconciliation semantics.

| Object or surface | Rehearsal status |
|---|---|
| `stations.station_type` | Only approved mutation in fixture apply. |
| `systems` | Untouched. |
| `bodies` | Untouched. |
| `station_body_links` | Untouched and absent from apply SQL. |
| `body_rings` | Untouched. |
| `body_scan_facts` | Untouched. |
| Distance fields | Untouched; `distance_from_star` absent from apply SQL. |
| Services, economies, faction, government, allegiance | Untouched. |
| Planner, scoring, Simulation Preview, optimiser, role, Build Plan state | Untouched. |
| Live EDSM/API and Docker paths | Not invoked. |
| Production scheduler wiring | Not added. |

## Failure/Stop Conditions Tested

The fixture-backed rehearsal intentionally covers failure cases that must remain stop conditions. Candidate construction blocks missing or mismatched stable external identity, name-only identity, internal primary-key-only identity, ambiguous canonical matches, mismatched `system_id64`, station-name mismatch, transient or unsupported station types, known canonical values that should not be overwritten, stale/volatile/source-only/report-only evidence, undated evidence without exception, and multi-field differences.

The apply contract blocks unsupported write aliases, missing approval parameters, missing explicit confirmation, checksum mismatch, unapproved table or field, missing `max_rows`, changed canonical station type pre-image, and changed station identity pre-image. The pre-image failure cases roll back the fake transaction and leave fixture data unchanged.

| Stop condition | Tested behavior |
|---|---|
| Name-only or missing stable station identifier | Blocked before dry-run eligibility. |
| Internal PK without external identity proof | Blocked before dry-run eligibility. |
| EDSM station ID without explicit flag | Blocked unless deliberately enabled. |
| Ambiguous or missing canonical match | Blocked. |
| Non-station-type difference in same candidate | Blocked. |
| Source-only, stale, volatile, risky, report-only evidence | Blocked. |
| Unsupported `--write` / `--commit` aliases | CLI fails closed. |
| Missing apply approval contract | CLI and validation fail closed. |
| Changed station type pre-image | Apply rolls back. |
| Changed station name pre-image | Apply rolls back. |

## Remaining Production Blocks

Stage 18J-R is not production approval. A production apply remains blocked until a separate production-specific approval confirms the production DSN, row limit, artifact checksum, source run/file, operator approval ID, database boundary, role permissions, backup and rollback ownership, artifact storage, and post-apply verification procedure.

The following blocks remain in place.

| Production block | Status after rehearsal |
|---|---|
| Production apply | Still blocked; not run. |
| Production artifact | Still blocked; not created. |
| Broad canonical backfill | Still blocked. |
| Non-station canonical writes | Still blocked. |
| Live EDSM/API crawl | Still blocked. |
| Docker invocation from UI/API | Still blocked. |
| Production scheduler wiring | Still blocked. |
| Ordinary warehouse loaders writing canonical tables | Still blocked. |
| Migration | Not added; stop if future rehearsal cannot run without one. |

## Recommendation

The Stage 18J-R fixture-backed rehearsal is sufficient as a non-production rehearsal for the current pilot implementation once the validation commands in this report pass. The next safe step is to review this documentation and the pull request evidence. Production apply should remain blocked until a separate, explicit production approval names a specific non-production-proven artifact checksum, a maximum row count, source run/file keys, the production database boundary, and a rollback/verification archive process.
