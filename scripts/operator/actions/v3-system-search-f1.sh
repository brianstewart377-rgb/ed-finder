#!/usr/bin/env bash
# Governed Search build for the pinned published parallel_v1 Ratings generation.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

# The receipt emitter precedes every refusal, including the identity
# preflight, so each stop prints a stopped operation-result line on stdout:
# the workflow records stdout only, and a reason that went to stderr alone was
# invisible in the downloadable receipt.
CURRENT_OPERATION="v3-system-search-f1"
if [[ "$ACTION" =~ ^(start|status|finalize)$ ]]; then
  CURRENT_OPERATION="v3-system-search-f1-$ACTION"
fi
# Mutation state for the stopped receipt. "false" until this invocation may
# have changed the database (a worker launched by it, or VACUUM started);
# "unknown" afterwards, because a refusal cannot prove what the worker or
# VACUUM committed before the stop.
DB_WRITES_STATE="false"
mark_db_writes_possible() { DB_WRITES_STATE="unknown"; }

fail() {
  local reason="$*" writes
  printf 'v3 system search f1: %s\n' "$reason" >&2
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  case "$DB_WRITES_STATE" in
    false) writes="false" ;;
    *) writes="null" ;;
  esac
  printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"%s","status":"stopped","read_only":false,"db_writes_performed":%s,"db_writes_may_have_been_performed":%s,"failures":["%s"]}\n' \
    "$CURRENT_OPERATION" "$writes" "$([ "$writes" = false ] && echo false || echo true)" "$reason"
  exit 64
}

# Identity is intentionally the first preflight in every mode.
IDENTITY_HELPER="$REPO_ROOT/scripts/operator/lib/f2d_operator_identity.sh"
[ -f "$IDENTITY_HELPER" ] && [ ! -L "$IDENTITY_HELPER" ] \
  || fail "identity helper is missing or symlinked"
# shellcheck source=../lib/f2d_operator_identity.sh
source "$IDENTITY_HELPER"
F2D_IDENTITY="$(require_f2d_operator_code_identity "$REPO_ROOT")" \
  || fail "attested operator identity refused (see stderr)"

TARGET_HOSTNAME="ed-finder-prod"
TARGET_FQDN="nb79a3d.mevnode.com"
POSTGRES_CONTAINER="edfinder-v3-phase4c-full-20260827_r5-postgres"
DATABASE_USER="edfinder_v3"
DATABASE_NAME="edfinder_v3_phase4c_full_20260827_r5"
COMPOSE_PROJECT="edfinder-v3-production"
WORKER_NETWORK="edfinder-v3-phase4c-full-20260827_r5-network"
TARGET_GENERATION_KEY="ratings_v4_prod_p4_parallel_v1"
TARGET_GENERATION_ID="cfc25d36-3bc7-4011-a465-d6460eaaf826"
TARGET_PUBLICATION_SEQUENCE="1"
TARGET_CANONICAL_SEQUENCE="4"
TARGET_CANONICAL_GENERATION="a7076522-54cd-52f3-a291-4e5406bea230"
TARGET_EXPECTED_SYSTEMS="198528286"
MIGRATION_006_NAME="006_v3_derived_product_lifecycle.sql"
MIGRATION_006_SHA="85f38fe5f0251bf3d5f81485a8a5b7de439750b4cc12ef9449755454898767f4"
MIGRATION_010_NAME="010_v3_system_search_body_type_counts.sql"
MIGRATION_010_SHA="a042ccd1544d95cf47407a0722497321a544f15c62ac07dc83c914a19d7acbdf"
MIGRATION_015_NAME="015_v3_derived_product_publication.sql"
MIGRATION_015_SHA="319a4655478e2da9b8d7f7e0c44d7d0c2b3548b8b2934a9564a3b6af897c5791"
WORKER="edfinder-v3-system-search-p4-parallel-v1"
OPERATION_LABEL="ed-finder.operation=v3-system-search-f1"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-search"
TARGET_CPUS="8"
TARGET_MEMORY="32g"
PYTHON_BIN=""

# Keep a crashed worker's log before it is removed; status reports its tail.
preserve_worker_log() {
  local target
  [ -d "$STATE_ROOT" ] || return 0
  target="$STATE_ROOT/worker-log.$(date -u +%Y%m%dT%H%M%SZ).txt"
  ( umask 077; docker logs --tail 200 "$WORKER" > "$target" 2>&1 || true )
  chmod 600 "$target" 2>/dev/null || true
}

preserved_worker_log_tail() {
  local latest
  latest="$(ls -1t "$STATE_ROOT"/worker-log.*.txt 2>/dev/null | head -n 1 || true)"
  [ -n "$latest" ] || return 0
  printf 'preserved_worker_log=%s\npreserved_worker_log_tail:\n' "$latest"
  tail -n 40 "$latest" | sed 's/^/  /'
}

# WAL archiving health (pgBackRest archive-push). A build writes hundreds of
# GB of WAL; an archiver that is failing, or silent while unarchived WAL piles
# up, would fill the data volume mid-build, so start refuses until it is
# healthy. The backlog is the archive_status .ready files (segments written
# but not yet archived), never the pg_wal segment count, which includes
# recycled and preallocated segments and so always looks full.
ARCHIVER_SILENCE_SECONDS=1800
ARCHIVER_WAL_FILE_LIMIT=50
archiver_status() {
  db_query "BEGIN READ ONLY; SELECT json_build_object(
    'archived_count',a.archived_count,
    'last_archived_wal',a.last_archived_wal,
    'last_archived_time',a.last_archived_time,
    'failed_count',a.failed_count,
    'last_failed_wal',a.last_failed_wal,
    'last_failed_time',a.last_failed_time,
    'seconds_since_last_archived',EXTRACT(EPOCH FROM (clock_timestamp()-a.last_archived_time))::bigint,
    'archiver_failing',COALESCE(a.failed_count>0 AND a.last_failed_time>COALESCE(a.last_archived_time,'-infinity'::timestamptz),false),
    'pg_wal_bytes',(SELECT COALESCE(sum(w.size),0) FROM pg_ls_waldir() w),
    'wal_unarchived_files',(SELECT count(*) FROM pg_ls_archive_statusdir() r WHERE r.name LIKE '%.ready')
  )::text FROM pg_stat_archiver a; COMMIT;"
}

require_archiver_healthy() {
  local status verdict
  status="$(archiver_status)"
  verdict="$("$PYTHON_BIN" - "$ARCHIVER_SILENCE_SECONDS" "$ARCHIVER_WAL_FILE_LIMIT" "$status" <<'PY'
import json
import sys
silence, wal_limit = int(sys.argv[1]), int(sys.argv[2])
try:
    value = json.loads(sys.argv[3])
except ValueError:
    print('invalid'); raise SystemExit(0)
if value.get('archiver_failing') is True:
    print('failing'); raise SystemExit(0)
silent = value.get('seconds_since_last_archived')
files = value.get('wal_unarchived_files')
if files is None:
    print('invalid'); raise SystemExit(0)
if (silent is None or silent > silence) and files > wal_limit:
    print('silent'); raise SystemExit(0)
print('healthy')
PY
)"
  [ "$verdict" = "healthy" ] || fail "wal_archiver_unhealthy:${verdict} ${status}"
}

# Read-only preflight precedes every operation lock, host write and container change.
require_purge_clear() {
  local helper="$REPO_ROOT/scripts/operator/lib/v3-purge-state.sh"
  if [ ! -f "$helper" ] || [ -L "$helper" ]; then
    printf '{"schema_version":"ed-finder/operator-operation-result/v1","operation":"%s","status":"stopped","read_only":false,"db_writes_performed":false,"failures":["purge_state_helper_missing"]}\n' "$1"
    exit 78
  fi
  # shellcheck source=../lib/v3-purge-state.sh
  source "$helper"
  v3_purge_require_clear "$1"
}

require_target() {
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable"
  PYTHON_BIN="$(command -v python3.14 || true)"
  [ -n "$PYTHON_BIN" ] || fail "python3.14 is unavailable"
  [ "$(hostname)" = "$TARGET_HOSTNAME" ] || fail "unexpected hostname"
  [ "$(hostname -f 2>/dev/null || true)" = "$TARGET_FQDN" ] || fail "unexpected fqdn"
  [ "$(docker context show)" = "default" ] || fail "unexpected docker context"
  docker context inspect default 2>/dev/null | grep -F 'unix:///var/run/docker.sock' >/dev/null \
    || fail "default docker context is not the local rootful socket"
  docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 \
    || fail "retained postgres container is unavailable"
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER")" = "true" ] \
    || fail "retained postgres container is not running"
}

require_stage() {
  [ -n "$REPO_ROOT" ] && [ -d "$REPO_ROOT" ] || fail "trusted main bundle path is required"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "trusted main SHA is invalid"
  case "$REPO_ROOT" in
    /var/tmp/edfinder-v3-search-"$SOURCE_SHA") ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ "$(cat "$REPO_ROOT/.v3-search-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  [ -f "$REPO_ROOT/scripts/v3_system_search.py" ] || fail "Search builder is missing"
  [ -f "$REPO_ROOT/scripts/operator/lib/f2d_evidence.py" ] || fail "F2d evidence helper is missing"
  [ -f "$REPO_ROOT/scripts/operator/actions/v3-finder-capacity-gate.sh" ] \
    || fail "Finder capacity gate action is missing"
  for migration in "$MIGRATION_006_NAME" "$MIGRATION_010_NAME" "$MIGRATION_015_NAME"; do
    [ -f "$REPO_ROOT/sql/v3/migrations/$migration" ] || fail "migration $migration is missing"
  done
  [ -d "$REPO_ROOT/.v3-search-wheelhouse" ] || fail "offline Search dependency wheelhouse is missing"
}

db_query() {
  docker exec "$POSTGRES_CONTAINER" psql -X --no-psqlrc --no-password \
    --tuples-only --no-align --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

# VACUUM cannot run in a transaction block. This is the sole maintenance write.
db_maintenance() {
  timeout --signal=TERM 7200 docker exec "$POSTGRES_CONTAINER" \
    psql -X --no-psqlrc --no-password --quiet --set ON_ERROR_STOP=1 \
    --username "$DATABASE_USER" --dbname "$DATABASE_NAME" --command "$1"
}

search_vacuum_is_current() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(
    s.last_vacuum > c.final_insert_at AND s.last_analyze > c.final_insert_at,
    false)::text
  FROM pg_stat_user_tables s
  CROSS JOIN (
    SELECT max(completed_at) AS final_insert_at
    FROM v3_derived.search_build_chunk
    WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid
  ) c
  WHERE s.schemaname='v3_derived' AND s.relname='system_search'; COMMIT;"
}

active_api_container() {
  local -a matches=()
  local container service
  while IFS= read -r container; do
    [ -n "$container" ] || continue
    service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")"
    case "$service" in api-*) matches+=("$container") ;; esac
  done < <(docker ps --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" --format '{{.Names}}')
  [ "${#matches[@]}" -eq 1 ] \
    || fail "expected exactly one running production API slot, found ${#matches[@]}"
  printf '%s\n' "${matches[0]}"
}

api_database_url() {
  local api="$1" value count
  value="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | sed -n 's/^DATABASE_URL=//p')"
  count="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$api" | grep -c '^DATABASE_URL=' || true)"
  [ "$count" -eq 1 ] || fail "active API does not expose exactly one DATABASE_URL"
  case "$value" in postgresql://*|postgres://*) ;; *) fail "active API DATABASE_URL is not a PostgreSQL DSN" ;; esac
  printf '%s' "$value"
}

require_generation() {
  local row key identifier state sequence current canonical canonical_sequence expected
  row="$(db_query "BEGIN READ ONLY; SELECT g.generation_key || E'\\t' || g.derived_generation_id::text || E'\\t' || g.lifecycle_state || E'\\t' || p.publication_sequence::text || E'\\t' || (p.derived_generation_id IS NOT NULL)::text || E'\\t' || g.canonical_generation_id::text || E'\\t' || g.canonical_publication_sequence::text || E'\\t' || g.expected_systems::text FROM v3_meta.derived_generation g LEFT JOIN v3_meta.current_derived_generation p ON p.singleton AND p.derived_generation_id=g.derived_generation_id WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;")"
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r key identifier state sequence current canonical canonical_sequence expected <<< "$row"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  [ "$identifier" = "$TARGET_GENERATION_ID" ] || fail "target generation UUID mismatch"
  [ "$state" = "PUBLISHED" ] || fail "target generation is not PUBLISHED"
  [ "$sequence" = "$TARGET_PUBLICATION_SEQUENCE" ] || fail "target generation publication sequence mismatch"
  [ "$current" = "true" ] || fail "target generation is not the current pointer"
  [ "$canonical" = "$TARGET_CANONICAL_GENERATION" ] || fail "target canonical generation mismatch"
  [ "$canonical_sequence" = "$TARGET_CANONICAL_SEQUENCE" ] || fail "target canonical publication sequence mismatch"
  [ "$expected" = "$TARGET_EXPECTED_SYSTEMS" ] || fail "target expected system count mismatch"
}

verify_migration() {
  local name="$1" expected="$2" label="$3" checkout_sha ledger_sha
  checkout_sha="$(sha256sum "$REPO_ROOT/sql/v3/migrations/$name" | awk '{print $1}')"
  [ "$checkout_sha" = "$expected" ] || fail "trusted migration $label source hash mismatch"
  ledger_sha="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${name}'; COMMIT;")"
  [ "$ledger_sha" = "$expected" ] || fail "migration $label live ledger hash mismatch"
}

require_search_schema() {
  verify_migration "$MIGRATION_006_NAME" "$MIGRATION_006_SHA" 006
  verify_migration "$MIGRATION_010_NAME" "$MIGRATION_010_SHA" 010
  verify_migration "$MIGRATION_015_NAME" "$MIGRATION_015_SHA" 015
}

latest_status() {
  db_query "BEGIN READ ONLY; SELECT json_build_object(
    'generation_key',g.generation_key,
    'generation_state',g.lifecycle_state,
    'ratings_completed_chunks',(SELECT count(*) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
    'ratings_completed_systems',(SELECT COALESCE(sum(b.systems),0) FROM v3_derived.build_chunk b WHERE b.derived_generation_id=g.derived_generation_id),
    'ratings_validation_status',g.validation_receipt->>'status',
    'search_product_state',(SELECT p.lifecycle_state FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_manifest_sha256',(SELECT encode(p.manifest_sha256,'hex') FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_validation_status',(SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_validated_at',(SELECT p.validated_at FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_search'),
    'search_completed_chunks',(SELECT count(*) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
    'search_completed_systems',(SELECT COALESCE(sum(s.systems),0) FROM v3_derived.search_build_chunk s WHERE s.derived_generation_id=g.derived_generation_id),
    'search_rows',(SELECT count(*) FROM v3_derived.system_search s WHERE s.derived_generation_id=g.derived_generation_id),
    'archetype_product_state',(SELECT p.lifecycle_state FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'archetype_validation_status',(SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'published_at',g.published_at
  )::text FROM v3_meta.derived_generation g WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;"
}

write_builder_env() {
  local path="$1" dsn="$2" expected_manifest="${3:-}"
  umask 077
  printf 'V3_SYSTEM_SEARCH_DATABASE_URL=%s\n' "$dsn" > "$path"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$path"
  if [ -n "$expected_manifest" ]; then
    printf 'EXPECTED_MANIFEST_SHA256=%s\n' "$expected_manifest" >> "$path"
  fi
  chmod 600 "$path"
}

compute_manifest_sha256() {
  local api_image="$1" env_file="$2" output
  output="$(docker run --rm \
    --network "$WORKER_NETWORK" --cpus 2 --memory 4g --memory-swap 4g \
    --pids-limit 128 --read-only --tmpfs /tmp --env-file "$env_file" \
    --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --entrypoint /bin/sh "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-search-wheelhouse --target /tmp/v3-search-deps \
        --require-hashes -r /work/deploy/v3-production/f2d-wheels.txt 1>&2
      export PYTHONPATH="/tmp/v3-search-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_system_search.py \
        --generation-key ratings_v4_prod_p4_parallel_v1 --print-manifest-sha256
    ')" || fail "Search manifest computation failed"
  [[ "$output" =~ ^[0-9a-f]{64}$ ]] || fail "Search manifest computation returned an invalid digest"
  printf '%s' "$output"
}

run_capacity_gate() {
  local temporary exit_code status
  temporary="$(mktemp "$STATE_ROOT/.capacity-gate-receipt.XXXXXX")" \
    || fail "capacity gate receipt temporary file could not be created"
  set +e
  F2D_OPERATOR_CODE_SHA256_ATTESTED="$F2D_IDENTITY" \
    "$REPO_ROOT/scripts/operator/actions/v3-finder-capacity-gate.sh" \
      run "$REPO_ROOT" "$SOURCE_SHA" > "$temporary"
  exit_code=$?
  set -e
  chmod 600 "$temporary"
  mv -f "$temporary" "$STATE_ROOT/capacity-gate-receipt.json"
  status="$($PYTHON_BIN - "$STATE_ROOT/capacity-gate-receipt.json" <<'PY'
import json
import sys
try:
    value = json.load(open(sys.argv[1], encoding='utf-8'))
except (OSError, ValueError):
    raise SystemExit(1)
if not isinstance(value, dict) or value.get('status') != 'passed':
    raise SystemExit(1)
print(value['status'])
PY
  )" || fail "capacity gate exited ${exit_code} without a passed operation-result envelope"
  [ "$exit_code" -eq 0 ] && [ "$status" = "passed" ] \
    || fail "capacity gate exited ${exit_code} without a passed operation-result envelope"
}

write_build_start_receipt() {
  local manifest_sha="$1" relation_size started_at path
  relation_size="$(db_query "BEGIN READ ONLY; SELECT pg_total_relation_size('v3_derived.system_search')::text; COMMIT;")"
  [[ "$relation_size" =~ ^[0-9]+$ ]] || fail "Search relation size reading is invalid"
  started_at="$(db_query "BEGIN READ ONLY; SELECT clock_timestamp()::text; COMMIT;")"
  [ -n "$started_at" ] || fail "Search build start timestamp is empty"
  path="$STATE_ROOT/build-start-receipt.json"
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$path" "$TARGET_GENERATION_ID" \
    "$manifest_sha" "$relation_size" "$started_at" "$F2D_IDENTITY" <<'PY' \
    || fail "Search build-start receipt is invalid, conflicts with this build, or was written under another operator identity"
import os
from pathlib import Path
import sys
from scripts.operator.lib.f2d_evidence import canonical_json, load_sealed, seal

path = Path(sys.argv[1])
identifier, manifest, relation_size, started_at, identity = sys.argv[2:]
if path.exists():
    receipt = load_sealed(path)
    expected = {
        'schema_version': 'ed-finder/v3-build-start-receipt/v1',
        'product_code': 'system_search',
        'derived_generation_id': identifier,
        'manifest_sha256': manifest,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise SystemExit(2)
    if (
        not isinstance(receipt.get('relation_total_bytes_at_start'), int)
        or isinstance(receipt.get('relation_total_bytes_at_start'), bool)
        or receipt['relation_total_bytes_at_start'] < 0
        or not isinstance(receipt.get('started_at'), str)
        or not isinstance(receipt.get('f2d_operator_code_sha256'), str)
        or len(receipt['f2d_operator_code_sha256']) != 64
    ):
        raise SystemExit(2)
    # A receipt written under another attested operator identity is never
    # resumed: the finalizers refuse it, so launching a build on it would strand
    # the product. The operator removes it deliberately or the build restarts
    # under the current identity.
    if receipt['f2d_operator_code_sha256'] != identity:
        raise SystemExit(3)
    raise SystemExit(0)
body = {
    'schema_version': 'ed-finder/v3-build-start-receipt/v1',
    'product_code': 'system_search',
    'derived_generation_id': identifier,
    'manifest_sha256': manifest,
    'relation_total_bytes_at_start': int(relation_size),
    'started_at': started_at,
    'f2d_operator_code_sha256': identity,
}
temporary = path.with_name(f'.{path.name}.tmp-{os.getpid()}')
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(canonical_json(seal(body)) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
finally:
    if temporary.exists():
        temporary.unlink()
PY
}

receipt_seal() {
  local path="$1"
  [ -f "$path" ] && [ ! -L "$path" ] || { printf 'missing'; return; }
  "$PYTHON_BIN" - "$path" <<'PY'
import json
import sys
try:
    value = json.load(open(sys.argv[1], encoding='utf-8'))
    seal = value.get('content_sha256')
    if not isinstance(seal, str) and isinstance(value.get('receipt'), dict):
        seal = value['receipt'].get('content_sha256')
    print(seal if isinstance(seal, str) else 'invalid')
except (OSError, ValueError):
    print('invalid')
PY
}

emit_receipt_status() {
  local name path key
  for name in capacity-gate-receipt build-start-receipt build-final-receipt; do
    path="$STATE_ROOT/$name.json"
    key="${name//-/_}"
    printf '%s_path=%s\n' "$key" "$path"
    printf '%s_seal=%s\n' "$key" "$(receipt_seal "$path")"
    if [ -f "$path" ] && [ ! -L "$path" ]; then
      printf '%s=%s\n' "$key" "$(tr -d '\n' < "$path")"
    fi
  done
}

# Stop a launched worker whose launch could not be proven, and confirm it is
# no longer running; refuse loudly if it cannot be stopped.
stop_unproven_worker() {
  local state
  if docker inspect "$WORKER" >/dev/null 2>&1; then
    state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$state" = "running" ]; then
      docker stop --time 60 "$WORKER" >/dev/null 2>&1 || true
      state="$(docker inspect -f '{{.State.Status}}' "$WORKER" 2>/dev/null || echo unknown)"
      [ "$state" != "running" ] \
        || fail "unproven worker ${WORKER} could not be stopped and may still be writing"
    fi
  fi
}

# A worker that is already running is accepted only when it was launched for
# this generation by this exact source and attested operator identity, and
# its build-start receipt already exists; nothing is written for it first.
# Sets EXISTING_WORKER to "running" for an accepted worker, "absent" when
# none is running; refuses (in this shell, not a subshell) otherwise.
EXISTING_WORKER=""
existing_worker_state() {
  local state label_source label_identity label_generation
  EXISTING_WORKER="absent"
  docker inspect "$WORKER" >/dev/null 2>&1 || return 0
  state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  [ "$state" = "running" ] || return 0
  label_source="$(docker inspect -f '{{index .Config.Labels "ed-finder.source-sha"}}' "$WORKER")"
  label_identity="$(docker inspect -f '{{index .Config.Labels "ed-finder.f2d-operator-code-sha256"}}' "$WORKER")"
  label_generation="$(docker inspect -f '{{index .Config.Labels "ed-finder.generation-id"}}' "$WORKER")"
  [ "$label_source" = "$SOURCE_SHA" ] && [ "$label_identity" = "$F2D_IDENTITY" ] \
    && [ "$label_generation" = "$TARGET_GENERATION_ID" ] \
    || fail "running worker ${WORKER} was launched by another source, identity or generation"
  [ -f "$STATE_ROOT/build-start-receipt.json" ] && [ ! -L "$STATE_ROOT/build-start-receipt.json" ] \
    || fail "running worker ${WORKER} has no build-start receipt"
  EXISTING_WORKER="running"
}

start_operation() {
  require_target
  require_purge_clear "v3-system-search-f1-start"
  require_stage
  require_search_schema
  require_generation
  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/start.lock"
  flock -n 9 || fail "another V3 Search start is in progress"

  existing_worker_state
  if [ "$EXISTING_WORKER" = "running" ]; then
    printf 'operation=v3-system-search-f1-start\nresult=already-running\nworker=%s\n' "$WORKER"
    emit_receipt_status
    printf 'latest_status=%s\n' "$(latest_status)"
  printf 'publication_performed=false\ncanonical_writes_performed=false\n'
    return 0
  fi

  local api api_image dsn env_file manifest_sha worker_state proof
  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"
  require_archiver_healthy
  run_capacity_gate

  env_file="$STATE_ROOT/search.env"
  write_builder_env "$env_file" "$dsn"
  trap 'rm -f -- "$env_file"' EXIT
  manifest_sha="$(compute_manifest_sha256 "$api_image" "$env_file")"
  write_build_start_receipt "$manifest_sha"

  if docker inspect "$WORKER" >/dev/null 2>&1; then
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$worker_state" = "running" ]; then
      rm -f -- "$env_file"
      trap - EXIT
      printf 'operation=v3-system-search-f1-start\nresult=already-running\nworker=%s\n' "$WORKER"
      emit_receipt_status
      printf 'latest_status=%s\n' "$(latest_status)"
      printf 'publication_performed=false\ncanonical_writes_performed=false\n'
      return 0
    fi
    preserve_worker_log
    docker rm "$WORKER" >/dev/null
  fi

  write_builder_env "$env_file" "$dsn" "$manifest_sha"
  # Chunks a previous worker already committed are not proof for this launch:
  # record them, and require this worker to commit at least one more.
  local baseline_chunks
  baseline_chunks="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.search_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  [[ "$baseline_chunks" =~ ^[0-9]+$ ]] || fail "Search baseline chunk query was invalid"
  # Search writes one chunk per Ratings build chunk. When every planned chunk
  # is already committed (a worker that wrote the last chunk but did not
  # finish validating), this launch can only validate: there is no further
  # chunk for it to prove itself by.
  local planned_chunks validation_only=false result=launched
  planned_chunks="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  [[ "$planned_chunks" =~ ^[1-9][0-9]*$ ]] || fail "Search planned chunk query was invalid"
  [ "$baseline_chunks" -le "$planned_chunks" ] \
    || fail "Search has more committed chunks than the Ratings chunk plan"
  [ "$baseline_chunks" -lt "$planned_chunks" ] || validation_only=true
  mark_db_writes_possible
  if ! docker run -d \
    --name "$WORKER" --label "$OPERATION_LABEL" \
    --label "ed-finder.generation-key=${TARGET_GENERATION_KEY}" \
    --label "ed-finder.generation-id=${TARGET_GENERATION_ID}" \
    --label "ed-finder.source-sha=${SOURCE_SHA}" \
    --label "ed-finder.f2d-operator-code-sha256=${F2D_IDENTITY}" \
    --network "$WORKER_NETWORK" --cpus "$TARGET_CPUS" \
    --memory "$TARGET_MEMORY" --memory-swap "$TARGET_MEMORY" \
    --pids-limit 256 --restart no --read-only --tmpfs /tmp:rw,nosuid,size=2g \
    --log-driver json-file --log-opt max-size=20m --log-opt max-file=3 \
    --env-file "$env_file" --mount "type=bind,src=${REPO_ROOT},dst=/work,readonly" \
    --entrypoint /bin/sh "$api_image" -lc '
      set -eu
      /usr/local/bin/python -m pip install --quiet --disable-pip-version-check --no-input --no-index \
        --find-links /work/.v3-search-wheelhouse --target /tmp/v3-search-deps \
        --require-hashes -r /work/deploy/v3-production/f2d-wheels.txt 1>&2
      export PYTHONPATH="/tmp/v3-search-deps:/work:/work/apps/api/src"
      cd /work
      exec /app/.venv/bin/python scripts/v3_system_search.py \
        --generation-key ratings_v4_prod_p4_parallel_v1 --follow --poll-seconds 5 \
        --expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"
    ' >/dev/null; then
    # set -e would otherwise exit here with no receipt: keep whatever the
    # daemon logged for a container that was created, then stop closed.
    rm -f -- "$env_file"
    trap - EXIT
    if docker inspect "$WORKER" >/dev/null 2>&1; then
      preserve_worker_log
    fi
    fail "worker_launch_failed"
  fi
  rm -f -- "$env_file"
  trap - EXIT

  sleep 3
  worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  proof="$baseline_chunks"
  if [ "$validation_only" = true ]; then
    # Validation-only resume: proven by a clean exit. While it is still
    # validating it is reported as such and left running (it can write no
    # further chunk); finalize requires its exit code 0 either way.
    # Ten minutes: a resume installs wheels, registers and lists ~198k chunks first.
    for _ in $(seq 1 300); do
      [ "$worker_state" = "running" ] || break
      sleep 2
      worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    done
    if [ "$worker_state" = "running" ]; then
      result=launched-validation-only
    elif [ "$worker_state" = "exited" ] \
      && [ "$(docker inspect -f '{{.State.ExitCode}}' "$WORKER")" = "0" ]; then
      result=validated
    else
      docker logs --tail 80 "$WORKER" >&2 || true
      preserve_worker_log
      fail "Search validation-only worker did not exit successfully"
    fi
  elif [ "$worker_state" != "running" ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    preserve_worker_log
    fail "Search worker did not remain running"
  fi
  for _ in $(seq 1 300); do
    [ "$validation_only" = false ] || break
    proof="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.search_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
    [[ "$proof" =~ ^[0-9]+$ ]] || fail "Search proof query was invalid"
    [ "$proof" -gt "$baseline_chunks" ] && break
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    [ "$worker_state" = "running" ] || break
    sleep 2
  done
  if [ "$validation_only" = false ] && [ "$proof" -le "$baseline_chunks" ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    preserve_worker_log
    # A failed start must not leave an unproven worker inserting in the
    # background: stop it (an uncommitted chunk rolls back; committed chunks
    # stay sealed for a later resume) before reporting the failure.
    stop_unproven_worker
    fail "Search worker did not prove a chunk committed by this launch; the worker was stopped"
  fi

  printf 'operation=v3-system-search-f1-start\nresult=%s\n' "$result"
  printf 'planned_chunks=%s\n' "$planned_chunks"
  printf 'source_sha=%s\ngeneration_key=%s\ngeneration_id=%s\n' \
    "$SOURCE_SHA" "$TARGET_GENERATION_KEY" "$TARGET_GENERATION_ID"
  printf 'manifest_sha256=%s\nworker=%s\nworker_state=%s\nproof_chunks=%s\nbaseline_chunks=%s\n' \
    "$manifest_sha" "$WORKER" "$worker_state" "$proof" "$baseline_chunks"
  printf 'migration_006_sha256=%s\nmigration_010_sha256=%s\nmigration_015_sha256=%s\n' \
    "$MIGRATION_006_SHA" "$MIGRATION_010_SHA" "$MIGRATION_015_SHA"
  emit_receipt_status
  printf 'latest_status=%s\n' "$(latest_status)"
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

status_operation() {
  require_target
  require_stage
  require_generation
  printf 'operation=v3-system-search-f1-status\nworker_containers:\n'
  docker ps -a --filter "label=${OPERATION_LABEL}" --format '  {{.Names}}\t{{.Status}}\t{{.Image}}' || true
  printf 'latest_status=%s\n' "$(latest_status)"
  printf 'archiver_status=%s\n' "$(archiver_status)"
  emit_receipt_status
  if docker inspect "$WORKER" >/dev/null 2>&1; then
    printf 'latest_worker_log_tail:\n'
    docker logs --tail 40 "$WORKER" 2>&1 | sed 's/^/  /' || true
  fi
  preserved_worker_log_tail
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

finalize_operation() {
  require_target
  require_purge_clear "v3-system-search-f1-finalize"
  require_stage
  require_search_schema
  require_generation
  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/finalize.lock"
  flock -n 9 || fail "another V3 Search finalize is in progress"

  local worker_state worker_exit manifest_sha product_row lifecycle validation registered_manifest
  local chunk_row final_insert_at chunk_count row_count stats last_vacuum last_analyze vacuum_performed=false
  [ -f "$STATE_ROOT/build-start-receipt.json" ] && [ ! -L "$STATE_ROOT/build-start-receipt.json" ] \
    || fail "Search build-start receipt is missing"
  manifest_sha="$(PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$STATE_ROOT/build-start-receipt.json" "$TARGET_GENERATION_ID" "$F2D_IDENTITY" <<'PY'
import sys
from scripts.operator.lib.f2d_evidence import load_sealed
receipt = load_sealed(sys.argv[1])
if (receipt.get('schema_version') != 'ed-finder/v3-build-start-receipt/v1'
        or receipt.get('product_code') != 'system_search'
        or receipt.get('derived_generation_id') != sys.argv[2]):
    raise SystemExit(1)
# A build started under a different attested operator identity is never
# finalized under this one: its gate and start evidence came from other code.
if receipt.get('f2d_operator_code_sha256') != sys.argv[3]:
    raise SystemExit(2)
print(receipt.get('manifest_sha256', ''))
PY
  )" || fail "Search build-start receipt is invalid or was produced under another operator identity"
  [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] || fail "Search build-start manifest digest is invalid"

  docker inspect "$WORKER" >/dev/null 2>&1 || fail "Search worker container is missing"
  worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  worker_exit="$(docker inspect -f '{{.State.ExitCode}}' "$WORKER")"
  [ "$worker_state" = "exited" ] && [ "$worker_exit" = "0" ] \
    || fail "Search worker has not exited successfully"

  product_row="$(db_query "BEGIN READ ONLY; SELECT lifecycle_state || E'\\t' || COALESCE(validation_receipt->>'status','') || E'\\t' || encode(manifest_sha256,'hex') FROM v3_meta.derived_product WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND product_code='system_search'; COMMIT;")"
  IFS=$'\t' read -r lifecycle validation registered_manifest <<< "$product_row"
  [ "$lifecycle" = "READY" ] && [ "$validation" = "VERIFIED" ] \
    || fail "Search product is not READY/VERIFIED"
  [ "$registered_manifest" = "$manifest_sha" ] \
    || fail "Search registered manifest differs from the build-start receipt"

  chunk_row="$(db_query "BEGIN READ ONLY; SELECT max(completed_at)::text || E'\\t' || count(*)::text || E'\\t' || COALESCE(sum(systems),0)::text FROM v3_derived.search_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  IFS=$'\t' read -r final_insert_at chunk_count row_count <<< "$chunk_row"
  [ -n "$final_insert_at" ] && [[ "$chunk_count" =~ ^[1-9][0-9]*$ ]] \
    && [ "$row_count" = "$TARGET_EXPECTED_SYSTEMS" ] \
    || fail "Search final-insert receipt coverage is invalid"

  stats="$(db_query "BEGIN READ ONLY; SELECT COALESCE(last_vacuum::text,'') || E'\\t' || COALESCE(last_analyze::text,'') FROM pg_stat_user_tables WHERE schemaname='v3_derived' AND relname='system_search'; COMMIT;")"
  IFS=$'\t' read -r last_vacuum last_analyze <<< "$stats"
  if [ "$(search_vacuum_is_current)" != "true" ]; then
    mark_db_writes_possible
    db_maintenance "VACUUM (ANALYZE) v3_derived.system_search;"
    vacuum_performed=true
    stats="$(db_query "BEGIN READ ONLY; SELECT COALESCE(last_vacuum::text,'') || E'\\t' || COALESCE(last_analyze::text,'') FROM pg_stat_user_tables WHERE schemaname='v3_derived' AND relname='system_search'; COMMIT;")"
    IFS=$'\t' read -r last_vacuum last_analyze <<< "$stats"
  fi
  [ "$(search_vacuum_is_current)" = "true" ] \
    || fail "Search vacuum/analyze timestamps do not postdate the final insert"

  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$STATE_ROOT/build-final-receipt.json" \
    "$TARGET_GENERATION_ID" "$manifest_sha" "$final_insert_at" "$last_vacuum" \
    "$last_analyze" "$chunk_count" "$row_count" "$lifecycle" "$validation" \
    "$F2D_IDENTITY" "$vacuum_performed" <<'PY' \
    || fail "Search build-final receipt could not be written"
import os
from pathlib import Path
import sys
from scripts.operator.lib.f2d_evidence import canonical_json, seal

(path, identifier, manifest, final_insert, last_vacuum, last_analyze,
 chunk_count, row_count, lifecycle, validation, identity, performed) = sys.argv[1:]
body = {
    'schema_version': 'ed-finder/v3-build-final-receipt/v1',
    'product_code': 'system_search',
    'derived_generation_id': identifier,
    'manifest_sha256': manifest,
    'final_insert_at': final_insert,
    'last_vacuum': last_vacuum,
    'last_analyze': last_analyze,
    'chunk_count': int(chunk_count),
    'row_count': int(row_count),
    'lifecycle_state': lifecycle,
    'validation_status': validation,
    'f2d_operator_code_sha256': identity,
    'vacuum_performed': performed == 'true',
    'idempotent_reverification': performed != 'true',
}
target = Path(path)
temporary = target.with_name(f'.{target.name}.tmp-{os.getpid()}')
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(canonical_json(seal(body)) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
finally:
    if temporary.exists():
        temporary.unlink()
PY
  printf 'operation=v3-system-search-f1-finalize\nstatus=completed\n'
  emit_receipt_status
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

case "$ACTION" in
  start) start_operation ;;
  status) status_operation ;;
  finalize) finalize_operation ;;
  *) fail "expected start, status, or finalize" ;;
esac
