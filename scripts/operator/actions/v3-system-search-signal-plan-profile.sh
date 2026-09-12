#!/usr/bin/env bash
set -euo pipefail

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"

fail() {
  printf 'v3 system search signal profile: %s\n' "$*" >&2
  exit 64
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
[ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
[ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
[ "$(docker context show)" = "default" ] || fail "unexpected docker context"
[ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)" = "true" ] \
  || fail "retained postgres container is not running"

psql_base=(
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password
  --tuples-only --no-align --quiet --set ON_ERROR_STOP=1
  --username "$DATABASE_USER" --dbname "$DATABASE_NAME"
)

meta="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT g.derived_generation_id::text || E'\\t' ||
       (g.manifest->>'canonical_schema') || E'\\t' ||
       COALESCE((SELECT max(b.chunk_ordinal)::text
                   FROM v3_derived.build_chunk b
                  WHERE b.derived_generation_id=g.derived_generation_id),'')
  FROM v3_meta.derived_generation g
 WHERE g.generation_key='${TARGET_GENERATION_KEY}';
COMMIT;")"
IFS=$'\t' read -r generation_id canonical_schema chunk_ordinal <<< "$meta"
[[ "$generation_id" =~ ^[0-9a-f-]{36}$ ]] || fail "derived generation id is invalid"
[[ "$canonical_schema" =~ ^v3_gen_[a-z0-9_]{1,31}$ ]] || fail "canonical schema is invalid"
[[ "$chunk_ordinal" =~ ^[0-9]+$ ]] || fail "profile chunk ordinal is invalid"

printf 'signal_profile_generation=%s\n' "$generation_id"
printf 'signal_profile_chunk=%s\n' "$chunk_ordinal"
printf 'signal_table_stats='
"${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT json_build_object(
  'n_live_tup',s.n_live_tup,
  'last_analyze',s.last_analyze,
  'last_autoanalyze',s.last_autoanalyze,
  'table_bytes',pg_relation_size(format('%I.body_signal_current','${canonical_schema}')::regclass),
  'total_bytes',pg_total_relation_size(format('%I.body_signal_current','${canonical_schema}')::regclass),
  'body_pk_n_distinct',(SELECT n_distinct FROM pg_stats WHERE schemaname='${canonical_schema}' AND tablename='body_signal_current' AND attname='body_pk')
)
FROM pg_stat_all_tables s
WHERE s.schemaname='${canonical_schema}' AND s.relname='body_signal_current';
COMMIT;"

run_variant() {
  local label="$1" settings="$2" query_kind="$3"
  printf 'signal_variant=%s\n' "$label"
  printf 'signal_plan_json=\n'
  if [ "$query_kind" = "current" ]; then
    docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
      --no-align --quiet --set ON_ERROR_STOP=1 --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
${settings}
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
WITH target AS MATERIALIZED (
    SELECT v.system_id64
      FROM v3_derived.system_rating_vector v
     WHERE v.derived_generation_id='${generation_id}'::uuid
       AND v.chunk_ordinal=${chunk_ordinal}
)
SELECT b.system_id64,
       bool_or(st.public_code='saa_signaltype_biological' AND bs.signal_count>0) AS has_biologicals,
       bool_or(st.public_code='saa_signaltype_geological' AND bs.signal_count>0) AS has_geologicals
  FROM ${canonical_schema}.body_signal_current bs
  JOIN ${canonical_schema}.bodies b ON b.body_pk=bs.body_pk
  JOIN target t ON t.system_id64=b.system_id64
  JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
 WHERE b.lifecycle_state='ACTIVE'
 GROUP BY b.system_id64;
ROLLBACK;
SQL
  else
    docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
      --no-align --quiet --set ON_ERROR_STOP=1 --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SET LOCAL jit=off;
SET LOCAL join_collapse_limit=1;
SET LOCAL from_collapse_limit=1;
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
WITH target AS MATERIALIZED (
    SELECT v.system_id64
      FROM v3_derived.system_rating_vector v
     WHERE v.derived_generation_id='${generation_id}'::uuid
       AND v.chunk_ordinal=${chunk_ordinal}
)
SELECT b.system_id64,
       bool_or(st.public_code='saa_signaltype_biological' AND bs.signal_count>0) AS has_biologicals,
       bool_or(st.public_code='saa_signaltype_geological' AND bs.signal_count>0) AS has_geologicals
  FROM target t
  JOIN ${canonical_schema}.bodies b ON b.system_id64=t.system_id64 AND b.lifecycle_state='ACTIVE'
  JOIN ${canonical_schema}.body_signal_current bs ON bs.body_pk=b.body_pk
  JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
 GROUP BY b.system_id64;
ROLLBACK;
SQL
  fi
}

run_variant baseline "SET LOCAL jit=off;" current
run_variant hashjoin_off "SET LOCAL jit=off; SET LOCAL enable_hashjoin=off;" current
run_variant seqscan_off "SET LOCAL jit=off; SET LOCAL enable_seqscan=off;" current
run_variant high_work_mem "SET LOCAL jit=off; SET LOCAL work_mem='256MB';" current
run_variant target_first "" target_first

printf 'database_writes_performed=false\n'
printf 'schema_changes_performed=false\n'
printf 'publication_performed=false\n'
printf 'canonical_writes_performed=false\n'
