# V3 identity migration local proof receipt

Proof date: 2026-08-26

Scope: two independent local disposable `postgres:18-bookworm` clusters. No
remote server, old-server database, or Phase 4C container/volume/network was
accessed.

## Migration authority

- Frozen baseline: `001_v3_baseline.sql`
- Frozen baseline SHA-256:
  `ee08c17eb3f87f614468db5a038d2f23273ce2b72906226c9aa1f669e724cd2e`
- First post-baseline migration: `002_v3_accounts_identity.sql`
- Migration SHA-256:
  `e7a2f404b7d8194d74ba4e807ae450c7520a1c8a186ca77e41377307e7b12b07`
- V3 manifest SHA-256:
  `3259dc3415186515716c8c5a728df9ef30e767b1f62ba1d2a0f7349c132a7df9`
- PostgreSQL version for both runs: `180006` (PostgreSQL 18.6)
- User relations before each bootstrap: `0`
- Non-relation user objects before each bootstrap: `0`
- User relations after each bootstrap: `56`
- V2 lineage used: `false`

Run receipts:

- `run-a-receipt.json`
- `run-b-receipt.json`
- `run-b-upgrade-noop-receipt.json` (explicit `upgrade` mode applied nothing
  after verifying the complete checksum ledger)

## Structural repeatability

- `run-a-inventory.json`: 398,888 bytes
- `run-b-inventory.json`: 398,888 bytes
- SHA-256 for both:
  `96bc6134d1e275bbb17ae5c0ab8316a7af95c76a0b90bc2a0030a6593c9a431d`
- Byte comparison: **IDENTICAL**
- Inventory counts: 6 V3 schemas, 56 relations, 403 columns, 591
  constraints, 118 indexes, 5 functions, and 1 non-internal trigger.
- Public-schema user relations: `0`
- Ledger: `001_v3_baseline.sql`, then `002_v3_accounts_identity.sql`
- Role seeds: `OWNER`, `ADMIN`, `MEMBER`, `SERVICE`

The stable inventories include the required V3 account, external identity,
Commander/access, session, role/assignment, OAuth login-state, and security
audit structures with their FKs, indexes, and constraints.

## Regression

- V3 Python migration/OAuth/PostgreSQL suite: **32 passed**
- Focused frontend auth/application suite: **41 passed**
- Targeted Ruff: **passed**
- Frontend TypeScript typecheck: **passed**

No V2-shaped-database compatibility test was run or required. PR #490 and
`sql/048_frontier_accounts.sql` remain superseded reference history and are not
members of the V3 manifest or V2 main manifest.
