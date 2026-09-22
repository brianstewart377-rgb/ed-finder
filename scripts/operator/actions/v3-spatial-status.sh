#!/usr/bin/env bash
# Read-only V3 spatial-pyramid status. Reports whether the pre-012 derived-keyed
# v3_spatial.cell_summary table exists and how many rows it holds (migration 012
# DROPs and replaces that table, so this is the emptiness receipt required before
# a governed schema-migration apply), plus whether the decoupled
# v3_spatial.spatial_generation table and migration 012 are already present in the
# ledger. Strictly read-only: BEGIN READ ONLY around every query, no writes, no
# service or filesystem changes.
set -euo pipefail

POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"

emit_stopped() {
  printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-spatial-status","status":"stopped","read_only":true,"direct_db_access_performed":false,"db_writes_performed":false,"service_changes_performed":false,"filesystem_writes_performed":false,"failures":["%s"]}\n' "$1"
  exit 1
}

command -v docker >/dev/null 2>&1 || emit_stopped "docker_unavailable"
docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || emit_stopped "postgres_container_unavailable"
[ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null)" = "true" ] || emit_stopped "postgres_container_not_running"

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

cell_summary="$(db_query "BEGIN READ ONLY; SELECT COALESCE(to_regclass('v3_spatial.cell_summary')::text,''); COMMIT;")" || emit_stopped "cell_summary_probe_failed"
cell_summary_rows="null"
cell_summary_columns=""
if [ -n "$cell_summary" ]; then
  cell_summary_rows="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_spatial.cell_summary; COMMIT;")" || emit_stopped "cell_summary_count_failed"
  cell_summary_columns="$(db_query "BEGIN READ ONLY; SELECT COALESCE(string_agg(column_name, ',' ORDER BY ordinal_position),'') FROM information_schema.columns WHERE table_schema='v3_spatial' AND table_name='cell_summary'; COMMIT;")" || cell_summary_columns=""
fi
spatial_generation="$(db_query "BEGIN READ ONLY; SELECT COALESCE(to_regclass('v3_spatial.spatial_generation')::text,''); COMMIT;")" || emit_stopped "spatial_generation_probe_failed"
migration_012="$(db_query "BEGIN READ ONLY; SELECT COALESCE(encode(migration_sha256,'hex'),'') FROM v3_meta.schema_migration WHERE migration_name='012_v3_spatial_pyramid_decouple.sql'; COMMIT;")" || emit_stopped "migration_ledger_probe_failed"

present() { [ -n "$1" ] && echo true || echo false; }

# 012's DROP TABLE IF EXISTS v3_spatial.cell_summary is a safe no-op when the
# table is absent, and safe when present-but-empty; only a populated table needs
# an explicit disposition.
if [ -z "$cell_summary" ] || [ "$cell_summary_rows" = "0" ]; then
  safe_to_drop="true"
else
  safe_to_drop="false"
fi

printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"v3-spatial-status","status":"ok","read_only":true,"direct_db_access_performed":true,"db_writes_performed":false,"service_changes_performed":false,"filesystem_writes_performed":false,"cell_summary_present":%s,"cell_summary_row_count":%s,"cell_summary_columns":"%s","spatial_generation_table_present":%s,"migration_012_in_ledger":%s,"safe_to_drop_cell_summary":%s}\n' \
  "$(present "$cell_summary")" \
  "${cell_summary_rows}" \
  "${cell_summary_columns}" \
  "$(present "$spatial_generation")" \
  "$(present "$migration_012")" \
  "${safe_to_drop}"
