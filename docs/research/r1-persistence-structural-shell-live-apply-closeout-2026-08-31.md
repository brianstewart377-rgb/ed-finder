# R1 Persistence Structural Shell — Live Apply Closeout

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`
Status: **live structural apply completed and independently re-verified read-only**

## Authorised scope

The owner explicitly authorised the live structural apply after confirming that R1 storage is additive to the retained normalized V3 database rather than a replacement.

This authorisation covered only:

- creation of the empty `r1_meta`, `r1_cache`, and `r1_plan` structural shell;
- insertion of one checksummed migration-ledger row in `v3_meta.schema_migration`;
- post-apply verification.

It did **not** authorise or perform:

- a galaxy-wide capability build;
- an `r1_cap_*` physical generation;
- capability publication;
- Finder/API/frontend cutover;
- legacy Ratings deletion;
- mutation of retained canonical V3 generation relations;
- the deferred canonical `body_subtype` correction;
- any ordinary Finder/search persistence.

## Exact retained target

The structural shell was applied only to the retained normalized V3 target:

```text
operator environment: ed-new-operator
container: edfinder-v3-phase4c-full-20260827_r5-postgres
database: edfinder_v3_phase4c_full_20260827_r5
database user: edfinder_v3
observed database size: 566 GB
recovery state: false
```

The ordinary Hetzner application database named `edfinder` was explicitly rejected as the wrong target during preflight because it contains the legacy/public application schema and does not contain the normalized V3 authority relations.

## Migration identity

Source migration:

```text
sql/r1_v3/001_structural_shell.sql
```

Reviewed migration checkpoint:

```text
commit: 3978b071d7f98b320c146e58a20b66c7f2845f86
Git blob SHA: 26d1ef3d4ae343159ba62281102f2143ccff7fb8
SHA-256: 1a2d15c2db5cff7714a01a5d0c710a22326ed57d90d9a20e362495714ad97a40
```

The SHA-256 above is the 32-byte digest stored in `v3_meta.schema_migration`. GitHub Actions masks the byte value `22` in ordinary log rendering because it collides with a configured secret value; the post-apply verifier emitted the digest byte-separated so the stored digest could be reconstructed unambiguously.

## Catalog-bound authority confirmed before apply

Before any write, read-only catalog checks proved:

```text
v3_identity.account.account_id = UUID NOT NULL
v3_meta.canonical_generation.generation_id = UUID NOT NULL
```

The migration therefore uses UUID for every account/canonical-generation foreign key.

The normalized V3 migration ledger was also confirmed as:

```text
v3_meta.schema_migration
  migration_name   TEXT PRIMARY KEY
  migration_sha256 BYTEA NOT NULL CHECK octet_length(...) = 32
  applied_at       TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp()
```

## Pre-apply live state

Immediately before the successful write:

```text
R1 schemas present: none
v3_meta.schema_migration rows: 2
v3_meta.canonical_generation rows: 2
v3_identity.account rows: 1
```

The last read-only confirmation of this unchanged baseline was GitHub Actions run `33413678290`.

## Atomic apply

Successful live apply:

```text
workflow: R1 V3 Normalized Live Structural Apply
run ID: 33413750497
job ID: 99559366303
request commit: 58ed1667e5e0f6a7b9e4b7e1365fb3a84f626008
```

The operator:

1. verified the exact authorised request;
2. verified the migration Git blob SHA;
3. verified the uploaded migration SHA-256;
4. re-checked exact database/container/user identity;
5. re-checked V3 authority relations and UUID FK types;
6. re-checked the ledger shape;
7. required all three R1 schemas to be absent;
8. required the R1 migration name to be absent from the ledger;
9. opened one PostgreSQL transaction;
10. set a 5-second lock timeout and 60-second statement timeout;
11. locked `v3_meta.schema_migration` for the migration decision;
12. created the reviewed additive R1 structural shell;
13. inserted the exact source SHA-256 into `v3_meta.schema_migration`;
14. committed the DDL and ledger row together;
15. immediately verified the resulting live state.

The apply completed successfully and PostgreSQL committed the transaction.

Observed ledger apply timestamp:

```text
2026-08-31 16:22:56.202949+00
```

## Immediate post-commit verification

The successful apply job reported:

```text
pre:
  canonical_generation: 2
  account: 1
  schema_migration: 2

post:
  canonical_generation: 2
  account: 1
  schema_migration: 3

R1 schemas:
  r1_cache
  r1_meta
  r1_plan

R1 table/view relation count: 11
all R1 relations empty: true
capability generation built: false
Finder cutover performed: false
legacy or V3 data deleted: false
```

The only intentional non-empty data mutation was the single new migration-ledger row.

## Independent read-only post-apply verification

A separate later workflow re-opened the retained database in read-only transactions and verified the committed state independently of the apply process.

```text
workflow: R1 V3 Normalized Post-Apply Verify
run ID: 33413976970
job ID: 99560121080
request commit: b2708ebd55453f0757463b0669b719d67312ba07
result: passed
```

It confirmed:

```text
target: edfinder_v3_phase4c_full_20260827_r5 / edfinder_v3 / 566 GB / not in recovery
R1 schemas: r1_cache, r1_meta, r1_plan
R1 table/view relation count: 11
migration ledger total rows: 3
migration digest: exact reviewed SHA-256 above
canonical_generation rows: 2
account rows: 1
all R1 relations empty: true
r1_cap_* schemas: none
capability generation built: false
```

## Earlier non-writing stops

The operational record deliberately retains the failed/stopped attempts rather than hiding them.

### Wrong target rejected

Run `33412449896` probed the ordinary Hetzner `edfinder` application database read-only. It observed a roughly 770 GB database with none of the normalized V3 authority relations and stopped before any write.

This established that the legacy/public application DB is not the normalized V3 target for R1 persistence.

### First normalized preflight checkout issue

An early normalized-V3 preflight failed before SSH/database work because a shallow Git checkout did not contain the older pinned migration commit. The check was changed to verify the exact current file's Git blob SHA instead. No database write occurred.

### First live-apply workflow definition issue

Run `33412991114` had no jobs because GitHub rejected the initial workflow definition. There was no SSH or database access.

### First executable apply attempt transferred no SQL to psql

Run `33413447473` reached the correct normalized target, but `docker exec` was missing stdin attachment (`-i`). `psql` therefore received no transaction and returned without executing DDL. Crucially, the mandatory post-check detected that all R1 schemas were still absent and failed the job.

Read-only run `33413678290` then independently confirmed:

```text
existing R1 schemas: none
migration ledger row count: 2
```

before the transport fix was allowed to retry.

## Live structures now present

Exactly these R1 table/view relations are present:

```text
r1_cache.system_capability_current          VIEW

r1_meta.mechanics_revision                 TABLE
r1_meta.model_revision                     TABLE
r1_meta.programme_revision                 TABLE
r1_meta.capability_generation              TABLE
r1_meta.current_capability_generation      TABLE

r1_plan.saved_plan                         TABLE
r1_plan.plan_revision                      TABLE
r1_plan.plan_node                          TABLE
r1_plan.plan_allocation                    TABLE
r1_plan.plan_assessment                    TABLE
```

The current capability view is intentionally typed but zero-row. No physical capability generation exists.

## Safety conclusion

The additive R1 persistence foundation now exists live beside normalized V3.

The retained V3 canonical-generation and account row counts were unchanged across the apply, no existing V3 relation was replaced or rewritten, no legacy/public schema was touched, and no Finder behavior changed.

The next storage-scale action is **not automatic**. The first capability-generation build remains a separate high-risk operation requiring its own review/authorisation and real-system validation before any publication into Finder.
