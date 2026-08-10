# Stage 18J-P17D — Station-type source mapping review closeout

## Result

Stage 18J-P17D generated a read-only source mapping review artifact for the 11 confirmed-identity canonical stations whose station type remains `Unknown`.

The review classified each source `public.staging_edsm_stations.station_type` value before any station-type dry-run or write is considered.

This stage does not infer station type, run a station-type dry-run, write station types, write canonical rows, or perform canonical apply.

## Source artifact

Mapping review artifact:

- `station_type_source_mapping_review_20260603T222512Z.json`
- File SHA-256: `e8deecfde31d913a63b6e5a6646cc6fc8d0d21d5bae759b861e2cc8baf37d88d`
- Artifact integrity SHA-256: `a5ff990c2c8f608c95c2c4875e5d8c6075fbdb4ed5f3e0bfc3d56a331c1ec8db`

## Execution boundary

The Stage 18J-P17D action was read-only and artifact-only.

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

## Read-only confirmation

The artifact recorded:

| Check | Result |
|---|---:|
| `schema_version` | `station_type_source_mapping_review/v1` |
| `read_only` | `True` |
| `transaction_read_only` | `on` |

## Mapping review summary

The artifact recorded:

| Check | Result |
|---|---:|
| Candidate rows | `11` |
| Distinct source values | `5` |
| Safe mapping candidate rows | `3` |
| Blocked/manual/design/refuse rows | `8` |
| `station_type_writes_planned` | `0` |
| `canonical_writes_planned` | `0` |
| `station_type_dry_run_performed` | `False` |
| `canonical_apply_performed` | `False` |
| `ready_for_bounded_dry_run_planning` | `True` |

## Source value classification

| Source `station_type` value | Rows | Classification | Proposed canonical type | Decision |
|---|---:|---|---|---|
| `Coriolis Starport` | `3` | `safe_mapping_candidate` | `Coriolis` | Safe candidate for a later bounded dry-run plan. |
| `Drake-Class Carrier` | `5` | `manual_review_required` | `FleetCarrier` | Likely mapping, but carrier semantics require explicit policy. |
| `Dodec Starport` | `1` | `requires_enum_support` | `Dodec` | Human decision: `Dodec Starport -> Dodec` is correct, but the current canonical enum lacks `Dodec`. |
| `Space Construction Depot` | `1` | `refuse_transient_construction_object` | `NULL` | Temporary construction object; do not map to a normal station type. |
| `NULL` | `1` | `refuse` | `NULL` | Source has no station type value. |

## Human decision recorded

The human reviewer confirmed:

```text
Dodec Starport -> Dodec 100%
```

This means the intended policy is now clear. However, `Dodec` is not currently available in the canonical `station_type` enum. Therefore, `Dodec Starport` cannot be included in a station-type write or dry-run that targets the current enum until a separate schema/design step adds enum support or otherwise updates the canonical station-type model.

## Construction depot policy

The human reviewer clarified that a construction depot is the temporary object deployed while materials are delivered to build a station. Once construction is complete, the final station appears and the construction depot disappears at the weekly tick.

Therefore:

```text
Space Construction Depot -> refuse/defer as transient construction object
```

It should not be mapped to a normal canonical station type.

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

Stage 18J-P17D confirms that only the 3 `Coriolis Starport -> Coriolis` rows are safe automatic candidates under the current schema.

`Dodec Starport -> Dodec` is the correct human-reviewed mapping, but it requires a separate schema/model step before it can be included in a canonical station-type dry-run or write path.

No station-type dry-run, station-type writes, canonical writes, or canonical apply are approved by this stage.

## Next stage

The next stage should be one of:

1. a bounded dry-run planning artifact for only the 3 currently safe `Coriolis Starport -> Coriolis` rows; or
2. a schema/design branch to add `Dodec` as a canonical station type before including the Dodec row in a later dry-run.

Any actual station-type dry-run remains a separate bounded action and must still produce its own artifact before any review packet or write can be discussed.

