#!/usr/bin/env bash
set -euo pipefail

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
CANONICAL_SEQUENCE="4"
CANONICAL_SCHEMA="v3_gen_phase4c_full_20260827_r5"
DERIVED_KEY="ratings_v4_prod_p4_opt1"
STATISTICS_TARGET="1000"
N_DISTINCT_OVERRIDE="-0.10"

fail() {
  printf 'v3 system search tune system-id stats: %s\n' "$*" >&2
  exit 64
}

command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
[ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
[ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
[ "$(docker context show)" = "default" ] || fail "unexpected docker context"
docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
  || fail "default docker context is not the local rootful socket"
[ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)" = "true" ] \
  || fail "retained postgres container is not running"

psql_base=(
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password
  --tuples-only --no-align --quiet --set ON_ERROR_STOP=1
  --username "$DATABASE_USER" --dbname "$DATABASE_NAME"
)

authority="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT c.generation_id::text || E'\\t' || c.publication_sequence::text || E'\\t' ||
       d.canonical_generation_id::text || E'\\t' || d.canonical_publication_sequence::text || E'\\t' ||
       (d.manifest->>'canonical_schema')
  FROM v3_meta.current_canonical_generation c
  JOIN v3_meta.derived_generation d
    ON d.generation_key='${DERIVED_KEY}'
 WHERE c.singleton;
COMMIT;")"
[ "$(printf '%s\n' "$authority" | wc -l)" -eq 1 ] || fail "production generation authority is missing or ambiguous"
IFS=$'\t' read -r current_canonical current_sequence derived_canonical derived_sequence derived_schema <<< "$authority"
[ "$current_canonical" = "$CANONICAL_GENERATION" ] || fail "current canonical generation changed"
[ "$current_sequence" = "$CANONICAL_SEQUENCE" ] || fail "current canonical publication sequence changed"
[ "$derived_canonical" = "$CANONICAL_GENERATION" ] || fail "derived generation canonical identity changed"
[ "$derived_sequence" = "$CANONICAL_SEQUENCE" ] || fail "derived generation canonical sequence changed"
[ "$derived_schema" = "$CANONICAL_SCHEMA" ] || fail "derived generation canonical schema changed"

relation_count="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT count(*)
  FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='${CANONICAL_SCHEMA}'
   AND c.relname='bodies'
   AND c.relkind='r';
COMMIT;")"
[ "$relation_count" = "1" ] || fail "canonical bodies relation is missing or ambiguous"

stats_json() {
  "${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT json_build_object(
  'relation_reltuples',c.reltuples::bigint,
  'statistics_target',a.attstattarget,
  'attribute_options',a.attoptions,
  'n_distinct',s.n_distinct,
  'implied_distinct',CASE
      WHEN s.n_distinct IS NULL THEN NULL
      WHEN s.n_distinct < 0 THEN round((-s.n_distinct * c.reltuples)::numeric)
      ELSE round(s.n_distinct::numeric)
    END,
  'implied_rows_per_system',CASE
      WHEN s.n_distinct IS NULL OR s.n_distinct=0 THEN NULL
      WHEN s.n_distinct < 0 THEN round((1 / -s.n_distinct)::numeric,2)
      ELSE round((c.reltuples / s.n_distinct)::numeric,2)
    END,
  'last_analyze',st.last_analyze,
  'last_autoanalyze',st.last_autoanalyze
)::text
  FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='system_id64' AND a.attnum>0 AND NOT a.attisdropped
  LEFT JOIN pg_stats s ON s.schemaname=n.nspname AND s.tablename=c.relname AND s.attname=a.attname
  LEFT JOIN pg_stat_all_tables st ON st.relid=c.oid
 WHERE n.nspname='${CANONICAL_SCHEMA}' AND c.relname='bodies';
COMMIT;"
}

printf 'operation=v3-system-search-f1-tune-systemid-stats\n'
printf 'canonical_generation=%s\n' "$CANONICAL_GENERATION"
printf 'canonical_sequence=%s\n' "$CANONICAL_SEQUENCE"
printf 'canonical_schema=%s\n' "$CANONICAL_SCHEMA"
printf 'statistics_target=%s\n' "$STATISTICS_TARGET"
printf 'n_distinct_override=%s\n' "$N_DISTINCT_OVERRIDE"
printf 'before_stats=%s\n' "$(stats_json)"

docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
  --set ON_ERROR_STOP=1 --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
SET statement_timeout='15min';
SET lock_timeout='5s';
ALTER TABLE ${CANONICAL_SCHEMA}.bodies
  ALTER COLUMN system_id64 SET STATISTICS ${STATISTICS_TARGET};
ALTER TABLE ${CANONICAL_SCHEMA}.bodies
  ALTER COLUMN system_id64 SET (n_distinct = ${N_DISTINCT_OVERRIDE});
ANALYZE ${CANONICAL_SCHEMA}.bodies (system_id64);
SQL

printf 'after_stats=%s\n' "$(stats_json)"

verification="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT a.attstattarget::text || E'\\t' ||
       COALESCE(s.n_distinct::text,'') || E'\\t' ||
       (COALESCE(s.n_distinct,0)=-0.1)::int::text || E'\\t' ||
       (st.last_analyze IS NOT NULL)::int::text
  FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='system_id64' AND a.attnum>0 AND NOT a.attisdropped
  LEFT JOIN pg_stats s ON s.schemaname=n.nspname AND s.tablename=c.relname AND s.attname=a.attname
  LEFT JOIN pg_stat_all_tables st ON st.relid=c.oid
 WHERE n.nspname='${CANONICAL_SCHEMA}' AND c.relname='bodies';
COMMIT;")"
IFS=$'\t' read -r observed_target observed_n_distinct override_applied analyzed <<< "$verification"
[ "$observed_target" = "$STATISTICS_TARGET" ] || fail "system_id64 statistics target was not applied"
[ -n "$observed_n_distinct" ] || fail "system_id64 n_distinct is missing after ANALYZE"
[ "$override_applied" = "1" ] || fail "system_id64 n_distinct override was not applied"
[ "$analyzed" = "1" ] || fail "bodies ANALYZE receipt was not visible"

printf 'result=planner-systemid-statistics-tuned\n'
printf 'planner_statistics_updated=true\n'
printf 'planner_metadata_changes_performed=true\n'
printf 'canonical_row_writes_performed=false\n'
printf 'application_data_writes_performed=false\n'
printf 'publication_performed=false\n'
printf 'application_service_changes_performed=false\n'
