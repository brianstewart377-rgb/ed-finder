# Stage 18J-P17E — Revised station-type source mapping review closeout

## Result

Stage 18J-P17E generated a revised read-only source mapping review artifact for the 11 confirmed-identity canonical stations whose station type remains `Unknown`.

This revision records the stricter human policy that fleet carriers should not be surfaced as stable canonical stations in ED-Finder because they are mobile, player-owned, and transient.

This stage does not infer station type, run a station-type dry-run, write station types, write canonical rows, or perform canonical apply.

## Source artifact

- Artifact: `station_type_source_mapping_review_revised_20260603T223755Z.json`
- File SHA-256: `c92268e0780c93e2152a73407c659c079b3467585aab8b87a11a526f0caa287c`
- Artifact integrity SHA-256: `20df98882ad4fb6fa043b7f42ffbb5b628cea83a067c38a245536990daa59fe6`

## Execution boundary

The Stage 18J-P17E action was read-only and artifact-only.

It did not perform any of the following:

- identity writes;
- canonical writes;
- station-type writes;
- station-type dry-run;
- canonical apply;
- imports;
- reconciliation writes;
- summarizer runs;
- production approval-record creation.

## Revised mapping summary

| Check | Result |
|---|---:|
| Candidate rows | `11` |
| Distinct source values | `5` |
| Safe mapping candidate rows | `3` |
| Rows requiring enum support | `1` |
| Refused or blocked rows | `8` |
| `station_type_writes_planned` | `0` |
| `canonical_writes_planned` | `0` |
| `station_type_dry_run_performed` | `False` |
| `canonical_apply_performed` | `False` |
| `ready_for_bounded_dry_run_planning` | `True` |

## Source value classification

| Source `station_type` value | Rows | Classification | Proposed canonical type | Decision |
|---|---:|---|---|---|
| `Coriolis Starport` | `3` | `safe_mapping_candidate` | `Coriolis` | Safe candidate for a later bounded dry-run plan. |
| `Dodec Starport` | `1` | `requires_enum_support` | `Dodec` | Human-approved mapping, but requires enum support before write/dry-run inclusion. |
| `Drake-Class Carrier` | `5` | `refuse_transient_mobile_carrier` | `NULL` | Refuse/defer because fleet carriers are mobile/player-owned/transient and should not be stable canonical stations in ED-Finder. |
| `Space Construction Depot` | `1` | `refuse_transient_construction_object` | `NULL` | Temporary construction object; do not map to normal station type. |
| `NULL` | `1` | `refuse` | `NULL` | Source has no station type value. |

## Human decisions recorded

The human reviewer confirmed that `Dodec Starport -> Dodec` is correct.

The human reviewer also clarified that fleet carriers should never show as stable station candidates because they are too transient.

Therefore, `Drake-Class Carrier` is refused/deferred as a transient/mobile carrier.

## Construction depot policy

A construction depot is the temporary object deployed while materials are delivered to build a station. Once construction is complete, the final station appears and the construction depot disappears at the weekly tick.

Therefore, `Space Construction Depot` is refused/deferred as a transient construction object and should not be mapped to a normal canonical station type.

## Current canonical enum constraint

The current canonical station-type enum supports:

- `AsteroidBase`
- `Coriolis`
- `FleetCarrier`
- `MegaShip`
- `Ocellus`
- `Orbis`
- `Outpost`
- `PlanetaryOutpost`
- `PlanetaryPort`
- `Unknown`

It does not currently support `Dodec`.

## Verdict

Only the 3 `Coriolis Starport -> Coriolis` rows are safe automatic candidates under the current schema and current transient-object policy.

`Dodec Starport -> Dodec` is the correct human-reviewed mapping, but it requires a separate enum/schema/model step before it can be included in a canonical station-type dry-run or write path.

`Drake-Class Carrier` and `Space Construction Depot` are refused/deferred as transient objects.

No station-type dry-run, station-type writes, canonical writes, or canonical apply are approved by this stage.

## Next stage

The next stage should be one of:

1. a bounded dry-run planning artifact for only the 3 currently safe `Coriolis Starport -> Coriolis` rows; or
2. a schema/design branch to add `Dodec` as a canonical station type before including the Dodec row in a later dry-run.

Any actual station-type dry-run remains a separate bounded action and must still produce its own artifact before any review packet or write can be discussed.

