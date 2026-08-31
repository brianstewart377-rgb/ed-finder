# R1 Persistence Structural Shell — Completion

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`
Status: implementation authored and disposable-DB verified; **not applied to the retained/live normalized V3 database**

## Scope completed

Implemented the first additive R1 persistence slice accepted in Persistence Review 2:

- isolated normalized-V3/R1 migration package under `sql/r1_v3/`;
- empty `r1_meta`, `r1_cache`, and `r1_plan` structural shell;
- immutable revision registries;
- capability-generation metadata and empty logical current capability view;
- private saved-plan header + immutable plan revisions;
- typed nodes and allocations;
- immutable saved-plan/Build-Pack/audit assessment snapshots;
- static schema contract tests;
- disposable PostgreSQL 18 relational tests.

No capability generation was built or published. No Finder or Ratings production path was changed.

## Safety / authority gates

The repository's strict state resolver was executed after explicitly fetching `origin/main`.

Result:

- `origin_main_contains_authority: True`
- `matched_invalid_state: null`
- `safe_for_operational_work: True`
- `safe_for_docs_only_work: True`
- `failure_category: none`

The earlier failed resolver attempt was caused only by a shallow checkout that did not expose `origin/main`; it performed no database work.

## Catalog-bound type correction

A metadata-only PostgreSQL catalog query established the actual normalized V3 FK types:

- `v3_identity.account.account_id` = UUID;
- `v3_meta.canonical_generation.generation_id` = UUID;
- `v3_vocab.body_type.body_type_id` = SMALLINT.

The migration uses UUID for every account/canonical-generation FK. Review-2 BIGINT canonical-generation placeholders are superseded by `r1-persistence-schema-review-2-type-correction-2026-08-31.md`.

## Migration-lane boundary

The repository's existing top-level `sql/migration-manifest.txt` was not modified.

The R1 structural shell lives in its own `sql/r1_v3/migration-manifest.txt`. It is therefore not reachable through the ordinary legacy/public application migration/deploy path.

A future live normalized-V3 applier must be separately reviewed and authorised and must record checksummed application state using the normalized warehouse migration authority (`v3_meta.schema_migration`).

## Changed files for the implementation slice

Base: `c9e7458bbed32c98cc16fde3764dedb0e51b9aca`
Tested head: `75f7874fdfa2ae3afb931331a0c087c77dd942e8`

Exactly seven files changed in the implementation/test slice:

1. `.github/r1-v3-schema-test-requests/2026-08-31.json`
2. `.github/workflows/r1-v3-schema-disposable-test.yml`
3. `docs/research/r1-persistence-schema-review-2-type-correction-2026-08-31.md`
4. `sql/r1_v3/001_structural_shell.sql`
5. `sql/r1_v3/README.md`
6. `sql/r1_v3/migration-manifest.txt`
7. `tests/test_r1_v3_schema_contract.py`

No production API, Finder, frontend, legacy ratings, legacy migration manifest, normalized V3 source schema, or retained canonical-generation relation was modified.

## Static contract verification

GitHub Actions workflow: `R1 V3 Structural Schema Disposable Test`
Run: `33410903879`

Focused static result:

```text
10 passed in 0.05s
```

The tests verify among other things:

- migration package is isolated from the legacy/public manifest;
- migration is additive/DDL-only;
- no V3 relation is created or altered;
- UUID catalog FK bindings are used;
- exact first-slice table set;
- capability current view is typed, empty and context-free;
- no Plan Fit/pair resilience/programme outcome is stored in the capability surface;
- immutable plan-revision binding exists;
- exclusive-resource DB uniqueness exists;
- numeric Plan Fit cannot be stored for unsupported/not-assessable states;
- no universal/legacy score table or column is introduced.

## Disposable PostgreSQL 18 verification

The exact `sql/r1_v3/001_structural_shell.sql` migration was applied to a fresh `postgres:18` GitHub Actions service container with stub normalized-V3 authority relations matching the catalog types.

Result:

```text
disposable_r1_schema_invariants: passed
```

Verified behavior included:

- zero-row `r1_cache.system_capability_current` after migration;
- UUID canonical-generation and account FK columns;
- deferred saved-plan/current-revision linkage works;
- valid immutable plan/node/allocation insert works;
- attempted exclusive double-credit is rejected by `uq_r1_plan_allocation_exclusive_resource`;
- attempted `not_supported` assessment with numeric Plan Fit is rejected by `chk_r1_plan_assessment_plan_fit_state`;
- valid Supported assessment persists;
- deleting the private saved plan cascades all plan revisions, nodes, allocations and assessments successfully.

## Explicit non-actions

This slice did **not**:

- connect to the retained 566 GiB database for writes;
- apply the R1 migration live;
- create or alter any `v3_*` schema/table;
- create the future `body_subtype` correction in the retained generation;
- build 198M capability rows;
- publish a capability generation;
- create a universal rating/score;
- write ordinary Finder searches/candidates;
- change live Finder ordering;
- delete, replace, truncate or rename any existing database structure.

## Next gate

The structural shell is ready for a separate **live-application review** if/when desired. That review should cover only the tiny additive DDL apply/ledger/rollback operation.

The first galaxy-wide capability build remains a later, separate review and must not be bundled with structural live application.
