# V3 production schema migration

Authority for changing the **schema** of the retained production PostgreSQL 18
database. The application promotion path is deliberately forbidden from doing
this, and this operation is deliberately forbidden from changing services.

Executable: [`scripts/operator/v3_production_migrate.py`](../../scripts/operator/v3_production_migrate.py)

## Scope

This operation applies committed V3 lineage migrations and nothing else. It does
not build derived data — that belongs to the derived-generation lifecycle in
`003`, which exists so that a derived rebuild never requires DDL.

Creating or reviewing this authority does not authorize running it. No command in
this runbook has been executed against production.

## What it refuses to do

Every one of these is a stop, not a warning:

- an invalid or unsafe target authority, or a host identity that is not the exact
  production host, or a Docker context that is not the local rootful socket;
- a pinned `schema_identity_sha256` that does not match the host schema identity
  file's owner, mode and checksum;
- a live ledger that is not an **exact prefix** of the committed lineage — same
  order, same names, same hashes. A ledger ahead of the lineage, or divergent in
  any row, stops the operation rather than guessing;
- a pending migration that does not manage its own transaction. Without
  `BEGIN; ... COMMIT;` a migration that failed halfway could leave half its
  statements committed, and the operation would have no honest way to continue;
- a migration whose bytes changed after the plan was derived;
- a second operation while the production deployment lock is held, so a schema
  change can never overlap a promotion.

## Operations

```bash
python3.14 scripts/operator/v3_production_migrate.py --operation authority-gate
python3.14 scripts/operator/v3_production_migrate.py --operation plan
python3.14 scripts/operator/v3_production_migrate.py --operation apply
```

- **`authority-gate`** validates the authority, host, Docker context and pinned
  schema identity, then reports how many migrations are pending. No writes.
- **`plan`** additionally reads the live ledger and prints the receipt it would
  write, including `applied_before` and `pending`. No writes.
- **`apply`** takes the production deployment lock and applies each pending
  migration in committed-lineage order. Each migration runs through `psql` with
  `ON_ERROR_STOP=1`, and its ledger row is inserted **only after that migration
  commits**. The live ledger must then equal the committed lineage exactly.

Every run writes a receipt into the authority's `receipt_directory`, with a
sidecar checksum, recording the desired ledger digest, what was applied before,
what was pending, what was applied now, the pinned schema identity hash, and
explicit `database_writes_performed` / `migrations_performed` flags.

## How a migration lands

1. Commit the migration under `sql/v3/migrations/` (or `sql/r1_v3/` for an R1
   shell) with `BEGIN; ... COMMIT;`.
2. Add its ledger name, hash and repository path to
   `sql/v3/migration-manifest.txt`.
3. Regenerate the reviewed schema identity with
   `scripts/operator/v3_schema_identity.py` and re-pin
   `schema_identity_sha256` in `deploy/v3-production/target-authority.json`.
   The identity describes the state the migration is about to make true.
4. Install the regenerated identity file on the host at the pinned owner and mode.
5. Run `plan`, review it, then run `apply`.

## Not yet built: governed delivery

The promotion path reaches the host through a manual-only workflow that ships a
sealed, source-free bundle over pinned SSH trust. This operation has no equivalent
yet: it is currently run by invoking the script on the host. Until a governed
delivery exists, treat this as a reviewed operator action rather than a governed
one, and say so in the receipt's review note.
