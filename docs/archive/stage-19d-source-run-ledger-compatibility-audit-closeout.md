# Stage 19D — Source-run ledger compatibility audit closeout

## Result

Stage 19D generated a read-only compatibility audit for the existing enrichment/source-run/import metadata tables.

The audit found that the existing source-run-like scaffolding is not sufficient as the final Data Warehouse Utopia source-run ledger contract.

Decision:

- existing usable ledger candidate: `False`
- recommended decision: `create_or_extend_source_runs_contract`

Therefore Stage 19 should proceed with a proper `source_runs` contract, either by creating a new table or extending existing structures in a controlled migration.

## Source artifact

- Artifact: `source_run_ledger_compatibility_audit_20260605T004536Z.json`
- File SHA-256: `cf2abbb2365866502fd990cd19e341601f9812134dabde1f8b32d96a0270a7f2`
- Artifact integrity SHA-256: `c89b32d1662da92a9c790027786b4560dc55f3afd9620ef3600247c7c8002418`

## Execution boundary

Stage 19D compatibility audit was read-only.

It did not perform:

- DB writes;
- imports;
- migrations;
- canonical apply;
- repo edits.

## Safety confirmation

| Check | Result |
|---|---:|
| `db_writes_performed` | `False` |
| `imports_performed` | `False` |
| `migrations_performed` | `False` |
| `canonical_apply_performed` | `False` |

## Compatibility summary

| Table | Looks like source-run ledger | Contract fields present | Contract fields missing |
|---|---:|---:|---:|
| `public.api_cache` | `False` | `1` | `25` |
| `public.app_meta` | `False` | `1` | `25` |
| `public.attractions` | `False` | `1` | `25` |
| `public.bodies` | `False` | `1` | `25` |
| `public.body_rings` | `False` | `1` | `25` |
| `public.body_rings_eddn_identity_report` | `False` | `0` | `26` |
| `public.body_scan_facts` | `False` | `1` | `25` |
| `public.cluster_summary` | `False` | `1` | `25` |
| `public.colony_simulations` | `False` | `1` | `25` |
| `public.enrichment_raw_records` | `False` | `0` | `26` |
| `public.enrichment_source_files` | `False` | `0` | `26` |
| `public.enrichment_source_runs` | `False` | `1` | `25` |
| `public.factions` | `False` | `1` | `25` |
| `public.import_meta` | `False` | `3` | `23` |
| `public.journal_events` | `False` | `0` | `26` |
| `public.profile_sync` | `False` | `2` | `24` |
| `public.ratings` | `False` | `1` | `25` |
| `public.staging_body_rings` | `False` | `0` | `26` |
| `public.staging_body_signals` | `False` | `0` | `26` |
| `public.staging_codex_entries` | `False` | `0` | `26` |
| `public.staging_edsm_bodies` | `False` | `0` | `26` |
| `public.staging_edsm_stations` | `False` | `0` | `26` |
| `public.staging_factions` | `False` | `0` | `26` |
| `public.staging_market_commodities` | `False` | `0` | `26` |
| `public.staging_station_economies` | `False` | `0` | `26` |
| `public.staging_station_services` | `False` | `0` | `26` |
| `public.staging_system_states` | `False` | `0` | `26` |
| `public.station_body_links` | `False` | `1` | `25` |
| `public.station_external_identity` | `True` | `3` | `23` |
| `public.stations` | `False` | `1` | `25` |
| `public.system_archetype_scores` | `False` | `1` | `25` |
| `public.system_archetype_traits` | `False` | `1` | `25` |
| `public.system_detail` | `False` | `1` | `25` |
| `public.system_factions` | `False` | `1` | `25` |
| `public.system_notes` | `False` | `1` | `25` |
| `public.system_slot_topology` | `False` | `1` | `25` |
| `public.systems` | `False` | `1` | `25` |

## Related table sizes

| Table | Approx rows | Size |
|---|---:|---:|
| `public.enrichment_raw_records` | `123444` | `7501 MB` |
| `public.enrichment_source_files` | `-1` | `80 kB` |
| `public.enrichment_source_runs` | `-1` | `80 kB` |
| `public.import_meta` | `3` | `80 kB` |

## Interpretation

The compatibility audit shows that the project has useful enrichment/source-run/import scaffolding, but it should not be treated as the final ledger without hardening.

The next stage should design and implement the durable `source_runs` ledger contract for all future automated imports.

## Next stage

Stage 19E should be the source-run ledger schema implementation plan.

It should decide whether to:

1. create a new `source_runs` table; or
2. extend existing `enrichment_source_runs` structures into the full contract.

Given this audit result, the current preferred path is:

`create_or_extend_source_runs_contract`

Any schema change must be a separate reviewed migration stage. No DB write is approved by this closeout.

## Verdict

Stage 19D compatibility audit is complete.

Proceed to Stage 19E source-run ledger schema implementation plan.

