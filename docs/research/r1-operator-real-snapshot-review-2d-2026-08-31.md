# ED-Finder R1 — Operator Real-System Snapshot
## Review 2D — Schema/Relation Metadata Discovery Amendment

Date: 2026-08-31
Status: metadata-only discovery amendment.

## Triggering evidence

The PostgreSQL inventory run `33398525949` found three PostgreSQL containers. The large retained ED-Finder database is present:

- container: `edfinder-v3-phase4c-full-20260827_r5-postgres`
- database: `edfinder_v3_phase4c_full_20260827_r5`
- size: ~566.44 GiB

However, `to_regclass('public.systems')`, `public.bodies`, `public.body_rings`, `public.ratings`, and `public.stations` all returned false.

This strongly suggests the retained dataset is not stored under the `public` schema and/or uses different relation names. No gameplay rows were read.

## Goal

Discover the schema/relation names needed to locate canonical system/body data without reading table rows.

## Allowed metadata queries

Against the identified large retained database only, run PostgreSQL catalog queries over `pg_namespace`, `pg_class`, `pg_attribute`, and `information_schema.tables` to report:

1. all non-system schemas and their relation counts;
2. relations whose names exactly equal or lexically contain:
   - `system`
   - `body`
   - `rating`
   - `station`
   - `ring`
3. for candidate relations only, column-name lists and approximate `reltuples` estimates from `pg_class`;
4. relation kind (table, partitioned table, view, materialized view) and schema.

No `SELECT *` or row reads from application/gameplay relations are allowed in this discovery stage.

## Safety

- catalog metadata only;
- no writes/schema mutations;
- no table data rows;
- no credentials logged/artifacted;
- pinned SSH trust and existing operator environment only.

## Decision rule

If metadata identifies a clear system/body source, define a narrow adapter for its actual schema before any body-row snapshot query.

If no body-like relation exists anywhere in the retained database, stop treating this PG18 snapshot as a possible R1 body source and move to the actual live canonical store or external/current source path instead.
