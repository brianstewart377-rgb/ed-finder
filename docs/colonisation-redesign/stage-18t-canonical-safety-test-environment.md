# Stage 18T — Canonical Safety Test Environment

## Purpose

Stage 18T hardens the test environment around canonical-write-capable code.
The goal is to make the Stage 18J station type pilot repeatable in CI and
locally, including dependency installation, fail-closed dry-run/apply checks,
disposable Postgres rehearsal, and permission-boundary coverage.

This stage does not authorize production apply. It creates no production
artifact, approval record, production database changes, migrations, scheduler
wiring, UI/API apply controls, or broad canonical backfill.

## Current Gap

Stage 18J and Stage 18J-P proved the station type pilot remains guarded, but
the safety tests still depended on remembered local commands. The repo also
configured `asyncio_mode = "auto"` for pytest, which can warn when
`pytest-asyncio` is not installed in the active test environment.

The missing Stage 18J-R non-production rehearsal document remains a reference
gap on `origin/main`. Stage 18T fills the executable test-environment gap; it
does not recreate that missing document.

## CI Gates Added

The CI workflow now has a dedicated `Canonical safety tests` job using Python
3.12. The job installs explicit canonical test dependencies, then runs:

```sh
python -m pytest \
    tests/test_station_type_canonical_pilot.py \
    tests/test_enrichment_warehouse_boundary.py \
    tests/test_enrichment_staging_db_loader.py \
    tests/test_enrichment_report_contracts.py \
    tests/test_edsm_station_normalization.py \
    -q

python -m py_compile \
    apps/importer/src/station_type_canonical_pilot.py \
    tests/test_station_type_canonical_pilot.py \
    tests/test_station_type_canonical_pilot_postgres.py
```

The job also starts a disposable Postgres service container and runs the
Postgres rehearsal test with:

```sh
EDFINDER_CANONICAL_TEST_DSN=postgresql://edfinder:edfinder@localhost:5432/edfinder \
EDFINDER_CONFIRM_CANONICAL_TEST_DB=yes \
python -m pytest tests/test_station_type_canonical_pilot_postgres.py -q
```

## Test Dependencies / Prerequisites

CI dependencies are declared in `tests/requirements-ci.txt`. That file pulls
the API and importer runtime requirements and pins the test runner
prerequisites:

- `pytest`
- `pytest-asyncio`
- the Postgres driver from the importer requirements
- API and importer runtime dependencies used by imported modules

Adding `pytest-asyncio` to the CI dependency path makes the configured
`asyncio_mode` option recognized by the canonical safety job instead of relying
on whatever a local virtualenv already has installed.

## Local Canonical Safety Test Command

Developers can run the non-production canonical safety suite with one command:

```sh
./scripts/run_canonical_safety_tests.sh
```

The script uses `.venv/bin/python` when present and otherwise falls back to
`python`. It runs the Stage 18J pilot tests, warehouse boundary tests, staging
loader fail-closed tests, report contract tests, station normalization tests,
and `py_compile` for the pilot module and tests.

Disposable Postgres rehearsal is opt-in locally. To run it, the developer must
set both variables:

```sh
EDFINDER_CANONICAL_TEST_DSN=postgresql://edfinder:edfinder@localhost:5432/edfinder \
EDFINDER_CONFIRM_CANONICAL_TEST_DB=yes \
./scripts/run_canonical_safety_tests.sh
```

If `pg_virtualenv` is available, a fully disposable local cluster can be used
without touching an existing developer database:

```sh
pg_virtualenv sh -c 'EDFINDER_CANONICAL_TEST_DSN="host=localhost port=$PGPORT dbname=postgres user=$PGUSER" EDFINDER_CONFIRM_CANONICAL_TEST_DB=yes ./scripts/run_canonical_safety_tests.sh'
```

## Disposable Postgres Rehearsal

`tests/test_station_type_canonical_pilot_postgres.py` is skipped unless
`EDFINDER_CANONICAL_TEST_DSN` is set and
`EDFINDER_CONFIRM_CANONICAL_TEST_DB=yes` is present.

The test rejects unsafe DSNs before connecting. It refuses to run when the DSN:

- is missing,
- lacks the exact confirmation value,
- uses a host outside `localhost`, `127.0.0.1`, `::1`, or the CI service host
  name `postgres`,
- lacks a database name,
- contains obvious production markers such as `prod`, `production`, `live`, or
  `hetzner`.

When enabled, the test creates a random disposable schema and disposable test
roles, then drops them at teardown. It verifies:

- the guarded apply path can update a disposable `stations.station_type` value,
- only the station type changes,
- no canonical-like table row counts change,
- station identity pre-image mismatch fails,
- station type pre-image mismatch fails,
- artifact checksum mismatch fails,
- expected candidate count mismatch fails,
- approved table mismatch fails,
- approved field mismatch fails,
- source run mismatch fails,
- explicit max row approval is required,
- rollback pre-image, audit rows, and post-apply verification are emitted.

## Permission Boundary Tests

The disposable Postgres rehearsal creates these test-only roles:

- `warehouse_loader_test_<token>`
- `canonical_apply_test_<token>`
- `canonical_read_test_<token>`

The permission-boundary test proves the warehouse loader role cannot update
`stations`, insert/update/delete canonical-like tables, or touch systems,
bodies, station-body links, rings, or body scan facts. It also proves the
canonical apply role can update only `stations.station_type` in the disposable
schema and cannot update station name, distance fields, systems, bodies,
station-body links, rings, or scan facts.

These roles are disposable test roles only. Stage 18T does not create or modify
production users or permissions.

## Tests Required Before Production Dry-Run

Before any future production station-type dry-run, the following gates should
be green on the candidate branch:

- the `Canonical safety tests` CI job,
- `./scripts/run_canonical_safety_tests.sh`,
- the focused Stage 18J pytest suite,
- the disposable Postgres rehearsal in CI,
- `git diff --check`.

A production-connected reconciliation command still requires separately
verified read-only/report-only DSN context. Stage 18T does not authorize that
command. Stage 18J-Q documents the production reconciliation artifact
prerequisite and the report-only generation contract:
[`stage-18j-q-production-reconciliation-artifact-readiness.md`](./stage-18j-q-production-reconciliation-artifact-readiness.md).

## Tests Required Before Production Apply

Before any future production apply, repeat the dry-run gates and additionally
require:

- the exact dry-run artifact hash to be approved,
- the exact candidate count to be approved,
- the exact source run/file to be approved,
- the table `stations` and field `station_type` to be approved,
- the bounded max row count to be approved,
- the apply DSN context to be explicitly approved,
- the disposable Postgres rehearsal and permission-boundary tests to be green,
- manual review confirming every candidate is an exact external identity match
  and no known canonical station type is overwritten by default.

Any future production apply still requires a separate explicit instruction and
approval. The guarded apply path must remain unavailable to UI/API, scheduler,
Docker automation, or broad backfill flows.

## Remaining Gaps

- The Stage 18J-R non-production rehearsal document is still absent on
  `origin/main`.
- The Postgres rehearsal uses a minimal disposable schema tailored to the
  station type pilot, not the full production schema.
- The permission-boundary test proves role behavior in a disposable schema. It
  does not create or validate production roles.
- Stage 18T does not generate a production reconciliation artifact or
  production dry-run artifact.

## Final Recommendation

Keep Stage 18J canonical apply blocked from production until the canonical
safety CI job is green, the local runner passes, a suitable report-only
production reconciliation artifact exists, and a separate explicit approval
names the exact artifact hash, candidate count, source run/file, table, field,
max row count, and apply DSN context.
