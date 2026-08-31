# ED-Finder R1 — Operator Real-System Snapshot
## Review 1 — Stage Definition

Date: 2026-08-31
Status: pre-code stage definition; operator/read-only only.

## Goal

Use the repository's existing `ed-new-operator` GitHub Actions/SSH boundary to execute the already-reviewed R1 real-system snapshot implementation against the configured candidate PostgreSQL database and return current canonical `systems`, `bodies`, and `body_rings` evidence for explicit named systems.

This exists because the ChatGPT runtime cannot directly reach the Hetzner database, while the repository already has a pinned-SSH, environment-secret operator path.

## Safety boundary

- GET/SELECT/SHOW only.
- The snapshot implementation itself calls `conn.set_session(readonly=True, autocommit=True)` and verifies `SHOW transaction_read_only = on` before canonical reads.
- Maximum 20 explicit selectors per workflow request.
- No discovery query, wildcard search, table scan by score, ranking rebuild, migration, write, cache change, deployment, or production Finder change.
- Use the existing `ED_NEW_CANDIDATE_DATABASE_URL` secret and pinned SSH trust from the `ed-new-operator` environment.
- Database URL must never be emitted to logs or artifacts.
- Snapshot code is checked out at an immutable reviewed revision, not from the request commit.
- Output is a JSON artifact plus compact log summary.

## Intended workflow trigger

A new dedicated workflow watches only:

`.github/r1-real-snapshot-requests/*.json`

Request shape:

```json
{"operation":"r1-real-system-snapshot","selectors":["HR 1188","Brambai DL-Y g32"]}
```

Validation requires exactly one request file changed in the triggering commit, exact keys only, 1-20 unique non-empty selector strings, bounded selector length, and exact operation name.

## Initial real-system batches

If the first batch succeeds, run additional request commits. Initial target is up to 60 explicit real systems across:

1. golden + ammonia regression controls;
2. sparse controls + famous/populated/exotic systems;
3. nearby/diverse star systems for general projection coverage.

Each batch remains independently bounded to 20.

## Non-goals

- no Plan Fit calibration;
- no candidate-plan generation/resilience;
- no live Finder ranking;
- no Evidence Store mutation;
- no DB schema changes;
- no inference that database-default false/zero is confirmed negative.

## Acceptance

Stage succeeds if workflow execution proves read-only state, produces parseable snapshot artifacts, reports requested/found/not-found systems, and no sensitive DB credential appears in artifacts/log summaries.
