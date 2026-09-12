#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-}"
SOURCE_SHA="${2:-}"

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
APPLICATION_NETWORK="edfinder-v3-production"
OPERATION_LABEL="ed-finder.operation=ratings-v4-generation"
STATE_ROOT="${HOME}/.local/state/ed-finder/ratings-v4"
TARGET_CPUS="16"
TARGET_MEMORY="64g"
TARGET_WORKERS="8"
TARGET_CHUNK_SIZE="1000"
MIN_PROOF_CHUNKS="2"

fail() {
  printf 'ratings-v4 optimize: %s\n' "$*" >&2
  exit 64
}

require_target() {
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
  [ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
  [ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
  [ "$(docker context show)" = "default" ] || fail "unexpected docker context"
  docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
    || fail "default docker context is not the local rootful socket"
  docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || fail "retained postgres container is unavailable"
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER")" = "true" ] \
    || fail "retained postgres container is not running"
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

active_api_container() {
  local -a matches=()
  local container service
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")"
    case "$service" in
      api-*) matches+=("$container") ;;
    esac
  done < <(docker ps --filter "label=com.docker.compose.project=${APPLICATION_NETWORK}" --format '{{.Names}}')
  [ "${#matches[@]}" -eq 1 ] || fail "expected exactly one running production API slot, found ${#matches[@]}"
  printf '%s\n' "${matches[0]}"
}

api_database_url() {
  local api="$1" value count
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')"
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || fail "active API does not expose exactly one DATABASE_URL"
  case "$value" in
    postgresql://*|postgres://*) ;;
    *) fail "active API DATABASE_URL is not a PostgreSQL DSN" ;;
  esac
  printf '%s' "$value"
}

source_metadata() {
  db_query "BEGIN READ ONLY; SELECT c.publication_sequence::text || E'\\t' || g.generation_id::text || E'\\t' || a.size_bytes::text || E'\\t' || encode(a.content_sha256,'hex') || E'\\t' || a.storage_locator FROM v3_meta.current_canonical_generation c JOIN v3_meta.canonical_generation g USING(generation_id) JOIN v3_source.source_run r ON r.source_run_id=g.build_source_run_id JOIN v3_source.source_artifact a ON a.artifact_id=r.artifact_id WHERE g.lifecycle_state='PUBLISHED'; COMMIT;"
}

resolve_source_path() {
  local locator="$1" expected_size="$2"
  local -a candidates=()
  local id src dst rel candidate root base actual_size

  case "$locator" in
    /*) ;;
    *) fail "canonical artifact storage locator is not an absolute path" ;;
  esac
  [[ "$locator" != *$'\n'* && "$locator" != *$'\r'* && "$locator" != *:* ]] \
    || fail "canonical artifact storage locator is unsafe"

  if [ -f "$locator" ] && [ ! -L "$locator" ]; then
    actual_size="$(stat -c '%s' "$locator")"
    [ "$actual_size" = "$expected_size" ] && candidates+=("$locator")
  fi

  while IFS= read -r id; do
    [ -n "$id" ] || continue
    while IFS=$'\t' read -r src dst; do
      [ -n "$src" ] && [ -n "$dst" ] || continue
      if [ "$locator" = "$dst" ]; then
        candidate="$src"
      elif [[ "$locator" == "$dst/"* ]]; then
        rel="${locator#"$dst"}"
        candidate="${src}${rel}"
      else
        continue
      fi
      if [ -f "$candidate" ] && [ ! -L "$candidate" ] && [ "$(stat -c '%s' "$candidate")" = "$expected_size" ]; then
        candidates+=("$candidate")
      fi
    done < <(docker inspect -f '{{range .Mounts}}{{printf "%s\t%s\n" .Source .Destination}}{{end}}' "$id")
  done < <(docker ps -aq)

  if [ "${#candidates[@]}" -eq 0 ]; then
    base="$(basename "$locator")"
    for root in /data /srv /opt "$HOME"; do
      [ -d "$root" ] || continue
      while IFS= read -r candidate; do
        [ -n "$candidate" ] && candidates+=("$candidate")
      done < <(find "$root" -xdev -type f -name "$base" -size "${expected_size}c" -print 2>/dev/null)
    done
  fi

  mapfile -t candidates < <(printf '%s\n' "${candidates[@]}" | awk 'NF && !seen[$0]++')
  [ "${#candidates[@]}" -eq 1 ] \
    || fail "expected exactly one retained canonical artifact with the reviewed size, found ${#candidates[@]}"
  printf '%s\n' "${candidates[0]}"
}

require_target
[ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
case "$REPO_ROOT" in
  /var/tmp/edfinder-ratings-v4-"$SOURCE_SHA") ;;
  *) fail "trusted main bundle path is outside the reviewed staging namespace" ;;
esac
[ "$(cat "$REPO_ROOT/.ratings-v4-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
  || fail "trusted main bundle SHA marker mismatch"
[ -f "$REPO_ROOT/scripts/ratings_v4/run_generation.py" ] || fail "generation runner is missing"
[ -f "$REPO_ROOT/scripts/ratings_v4/production_generation.py" ] || fail "generation builder is missing"
[ -d "$REPO_ROOT/.ratings-v4-wheelhouse" ] || fail "offline dependency wheelhouse is missing"

grep -F "--workers" "$REPO_ROOT/scripts/ratings_v4/run_generation.py" >/dev/null \
  || fail "trusted runner has no parallel worker contract"

install -d -m 700 "$STATE_ROOT"
command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
exec 9>"$STATE_ROOT/start.lock"
flock -n 9 || fail "another Ratings V4 generation operation is in progress"

metadata="$(source_metadata)"
[ "$(printf '%s\n' "$metadata" | wc -l)" -eq 1 ] || fail "canonical source metadata is ambiguous"
IFS=$'\t' read -r sequence canonical_generation expected_size expected_sha storage_locator <<< "$metadata"
[[ "$sequence" =~ ^[1-9][0-9]*$ ]] || fail "canonical publication sequence is invalid"
[[ "$canonical_generation" =~ ^[0-9a-f-]{36}$ ]] || fail "canonical generation id is invalid"
[[ "$expected_size" =~ ^[1-9][0-9]*$ ]] || fail "canonical artifact size is invalid"
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || fail "canonical artifact sha256 is invalid"
[ -n "$storage_locator" ] || fail "canonical artifact storage locator is empty"

source_path="$(resolve_source_path "$storage_locator" "$expected_size")"
old_generation_key="ratings_v4_prod_p${sequence}"
old_worker="edfinder-ratings-v4-prod-p${sequence}"
new_generation_key="ratings_v4_prod_p${sequence}_opt1"
new_worker="edfinder-ratings-v4-prod-p${sequence}-opt1"

# The original container is the rollback path. It may be running (first cutover)
# or stopped (idempotent retry), but it must never be removed by this operation.
docker inspect "$old_worker" >/dev/null 2>&1 || fail "original Ratings V4 worker is unavailable for rollback"
old_key_label="$(docker inspect -f '{{index .Config.Labels "ed-finder.generation-key"}}' "$old_worker")"
[ "$old_key_label" = "$old_generation_key" ] || fail "original worker generation identity mismatch"

api="$(active_api_container)"
api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
[ -n "$api_image" ] || fail "active API image identity is empty"
dsn="$(api_database_url "$api")"

if docker inspect "$new_worker" >/dev/null 2>&1; then
  new_state="$(docker inspect -f '{{.State.Status}}' "$new_worker")"
  if [ "$new_state" != "running" ]; then
    docker rm "$new_worker" >/dev/null
  fi
fi

if ! docker inspect "$new_worker" >/dev/null 2>&1; then
  env_file="$STATE_ROOT/${new_generation_key}.env"
  umask 077
  {
    printf 'RATINGS_V4_CANONICAL_DATABASE_URL=%s\n' "$dsn"
    printf 'RATINGS_V4_DERIVED_DATABASE_URL=%s\n' "$dsn"
    printf 'RATINGS_V4_SOURCE=/source/galaxy.json.gz\n'
    printf 'RATINGS_V4_GENERATION_KEY=%s\n' "$new_generation_key"
  } > "$env_file"
  chmod 600 "$env_file"

  docker run -d \
    --name "$new_worker" \
    --label "$OPERATION_LABEL" \
    --label "ed-finder.generation-key=${new_generation_key}" \
    --label "ed-finder.source-sha=${SOURCE_SHA}" \
    --label "ed-finder.optimization=parallel-encoding-v1" \
    --network "$APPLICATION_NETWORK" \
    --cpus "$TARGET_CPUS" \
    --memory "$TARGET_MEMORY" \
    --memory-swap "$TARGET_MEMORY" \
    --pids-limit 512 \
    --restart no \
    --log-driver json-file \
    --log-opt max-size=20m \
    --log-opt max-file=3 \
    --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --mount "type=bind,src=${source_path},dst=/source/galaxy.json.gz,readonly" \
    --entrypoint /bin/sh \
    "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --disable-pip-version-check --no-input --no-index \
        --find-links /work/.ratings-v4-wheelhouse --target /tmp/ratings-v4-deps \
        "psycopg[binary]==3.3.4" "ijson==3.5.1"
      export PYTHONPATH="/tmp/ratings-v4-deps:/work:/work/apps/api/src"
      cd /work
      /app/.venv/bin/python scripts/ratings_v4/verify_freeze.py >/tmp/ratings-v4-freeze-receipt.json
      exec /app/.venv/bin/python scripts/ratings_v4/run_generation.py \
        --source "$RATINGS_V4_SOURCE" \
        --generation-key "$RATINGS_V4_GENERATION_KEY" \
        --chunk-size 1000 \
        --workers 8
    ' >/dev/null
  rm -f "$env_file"
fi

# Prove the new immutable generation is genuinely committing chunks before the
# original worker is stopped. A failed proof leaves the original worker alone.
proof_chunks=0
for _ in $(seq 1 45); do
  [ "$(docker inspect -f '{{.State.Running}}' "$new_worker" 2>/dev/null || true)" = "true" ] \
    || { docker logs --tail 80 "$new_worker" >&2 || true; fail "optimized worker exited before cutover proof"; }
  proof_chunks="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.build_chunk b JOIN v3_meta.derived_generation g USING(derived_generation_id) WHERE g.generation_key='${new_generation_key}'; COMMIT;")"
  [[ "$proof_chunks" =~ ^[0-9]+$ ]] || fail "optimized generation proof query was invalid"
  if [ "$proof_chunks" -ge "$MIN_PROOF_CHUNKS" ]; then
    break
  fi
  sleep 2
done
[ "$proof_chunks" -ge "$MIN_PROOF_CHUNKS" ] || fail "optimized worker did not prove chunk progress"

old_was_running="$(docker inspect -f '{{.State.Running}}' "$old_worker")"
if [ "$old_was_running" = "true" ]; then
  docker stop --time 30 "$old_worker" >/dev/null
fi
[ "$(docker inspect -f '{{.State.Running}}' "$new_worker")" = "true" ] || fail "optimized worker stopped during cutover"
[ "$(docker inspect -f '{{.State.Running}}' "$old_worker")" = "false" ] || fail "original worker did not stop"

printf 'operation=ratings-v4-generation-optimize\n'
printf 'result=optimized-worker-proven-and-cut-over\n'
printf 'source_sha=%s\n' "$SOURCE_SHA"
printf 'canonical_generation_id=%s\n' "$canonical_generation"
printf 'canonical_publication_sequence=%s\n' "$sequence"
printf 'source_artifact_sha256=%s\n' "$expected_sha"
printf 'new_generation_key=%s\n' "$new_generation_key"
printf 'new_worker=%s\n' "$new_worker"
printf 'proof_chunks=%s\n' "$proof_chunks"
printf 'chunk_size=%s\n' "$TARGET_CHUNK_SIZE"
printf 'encoder_workers=%s\n' "$TARGET_WORKERS"
printf 'cpu_limit=%s\n' "$TARGET_CPUS"
printf 'memory_limit=%s\n' "$TARGET_MEMORY"
printf 'new_worker_running=true\n'
printf 'old_worker=%s\n' "$old_worker"
printf 'old_worker_was_running=%s\n' "$old_was_running"
printf 'old_worker_retained=true\n'
printf 'old_worker_running=false\n'
printf 'publication_performed=false\n'
printf 'migrations_performed=false\n'
printf 'canonical_writes_performed=false\n'
printf 'old_generation_deleted=false\n'
printf 'new_generation_published=false\n'
printf 'latest_new_worker_log_tail:\n'
docker logs --tail 20 "$new_worker" 2>&1 | sed 's/^/  /' || true
