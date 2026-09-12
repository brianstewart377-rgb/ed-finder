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

# This template must be rendered on the runner from trusted main first.
# Query bodies are fixed code; only validated generation/schema/ordinal vary.
legacy_query() {
  cat <<SQL
__SEARCH_LEGACY_SQL__
SQL
}

candidate_query() {
  cat <<SQL
__SEARCH_CANDIDATE_SQL__
SQL
}

meta="$("${psql_base[@]}" --command "BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT g.derived_generation_id::text || E'\\t' ||
       (g.manifest->>'canonical_schema') || E'\\t' ||
       COALESCE((SELECT max(b.chunk_ordinal)::text
                   FROM v3_derived.build_chunk b
                  WHERE b.derived_generation_id=g.derived_generation_id),'') || E'\\t' ||
       COALESCE((SELECT min(b.chunk_ordinal)::text
                   FROM v3_derived.build_chunk b
                  WHERE b.derived_generation_id=g.derived_generation_id
                    AND NOT EXISTS (
                        SELECT 1 FROM v3_derived.search_build_chunk s
                         WHERE s.derived_generation_id=b.derived_generation_id
                           AND s.chunk_ordinal=b.chunk_ordinal)),'caught_up')
  FROM v3_meta.derived_generation g
 WHERE g.generation_key='${TARGET_GENERATION_KEY}';
COMMIT;")"
[ "$(printf '%s\n' "$meta" | wc -l)" -eq 1 ] || fail "target generation metadata is missing or ambiguous"
IFS=$'\t' read -r generation_id canonical_schema ratings_tip search_frontier <<< "$meta"
[[ "$generation_id" =~ ^[0-9a-f-]{36}$ ]] || fail "derived generation id is invalid"
[[ "$canonical_schema" =~ ^v3_gen_[a-z0-9_]{1,31}$ ]] || fail "canonical schema is invalid"
[[ "$ratings_tip" =~ ^[0-9]+$ ]] || fail "Ratings tip ordinal is invalid"
[[ "$search_frontier" =~ ^[0-9]+$ || "$search_frontier" = caught_up ]] || fail "Search frontier ordinal is invalid"

printf 'operation=v3-system-search-f1-profile\n'
printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
printf 'derived_generation_id=%s\n' "$generation_id"
printf 'canonical_schema=%s\n' "$canonical_schema"
printf 'ratings_tip_chunk_ordinal=%s\n' "$ratings_tip"
printf 'search_frontier_chunk_ordinal=%s\n' "$search_frontier"
printf 'profile_started_at=%s\n' "$(date -u +%FT%TZ)"

run_cohort() {
  local cohort="$1" chunk_ordinal="$2" legacy candidate
  legacy="$(legacy_query)"
  candidate="$(candidate_query)"
  [[ "$legacy" != *__SEARCH_* && "$candidate" != *__SEARCH_* ]] \
    || fail "profile template was not rendered"
  printf 'profile_cohort=%s\nprofile_chunk_ordinal=%s\n' "$cohort" "$chunk_ordinal"
  docker exec -i "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" <<SQL
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='60s';
\\echo full_query_variant=baseline
\\echo select_plan_json=
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
${legacy};
SET LOCAL jit=off;
\\echo full_query_variant=jit_off
\\echo jit_off_select_plan_json=
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
${legacy};
SET LOCAL enable_seqscan=off;
\\echo full_query_variant=indexed_no_seqscan
\\echo indexed_select_plan_json=
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
${legacy};
SET LOCAL enable_seqscan=DEFAULT;
SET LOCAL jit=DEFAULT;
\\echo full_query_variant=candidate_default
\\echo candidate_select_plan_json=
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
${candidate};
SET LOCAL jit=off;
\\echo full_query_variant=candidate_jit_off
\\echo candidate_jit_off_select_plan_json=
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, SUMMARY, FORMAT JSON)
${candidate};
SET LOCAL jit=DEFAULT;
WITH baseline AS MATERIALIZED (${legacy}),
     candidate AS MATERIALIZED (${candidate}),
     differences AS (
         (SELECT * FROM baseline EXCEPT ALL SELECT * FROM candidate)
         UNION ALL
         (SELECT * FROM candidate EXCEPT ALL SELECT * FROM baseline)
     ),
     counts AS (
         SELECT (SELECT count(*) FROM baseline) AS baseline_rows,
                (SELECT count(*) FROM candidate) AS candidate_rows,
                (SELECT count(*) FROM differences) AS different_rows,
                (SELECT systems FROM v3_derived.build_chunk
                  WHERE derived_generation_id='${generation_id}'::uuid
                    AND chunk_ordinal=${chunk_ordinal}) AS expected_rows
     )
SELECT *, (different_rows=0 AND baseline_rows=expected_rows
                           AND candidate_rows=expected_rows
                           AND expected_rows>0) AS equivalent
  FROM counts
\\gset comparison_
\\echo comparison_baseline_rows=:comparison_baseline_rows
\\echo comparison_candidate_rows=:comparison_candidate_rows
\\echo comparison_expected_rows=:comparison_expected_rows
\\echo comparison_different_rows=:comparison_different_rows
\\echo comparison_equivalent=:comparison_equivalent
\\if :comparison_equivalent
\\else
\\echo ERROR: Search projection equivalence or coverage failed
\\quit 3
\\endif
ROLLBACK;
SQL
}

if [ "$search_frontier" != caught_up ]; then
  run_cohort search_frontier "$search_frontier"
else
  printf 'search_frontier_skipped=already_caught_up\n'
fi
run_cohort ratings_tip "$ratings_tip"

printf 'profile_finished_at=%s\n' "$(date -u +%FT%TZ)"
printf 'database_writes_performed=false\n'
printf 'schema_changes_performed=false\n'
printf 'publication_performed=false\n'
printf 'canonical_writes_performed=false\n'
printf 'application_service_changes_performed=false\n'
