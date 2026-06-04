# Stage 19A — Warehouse auto-import readiness closeout

## Result

Stage 19A generated a read-only warehouse and auto-import readiness artifact.

The artifact confirms that the data warehouse is not empty, but it is not yet operational as an automated import engine. It contains substantial existing data and domain scaffolding, but the automation/freshness/source-run pipeline still needs to be made real.

## Source artifact

- `warehouse_auto_import_readiness_20260604T230841Z.json`
- File SHA-256: `95b9869529a16fd0f0b43c0f57c9cbfde71ff0d6edc7addec1ab7f788d76eefb`
- Artifact integrity SHA-256: `e0e80179d352608e3ccdadbeda0b3f04f990ab7411f50621ef1104599e6d57a7`

## Execution boundary

Stage 19A was read-only.

It did not perform any of the following:

- DB writes;
- imports;
- migrations;
- canonical apply;
- station-type writes.

## High-level findings

The artifact recorded:

| Check | Result |
|---|---:|
| `schema_version` | `warehouse_auto_import_readiness/v1` |
| `read_only` | `True` |
| `transaction_read_only` | `on` |
| DB table count | `59` |
| Warehouse-related columns | `361` |
| Warehouse-related indexes | `63` |
| Provenance columns | `64` |

## Warehouse signals

| Signal | Result |
|---|---:|
| `has_staging_tables` | `True` |
| `has_enrichment_tables` | `True` |
| `has_import_tables` | `True` |
| `has_source_like_tables` | `True` |
| `has_source_run_table` | `True` |
| `has_body_tables` | `True` |
| `has_ring_tables` | `True` |
| `has_mission_tables` | `True` |
| `has_snapshot_tables` | `False` |
| `has_warehouse_tables` | `False` |

## Domain presence summary

| Domain | Tables | Repo file matches | Notes |
|---|---:|---:|---|
| Systems | `8` | `4` | Existing system tables are substantial. |
| Bodies | `7` | `11` | Body/ring scaffolding exists. |
| Rings | `3` | `12` | Rings are already represented. |
| Stations | `7` | `33` | Station staging/canonical/evidence tables exist. |
| Factions | `3` | `0` | DB tables exist but repo code visibility is low. |
| Markets | `1` | `0` | Staging market commodity table exists. |
| Services | `1` | `5` | Staging service table exists. |
| Missions | `1` | `0` | Mission intelligence table exists, but code support looks thin. |
| Facilities | `1` | `5` | Facility templates exist. |
| Construction | `1` | `94` | Colonisation intelligence exists. |
| Artifacts | `0` | `45` | Many repo artifact references, but no first-class artifact table yet. |
| Belt clusters | `0` | `0` | Missing as first-class domain. |
| Settlements | `0` | `0` | Missing as first-class domain. |
| Stars | `0` | `0` | Missing as first-class domain. |

## Large existing tables

The artifact shows that the database already contains very large datasets:

| Table | Approx rows | Size |
|---|---:|---:|
| `ratings` | `187,834,544` | `437 GB` |
| `systems` | `187,330,784` | `238 GB` |
| `bodies` | `573,945,728` | `212 GB` |
| `system_archetype_scores` | `9,850,696` | `17 GB` |
| `economy_pair_synergy` | `61,753,136` | `12 GB` |
| `enrichment_raw_records` | `123,444` | `7501 MB` |
| `system_slot_topology` | `5,617,070` | `5187 MB` |
| `staging_edsm_stations` | `298,177` | `3528 MB` |
| `eddn_log` | `19,915,518` | `3049 MB` |

This means Stage 19 is not starting from an empty database. It is starting from a large existing dataset that needs import discipline, lifecycle management, automation, and visibility.

## Identity/station-type state

The artifact recorded:

| Source type | Canonical station type | Rows |
|---|---|---:|
| `Coriolis Starport` | `Coriolis` | `4` |
| `Dodec Starport` | `Dodec` | `1` |
| `Drake-Class Carrier` | `Unknown` | `5` |
| `Outpost` | `Outpost` | `7` |
| `Planetary Outpost` | `PlanetaryOutpost` | `1` |
| `Space Construction Depot` | `Unknown` | `1` |
| `NULL` | `Unknown` | `1` |

This confirms the Stage 18J/P18 policies are reflected in the current production state.

## Interpretation

Stage 19A confirms the warehouse problem is not lack of data. The problem is that the existing data and scaffolding are not yet organised into a boring, automated, auditable import pipeline.

The next engineering work should focus on:

1. source-run ledger / import-run truth;
2. source/domain architecture boundaries;
3. idempotent import wrappers;
4. first automated source import, likely EDSM;
5. freshness/failure artifacts;
6. admin/operator visibility.

## Recommended next stage

Stage 19B should define the warehouse target architecture and auto-import safety design.

It should decide how to handle:

- raw/source layer;
- staging layer;
- warehouse facts;
- canonical layer;
- source-run ledger;
- operator artifacts;
- freshness reporting;
- scheduler/automation safety;
- admin visibility.

## Verdict

Stage 19A is complete.

No imports, DB writes, migrations, station-type writes, or canonical apply were performed.