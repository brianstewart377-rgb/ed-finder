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
- [ ] Deploy the body-data contract hardening and run the guarded reconciliation
      pass on production.
- [ ] Re-run invariants after reconciliation and record the post-rerate steady
      state.
- [ ] Ship a temporary UI trust cue only if any mixed population remains visible
      during the transition window.

Definition of done:
- Production no longer serves a mixed eligible population of `3.4` and `NULL`
  rating versions.
- A committed invariant check exists so this does not silently regress.
- The dirty-ratings maintenance path is restored in a verified steady state.
- `systems.has_body_data` / `systems.body_count` no longer drift from the actual
  `bodies` catalogue for the reconciled population.

### 2. Migration Safety

Status: queued

Goals:
- Stop replaying the full `sql/` tree on every deploy.
- Make migration order explicit, auditable, and machine-enforced.

Reference:
- See `docs/operations/migration-ledger-implementation-plan.md` for the
  proposed ledger design, manifest approach, rollout phases, and production
  baseline strategy.

Checklist:
- [ ] Introduce a migration ledger (`schema_migrations` or equivalent).
- [ ] Record filename, checksum, and applied timestamp for committed
      migrations.
- [ ] Remove the deploy-time replay-all-migrations behavior.
- [ ] Resolve duplicate migration numbering in `sql/`.
- [ ] Replace shell-script exceptions with explicit migration state.
- [ ] Add a migration replay/integration test that proves migrations are
      idempotent or correctly ledgered.

Definition of done:
- Deploys apply only unapplied migrations.
- Duplicate numbering and hidden skip rules are gone.
- Migration state is auditable from the database, not just shell comments.

### 3. Backup And Restore

Status: in progress

Goals:
- Add a committed backup path and prove restore readiness.

Checklist:
- [x] Add scheduled Postgres backups through the maintained ops path.
- [x] Define retention policy and backup destination clearly.
- [x] Document restore steps in a committed runbook.
- [ ] Execute and record at least one real restore rehearsal.

Definition of done:
- The repo contains backup automation, retention rules, and a tested restore
  runbook.
- Current implementation:
  - `apps/maintenance/scripts/run_backup.sh`
  - `apps/maintenance/scripts/crontab`
  - `scripts/restore_postgres_backup.sh`
  - `docs/operations/postgres-backup-and-restore.md`

### 4. CI, Tests, And Build Reproducibility

Status: in progress

Goals:
- Make green CI actually mean something.
- Make deployed frontend dependency resolution match what CI certified.

Checklist:
- [ ] Use the committed frontend lockfile in CI and deploy/build paths.
- [ ] Stop relying on fresh dependency resolution during production builds.
- [ ] Expand CI so materially more of the existing test estate is gated.
- [ ] Convert key false-safety tests into outcome-based checks where needed.
- [x] Add a committed/on-demand invariant runner for core data-trust checks and wire it into seeded CI verification paths.

Definition of done:
- CI covers a meaningfully broader test surface.
- Frontend dependency resolution is pinned and reproducible across CI and
  deployment.
- Core integrity checks run from committed code, not human memory.

### 5. Bounded Hygiene Pass

Status: deferred until 1-4 are complete or safely underway

Goals:
- Remove the most misleading residue without pretending cleanup equals safety.

Checklist:
- [ ] Decide the fate of `frontend/src/_redesign/`.
- [ ] Remove or redirect hidden/ghost routes that no longer match the product.
- [ ] Archive completed stage-specific one-shot scripts that should not be
      executable history.
- [ ] Clean up stale version naming, platform-migration residue, and misleading
      labels.
- [ ] Move or archive root-level planning residue that no longer belongs in the
      repo root.

Definition of done:
- The shipped tree no longer presents obviously conflicting product identities
  or misleading operator residue.

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
