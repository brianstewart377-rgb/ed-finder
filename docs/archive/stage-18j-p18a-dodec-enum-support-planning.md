# Stage 18J-P18A — Dodec enum support planning closeout

## Result

Stage 18J-P18A generated a read-only Dodec enum/schema support planning artifact.

The artifact confirms that `Dodec Starport -> Dodec` is the human-reviewed mapping policy, but the current canonical `station_type` enum does not yet include `Dodec`.

This stage did not modify the enum, run migrations, write station types, run a station-type dry-run, write canonical rows, or perform canonical apply.

## Source artifact

Planning artifact:

- `dodec_station_type_enum_support_plan_20260604T093628Z.json`
- File SHA-256: `3b657943bf1c6009801c31345c7ef8e5bb8302dc784f9f15f39e9284486863e0`
- Artifact integrity SHA-256: `496f107505785210b5f28ae19778fa339e1bdee9c989bb6b76cf92b7673cd7df`

## Execution boundary

The Stage 18J-P18A action was read-only and artifact-only.

It did not perform any of the following:

- enum changes;
- migrations;
- identity writes;
- canonical writes;
- station-type writes;
- station-type dry-run;
- canonical apply;
- imports;
- reconciliation writes;
- summarizer runs;
- production approval-record creation;
- repo edits.

## Read-only confirmation

The artifact recorded:

| Check | Result |
|---|---:|
| `schema_version` | `dodec_station_type_enum_support_plan/v1` |
| `read_only` | `True` |
| `transaction_read_only` | `on` |

## Current enum state

The artifact recorded the current canonical `station_type` enum values:

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

It also recorded:

| Check | Result |
|---|---:|
| `dodec_in_station_type_enum` | `False` |
| `schema_support_required` | `True` |
| `station_type_columns` | `public.stations.station_type` |

## Dodec candidate row

The artifact found one Dodec candidate row:

| Field | Value |
|---|---|
| Canonical station ID | `4332505347` |
| Canonical station name | `Piccard Town` |
| Current canonical station type | `Unknown` |
| EDSM station ID | `4332505347` |
| Source station type | `Dodec Starport` |
| Landing pad size | `L` |
| Primary economy | `Tourism` |
| Has market | `True` |
| Has shipyard | `True` |
| Has outfitting | `True` |

## Policy

Human-reviewed mapping policy:

```text
Dodec Starport -> Dodec
```

This policy is approved, but it cannot be written to `stations.station_type` until the canonical `station_type` enum/model supports `Dodec`.

## Proposed next steps

The artifact recommends:

1. Create a separate schema/design PR to add `Dodec` to the canonical station-type model.
2. Use a migration shape similar to:

```sql
ALTER TYPE station_type ADD VALUE IF NOT EXISTS 'Dodec';
```

3. Add or update station-type mapping logic only after enum support exists.
4. Add tests proving:
   - `Dodec Starport -> Dodec` is accepted only when enum/model support exists;
   - `Drake-Class Carrier` remains refused/deferred as transient/mobile;
   - `Space Construction Depot` remains refused/deferred as transient construction object;
   - `NULL` source station type remains refused.

## Safety boundary confirmation

The artifact safety summary confirms:

| Boundary | Result |
|---|---:|
| `db_read_only_confirmed` | `True` |
| `identity_rows_written` | `0` |
| `canonical_writes_planned` | `0` |
| `station_type_writes_planned` | `0` |
| `station_type_dry_run_performed` | `False` |
| `canonical_apply_performed` | `False` |
| `imports_performed` | `False` |
| `reconciliation_write_performed` | `False` |
| `summarizer_performed` | `False` |
| `approval_record_created` | `False` |
| `repo_edits_performed` | `False` |
| `dodec_candidate_count_expected` | `True` |
| `dodec_enum_support_missing_as_expected` | `True` |

## Verdict

Stage 18J-P18A confirms that Dodec support is a schema/model prerequisite before the Dodec candidate can enter any station-type dry-run or write path.

No enum changes, station-type dry-run, station-type writes, canonical writes, or canonical apply are approved by this stage.

## Next stage

The next stage should be a separate schema/model branch for Dodec enum support.

That branch should be reviewed and tested independently before any station-type dry-run includes the Dodec candidate row.

