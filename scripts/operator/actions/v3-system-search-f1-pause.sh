# Bounded pause for the V3 Search F1 follower.
#
# This is a reviewed, reversible lever for relieving load on the retained
# production database while the Ratings V4 generation is VALIDATING. The Search
# follower keeps building chunks over the same derived relations, so it contends
# with the replaying validator for buffers, IO and CPU.
#
# It is not a fix for validation cost. The validator's own replay is dominated by
# its chunk reads, and the running generation cannot change code: its manifest
# pins the identity of the code replaying it, and the plan of its semi-join is
# unaffected by disabling parallelism (measured read-only on the retained
# database, 2026-09-13). Expect contention relief only, not a faster replay, and
# weigh it against the Search build progress this stops.
#
# The operation only stops the worker. It never removes the container, so logs
# stay available for inspection, and it never touches canonical, ratings or
# Search rows. Chunk writes are single transactions (scripts/v3_system_search.py
# commits the Search rows and the chunk receipt together), so an interrupted
# chunk rolls back whole and is rebuilt on resume; no committed progress is lost.
# Resume with the reviewed v3-system-search-f1-start operation, which removes the
# stopped container and relaunches the same generation.

ACTION="${1:-}"

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_opt1"
WORKER="edfinder-v3-system-search-p4-opt1"
OPERATION_LABEL="ed-finder.operation=v3-system-search-f1"
STOP_GRACE_SECONDS="60"

fail() {
  printf 'v3 system search f1 pause: %s\n' "$*" >&2
  exit 64
}

require_target() {
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
  [ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
  [ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
  [ "$(docker context show)" = "default" ] || fail "unexpected docker context"
  docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
    || fail "default docker context is not the local rootful socket"
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)" = "true" ] \
    || fail "retained postgres container is not running"
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

require_single_running_worker() {
  local -a workers=()
  local container
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    workers+=("$container")
  done < <(docker ps --filter "label=${OPERATION_LABEL}" --format '{{.Names}}')
  [ "${#workers[@]}" -eq 1 ] || fail "expected exactly one running V3 Search worker, found ${#workers[@]}"
  [ "${workers[0]}" = "$WORKER" ] || fail "unexpected V3 Search worker name"
  [ "$(docker inspect -f '{{index .Config.Labels "ed-finder.generation-key"}}' "$WORKER")" \
      = "$TARGET_GENERATION_KEY" ] || fail "worker generation label mismatch"
}

# Committed Search progress: how many chunk receipts exist and the highest
# chunk ordinal. Pausing must never reduce either.
committed_frontier() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(count(*),0)::text || E'\\t' || COALESCE(max(s.chunk_ordinal),-1)::text
    FROM v3_derived.search_build_chunk s
    JOIN v3_meta.derived_generation g USING(derived_generation_id)
   WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;"
}

ratings_state() {
  db_query "BEGIN READ ONLY; SELECT lifecycle_state FROM v3_meta.derived_generation
   WHERE generation_key='${TARGET_GENERATION_KEY}'; COMMIT;"
}

pause_operation() {
  require_target
  require_single_running_worker

  local before after before_count before_frontier after_count after_frontier state
  before="$(committed_frontier)"
  IFS=$'\t' read -r before_count before_frontier <<< "$before"
  [[ "$before_count" =~ ^[0-9]+$ ]] || fail "committed Search frontier query was invalid"
  state="$(ratings_state)"

  docker stop --time "$STOP_GRACE_SECONDS" "$WORKER" >/dev/null
  [ "$(docker inspect -f '{{.State.Running}}' "$WORKER")" = "false" ] || fail "worker did not stop"

  after="$(committed_frontier)"
  IFS=$'\t' read -r after_count after_frontier <<< "$after"
  [[ "$after_count" =~ ^[0-9]+$ ]] || fail "committed Search frontier query was invalid"
  [ "$after_count" -ge "$before_count" ] || fail "committed Search progress regressed while pausing"

  printf 'operation=v3-system-search-f1-pause\n'
  printf 'result=stopped\n'
  printf 'generation_key=%s\n' "$TARGET_GENERATION_KEY"
  printf 'ratings_lifecycle_state=%s\n' "$state"
  printf 'worker=%s\n' "$WORKER"
  printf 'worker_removed=false\n'
  printf 'stop_grace_seconds=%s\n' "$STOP_GRACE_SECONDS"
  printf 'committed_chunks_before=%s\n' "$before_count"
  printf 'committed_chunk_frontier_before=%s\n' "$before_frontier"
  printf 'committed_chunks_after=%s\n' "$after_count"
  printf 'committed_chunk_frontier_after=%s\n' "$after_frontier"
  printf 'committed_progress_preserved=true\n'
  printf 'resume_operation=v3-system-search-f1-start\n'
  printf 'publication_performed=false\n'
  printf 'canonical_writes_performed=false\n'
  printf 'application_service_changes_performed=false\n'
}

case "$ACTION" in
  pause) pause_operation ;;
  *) fail "expected pause" ;;
esac