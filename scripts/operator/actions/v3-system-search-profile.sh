#!/usr/bin/env bash
set -euo pipefail

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"

fail() {
  printf 'v3 system search profile: %s\n' "$*" >&2
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

meta="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT g.derived_generation_id::text || E'\\t' ||
       (g.manifest->>'canonical_schema') || E'\\t' ||
       COALESCE((SELECT max(b.chunk_ordinal)::text
                   FROM v3_derived.build_chunk b
                  WHERE b.derived_generation_id=g.derived_generation_id),'')
  FROM v3_meta.derived_generation g
 WHERE g.generation_key='${TARGET_GENERATION_KEY}';
COMMIT;")"
[ "$(printf '%s\n' "$meta" | wc -l)" -eq 1 ] || fail "target generation metadata is missing or ambiguous"
IFS=$'\t' read -r generation_id canonical_schema chunk_ordinal <<< "$meta"
[[ "$generation_id" =~ ^[0-9a-f-]{36}$ ]] || fail "derived generation id is invalid"
[[ "$canonical_schema" =~ ^v3_gen_[a-z0-9_]{1,31}$ ]] || fail "canonical schema is invalid"
[[ "$chunk_ordinal" =~ ^[0-9]+$ ]] || fail "profile chunk ordinal is invalid"

printf 'operation=v3-system-search-f1-profile\n'
printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
printf 'derived_generation_id=%s\n' "$generation_id"
printf 'canonical_schema=%s\n' "$canonical_schema"
printf 'profile_chunk_ordinal=%s\n' "$chunk_ordinal"
printf 'latest_status='
"${psql_base[@]}" --command "BEGIN READ ONLY;
SELECT json_build_object(
  'ratings_completed_chunks',(SELECT count(*) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
  'ratings_completed_systems',(SELECT COALESCE(sum(b.systems),0) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
  'search_completed_chunks',(SELECT count(*) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
  'search_completed_systems',(SELECT COALESCE(sum(s.systems),0) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
  'search_rows',(SELECT count(*) FROM v3_derived.system_search s WHERE s.derived_generation_id=g.derived_generation_id)
)::text
FROM v3_meta.derived_generation g
WHERE g.derived_generation_id='${generation_id}'::uuid;
COMMIT;"

run_full_query_variant() {
  local label="$1" settings="$2" plan_key="$3"
  printf 'full_query_variant=%s\n' "$label"
  printf '%s=\n' "$plan_key"
  docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
${settings}
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
WITH target AS MATERIALIZED (
    SELECT v.system_id64,v.loaded_body_count,v.completeness,v.confidence
      FROM v3_derived.system_rating_vector v
     WHERE v.derived_generation_id='${generation_id}'::uuid
       AND v.chunk_ordinal=${chunk_ordinal}
),
body_summary AS (
    SELECT b.system_id64,
           (count(*) FILTER (
               WHERE b.lifecycle_state='ACTIVE' AND b.is_landable IS TRUE
           ))::integer AS landable_count,
           bool_or(
               b.lifecycle_state='ACTIVE'
               AND ts.public_code IN ('terraformable','terraformed','terraforming')
           ) AS has_terraformable
      FROM ${canonical_schema}.bodies b
      JOIN target t ON t.system_id64=b.system_id64
 LEFT JOIN v3_vocab.terraforming_state ts
        ON ts.terraforming_state_id=b.terraforming_state_id
  GROUP BY b.system_id64
),
ring_summary AS (
    SELECT r.system_id64,true AS has_rings
      FROM ${canonical_schema}.rings r
      JOIN target t ON t.system_id64=r.system_id64
     WHERE r.lifecycle_state='ACTIVE' AND r.kind='RING'
  GROUP BY r.system_id64
),
signal_summary AS (
    SELECT b.system_id64,
           bool_or(st.public_code='saa_signaltype_biological'
                   AND bs.signal_count>0) AS has_biologicals,
           bool_or(st.public_code='saa_signaltype_geological'
                   AND bs.signal_count>0) AS has_geologicals
      FROM ${canonical_schema}.body_signal_current bs
      JOIN ${canonical_schema}.bodies b ON b.body_pk=bs.body_pk
      JOIN target t ON t.system_id64=b.system_id64
      JOIN v3_vocab.signal_type st ON st.signal_type_id=bs.signal_type_id
     WHERE b.lifecycle_state='ACTIVE'
  GROUP BY b.system_id64
),
station_summary AS (
    SELECT st.system_id64,
           (count(*) FILTER (WHERE st.lifecycle_state='ACTIVE'))::integer AS station_count
      FROM ${canonical_schema}.stations st
      JOIN target t ON t.system_id64=st.system_id64
  GROUP BY st.system_id64
),
main_star AS (
    SELECT DISTINCT ON (bm.system_id64)
           bm.system_id64,bm.body_class AS main_star_class
      FROM v3_derived.body_mechanics bm
      JOIN target t ON t.system_id64=bm.system_id64
     WHERE bm.derived_generation_id='${generation_id}'::uuid
       AND bm.is_main_star IS TRUE
  ORDER BY bm.system_id64,bm.body_pk
)
SELECT t.system_id64,s.name,s.x_ly,s.y_ly,s.z_ly,
       cube(ARRAY[s.x_ly,s.y_ly,s.z_ly]),
       s.galaxy_region_id,gr.display_name,ms.main_star_class,
       t.loaded_body_count,COALESCE(bs.landable_count,0),
       COALESCE(ss.station_count,0),COALESCE(rs.has_rings,false),
       COALESCE(sig.has_biologicals,false),
       COALESCE(sig.has_geologicals,false),
       COALESCE(bs.has_terraformable,false),
       s.source_updated_at,
       (SELECT min(value)::double precision/10000 FROM unnest(t.completeness) AS value),
       (SELECT min(value)::double precision/10000 FROM unnest(t.confidence) AS value)
  FROM target t
  JOIN ${canonical_schema}.systems s ON s.id64=t.system_id64
 LEFT JOIN v3_vocab.galaxy_region gr ON gr.galaxy_region_id=s.galaxy_region_id
 LEFT JOIN body_summary bs USING(system_id64)
 LEFT JOIN ring_summary rs USING(system_id64)
 LEFT JOIN signal_summary sig USING(system_id64)
 LEFT JOIN station_summary ss USING(system_id64)
 LEFT JOIN main_star ms USING(system_id64)
 ORDER BY t.system_id64;
ROLLBACK;
SQL
}

run_full_query_variant baseline "" select_plan_json
run_full_query_variant jit_off "SET LOCAL jit=off;" jit_off_select_plan_json
run_full_query_variant indexed_no_seqscan \
  "SET LOCAL jit=off; SET LOCAL enable_seqscan=off;" \
  indexed_select_plan_json

printf 'database_writes_performed=false\n'
printf 'schema_changes_performed=false\n'
printf 'publication_performed=false\n'
printf 'canonical_writes_performed=false\n'
printf 'application_service_changes_performed=false\n'
