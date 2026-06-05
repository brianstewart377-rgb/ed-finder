# Stage 19V — source-run FK compatibility correction plan

## Result

Stage 19U audited source-run foreign-key compatibility across the production schema and repository code.

The audit confirmed the important compatibility boundary discovered during Stage 19T review:

- the new `source_runs` ledger exists and is valid for import-run provenance;
- legacy enrichment staging tables still use `source_run_id` values that reference `enrichment_source_runs(id)`;
- therefore `source_runs.id` must not be passed directly into legacy staging tables unless a compatibility bridge or migration has been designed and applied.

## Source artifact

- Artifact: `source_run_fk_compatibility_audit_20260605T163838Z.json`
- File SHA-256: `c58dd009e2fad79c0cb32b38c46f38567ef3a5d8a0f0978353e69db69b40c3bb`
- Artifact integrity SHA-256: `744232b5febef15b4068307151d7576e61cec5915a2b7f2165a1cffc93f3d7a2`

## Execution boundary

Stage 19U was read-only and audit-only.

| Check | Result |
|---|---:|
| DB writes performed | `False` |
| Imports performed | `False` |
| Migrations performed | `False` |
| Canonical writes performed | `False` |
| Canonical apply performed | `False` |
| Scheduler enabled | `False` |

## Validation checks

| Check | Result |
|---|---:|
| `known_edsm_legacy_fk_boundary_detected` | `True` |
| `source_run_id_fk_inventory_present` | `True` |
| `source_runs_counts_loaded` | `True` |
| `staging_fk_inventory_present` | `True` |

## Legacy source-run FK tables

| Table | FK target | Meaning |
|---|---|---|
| `derived_alert_candidates` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `derived_colonisation_economy_intelligence` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `derived_exploration_intelligence` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `derived_mission_intelligence` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `enrichment_raw_records` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `enrichment_source_files` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_body_rings` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_body_signals` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_codex_entries` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_edsm_bodies` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_edsm_stations` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_factions` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_market_commodities` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_station_economies` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_station_services` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |
| `staging_system_states` | `enrichment_source_runs(id)` | New `source_runs.id` is not directly compatible. |

## New source-run FK tables

| Table | FK target | Meaning |
|---|---|---|
| None found | n/a | n/a |

## Staging FK summary

| Table | `source_run_id` target | `source_file_id` target | `raw_record_id` target |
|---|---|---|---|
| `staging_body_rings` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_body_signals` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_codex_entries` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_edsm_bodies` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_edsm_stations` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_factions` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_market_commodities` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_station_economies` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_station_services` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |
| `staging_system_states` | `enrichment_source_runs` | `enrichment_source_files` | `enrichment_raw_records` |

## Potential code issues

The audit scanned repository references to `source_run_id`, `source_runs`, `enrichment_source_runs`, and staging inserts.

| Path | Line | Risk | Snippet |
|---|---:|---|---|
| `apps/importer/src/enrichment_warehouse_sql.py` | `439` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = ss.source_run_id` |
| `apps/importer/src/enrichment_warehouse_sql.py` | `538` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = sb.source_run_id` |
| `apps/importer/src/enrichment_warehouse_sql.py` | `639` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = br.source_run_id` |
| `tests/test_edsm_station_import.py` | `42` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `        if compact.startswith('insert into staging_edsm_stations'):` |
| `tests/test_edsm_station_import.py` | `137` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `                INSERT INTO staging_edsm_stations (` |
| `tests/test_edsm_station_import.py` | `259` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert not any('INSERT INTO staging_edsm_stations' in sql for sql, _params in conn.statements)` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `314` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_edsm_bodies' in sql_text` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `315` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_body_rings' in sql_text` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `316` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_edsm_stations' not in sql_text` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `366` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    conn = FakeConn(fail_on='insert into staging_body_rings')` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `378` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert any('INSERT INTO staging_edsm_bodies' in sql for sql, _params in conn.statements)` |
| `tests/test_enrichment_body_ring_staging_loader.py` | `379` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert any('INSERT INTO staging_body_rings' in sql for sql, _params in conn.statements)` |
| `tests/test_enrichment_staging_db_loader.py` | `186` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_edsm_stations' in sql_text` |
| `tests/test_enrichment_staging_db_loader.py` | `252` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    conn = FakeConn(fail_on='insert into staging_edsm_stations')` |
| `tests/test_enrichment_staging_db_loader.py` | `266` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `        'INSERT INTO staging_edsm_stations' in sql` |
| `tests/test_enrichment_staging_db_loader.py` | `430` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `        if 'INSERT INTO staging_edsm_stations' in sql` |
| `tests/test_enrichment_staging_db_loader.py` | `450` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_edsm_stations' in sql_text` |
| `tests/test_enrichment_staging_db_loader.py` | `451` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_edsm_bodies' not in sql_text` |
| `tests/test_enrichment_staging_db_loader.py` | `452` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `    assert 'INSERT INTO staging_body_rings' not in sql_text` |
| `tests/test_enrichment_staging_db_loader.py` | `561` | verify whether source_run_id value is an enrichment_source_runs.id or source_runs.id | `        if 'INSERT INTO staging_edsm_stations' in sql` |

## Policy recorded

Effective immediately:

1. Do not pass `source_runs.id` into a `source_run_id` column unless that column explicitly references `source_runs(id)`.
2. Treat all legacy enrichment staging tables as requiring `enrichment_source_runs.id` until proven otherwise.
3. Any importer using the new `source_runs` ledger and old enrichment staging must either:
   - use an explicit compatible stager that creates/uses the required legacy enrichment source-run rows;
   - use a schema bridge designed and migrated separately;
   - or remain parse/plan/artifact/source-run only with no real staging write.
4. Fake-connection tests are not enough for FK compatibility; any future staging execution path needs either disposable-DB tests or a rollback rehearsal.

## Correction options

### Option A — Explicit compatible stagers only

Keep `source_runs` as the root operational ledger while each legacy staging writer explicitly creates or resolves the required `enrichment_source_runs` row before inserting into legacy staging tables.

Pros:

- lowest schema risk;
- works with existing staging schema;
- avoids immediate migration of large staging tables.

Cons:

- temporary dual-ledger complexity;
- requires clear helper functions so importers do not hand-roll compatibility logic.

### Option B — Compatibility bridge table

Create a bridge from `source_runs` to `enrichment_source_runs`, for example one row mapping each new source run to its legacy enrichment run.

Pros:

- explicit relationship between new and old provenance systems;
- avoids changing large staging table FKs immediately.

Cons:

- still dual-ledger;
- requires migration and tests.

### Option C — Migrate staging FKs to `source_runs`

Change staging tables so `source_run_id` references `source_runs(id)`.

Pros:

- clean long-term model;
- removes dual-ledger mismatch.

Cons:

- higher-risk schema migration;
- requires backfill/mapping strategy for existing 298k+ EDSM station staging rows and other staging tables;
- should not be the first implementation step.

## Recommended path

Use **Option A first**.

Stage 19W should implement a small repo-only compatibility helper that can create or resolve a legacy `enrichment_source_runs` row for a new `source_runs` run in disposable/fake tests.

Only after that helper exists should we consider a controlled production staging rehearsal.

## Next stage

Stage 19W should be a Codex implementation prompt for a repo-only source-run/enrichment-run compatibility helper.

Stage 19W must remain repo-only:

- no production DB access;
- no production imports;
- no scheduler/timer enablement;
- no canonical writes;
- no canonical apply.

## Verdict

Stage 19V records the correction plan for source-run FK compatibility.

No imports, DB writes, migrations, scheduler/timer enablement, canonical writes, or canonical apply are approved by this document.
