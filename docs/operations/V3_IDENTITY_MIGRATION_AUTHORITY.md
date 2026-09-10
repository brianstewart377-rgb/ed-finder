# V3 identity migration authority and repeatability proof

Status: implementation and local PostgreSQL 18 proof

Decision date: 2026-08-26

## Owner decision and V2 disposition

Frontier OAuth in V2 was never deployed or used. It was never production
state, and there are no V2 OAuth accounts, sessions, provider links, login
states, roles, or audit rows to migrate.

- PR #490 V2 OAuth implementation: **RETIRE / SUPERSEDED BY V3**.
- `sql/048_frontier_accounts.sql`: **RETIRE / NOT PART OF V3**.
- PR/branch history is retained as reference evidence until the verified V3
  port is safely merged. This task does not delete Git history.
- No V2 OAuth data migration, schema compatibility, table conversion, or
  V2-shaped-database test is required.
- The live old server is not accessed or modified.

## Separate V3 authority

The only V3 migration manifest is `sql/v3/migration-manifest.txt`. It pins:

1. `001_v3_baseline.sql` — frozen SHA-256
   `ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e`.
2. `002_v3_accounts_identity.sql` — the first post-baseline migration.

The frozen baseline establishes `v3_meta.schema_migration`. The explicit runner
`scripts/v3/apply_migrations.py` verifies manifest checksums, requires
PostgreSQL 18, locks the V3 lineage, records each applied file and its SHA-256,
and supports only two named modes:

- `bootstrap-empty`: refuses a database containing any user relation or
  non-relation user residue (custom schema, routine, type, or extension) and
  applies the complete V3 chain.
- `upgrade`: requires the frozen baseline and checksum in the V3 ledger and
  applies only the contiguous pending V3 suffix.

The runner never reads `sql/migration-manifest.txt`. V2 migration history is
not a predecessor, compatibility source, or fallback.

## V3 identity/OAuth delta

The frozen baseline already defines account UUID authority, external
identities, Commanders and account access, sessions, roles/assignments,
security audit, private ownership, and legacy sync-key claim isolation.
Migration 002 extends that fresh schema with:

- stable application-role seeds and a single-active-owner constraint;
- role grant provenance;
- normalized/nonblank provider identity constraints and an active-identity
  index;
- session revocation reason consistency;
- short-lived digest-keyed PKCE login/link state;
- security event-code indexing.

The API uses schema-qualified singular V3 relations. It does not create or
query the V2 prototype's `accounts`, `external_identities`, `account_sessions`,
or other public-schema OAuth tables. Provider tokens are discarded after
identity verification.

## Two-database proof

Two independent local, disposable PostgreSQL 18 clusters are created with
unique container names, ports, and data directories. Each starts with zero user
relations and runs:

```text
empty PostgreSQL 18
  -> 001_v3_baseline.sql
  -> v3_meta.schema_migration ledger entry for 001
  -> 002_v3_accounts_identity.sql
  -> ledger entry for 002
  -> stable structural inventory
```

The inventory includes all V3 schemas, relations, columns, constraints,
indexes, functions, role seeds, and checksum-ledger rows while excluding
database names, OIDs, timestamps, sizes, and paths. The two rendered JSON files
must be byte-identical. Receipts and inventories are stored under
`artifacts/v3/identity-migration/`.

## Proof result

The result section is completed only from the local proof artifacts:

- PostgreSQL 18 database A: **PASS** (`server_version_num=180006`, zero user
  relations and zero non-relation user objects before bootstrap)
- PostgreSQL 18 database B: **PASS** (`server_version_num=180006`, zero user
  relations and zero non-relation user objects before bootstrap)
- Frozen baseline SHA-256: **PASS**
- First post-baseline migration: **PASS**
- V3 manifest/ledger separation: **PASS**
- Structural inventory SHA-256 A:
  `96bc6134d1e275bbb17ae5c0ab8316a7af95c76a0b90bc2a0030a6593c9a431d`
- Structural inventory SHA-256 B:
  `96bc6134d1e275bbb17ae5c0ab8316a7af95c76a0b90bc2a0030a6593c9a431d`
- Inventories byte-identical: **PASS** (398,888 bytes each, including the
  non-internal V3 trigger inventory)
- Required relations: **PASS** (`account`, `external_identity`, `commander`,
  `account_commander_access`, `session`, `role`, `account_role`,
  `oauth_login_state`, and `security_audit_event`)
- V3 OAuth regression: **PASS** (32 Python contract/PostgreSQL tests and 41
  focused frontend tests; Ruff and TypeScript typecheck passed)

No proof command targets the live old server or any Phase 4C container, volume,
database, network, port, or artifact directory.
