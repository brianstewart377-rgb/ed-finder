# Audit Remediation Plan

This document converts the external adversarial audit into an executable
remediation checklist for ED-Finder. It does not replace `docs/ROADMAP.md`.
The roadmap remains the source of truth for priority and sequencing; this file
exists to make the agreed sequence concrete and reviewable.

## Current Intent

- Close the ratings integrity gap first.
- Fix the highest-risk foundation issues next: migrations, backups, and
  CI/build reproducibility.
- Run one bounded hygiene pass only after the foundation risks above are under
  control.
- Keep accounts/auth and broader product-lane expansion deferred until the
  foundation work is complete.

## Current Checkpoint (2026-07-10)

This is the current position of the external adversarial audit / Claude-report
response lane.

- Local engineering trust is materially improved:
  - repo-local Python 3.12 `.venv` is the canonical local runner;
  - Docker-backed disposable Postgres/Redis preflight is green;
  - the broad local pytest burn-down was most recently observed green at
    `1487 passed, 16 skipped` in the current workspace.
- The recently closed local failures were not new product-lane work; they were
  trust/honesty fixes in the local verification stack:
  - preflight now handles missing host `pg_isready` and does not over-probe;
  - map MV tests now stay fast because cache I/O is best-effort instead of a
    request-path dependency;
  - archetypes rerank responses now normalize JSONB-ish fields like
    `rationale` instead of surfacing stringified JSON into response models;
  - Stage 19 real-service readiness tests now skip explicitly when the
    historical approved baseline/checkpoint rows are absent from the empty
    disposable DB, instead of failing as if that were a product regression.
- The audit-response lane is therefore no longer blocked on local environment
  noise. The next unfinished audit items are the actual foundation items below:
  production ratings/body-contract closeout evidence, migration ledger,
  restore rehearsal, and CI/build reproducibility expansion.
- Production closeout evidence is now recorded from live production using
  production-safe targeted checks instead of the heavyweight full invariant
  sweep:
  - `flagged_but_zero_count = 3`
  - `unflagged_but_positive_count = 0`
  - `ring_status_drift = 0`
  - `dirty_rows` now oscillates in a small live retry band after rerates and
    no-body reconciles, rather than reflecting the original audit-scale
    backlog.
  - station-link `total_mismatches = 0`
- A committed lightweight closeout probe now exists at
  `scripts/checks/data_trust_health_snapshot.py`. The latest production snapshot
  reported:
  - `flagged_but_zero_count = 0`
  - `unflagged_but_positive_count = 0`
  - `ring_status_drift = 0`
  - station-link drift buckets at `0`
  - dirty tail split into `167` truthful no-body rows and `352` body-backed
    dirty rows, confirming the residue is classification/retry churn rather
    than structural contract drift
- Production migration state is also now clarified:
  - `schema_migrations` was already active through
    `035_nullable_population.sql`
  - production did not require a baseline cutover
  - `019_nullable_coords.sql` is now explicitly recorded in
    `schema_migration_manual_status`
- On the 120 GB production database, the full
  `scripts/checks/data_invariants.py` pass was too heavyweight for live
  closeout. The script now has a `--production-safe` mode for very large
  databases, and targeted SQL plus the committed repair/preview scripts remain
  the practical proof path when a bounded closeout is all that is needed.

## Fresh Chat Resume

If a new chat needs to resume the Claude-report lane, use this summary:

- Treat `docs/ROADMAP.md` as the authoritative priority order.
- Treat this document as the executable checklist for the accepted audit
  response.
- Current state:
  - ratings migration/cutover is complete;
  - production ratings is in healthy steady state, with remaining follow-up in
    contract/integrity hardening rather than a live mixed-generation backlog;
  - local preflight and disposable DB/Redis verification are green;
  - broad local pytest was most recently observed green at
    `1487 passed, 16 skipped` in the current workspace.
- The next audit-response work is still:
  1. finish production body-contract closeout evidence,
  2. land migration-ledger discipline,
  3. execute and record a real restore rehearsal,
  4. carry the now-honest local verification posture into CI/build paths.

## Sequence

1. Ratings rebaseline completion and trust closure
2. Migration-ledger and deploy-safety work
3. Backup/restore automation and restore readiness
4. CI/test/build reproducibility honesty
5. One bounded residue/hygiene pass
6. Re-evaluate accounts/auth only after 1-5 are complete

## Workstreams

### 1. Ratings Rebaseline Closure

Status: in progress

Goals:
- Finish the live production rerate to `rating_version = '3.4'`.
- Verify the end-state instead of inferring completion from code or cron
  behavior.
- Reconcile the post-rerate body-data contract drift that surfaced during
  closeout.
- Stop treating mixed-generation rows or impossible body-data eligibility states
  as an acceptable steady state.

Checklist:
- [x] Let the live full rerate complete cleanly.
- [x] Re-run production verification queries for `rating_version` distribution.
- [x] Verify rebuild-eligible rows are uniformly `rating_version = '3.4'` as
      far as production-safe verification permits.
- [x] Check `systems.rating_dirty` after the rebuild completes.
- [x] Restore the steady-state dirty-ratings cron only after verification.
- [x] Add a committed invariant check for rating-version uniformity and rating
      coverage.
- [x] Add a committed repair path for body-data contract drift
      (`scripts/repair_body_contract.py` plus `033_body_data_contract_hardening.sql`).
- [x] Deploy the body-data contract hardening and run the guarded reconciliation
      pass on production.
- [x] Re-run production-safe targeted evidence after reconciliation and record
      the post-rerate steady state. `data_invariants.py` now has a
      `--production-safe` mode for very large databases, and targeted SQL plus
      the committed repair/preview scripts remain the canonical closeout
      evidence for this lane.
- [ ] Ship a temporary UI trust cue only if any mixed population remains visible
      during the transition window.

Definition of done:
- Production no longer serves a mixed eligible population of `3.4` and `NULL`
  rating versions.
- A committed invariant check exists so this does not silently regress.
- The dirty-ratings maintenance path is restored in a verified steady state.
- `systems.has_body_data` / `systems.body_count` no longer drift from the actual
  `bodies` catalogue for the reconciled population.

Checkpoint note (2026-07-09):
- The live rerate and dirty-ratings stabilization are already behind us.
- The remaining unresolved portion of this workstream is evidence-backed
  production closeout for the body-data contract and related integrity checks,
  not a large active rerate backlog.

Checkpoint note (2026-07-10):
- Production body-contract closeout is now in a healthy operating band rather
  than a large drift bucket.
- The committed production-safe repair flow (`repair_body_contract.py` with
  `--skip-summary` and the optimized `missing-bodies-only` path) drained the
  dominant `has_body_data = TRUE` but zero-body population from `18434` down to
  `3`.
- `repair_body_ring_association_status.py` now provides the equivalent
  production-safe repair path for `body_rings.association_status` drift. On
  production it repaired `428` rows to canonical status and reduced
  `ring_status_drift` to `0`.
- Repeated `reconcile_no_body_ratings.py` passes and dirty-rating retries
  drained the stale no-body rating pockets and reduced the dirty queue to a
  small live tail. Final observed production shape:
  - `flagged_but_zero_count = 3`
  - `unflagged_but_positive_count = 0`
  - `ring_status_drift = 0`
  - `dirty_rows` / `dirty_truthful_no_bodies` continue to wobble in a bounded
    live-churn band after retries, rather than reopening the original backlog
- The new `data_trust_health_snapshot.py` probe makes that residue explicit:
  the live tail is a mixture of truthful no-body rows awaiting reconciliation
  and genuinely body-backed dirty rows awaiting the next rerate pass, not a
  reopened contract/integrity drift bucket.
- `repair_station_body_links.py --json` now reports `total_mismatches = 0` on
  production.
- The remaining residue is small enough to treat as steady-state retry/live
  churn, not the original audit-scale body-contract backlog.

### 2. Migration Safety

Status: in progress

Goals:
- Stop replaying the full `sql/` tree on every deploy.
- Make migration order explicit, auditable, and machine-enforced.

Reference:
- See `docs/operations/migration-ledger-implementation-plan.md` for the
  proposed ledger design, manifest approach, rollout phases, and production
  baseline strategy.

Checklist:
- [x] Introduce a migration ledger (`schema_migrations` or equivalent).
- [x] Record filename, checksum, and applied timestamp for committed
      migrations.
- [x] Remove the deploy-time replay-all-migrations behavior.
- [x] Resolve duplicate migration numbering in `sql/`.
- [x] Replace shell-script exceptions with explicit migration state.
- [x] Add a migration replay/integration test that proves migrations are
      idempotent or correctly ledgered.
- [x] Add a reviewed baseline helper for already-existing databases that
      predate `schema_migrations`.
- [x] Execute and record that baseline on the canonical local pre-ledger
      disposable database (`artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json`
      plus `artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json`).
- [x] Audit production pre-ledger state and record the correct manual
      bookkeeping instead of forcing a baseline cutover where one is not
      needed.

Definition of done:
- Deploys apply only unapplied migrations.
- Duplicate numbering and hidden skip rules are gone.
- Migration state is auditable from the database, not just shell comments.

Checkpoint note (2026-07-09):
- The repo now has a manifest-ledger migration applier, deploy/seed callers use
  it, and the duplicate `025` numbering is normalized in-tree.
- A real runtime rehearsal test now proves second-run skip behavior and manual
  migration handling, and Windows/local docs now include an explicit disposable
  DB reset path through the ledgered flow.
- `scripts/baseline_migration_ledger.sh` now provides the reviewed one-time
  cutover helper for pre-ledger databases, including explicit `019` review
  state recording.
- The canonical local pre-ledger `edfinder` database has now been cut over and
  recorded. The safe baseline stopped at `029_create_source_runs.sql`, then the
  normal applier advanced the DB through `035_nullable_population.sql`; the
  recorded evidence is:
  - `artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json`
  - `artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json`
- The remaining unresolved part of this workstream is executing that reviewed
  baseline on any other already-existing databases that were initialized before
  `schema_migrations` existed, including production if still pending.

Checkpoint note (2026-07-10):
- Production was audited directly and was already ledgered through
  `035_nullable_population.sql`.
- The missing historical detail was not a production baseline cutover; it was
  manual bookkeeping for `019_nullable_coords.sql`.
- `schema_migration_manual_status` now exists on production and records
  `019_nullable_coords.sql` as `applied`, with notes explaining that
  `systems.x/y/z` are already nullable and the normal ledger is active.
- For the production database, the migration-ledger closeout is therefore an
  audit/recording fix, not a baseline execution task.

### 3. Backup And Restore

Status: completed

Goals:
- Add a committed backup path and prove restore readiness.

Checklist:
- [x] Add scheduled Postgres backups through the maintained ops path.
- [x] Define retention policy and backup destination clearly.
- [x] Document restore steps in a committed runbook.
- [x] Execute and record at least one real restore rehearsal.

Definition of done:
- The repo contains backup automation, retention rules, and a tested restore
  runbook.
- Current implementation:
  - `apps/maintenance/scripts/run_backup.sh`
  - `apps/maintenance/scripts/crontab`
  - `scripts/restore_postgres_backup.sh`
  - `scripts/rehearse_postgres_restore.sh`
  - `docs/operations/postgres-backup-and-restore.md`

Checkpoint note (2026-07-09):
- A real local disposable restore rehearsal was executed and recorded via
  `scripts/rehearse_postgres_restore.sh` against `docker-compose.local.yml`.
- Receipt: `artifacts/restore-rehearsals/local-restore-receipt-2026-07-09.json`
- Observed result: `public_tables = 68`, `schema_migrations = 35`, restored DB
  dropped cleanly after verification.

### 4. CI, Tests, And Build Reproducibility

Status: in progress

Goals:
- Make green CI actually mean something.
- Make deployed frontend dependency resolution match what CI certified.

Checklist:
- [x] Use the committed frontend lockfile in CI and deploy/build paths.
- [x] Stop relying on fresh dependency resolution during production builds.
- [x] Expand CI so materially more of the existing test estate is gated.
- [x] Convert key false-safety tests into outcome-based checks where needed.
- [x] Add a committed/on-demand invariant runner for core data-trust checks and wire it into seeded CI verification paths.

Definition of done:
- CI covers a meaningfully broader test surface.
- Frontend dependency resolution is pinned and reproducible across CI and
  deployment.
- Core integrity checks run from committed code, not human memory.

Checkpoint note (2026-07-09):
- Local honesty is materially better than when this plan was first written.
- The repo-local `.venv` path, disposable DB preflight, and broad local pytest
  burn-down are green.
- CI now pins Node installs through the committed `frontend/yarn.lock`,
  packages a deployable frontend archive, and the release path can ship that
  exact certified artifact instead of rebuilding JS dependencies on the server.
- Disposable-DB runtime coverage now exercises the body-contract repair,
  no-body reconciliation, station-link repair, and invariant runner together
  so this lane is no longer relying only on source-text contract assertions.
- The highest-value remaining false-safety checks in this lane have now been
  converted into executable behavior coverage:
  - `tests/test_ci_build_reproducibility_contracts.py` now runs the frontend
    bundle packager against a real temporary `frontend/dist` and verifies the
    emitted archive plus checksum;
  - `tests/test_data_trust_runtime.py` now executes
    `data_trust_health_snapshot.py` against a seeded disposable database and
    asserts the reported drift buckets, rather than only scanning source text;
  - `tests/test_data_trust_health_snapshot.py` now verifies the actual CLI
    error path when no database URL is supplied.

### 5. Bounded Hygiene Pass

Status: in progress

Goals:
- Remove the most misleading residue without pretending cleanup equals safety.

Checklist:
- [x] Decide the fate of the archived frontend redesign prototype.
- [x] Remove or redirect hidden/ghost routes that no longer match the product.
- [x] Archive completed stage-specific one-shot scripts that should not be
      executable history.
- [x] Clean up stale version naming, platform-migration residue, and misleading
      labels.
- [x] Move or archive root-level planning residue that no longer belongs in the
      repo root.

Definition of done:
- The shipped tree no longer presents obviously conflicting product identities
  or misleading operator residue.

Current checkpoint:
- `frontend/src/main.tsx` no longer conditionally imports
  `_redesign/RedesignApp.jsx`; the archived prototype is no longer a live
  runtime entrypoint.
- The archived redesign prototype now lives under
  `docs/archive/frontend-redesign-prototype/` instead of inside `frontend/src/`.
- `#planner-preview` and `#chip-preview` no longer ship as live top-level
  routes; the old preview components remain historical reference material
  rather than production-reachable UI.
- Historical Stage 18J offline identity/summary wrappers now live under
  `scripts/operator/archive/stage18j/`, while the still-verified Stage 19
  safety wrappers remain in `scripts/operator/` because current tests and
  preflight still load them directly.
- Detached root residue has been moved under `docs/archive/root-residue/`, and
  the root-level `robocopy.log` has been removed. The journal-import design
  report remains at repo root intentionally because `docs/ROADMAP.md` still
  links to it as historical reference.
- `docs/development/repo-hygiene.md` now defines the standing repo-shape
  rules, and CI/local parity now run `tests/test_repo_hygiene_contract.py` to
  fail fast if new visible root clutter or ambiguous control-doc residue is
  introduced without an explicit decision.
- `tests/test_bounded_hygiene_pass.py` guards both expectations so this
  archived path does not quietly become a live entrypoint again, and the
  archived route/root/script residue does not silently reappear at the top
  level.

### 6. Accounts/Auth Re-Evaluation

Status: explicitly deferred

Entry criteria:
- Ratings rebaseline is complete and verified.
- Migration safety work is complete.
- Backup/restore posture is real and tested.
- CI/build reproducibility work is complete enough to trust further expansion.

Checklist:
- [ ] Re-open the accounts/auth decision only after the entry criteria above are
      satisfied.
- [ ] Prefer a local-first, self-hosted approach over introducing a new
      third-party dependency prematurely.

## Notes

- The audit was useful because it identified priority order, not because every
  residue finding is equally urgent.
- Ratings integrity, migration safety, backup readiness, and CI/build honesty
  remain the top four foundation concerns.
- Cleanup, product-surface consolidation, and accounts work should follow that
  order instead of competing with it.
