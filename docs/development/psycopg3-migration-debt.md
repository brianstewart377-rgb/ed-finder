# Psycopg 3 Migration Debt

The V3 API dependency graph contains asyncpg for application database access
and Psycopg 3 only for synchronous release/checkpoint test tooling. It contains
no psycopg2 dependency.

The following CPython 3.14 importer modules still import psycopg2 and are
bounded driver-migration debt. They remain covered by the non-runtime retained-tooling
lane defined in `.github/workflows/ci.yml`; this correction does not attempt an
unbounded importer rewrite:

- `apps/importer/src/backfill_station_body_links.py`
- `apps/importer/src/build_archetype_scores.py`
- `apps/importer/src/build_clusters.py`
- `apps/importer/src/build_grid.py`
- `apps/importer/src/build_ratings.py`
- `apps/importer/src/build_regional_analysis.py`
- `apps/importer/src/build_topology.py`
- `apps/importer/src/canonical_evidence_promotion.py`
- `apps/importer/src/edsm_station_enrichment_probe.py`
- `apps/importer/src/enrich_system_data.py`
- `apps/importer/src/enrichment_staging_db_loader.py`
- `apps/importer/src/fix_index.py`
- `apps/importer/src/import_spansh.py`
- `apps/importer/src/inara_evidence_import.py`
- `apps/importer/src/station_external_identity_candidates.py`
- `apps/importer/src/station_external_identity_loader.py`
- `apps/importer/src/station_type_canonical_pilot.py`

Directly related synchronous debt outside `apps/importer/` is limited to the
five importer repair/reconciliation scripts under `scripts/`, the local test
environment preflight, and two retained Stage 19 operator rehearsals:

- `scripts/reconcile_no_body_ratings.py`
- `scripts/repair_body_contract.py`
- `scripts/repair_body_ring_association_status.py`
- `scripts/repair_eddn_ring_identity.py`
- `scripts/repair_station_body_links.py`
- `scripts/dev/test_env_preflight.py`
- `scripts/operator/stage19anr_warehouse_derived_staging_rehearsal.py`
- `scripts/operator/stage19ar_edsm_25_row_staging_pilot.py`

`tests/legacy_psycopg2_test_paths.txt` is the executable test-lane boundary for
this debt. Remove entries from both inventories as each path is ported.
