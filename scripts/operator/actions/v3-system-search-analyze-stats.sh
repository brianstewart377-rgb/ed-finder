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

fail() {
  printf 'v3 system search analyze stats: %s\n' "$*" >&2
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

for relation in bodies body_signal_current; do
  exists="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='${CANONICAL_SCHEMA}' AND c.relname='${relation}' AND c.relkind='r';
COMMIT;")"
  [ "$exists" = "1" ] || fail "required canonical relation ${relation} is missing or ambiguous"
done

stats_json() {
  "${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT json_agg(row_to_json(q) ORDER BY q.relation)::text
FROM (
  SELECT s.relname AS relation,
         s.n_live_tup,
         s.last_analyze,
         s.last_autoanalyze,
         c.reltuples::bigint AS reltuples,
         pg_relation_size(c.oid) AS table_bytes,
         pg_total_relation_size(c.oid) AS total_bytes
    FROM pg_stat_all_tables s
    JOIN pg_class c ON c.oid=s.relid
   WHERE s.schemaname='${CANONICAL_SCHEMA}'
     AND s.relname IN ('bodies','body_signal_current')
) q;
COMMIT;"
}

printf 'operation=v3-system-search-f1-analyze-stats\n'
printf 'canonical_generation=%s\n' "$CANONICAL_GENERATION"
printf 'canonical_sequence=%s\n' "$CANONICAL_SEQUENCE"
printf 'canonical_schema=%s\n' "$CANONICAL_SCHEMA"
printf 'before_stats=%s\n' "$(stats_json)"

# ANALYZE updates planner statistics/catalog metadata only. The canonical tables
# are immutable inputs here: this operation performs no INSERT/UPDATE/DELETE and
# changes no application rows, constraints, indexes, services or publication.
docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
  --set ON_ERROR_STOP=1 --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
SET statement_timeout='15min';
SET lock_timeout='5s';
ANALYZE ${CANONICAL_SCHEMA}.bodies (system_id64, lifecycle_state, is_landable, terraforming_state_id);
ANALYZE ${CANONICAL_SCHEMA}.body_signal_current (body_pk, signal_type_id, signal_count);
SQL

after="$(stats_json)"
printf 'after_stats=%s\n' "$after"

verification="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT
  (SELECT (last_analyze IS NOT NULL)::int FROM pg_stat_all_tables
    WHERE schemaname='${CANONICAL_SCHEMA}' AND relname='bodies') || E'\\t' ||
  (SELECT (last_analyze IS NOT NULL)::int FROM pg_stat_all_tables
    WHERE schemaname='${CANONICAL_SCHEMA}' AND relname='body_signal_current') || E'\\t' ||
  (SELECT count(*) FROM pg_stats
    WHERE schemaname='${CANONICAL_SCHEMA}' AND tablename='bodies'
      AND attname IN ('system_id64','lifecycle_state','is_landable','terraforming_state_id')) || E'\\t' ||
  (SELECT count(*) FROM pg_stats
    WHERE schemaname='${CANONICAL_SCHEMA}' AND tablename='body_signal_current'
      AND attname IN ('body_pk','signal_type_id','signal_count'));
COMMIT;")"
IFS=$'\t' read -r bodies_analyzed signals_analyzed bodies_stats_cols signal_stats_cols <<< "$verification"
[ "$bodies_analyzed" = "1" ] || fail "bodies ANALYZE receipt was not visible"
[ "$signals_analyzed" = "1" ] || fail "body_signal_current ANALYZE receipt was not visible"
[ "$bodies_stats_cols" = "4" ] || fail "bodies planner statistics are incomplete"
[ "$signal_stats_cols" = "3" ] || fail "body_signal_current planner statistics are incomplete"

printf 'result=planner-statistics-refreshed\n'
printf 'planner_statistics_updated=true\n'
printf 'canonical_row_writes_performed=false\n'
printf 'application_data_writes_performed=false\n'
printf 'schema_changes_performed=false\n'
printf 'publication_performed=false\n'
printf 'application_service_changes_performed=false\n'
