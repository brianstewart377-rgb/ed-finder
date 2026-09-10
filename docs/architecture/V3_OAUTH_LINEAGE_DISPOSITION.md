# V3 OAuth lineage disposition

Status: owner decision recorded 2026-08-26.

## V2 disposition

Frontier OAuth in V2 was never deployed and never became production state.
PR #490 (`feat(auth): Frontier OAuth owner access`) is retained as prototype
and behavioral reference evidence, but its implementation is superseded by
the verified V3 port. Its branch and PR history remain intact until the V3
port is safely merged.

`sql/048_frontier_accounts.sql` is retired and is not part of the V2/main or
V3 migration chain. No V2 OAuth data migration, schema compatibility layer,
or V2-to-V3 OAuth table conversion exists or is required.

## V3 authority

V3 uses the independent, checksum-locked manifest
`sql/v3/migration-manifest.txt`, migration directory
`sql/v3/migrations`, and ledger `v3_meta.schema_migration`. The V2 manifest
and `schema_migrations` ledger are not consulted by the V3 runner.

The chain is:

1. `001_v3_baseline.sql`, frozen at SHA-256
   `ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e`.
2. `002_v3_accounts_identity.sql`, the first post-baseline V3 migration.

The baseline owns the fresh `v3_identity` account, external-identity,
Commander, role, session, and audit model. Migration 002 extends that model
with OAuth state and runtime constraints. It does not read or reproduce any
V2 OAuth table. V3 OAuth therefore begins with a fresh V3 identity schema and
has no legacy OAuth data migration.

## Runner semantics

`scripts/v3/apply_migrations.py` requires an explicit mode:

- `bootstrap-empty` refuses a database containing any user relation, applies
  the frozen baseline and each ordered migration atomically, and records the
  exact file checksums in the V3 ledger.
- `upgrade` requires the checksum-verified baseline ledger entry and applies
  only the remaining contiguous V3 manifest suffix.

Unknown ledger entries, checksum drift, gaps, a non-PostgreSQL-18 server, or a
changed baseline fail closed. Neither mode performs database lifecycle work.

No old-server configuration or Phase 4C resource is an authority for this
decision, and neither is to be mutated by this migration task.
