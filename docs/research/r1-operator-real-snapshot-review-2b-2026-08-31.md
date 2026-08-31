# ED-Finder R1 — Operator Real-System Snapshot
## Review 2B — Optional Ring Source Amendment

Date: 2026-08-31
Status: bounded contract correction after retained-PG18 discovery.

## Triggering evidence

Retry workflow run `33397690651` reached the retained PostgreSQL container and successfully enumerated database tables, but found no database containing all of `systems`, `bodies`, and `body_rings` because the retained PG18 snapshot predates the canonical `body_rings` table.

No R1 system/body snapshot query was executed.

## Semantic correction

Absence of the ring table must **not** block validation of canonical system/body facts and must never be interpreted as `has_rings=false`.

This matches the R1 evidence rule already established for rings:

> missing ring evidence means Unknown, not no rings.

## Snapshot-loader change

The bounded loader may inspect table availability with one additional static SELECT:

`SELECT to_regclass('public.body_rings') IS NOT NULL AS body_rings_present`

After verifying `transaction_read_only=on`:

- if the table exists, query `body_rings` as before;
- if absent, do not issue the ring SELECT and use an empty ring-evidence tuple;
- downstream body projection therefore keeps `has_rings=None` unless another trusted ring source exists;
- snapshot bundle/report must expose `ring_source_available: bool` so consumers can distinguish “source unavailable” from “source queried with no matched rows”.

## Report caveat

When `ring_source_available=false`, add explicit caveat:

`canonical body_rings source unavailable in this database snapshot; ring facts remain Unknown`

The snapshot digest must include ring-source availability so snapshots from schemas with/without the ring source cannot collide.

## Operator discovery change

The workflow database identity gate now requires exactly one retained database with:

- `systems`
- `bodies`

`body_rings` and `ratings` become diagnostic booleans, not selection blockers.

If multiple databases contain systems+bodies, still fail closed.

## Tests

Add regression assertions:

- missing `body_rings` table does not block body snapshot;
- no ring query occurs when source unavailable;
- projected ring value remains Unknown;
- report exposes `ring_source_available=false` and caveat;
- digest differs when ring source availability differs;
- source SQL remains SELECT/SHOW only.

No other data source or scoring behavior changes.
