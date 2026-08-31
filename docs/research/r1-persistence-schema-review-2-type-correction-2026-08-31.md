# R1 Persistence Review 2 — Catalog Type Correction

Date: 2026-08-31
Status: implementation-binding correction to accepted Review 2
Branch: `chatgpt-ed-new-ops-requests`

## Purpose

Bind the accepted R1 persistence contract to the actual normalized V3 PostgreSQL catalog types discovered before authoring DDL.

This is a type correction only. It does not change the persistence architecture or authorise live database application.

## Catalog evidence

A metadata-only catalog query against the retained normalized V3 PostgreSQL database established:

- `v3_identity.account.account_id` = `UUID NOT NULL`;
- `v3_meta.canonical_generation.generation_id` = `UUID NOT NULL`;
- `v3_vocab.body_type.body_type_id` = `SMALLINT NOT NULL`.

The strict repository project-state resolver was then rerun with `origin/main` available and reported `safe_for_operational_work: True` with no matched invalid state.

## Binding correction

Every R1 foreign key that references `v3_meta.canonical_generation(generation_id)` MUST therefore use `UUID`, including:

- `r1_meta.capability_generation.canonical_generation_id`;
- `r1_plan.plan_revision.created_from_canonical_generation_id`;
- `r1_plan.plan_assessment.canonical_generation_id`.

`r1_plan.saved_plan.owner_account_id` MUST use `UUID` and reference `v3_identity.account(account_id)`.

The future `v3_vocab.body_subtype.body_type_id` MUST use `SMALLINT` to match `v3_vocab.body_type(body_type_id)`.

Any earlier Review-2 prose that showed `BIGINT` for a canonical-generation reference was a placeholder and is superseded by this catalog-bound correction.

## Migration-lane boundary

The repository's existing `sql/migration-manifest.txt` is the established migration ledger for the legacy/public application schema. The normalized V3 warehouse uses versioned schemas and exposes its own `v3_meta.schema_migration` metadata.

The R1 normalized-V3 structural shell MUST therefore be authored in a separate migration package and MUST NOT be appended to the legacy/public manifest or normal deploy path by this slice.

Live application to the normalized V3 database remains a separate explicitly reviewed operator action.
