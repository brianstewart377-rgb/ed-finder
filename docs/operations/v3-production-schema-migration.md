# V3 production schema migration

Authority for changing the **schema** of the retained production PostgreSQL 18
database. The application promotion path is deliberately forbidden from doing
this, and this operation is deliberately forbidden from changing services.

Executable: [`scripts/operator/v3_production_migrate.py`](../../scripts/operator/v3_production_migrate.py)

## Scope

This operation applies committed V3 lineage migrations and nothing else. It does
not build derived data — that belongs to the derived-generation lifecycle in
`003`, which exists so that a derived rebuild never requires DDL.

Execution is available only through the manual
`V3 production schema migration` workflow on exact current `main`. Both `plan`
and `apply` use the protected `v3-production` environment and pinned SSH trust;
`apply` remains a separate deliberate dispatch after the plan receipt is reviewed.

## What it refuses to do

Every one of these is a stop, not a warning:

- an invalid or unsafe target authority, or a host identity that is not the exact
  production host, or a Docker context that is not the local rootful socket;
- a target schema identity that does not match the committed V3 lineage and the
  exact checksum pinned in target authority;
- an installed identity outside the reviewed `from`/`to` transition, or a live
  ledger outside the corresponding exact prefix range;
- an accepted active application release that is not explicitly compatible
  with every schema identity reachable during the transition;
- a live ledger that is not an **exact prefix** of the committed lineage — same
  order, same names, same hashes. A ledger ahead of the lineage, or divergent in
  any row, stops the operation rather than guessing;
- a pending migration that does not manage its own transaction. Without
  `BEGIN; ... COMMIT;` a migration that failed halfway could leave half its
  statements committed, and the operation would have no honest way to continue;
- a migration whose bytes changed after the plan was derived;
- a second operation while the production deployment lock is held, so a schema
  change can never overlap a promotion.

## Purge-state entry fence

`apply` checks the shared read-only purge ledger and host lease before taking
its deployment lock, then rechecks before DDL. Missing ledger refuses except
when the live prefix exactly matches the authenticated plan's recorded prefix
and its complete pending suffix ends in 016; an already-applied 016 never gets
this exception. The authenticated plan is copied into the operation bundle,
so apply never substitutes its fresh observation for the reviewed prefix.
See [purge fences and wrapper install order](v3-governed-derived-purge.md).

## Operations

```bash
gh workflow run v3-production-schema-migration.yml -f operation=plan \
  -f target_confirmation=ed-finder-prod/nb79a3d.mevnode.com
gh workflow run v3-production-schema-migration.yml -f operation=apply \
  -f target_confirmation=ed-finder-prod/nb79a3d.mevnode.com \
  -f plan_run_id=<successful-reviewed-plan-run-id>
```

- **`plan`** validates the exact host and Docker context, reads the live ledger,
  binds the installed and target identities, verifies the accepted rollback
  release against every transition prefix, and prints `applied_before` and
  `pending`. It does not change the database, services, or installed identity.
- **`apply`** takes the production deployment lock and applies each pending
  migration in committed-lineage order. Each migration and its ledger row commit
  in the **same PostgreSQL transaction**, removing the crash window between DDL
  and ledger advancement. The live ledger must then equal the committed lineage
  exactly before the target schema identity is atomically installed. Apply first
  downloads a prior plan artifact and verifies GitHub-owned run provenance, exact
  workflow and source SHA, successful completion, receipt identity, and the exact
  applied/pending split against the current committed lineage. A plan run ID from
  any other workflow, commit, repository, target, or failed run is rejected.

Every workflow run preserves its emitted receipt as an Actions artifact. An
`apply` also writes the receipt into the authority's `receipt_directory` with a
sidecar checksum. Receipts record the desired ledger digest, what was applied
before, what was pending, what was applied now, the pinned schema identity hash,
and explicit `database_writes_performed` / `migrations_performed` flags.

## How a migration lands

1. Commit the migration under `sql/v3/migrations/` (or `sql/r1_v3/` for an R1
   shell) with `BEGIN; ... COMMIT;`.
2. Add its ledger name, hash and repository path to
   `sql/v3/migration-manifest.txt`.
3. Add or update `schema_transition` and the accepted-release compatibility
   attestation in `deploy/v3-production/target-authority.json`. Every prefix from
   the installed schema to the target must be listed as compatible.
4. Regenerate the target identity with `scripts/operator/v3_schema_identity.py`
   and pin its checksum as `schema_identity_sha256`. The protected workflow
   independently regenerates it and refuses any mismatch.
5. Merge the change through exact-head acceptance. Dispatch `plan`, review its
   retained receipt, then separately dispatch `apply` with that plan run ID.

## Applying 023: Search prefix autocomplete

Migration `023_v3_system_search_name_prefix_index.sql` adds
`v3_derived.system_search_name_prefix` on
`(derived_generation_id, lower(name) text_pattern_ops)` and preserves
`system_search_name_lower`. The installed prefix is through `022` (apply run
41180459540, 2026-10-31). The new exact-head governed **plan must list pending
exactly `[023]`**; stop and review any other pending set before a separate apply.
This registration does not claim that 023 has been applied. Apply 023 before
promoting the autocomplete application fix.

The runner inserts the ledger row before the migration's terminal `COMMIT`, so
the ordinary, non-concurrent `CREATE INDEX` and ledger advance atomically. Its
SHARE table lock permits ordinary reads throughout the build but blocks derived
generation builds/purges until commit; schedule outside those operations. It
does not lock or change canonical `systems`. `lock_timeout = '5s'` bounds lock
acquisition and `statement_timeout = '4h'` bounds the build. The runner grants
**only 023** a 245-minute child timeout, with a 270-minute apply workflow
envelope (plan remains 30 minutes), allowing SQL to stop before either wrapper.
Timeout rolls back the transaction; review the stopped receipt before retrying.

For ~198.5 million published rows, budget **1–3 hours**, **12–20 GiB** for the
new index and **60 GiB additional free disk** for the index plus temporary sort
and WAL headroom. These are planning estimates, not a benchmark or a measured
current capacity claim: the retained
[2026-10-10 inventory](evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json)
reported the same-key default-opclass index at 15,531,458,560 bytes (14.5 GiB)
for approximately 198.5 million Search rows. The new index includes **all rows
from every retained generation**, so scale the disk estimate by total Search
rows / 198.5 million; build duration also depends on row count, I/O and sort
memory. Review current free space, retained generations and WAL/archive health
with the plan; unexpected capacity or an estimate beyond the four-hour bound
requires a separately reviewed adjustment. This coding change performs no
production operation.

## Governed delivery

The workflow sends only the bounded operator, verifier, authority and migration
files required for the operation over pinned SSH trust. It does not send a
repository credential or registry token, and it cannot stop or recreate
application services. Application promotion uses the same lock, so migration
and cutover cannot overlap.
