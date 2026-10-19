#!/usr/bin/env bash
# Governed wide Archetype build for the pinned published parallel_v1 generation.
set -euo pipefail

ACTION="${1:-}"
REPO_ROOT="${2:-}"
SOURCE_SHA="${3:-}"

# The receipt emitter precedes every refusal, including the identity
# preflight, so each stop prints a stopped operation-result line on stdout:
# the workflow records stdout only, and a reason that went to stderr alone was
# invisible in the downloadable receipt.
CURRENT_OPERATION="v3-system-archetype"
if [[ "$ACTION" =~ ^(start|status|finalize)$ ]]; then
  CURRENT_OPERATION="v3-system-archetype-$ACTION"
fi
# Mutation state for the stopped receipt. "false" until this invocation may
# have changed the database (a worker launched by it, or VACUUM started);
# "unknown" afterwards, because a refusal cannot prove what the worker or
# VACUUM committed before the stop.
DB_WRITES_STATE="false"
mark_db_writes_possible() { DB_WRITES_STATE="unknown"; }

fail() {
  local reason="$*" writes
  printf 'v3 system archetype: %s\n' "$reason" >&2
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
MIGRATION_011_NAME="011_v3_system_archetype.sql"
MIGRATION_011_SHA="652982595f7ff86f78452bcadd467e399643980e126fbf9c427854608d8c5e25"
MIGRATION_015_NAME="015_v3_derived_product_publication.sql"
MIGRATION_015_SHA="319a4655478e2da9b8d7f7e0c44d7d0c2b3548b8b2934a9564a3b6af897c5791"
WORKER="edfinder-v3-system-archetype-p4-parallel-v1"
OPERATION_LABEL="ed-finder.operation=v3-system-archetype"
STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-archetype"
SEARCH_STATE_ROOT="${HOME}/.local/state/ed-finder/v3-system-search"
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
    /var/tmp/edfinder-v3-archetype-build-"$SOURCE_SHA") ;;
    *) fail "trusted main bundle path is outside reviewed staging namespace" ;;
  esac
  [ "$(cat "$REPO_ROOT/.v3-archetype-build-source-sha" 2>/dev/null || true)" = "$SOURCE_SHA" ] \
    || fail "trusted main bundle SHA marker mismatch"
  for path in \
    scripts/v3_system_archetype.py \
    scripts/v3_archetype_calibration_complete.py \
    scripts/operator/lib/f2d_evidence.py \
    scripts/operator/actions/v3-finder-capacity-gate.sh \
    shared_contracts/v3_system_archetype_model.py; do
    [ -f "$REPO_ROOT/$path" ] && [ ! -L "$REPO_ROOT/$path" ] \
      || fail "required Archetype build source $path is missing or symlinked"
  done
  for migration in "$MIGRATION_011_NAME" "$MIGRATION_015_NAME"; do
    [ -f "$REPO_ROOT/sql/v3/migrations/$migration" ] \
      || fail "migration $migration is missing"
  done
  [ -d "$REPO_ROOT/.v3-archetype-wheelhouse" ] \
    || fail "offline Archetype dependency wheelhouse is missing"
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

archetype_vacuum_is_current() {
  db_query "BEGIN READ ONLY; SELECT COALESCE(
    s.last_vacuum > c.final_insert_at AND s.last_analyze > c.final_insert_at,
    false)::text
  FROM pg_stat_user_tables s
  CROSS JOIN (
    SELECT max(completed_at) AS final_insert_at
    FROM v3_derived.archetype_build_chunk
    WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid
  ) c
  WHERE s.schemaname='v3_derived' AND s.relname='system_archetype'; COMMIT;"
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
  [ "$(printf '%s\n' "$row" | wc -l)" -eq 1 ] \
    || fail "target derived generation is missing or ambiguous"
  IFS=$'\t' read -r key identifier state sequence current canonical canonical_sequence expected <<< "$row"
  [ "$key" = "$TARGET_GENERATION_KEY" ] || fail "target generation key mismatch"
  [ "$identifier" = "$TARGET_GENERATION_ID" ] || fail "target generation UUID mismatch"
  [ "$state" = "PUBLISHED" ] || fail "target generation is not PUBLISHED"
  [ "$sequence" = "$TARGET_PUBLICATION_SEQUENCE" ] \
    || fail "target generation publication sequence mismatch"
  [ "$current" = "true" ] || fail "target generation is not the current pointer"
  [ "$canonical" = "$TARGET_CANONICAL_GENERATION" ] \
    || fail "target canonical generation mismatch"
  [ "$canonical_sequence" = "$TARGET_CANONICAL_SEQUENCE" ] \
    || fail "target canonical publication sequence mismatch"
  [ "$expected" = "$TARGET_EXPECTED_SYSTEMS" ] \
    || fail "target expected system count mismatch"
}

verify_migration() {
  local name="$1" expected="$2" label="$3" checkout_sha ledger_sha
  checkout_sha="$(sha256sum "$REPO_ROOT/sql/v3/migrations/$name" | awk '{print $1}')"
  [ "$checkout_sha" = "$expected" ] || fail "trusted migration $label source hash mismatch"
  ledger_sha="$(db_query "BEGIN READ ONLY; SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration WHERE migration_name='${name}'; COMMIT;")"
  [ "$ledger_sha" = "$expected" ] || fail "migration $label live ledger hash mismatch"
}

require_archetype_schema() {
  verify_migration "$MIGRATION_011_NAME" "$MIGRATION_011_SHA" 011
  verify_migration "$MIGRATION_015_NAME" "$MIGRATION_015_SHA" 015
}

latest_status() {
  db_query "BEGIN READ ONLY; SELECT json_build_object(
    'generation_key',g.generation_key,
    'generation_state',g.lifecycle_state,
    'archetype_product_state',(SELECT p.lifecycle_state FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'archetype_manifest_sha256',(SELECT encode(p.manifest_sha256,'hex') FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'archetype_validation_status',(SELECT p.validation_receipt->>'status' FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'archetype_validated_at',(SELECT p.validated_at FROM v3_meta.derived_product p WHERE p.derived_generation_id=g.derived_generation_id AND p.product_code='system_archetype'),
    'archetype_completed_chunks',(SELECT count(*) FROM v3_derived.archetype_build_chunk a WHERE a.derived_generation_id=g.derived_generation_id),
    'archetype_completed_systems',(SELECT COALESCE(sum(a.systems),0) FROM v3_derived.archetype_build_chunk a WHERE a.derived_generation_id=g.derived_generation_id),
    'archetype_rows',(SELECT count(*) FROM v3_derived.system_archetype a WHERE a.derived_generation_id=g.derived_generation_id),
    'published_at',g.published_at
  )::text FROM v3_meta.derived_generation g WHERE g.generation_key='${TARGET_GENERATION_KEY}'; COMMIT;"
}

require_search_prerequisite() {
  local row lifecycle validation registered_manifest path
  row="$(db_query "BEGIN READ ONLY; SELECT lifecycle_state || E'\\t' || COALESCE(validation_receipt->>'status','') || E'\\t' || encode(manifest_sha256,'hex') FROM v3_meta.derived_product WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND product_code='system_search'; COMMIT;")"
  IFS=$'\t' read -r lifecycle validation registered_manifest <<< "$row"
  [ "$lifecycle" = "READY" ] && [ "$validation" = "VERIFIED" ] \
    || fail "Search product prerequisite is not READY/VERIFIED"
  path="$SEARCH_STATE_ROOT/build-final-receipt.json"
  [ -f "$path" ] && [ ! -L "$path" ] || fail "Search build-final receipt is missing"
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$path" "$TARGET_GENERATION_ID" \
    "$F2D_IDENTITY" "$registered_manifest" "$TARGET_EXPECTED_SYSTEMS" <<'PY' \
    || fail "Search build-final receipt is invalid"
import re
import sys
from datetime import datetime
from scripts.operator.lib.f2d_evidence import load_sealed

receipt = load_sealed(sys.argv[1])
expected = {
    'schema_version': 'ed-finder/v3-build-final-receipt/v1',
    'product_code': 'system_search',
    'derived_generation_id': sys.argv[2],
    'lifecycle_state': 'READY',
    'validation_status': 'VERIFIED',
    'f2d_operator_code_sha256': sys.argv[3],
    'manifest_sha256': sys.argv[4],
}
if any(receipt.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if re.fullmatch(r'[0-9a-f]{64}', str(receipt.get('manifest_sha256', ''))) is None:
    raise SystemExit(1)
if not receipt.get('final_insert_at') or not receipt.get('last_vacuum') or not receipt.get('last_analyze'):
    raise SystemExit(1)
if receipt.get('row_count') != int(sys.argv[5]):
    raise SystemExit(1)
if not isinstance(receipt.get('chunk_count'), int) or receipt['chunk_count'] < 1:
    raise SystemExit(1)
final_insert = datetime.fromisoformat(receipt['final_insert_at'].replace('Z', '+00:00'))
last_vacuum = datetime.fromisoformat(receipt['last_vacuum'].replace('Z', '+00:00'))
last_analyze = datetime.fromisoformat(receipt['last_analyze'].replace('Z', '+00:00'))
if last_vacuum <= final_insert or last_analyze <= final_insert:
    raise SystemExit(1)
PY
}

expected_manifest_sha256() {
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$REPO_ROOT" "$TARGET_GENERATION_KEY" \
    "$TARGET_GENERATION_ID" "$TARGET_PUBLICATION_SEQUENCE" "$TARGET_EXPECTED_SYSTEMS" \
    "$F2D_IDENTITY" <<'PY'
import re
import sys
from scripts.operator.lib.f2d_evidence import (
    COMPLETE_RECEIPT, canonical_sha256, load_sealed,
)
from scripts.v3_archetype_calibration_complete import validate_complete_receipt

root, key, identifier, sequence, systems, identity = sys.argv[1:]
receipt = load_sealed(__import__('pathlib').Path(root) / COMPLETE_RECEIPT)
validate_complete_receipt(receipt)
generation = receipt.get('generation')
manifest = receipt.get('expected_product_manifest')
digest = receipt.get('expected_product_manifest_sha256')
if receipt.get('status') != 'completed' or not isinstance(generation, dict):
    raise SystemExit(1)
if generation.get('generation_key') != key or generation.get('derived_generation_id') != identifier:
    raise SystemExit(1)
if generation.get('publication_sequence') != int(sequence):
    raise SystemExit(1)
if receipt.get('system_count') != int(systems):
    raise SystemExit(1)
if receipt.get('f2d_operator_code_sha256') != identity:
    raise SystemExit(1)
if not isinstance(manifest, dict) or manifest.get('product_code') != 'system_archetype':
    raise SystemExit(1)
if manifest.get('derived_generation_id') != identifier or manifest.get('generation_key') != key:
    raise SystemExit(1)
if re.fullmatch(r'[0-9a-f]{64}', str(digest)) is None:
    raise SystemExit(1)
if canonical_sha256(manifest) != digest:
    raise SystemExit(1)
print(digest)
PY
}

write_builder_env() {
  local path="$1" dsn="$2" expected_manifest="$3"
  umask 077
  printf 'V3_SYSTEM_ARCHETYPE_DATABASE_URL=%s\n' "$dsn" > "$path"
  printf 'F2D_OPERATOR_CODE_SHA256_ATTESTED=%s\n' "$F2D_IDENTITY" >> "$path"
  printf 'EXPECTED_MANIFEST_SHA256=%s\n' "$expected_manifest" >> "$path"
  chmod 600 "$path"
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
  relation_size="$(db_query "BEGIN READ ONLY; SELECT pg_total_relation_size('v3_derived.system_archetype')::text; COMMIT;")"
  [[ "$relation_size" =~ ^[0-9]+$ ]] || fail "Archetype relation size reading is invalid"
  started_at="$(db_query "BEGIN READ ONLY; SELECT clock_timestamp()::text; COMMIT;")"
  [ -n "$started_at" ] || fail "Archetype build start timestamp is empty"
  path="$STATE_ROOT/build-start-receipt.json"
  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$path" "$TARGET_GENERATION_ID" \
    "$manifest_sha" "$relation_size" "$started_at" "$F2D_IDENTITY" <<'PY' \
    || fail "Archetype build-start receipt is invalid, conflicts with this build, or was written under another operator identity"
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
        'product_code': 'system_archetype',
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
    'product_code': 'system_archetype',
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

# Validation (every chunk re-read and re-scored, hours at 198.5 M systems)
# runs inside the detached worker after its last chunk, exactly as the Search
# worker does; it is never a bounded foreground container. Finalize therefore
# only confirms the worker's clean exit and the READY/VERIFIED product before
# the maintenance VACUUM.

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
  require_purge_clear "v3-system-archetype-start"
  require_stage
  require_archetype_schema
  require_generation
  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/start.lock"
  flock -n 9 || fail "another V3 Archetype start is in progress"

  existing_worker_state
  if [ "$EXISTING_WORKER" = "running" ]; then
    printf 'operation=v3-system-archetype-start\nresult=already-running\nworker=%s\n' "$WORKER"
    emit_receipt_status
    printf 'latest_status=%s\n' "$(latest_status)"
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
    return 0
  fi

  local api api_image dsn env_file manifest_sha worker_state proof
  require_search_prerequisite
  api="$(active_api_container)"
  api_image="$(docker inspect -f '{{.Config.Image}}' "$api")"
  [ -n "$api_image" ] || fail "active API image identity is empty"
  dsn="$(api_database_url "$api")"
  require_archiver_healthy
  run_capacity_gate
  manifest_sha="$(expected_manifest_sha256)" \
    || fail "complete-read expected Archetype manifest is invalid"
  [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] \
    || fail "complete-read expected Archetype manifest digest is invalid"
  write_build_start_receipt "$manifest_sha"

  if docker inspect "$WORKER" >/dev/null 2>&1; then
    worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
    if [ "$worker_state" = "running" ]; then
      printf 'operation=v3-system-archetype-start\nresult=already-running\nworker=%s\n' "$WORKER"
      emit_receipt_status
      printf 'latest_status=%s\n' "$(latest_status)"
      printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
      return 0
    fi
    preserve_worker_log
    docker rm "$WORKER" >/dev/null
  fi

  env_file="$STATE_ROOT/archetype.env"
  write_builder_env "$env_file" "$dsn" "$manifest_sha"
  trap 'rm -f -- "$env_file"' EXIT
  # Chunks a previous worker already committed are not proof for this launch:
  # record them, and require this worker to commit at least one more.
  local baseline_chunks
  baseline_chunks="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.archetype_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  [[ "$baseline_chunks" =~ ^[0-9]+$ ]] || fail "Archetype baseline chunk query was invalid"
  local planned_chunks validation_only=false result=launched
  planned_chunks="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  [[ "$planned_chunks" =~ ^[1-9][0-9]*$ ]] || fail "Archetype planned chunk query was invalid"
  [ "$baseline_chunks" -le "$planned_chunks" ] \
    || fail "Archetype has more committed chunks than the Ratings chunk plan"
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
        --find-links /work/.v3-archetype-wheelhouse --target /tmp/v3-archetype-deps \
        --require-hashes -r /work/deploy/v3-production/f2d-wheels.txt 1>&2
      export PYTHONPATH="/tmp/v3-archetype-deps:/work:/work/apps/api/src"
      cd /work
      /app/.venv/bin/python -c "from pathlib import Path; from scripts.v3_archetype_calibration_complete import require_image_model_match; require_image_model_match(Path(\"/app/shared_contracts/v3_system_archetype_model.py\"))"
      exec /app/.venv/bin/python scripts/v3_system_archetype.py \
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
    # Validation-only resume (every chunk already sealed): the worker re-reads
    # and re-scores every chunk for hours, so it is left running and finalize
    # requires its clean exit; a quick clean exit means it was already READY.
    if [ "$worker_state" = "running" ]; then
      result=launched-validation-only
    elif [ "$worker_state" = "exited" ] \
      && [ "$(docker inspect -f '{{.State.ExitCode}}' "$WORKER")" = "0" ]; then
      result=validated
    else
      docker logs --tail 80 "$WORKER" >&2 || true
      preserve_worker_log
      fail "Archetype validation-only worker did not exit successfully"
    fi
  elif [ "$worker_state" != "running" ]; then
    docker logs --tail 80 "$WORKER" >&2 || true
    preserve_worker_log
    fail "Archetype worker did not remain running"
  fi
  # The worker must prove itself within ten minutes: a resume first installs
  # wheels, registers, lists ~198k chunks and reads a cold first chunk.
  for _ in $(seq 1 300); do
    [ "$validation_only" = false ] || break
    proof="$(db_query "BEGIN READ ONLY; SELECT count(*) FROM v3_derived.archetype_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
    [[ "$proof" =~ ^[0-9]+$ ]] || fail "Archetype proof query was invalid"
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
    fail "Archetype worker did not prove a chunk committed by this launch; the worker was stopped"
  fi

  printf 'operation=v3-system-archetype-start\nresult=%s\n' "$result"
  printf 'planned_chunks=%s\n' "$planned_chunks"

  printf 'source_sha=%s\ngeneration_key=%s\ngeneration_id=%s\n' \
    "$SOURCE_SHA" "$TARGET_GENERATION_KEY" "$TARGET_GENERATION_ID"
  printf 'manifest_sha256=%s\nworker=%s\nworker_state=%s\nproof_chunks=%s\nbaseline_chunks=%s\n' \
    "$manifest_sha" "$WORKER" "$worker_state" "$proof" "$baseline_chunks"
  printf 'migration_011_sha256=%s\nmigration_015_sha256=%s\n' \
    "$MIGRATION_011_SHA" "$MIGRATION_015_SHA"
  emit_receipt_status
  printf 'latest_status=%s\n' "$(latest_status)"
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

status_operation() {
  require_target
  require_stage
  require_generation
  printf 'operation=v3-system-archetype-status\nworker_containers:\n'
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
  require_purge_clear "v3-system-archetype-finalize"
  require_stage
  require_archetype_schema
  require_generation
  install -d -m 700 "$STATE_ROOT"
  command -v flock >/dev/null 2>&1 || fail "flock is unavailable"
  exec 9>"$STATE_ROOT/finalize.lock"
  flock -n 9 || fail "another V3 Archetype finalize is in progress"

  local worker_state worker_exit manifest_sha expected_manifest
  local product_row lifecycle validation registered_manifest expected_rows wide_rows
  local chunk_row final_insert_at chunk_count row_count stats last_vacuum last_analyze vacuum_performed=false
  require_search_prerequisite
  [ -f "$STATE_ROOT/build-start-receipt.json" ] && [ ! -L "$STATE_ROOT/build-start-receipt.json" ] \
    || fail "Archetype build-start receipt is missing"
  manifest_sha="$(PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$STATE_ROOT/build-start-receipt.json" "$TARGET_GENERATION_ID" "$F2D_IDENTITY" <<'PY'
import sys
from scripts.operator.lib.f2d_evidence import load_sealed
receipt = load_sealed(sys.argv[1])
if (receipt.get('schema_version') != 'ed-finder/v3-build-start-receipt/v1'
        or receipt.get('product_code') != 'system_archetype'
        or receipt.get('derived_generation_id') != sys.argv[2]
        or receipt.get('f2d_operator_code_sha256') != sys.argv[3]):
    raise SystemExit(1)
print(receipt.get('manifest_sha256', ''))
PY
  )" || fail "Archetype build-start receipt is invalid"
  [[ "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] \
    || fail "Archetype build-start manifest digest is invalid"
  expected_manifest="$(expected_manifest_sha256)" \
    || fail "complete-read expected Archetype manifest is invalid"
  [ "$manifest_sha" = "$expected_manifest" ] \
    || fail "Archetype build-start manifest differs from the complete read"

  docker inspect "$WORKER" >/dev/null 2>&1 || fail "Archetype worker container is missing"
  worker_state="$(docker inspect -f '{{.State.Status}}' "$WORKER")"
  worker_exit="$(docker inspect -f '{{.State.ExitCode}}' "$WORKER")"
  if [ "$worker_state" = "running" ]; then
    fail "Archetype worker is still running (building or validating); finalize after it exits"
  fi
  [ "$worker_state" = "exited" ] && [ "$worker_exit" = "0" ] \
    || { preserve_worker_log; fail "Archetype worker has not exited successfully (state=${worker_state} exit=${worker_exit})"; }

  product_row="$(db_query "BEGIN READ ONLY; SELECT p.lifecycle_state || E'\\t' || COALESCE(p.validation_receipt->>'status','') || E'\\t' || encode(p.manifest_sha256,'hex') || E'\\t' || p.expected_rows::text || E'\\t' || (SELECT count(*)::text FROM v3_derived.system_archetype a WHERE a.derived_generation_id=p.derived_generation_id) FROM v3_meta.derived_product p WHERE p.derived_generation_id='${TARGET_GENERATION_ID}'::uuid AND p.product_code='system_archetype'; COMMIT;")"
  IFS=$'\t' read -r lifecycle validation registered_manifest expected_rows wide_rows <<< "$product_row"
  [ "$lifecycle" = "READY" ] && [ "$validation" = "VERIFIED" ] \
    || fail "Archetype product is not READY/VERIFIED"
  [ "$registered_manifest" = "$manifest_sha" ] \
    || fail "Archetype registered manifest differs from the build-start receipt"
  [ "$expected_rows" = "$TARGET_EXPECTED_SYSTEMS" ] \
    && [ "$wide_rows" = "$TARGET_EXPECTED_SYSTEMS" ] \
    || fail "Archetype wide-row count differs from the generation expected systems"

  chunk_row="$(db_query "BEGIN READ ONLY; SELECT max(completed_at)::text || E'\\t' || count(*)::text || E'\\t' || COALESCE(sum(systems),0)::text FROM v3_derived.archetype_build_chunk WHERE derived_generation_id='${TARGET_GENERATION_ID}'::uuid; COMMIT;")"
  IFS=$'\t' read -r final_insert_at chunk_count row_count <<< "$chunk_row"
  [ -n "$final_insert_at" ] && [[ "$chunk_count" =~ ^[1-9][0-9]*$ ]] \
    && [ "$row_count" = "$TARGET_EXPECTED_SYSTEMS" ] \
    || fail "Archetype final-insert receipt coverage is invalid"

  stats="$(db_query "BEGIN READ ONLY; SELECT COALESCE(last_vacuum::text,'') || E'\\t' || COALESCE(last_analyze::text,'') FROM pg_stat_user_tables WHERE schemaname='v3_derived' AND relname='system_archetype'; COMMIT;")"
  IFS=$'\t' read -r last_vacuum last_analyze <<< "$stats"
  if [ "$(archetype_vacuum_is_current)" != "true" ]; then
    mark_db_writes_possible
    db_maintenance "VACUUM (ANALYZE) v3_derived.system_archetype;"
    vacuum_performed=true
    stats="$(db_query "BEGIN READ ONLY; SELECT COALESCE(last_vacuum::text,'') || E'\\t' || COALESCE(last_analyze::text,'') FROM pg_stat_user_tables WHERE schemaname='v3_derived' AND relname='system_archetype'; COMMIT;")"
    IFS=$'\t' read -r last_vacuum last_analyze <<< "$stats"
  fi
  [ "$(archetype_vacuum_is_current)" = "true" ] \
    || fail "Archetype vacuum/analyze timestamps do not postdate the final insert"

  PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" - "$STATE_ROOT/build-final-receipt.json" \
    "$TARGET_GENERATION_ID" "$manifest_sha" "$final_insert_at" "$last_vacuum" \
    "$last_analyze" "$chunk_count" "$row_count" "$lifecycle" "$validation" \
    "$F2D_IDENTITY" "$vacuum_performed" <<'PY' \
    || fail "Archetype build-final receipt could not be written"
import os
from pathlib import Path
import sys
from scripts.operator.lib.f2d_evidence import canonical_json, seal

(path, identifier, manifest, final_insert, last_vacuum, last_analyze,
 chunk_count, row_count, lifecycle, validation, identity, performed) = sys.argv[1:]
body = {
    'schema_version': 'ed-finder/v3-build-final-receipt/v1',
    'product_code': 'system_archetype',
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
  printf 'operation=v3-system-archetype-finalize\nstatus=completed\n'
  emit_receipt_status
  printf 'publication_performed=false\ncanonical_writes_performed=false\napplication_service_changes_performed=false\n'
}

case "$ACTION" in
  start) start_operation ;;
  status) status_operation ;;
  finalize) finalize_operation ;;
  *) fail "expected start, status, or finalize" ;;
esac
