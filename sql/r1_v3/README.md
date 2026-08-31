# R1 normalized-V3 migration package

This directory is the additive migration lane for R1 persistence structures that live alongside the normalized V3 warehouse schemas.

It is deliberately separate from `sql/migration-manifest.txt`, which is the established ledger for the legacy/public application schema.

## Safety boundary

This package MUST NOT be invoked by the ordinary application deploy path unless a later reviewed cutover explicitly wires it in.

The initial migration:

- creates `r1_meta`, `r1_cache`, and `r1_plan` only;
- references existing normalized V3 authority by foreign key where stable authority exists;
- does not mutate `v3_meta`, `v3_identity`, `v3_source`, `v3_vocab`, or any immutable `v3_gen_*` generation;
- does not create the future canonical `body_subtype` correction in the retained generation;
- does not build or publish a galaxy capability generation;
- does not insert, update, delete, truncate, copy, or drop gameplay/canonical rows;
- does not alter Finder, legacy ratings, or production ranking behavior.

## Ledger

`migration-manifest.txt` is the source order for this package.

A later live normalized-V3 applier must:

1. run only after explicit operator authorisation;
2. use `ON_ERROR_STOP`/transactional failure semantics;
3. verify the migration SHA-256 before application;
4. record the applied migration in the normalized warehouse migration authority (`v3_meta.schema_migration`) using its established contract;
5. refuse checksum drift;
6. never silently fall back to the legacy/public migration ledger.

The live applier itself is intentionally not introduced by the first structural slice.

## Current logical surface

`r1_cache.system_capability_current` is initially a typed zero-row view. It exists so API/schema work can bind to a stable factual capability contract without publishing any galaxy data.

A future, separately authorised capability-build stage will create an immutable physical `r1_cap_<generation>.system_capability` relation, validate it, and atomically repoint the logical current view.

## Catalog-bound foreign-key types

The migration is bound to metadata-only catalog observations from the normalized V3 database:

- `v3_identity.account.account_id`: UUID;
- `v3_meta.canonical_generation.generation_id`: UUID.

These are not inferred placeholder types.
