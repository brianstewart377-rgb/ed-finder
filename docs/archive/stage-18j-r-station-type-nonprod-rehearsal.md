# Stage 18J-R station type non-production rehearsal

This document is historical evidence only.
It is not current operational guidance.
For current project state, use docs/colonisation-redesign/stage-19-state-authority.json.
Stage 19 is currently paused.
Stage 19AS-AU has not run.
Do not use this document to authorize writes, canonical apply, production DB actions, or Stage 19 execution.

## Archive source

This archive preserves useful historical documentation from PR #105:

- PR: https://github.com/brianstewart377-rgb/ed-finder/pull/105
- Branch: `stage-18j-r-station-type-nonprod-rehearsal`
- Head: `14dc9aef0a16203fb407073a03aecba126ab8dfa`
- Original title: `docs: Stage 18J-R station type non-production rehearsal report`

The original PR also changed active roadmap and runbook files. Those active links and operational pointers are intentionally not restored here as current guidance.

## Historical purpose

Stage 18J-R rehearsed the Stage 18J station type canonical pilot without touching production data, creating production artifacts, starting broad backfill, or advancing beyond station-type-only scope.

The historical rehearsal existed to show that the pilot tooling could build a deterministic dry-run artifact, exercise the guarded apply path against disposable fixture data, emit audit and rollback evidence, verify post-apply state, and keep every non-approved canonical table and downstream planner surface untouched.

The original report stated that it was a rehearsal report, not production approval. The only canonical field in scope was `stations.station_type`; every other canonical field, derived product state, scheduler path, live crawler, and Docker invocation remained out of scope.

## Historical preconditions

The original report said the Stage 18J implementation was present on `main` through merge commit `acf7b88222ac1f0d20136815aa741f48dd426ec6`.

Before any real apply command was considered, the operator had to confirm the DSN pointed only to a disposable or staging database. The rehearsal did not pass any DSN to the apply CLI and did not connect to Postgres. The guarded apply behavior was exercised only by `tests/test_station_type_canonical_pilot.py` through an in-memory `FakeApplyConn`.

| Precondition | Historical rehearsal state |
|---|---|
| Stage 18J code present | Confirmed by branch history including merge commit `acf7b88`. |
| Production apply forbidden | Confirmed; no production apply command was run. |
| Production artifact forbidden | Confirmed; no artifact was produced from production data. |
| Disposable or non-production data only | Confirmed; guarded apply used `FakeApplyConn` fixture rows only. |
| Narrow scope | Confirmed; the pilot code and tests targeted only `stations.station_type`. |
| Warehouse loaders remain non-canonical | Confirmed by boundary and loader tests in the validation set. |

## Historical rehearsal environment

| Environment item | Historical value |
|---|---|
| Branch | `stage-18j-r-station-type-nonprod-rehearsal` |
| Base | `origin/main` at Stage 18J merge commit `acf7b88` |
| Data source | Local pytest fixtures and in-memory fake connection |
| Apply target | `FakeApplyConn`, not a real database |
| Production DB | Not touched |
| Production artifact | Not created |

The original report included local branch-preparation commands. Those commands are intentionally not reproduced here as current instructions.

## Historical validation commands and results

The original report recorded these validation results:

| Command group | Historical result |
|---|---|
| Stage 18J focused pytest | Passed: `26 passed in 0.10s`. |
| Stage 18J plus warehouse boundary pytest set | Passed: `81 passed in 0.27s`. |
| `py_compile` | Passed: no output. |
| `git diff --check` | Passed: no output. |

These results are preserved as historical evidence only. They are not current CI status and do not authorize current production apply.

## Historical dry-run artifact result

The rehearsal dry-run path was exercised by `test_dry_run_builds_deterministic_station_type_artifact` and `test_cli_writes_dry_run_json_artifact`.

The dry-run builder produced `station_type_canonical_pilot_dry_run/v1`, marked the artifact as `dry_run = true`, recorded the canonical table as `stations`, recorded the canonical field as `station_type`, and embedded a canonical JSON SHA-256 checksum recomputed in the test.

| Dry-run check | Historical rehearsal result |
|---|---|
| Versioned artifact | `station_type_canonical_pilot_dry_run/v1` |
| Default dry-run behavior | Confirmed through builder and CLI tests. |
| Approved table | `stations` only. |
| Approved field | `station_type` only. |
| Artifact checksum | Recomputed and matched through `pilot.artifact_sha256(...)`. |
| Row limit behavior | Explicit limit accepted and first-pilot maximum enforced by code. |
| Unsafe evidence handling | Blocked rows included explicit `blocking_reasons`. |

## Historical guarded apply result

The guarded apply path was exercised only against `FakeApplyConn` fixture data. The successful rehearsal constructed a dry-run artifact, approved its exact checksum, candidate count, table, field, source run, source file, approval ID, confirmation flag, and `max_rows = 1`, then called `apply_station_type_pilot(...)`.

The fake database row began as `station_type = 'Unknown'` and ended as `station_type = 'Orbis'`.

The apply rehearsal selected by canonical primary key plus `system_id64`, verified station name and station type pre-image, then updated only `stations.station_type`. The test inspected recorded SQL and confirmed that `distance_from_star` and `station_body_links` did not appear in the apply SQL.

| Apply guard | Historical rehearsal result |
|---|---|
| Explicit confirmation required | Confirmed by parser and apply validation tests. |
| Approval ID required | Confirmed by validation contract. |
| Artifact checksum required | Confirmed; mismatched checksum failed closed. |
| Candidate count approval required | Confirmed; count mismatch failed closed. |
| Table and field approval required | Confirmed; non-`station_type` field failed closed. |
| Explicit max row approval required | Confirmed; missing `max_rows` failed closed. |
| Pre-image validation | Confirmed; changed station type rolled back. |
| Identity pre-image validation | Confirmed; renamed station rolled back. |

## Historical audit, rollback, and verification evidence

The successful guarded apply rehearsal emitted an apply audit artifact with schema `station_type_canonical_pilot_apply/v1`. The audit included the apply run ID, dry-run artifact checksum, approval metadata, row-level old and new values, and summary counts.

It also contained a rollback pre-image artifact with schema `station_type_canonical_pilot_rollback_preimage/v1` and a post-apply verification artifact with schema `station_type_canonical_pilot_verification/v1`.

| Artifact | Historical evidence |
|---|---|
| Dry-run artifact | Versioned, checksumed, deterministic station-type-only artifact. |
| Apply audit | `station_type_canonical_pilot_apply/v1`, summary `applied = 1`. |
| Rollback pre-image | `station_type_canonical_pilot_rollback_preimage/v1`, old value captured before apply. |
| Post-apply verification | `station_type_canonical_pilot_verification/v1`, summary `ok = true`. |
| Secrets hygiene | No DSN, API key, or private path emitted by fixture artifacts. |

The rollback pre-image row recorded `pre_image_value = 'Unknown'` and `applied_value = 'Orbis'`. The verification artifact confirmed that the row had the expected approved station type and that the verification summary was `ok = true`.

## Historical tables confirmed untouched

| Object or surface | Historical rehearsal status |
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

## Historical failure and stop conditions tested

The fixture-backed rehearsal covered failure cases that were intended to remain stop conditions:

- missing or mismatched stable external identity;
- name-only identity;
- internal primary-key-only identity;
- ambiguous canonical matches;
- mismatched `system_id64`;
- station-name mismatch;
- transient or unsupported station types;
- known canonical values that should not be overwritten;
- stale, volatile, source-only, or report-only evidence;
- undated evidence without exception;
- multi-field differences.

The apply contract blocked unsupported write aliases, missing approval parameters, missing explicit confirmation, checksum mismatch, unapproved table or field, missing `max_rows`, changed canonical station type pre-image, and changed station identity pre-image. The pre-image failure cases rolled back the fake transaction and left fixture data unchanged.

## Historical production blocks

The original report said Stage 18J-R was not production approval. A production apply remained blocked until a separate production-specific approval confirmed the production DSN, row limit, artifact checksum, source run/file, operator approval ID, database boundary, role permissions, backup and rollback ownership, artifact storage, and post-apply verification procedure.

| Production block | Historical status after rehearsal |
|---|---|
| Production apply | Still blocked; not run. |
| Production artifact | Still blocked; not created. |
| Broad canonical backfill | Still blocked. |
| Non-station canonical writes | Still blocked. |
| Live EDSM/API crawl | Still blocked. |
| Docker invocation from UI/API | Still blocked. |
| Production scheduler wiring | Still blocked. |
| Ordinary warehouse loaders writing canonical tables | Still blocked. |
| Migration | Not added; stop if future rehearsal could not run without one. |

## Current authority caveat

The original report's recommendation and active-doc links are preserved here only as historical evidence. They are not current operational guidance.

Current project state is governed by `docs/colonisation-redesign/stage-19-state-authority.json`: Stage 19 is paused, Stage 19AS-AU has not run, and this archive recovery did not execute Stage 19.
