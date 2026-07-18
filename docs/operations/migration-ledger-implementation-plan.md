# Migration Ledger Implementation Plan

This document turns the audit finding around migration replay into a concrete
implementation plan for ED-Finder.

It is intentionally practical:

- preserve raw SQL as the source of truth
- keep the production deploy path boring
- avoid a big-bang migration-system rewrite
- make production state auditable instead of implied by shell comments

## Goal

Replace the current "replay every numbered SQL file on every deploy" model with
a ledgered migration path that:

- applies only unapplied migrations
- records filename, checksum, and applied time
- makes manual/data-heavy exceptions explicit
- stops treating operational backfills and maintenance SQL as schema migrations

## Current State Audit

### What the repo does today

- `scripts/deploy_main.sh` finds every `sql/[0-9][0-9][0-9]_*.sql`, excludes
  `019_nullable_coords.sql`, sorts lexically, and pipes each file into `psql`
  on every deploy.
- `scripts/seed_check.sh` applies every `sql/*.sql` except `seed_preview.sql`
  against a fresh database in lexical order.
- `scripts/release-main-to-prod.ps1` shells into the server and runs
  `bash scripts/deploy_main.sh`, so the replay-all behavior is the canonical
  production path.

### Why that is unsafe

- The deploy path assumes every numbered SQL file is permanently idempotent.
- Production migration state is not recorded anywhere in the database.
- `019_nullable_coords.sql` is excluded only by a shell glob exception and a
  comment.
- Two files historically shared the `025` prefix:
  - `sql/025_eddn_ring_identity.sql`
  - `sql/031_eddn_ring_identity_hardening.sql` now carries the former hardening
    file so the sequence is at least uniquely named even before a later full
    numbering tidy-up.
- `sql/999_refresh_materialized_views.sql` is not a schema migration at all; it
  is an operational refresh command.
- `sql/008_body_filter_aggregates.sql` mixes real schema change with a long,
  rerunnable backfill block and is therefore not a clean "deploy-safe forever"
  migration unit.

### Edge cases we must handle explicitly

#### `019_nullable_coords.sql`

- This file is partly schema change and partly a large data rewrite on
  `systems`.
- The production deploy script already treats it as a manual runbook step.
- A ledgered system must preserve that explicit/manual status instead of hiding
  it in a filename filter.

#### Historical `025` duplicate numbering

- The hardening follow-up has been renamed to
  `031_eddn_ring_identity_hardening.sql` so the tree is no longer ambiguous.
- Manifest ordering still carries the logical apply order explicitly.
- A later numbering tidy-up may still be worthwhile if we want filenames to
  match strict chronological sequence.

#### `008_body_filter_aggregates.sql`

- The column additions are migration-like.
- The large aggregate backfill is operational work that should not be implied by
  future normal deploys.
- Ledgering immediately removes the worst replay problem, but this file should
  still be split later into schema and backfill concerns.

#### `999_refresh_materialized_views.sql`

- This is an operational convenience file, not a schema migration.
- It should move out of the ledgered migration sequence entirely.

## Recommendation

Use a small in-repo migration ledger first, not a full toolchain migration.

Reasoning:

- The repo already standardises on raw SQL plus thin shell/PowerShell wrappers.
- A custom, auditable in-repo applier is faster to land safely than introducing
  a new binary distribution path across production, CI, and developer machines.
- We can still adopt `dbmate` later if we decide the external tool is worth it
  once the dangerous replay model is gone.

This is not anti-`dbmate`; it is sequencing. The urgent fix is ledgered
application behavior, not tool branding.

## Proposed Design

### 1. Add a ledger table

Create a committed bootstrap migration that defines:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename      TEXT PRIMARY KEY,
    checksum_sha256 TEXT NOT NULL,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    apply_mode    TEXT NOT NULL DEFAULT 'auto',
    notes         TEXT
);
```

Notes:

- `filename` is the stable identity.
- `checksum_sha256` lets the applier detect drift if an old migration file is
  edited after application.
- `apply_mode` supports `auto`, `manual`, and `baseline` without inventing
  hidden shell behavior.

### 2. Replace globbing with an explicit manifest

Add a committed ordered manifest, for example:

- `sql/migration-manifest.txt`

Each line should name exactly one migration in canonical order.

Example shape:

```text
001_schema.sql
002_indexes.sql
...
018_observed_facts_stage6a.sql
019_nullable_coords.sql|manual
020_rating_version.sql
...
031_eddn_ring_identity_hardening.sql
```

Why a manifest:

- removes lexical-order accidents
- makes manual exceptions explicit
- lets us exclude non-migrations like `999_refresh_materialized_views.sql`
- lets seed and deploy use the same source of truth

### 3. Add one canonical applier

Add a script such as:

- `scripts/apply_migrations.sh`

Responsibilities:

- create the ledger table if missing
- read the manifest in order
- skip `manual` entries during normal auto-apply
- compute the file checksum before applying
- if the filename is already in `schema_migrations`:
  - verify checksum matches
  - skip re-application
- if the filename is absent:
  - apply with `psql -v ON_ERROR_STOP=1`
  - insert a ledger row
- fail loudly on checksum mismatch or missing files

### 4. Baseline production once

We cannot infer production state purely from filenames because the old system
replayed files without a ledger and `019` was handled manually.

The production cutover should therefore be:

1. Audit the live database for markers of historically applied migrations.
2. Create the ledger table.
3. Insert baseline rows for migrations already represented in production.
4. Mark `019_nullable_coords.sql` explicitly as:
   - `manual_applied`, if the schema/data change is confirmed complete, or
   - `manual_pending`, if not.
5. Switch deploys to the ledgered applier only after the baseline is written and
   reviewed.

This baseline step should be a reviewed one-time operator action, not an
implicit side effect of normal deploys.

### 5. Update the current callers

#### `scripts/deploy_main.sh`

- Replace the current `find sql ... | sort` loop with the canonical applier.
- Remove the hardcoded `! -name '019_nullable_coords.sql'` filter.
- Keep `--skip-migrations`, but make it skip the ledgered applier rather than a
  full replay loop.

#### `scripts/seed_check.sh`

- Stop applying `sql/*.sql` blindly.
- Apply only the manifest-listed auto migrations.
- Continue applying `seed_preview.sql` separately.
- Keep invariant checks after schema + seed application.

#### CI and local parity paths

- Anything that currently assumes "apply every SQL file" should be repointed to
  the same canonical applier or manifest.
- The goal is one migration truth, not one truth for prod and another for CI.

## File Classification Plan

### Keep as ledgered migrations

- true schema and one-time data-shape migrations
- examples: `001` through normal schema evolution files like `020`, `021`,
  `022`, `023`, `024`, `026`, `027`, `028`, `029`, `030`

### Explicit manual entries

- `019_nullable_coords.sql`

### Remove from normal migration path

- `999_refresh_materialized_views.sql`

Recommended destination:

- `sql/ops/refresh_materialized_views.sql`

### Split later, but not required to land the ledger

- `008_body_filter_aggregates.sql`

Immediate safe posture:

- keep it ledgered once so normal deploys stop replaying it forever

Follow-up posture:

- split into:
  - schema change migration
  - separate rerunnable ops/backfill script

## Numbering Cleanup Plan

### Duplicate `025`

Implemented approach:

- rename the hardening follow-up to
  `sql/031_eddn_ring_identity_hardening.sql`

Why:

- it avoids renumbering a long tail of later files
- it removes ordering ambiguity immediately
- it is easy to represent in the new manifest

Required verification before landing:

- run fresh-database application in canonical order
- confirm no later migration depends on the hardening file being positioned
  before `026`

If that dependency exists, the alternative is a one-time renumber sweep of later
files, but that is the riskier option and should only be taken if required.

## Rollout Plan

### Phase 1: Planning and inventory

- audit live production schema markers relevant to the baseline
- decide the final filename for the duplicate `025` hardening file
- classify `999` as ops-only

### Phase 2: Introduce ledger mechanics

- add `schema_migrations` bootstrap
- add the manifest
- add `scripts/apply_migrations.sh`
- update `deploy_main.sh` to call it
- update `seed_check.sh` to use it

### Phase 3: Production baseline

- create the ledger table on production
- insert reviewed baseline rows
- explicitly record `019` state
- switch production deploys to the new path

Current committed operator path:

- `scripts/baseline_migration_ledger.sh` provides the reviewed one-time
  cutover helper for databases that predate `schema_migrations`
- it records baseline rows without replaying SQL
- it also records explicit `019_nullable_coords.sql` review state in
  `schema_migration_manual_status`
- it deliberately refuses to continue past `019` while that manual migration is
  still marked pending
- both `scripts/baseline_migration_ledger.sh` and
  `scripts/apply_migrations.sh` now accept compose overrides
  (`--compose-file` / `EDFINDER_DOCKER_COMPOSE_FILE`) so Windows/local
  operator flows can target `docker-compose.local.yml` without requiring host
  `psql`
- both helpers default to a one-hour statement timeout and a 30-second lock
  timeout. Reviewed finite overrides use `MIGRATION_STATEMENT_TIMEOUT` and
  `MIGRATION_LOCK_TIMEOUT`; setting either to zero additionally requires
  `EDFINDER_ALLOW_UNBOUNDED_MIGRATION_TIMEOUTS=yes`
- recorded local evidence now exists for the canonical pre-ledger `edfinder`
  database cutover:
  - `artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json`
  - `artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json`

### Phase 4: Cleanup follow-ups

- move `999_refresh_materialized_views.sql` out of the normal migration tree
- split `008_body_filter_aggregates.sql` into schema vs ops concerns
- add a migration replay/integration check in CI

## Definition of Done

- Production deploys no longer replay the full numbered SQL tree.
- Migration state is queryable from `schema_migrations`.
- `019` is explicit state, not a shell-script exception.
- Duplicate `025` numbering is gone.
- `999_refresh_materialized_views.sql` is no longer treated as a migration.
- CI/fresh-db setup uses the same canonical migration source of truth as
  production.
- Migration sessions cannot wait indefinitely unless an operator makes the
  explicit reviewed unbounded-timeout acknowledgement.

## Current Status

The manifest, checksum ledger, canonical applier, production baseline, manual
019 record, CI runtime rehearsal, and finite timeout policy are implemented and
production-proven. Future changes extend this path; they do not replay or
replace it ad hoc.
